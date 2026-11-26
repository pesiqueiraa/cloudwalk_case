import pytest

from helpdesk.triage import decision


@pytest.mark.parametrize("p, expected", [(0.95, "yes"), (0.71, "yes"), (0.7, "undecided"), (0.5, "undecided"),
                                         (0.3, "undecided"), (0.29, "no"), (0.0, "no")])
def test_band(p, expected):
    assert decision.band(p) == expected


@pytest.mark.parametrize("topic, has_topic, expected", [
    ("hardware", 0.9, "hardware"), ("hardware", 0.5, "hardware"), ("card", 0.49, "other"),
])
def test_category_needs_a_topic(topic, has_topic, expected):
    assert decision.category_from(topic, has_topic) == expected


@pytest.mark.parametrize("category, urgent, expected", [
    ("fraud", 0.0, "high"), ("payments", 0.9, "high"), ("payments", 0.5, "normal"), ("card", 0.1, "normal"),
])
def test_priority(category, urgent, expected):
    assert decision.priority_from(category, urgent) == expected


@pytest.mark.parametrize("p, expected", [(None, False), (0.2, False), (0.6, False), (0.8, True)])
def test_asks_for_human_only_on_clear_yes(p, expected):
    assert decision.asks_for_human(p) is expected


@pytest.mark.parametrize("frustration, threshold, expected", [
    (None, 2, False), (2.4, None, False), (1.4, 2, False), (1.5, 2, True), (2.5, 3, True), (2.49, 3, False),
    (0.0, 0, True),
])
def test_frustration_reached_rounds_half_up(frustration, threshold, expected):
    assert decision.frustration_reached(frustration, threshold) is expected
