"""Handoff para humano: o mesmo caminho para quem escala (o agente, ou a própria triagem)."""
from uuid import UUID

import psycopg

from helpdesk.platform import audit, outbox


def escalate(conn: psycopg.Connection, *, conversation_id: UUID, from_queue: UUID | None, trace_id: UUID,
             reason: str, summary: str, actor: str, extra: dict | None = None) -> UUID | None:
    """Troca o dono para humano, move para a fila de escalas (se a fila tiver uma ativa) e cancela o que
    ainda ia para o agente. Chamar dentro da transação, com a conversa travada. Devolve a fila de destino."""
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
        (to_queue, reason, summary, conversation_id),
    )
    cancelled = outbox.cancel_pending(conn, conversation_id)
    audit.record(
        conn, type="conversation.escalated", trace_id=trace_id, conversation_id=conversation_id, actor=actor,
        payload={
            "reason": reason, "summary": summary,
            "from_queue_id": str(from_queue) if from_queue else None,
            "to_queue_id": str(to_queue) if to_queue else None,
            "to_queue_name": target["name"] if target else None,
            "cancelled_jobs": len(cancelled),
            **(extra or {}),
        },
    )
    # Cada mensagem que não chegou ao agente fica com a equipe, sob o trace_id dela
    for job in cancelled:
        audit.record(
            conn, type="message.held_for_human", trace_id=job.trace_id, conversation_id=conversation_id,
            actor="platform",
            payload={"queue_id": str(to_queue) if to_queue else None, "cause": "handoff",
                     "job_event_id": str(job.event_id)},
        )
    return to_queue
