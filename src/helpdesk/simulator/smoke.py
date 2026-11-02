"""Smoke tests ponta a ponta, conferidos pela API.

run_smoke: uma mensagem do chat é classificada, roteada e volta respondida, com a auditoria sob um trace_id.
run_escalation_smoke: o cliente pede um humano, o agente escala, a conversa passa para a equipe e a
mensagem seguinte não vai mais ao agente.
"""
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx

EXPECTED_TIMELINE = ["message.received", "message.classified", "conversation.routed",
                     "message.sent_to_agent", "agent.replied"]
ESCALATION_TIMELINE = EXPECTED_TIMELINE + ["conversation.escalated"]
AFTER_HANDOFF_TIMELINE = ["message.received", "message.classified", "message.held_for_human"]


class SmokeFailure(Exception):
    pass


def run_smoke(platform_url: str, timeout_s: float = 30) -> None:
    with httpx.Client(base_url=platform_url, timeout=5) as client:
        payload = {
            "session_id": f"smoke-{uuid4()}",
            "message_id": f"smoke-{uuid4()}",
            "brand": "infinitepay",
            "customer": {"external_id": "smoke-001", "name": "Cliente Smoke", "email": "smoke@example.com"},
            "text": "Minha maquininha não liga",  # cai na fila de Hardware, atendida pela IA
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        response = client.post("/channels/chat/messages", json=payload)
        if response.status_code != 202:
            raise SmokeFailure(f"ingestão devolveu {response.status_code}: {response.text}")
        ingested = response.json()
        trace_id, conversation_id = ingested["trace_id"], ingested["conversation_id"]
        print(f"enviada: trace_id={trace_id} conversation_id={conversation_id}")

        start = time.monotonic()
        reply = None
        while reply is None:
            if time.monotonic() - start > timeout_s:
                raise SmokeFailure(f"sem resposta do agente em {timeout_s:.0f} s")
            time.sleep(0.5)
            messages = client.get(f"/api/conversations/{conversation_id}").json()["messages"]
            reply = next((m for m in messages if m["direction"] == "out" and m["author"] == "agent"), None)
        elapsed = time.monotonic() - start
        print(f"resposta em {elapsed:.2f} s: {reply['text']}")

        events = client.get(f"/api/traces/{trace_id}/audit").json()
        print("linha do tempo:")
        for event in events:
            print(f"  {event['occurred_at']}  {event['type']:<24} {event['actor']:<16} trace_id={event['trace_id']}")

        types = [e["type"] for e in events]
        if types != EXPECTED_TIMELINE:
            raise SmokeFailure(f"linha do tempo {types}, esperado {EXPECTED_TIMELINE}")
        if {e["trace_id"] for e in events} != {trace_id}:
            raise SmokeFailure("eventos com trace_id diferente")

        routed = next(e for e in events if e["type"] == "conversation.routed")["payload"]
        rule = routed["rule"]["name"] if routed["rule"] else "nenhuma (fila padrão)"
        print(f"fila: {routed['queue_name']} (regra: {rule})")


def chat_payload(session_id: str, text: str) -> dict:
    return {
        "session_id": session_id,
        "message_id": f"smoke-{uuid4()}",
        "brand": "infinitepay",
        "customer": {"external_id": "smoke-002", "name": "Cliente Smoke", "email": "smoke@example.com"},
        "text": text,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }


def post_chat(client: httpx.Client, payload: dict) -> dict:
    response = client.post("/channels/chat/messages", json=payload)
    if response.status_code != 202:
        raise SmokeFailure(f"ingestão devolveu {response.status_code}: {response.text}")
    return response.json()


def print_timeline(events: list[dict]) -> None:
    for event in events:
        print(f"  {event['occurred_at']}  {event['type']:<24} {event['actor']:<16} trace_id={event['trace_id']}")


def check_timeline(client: httpx.Client, trace_id: str, expected: list[str]) -> list[dict]:
    events = client.get(f"/api/traces/{trace_id}/audit").json()
    print_timeline(events)
    types = [e["type"] for e in events]
    if types != expected:
        raise SmokeFailure(f"linha do tempo {types}, esperado {expected}")
    if {e["trace_id"] for e in events} != {trace_id}:
        raise SmokeFailure("eventos com trace_id diferente")
    return events


def run_escalation_smoke(platform_url: str, timeout_s: float = 30) -> None:
    session_id = f"smoke-{uuid4()}"
    with httpx.Client(base_url=platform_url, timeout=5) as client:
        first = post_chat(client, chat_payload(session_id, "Quero falar com um atendente"))
        conversation_id = first["conversation_id"]
        print(f"pedido de humano: trace_id={first['trace_id']} conversation_id={conversation_id}")

        start = time.monotonic()
        while True:
            if time.monotonic() - start > timeout_s:
                raise SmokeFailure(f"conversa não foi escalada em {timeout_s:.0f} s")
            time.sleep(0.5)
            view = client.get(f"/api/conversations/{conversation_id}").json()
            if view["conversation"]["handled_by"] == "human":
                break
        conversation = view["conversation"]
        print(f"escalada em {time.monotonic() - start:.2f} s")

        transfer = [m for m in view["messages"] if m["author"] == "agent"]
        if len(transfer) != 1:
            raise SmokeFailure(f"esperada 1 mensagem de transferência do agente, vieram {len(transfer)}")
        print(f"transferência: {transfer[0]['text']}")
        print(f"motivo: {conversation['escalation_reason']}")
        print(f"resumo: {conversation['escalation_summary']}")
        if conversation["status"] != "escalated" or not conversation["escalation_summary"]:
            raise SmokeFailure(f"conversa sem status/resumo de escalação: {conversation}")

        print("linha do tempo do pedido:")
        events = check_timeline(client, first["trace_id"], ESCALATION_TIMELINE)
        escalated = next(e for e in events if e["type"] == "conversation.escalated")["payload"]
        print(f"fila: {escalated['from_queue_id']} → {escalated['to_queue_id']}")

        second = post_chat(client, chat_payload(session_id, "Ainda estou esperando"))
        if second["conversation_id"] != conversation_id:
            raise SmokeFailure("a mensagem seguinte abriu outra conversa")
        print(f"mensagem depois do handoff: trace_id={second['trace_id']}")
        print("linha do tempo da mensagem seguinte:")
        check_timeline(client, second["trace_id"], AFTER_HANDOFF_TIMELINE)
