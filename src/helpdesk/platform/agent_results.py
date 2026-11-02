"""Aplica na plataforma o resultado do agente que o broker entrega pelo callback.

Três desfechos possíveis:
- applied: resposta gravada (e, se for escalação, handoff feito);
- duplicate: esse event_id já tinha sido aplicado;
- discarded: a conversa já está com humano ou encerrada; a resposta é guardada e auditada, nunca entregue.
"""
from typing import Literal
from uuid import UUID

import psycopg

from helpdesk.contracts import AgentResult
from helpdesk.platform import audit, outbox

Outcome = Literal["applied", "duplicate", "discarded"]


class ConversationNotFound(Exception):
    pass


class ResultMismatch(Exception):
    """O resultado não responde a uma mensagem de entrada desta conversa, com o mesmo trace_id."""


def apply_agent_result(conn: psycopg.Connection, result: AgentResult) -> Outcome:
    with conn.transaction():
        # A trava serializa callback e handoff da mesma conversa
        conversation = conn.execute(
            "SELECT id, queue_id, handled_by, status FROM conversations WHERE id = %s FOR UPDATE",
            (result.conversation_id,),
        ).fetchone()
        if conversation is None:
            raise ConversationNotFound(result.conversation_id)
        _check_origin(conn, result)

        # Antes do descarte: a reentrega da própria escalação é duplicata, não resposta tardia
        if conn.execute("SELECT 1 FROM messages WHERE source_event_id = %s", (result.event_id,)).fetchone():
            return "duplicate"
        if conversation["status"] == "closed":
            return _discard(conn, result, "conversation_closed")
        if conversation["handled_by"] == "human":
            return _discard(conn, result, "handed_off_to_human")

        inserted = conn.execute(
            """
            INSERT INTO messages (conversation_id, trace_id, direction, author, text, source_event_id)
            VALUES (%s, %s, 'out', 'agent', %s, %s)
            ON CONFLICT (source_event_id) DO NOTHING
            RETURNING id
            """,
            (result.conversation_id, result.trace_id, result.text, result.event_id),
        ).fetchone()
        if inserted is None:
            return "duplicate"

        audit.record(
            conn, type="agent.replied", trace_id=result.trace_id, conversation_id=result.conversation_id,
            actor="agent-mock",
            payload={"event_id": str(result.event_id), "message_id": str(inserted["id"])},
        )
        if result.event_type == "agent.escalated":
            _hand_off(conn, result, conversation)
        return "applied"


def _check_origin(conn: psycopg.Connection, result: AgentResult) -> None:
    origin = conn.execute(
        "SELECT trace_id FROM messages WHERE id = %s AND conversation_id = %s AND direction = 'in'",
        (result.in_reply_to, result.conversation_id),
    ).fetchone()
    if origin is None:
        raise ResultMismatch(f"in_reply_to {result.in_reply_to} não é mensagem de entrada desta conversa")
    if origin["trace_id"] != result.trace_id:
        raise ResultMismatch(f"trace_id {result.trace_id} difere do trace_id da mensagem respondida")


def _hand_off(conn: psycopg.Connection, result: AgentResult, conversation: dict) -> None:
    """Troca o dono para humano, move para a fila de escalas (se a fila tiver uma ativa) e
    cancela o que ainda ia para o agente."""
    from_queue: UUID | None = conversation["queue_id"]
    target = conn.execute(
        """
        SELECT e.id, e.name FROM queues q JOIN queues e ON e.id = q.escalation_queue_id AND e.active
        WHERE q.id = %s
        """,
        (from_queue,),
    ).fetchone()
    to_queue = target["id"] if target else from_queue

    conn.execute(
        """
        UPDATE conversations SET status = 'escalated', handled_by = 'human', queue_id = %s,
               escalated_at = now(), escalation_reason = %s, escalation_summary = %s
        WHERE id = %s
        """,
        (to_queue, result.reason, result.summary, result.conversation_id),
    )
    cancelled = outbox.cancel_pending(conn, result.conversation_id)
    audit.record(
        conn, type="conversation.escalated", trace_id=result.trace_id,
        conversation_id=result.conversation_id, actor="agent-mock",
        payload={
            "reason": result.reason, "summary": result.summary,
            "from_queue_id": str(from_queue) if from_queue else None,
            "to_queue_id": str(to_queue) if to_queue else None,
            "to_queue_name": target["name"] if target else None,
            "cancelled_jobs": len(cancelled),
        },
    )
    # Cada mensagem que não chegou ao agente fica com a equipe, sob o trace_id dela
    for job in cancelled:
        audit.record(
            conn, type="message.held_for_human", trace_id=job.trace_id,
            conversation_id=result.conversation_id, actor="platform",
            payload={"queue_id": str(to_queue) if to_queue else None, "cause": "handoff",
                     "job_event_id": str(job.event_id)},
        )


def _discard(conn: psycopg.Connection, result: AgentResult, reason: str) -> Outcome:
    inserted = conn.execute(
        """
        INSERT INTO discarded_agent_results (event_id, conversation_id, trace_id, in_reply_to, event_type, text, reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (event_id) DO NOTHING
        RETURNING event_id
        """,
        (result.event_id, result.conversation_id, result.trace_id, result.in_reply_to,
         result.event_type, result.text, reason),
    ).fetchone()
    if inserted is None:
        return "duplicate"
    audit.record(
        conn, type="agent.reply_discarded", trace_id=result.trace_id, conversation_id=result.conversation_id,
        actor="platform",
        payload={"event_id": str(result.event_id), "event_type": result.event_type, "reason": reason,
                 "in_reply_to": str(result.in_reply_to)},
    )
    return "discarded"
