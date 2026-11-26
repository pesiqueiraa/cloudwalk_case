"""Banco de mensagens sintéticas rotuladas: mede o classificador e alimenta o simulador."""
import json
from dataclasses import dataclass
from importlib.resources import files

from helpdesk.contracts import Brand, Category, Priority


@dataclass(frozen=True)
class LabeledMessage:
    brand: Brand
    text: str
    category: Category
    priority: Priority


def load_labeled_messages() -> list[LabeledMessage]:
    lines = files("helpdesk.triage").joinpath("labeled_messages.jsonl").read_text().splitlines()
    return [LabeledMessage(**json.loads(line)) for line in lines if line.strip()]


@dataclass(frozen=True)
class SentimentMessage:
    """Frase rotulada também com frustração (0 a 3) e pedido de humano: avalia o Jev além da categoria."""
    brand: Brand
    text: str
    category: Category
    frustration: int
    wants_human: bool


# hard: paráfrases sem as palavras-chave das regras, escritas junto com as perguntas do Jev (25/11)
# blind: escritas às cegas, por quem não viu as perguntas do Jev (25/11)
SENTIMENT_SETS = ("hard", "blind")


def load_sentiment_messages(name: str) -> list[SentimentMessage]:
    if name not in SENTIMENT_SETS:
        raise ValueError(f"conjunto desconhecido: {name}")
    path = files("helpdesk.triage").joinpath(f"{name}_messages.jsonl")
    if not path.is_file():
        return []
    return [SentimentMessage(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]
