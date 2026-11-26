"""Avaliação da triagem: regras e Jev nos mesmos conjuntos rotulados, com acerto, sentimento e latência.

Uso: docker compose run --rm -T simulator evaluate-classifier > avaliacao.md
Os conjuntos: "base" (o banco do simulador, que as regras conhecem), "hard" (paráfrases) e "blind"
(escrito às cegas). O conjunto "base" não tem rótulo de sentimento.
"""
import statistics
import time
from collections.abc import Iterable
from dataclasses import dataclass, field

from helpdesk.triage.classifier import Classification, Classifier
from helpdesk.triage.dataset import SENTIMENT_SETS, load_labeled_messages, load_sentiment_messages
from helpdesk.triage.decision import asks_for_human


@dataclass
class Case:
    dataset: str
    brand: str
    text: str
    category: str
    frustration: int | None = None
    wants_human: bool | None = None


@dataclass
class Outcome:
    case: Case
    result: Classification
    ms: float


@dataclass
class Report:
    classifier: str
    outcomes: list[Outcome] = field(default_factory=list)

    def subset(self, dataset: str) -> list[Outcome]:
        return [o for o in self.outcomes if o.case.dataset == dataset]


def load_cases() -> list[Case]:
    cases = [Case("base", m.brand, m.text, m.category) for m in load_labeled_messages()]
    for name in SENTIMENT_SETS:
        cases += [Case(name, m.brand, m.text, m.category, m.frustration, m.wants_human)
                  for m in load_sentiment_messages(name)]
    return cases


def run(classifier: Classifier, name: str, cases: Iterable[Case], clock=time.perf_counter) -> Report:
    report = Report(name)
    for case in cases:
        start = clock()
        result = classifier.classify(case.text, case.brand, "chat")
        report.outcomes.append(Outcome(case, result, (clock() - start) * 1000))
    return report


def pct(n: int, d: int) -> str:
    return f"{n / d:.0%}" if d else "—"


def category_accuracy(outcomes: list[Outcome]) -> tuple[int, int]:
    return sum(o.result.category == o.case.category for o in outcomes), len(outcomes)


def frustration_metrics(outcomes: list[Outcome]) -> dict:
    """Nível exato, a ±1, e precisão/recall de "frustrado ou mais" (nível ≥ 2)."""
    rated = [o for o in outcomes if o.case.frustration is not None and o.result.frustration is not None]
    level = [round(o.result.frustration) for o in rated]
    exact = sum(lv == o.case.frustration for lv, o in zip(level, rated))
    near = sum(abs(o.result.frustration - o.case.frustration) <= 1 for o in rated)
    predicted = [o for o in rated if o.result.frustration >= 1.5]
    actual = [o for o in rated if o.case.frustration >= 2]
    hits = sum(1 for o in rated if o.result.frustration >= 1.5 and o.case.frustration >= 2)
    return {"n": len(rated), "exact": exact, "near": near, "hits": hits,
            "predicted": len(predicted), "actual": len(actual)}


def wants_human_accuracy(outcomes: list[Outcome]) -> tuple[int, int]:
    rated = [o for o in outcomes if o.case.wants_human is not None and o.result.wants_human is not None]
    return sum(asks_for_human(o.result.wants_human) == o.case.wants_human for o in rated), len(rated)


def to_markdown(reports: list[Report]) -> str:
    datasets = [d for d in ("base", *SENTIMENT_SETS) if any(r.subset(d) for r in reports)]
    lines = ["| Conjunto | n | " + " | ".join(r.classifier for r in reports) + " |",
             "|---|---|" + "---|" * len(reports)]
    for d in datasets:
        n = len(reports[0].subset(d))
        cells = [pct(*category_accuracy(r.subset(d))) for r in reports]
        lines.append(f"| Categoria — {d} | {n} | " + " | ".join(cells) + " |")
    out = ["## Categoria", "", *lines, ""]

    for r in reports:
        rated = [d for d in SENTIMENT_SETS if frustration_metrics(r.subset(d))["n"]]
        if not rated:
            continue
        out += [f"## Sentimento ({r.classifier})", "",
                "| Conjunto | n | Nível exato | ±1 nível | Frustrado ou mais: precisão | recall | Pede humano |",
                "|---|---|---|---|---|---|---|"]
        for d in rated:
            m = frustration_metrics(r.subset(d))
            out.append(f"| {d} | {m['n']} | {pct(m['exact'], m['n'])} | {pct(m['near'], m['n'])} | "
                       f"{pct(m['hits'], m['predicted'])} | {pct(m['hits'], m['actual'])} | "
                       f"{pct(*wants_human_accuracy(r.subset(d)))} |")
        out.append("")

    out += ["## Latência e reservas", "", "| Classificador | p50 | p95 | Caiu nas regras |", "|---|---|---|---|"]
    for r in reports:
        ms = sorted(o.ms for o in r.outcomes)
        p95 = ms[min(len(ms) - 1, int(len(ms) * 0.95))]
        fallbacks = sum(o.result.fallback_reason is not None for o in r.outcomes)
        out.append(f"| {r.classifier} | {statistics.median(ms):.0f} ms | {p95:.0f} ms | {fallbacks} |")

    out += ["", "## Erros de categoria", ""]
    for r in reports:
        for o in r.outcomes:
            if o.result.category != o.case.category:
                out.append(f"- {r.classifier} [{o.case.dataset}] esperado {o.case.category}, "
                           f"veio {o.result.category}: “{o.case.text}”")
    return "\n".join(out) + "\n"
