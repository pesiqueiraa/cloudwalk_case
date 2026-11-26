from uuid import uuid4

import pytest

from helpdesk.platform.agent_results import ConversationNotFound, ResultMismatch, apply_agent_result
from helpdesk.platform.ingestion import ingest_chat
from tests.factories import agent_result, chat_inbound

IP_DEFAULT = "10000000-0000-0000-0000-000000000001"
IP_HARDWARE = "10000000-0000-0000-0000-000000000003"


def result_for(ingested, **overrides):
    return agent_result(**{"trace_id": ingested.trace_id, "conversation_id": ingested.conversation_id,
                           "in_reply_to": ingested.message_id, **overrides})


def delivered(db, ingested):
    # O que o worker faz antes de o agente responder
    db.execute("UPDATE webhook_jobs SET status = 'done' WHERE trace_id = %s", (ingested.trace_id,))
    return ingested


def escalation_for(ingested, **overrides):
    return result_for(ingested, event_type="agent.escalated", text="Vou te transferir para um especialista.",
                      reason="cliente pediu atendimento humano",
                      summary="Ana Teste (chat) pediu atendimento humano.", **overrides)


def audit_types(db):
    return [r["type"] for r in db.execute("SELECT type FROM audit_events ORDER BY id")]


def conversation(db, conversation_id):
    return db.execute("SELECT * FROM conversations WHERE id = %s", (conversation_id,)).fetchone()


def test_apply_reply_creates_message_and_audit(db):
    ingested = ingest_chat(db, chat_inbound())
    result = result_for(ingested, text="Olá, Ana!")

    assert apply_agent_result(db, result) == "applied"

    message = db.execute("SELECT * FROM messages WHERE direction = 'out'").fetchone()
    assert (message["author"], message["text"], message["trace_id"]) == ("agent", "Olá, Ana!", ingested.trace_id)
    assert audit_types(db) == ["message.received", "message.classified", "conversation.routed", "agent.replied"]


def test_apply_twice_is_noop(db):
    ingested = ingest_chat(db, chat_inbound())
    result = result_for(ingested)

    assert apply_agent_result(db, result) == "applied"
    assert apply_agent_result(db, result) == "duplicate"

    assert db.execute("SELECT count(*) AS n FROM messages WHERE direction = 'out'").fetchone()["n"] == 1
    assert audit_types(db).count("agent.replied") == 1


def test_unknown_conversation_raises(db):
    with pytest.raises(ConversationNotFound):
        apply_agent_result(db, agent_result())


# Validação do callback

def test_reply_to_other_conversation_is_rejected(db):
    mine = ingest_chat(db, chat_inbound())
    other = ingest_chat(db, chat_inbound())
    with pytest.raises(ResultMismatch):
        apply_agent_result(db, result_for(mine, in_reply_to=other.message_id))
    assert db.execute("SELECT count(*) AS n FROM messages WHERE direction = 'out'").fetchone()["n"] == 0


def test_reply_with_wrong_trace_id_is_rejected(db):
    ingested = ingest_chat(db, chat_inbound())
    with pytest.raises(ResultMismatch):
        apply_agent_result(db, result_for(ingested, trace_id=uuid4()))


def test_reply_to_outbound_message_is_rejected(db):
    ingested = ingest_chat(db, chat_inbound())
    apply_agent_result(db, result_for(ingested))
    out_id = db.execute("SELECT id FROM messages WHERE direction = 'out'").fetchone()["id"]
    with pytest.raises(ResultMismatch):
        apply_agent_result(db, result_for(ingested, in_reply_to=out_id))


# Handoff

def test_escalation_hands_off_to_human(db):
    ingested = delivered(db, ingest_chat(db, chat_inbound()))
    assert apply_agent_result(db, escalation_for(ingested)) == "applied"

    conv = conversation(db, ingested.conversation_id)
    assert (conv["status"], conv["handled_by"]) == ("escalated", "human")
    assert conv["escalation_reason"] == "cliente pediu atendimento humano"
    assert conv["escalation_summary"] == "Ana Teste (chat) pediu atendimento humano."
    assert conv["escalated_at"] is not None
    assert conv["queue_id"] == ingested.queue_id  # sem fila de escalas: fica na mesma

    assert audit_types(db) == ["message.received", "message.classified", "conversation.routed",
                               "agent.replied", "conversation.escalated"]
    payload = db.execute("SELECT payload FROM audit_events WHERE type = 'conversation.escalated'").fetchone()["payload"]
    assert payload["summary"] == "Ana Teste (chat) pediu atendimento humano."
    assert payload["from_queue_id"] == payload["to_queue_id"] == str(ingested.queue_id)
    assert payload["cancelled_jobs"] == 0


def test_escalation_moves_to_escalation_queue(db):
    db.execute("UPDATE queues SET escalation_queue_id = %s WHERE id = %s", (IP_DEFAULT, IP_HARDWARE))
    ingested = ingest_chat(db, chat_inbound(text="Minha maquininha não liga"))
    assert str(ingested.queue_id) == IP_HARDWARE

    apply_agent_result(db, escalation_for(ingested))

    assert str(conversation(db, ingested.conversation_id)["queue_id"]) == IP_DEFAULT
    payload = db.execute("SELECT payload FROM audit_events WHERE type = 'conversation.escalated'").fetchone()["payload"]
    assert (payload["from_queue_id"], payload["to_queue_id"]) == (IP_HARDWARE, IP_DEFAULT)
    assert payload["to_queue_name"]


def test_inactive_escalation_queue_keeps_conversation_in_place(db):
    db.execute("INSERT INTO queues (id, name, brand_id, team_id, first_responder) "
               "VALUES ('40000000-0000-0000-0000-000000000001', 'Escalas', 'infinitepay', 'geral', 'human')")
    db.execute("UPDATE queues SET escalation_queue_id = '40000000-0000-0000-0000-000000000001' WHERE id = %s",
               (IP_HARDWARE,))
    db.execute("UPDATE queues SET active = false WHERE name = 'Escalas'")
    ingested = ingest_chat(db, chat_inbound(text="Minha maquininha não liga"))

    apply_agent_result(db, escalation_for(ingested))

    assert str(conversation(db, ingested.conversation_id)["queue_id"]) == IP_HARDWARE


def test_escalation_cancels_pending_jobs(db):
    first = ingest_chat(db, chat_inbound(session_id="s-1", message_id="m-1"))
    second = ingest_chat(db, chat_inbound(session_id="s-1", message_id="m-2", text="Alô?"))
    delivered(db, first)

    apply_agent_result(db, escalation_for(first))

    jobs = db.execute("SELECT trace_id, status FROM webhook_jobs ORDER BY id").fetchall()
    assert [j["status"] for j in jobs] == ["done", "cancelled"]
    held = db.execute("SELECT trace_id, payload FROM audit_events WHERE type = 'message.held_for_human'").fetchall()
    assert [h["trace_id"] for h in held] == [second.trace_id]
    assert held[0]["payload"]["cause"] == "handoff"


def test_message_after_handoff_does_not_reach_agent(db):
    first = ingest_chat(db, chat_inbound(session_id="s-1", message_id="m-1"))
    apply_agent_result(db, escalation_for(first))

    later = ingest_chat(db, chat_inbound(session_id="s-1", message_id="m-2", text="Ainda estou aqui"))

    assert later.conversation_id == first.conversation_id
    assert db.execute("SELECT count(*) AS n FROM webhook_jobs WHERE trace_id = %s",
                      (later.trace_id,)).fetchone()["n"] == 0
    types = [r["type"] for r in db.execute("SELECT type FROM audit_events WHERE trace_id = %s ORDER BY id",
                                            (later.trace_id,))]
    assert types == ["message.received", "message.classified", "message.held_for_human"]


def test_escalation_redelivery_is_duplicate_not_discard(db):
    ingested = ingest_chat(db, chat_inbound())
    escalation = escalation_for(ingested)
    apply_agent_result(db, escalation)

    assert apply_agent_result(db, escalation) == "duplicate"
    assert "agent.reply_discarded" not in audit_types(db)


# Resposta tardia

def test_late_reply_after_handoff_is_discarded(db):
    first = ingest_chat(db, chat_inbound(session_id="s-1", message_id="m-1"))
    second = ingest_chat(db, chat_inbound(session_id="s-1", message_id="m-2", text="Alô?"))
    apply_agent_result(db, escalation_for(first))

    late = result_for(second, text="Resposta que chegou tarde")
    assert apply_agent_result(db, late) == "discarded"

    texts = [m["text"] for m in db.execute("SELECT text FROM messages WHERE direction = 'out'")]
    assert "Resposta que chegou tarde" not in texts
    discarded = db.execute("SELECT * FROM discarded_agent_results").fetchone()
    assert (discarded["event_id"], discarded["reason"]) == (late.event_id, "handed_off_to_human")
    event = db.execute("SELECT trace_id, payload FROM audit_events WHERE type = 'agent.reply_discarded'").fetchone()
    assert event["trace_id"] == second.trace_id
    assert event["payload"]["event_id"] == str(late.event_id)


def test_discard_is_idempotent(db):
    first = ingest_chat(db, chat_inbound(session_id="s-1", message_id="m-1"))
    second = ingest_chat(db, chat_inbound(session_id="s-1", message_id="m-2", text="Alô?"))
    apply_agent_result(db, escalation_for(first))
    late = result_for(second)

    assert apply_agent_result(db, late) == "discarded"
    assert apply_agent_result(db, late) == "duplicate"
    assert audit_types(db).count("agent.reply_discarded") == 1


def test_reply_to_closed_conversation_is_discarded(db):
    ingested = ingest_chat(db, chat_inbound())
    db.execute("UPDATE conversations SET status = 'closed', closed_at = now()")

    assert apply_agent_result(db, result_for(ingested)) == "discarded"
    assert db.execute("SELECT reason FROM discarded_agent_results").fetchone()["reason"] == "conversation_closed"


def test_reply_to_human_queue_conversation_is_discarded(db):
    # Fraude vai para fila com first_responder = human: nenhuma resposta do agente vale
    ingested = ingest_chat(db, chat_inbound(text="Fui vítima de golpe, clonaram meu cartão"))
    assert conversation(db, ingested.conversation_id)["handled_by"] == "human"
    assert apply_agent_result(db, result_for(ingested)) == "discarded"


def test_agent_identity_goes_to_the_audit(db):
    from helpdesk.platform.agent_results import apply_agent_result
    from helpdesk.platform.ingestion import ingest_chat
    from tests.factories import agent_result, chat_inbound
    ingested = ingest_chat(db, chat_inbound())
    apply_agent_result(db, agent_result(
        trace_id=ingested.trace_id, conversation_id=ingested.conversation_id, in_reply_to=ingested.message_id,
        agent={"impl": "llm", "model": "claude-sonnet-5-5", "effort": "low", "prompt_version": "1"}))
    payload = db.execute("SELECT payload FROM audit_events WHERE type = 'agent.replied'").fetchone()["payload"]
    assert payload["agent"] == {"impl": "llm", "model": "claude-sonnet-5-5", "effort": "low", "prompt_version": "1"}
