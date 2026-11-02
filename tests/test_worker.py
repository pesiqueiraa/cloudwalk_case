import httpx

from helpdesk.config import Settings
from helpdesk.platform.ingestion import ingest_chat
from helpdesk.platform.worker import deliver_once
from tests.factories import chat_inbound

SETTINGS = Settings(database_url="unused", broker_url="http://broker.test", webhook_max_attempts=5)


def client_with(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def job(db):
    return db.execute("SELECT * FROM webhook_jobs").fetchone()


def audit_types(db):
    return [r["type"] for r in db.execute("SELECT type FROM audit_events ORDER BY id")]


def test_delivers_and_audits(db):
    result = ingest_chat(db, chat_inbound())
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(202)

    assert deliver_once(db, client_with(handler), SETTINGS) == 1

    assert job(db)["status"] == "done"
    assert sent[0].url == "http://broker.test/webhooks/agent-requests"
    assert sent[0].headers["X-Trace-Id"] == str(result.trace_id)
    events = db.execute("SELECT * FROM audit_events WHERE type = 'message.sent_to_agent'").fetchall()
    assert [(e["trace_id"], e["payload"]) for e in events] == [(result.trace_id, {"attempt": 1})]


def test_broker_down_keeps_job_pending(db):
    ingest_chat(db, chat_inbound())

    def handler(request):
        raise httpx.ConnectError("broker fora do ar")

    deliver_once(db, client_with(handler), SETTINGS)

    row = db.execute("SELECT *, next_attempt_at > now() AS in_future FROM webhook_jobs").fetchone()
    assert row["status"] == "pending"
    assert row["attempts"] == 1
    assert row["in_future"] is True
    assert "broker fora do ar" in row["last_error"]
    assert "message.sent_to_agent" not in audit_types(db)


def test_non_2xx_is_retried(db):
    ingest_chat(db, chat_inbound())
    deliver_once(db, client_with(lambda r: httpx.Response(503)), SETTINGS)
    assert (job(db)["status"], job(db)["attempts"]) == ("pending", 1)


def test_gives_up_after_max_attempts(db):
    ingest_chat(db, chat_inbound())
    settings = SETTINGS.model_copy(update={"webhook_max_attempts": 2})
    failing = client_with(lambda r: httpx.Response(500))

    deliver_once(db, failing, settings)
    db.execute("UPDATE webhook_jobs SET next_attempt_at = now()")
    deliver_once(db, failing, settings)

    assert (job(db)["status"], job(db)["attempts"]) == ("failed", 2)


def test_not_due_job_is_skipped(db):
    ingest_chat(db, chat_inbound())
    db.execute("UPDATE webhook_jobs SET next_attempt_at = now() + interval '1 hour'")
    assert deliver_once(db, client_with(lambda r: httpx.Response(202)), SETTINGS) == 0


def test_preserves_order_within_conversation(db):
    first = ingest_chat(db, chat_inbound(session_id="sess-1", message_id="m-1"))
    ingest_chat(db, chat_inbound(session_id="sess-1", message_id="m-2"))
    sent = []

    def broker_down(request):
        sent.append(request)
        raise httpx.ConnectError("broker fora do ar")

    deliver_once(db, client_with(broker_down), SETTINGS)

    # Só a primeira mensagem da conversa pode ser tentada; a segunda espera atrás dela
    assert len(sent) == 1
    assert sent[0].headers["X-Trace-Id"] == str(first.trace_id)
    attempts = [r["attempts"] for r in db.execute("SELECT attempts FROM webhook_jobs ORDER BY id")]
    assert attempts == [1, 0]


def test_other_conversations_are_not_blocked(db):
    ingest_chat(db, chat_inbound(session_id="sess-1", message_id="m-1"))
    ingest_chat(db, chat_inbound(session_id="sess-2", message_id="m-1"))
    sent = []

    def handler(request):
        sent.append(request)
        raise httpx.ConnectError("broker fora do ar")

    deliver_once(db, client_with(handler), SETTINGS)
    assert len(sent) == 2


def test_failed_job_does_not_block_the_next(db):
    ingest_chat(db, chat_inbound(session_id="sess-1", message_id="m-1"))
    second = ingest_chat(db, chat_inbound(session_id="sess-1", message_id="m-2"))
    db.execute("UPDATE webhook_jobs SET status = 'failed' WHERE id = (SELECT min(id) FROM webhook_jobs)")

    deliver_once(db, client_with(lambda r: httpx.Response(202)), SETTINGS)

    job = db.execute("SELECT status FROM webhook_jobs WHERE trace_id = %s", (second.trace_id,)).fetchone()
    assert job["status"] == "done"


def test_giving_up_is_audited(db):
    result = ingest_chat(db, chat_inbound())
    settings = SETTINGS.model_copy(update={"webhook_max_attempts": 1})

    deliver_once(db, client_with(lambda r: httpx.Response(500)), settings)

    events = db.execute("SELECT * FROM audit_events WHERE type = 'message.delivery_failed'").fetchall()
    assert [(e["trace_id"], e["payload"]["attempts"]) for e in events] == [(result.trace_id, 1)]


def test_default_retry_budget_covers_minutes():
    attempts = Settings(database_url="unused").webhook_max_attempts
    # Esperas entre tentativas: 2, 4, 8, ... até 60 s cada
    budget = sum(min(2 ** n, 60) for n in range(1, attempts))
    assert budget >= 300


def test_connect_with_retry_survives_slow_database():
    import psycopg

    from helpdesk.platform.worker import connect_with_retry

    calls = []

    def flaky_connect(url):
        calls.append(url)
        if len(calls) < 3:
            raise psycopg.OperationalError("postgres subindo")
        return "conn"

    assert connect_with_retry("db-url", connect_fn=flaky_connect, sleep=lambda s: None) == "conn"
    assert len(calls) == 3


def test_cancelled_job_is_not_delivered(db):
    from helpdesk.platform import outbox

    ingested = ingest_chat(db, chat_inbound())
    cancelled = outbox.cancel_pending(db, ingested.conversation_id)
    assert [j.trace_id for j in cancelled] == [ingested.trace_id]
    assert outbox.cancel_pending(db, ingested.conversation_id) == []

    calls = []
    assert deliver_once(db, client_with(lambda r: calls.append(r) or httpx.Response(202)), SETTINGS) == 0
    assert calls == []
    assert job(db)["status"] == "cancelled"
