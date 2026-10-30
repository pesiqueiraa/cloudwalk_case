"""Aplica na plataforma o resultado do agente que o broker entrega pelo callback."""
import psycopg

from helpdesk.contracts import AgentResult
from helpdesk.platform import audit


class ConversationNotFound(Exception):
    pass


def apply_agent_result(conn: psycopg.Connection, result: AgentResult) -> bool:
    """Grava a resposta do agente. Devolve False se esse event_id já tinha sido aplicado."""
    with conn.transaction():
        conversation = conn.execute(
            "SELECT id FROM conversations WHERE id = %s FOR UPDATE", (result.conversation_id,)
        ).fetchone()
        if conversation is None:
            raise ConversationNotFound(result.conversation_id)

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
            return False

        audit.record(
            conn, type="agent.replied", trace_id=result.trace_id, conversation_id=result.conversation_id,
            actor="agent-mock",
            payload={"event_id": str(result.event_id), "message_id": str(inserted["id"])},
        )
        if result.event_type == "agent.escalated":
            # Fila de escalas e bloqueio de resposta tardia entram na semana 3
            conn.execute("UPDATE conversations SET status = 'escalated' WHERE id = %s", (result.conversation_id,))
            audit.record(
                conn, type="conversation.escalated", trace_id=result.trace_id,
                conversation_id=result.conversation_id, actor="agent-mock",
                payload={"reason": result.reason},
            )
        return True
