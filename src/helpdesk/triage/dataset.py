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
