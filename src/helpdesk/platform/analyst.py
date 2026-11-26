"""API do analista: fila de escalas, assumir, responder e encerrar casos, com a memória do cliente.

Sem login (fora de escopo): o analista se identifica pelo analyst_id no corpo da requisição.
"""
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from helpdesk.contracts import Brand, Text
from helpdesk.platform import audit, outbox
from helpdesk.platform.deps import get_conn

router = APIRouter(tags=["analista"])

CONVERSATION_VIEW = """
    SELECT c.*, cu.name AS customer_name, cu.external_id AS customer_external_id,
           q.name AS queue_name, q.team_id, a.name AS assigned_analyst_name
    FROM conversations c
    JOIN customers cu ON cu.id = c.customer_id
    LEFT JOIN queues q ON q.id = c.queue_id
    LEFT JOIN analysts a ON a.id = c.assigned_analyst_id
"""


class AnalystAction(BaseModel):
    analyst_id: UUID


class AnalystMessage(BaseModel):
    analyst_id: UUID
    text: Text


@router.get("/api/escalations")
def list_escalations(team_id: str | None = None, brand: Brand | None = None,
                     conn: psycopg.Connection = Depends(get_conn)) -> list[dict]:
    """Casos com a equipe humana ainda abertos: não assumidos primeiro, depois prioridade alta,
    depois o que espera há mais tempo."""
    return conn.execute(
        CONVERSATION_VIEW + """
        WHERE c.handled_by = 'human' AND c.status <> 'closed'
          AND (%(team)s::text IS NULL OR q.team_id = %(team)s)
          AND (%(brand)s::text IS NULL OR c.brand_id = %(brand)s)
        ORDER BY (c.assigned_analyst_id IS NULL) DESC, (c.priority = 'high') DESC,
                 coalesce(c.escalated_at, c.routed_at, c.created_at), c.id
        """,
        {"team": team_id, "brand": brand},
    ).fetchall()


@router.get("/api/conversations")
def list_conversations(brand: Brand | None = None, status: str | None = None, handled_by: str | None = None,
                       limit: int = 50, conn: psycopg.Connection = Depends(get_conn)) -> list[dict]:
    """Conversas com atividade mais recente primeiro."""
    return conn.execute(
        """
        SELECT v.*, last.created_at AS last_message_at, last.text AS last_message_text,
               mood.frustration AS last_customer_frustration
        FROM (""" + CONVERSATION_VIEW + """) v
        LEFT JOIN LATERAL (
            SELECT created_at, text FROM messages WHERE conversation_id = v.id ORDER BY created_at DESC, id DESC LIMIT 1
        ) last ON true
        -- Como o cliente está agora (Jev): a lista destaca quem está frustrado. Nulo com as regras
        LEFT JOIN LATERAL (
            SELECT frustration FROM messages
            WHERE conversation_id = v.id AND author = 'customer' AND frustration IS NOT NULL
            ORDER BY created_at DESC, id DESC LIMIT 1
        ) mood ON true
        WHERE (%(brand)s::text IS NULL OR v.brand_id = %(brand)s)
          AND (%(status)s::text IS NULL OR v.status = %(status)s)
          AND (%(handled_by)s::text IS NULL OR v.handled_by = %(handled_by)s)
        ORDER BY coalesce(last.created_at, v.created_at) DESC, v.id
        LIMIT %(limit)s
        """,
        {"brand": brand, "status": status, "handled_by": handled_by, "limit": max(1, min(limit, 200))},
    ).fetchall()


@router.get("/api/cases/{conversation_id}")
def get_case(conversation_id: UUID, conn: psycopg.Connection = Depends(get_conn)) -> dict:
    """Tudo o que o analista precisa: resumo, conversa, auditoria e atendimentos anteriores do cliente."""
    conversation = conn.execute(CONVERSATION_VIEW + " WHERE c.id = %s", (conversation_id,)).fetchone()
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    messages = conn.execute(
        "SELECT * FROM messages WHERE conversation_id = %s ORDER BY created_at, id", (conversation_id,)
    ).fetchall()
    previous = conn.execute(
        """
        SELECT c.id, c.channel, c.status, c.created_at, c.closed_at, c.escalation_summary, c.escalation_reason,
               q.name AS queue_name, a.name AS assigned_analyst_name,
               (SELECT count(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count,
               (SELECT text FROM messages m WHERE m.conversation_id = c.id AND m.direction = 'in'
                ORDER BY m.created_at, m.id LIMIT 1) AS first_message_text
        FROM conversations c
        LEFT JOIN queues q ON q.id = c.queue_id
        LEFT JOIN analysts a ON a.id = c.assigned_analyst_id
        WHERE c.customer_id = %s AND c.id <> %s
        ORDER BY c.created_at DESC, c.id
        LIMIT 20
        """,
        (conversation["customer_id"], conversation_id),
    ).fetchall()
    return {
        "conversation": conversation,
        "messages": messages,
        "audit": audit.list_by_conversation(conn, conversation_id),
        "previous_conversations": previous,
    }


@router.post("/api/conversations/{conversation_id}/assign")
def assign(conversation_id: UUID, body: AnalystAction, conn: psycopg.Connection = Depends(get_conn)) -> dict:
    with conn.transaction():
        conversation = _lock_human_conversation(conn, conversation_id)
        analyst = conn.execute("SELECT * FROM analysts WHERE id = %s", (body.analyst_id,)).fetchone()
        if analyst is None:
            raise HTTPException(status_code=422, detail=f"analista inexistente: {body.analyst_id}")
        team = conn.execute("SELECT team_id FROM queues WHERE id = %s", (conversation["queue_id"],)).fetchone()
        if team is None or analyst["team_id"] != team["team_id"]:
            raise HTTPException(status_code=422, detail="o analista não é da equipe da fila da conversa")

        current = conversation["assigned_analyst_id"]
        if current == body.analyst_id:
            return _view(conn, conversation_id)  # já é dele: sem evento novo
        if current is not None:
            raise HTTPException(status_code=409, detail="caso já assumido por outro analista")

        conn.execute(
            "UPDATE conversations SET assigned_analyst_id = %s, assigned_at = now() WHERE id = %s",
            (body.analyst_id, conversation_id),
        )
        audit.record(
            conn, type="conversation.assigned", trace_id=_latest_trace(conn, conversation_id),
            conversation_id=conversation_id, actor=f"analyst:{body.analyst_id}",
            payload={"analyst_id": str(body.analyst_id), "analyst_name": analyst["name"],
                     "team_id": analyst["team_id"], "queue_id": str(conversation["queue_id"])},
        )
        return _view(conn, conversation_id)


@router.post("/api/conversations/{conversation_id}/messages", status_code=201)
def reply(conversation_id: UUID, body: AnalystMessage, conn: psycopg.Connection = Depends(get_conn)) -> dict:
    with conn.transaction():
        _lock_assigned_to(conn, conversation_id, body.analyst_id)
        # A resposta continua o trace da última mensagem do cliente
        trace_id = _latest_trace(conn, conversation_id)
        message = conn.execute(
            """
            INSERT INTO messages (conversation_id, trace_id, direction, author, text)
            VALUES (%s, %s, 'out', 'analyst', %s) RETURNING *
            """,
            (conversation_id, trace_id, body.text),
        ).fetchone()
        audit.record(
            conn, type="analyst.replied", trace_id=trace_id, conversation_id=conversation_id,
            actor=f"analyst:{body.analyst_id}", payload={"message_id": str(message["id"])},
        )
        return message


@router.post("/api/conversations/{conversation_id}/close")
def close(conversation_id: UUID, body: AnalystAction, conn: psycopg.Connection = Depends(get_conn)) -> dict:
    with conn.transaction():
        _lock_assigned_to(conn, conversation_id, body.analyst_id)
        conn.execute(
            "UPDATE conversations SET status = 'closed', closed_at = now() WHERE id = %s", (conversation_id,)
        )
        cancelled = outbox.cancel_pending(conn, conversation_id)
        audit.record(
            conn, type="conversation.closed", trace_id=_latest_trace(conn, conversation_id),
            conversation_id=conversation_id, actor=f"analyst:{body.analyst_id}",
            payload={"analyst_id": str(body.analyst_id), "cancelled_jobs": len(cancelled)},
        )
        return _view(conn, conversation_id)


def _lock_human_conversation(conn: psycopg.Connection, conversation_id: UUID) -> dict:
    conversation = conn.execute(
        "SELECT * FROM conversations WHERE id = %s FOR UPDATE", (conversation_id,)
    ).fetchone()
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    if conversation["status"] == "closed":
        raise HTTPException(status_code=409, detail="conversa encerrada")
    if conversation["handled_by"] != "human":
        raise HTTPException(status_code=409, detail="conversa está com o agente, não com a equipe humana")
    return conversation


def _lock_assigned_to(conn: psycopg.Connection, conversation_id: UUID, analyst_id: UUID) -> dict:
    conversation = _lock_human_conversation(conn, conversation_id)
    if conversation["assigned_analyst_id"] != analyst_id:
        raise HTTPException(status_code=409, detail="o caso não está assumido por este analista")
    return conversation


def _latest_trace(conn: psycopg.Connection, conversation_id: UUID) -> UUID:
    return conn.execute(
        """
        SELECT trace_id FROM messages WHERE conversation_id = %s AND direction = 'in'
        ORDER BY created_at DESC, id DESC LIMIT 1
        """,
        (conversation_id,),
    ).fetchone()["trace_id"]


def _view(conn: psycopg.Connection, conversation_id: UUID) -> dict:
    return conn.execute(CONVERSATION_VIEW + " WHERE c.id = %s", (conversation_id,)).fetchone()
