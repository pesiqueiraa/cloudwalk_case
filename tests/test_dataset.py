from collections import Counter
from typing import get_args

from helpdesk.contracts import BRAND_LOCALE, Category, Priority
from helpdesk.triage.dataset import load_labeled_messages


def test_labeled_messages_are_valid():
    messages = load_labeled_messages()
    assert all(m.brand in BRAND_LOCALE for m in messages)
    assert all(m.category in get_args(Category) for m in messages)
    assert all(m.priority in get_args(Priority) for m in messages)
    assert len({m.text for m in messages}) == len(messages)


def test_every_category_has_at_least_five_messages_per_brand():
    counts = Counter((m.brand, m.category) for m in load_labeled_messages())
    for brand in BRAND_LOCALE:
        for category in get_args(Category):
            assert counts[(brand, category)] >= 5, (brand, category)


def test_fraud_is_always_high_priority():
    assert all(m.priority == "high" for m in load_labeled_messages() if m.category == "fraud")


def test_simulator_picks_text_of_requested_brand_and_category():
    from helpdesk.simulator.main import pick_text

    fraud_texts = {m.text for m in load_labeled_messages() if m.brand == "jim" and m.category == "fraud"}
    assert all(pick_text("jim", "fraud") in fraud_texts for _ in range(20))
