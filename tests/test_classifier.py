import pytest

from helpdesk.config import Settings
from helpdesk.triage.classifier import KeywordClassifier, get_classifier
from helpdesk.triage.dataset import load_labeled_messages

classifier = KeywordClassifier()


@pytest.mark.parametrize("brand, text, category, priority", [
    ("infinitepay", "Minha maquininha não liga", "hardware", "normal"),
    ("infinitepay", "O Pix não caiu na conta", "payments", "normal"),
    ("infinitepay", "Acho que fui vítima de golpe", "fraud", "high"),
    ("infinitepay", "Meu cartão está bloqueado", "card", "high"),
    ("jim", "My card reader won't turn on", "hardware", "normal"),
    ("jim", "Urgent: where is my payout?", "payments", "high"),
    ("jim", "Is there a fee for travel agency purchases?", "other", "normal"),
])
def test_classifies_examples(brand, text, category, priority):
    result = classifier.classify(text, brand, "chat")
    assert (result.category, result.priority) == (category, priority)


def test_no_terms_gives_other_with_zero_confidence():
    result = classifier.classify("Bom dia!", "infinitepay", "chat")
    assert (result.category, result.confidence, result.matched_terms) == ("other", 0.0, ())


def test_reports_classifier_and_version():
    result = classifier.classify("Esqueci a senha", "infinitepay", "chat")
    assert (result.classifier, result.version) == ("keyword", KeywordClassifier.version)
    assert "senha" in result.matched_terms


def test_keyword_classifier_accuracy_on_labeled_messages():
    messages = load_labeled_messages()
    results = [(m, classifier.classify(m.text, m.brand, "chat")) for m in messages]
    wrong_category = [(m.text, m.category, r.category) for m, r in results if r.category != m.category]
    wrong_priority = [(m.text, m.priority, r.priority) for m, r in results if r.priority != m.priority]

    assert len(wrong_category) / len(messages) <= 0.10, wrong_category
    assert len(wrong_priority) / len(messages) <= 0.10, wrong_priority


def test_get_classifier():
    assert isinstance(get_classifier(Settings(database_url="postgresql://x")), KeywordClassifier)
    with pytest.raises(ValueError):
        get_classifier(Settings(database_url="postgresql://x", classifier="desconhecido"))


def test_keyword_classifier_does_not_measure_sentiment():
    result = classifier.classify("Quero falar com um atendente!!!", "infinitepay", "chat")
    assert (result.frustration, result.wants_human, result.fallback_reason) == (None, None, None)
