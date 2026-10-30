"""Simulador de canais. Uso:
    python -m helpdesk.simulator.main send [--channel chat|whatsapp|email] [--brand infinitepay|jim] [--text "..."]
    python -m helpdesk.simulator.main smoke
"""
import argparse
import json
import random
import sys
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from helpdesk.config import get_settings
from helpdesk.simulator.data import CUSTOMERS, PHRASES
from helpdesk.simulator.smoke import SmokeFailure, run_smoke


def build_payload(channel: str, brand: str, text: str) -> dict:
    """Cada canal tem o seu formato, como teria na integração real."""
    customer = random.choice(CUSTOMERS[brand])
    sent_at = datetime.now(timezone.utc).isoformat()
    if channel == "whatsapp":
        return {"wa_message_id": f"wamid.{uuid4().hex}", "from_phone": customer["phone"],
                "profile_name": customer["name"], "brand": brand, "body": text, "timestamp": sent_at}
    if channel == "email":
        subject, _, body = text.partition(". ")
        return {"message_id": f"<{uuid4().hex}@example.com>", "from_address": customer["email"],
                "from_name": customer["name"], "to_address": f"suporte@{brand}.example.com",
                "brand": brand, "subject": subject, "body_text": body or text, "received_at": sent_at}
    return {"session_id": f"sim-{uuid4()}", "message_id": f"sim-{uuid4()}", "brand": brand,
            "customer": {k: customer[k] for k in ("external_id", "name", "email")},
            "text": text, "sent_at": sent_at}


def send(platform_url: str, channel: str, brand: str, text: str | None) -> dict:
    payload = build_payload(channel, brand, text or random.choice(PHRASES[brand]))
    response = httpx.post(f"{platform_url}/channels/{channel}/messages", json=payload, timeout=5)
    response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(prog="simulator")
    commands = parser.add_subparsers(dest="command", required=True)
    send_cmd = commands.add_parser("send", help="envia uma mensagem sintética")
    send_cmd.add_argument("--channel", choices=["chat", "whatsapp", "email"], default="chat")
    send_cmd.add_argument("--brand", choices=sorted(CUSTOMERS), default="infinitepay")
    send_cmd.add_argument("--text")
    smoke_cmd = commands.add_parser("smoke", help="smoke test ponta a ponta")
    smoke_cmd.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()

    platform_url = get_settings().platform_url
    if args.command == "send":
        print(json.dumps(send(platform_url, args.channel, args.brand, args.text), indent=2))
        return 0
    try:
        run_smoke(platform_url, args.timeout)
    except (SmokeFailure, httpx.HTTPError) as exc:
        print(f"SMOKE FALHOU: {exc}")
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
