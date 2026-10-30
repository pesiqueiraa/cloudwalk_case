"""Eventos de auditoria append-only: um por efeito relevante, sempre com trace_id."""
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb


def record(conn: psycopg.Connection, *, type: str, trace_id: UUID, conversation_id: UUID,
           actor: str, payload: dict) -> None:
    conn.execute(
        """
        INSERT INTO audit_events (trace_id, conversation_id, type, actor, payload)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (trace_id, conversation_id, type, actor, Jsonb(payload)),
    )


def list_by_trace(conn: psycopg.Connection, trace_id: UUID) -> list[dict]:
    return conn.execute(
        "SELECT * FROM audit_events WHERE trace_id = %s ORDER BY id", (trace_id,)
    ).fetchall()


def list_by_conversation(conn: psycopg.Connection, conversation_id: UUID) -> list[dict]:
    return conn.execute(
        "SELECT * FROM audit_events WHERE conversation_id = %s ORDER BY id", (conversation_id,)
    ).fetchall()
