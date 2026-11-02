"""Casamento de termos por palavra inteira: "agent" casa em "an agent", não em "agency"."""
import re
from collections.abc import Iterable


def compile_terms(terms: Iterable[str]) -> re.Pattern:
    # Termos mais longos primeiro, para "pessoa de verdade" ganhar de um termo contido nele
    alternatives = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"\b(?:{alternatives})\b", re.IGNORECASE)


def find_terms(pattern: re.Pattern, text: str) -> list[str]:
    return [m.group(0).lower() for m in pattern.finditer(text)]
