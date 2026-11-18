"""Análise do experimento: agrega as 3 rodadas de cada cenário e gera os gráficos do README.

Uso: docker compose run --rm analysis [experiment/results/<data>]   (padrão: o experimento mais recente)

Lê o summary.json de cada rodada (gerado por run_summary.py) e, para o gráfico de linha do tempo,
o report.json (horário de cada mensagem) e o meta.json (janela da queda). Grava na pasta do experimento:
  rodadas.csv            uma linha por rodada
  cenarios.md            média ± desvio-padrão por cenário (tabela do README)
  latencia.png           p50, p95 e p99 ponta a ponta por cenário (média e desvio das 3 rodadas)
  vazao.png              taxa pedida × vazão ponta a ponta por cenário
  agente_fora.png        latência de cada mensagem ao longo da rodada, com a queda marcada
"""
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

ORDER = ["base", "pico", "agente-fora", "reentrega", "maxima"]
LABELS = {"base": "Base (2 msg/s)", "pico": "Pico (11)", "agente-fora": "Pico, agente fora (11)",
          "reentrega": "Reentrega forçada (11)", "maxima": "Máxima (22)"}
# Verde = IA e cobre = equipe são as cores das telas
COLORS = {"p50": "#00875A", "p95": "#B0521A", "p99": "#5B5BD6"}
LIMIT_S = 1.0


def load_runs(root: Path) -> pd.DataFrame:
    rows = [json.loads(p.read_text()) for p in sorted(root.glob("*/summary.json"))]
    if not rows:
        sys.exit(f"nenhum summary.json em {root}")
    df = pd.DataFrame(rows)
    df["scenario"] = pd.Categorical(df["scenario"], [s for s in ORDER if s in set(df["scenario"])], ordered=True)
    return df.sort_values(["scenario", "run"])


def aggregate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    metrics = ["send_rate", "throughput", "ingest_p95_ms", "e2e_p50_s", "e2e_p95_s", "e2e_p99_s", "e2e_max_s",
               "outside_p95_s", "recovery_s", "during_outage", "outage_s"]
    metrics = [m for m in metrics if m in df]
    agg = df.groupby("scenario", observed=True)[metrics].agg(["mean", "std"])
    totals = df.groupby("scenario", observed=True)[["accepted", "lost", "duplicated", "out_of_order",
                                                     "dropped_iterations"]].sum()
    return agg, totals


def fmt(mean, std, digits=2):
    if pd.isna(mean):
        return "–"
    return f"{mean:.{digits}f} ± {0 if pd.isna(std) else std:.{digits}f}"


def markdown(df: pd.DataFrame, agg: pd.DataFrame, totals: pd.DataFrame) -> str:
    runs = df.groupby("scenario", observed=True)["run"].count()
    lines = ["| Cenário | Rodadas | Mensagens | Perdidas | Duplicadas | Fora de ordem | Vazão (resp/s) | "
             "Ingestão p95 (ms) | Ponta a ponta p50 (s) | p95 (s) | p99 (s) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for scenario in agg.index:
        a, t = agg.loc[scenario], totals.loc[scenario]
        lines.append(
            f"| {LABELS[scenario]} | {runs[scenario]} | {t['accepted']} | {t['lost']} | {t['duplicated']} | {t['out_of_order']} | "
            f"{fmt(a['throughput']['mean'], a['throughput']['std'], 1)} | "
            f"{fmt(a['ingest_p95_ms']['mean'], a['ingest_p95_ms']['std'], 1)} | "
            f"{fmt(a['e2e_p50_s']['mean'], a['e2e_p50_s']['std'])} | {fmt(a['e2e_p95_s']['mean'], a['e2e_p95_s']['std'])} | "
            f"{fmt(a['e2e_p99_s']['mean'], a['e2e_p99_s']['std'])} |")
    if "agente-fora" in agg.index and "outage_s" in agg:
        a = agg.loc["agente-fora"]
        out = df[df.scenario == "agente-fora"]
        verdicts = ", ".join("confirmada" if h else "refutada" for h in out["hypothesis"])
        lines += ["", "Agente fora do ar (média ± desvio das rodadas):", "",
                  "| Queda medida (s) | Mensagens na queda | p95 fora da queda (s) | Recuperação (s) | Hipótese por rodada |",
                  "|---|---|---|---|---|",
                  f"| {fmt(a['outage_s']['mean'], a['outage_s']['std'], 1)} | "
                  f"{fmt(a['during_outage']['mean'], a['during_outage']['std'], 0)} | "
                  f"{fmt(a['outside_p95_s']['mean'], a['outside_p95_s']['std'])} | "
                  f"{fmt(a['recovery_s']['mean'], a['recovery_s']['std'], 1)} | {verdicts} |"]
    return "\n".join(lines) + "\n"


def layout(fig: go.Figure, title: str, y_title: str) -> go.Figure:
    fig.update_layout(title=title, template="plotly_white", font=dict(family="Helvetica, Arial", size=14),
                      yaxis_title=y_title, legend=dict(orientation="h", y=-0.18), margin=dict(t=70, b=90),
                      width=1000, height=520)
    return fig


def latency_chart(agg: pd.DataFrame) -> go.Figure:
    names = [LABELS[s] for s in agg.index]
    fig = go.Figure()
    for p in ("p50", "p95", "p99"):
        col = agg[f"e2e_{p}_s"]
        fig.add_bar(name=p, x=names, y=col["mean"], marker_color=COLORS[p],
                    error_y=dict(type="data", array=col["std"].fillna(0)))
    fig.add_hline(y=LIMIT_S, line_dash="dash", line_color="#666",
                  annotation_text="limite da hipótese (p95 < 1 s, fora da queda)", annotation_position="top left")
    fig.update_layout(barmode="group")
    return layout(fig, "Latência ponta a ponta (recebida → respondida pelo agente), média de 3 rodadas", "segundos")


def throughput_chart(df: pd.DataFrame, agg: pd.DataFrame) -> go.Figure:
    names = [LABELS[s] for s in agg.index]
    requested = df.groupby("scenario", observed=True)["rate"].first()
    fig = go.Figure()
    fig.add_bar(name="taxa pedida ao k6", x=names, y=requested.values, marker_color="#C9CED6")
    fig.add_bar(name="vazão ponta a ponta", x=names, y=agg["throughput"]["mean"], marker_color=COLORS["p50"],
                error_y=dict(type="data", array=agg["throughput"]["std"].fillna(0)))
    fig.update_layout(barmode="group")
    return layout(fig, "Taxa pedida × respostas por segundo", "mensagens por segundo")


def outage_chart(root: Path) -> go.Figure | None:
    run_dir = root / "agente-fora-1"
    if not (run_dir / "report.json").exists():
        return None
    meta = json.loads((run_dir / "meta.json").read_text())
    samples = pd.DataFrame(json.loads((run_dir / "report.json").read_text())["samples"])
    samples["received_at"] = pd.to_datetime(samples["received_at"], format="ISO8601", utc=True)
    t0 = samples["received_at"].min()
    samples["t"] = (samples["received_at"] - t0).dt.total_seconds()
    start = (pd.Timestamp(meta["outage_start"]) - t0).total_seconds()
    end = (pd.Timestamp(meta["outage_end"]) - t0).total_seconds()
    fig = go.Figure()
    fig.add_vrect(x0=start, x1=end, fillcolor="#B0521A", opacity=0.12, line_width=0,
                  annotation_text="agente fora do ar", annotation_position="top left")
    fig.add_scatter(x=samples["t"], y=samples["latency_s"], mode="markers", name="mensagem",
                    marker=dict(size=5, color=COLORS["p50"]))
    fig.add_hline(y=LIMIT_S, line_dash="dash", line_color="#666", annotation_text="1 s")
    fig.update_xaxes(title="segundos desde a primeira mensagem (rodada 1)")
    return layout(fig, "Pico com o agente fora do ar: latência de cada mensagem", "latência ponta a ponta (s)")


def main(argv: list[str]) -> int:
    results = Path("experiment/results")
    root = Path(argv[0]) if argv else max(p for p in results.iterdir() if p.is_dir())
    df = load_runs(root)
    agg, totals = aggregate(df)
    df.to_csv(root / "rodadas.csv", index=False)
    table = markdown(df, agg, totals)
    (root / "cenarios.md").write_text(table)
    latency_chart(agg).write_image(root / "latencia.png", scale=2)
    throughput_chart(df, agg).write_image(root / "vazao.png", scale=2)
    if (fig := outage_chart(root)) is not None:
        fig.write_image(root / "agente_fora.png", scale=2)
    print(table)
    print(f"gráficos e tabelas em {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
