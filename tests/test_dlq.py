"""Laços de consumo e DLQ do Kafka, com consumidor e produtor falsos."""
from dataclasses import dataclass, field

import httpx

from helpdesk.agent_mock.main import handle_record as agent_handle
from helpdesk.broker.dlq import dead_letter_headers, dlq_topic, header, replay_record
from helpdesk.broker.kafka import to_record
from helpdesk.broker.outbound import handle_record as outbound_handle
from helpdesk.config import Settings
from tests.factories import agent_request, agent_result

SETTINGS = Settings(platform_url="http://platform.test")


@dataclass
class FakeRecord:
    value: bytes
    key: bytes = b"conversa-1"
    topic: str = "helpdesk.outbound"
    partition: int = 2
    offset: int = 41
    headers: list = field(default_factory=lambda: [("trace_id", b"trace-1")])


class FakeProducer:
    def __init__(self):
        self.sent = []

    async def send_and_wait(self, topic, value=None, key=None, headers=None):
        self.sent.append({"topic": topic, "key": key, "value": value, "headers": headers})


def record_of(model, topic):
    key, value, headers = to_record(model)
    return FakeRecord(value=value, key=key, topic=topic, headers=headers)


def platform(*statuses):
    """Plataforma falsa que devolve os status em sequência."""
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(statuses[min(len(calls), len(statuses)) - 1], text="motivo")

    return httpx.AsyncClient(transport=httpx.MockTransport(respond)), calls


async def no_sleep(seconds):
    no_sleep.waits.append(seconds)


# Cabeçalhos da DLQ

def test_dead_letter_keeps_original_headers_and_adds_origin():
    headers = dict(dead_letter_headers(FakeRecord(value=b"x"), "invalid_payload", "erro"))
    assert headers["trace_id"] == b"trace-1"
    assert (headers["dlq_reason"], headers["dlq_source_topic"]) == (b"invalid_payload", b"helpdesk.outbound")
    assert (headers["dlq_source_partition"], headers["dlq_source_offset"]) == (b"2", b"41")


def test_dead_letter_takes_trace_id_from_body_when_header_is_missing():
    record = FakeRecord(value=b'{"trace_id": "abc-123", "x": 1}', headers=[])
    assert dict(dead_letter_headers(record, "invalid_payload", "erro"))["trace_id"] == b"abc-123"
    assert "trace_id" not in dict(dead_letter_headers(FakeRecord(value=b"lixo", headers=[]), "r", "d"))


def test_dlq_topic_name():
    assert dlq_topic("helpdesk.inbound") == "helpdesk.inbound.dlq"


async def test_replay_returns_record_to_source_without_dlq_headers():
    dead = FakeRecord(value=b'{"x": 1}', topic="helpdesk.outbound.dlq",
                      headers=dead_letter_headers(FakeRecord(value=b"x"), "callback_rejected", "422"))
    producer = FakeProducer()
    assert await replay_record(producer, dead) == "helpdesk.outbound"
    sent = producer.sent[0]
    assert (sent["topic"], sent["key"], sent["value"]) == ("helpdesk.outbound", b"conversa-1", b'{"x": 1}')
    assert [k for k, _ in sent["headers"]] == ["trace_id"]


# broker-outbound

async def test_outbound_invalid_payload_goes_to_dlq():
    producer = FakeProducer()
    client, calls = platform(200)
    async with client:
        outcome = await outbound_handle(FakeRecord(value=b"{nao e json"), client, producer, SETTINGS)
    assert outcome == "dead_letter"
    assert calls == []
    assert producer.sent[0]["topic"] == "helpdesk.outbound.dlq"
    assert header(FakeRecord(value=b"", headers=producer.sent[0]["headers"]), "dlq_reason") == "invalid_payload"


async def test_outbound_rejected_callback_goes_to_dlq_with_status():
    producer = FakeProducer()
    client, _ = platform(422)
    async with client:
        outcome = await outbound_handle(record_of(agent_result(), "helpdesk.outbound"), client, producer, SETTINGS)
    assert outcome == "dead_letter"
    detail = dict(producer.sent[0]["headers"])["dlq_detail"]
    assert detail.startswith(b"422")


async def test_outbound_retries_until_platform_accepts_without_dlq():
    no_sleep.waits = []
    producer = FakeProducer()
    client, calls = platform(503, 429, 408, 200)
    async with client:
        outcome = await outbound_handle(record_of(agent_result(), "helpdesk.outbound"), client, producer,
                                        SETTINGS, sleep=no_sleep)
    assert outcome == "done"
    assert len(calls) == 4
    assert no_sleep.waits == [2, 4, 8]
    assert producer.sent == []


# agent-mock

async def test_agent_invalid_payload_goes_to_dlq():
    producer = FakeProducer()
    outcome = await agent_handle(FakeRecord(value=b"[]", topic="helpdesk.inbound"), producer, SETTINGS)
    assert outcome == "dead_letter"
    assert [s["topic"] for s in producer.sent] == ["helpdesk.inbound.dlq"]


async def test_agent_publishes_reply_keyed_by_conversation():
    producer = FakeProducer()
    req = agent_request()
    outcome = await agent_handle(record_of(req, "helpdesk.inbound"), producer, SETTINGS)
    assert outcome == "agent.replied"
    sent = producer.sent[0]
    assert (sent["topic"], sent["key"]) == ("helpdesk.outbound", str(req.conversation_id).encode())
    assert ("trace_id", str(req.trace_id).encode()) in sent["headers"]
