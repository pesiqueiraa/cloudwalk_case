"""platform-worker: envia os webhooks pendentes ao broker, fora da requisição de entrada."""
import logging
import time

import httpx
import psycopg

from helpdesk.config import Settings, get_settings
from helpdesk.logs import configure_logging
from helpdesk.platform import audit, outbox
from helpdesk.platform.db import connect

log = logging.getLogger(__name__)

BATCH_SIZE = 10


def deliver_once(conn: psycopg.Connection, client: httpx.Client, settings: Settings) -> int:
    """Processa até BATCH_SIZE jobs vencidos, cada um na sua transação. Devolve quantos processou."""
    processed = 0
    while processed < BATCH_SIZE:
        with conn.transaction():
            jobs = outbox.claim_due(conn, limit=1)
            if not jobs:
                break
            _deliver(conn, client, settings, jobs[0])
        processed += 1
    return processed


def _deliver(conn: psycopg.Connection, client: httpx.Client, settings: Settings, job: outbox.Job) -> None:
    attempt = job.attempts + 1
    context = {"trace_id": job.trace_id, "event_id": job.event_id, "attempt": attempt}
    try:
        response = client.post(
            f"{settings.broker_url}/webhooks/agent-requests",
            json=job.payload,
            headers={"X-Trace-Id": str(job.trace_id)},
            timeout=5,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        gave_up = outbox.mark_retry(conn, job.id, f"{type(exc).__name__}: {exc}", settings.webhook_max_attempts)
        if not gave_up:
            log.warning("falha ao enviar webhook", extra={**context, "error": str(exc)})
            return
        # Fica como 'failed' em webhook_jobs, para a DLQ da semana 3 reprocessar
        audit.record(
            conn, type="message.delivery_failed", trace_id=job.trace_id,
            conversation_id=job.payload["conversation_id"], actor="platform-worker",
            payload={"attempts": attempt, "error": str(exc)},
        )
        log.error("webhook desistiu depois de todas as tentativas", extra={**context, "error": str(exc)})
        return

    outbox.mark_done(conn, job.id)
    audit.record(
        conn, type="message.sent_to_agent", trace_id=job.trace_id,
        conversation_id=job.payload["conversation_id"], actor="platform-worker",
        payload={"attempt": attempt},
    )
    log.info("webhook enviado", extra=context)


def connect_with_retry(url: str, connect_fn=connect, sleep=time.sleep) -> psycopg.Connection:
    """Tenta conectar até o banco responder, com espera crescente (até 10 s)."""
    attempt = 0
    while True:
        try:
            return connect_fn(url)
        except psycopg.OperationalError as exc:
            attempt += 1
            log.warning("banco indisponível; tentando de novo", extra={"attempt": attempt, "error": str(exc)})
            sleep(min(attempt, 10))


def main() -> None:
    configure_logging("platform-worker")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = get_settings()
    conn = connect_with_retry(settings.database_url)
    with httpx.Client() as client:
        while True:
            try:
                processed = deliver_once(conn, client, settings)
            except psycopg.OperationalError:
                log.exception("erro de banco; reconectando")
                conn.close()
                conn = connect_with_retry(settings.database_url)
                continue
            if processed == 0:
                time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
