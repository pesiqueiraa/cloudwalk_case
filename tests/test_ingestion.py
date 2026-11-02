from uuid import UUID

from helpdesk.platform.ingestion import ingest_chat
from tests.factories import chat_inbound


def count(db, sql, *params):
    return db.execute(sql, params).fetchone()["n"]


def test_ingest_creates_message_audit_and_job(db):
    result = ingest_chat(db, chat_inbound())

    message = db.execute("SELECT * FROM messages").fetchone()
    assert (message["direction"], message["author"]) == ("in", "customer")
    assert message["trace_id"] == result.trace_id

    events = db.execute("SELECT * FROM audit_events ORDER BY id").fetchall()
    assert [(e["type"], e["trace_id"]) for e in events] == [
        ("message.received", result.trace_id),
        ("message.classified", result.trace_id),
        ("conversation.routed", result.trace_id),
    ]

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
    assert count(db, "SELECT count(*) AS n FROM audit_events") == 3


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
    event = db.execute("SELECT payload FROM audit_events WHERE type = 'message.received'").fetchone()
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
    customer = db.execute("SELECT email FROM customers WHERE external_id = 'mary.sample@example.com'").fetchone()
    assert customer["email"] == "mary.sample@example.com"


def test_same_phone_on_two_brands_gets_two_conversations(db):
    from helpdesk.platform.ingestion import ingest, normalize_whatsapp
    from tests.factories import whatsapp_inbound

    ip = ingest(db, normalize_whatsapp(whatsapp_inbound(brand="infinitepay", from_phone="+5500900000007")))
    jim = ingest(db, normalize_whatsapp(whatsapp_inbound(brand="jim", from_phone="+5500900000007")))

    assert ip.conversation_id != jim.conversation_id
    brands = db.execute("SELECT id, brand_id FROM conversations").fetchall()
    assert {r["id"]: r["brand_id"] for r in brands} == {ip.conversation_id: "infinitepay", jim.conversation_id: "jim"}


def customer_name(db, external_id="cli-001"):
    return db.execute("SELECT name FROM customers WHERE external_id = %s", (external_id,)).fetchone()["name"]


def test_duplicate_does_not_touch_customer(db):
    payload = chat_inbound()
    ingest_chat(db, payload)
    renamed = payload.model_copy(update={"customer": payload.customer.model_copy(update={"name": "Outro Nome"})})

    assert ingest_chat(db, renamed).duplicate is True
    assert customer_name(db) == "Ana Teste"


def test_new_message_updates_customer_name(db):
    payload = chat_inbound()
    ingest_chat(db, payload)
    renamed = chat_inbound(customer=payload.customer.model_copy(update={"name": "Ana Renomeada"}))

    assert ingest_chat(db, renamed).duplicate is False
    assert customer_name(db) == "Ana Renomeada"


IP_PAYMENTS = UUID("10000000-0000-0000-0000-000000000002")
IP_SECURITY = UUID("10000000-0000-0000-0000-000000000004")


def events_of(db, conversation_id):
    return [e["type"] for e in db.execute(
        "SELECT type FROM audit_events WHERE conversation_id = %s ORDER BY id", (conversation_id,)).fetchall()]


def conversation(db, conversation_id):
    return db.execute("SELECT * FROM conversations WHERE id = %s", (conversation_id,)).fetchone()


def test_ingest_classifies_and_routes(db):
    result = ingest_chat(db, chat_inbound(text="Não recebi o pagamento de ontem"))

    message = db.execute("SELECT category, priority FROM messages WHERE id = %s", (result.message_id,)).fetchone()
    assert message == {"category": "payments", "priority": "normal"}
    conv = conversation(db, result.conversation_id)
    assert (conv["queue_id"], conv["priority"], conv["handled_by"]) == (IP_PAYMENTS, "normal", "agent")
    assert conv["routed_at"] is not None
    assert result.queue_id == IP_PAYMENTS

    classified = db.execute("SELECT * FROM audit_events WHERE type = 'message.classified'").fetchone()
    assert classified["actor"] == "triage"
    assert classified["payload"]["category"] == "payments"
    assert classified["payload"]["classifier"] == "keyword"
    routed = db.execute("SELECT * FROM audit_events WHERE type = 'conversation.routed'").fetchone()
    assert routed["actor"] == "router"
    assert routed["trace_id"] == result.trace_id
    assert routed["payload"]["queue_name"] == "InfinitePay · Pagamentos"
    assert routed["payload"]["matched_by"] == "rule"
    assert routed["payload"]["rule"]["name"] == "InfinitePay: pagamentos"
    assert count(db, "SELECT count(*) AS n FROM webhook_jobs") == 1


def test_second_message_keeps_queue(db):
    first = ingest_chat(db, chat_inbound(session_id="s", text="Não recebi o pagamento"))
    second = ingest_chat(db, chat_inbound(session_id="s", text="Minha maquininha não liga"))

    assert conversation(db, first.conversation_id)["queue_id"] == IP_PAYMENTS
    assert second.queue_id == IP_PAYMENTS
    assert events_of(db, first.conversation_id).count("conversation.routed") == 1
    assert events_of(db, first.conversation_id).count("message.classified") == 2


def test_priority_only_rises(db):
    first = ingest_chat(db, chat_inbound(session_id="s", text="Não recebi o pagamento"))
    ingest_chat(db, chat_inbound(session_id="s", text="Urgente, preciso do dinheiro"))
    assert conversation(db, first.conversation_id)["priority"] == "high"
    ingest_chat(db, chat_inbound(session_id="s", text="Era só isso"))
    assert conversation(db, first.conversation_id)["priority"] == "high"
    assert events_of(db, first.conversation_id).count("conversation.priority_raised") == 1


def test_human_queue_skips_agent(db):
    first = ingest_chat(db, chat_inbound(session_id="s", text="Caí num golpe"))
    conv = conversation(db, first.conversation_id)
    assert (conv["queue_id"], conv["handled_by"], conv["priority"]) == (IP_SECURITY, "human", "high")
    assert count(db, "SELECT count(*) AS n FROM webhook_jobs") == 0

    ingest_chat(db, chat_inbound(session_id="s", text="Não recebi o pagamento"))
    assert count(db, "SELECT count(*) AS n FROM webhook_jobs") == 0
    held = db.execute("SELECT * FROM audit_events WHERE type = 'message.held_for_human' ORDER BY id").fetchall()
    assert len(held) == 2
    assert held[0]["payload"]["queue_id"] == str(IP_SECURITY)


def test_duplicate_is_not_reclassified(db):
    payload = chat_inbound()
    ingest_chat(db, payload)
    before = count(db, "SELECT count(*) AS n FROM audit_events")
    ingest_chat(db, payload)
    assert count(db, "SELECT count(*) AS n FROM audit_events") == before


def test_closed_conversation_opens_new_one(db):
    first = ingest_chat(db, chat_inbound(session_id="sess-1", message_id="m-1", text="Não recebi o pagamento"))
    db.execute("UPDATE conversations SET status = 'closed', closed_at = now() WHERE id = %s",
               (first.conversation_id,))

    second = ingest_chat(db, chat_inbound(session_id="sess-1", message_id="m-2", text="Minha maquininha não liga"))

    assert second.conversation_id != first.conversation_id
    assert second.queue_id != first.queue_id  # roteada do zero
    assert count(db, "SELECT count(*) AS n FROM webhook_jobs WHERE conversation_id = %s",
                 second.conversation_id) == 1
    statuses = {r["id"]: r["status"] for r in db.execute("SELECT id, status FROM conversations")}
    assert statuses == {first.conversation_id: "closed", second.conversation_id: "open"}


def test_escalated_conversation_is_reused(db):
    first = ingest_chat(db, chat_inbound(session_id="sess-1", message_id="m-1"))
    db.execute("UPDATE conversations SET status = 'escalated', handled_by = 'human'")
    second = ingest_chat(db, chat_inbound(session_id="sess-1", message_id="m-2"))
    assert second.conversation_id == first.conversation_id
