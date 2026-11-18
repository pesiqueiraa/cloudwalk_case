"""Resumo de uma rodada do experimento (só biblioteca padrão; roda no host).

Uso: python3 experiment/run_summary.py experiment/results/<data>/<cenário>-<n> [...]

Lê meta.json, k6-summary.json e report.json da rodada e imprime uma linha. Grava summary.json
na pasta da rodada, que é o que a análise (pandas) lê.

Hipótese (decisão de 17/11): no pico de referência (11 msg/s), com o agente fora do ar por 10 s,
nenhuma mensagem se perde ou duplica, e 95% das respostas às mensagens enviadas fora da queda
chegam em menos de 1 s. As mensagens recebidas durante a queda são medidas à parte: quanto tempo,
depois da volta do agente, a última delas levou para ser respondida (recuperação).
"""
import json
import math
import sys
from datetime import datetime
from pathlib import Path

P95_LIMIT_S = 1.0


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(p / 100 * len(ordered)) - 1))]


def summarize(run_dir: Path) -> dict:
    meta = json.loads((run_dir / "meta.json").read_text())
    k6 = json.loads((run_dir / "k6-summary.json").read_text())
    report = json.loads((run_dir / "report.json").read_text())
    samples = report["samples"]
    summary = {
        "scenario": meta["scenario"], "run": meta["run"], "rate": meta["rate"], "count": meta["count"],
        "accepted": k6["accepted"], "rejected": k6["rejected"], "dropped_iterations": k6["dropped_iterations"],
        "send_rate": k6["accepted"] / k6["send_window_s"] if k6["send_window_s"] else None,
        "ingest_p50_ms": k6["ingest_ms"]["p50"], "ingest_p95_ms": k6["ingest_ms"]["p95"],
        "ingest_p99_ms": k6["ingest_ms"]["p99"],
        "lost": report["lost"], "duplicated": report["duplicated"], "out_of_order": report["out_of_order"],
        "resent_webhooks": report["resent_webhooks"], "throughput": report["throughput"],
        "e2e_p50_s": report["p50_s"], "e2e_p95_s": report["p95_s"], "e2e_p99_s": report["p99_s"],
        "e2e_max_s": report["max_s"], "verify_ok": report["ok"],
    }
    for key in ("rewound_agent_mock", "rewound_broker_outbound"):
        if key in meta:
            summary[key] = meta[key]

    if "outage_start" in meta:
        start = datetime.fromisoformat(meta["outage_start"])
        end = datetime.fromisoformat(meta["outage_end"])
        is_inside = [start <= datetime.fromisoformat(s["received_at"]) <= end for s in samples]
        inside = [s for s, flag in zip(samples, is_inside) if flag]
        outside = [s["latency_s"] for s, flag in zip(samples, is_inside) if not flag]
        last_reply = max((datetime.fromisoformat(s["replied_at"]) for s in inside), default=None)
        summary |= {
            "outage_s": (end - start).total_seconds(),
            "during_outage": len(inside),
            "outside_p95_s": percentile(outside, 95),
            "outside_p99_s": percentile(outside, 99),
            "recovery_s": (last_reply - end).total_seconds() if last_reply else None,
        }
        latency_ok = summary["outside_p95_s"] is not None and summary["outside_p95_s"] < P95_LIMIT_S
        summary["hypothesis"] = bool(report["ok"] and latency_ok)
    return summary


def line(s: dict) -> str:
    def f(v, fmt):
        return "-" if v is None else format(v, fmt)
    text = (f"{s['scenario']:<12} #{s['run']}  {s['accepted']}/{s['count']} a {f(s['send_rate'], '.1f')} msg/s  "
            f"perdidas={s['lost']} duplicadas={s['duplicated']} fora_de_ordem={s['out_of_order']}  "
            f"e2e p50={f(s['e2e_p50_s'], '.2f')} p95={f(s['e2e_p95_s'], '.2f')} p99={f(s['e2e_p99_s'], '.2f')} s  "
            f"ingestão p95={f(s['ingest_p95_ms'], '.1f')} ms  descartadas_k6={s['dropped_iterations']}")
    if "outage_s" in s:
        text += (f"\n{'':<14}queda={s['outage_s']:.1f} s  na queda={s['during_outage']}  "
                 f"p95 fora da queda={f(s['outside_p95_s'], '.2f')} s  recuperação={f(s['recovery_s'], '.1f')} s  "
                 f"HIPÓTESE {'CONFIRMADA' if s['hypothesis'] else 'REFUTADA'}")
    return text


def main(paths: list[str]) -> int:
    ok = True
    for path in paths:
        run_dir = Path(path)
        summary = summarize(run_dir)
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        print(line(summary))
        ok = ok and summary["verify_ok"] and summary.get("hypothesis", True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
