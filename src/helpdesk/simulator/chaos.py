"""Lote de mensagens e conferência pela API: nenhuma perdida, nenhuma duplicada, ordem por conversa.

burst  manda N mensagens (opcionalmente várias por conversa, ou cada uma duas vezes) e imprime em stdout
       um JSON com o trace_id de cada uma; o progresso vai para stderr.
verify lê esse JSON, espera as respostas pela API e confere, para cada mensagem:
       1 message.received, 1 agent.replied, 1 mensagem do agente; e a ordem das respostas por conversa.
"""
import json
import math
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

import httpx

from helpdesk.agent_mock.policy import ESCALATION_TERMS
from helpdesk.contracts import BRAND_LOCALE
from helpdesk.simulator.data import CUSTOMERS
from helpdesk.triage.dataset import load_labeled_messages

# Categorias que ficam com o agente (fraude vai para fila humana e não tem resposta)
AGENT_CATEGORIES = ("payments", "hardware", "card", "account")


def agent_texts(brand: str) -> list[str]:
    """Frases que o agente responde sem escalar: a conferência espera exatamente uma resposta."""
    terms = ESCALATION_TERMS[BRAND_LOCALE[brand]]
    return [m.text for m in load_labeled_messages()
            if m.brand == brand and m.category in AGENT_CATEGORIES and not terms.search(m.text)]


def k6_pool(brand: str) -> dict:
    """Frases e clientes sintéticos que o gerador k6 sorteia; as mesmas regras do burst."""
    return {"brand": brand, "texts": agent_texts(brand),
            "customers": [{k: c[k] for k in ("external_id", "name", "email")} for c in CUSTOMERS[brand]]}


def from_k6_lines(lines: list[str], rate: float | None = None) -> dict:
    """Converte a saída do k6 (uma linha JSON por mensagem) no lote que o verify lê.

    Linhas com "error" são requisições que a ingestão recusou ou não respondeu: entram em
    ingest_errors e contam como falha no verify, porque o canal não teve confirmação.
    """
    sent, errors = [], []
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        item = json.loads(line)
        if "error" in item:
            errors.append(item)
        else:
            sent.append({k: item[k] for k in ("trace_id", "conversation_id", "message_id", "seq")}
                        | {"ingest_ms": item.get("ingest_ms")})
    sent.sort(key=lambda s: s["seq"])
    return {"messages": sent, "rate": rate, "ingest_errors": len(errors), "source": "k6"}


def chat_payload(brand: str, session_id: str, text: str) -> dict:
    customer = random.choice(CUSTOMERS[brand])
    return {"session_id": session_id, "message_id": f"chaos-{uuid4()}", "brand": brand,
            "customer": {k: customer[k] for k in ("external_id", "name", "email")},
            "text": text, "sent_at": datetime.now().astimezone().isoformat()}


def burst(platform_url: str, count: int, rate: float, per_conversation: int = 1,
          duplicate: bool = False, brand: str = "infinitepay") -> dict:
    texts = agent_texts(brand)
    sent = []
    interval = 1 / rate if rate > 0 else 0
    start = time.monotonic()
    with httpx.Client(base_url=platform_url, timeout=10) as client:
        session_id = None
        for i in range(count):
            if i % per_conversation == 0:
                session_id = f"chaos-{uuid4()}"
            payload = chat_payload(brand, session_id, random.choice(texts))
            copies = 2 if duplicate else 1
            results = []
            for _ in range(copies):
                response = client.post("/channels/chat/messages", json=payload)
                response.raise_for_status()
                results.append(response.json())
            if duplicate and not results[1]["duplicate"]:
                raise RuntimeError(f"cópia não marcada como duplicata: {payload['message_id']}")
            first = results[0]
            sent.append({"trace_id": first["trace_id"], "conversation_id": first["conversation_id"],
                         "message_id": first["message_id"], "seq": i})
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{count} enviadas", file=sys.stderr)
            # Ritmo constante: espera até o horário da próxima mensagem
            delay = start + (i + 1) * interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
    elapsed = time.monotonic() - start
    print(f"{count} mensagens em {elapsed:.1f} s ({count / elapsed:.1f} msg/s)", file=sys.stderr)
    return {"messages": sent, "rate": rate, "elapsed_s": elapsed}


@dataclass
class Report:
    total: int
    lost: list[str] = field(default_factory=list)
    duplicated: list[str] = field(default_factory=list)
    out_of_order: list[str] = field(default_factory=list)
    resent_webhooks: int = 0
    latencies_s: list[float] = field(default_factory=list)
    # Uma linha por mensagem respondida, com os horários da auditoria: a análise separa janelas (ex.: queda)
    samples: list[dict] = field(default_factory=list)
    ingest_errors: int = 0
    # Janela da primeira mensagem recebida à última respondida, para a vazão ponta a ponta
    window_s: float | None = None

    @property
    def ok(self) -> bool:
        return not (self.lost or self.duplicated or self.out_of_order or self.ingest_errors)

    @property
    def throughput(self) -> float | None:
        """Respostas por segundo ao longo da janela do lote."""
        if not self.window_s:
            return None
        return len(self.latencies_s) / self.window_s

    def as_dict(self) -> dict:
        lat = self.latencies_s
        return {"total": self.total, "lost": len(self.lost), "duplicated": len(self.duplicated),
                "out_of_order": len(self.out_of_order), "resent_webhooks": self.resent_webhooks,
                "ingest_errors": self.ingest_errors, "window_s": self.window_s,
                "throughput": self.throughput,
                "p50_s": percentile(lat, 50) if lat else None, "p95_s": percentile(lat, 95) if lat else None,
                "p99_s": percentile(lat, 99) if lat else None, "max_s": max(lat) if lat else None,
                "samples": self.samples, "ok": self.ok}


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    # Nearest-rank: o menor valor com pelo menos p% dos valores abaixo ou iguais
    index = min(len(ordered) - 1, max(0, math.ceil(p / 100 * len(ordered)) - 1))
    return ordered[index]


def analyze(sent: list[dict], audit_by_trace: dict[str, list[dict]],
            messages_by_conversation: dict[str, list[dict]]) -> Report:
    report = Report(total=len(sent))
    first_received, last_replied = None, None
    for item in sent:
        trace = item["trace_id"]
        events = audit_by_trace.get(trace, [])
        types = [e["type"] for e in events]
        agent_messages = [m for m in messages_by_conversation.get(item["conversation_id"], [])
                          if m["author"] == "agent" and m["trace_id"] == trace]
        replies = types.count("agent.replied")
        if replies == 0 or not agent_messages:
            report.lost.append(trace)
        elif replies > 1 or len(agent_messages) > 1 or types.count("message.received") > 1:
            report.duplicated.append(trace)
        report.resent_webhooks += max(0, types.count("message.sent_to_agent") - 1)
        received = next((e for e in events if e["type"] == "message.received"), None)
        replied = next((e for e in events if e["type"] == "agent.replied"), None)
        if received and replied:
            received_at = datetime.fromisoformat(received["occurred_at"])
            replied_at = datetime.fromisoformat(replied["occurred_at"])
            latency = (replied_at - received_at).total_seconds()
            report.latencies_s.append(latency)
            report.samples.append({"trace_id": trace, "conversation_id": item["conversation_id"],
                                   "seq": item["seq"], "received_at": received["occurred_at"],
                                   "replied_at": replied["occurred_at"], "latency_s": latency})
            first_received = min(first_received or received_at, received_at)
            last_replied = max(last_replied or replied_at, replied_at)
    if first_received and last_replied:
        report.window_s = (last_replied - first_received).total_seconds()

    # Ordem por conversa: as respostas do agente saem na mesma ordem das perguntas
    by_conversation: dict[str, list[dict]] = {}
    for item in sorted(sent, key=lambda s: s["seq"]):
        by_conversation.setdefault(item["conversation_id"], []).append(item)
    for conversation_id, items in by_conversation.items():
        asked = [i["trace_id"] for i in items]
        answered = [m["trace_id"] for m in messages_by_conversation.get(conversation_id, [])
                    if m["author"] == "agent" and m["trace_id"] in asked]
        if answered != [t for t in asked if t in answered]:
            report.out_of_order.append(conversation_id)
    return report


def collect(client: httpx.Client, sent: list[dict]) -> tuple[dict, dict]:
    audit_by_trace = {s["trace_id"]: client.get(f"/api/traces/{s['trace_id']}/audit").json() for s in sent}
    messages = {}
    for conversation_id in {s["conversation_id"] for s in sent}:
        messages[conversation_id] = client.get(f"/api/conversations/{conversation_id}").json()["messages"]
    return audit_by_trace, messages


def verify(platform_url: str, data: dict, timeout_s: float = 120, settle_s: float = 5) -> Report:
    """Espera todas as respostas (ou o timeout), espera mais settle_s para pegar reentregas, e confere."""
    sent = data["messages"]
    deadline = time.monotonic() + timeout_s
    with httpx.Client(base_url=platform_url, timeout=10) as client:
        while True:
            audit_by_trace, messages = collect(client, sent)
            pending = [s for s in sent if not any(e["type"] == "agent.replied" for e in audit_by_trace[s["trace_id"]])]
            if not pending or time.monotonic() > deadline:
                break
            print(f"  aguardando {len(pending)} resposta(s)", file=sys.stderr)
            time.sleep(2)
        time.sleep(settle_s)
        report = analyze(sent, *collect(client, sent))
    report.ingest_errors = data.get("ingest_errors", 0)
    return report


def print_report(report: Report) -> None:
    print(f"mensagens: {report.total}")
    if report.ingest_errors:
        print(f"recusadas na ingestão: {report.ingest_errors}")
    print(f"perdidas: {len(report.lost)}")
    print(f"duplicadas: {len(report.duplicated)}")
    print(f"fora de ordem (conversas): {len(report.out_of_order)}")
    print(f"webhooks reenviados (absorvidos): {report.resent_webhooks}")
    if report.latencies_s:
        lat = report.latencies_s
        print(f"latência recebida → respondida: p50={percentile(lat, 50):.2f} s  p95={percentile(lat, 95):.2f} s  "
              f"p99={percentile(lat, 99):.2f} s  máx={max(lat):.2f} s")
    if report.throughput:
        print(f"vazão ponta a ponta: {report.throughput:.1f} respostas/s em {report.window_s:.1f} s")
    for label, items in (("perdida", report.lost), ("duplicada", report.duplicated),
                         ("fora de ordem", report.out_of_order)):
        for item in items[:5]:
            print(f"  {label}: {item}")


def dump(data: dict) -> str:
    return json.dumps(data)
