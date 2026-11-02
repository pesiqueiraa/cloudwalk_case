import httpx
import pytest
from aiokafka.errors import KafkaError
from fastapi.testclient import TestClient

from helpdesk.broker import app as broker_app
from helpdesk.broker.kafka import from_record, to_record
from helpdesk.broker.outbound import forward
from helpdesk.config import Settings
from helpdesk.contracts import AgentRequest
from tests.factories import agent_request, agent_result


class FakeProducer:
    def __init__(self, error: Exception | None = None):
        self.sent = []
        self.error = error

    async def send_and_wait(self, topic, value=None, key=None, headers=None):
        if self.error:
            raise self.error
        self.sent.append({"topic": topic, "key": key, "value": value, "headers": headers})


@pytest.fixture
def client():
    # Sem o "with", o lifespan não roda e nenhum produtor Kafka real é criado
    return TestClient(broker_app.app)


def test_to_record_uses_conversation_id_as_key():
    req = agent_request()
    key, value, headers = to_record(req)
    assert key == str(req.conversation_id).encode()
    assert dict(headers)["trace_id"] == str(req.trace_id).encode()
    assert from_record(value, AgentRequest) == req


def test_webhook_publishes_and_returns_202(client):
    broker_app.app.state.producer = FakeProducer()
    req = agent_request()

    response = client.post("/webhooks/agent-requests", content=req.model_dump_json())

    assert response.status_code == 202
    [sent] = broker_app.app.state.producer.sent
    assert sent["topic"] == "helpdesk.inbound"
    assert sent["key"] == str(req.conversation_id).encode()


def test_webhook_returns_503_when_kafka_fails(client):
    broker_app.app.state.producer = FakeProducer(error=KafkaError("redpanda fora"))
    response = client.post("/webhooks/agent-requests", content=agent_request().model_dump_json())
    assert response.status_code == 503


def test_webhook_rejects_invalid_body(client):
    broker_app.app.state.producer = FakeProducer()
    body = agent_request().model_dump(mode="json")
    del body["trace_id"]
    assert client.post("/webhooks/agent-requests", json=body).status_code == 422


@pytest.mark.parametrize("status, expected", [
    (200, "done"),
    (404, "dead_letter"),
    (422, "dead_letter"),
    (408, "retry"),
    (429, "retry"),
    (500, "retry"),
    (503, "retry"),
])
async def test_forward_maps_status_codes(status, expected):
    settings = Settings(platform_url="http://platform.test")
    transport = httpx.MockTransport(lambda r: httpx.Response(status, text="motivo"))
    async with httpx.AsyncClient(transport=transport) as client:
        assert (await forward(agent_result(), client, settings)).outcome == expected


async def test_forward_retries_when_platform_unreachable():
    def respond(request):
        raise httpx.ConnectError("plataforma fora")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert (await forward(agent_result(), client, Settings())).outcome == "retry"


async def test_forward_posts_to_callback_endpoint():
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200)

    result = agent_result()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await forward(result, client, Settings(platform_url="http://platform.test"))

    assert seen[0].url == "http://platform.test/internal/agent-results"
    assert seen[0].headers["X-Trace-Id"] == str(result.trace_id)
