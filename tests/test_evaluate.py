from helpdesk.triage import evaluate
from helpdesk.triage.classifier import Classification, KeywordClassifier
from helpdesk.triage.dataset import load_sentiment_messages


class FixedSentiment:
    def __init__(self, frustration, wants_human):
        self.frustration, self.wants_human = frustration, wants_human

    def classify(self, text, brand, channel, history=()):
        return Classification("other", "normal", 1.0, "fixo", "1", (), self.frustration, self.wants_human)


def ticking_clock(step=0.01):
    t = [0.0]

    def clock():
        t[0] += step
        return t[0]
    return clock


def test_sentiment_sets_are_labeled_consistently():
    for name in ("hard", "blind"):
        for m in load_sentiment_messages(name):
            assert m.brand in ("infinitepay", "jim") and 0 <= m.frustration <= 3, m


def test_load_cases_includes_base_and_hard():
    datasets = {c.dataset for c in evaluate.load_cases()}
    assert {"base", "hard"} <= datasets


def test_frustration_metrics():
    cases = [evaluate.Case("hard", "jim", "a", "other", 3, False),
             evaluate.Case("hard", "jim", "b", "other", 0, False)]
    report = evaluate.run(FixedSentiment(2.4, 0.1), "fixo", cases, clock=ticking_clock())
    m = evaluate.frustration_metrics(report.outcomes)
    assert (m["exact"], m["near"], m["hits"], m["predicted"], m["actual"]) == (0, 1, 1, 2, 1)
    assert evaluate.wants_human_accuracy(report.outcomes) == (2, 2)


def test_markdown_compares_classifiers_and_skips_unmeasured_sentiment():
    cases = [evaluate.Case("base", "infinitepay", "Minha maquininha não liga", "hardware"),
             evaluate.Case("hard", "infinitepay", "A tela da POS apagou", "hardware", 1, False)]
    reports = [evaluate.run(KeywordClassifier(), "regras", cases, clock=ticking_clock()),
               evaluate.run(FixedSentiment(1.0, 0.0), "fixo", cases, clock=ticking_clock())]
    md = evaluate.to_markdown(reports)
    assert "| Categoria — base | 1 | 100% | 0% |" in md
    assert "## Sentimento (fixo)" in md and "## Sentimento (regras)" not in md
    assert "| regras | 10 ms | 10 ms | 0 |" in md
