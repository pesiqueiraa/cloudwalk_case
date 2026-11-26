"""Escalação proativa na triagem: pedido de humano ou frustração no limiar da fila, sem passar pelo agente."""
from helpdesk.platform.ingestion import ingest, normalize_chat
from tests.factories import RecordingClassifier, chat_inbound


def send(db, triage, **overrides):
    return ingest(db, normalize_chat(chat_inbound(**overrides)), triage)


def set_threshold(db, level):
    db.execute("UPDATE queues SET escalate_on_frustration = %s", (level,))


def conversation(db, conversation_id):
    return db.execute("SELECT * FROM conversations WHERE id = %s", (conversation_id,)).fetchone()


def jobs_of(db, trace_id):
    return db.execute("SELECT status FROM webhook_jobs WHERE trace_id = %s", (trace_id,)).fetchall()


def test_customer_asking_for_a_person_is_escalated_without_the_agent(db):
    result = send(db, RecordingClassifier(frustration=0.2, wants_human=0.95), brand="infinitepay")

    conv = conversation(db, result.conversation_id)
    assert (conv["handled_by"], conv["status"]) == ("human", "escalated")
    assert "pediu atendimento humano" in conv["escalation_reason"]
    assert conv["escalation_summary"].startswith(chat_inbound().customer.name)
    assert jobs_of(db, result.trace_id) == []

    system = db.execute("SELECT text FROM messages WHERE author = 'system'").fetchone()
    assert system["text"].startswith("Entendi. Vou passar você")
    types = [e["type"] for e in db.execute(
        "SELECT type FROM audit_events WHERE trace_id = %s ORDER BY id", (result.trace_id,)).fetchall()]
    assert types == ["message.received", "message.classified", "conversation.routed",
                     "conversation.escalated", "message.held_for_human"]
    escalated = db.execute("SELECT actor, payload FROM audit_events WHERE type = 'conversation.escalated'").fetchone()
    assert escalated["actor"] == "triage"
    assert (escalated["payload"]["wants_human"], escalated["payload"]["classifier"]) == (0.95, "jev")


def test_frustration_at_queue_threshold_escalates(db):
    set_threshold(db, 2)
    result = send(db, RecordingClassifier(frustration=1.6, wants_human=0.1), brand="jim")
    conv = conversation(db, result.conversation_id)
    assert conv["handled_by"] == "human"
    assert conv["escalation_reason"] == ("cliente frustrado (1,6 de 3); a fila passa para a equipe a partir de "
                                         "frustrado (triagem)")
    assert db.execute("SELECT text FROM messages WHERE author = 'system'").fetchone()["text"].startswith("Got it.")


def test_frustration_below_threshold_goes_to_the_agent(db):
    set_threshold(db, 2)
    result = send(db, RecordingClassifier(frustration=1.4, wants_human=0.1))
    assert conversation(db, result.conversation_id)["handled_by"] == "agent"
    assert [j["status"] for j in jobs_of(db, result.trace_id)] == ["pending"]


def test_threshold_off_never_escalates_on_frustration(db):
    result = send(db, RecordingClassifier(frustration=3.0, wants_human=0.1))
    assert conversation(db, result.conversation_id)["handled_by"] == "agent"


def test_undecided_request_for_a_person_does_not_escalate(db):
    result = send(db, RecordingClassifier(frustration=0.5, wants_human=0.6))
    assert conversation(db, result.conversation_id)["handled_by"] == "agent"


def test_rules_never_escalate_proactively(db):
    from helpdesk.platform.ingestion import ingest_chat
    set_threshold(db, 0)
    result = ingest_chat(db, chat_inbound(text="Quero falar com um atendente agora!!!"))
    # Sem sinais do Jev, quem escala é o agente, como antes
    assert conversation(db, result.conversation_id)["handled_by"] == "agent"


def test_later_message_escalates_and_cancels_pending_job(db):
    set_threshold(db, 2)
    first = send(db, RecordingClassifier(frustration=0.5, wants_human=0.1), session_id="s-1", message_id="m-1")
    second = send(db, RecordingClassifier(frustration=2.8, wants_human=0.1), session_id="s-1", message_id="m-2")

    assert first.conversation_id == second.conversation_id
    assert conversation(db, second.conversation_id)["handled_by"] == "human"
    # O job da primeira mensagem ainda não tinha saído: o handoff o cancela
    assert [j["status"] for j in jobs_of(db, first.trace_id)] == ["cancelled"]
    assert jobs_of(db, second.trace_id) == []


def test_conversation_already_with_a_human_is_not_escalated_twice(db):
    send(db, RecordingClassifier(wants_human=0.9), session_id="s-2", message_id="m-1")
    send(db, RecordingClassifier(wants_human=0.9), session_id="s-2", message_id="m-2")
    assert db.execute("SELECT count(*) AS n FROM audit_events WHERE type = 'conversation.escalated'").fetchone()["n"] == 1
    assert db.execute("SELECT count(*) AS n FROM messages WHERE author = 'system'").fetchone()["n"] == 1


def test_escalation_moves_to_the_queue_escalation_target(db):
    routed = send(db, RecordingClassifier(wants_human=0.1), session_id="s-a", message_id="m-1").queue_id
    target = db.execute(
        "SELECT id FROM queues WHERE brand_id = 'infinitepay' AND active AND id <> %s LIMIT 1", (routed,)
    ).fetchone()["id"]
    db.execute("UPDATE queues SET escalation_queue_id = %s WHERE id = %s", (target, routed))

    result = send(db, RecordingClassifier(wants_human=0.9), session_id="s-b", message_id="m-2")
    assert conversation(db, result.conversation_id)["queue_id"] == target
