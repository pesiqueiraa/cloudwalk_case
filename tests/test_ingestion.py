from helpdesk.platform.ingestion import ingest_chat
from tests.factories import chat_inbound


def count(db, sql, *params):
    return db.execute(sql, params).fetchone()["n"]


def test_ingest_creates_message_audit_and_job(db):
    result = ingest_chat(db, chat_inbound())

    message = db.execute("SELECT * FROM messages").fetchone()
    assert (message["direction"], message["author"]) == ("in", "customer")
    assert message["trace_id"] == result.trace_id

    events = db.execute("SELECT * FROM audit_events").fetchall()
    assert [(e["type"], e["trace_id"]) for e in events] == [("message.received", result.trace_id)]

    job = db.execute("SELECT * FROM webhook_jobs").fetchone()
    assert job["status"] == "pending"
    assert job["payload"]["trace_id"] == str(result.trace_id)
    assert job["payload"]["conversation_id"] == str(result.conversation_id)


def test_ingest_is_idempotent_by_channel_message_id(db):
    payload = chat_inbound()
    first = ingest_chat(db, payload)
    second = ingest_chat(db, payload)

    assert first.duplicate is False
    assert second.duplicate is True
    assert second.trace_id == first.trace_id
    assert second.message_id == first.message_id
    assert count(db, "SELECT count(*) AS n FROM messages") == 1
    assert count(db, "SELECT count(*) AS n FROM webhook_jobs") == 1
    assert count(db, "SELECT count(*) AS n FROM audit_events") == 1


def test_same_session_reuses_conversation(db):
    first = ingest_chat(db, chat_inbound(session_id="sess-1", message_id="m-1"))
    second = ingest_chat(db, chat_inbound(session_id="sess-1", message_id="m-2"))
    assert first.conversation_id == second.conversation_id
    assert first.trace_id != second.trace_id


def test_jim_request_has_en_us_locale(db):
    ingest_chat(db, chat_inbound(brand="jim", text="My card reader is off"))
    job = db.execute("SELECT payload FROM webhook_jobs").fetchone()
    assert job["payload"]["locale"] == "en-US"
    assert job["payload"]["brand"] == "jim"


def test_whatsapp_normalizes_and_ingests(db):
    from helpdesk.platform.ingestion import ingest, normalize_whatsapp
    from tests.factories import whatsapp_inbound

    result = ingest(db, normalize_whatsapp(whatsapp_inbound(from_phone="+5500900000009")))

    conversation = db.execute("SELECT * FROM conversations").fetchone()
    assert (conversation["channel"], conversation["external_session_id"]) == ("whatsapp", "+5500900000009")
    event = db.execute("SELECT payload FROM audit_events").fetchone()
    assert event["payload"]["channel"] == "whatsapp"
    job = db.execute("SELECT payload FROM webhook_jobs").fetchone()
    assert (job["payload"]["channel"], job["payload"]["trace_id"]) == ("whatsapp", str(result.trace_id))


def test_whatsapp_idempotent_by_wa_message_id(db):
    from helpdesk.platform.ingestion import ingest, normalize_whatsapp
    from tests.factories import whatsapp_inbound

    payload = whatsapp_inbound()
    ingest(db, normalize_whatsapp(payload))
    assert ingest(db, normalize_whatsapp(payload)).duplicate is True
    assert count(db, "SELECT count(*) AS n FROM webhook_jobs") == 1


def test_email_text_includes_subject(db):
    from helpdesk.platform.ingestion import ingest, normalize_email
    from tests.factories import email_inbound

    ingest(db, normalize_email(email_inbound(subject="Payout missing", body_text="Where is it?")))

    message = db.execute("SELECT text FROM messages").fetchone()
    assert message["text"] == "Payout missing\n\nWhere is it?"
    customer = db.execute("SELECT email FROM customers").fetchone()
    assert customer["email"] == "mary.sample@example.com"


def test_same_phone_on_two_brands_gets_two_conversations(db):
    from helpdesk.platform.ingestion import ingest, normalize_whatsapp
    from tests.factories import whatsapp_inbound

    ip = ingest(db, normalize_whatsapp(whatsapp_inbound(brand="infinitepay", from_phone="+5500900000007")))
    jim = ingest(db, normalize_whatsapp(whatsapp_inbound(brand="jim", from_phone="+5500900000007")))

    assert ip.conversation_id != jim.conversation_id
    brands = db.execute("SELECT id, brand_id FROM conversations").fetchall()
    assert {r["id"]: r["brand_id"] for r in brands} == {ip.conversation_id: "infinitepay", jim.conversation_id: "jim"}
