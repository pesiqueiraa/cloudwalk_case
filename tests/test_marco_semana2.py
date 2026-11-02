"""Marco da semana 2: fila e regra criadas pela API valem no atendimento seguinte, sem reiniciar nada."""
import pytest
from fastapi.testclient import TestClient

from helpdesk.platform.app import app, get_conn
from tests.factories import chat_inbound

JIM_PAYMENTS = "10000000-0000-0000-0000-000000000012"


@pytest.fixture
def client(db):
    app.dependency_overrides[get_conn] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def send(client, text="I didn't get yesterday's payout"):
    response = client.post("/channels/chat/messages", content=chat_inbound(brand="jim", text=text).model_dump_json())
    assert response.status_code == 202
    return response.json()


def routed_event(client, conversation_id):
    audit = client.get(f"/api/conversations/{conversation_id}").json()["audit"]
    return next(e for e in audit if e["type"] == "conversation.routed")


@pytest.fixture
def chargebacks(client):
    """Cria, pela API, a fila "JIM · Chargebacks" e uma regra que manda pagamentos da JIM para ela."""
    queue = client.post("/api/admin/queues", json={
        "name": "JIM · Chargebacks", "brand_id": "jim", "team_id": "pagamentos", "first_responder": "agent",
    }).json()
    rule = client.post("/api/admin/routing-rules", json={
        "name": "JIM: pagamentos para chargebacks", "position": 1, "brand_id": "jim", "category": "payments",
        "queue_id": queue["id"],
    }).json()
    return queue, rule


def test_new_queue_and_rule_apply_immediately(client, chargebacks):
    queue, rule = chargebacks
    ingested = send(client)

    conversation = client.get(f"/api/conversations/{ingested['conversation_id']}").json()["conversation"]
    assert conversation["queue_id"] == queue["id"]
    event = routed_event(client, ingested["conversation_id"])
    assert (event["payload"]["queue_name"], event["payload"]["rule"]["id"]) == ("JIM · Chargebacks", rule["id"])
    assert event["trace_id"] == ingested["trace_id"]
    queued = [c["id"] for c in client.get(f"/api/queues/{queue['id']}/conversations").json()]
    assert queued == [ingested["conversation_id"]]


def test_rule_edit_does_not_rewrite_audit(client, chargebacks):
    _, rule = chargebacks
    before = send(client)
    client.patch(f"/api/admin/routing-rules/{rule['id']}", json={"category": "card"})

    assert routed_event(client, before["conversation_id"])["payload"]["rule"]["category"] == "payments"
    after = send(client)
    assert after["queue_id"] == JIM_PAYMENTS


def test_deactivated_rule_stops_matching(client, chargebacks):
    _, rule = chargebacks
    client.patch(f"/api/admin/routing-rules/{rule['id']}", json={"active": False})
    assert send(client)["queue_id"] == JIM_PAYMENTS
