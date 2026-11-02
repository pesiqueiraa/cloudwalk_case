import pytest

from helpdesk.platform.agent_results import ConversationNotFound, apply_agent_result
from helpdesk.platform.ingestion import ingest_chat
from tests.factories import agent_result, chat_inbound


def result_for(ingested, **overrides):
    return agent_result(trace_id=ingested.trace_id, conversation_id=ingested.conversation_id,
                        in_reply_to=ingested.message_id, **overrides)


def audit_types(db):
    return [r["type"] for r in db.execute("SELECT type FROM audit_events ORDER BY id")]


def test_apply_reply_creates_message_and_audit(db):
    ingested = ingest_chat(db, chat_inbound())
    result = result_for(ingested, text="Olá, Ana!")

    assert apply_agent_result(db, result) is True

    message = db.execute("SELECT * FROM messages WHERE direction = 'out'").fetchone()
    assert (message["author"], message["text"], message["trace_id"]) == ("agent", "Olá, Ana!", ingested.trace_id)
    assert audit_types(db) == ["message.received", "message.classified", "conversation.routed", "agent.replied"]


def test_apply_twice_is_noop(db):
    ingested = ingest_chat(db, chat_inbound())
    result = result_for(ingested)

    assert apply_agent_result(db, result) is True
    assert apply_agent_result(db, result) is False

    assert db.execute("SELECT count(*) AS n FROM messages WHERE direction = 'out'").fetchone()["n"] == 1
    assert audit_types(db).count("agent.replied") == 1


def test_escalation_sets_status_and_audits(db):
    ingested = ingest_chat(db, chat_inbound())
    apply_agent_result(db, result_for(ingested, event_type="agent.escalated", reason="cliente pediu atendimento humano"))

    status = db.execute("SELECT status FROM conversations").fetchone()["status"]
    assert status == "escalated"
    assert audit_types(db) == ["message.received", "message.classified", "conversation.routed", "agent.replied", "conversation.escalated"]
    escalated = db.execute("SELECT payload FROM audit_events WHERE type = 'conversation.escalated'").fetchone()
    assert escalated["payload"]["reason"] == "cliente pediu atendimento humano"


def test_unknown_conversation_raises(db):
    with pytest.raises(ConversationNotFound):
        apply_agent_result(db, agent_result())
