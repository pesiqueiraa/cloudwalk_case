from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from helpdesk.platform.app import app, get_conn

IP_DEFAULT = "10000000-0000-0000-0000-000000000001"
IP_PAYMENTS = "10000000-0000-0000-0000-000000000002"
JIM_PAYMENTS = "10000000-0000-0000-0000-000000000012"


@pytest.fixture
def client(db):
    app.dependency_overrides[get_conn] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def new_queue(client, **overrides):
    body = {"name": f"Fila {uuid4().hex[:6]}", "brand_id": "infinitepay", "team_id": "pagamentos",
            "first_responder": "agent", **overrides}
    return client.post("/api/admin/queues", json=body)


def new_rule(client, **overrides):
    body = {"name": "Regra de teste", "position": 5, "category": "payments", "queue_id": IP_PAYMENTS, **overrides}
    return client.post("/api/admin/routing-rules", json=body)


# Equipes e analistas

def test_lists_teams_and_analysts(client):
    assert {t["id"] for t in client.get("/api/admin/teams").json()} == {"geral", "pagamentos", "hardware", "seguranca"}
    analysts = client.get("/api/admin/analysts", params={"team_id": "seguranca"}).json()
    assert analysts and {a["team_id"] for a in analysts} == {"seguranca"}


# Filas

def test_create_and_list_queue(client):
    response = new_queue(client, name="InfinitePay · Chargebacks")
    assert response.status_code == 201
    queue = response.json()
    assert (queue["name"], queue["active"], queue["is_default"]) == ("InfinitePay · Chargebacks", True, False)

    names = [q["name"] for q in client.get("/api/admin/queues", params={"brand": "infinitepay"}).json()]
    assert "InfinitePay · Chargebacks" in names
    assert all("JIM" not in n for n in names)


@pytest.mark.parametrize("overrides", [
    {"brand_id": "acme"}, {"first_responder": "robot"}, {"name": ""},
])
def test_create_queue_rejects_invalid_values(client, overrides):
    assert new_queue(client, **overrides).status_code == 422


def test_create_queue_rejects_unknown_team(client):
    assert new_queue(client, team_id="nao-existe").status_code == 422


def test_create_queue_rejects_duplicate_name(client):
    assert new_queue(client, name="InfinitePay · Geral").status_code == 409


def test_patch_queue(client):
    queue = new_queue(client).json()
    response = client.patch(f"/api/admin/queues/{queue['id']}", json={"first_responder": "human", "team_id": "seguranca"})
    assert response.status_code == 200
    updated = response.json()
    assert (updated["first_responder"], updated["team_id"]) == ("human", "seguranca")
    assert updated["updated_at"] > queue["updated_at"]


def test_patch_unknown_queue(client):
    assert client.patch(f"/api/admin/queues/{uuid4()}", json={"active": False}).status_code == 404


def test_new_default_replaces_previous_one(client):
    queue = new_queue(client).json()
    response = client.patch(f"/api/admin/queues/{queue['id']}", json={"is_default": True})
    assert response.status_code == 200
    defaults = [q["id"] for q in client.get("/api/admin/queues", params={"brand": "infinitepay"}).json()
                if q["is_default"]]
    assert defaults == [queue["id"]]


def test_create_queue_as_default_replaces_previous_one(client):
    queue = new_queue(client, is_default=True).json()
    defaults = [q["id"] for q in client.get("/api/admin/queues", params={"brand": "infinitepay"}).json()
                if q["is_default"]]
    assert defaults == [queue["id"]]


@pytest.mark.parametrize("change", [{"active": False}, {"is_default": False}])
def test_cannot_remove_the_brand_default_queue(client, change):
    assert client.patch(f"/api/admin/queues/{IP_DEFAULT}", json=change).status_code == 422


def test_deactivated_queue_is_listed_with_filter(client):
    queue = new_queue(client).json()
    client.patch(f"/api/admin/queues/{queue['id']}", json={"active": False})
    active_ids = [q["id"] for q in client.get("/api/admin/queues", params={"active": "true"}).json()]
    inactive_ids = [q["id"] for q in client.get("/api/admin/queues", params={"active": "false"}).json()]
    assert queue["id"] not in active_ids
    assert queue["id"] in inactive_ids


# Regras

def test_create_and_list_rule(client):
    response = new_rule(client, position=1, priority="high")
    assert response.status_code == 201
    rule = response.json()
    assert (rule["category"], rule["priority"], rule["channel"], rule["brand_id"]) == ("payments", "high", None, None)

    rules = client.get("/api/admin/routing-rules", params={"brand": "infinitepay"}).json()
    assert rules[0]["id"] == rule["id"]
    assert [r["position"] for r in rules] == sorted(r["position"] for r in rules)


@pytest.mark.parametrize("overrides", [
    {"category": "astrology"}, {"channel": "fax"}, {"priority": "urgent"}, {"brand_id": "acme"},
])
def test_create_rule_rejects_invalid_conditions(client, overrides):
    assert new_rule(client, **overrides).status_code == 422


def test_create_rule_rejects_unknown_queue(client):
    assert new_rule(client, queue_id=str(uuid4())).status_code == 422


def test_create_rule_rejects_inactive_queue(client):
    queue = new_queue(client).json()
    client.patch(f"/api/admin/queues/{queue['id']}", json={"active": False})
    assert new_rule(client, queue_id=queue["id"]).status_code == 422


def test_create_rule_rejects_brand_mismatch(client):
    assert new_rule(client, brand_id="jim", queue_id=IP_PAYMENTS).status_code == 422


def test_patch_rule_can_clear_a_condition(client):
    rule = new_rule(client, channel="whatsapp").json()
    response = client.patch(f"/api/admin/routing-rules/{rule['id']}", json={"channel": None, "position": 3})
    assert response.status_code == 200
    assert (response.json()["channel"], response.json()["position"]) == (None, 3)
    assert response.json()["category"] == "payments"


def test_patch_rule_validates_new_queue(client):
    rule = new_rule(client).json()
    response = client.patch(f"/api/admin/routing-rules/{rule['id']}", json={"brand_id": "jim"})
    assert response.status_code == 422
    response = client.patch(f"/api/admin/routing-rules/{rule['id']}", json={"brand_id": "jim", "queue_id": JIM_PAYMENTS})
    assert response.status_code == 200


def test_patch_unknown_rule(client):
    assert client.patch(f"/api/admin/routing-rules/{uuid4()}", json={"active": False}).status_code == 404


# Fila de escalas

IP_SECURITY = "10000000-0000-0000-0000-000000000004"
JIM_SECURITY = "10000000-0000-0000-0000-000000000014"


def test_create_queue_with_escalation_queue(client):
    response = new_queue(client, escalation_queue_id=IP_SECURITY)
    assert response.status_code == 201
    assert response.json()["escalation_queue_id"] == IP_SECURITY


def test_patch_sets_and_clears_escalation_queue(client):
    response = client.patch(f"/api/admin/queues/{IP_PAYMENTS}", json={"escalation_queue_id": IP_SECURITY})
    assert (response.status_code, response.json()["escalation_queue_id"]) == (200, IP_SECURITY)

    renamed = client.patch(f"/api/admin/queues/{IP_PAYMENTS}", json={"name": "InfinitePay · Pix"})
    assert renamed.json()["escalation_queue_id"] == IP_SECURITY  # campo ausente fica como está

    cleared = client.patch(f"/api/admin/queues/{IP_PAYMENTS}", json={"escalation_queue_id": None})
    assert (cleared.status_code, cleared.json()["escalation_queue_id"]) == (200, None)


@pytest.mark.parametrize("target, detail", [
    (JIM_SECURITY, "outra marca"),
    (IP_PAYMENTS, "própria fila"),
    (str(uuid4()), "inexistente"),
])
def test_patch_rejects_invalid_escalation_queue(client, target, detail):
    response = client.patch(f"/api/admin/queues/{IP_PAYMENTS}", json={"escalation_queue_id": target})
    assert response.status_code == 422
    assert detail in response.json()["detail"]


def test_escalation_queue_must_be_active(client):
    inactive = new_queue(client).json()
    client.patch(f"/api/admin/queues/{inactive['id']}", json={"active": False})
    response = new_queue(client, escalation_queue_id=inactive["id"])
    assert response.status_code == 422
    assert "desativada" in response.json()["detail"]
