import pytest
from typesafe_sdk import SystemOneResponse, TypeSafeAPIConnectionError, TypeSafeAPITimeoutError

from helpdesk.config import Settings
from helpdesk.triage.classifier import KeywordClassifier, get_classifier
from helpdesk.triage.jev import JevClassifier
from helpdesk.triage.jev_questions import QUESTIONS, QUESTIONS_VERSION


def answers(topic="hardware", has_topic=0.95, frustration=0.4, wants_human=0.05, urgent=0.1):
    probs = {k: 0.0 for k in ("payments", "card", "hardware", "account", "fraud")} | {topic: 0.9}
    return SystemOneResponse.model_validate({
        "model": "jev-1.14.0",
        "usage": {"input_tokens": 800, "output_tokens": 0},
        "answers": {
            "topic": {"type": "choice", "choice": topic, "confidence": 0.9, "probabilities": probs},
            "has_topic": {"type": "noul", "noul": has_topic},
            "frustration": {"type": "score", "score": frustration, "confidence": 0.7,
                            "legend": {0: "a", 1: "b", 2: "c", 3: "d"},
                            "probabilities": {0: 0.6, 1: 0.4, 2: 0.0, 3: 0.0}},
            "wants_human": {"type": "noul", "noul": wants_human},
            "urgent": {"type": "noul", "noul": urgent},
        },
    })


class FakeTypeSafe:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def system_one(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def jev(client):
    return JevClassifier(client, "jev-1.14.0", 1.0)


def test_sends_all_questions_with_pinned_model_and_timeout():
    client = FakeTypeSafe(answers())
    jev(client).classify("Minha maquininha não liga", "infinitepay", "chat")
    call = client.calls[0]
    assert set(call["questions"]) == set(QUESTIONS)
    assert (call["model"], call["timeout"]) == ("jev-1.14.0", 1.0)
    assert call["state"]["message"] == "Minha maquininha não liga"
    assert "InfinitePay" in call["state"]["company"]


def test_state_carries_who_said_what_and_caps_history():
    client = FakeTypeSafe(answers())
    history = [{"author": "customer" if i % 2 else "agent", "text": f"m{i}"} for i in range(15)]
    jev(client).classify("de novo isso", "infinitepay", "chat", history)
    conversation = client.calls[0]["state"]["conversation"]
    assert len(conversation) == 10
    assert conversation[0] == {"from": "customer", "text": "m5"}
    assert conversation[-1] == {"from": "agent", "text": "m14"}


def test_maps_answers_through_the_decision_table():
    result = jev(FakeTypeSafe(answers(topic="payments", urgent=0.9, frustration=2.3, wants_human=0.1))).classify(
        "x", "infinitepay", "chat")
    assert (result.category, result.priority) == ("payments", "high")
    assert (result.frustration, result.wants_human) == (2.3, 0.1)
    assert result.classifier == "jev"
    assert result.version == f"jev-1.14.0/q{QUESTIONS_VERSION}"
    assert result.signals["frustration"] == {0: 0.6, 1: 0.4, 2: 0.0, 3: 0.0}
    assert result.fallback_reason is None


def test_no_topic_becomes_other_with_inverse_confidence():
    result = jev(FakeTypeSafe(answers(topic="card", has_topic=0.1))).classify("Valeu!", "jim", "chat")
    assert (result.category, result.confidence) == ("other", 0.9)


@pytest.mark.parametrize("error, name", [
    (TypeSafeAPITimeoutError(1.0), "TypeSafeAPITimeoutError"),
    (TypeSafeAPIConnectionError("sem rede"), "TypeSafeAPIConnectionError"),
])
def test_failure_falls_back_to_rules_and_says_why(error, name):
    result = jev(FakeTypeSafe(error=error)).classify("Minha maquininha não liga", "infinitepay", "chat")
    assert (result.classifier, result.category) == ("keyword", "hardware")
    assert result.fallback_reason.startswith(name)
    assert result.frustration is None


def test_missing_answer_falls_back_to_rules():
    response = answers()
    del response.answers["urgent"]
    result = jev(FakeTypeSafe(response)).classify("Minha maquininha não liga", "infinitepay", "chat")
    assert result.classifier == "keyword"
    assert result.fallback_reason.startswith("KeyError")


def test_get_classifier_choices():
    base = {"database_url": "postgresql://x"}
    assert isinstance(get_classifier(Settings(**base)), KeywordClassifier)
    assert isinstance(get_classifier(Settings(**base, classifier="jev", typesafe_api_key="")), KeywordClassifier)
    assert isinstance(get_classifier(Settings(**base, classifier="jev", typesafe_api_key="k")), JevClassifier)
    with pytest.raises(ValueError):
        get_classifier(Settings(**base, classifier="llm-qualquer"))
