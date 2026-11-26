"""Tabela de verdade da triagem: o Jev dá os julgamentos, o código decide.

Limiares de partida da documentação do TypeSafe (Noul: acima de 0,7 é sim, abaixo de 0,3 é não),
conferidos na sonda de 25/11. A faixa do meio é "indeciso" e tem a sua própria linha em cada decisão.
"""
import math
from typing import Literal

from helpdesk.contracts import Category, Priority

NOUL_YES = 0.7
NOUL_NO = 0.3
HAS_TOPIC_MIN = 0.5   # abaixo disso, a mensagem não é sobre nenhum produto: "other"

Band = Literal["yes", "no", "undecided"]


def band(p: float) -> Band:
    if p > NOUL_YES:
        return "yes"
    if p < NOUL_NO:
        return "no"
    return "undecided"


def category_from(topic: str, has_topic: float) -> Category:
    return topic if has_topic >= HAS_TOPIC_MIN else "other"  # type: ignore[return-value]


def priority_from(category: Category, urgent: float) -> Priority:
    # Fraude é sempre alta. Urgência indecisa fica normal: a prioridade só sobe com um "sim" claro
    return "high" if category == "fraud" or band(urgent) == "yes" else "normal"


def asks_for_human(wants_human: float | None) -> bool:
    # Indeciso não escala: falso positivo gasta tempo de analista; o agente ainda pode escalar depois
    return wants_human is not None and band(wants_human) == "yes"


def frustration_level(frustration: float) -> int:
    """Nível de 0 a 3 mais próximo do Score: 1,6 conta como 2.

    floor(x + 0,5) e não round(): o round do Python arredonda 2,5 para 2."""
    return min(3, max(0, math.floor(frustration + 0.5)))


def frustration_reached(frustration: float | None, threshold: int | None) -> bool:
    """Limiar por fila (0 a 3; nulo = desligado)."""
    return frustration is not None and threshold is not None and frustration_level(frustration) >= threshold
