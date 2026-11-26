"""Triagem pelo Jev (TypeSafe): uma chamada com as perguntas de jev_questions, decisão em decision.py.

Qualquer falha (rede, tempo esgotado, 4xx/5xx, resposta sem uma pergunta) cai nas regras, e o motivo
vai para a auditoria: a falha nunca vira uma resposta do Jev.
"""
import logging
from collections.abc import Sequence
from dataclasses import replace

from typesafe_sdk import RetryPolicy, TypeSafeClient, TypeSafeError

from helpdesk.config import Settings
from helpdesk.contracts import Brand, Channel
from helpdesk.triage import decision
from helpdesk.triage.classifier import Classification, Classifier, KeywordClassifier
from helpdesk.triage.jev_questions import QUESTIONS, QUESTIONS_VERSION, build_state

log = logging.getLogger(__name__)

HISTORY_MAX = 10   # mensagens anteriores no estado: o bastante para o tom, sem afogar a pergunta


class JevClassifier:
    name = "jev"

    def __init__(self, client: TypeSafeClient, model: str, timeout: float, fallback: Classifier | None = None):
        self._client = client
        self._model = model
        self._timeout = timeout
        self._fallback = fallback or KeywordClassifier()
        self.version = f"{model}/q{QUESTIONS_VERSION}"

    @classmethod
    def from_settings(cls, settings: Settings) -> "JevClassifier":
        # Sem repetição: a chamada está no caminho da ingestão; passou do tempo, as regras assumem
        client = TypeSafeClient(api_key=settings.typesafe_api_key, model=settings.jev_model,
                                retry=RetryPolicy(max_retries=0), timeout=settings.jev_timeout_seconds)
        return cls(client, settings.jev_model, settings.jev_timeout_seconds)

    def classify(self, text: str, brand: Brand, channel: Channel,
                 history: Sequence[dict] = ()) -> Classification:
        state = build_state(brand, text, list(history)[-HISTORY_MAX:])
        try:
            response = self._client.system_one(state=state, questions=QUESTIONS, model=self._model,
                                               timeout=self._timeout)
            answers = response.answers
            topic, has_topic = answers["topic"], answers["has_topic"].noul
            frustration, wants_human, urgent = answers["frustration"], answers["wants_human"].noul, answers["urgent"].noul
        except (TypeSafeError, KeyError, AttributeError) as exc:
            reason = f"{type(exc).__name__}: {exc}"[:300]
            log.warning("Jev indisponível; triagem pelas regras", extra={"error": reason})
            return replace(self._fallback.classify(text, brand, channel, history), fallback_reason=reason)

        category = decision.category_from(topic.choice, has_topic)
        confidence = topic.confidence if category != "other" else 1 - has_topic
        return Classification(
            category=category,
            priority=decision.priority_from(category, urgent),
            confidence=round(confidence, 3),
            classifier=self.name,
            version=response.model and f"{response.model}/q{QUESTIONS_VERSION}" or self.version,
            matched_terms=(),
            frustration=round(frustration.score, 3),
            wants_human=round(wants_human, 3),
            signals={
                "topic": {k: round(v, 3) for k, v in topic.probabilities.items()},
                "has_topic": round(has_topic, 3),
                "frustration": {k: round(v, 3) for k, v in frustration.probabilities.items()},
                "wants_human": round(wants_human, 3),
                "urgent": round(urgent, 3),
            },
        )
