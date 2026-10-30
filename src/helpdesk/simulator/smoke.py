"""Smoke test ponta a ponta: uma mensagem do chat precisa voltar respondida, com a auditoria sob um trace_id."""
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx

EXPECTED_TIMELINE = ["message.received", "message.sent_to_agent", "agent.replied"]


class SmokeFailure(Exception):
    pass


def run_smoke(platform_url: str, timeout_s: float = 30) -> None:
    with httpx.Client(base_url=platform_url, timeout=5) as client:
        payload = {
            "session_id": f"smoke-{uuid4()}",
            "message_id": f"smoke-{uuid4()}",
            "brand": "infinitepay",
            "customer": {"external_id": "smoke-001", "name": "Cliente Smoke", "email": "smoke@example.com"},
            "text": "Minha maquininha não liga",
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
