"""Fila de envio do webhook (outbox), gravada na mesma transação da mensagem."""
from dataclasses import dataclass
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from helpdesk.contracts import AgentRequest


def enqueue(conn: psycopg.Connection, request: AgentRequest) -> None:
    conn.execute(
        "INSERT INTO webhook_jobs (event_id, trace_id, conversation_id, payload) VALUES (%s, %s, %s, %s)",
        (request.event_id, request.trace_id, request.conversation_id, Jsonb(request.model_dump(mode="json"))),
    )


@dataclass(frozen=True)
class Job:
    id: int
    event_id: UUID
    trace_id: UUID
    payload: dict
    attempts: int


def claim_due(conn: psycopg.Connection, limit: int = 10) -> list[Job]:
    """Trava jobs vencidos até o fim da transação; outro worker pula os travados.

    Só o job pendente mais antigo de cada conversa pode sair: se ele está esperando o
    backoff, os de trás esperam também, e a ordem da conversa chega intacta ao Kafka.
    Um job 'failed' não segura os seguintes.
    """
    rows = conn.execute(
        """
        SELECT j.id, j.event_id, j.trace_id, j.payload, j.attempts FROM webhook_jobs j
        WHERE j.status = 'pending' AND j.next_attempt_at <= now()
          AND NOT EXISTS (
              SELECT 1 FROM webhook_jobs earlier
              WHERE earlier.conversation_id = j.conversation_id
                AND earlier.status = 'pending' AND earlier.id < j.id
          )
        ORDER BY j.id
        LIMIT %s
        FOR UPDATE SKIP LOCKED
        """,
        (limit,),
    ).fetchall()
    return [Job(**row) for row in rows]


def mark_done(conn: psycopg.Connection, job_id: int) -> None:
    conn.execute(
        "UPDATE webhook_jobs SET status = 'done', attempts = attempts + 1 WHERE id = %s", (job_id,)
    )


def mark_retry(conn: psycopg.Connection, job_id: int, error: str, max_attempts: int) -> bool:
    """Backoff exponencial (2, 4, 8... até 60 s); depois de max_attempts, o job fica 'failed'.

    Devolve True quando o job desistiu.
    """
    row = conn.execute(
        """
        UPDATE webhook_jobs SET
            attempts = attempts + 1,
            last_error = %s,
            status = CASE WHEN attempts + 1 >= %s THEN 'failed' ELSE 'pending' END,
            next_attempt_at = now() + make_interval(secs => least(power(2, attempts + 1), 60))
        WHERE id = %s
        RETURNING status
        """,
        (error, max_attempts, job_id),
    ).fetchone()
    return row["status"] == "failed"
