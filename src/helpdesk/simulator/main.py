"""Simulador de canais. Uso:
    python -m helpdesk.simulator.main send [--channel chat|whatsapp|email] [--brand infinitepay|jim]
                                           [--category payments|hardware|card|account|fraud|other] [--text "..."]
    python -m helpdesk.simulator.main smoke [--escalation]
    python -m helpdesk.simulator.main burst --count N [--rate R] [--per-conversation K] [--duplicate] > lote.json
    python -m helpdesk.simulator.main verify [--json] < lote.json
    python -m helpdesk.simulator.main k6-pool [--brand ...] > pool.json      frases e clientes para o k6
    python -m helpdesk.simulator.main from-k6 [--rate R] < k6.log > lote.json  saída do k6 → lote do verify
    python -m helpdesk.simulator.main evaluate-classifier > avaliacao.md       regras × Jev nos conjuntos rotulados
"""
import argparse
import json
import random
import sys
from datetime import datetime, timezone
from typing import get_args
from uuid import uuid4

import httpx

from helpdesk.config import get_settings
from helpdesk.contracts import Category
from helpdesk.simulator.data import CUSTOMERS
from helpdesk.simulator import chaos
from helpdesk.simulator.smoke import SmokeFailure, run_escalation_smoke, run_smoke
from helpdesk.triage.dataset import load_labeled_messages


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


def pick_text(brand: str, category: str | None = None) -> str:
    """Sorteia uma frase do banco rotulado, da marca e, se pedida, da categoria."""
    options = [m.text for m in load_labeled_messages()
               if m.brand == brand and (category is None or m.category == category)]
    return random.choice(options)


def send(platform_url: str, channel: str, brand: str, text: str | None, category: str | None = None) -> dict:
    payload = build_payload(channel, brand, text or pick_text(brand, category))
    response = httpx.post(f"{platform_url}/channels/{channel}/messages", json=payload, timeout=5)
    response.raise_for_status()
    return response.json()


def evaluate_classifier() -> int:
    """Roda as regras e, com TYPESAFE_API_KEY, o Jev. Tempo máximo de 5 s: aqui mede-se o acerto, não a reserva."""
    from helpdesk.triage import evaluate
    from helpdesk.triage.classifier import KeywordClassifier
    from helpdesk.triage.jev import JevClassifier

    settings = get_settings()
    cases = evaluate.load_cases()
    reports = [evaluate.run(KeywordClassifier(), "regras", cases)]
    if settings.typesafe_api_key:
        jev = JevClassifier.from_settings(settings.model_copy(update={"jev_timeout_seconds": 5.0}))
        reports.append(evaluate.run(jev, "jev", cases))
    else:
        print("sem TYPESAFE_API_KEY: só as regras", file=sys.stderr)
    print(evaluate.to_markdown(reports))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="simulator")
    commands = parser.add_subparsers(dest="command", required=True)
    send_cmd = commands.add_parser("send", help="envia uma mensagem sintética")
    send_cmd.add_argument("--channel", choices=["chat", "whatsapp", "email"], default="chat")
    send_cmd.add_argument("--brand", choices=sorted(CUSTOMERS), default="infinitepay")
    send_cmd.add_argument("--category", choices=get_args(Category), help="sorteia uma frase desta categoria")
    send_cmd.add_argument("--text", help="texto fixo; tem prioridade sobre --category")
    smoke_cmd = commands.add_parser("smoke", help="smoke test ponta a ponta")
    smoke_cmd.add_argument("--timeout", type=float, default=30)
    smoke_cmd.add_argument("--escalation", action="store_true",
                           help="cliente pede humano: confere o handoff e o bloqueio do agente")
    burst_cmd = commands.add_parser("burst", help="lote de mensagens; imprime o JSON para o verify")
    burst_cmd.add_argument("--count", type=int, required=True)
    burst_cmd.add_argument("--rate", type=float, default=10, help="mensagens por segundo (0 = sem pausa)")
    burst_cmd.add_argument("--per-conversation", type=int, default=1, help="mensagens por conversa")
    burst_cmd.add_argument("--duplicate", action="store_true", help="manda cada mensagem duas vezes")
    burst_cmd.add_argument("--brand", choices=sorted(CUSTOMERS), default="infinitepay")
    verify_cmd = commands.add_parser("verify", help="confere o lote lido de stdin: perdidas, duplicadas, ordem")
    verify_cmd.add_argument("--timeout", type=float, default=120)
    verify_cmd.add_argument("--settle", type=float, default=5, help="espera extra para pegar reentregas")
    verify_cmd.add_argument("--json", action="store_true", help="imprime o relatório em JSON (para a análise)")
    pool_cmd = commands.add_parser("k6-pool", help="frases e clientes sintéticos para o gerador k6")
    pool_cmd.add_argument("--brand", choices=sorted(CUSTOMERS), default="infinitepay")
    from_k6_cmd = commands.add_parser("from-k6", help="converte a saída do k6 (stdin) no lote do verify")
    from_k6_cmd.add_argument("--rate", type=float, help="taxa pedida ao k6, guardada no lote")
    commands.add_parser("evaluate-classifier", help="regras e Jev (se houver chave) nos conjuntos rotulados")
    args = parser.parse_args()

    platform_url = get_settings().platform_url
    if args.command == "send":
        print(json.dumps(send(platform_url, args.channel, args.brand, args.text, args.category), indent=2))
        return 0
    if args.command == "burst":
        print(chaos.dump(chaos.burst(platform_url, args.count, args.rate, args.per_conversation,
                                     args.duplicate, args.brand)))
        return 0
    if args.command == "verify":
        report = chaos.verify(platform_url, json.load(sys.stdin), args.timeout, args.settle)
        if args.json:
            print(json.dumps(report.as_dict()))
        else:
            chaos.print_report(report)
            print("VERIFY OK" if report.ok else "VERIFY FALHOU")
        return 0 if report.ok else 1
    if args.command == "k6-pool":
        print(json.dumps(chaos.k6_pool(args.brand), ensure_ascii=False))
        return 0
    if args.command == "from-k6":
        print(chaos.dump(chaos.from_k6_lines(sys.stdin.readlines(), args.rate)))
        return 0
    if args.command == "evaluate-classifier":
        return evaluate_classifier()
    try:
        (run_escalation_smoke if args.escalation else run_smoke)(platform_url, args.timeout)
    except (SmokeFailure, httpx.HTTPError) as exc:
        print(f"SMOKE FALHOU: {exc}")
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
