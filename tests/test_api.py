from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from helpdesk.platform.app import app, get_conn
from tests.factories import agent_result, chat_inbound


@pytest.fixture
def client(db):
    # Sem o "with", o lifespan não roda: a API usa a conexão do banco de teste
    app.dependency_overrides[get_conn] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_flow(client):
    response = client.post("/channels/chat/messages", content=chat_inbound().model_dump_json())
    assert response.status_code == 202
    ingested = response.json()
    assert ingested["duplicate"] is False

    result = agent_result(trace_id=ingested["trace_id"], conversation_id=ingested["conversation_id"],
                          in_reply_to=ingested["message_id"])
    callback = client.post("/internal/agent-results", content=result.model_dump_json())
    assert callback.status_code == 200
    assert callback.json() == {"applied": True}

    conversation = client.get(f"/api/conversations/{ingested['conversation_id']}").json()
    assert [(m["direction"], m["author"]) for m in conversation["messages"]] == [("in", "customer"), ("out", "agent")]
    assert [e["type"] for e in conversation["audit"]] == ["message.received", "message.classified", "conversation.routed", "agent.replied"]
    assert conversation["conversation"]["status"] == "open"

    trace = client.get(f"/api/traces/{ingested['trace_id']}/audit").json()
    assert {e["trace_id"] for e in trace} == {ingested["trace_id"]}


def test_duplicate_callback_returns_applied_false(client):
    ingested = client.post("/channels/chat/messages", content=chat_inbound().model_dump_json()).json()
    result = agent_result(trace_id=ingested["trace_id"], conversation_id=ingested["conversation_id"],
                          in_reply_to=ingested["message_id"])
    client.post("/internal/agent-results", content=result.model_dump_json())
    second = client.post("/internal/agent-results", content=result.model_dump_json())
    assert (second.status_code, second.json()) == (200, {"applied": False})


def test_callback_unknown_conversation_returns_404(client):
    response = client.post("/internal/agent-results", content=agent_result().model_dump_json())
    assert response.status_code == 404


def test_unknown_conversation_returns_404(client):
    assert client.get(f"/api/conversations/{uuid4()}").status_code == 404


def test_invalid_chat_payload_returns_422(client):
    body = chat_inbound().model_dump(mode="json")
    body["text"] = ""
    assert client.post("/channels/chat/messages", json=body).status_code == 422


def test_whatsapp_and_email_endpoints(client):
    from tests.factories import email_inbound, whatsapp_inbound

    wa = client.post("/channels/whatsapp/messages", content=whatsapp_inbound().model_dump_json())
    email = client.post("/channels/email/messages", content=email_inbound().model_dump_json())
    assert (wa.status_code, email.status_code) == (202, 202)
    assert wa.json()["conversation_id"] != email.json()["conversation_id"]


def test_queue_conversations_ordered_by_priority_then_age(client):
    queue_id = "10000000-0000-0000-0000-000000000002"
    texts = ["Não recebi o pagamento", "Urgente: não recebi o pagamento", "O Pix não caiu"]
    ids = [client.post("/channels/chat/messages",
                       content=chat_inbound(text=t).model_dump_json()).json()["conversation_id"] for t in texts]

    response = client.get(f"/api/queues/{queue_id}/conversations")
    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == [ids[1], ids[0], ids[2]]


def test_queue_conversations_unknown_queue(client):
    assert client.get(f"/api/queues/{uuid4()}/conversations").status_code == 404
