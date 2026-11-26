from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from helpdesk.platform.app import app, get_conn
from tests.factories import agent_result, chat_inbound

LIA = "30000000-0000-0000-0000-000000000001"      # geral
TOM = "30000000-0000-0000-0000-000000000002"      # geral
OLGA = "30000000-0000-0000-0000-000000000007"     # seguranca


@pytest.fixture
def client(db):
    app.dependency_overrides[get_conn] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def send(client, session_id=None, text="Quero falar com um atendente", **overrides):
    payload = chat_inbound(session_id=session_id or f"sess-{uuid4()}", text=text, **overrides)
    response = client.post("/channels/chat/messages", content=payload.model_dump_json())
    assert response.status_code == 202
    return response.json()


def escalate(client, ingested):
    result = agent_result(trace_id=ingested["trace_id"], conversation_id=ingested["conversation_id"],
                          in_reply_to=ingested["message_id"], event_type="agent.escalated",
                          text="Vou te transferir.", reason="cliente pediu atendimento humano",
                          summary="Ana Teste (chat) pediu atendimento humano.")
    assert client.post("/internal/agent-results", content=result.model_dump_json()).json()["outcome"] == "applied"
    return ingested["conversation_id"]


def escalated_case(client, **overrides):
    return escalate(client, send(client, **overrides))


def assign(client, conversation_id, analyst_id=LIA):
    return client.post(f"/api/conversations/{conversation_id}/assign", json={"analyst_id": analyst_id})


def audit_types(client, conversation_id):
    return [e["type"] for e in client.get(f"/api/cases/{conversation_id}").json()["audit"]]


# Fila de escalas

def test_escalations_lists_human_conversations_only(client):
    escalated = escalated_case(client)
    send(client, text="Minha maquininha não liga")  # fica com o agente
    fraud = send(client, text="Fui vítima de golpe")  # fila humana desde o roteamento

    ids = [c["id"] for c in client.get("/api/escalations").json()]
    assert set(ids) == {escalated, fraud["conversation_id"]}


def test_escalations_filter_by_team_and_order(client):
    first = escalated_case(client)
    second = escalated_case(client)
    assign(client, first)
    fraud = send(client, text="Fui vítima de golpe")["conversation_id"]

    geral = client.get("/api/escalations", params={"team_id": "geral"}).json()
    assert [c["id"] for c in geral] == [second, first]  # não assumida antes da assumida
    assert geral[1]["assigned_analyst_name"] == "Lia Exemplo"
    assert [c["id"] for c in client.get("/api/escalations", params={"team_id": "seguranca"}).json()] == [fraud]


# Assumir

def test_assign_audits_and_is_idempotent_for_same_analyst(client):
    conversation_id = escalated_case(client)
    first = assign(client, conversation_id)
    assert first.status_code == 200
    assert first.json()["assigned_analyst_id"] == LIA
    assert assign(client, conversation_id).status_code == 200
    assert audit_types(client, conversation_id).count("conversation.assigned") == 1


def test_assign_conflict_with_other_analyst(client):
    conversation_id = escalated_case(client)
    assign(client, conversation_id, LIA)
    response = assign(client, conversation_id, TOM)
    assert response.status_code == 409


def test_assign_requires_team_of_the_queue(client):
    conversation_id = escalated_case(client)
    response = assign(client, conversation_id, OLGA)
    assert response.status_code == 422
    assert "equipe" in response.json()["detail"]


def test_assign_unknown_analyst(client):
    assert assign(client, escalated_case(client), str(uuid4())).status_code == 422


def test_cannot_assign_conversation_with_agent(client):
    conversation_id = send(client, text="Minha maquininha não liga")["conversation_id"]
    assert assign(client, conversation_id).status_code == 409


def test_assign_unknown_conversation(client):
    assert assign(client, str(uuid4())).status_code == 404


# Responder

def test_analyst_reply_is_recorded_and_audited(client):
    conversation_id = escalated_case(client)
    assign(client, conversation_id)
    response = client.post(f"/api/conversations/{conversation_id}/messages",
                           json={"analyst_id": LIA, "text": "Oi, sou a Lia. Vou te ajudar."})
    assert response.status_code == 201
    assert (response.json()["author"], response.json()["direction"]) == ("analyst", "out")

    case = client.get(f"/api/cases/{conversation_id}").json()
    assert case["messages"][-1]["text"] == "Oi, sou a Lia. Vou te ajudar."
    assert audit_types(client, conversation_id)[-1] == "analyst.replied"


def test_only_assigned_analyst_can_reply(client):
    conversation_id = escalated_case(client)
    body = {"analyst_id": LIA, "text": "Olá"}
    assert client.post(f"/api/conversations/{conversation_id}/messages", json=body).status_code == 409
    assign(client, conversation_id, TOM)
    assert client.post(f"/api/conversations/{conversation_id}/messages", json=body).status_code == 409


def test_reply_rejects_empty_text(client):
    conversation_id = escalated_case(client)
    assign(client, conversation_id)
    response = client.post(f"/api/conversations/{conversation_id}/messages", json={"analyst_id": LIA, "text": ""})
    assert response.status_code == 422


# Encerrar e memória

def test_close_then_next_message_opens_new_conversation_with_memory(client):
    session = f"sess-{uuid4()}"
    conversation_id = escalated_case(client, session_id=session)
    assign(client, conversation_id)
    closed = client.post(f"/api/conversations/{conversation_id}/close", json={"analyst_id": LIA})
    assert (closed.status_code, closed.json()["status"]) == (200, "closed")
    assert audit_types(client, conversation_id)[-1] == "conversation.closed"
    assert conversation_id not in [c["id"] for c in client.get("/api/escalations").json()]

    new = send(client, session_id=session, text="Minha maquininha não liga")
    assert new["conversation_id"] != conversation_id

    case = client.get(f"/api/cases/{new['conversation_id']}").json()
    assert case["conversation"]["handled_by"] == "agent"
    previous = case["previous_conversations"]
    assert [p["id"] for p in previous] == [conversation_id]
    assert previous[0]["escalation_summary"] == "Ana Teste (chat) pediu atendimento humano."
    assert previous[0]["assigned_analyst_name"] == "Lia Exemplo"
    assert previous[0]["first_message_text"] == "Quero falar com um atendente"


def test_only_assigned_analyst_can_close(client):
    conversation_id = escalated_case(client)
    assign(client, conversation_id, LIA)
    assert client.post(f"/api/conversations/{conversation_id}/close", json={"analyst_id": TOM}).status_code == 409
    client.post(f"/api/conversations/{conversation_id}/close", json={"analyst_id": LIA})
    assert client.post(f"/api/conversations/{conversation_id}/close", json={"analyst_id": LIA}).status_code == 409


def test_memory_is_per_customer(client):
    mine = escalated_case(client)
    other = send(client, customer={"external_id": "cli-999", "name": "Outro", "email": "o@example.com"})
    case = client.get(f"/api/cases/{other['conversation_id']}").json()
    assert mine not in [p["id"] for p in case["previous_conversations"]]


def test_case_unknown_returns_404(client):
    assert client.get(f"/api/cases/{uuid4()}").status_code == 404


# Lista de conversas

def test_list_conversations_filters_and_orders_by_activity(client):
    older = send(client, text="Minha maquininha não liga")["conversation_id"]
    escalated = escalated_case(client)
    send(client, brand="jim", text="My card reader is off")

    infinitepay = client.get("/api/conversations", params={"brand": "infinitepay"}).json()
    assert [c["id"] for c in infinitepay] == [escalated, older]
    assert infinitepay[0]["last_message_text"] == "Vou te transferir."
    human = client.get("/api/conversations", params={"handled_by": "human"}).json()
    assert [c["id"] for c in human] == [escalated]


def test_list_shows_last_customer_frustration(client, db):
    conversation_id = send(client, text="Minha maquininha não liga")["conversation_id"]
    listed = client.get("/api/conversations").json()[0]
    assert listed["last_customer_frustration"] is None   # regras não medem frustração

    db.execute("UPDATE messages SET frustration = 2.6 WHERE conversation_id = %s AND author = 'customer'",
               (conversation_id,))
    assert client.get("/api/conversations").json()[0]["last_customer_frustration"] == 2.6
