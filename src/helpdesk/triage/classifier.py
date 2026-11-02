"""Triagem: categoria e prioridade de cada mensagem, atrás de uma interface trocável."""
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from helpdesk.config import Settings
from helpdesk.contracts import BRAND_LOCALE, Brand, Category, Channel, Priority
from helpdesk.text_match import compile_terms


@dataclass(frozen=True)
class Classification:
    category: Category
    priority: Priority
    confidence: float
    classifier: str
    version: str
    matched_terms: tuple[str, ...]


class Classifier(Protocol):
    def classify(self, text: str, brand: Brand, channel: Channel) -> Classification: ...


CATEGORY_TERMS: dict[str, dict[Category, list[str]]] = {
    "pt-BR": {
        "fraud": ["golpe", "fraude", "não reconheço", "clonado", "clonaram", "invadiu", "invadiram",
                  "suspeita", "código de segurança"],
        "payments": ["pagamento", "pagamentos", "pix", "não recebi", "não caiu", "dinheiro", "venda", "vendas",
                     "saldo", "antecipar", "antecipação", "recebimento", "recebimentos", "depósito",
                     "transferência", "saque"],
        "card": ["cartão", "cartão de crédito", "cartão virtual", "segunda via", "limite", "fatura",
                 "desbloquear"],
        "hardware": ["maquininha", "maquina", "máquina", "bateria", "comprovante", "leitor de chip", "defeito"],
        "account": ["senha", "e-mail", "email", "cadastro", "cadastrada", "cadastrado", "conta bancária",
                    "login", "não consigo entrar", "endereço"],
    },
    "en-US": {
        "fraud": ["scam", "scammed", "fraud", "don't recognize", "cloned", "hacked", "unauthorized",
                  "security code"],
        "payments": ["payment", "payout", "payouts", "deposit", "deposited", "money", "balance", "transfer",
                     "sales"],
        "card": ["card", "credit card", "replacement card", "virtual card", "new card", "limit", "statement",
                 "activate"],
        "hardware": ["card reader", "reader", "battery", "receipts", "chip slot", "broken", "screen"],
        "account": ["password", "email", "account", "bank account", "log in", "login", "can't get in", "address"],
    },
}

URGENCY_TERMS = {
    "pt-BR": ["urgente", "urgência", "bloqueado", "bloqueada"],
    "en-US": ["urgent", "asap", "locked"],
}

# Desempate: na dúvida, o caso mais sensível ganha
TIE_ORDER: list[Category] = ["fraud", "payments", "card", "hardware", "account"]


class KeywordClassifier:
    """Conta termos por categoria, com limite de palavra. Termo mais longo ganha ("card reader" > "card")."""

    name = "keyword"
    version = "1"

    def __init__(self) -> None:
        self._category_of = {
            locale: {term: category for category, terms in by_category.items() for term in terms}
            for locale, by_category in CATEGORY_TERMS.items()
        }
        self._patterns = {locale: compile_terms(terms) for locale, terms in self._category_of.items()}
        self._urgency = {locale: compile_terms(terms) for locale, terms in URGENCY_TERMS.items()}

    def classify(self, text: str, brand: Brand, channel: Channel) -> Classification:
        locale = BRAND_LOCALE[brand]
        matched = [m.group(0).lower() for m in self._patterns[locale].finditer(text)]
        counts = Counter(self._category_of[locale][term] for term in matched)

        if counts:
            category = max(TIE_ORDER, key=lambda c: (counts[c], -TIE_ORDER.index(c)))
            confidence = round(counts[category] / sum(counts.values()), 2)
        else:
            category, confidence = "other", 0.0

        urgent = self._urgency[locale].search(text) is not None
        priority: Priority = "high" if category == "fraud" or urgent else "normal"
        return Classification(category, priority, confidence, self.name, self.version, tuple(matched))


def get_classifier(settings: Settings) -> Classifier:
    if settings.classifier == "keyword":
        return KeywordClassifier()
    raise ValueError(f"classificador desconhecido: {settings.classifier}")
