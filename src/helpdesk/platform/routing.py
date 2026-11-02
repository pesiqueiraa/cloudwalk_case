"""Roteamento: escolhe a fila da conversa pelas regras do banco, lidas a cada atendimento (sem cache)."""
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import psycopg


class NoQueueForBrand(Exception):
    pass


@dataclass(frozen=True)
class Route:
    queue_id: UUID
    queue_name: str
    first_responder: Literal["agent", "human"]
    matched_by: Literal["rule", "default"]
    rule: dict | None   # retrato da regra no momento do roteamento, para a auditoria


def route(conn: psycopg.Connection, *, brand: str, channel: str, category: str, priority: str) -> Route:
    """Primeira regra ativa por position cuja fila está ativa e é da marca; senão, a fila padrão da marca."""
    row = conn.execute(
        """
        SELECT r.id, r.name, r.position, r.brand_id, r.channel, r.category, r.priority,
               q.id AS queue_id, q.name AS queue_name, q.first_responder
        FROM routing_rules r JOIN queues q ON q.id = r.queue_id
        WHERE r.active AND q.active AND q.brand_id = %(brand)s
          AND (r.brand_id IS NULL OR r.brand_id = %(brand)s)
          AND (r.channel IS NULL OR r.channel = %(channel)s)
          AND (r.category IS NULL OR r.category = %(category)s)
          AND (r.priority IS NULL OR r.priority = %(priority)s)
        ORDER BY r.position, r.created_at, r.id
        LIMIT 1
        """,
        {"brand": brand, "channel": channel, "category": category, "priority": priority},
    ).fetchone()
    if row is not None:
        rule = {key: row[key] for key in ("name", "position", "brand_id", "channel", "category", "priority")}
        rule["id"] = str(row["id"])
        return Route(row["queue_id"], row["queue_name"], row["first_responder"], "rule", rule)

    default = conn.execute(
        "SELECT id, name, first_responder FROM queues WHERE brand_id = %s AND is_default AND active", (brand,)
    ).fetchone()
    if default is None:
        raise NoQueueForBrand(brand)
    return Route(default["id"], default["name"], default["first_responder"], "default", None)


def list_queue_conversations(conn: psycopg.Connection, queue_id: UUID) -> list[dict]:
    """Ordem de atendimento: prioridade alta primeiro e, dentro dela, a conversa mais antiga."""
    return conn.execute(
        """
        SELECT * FROM conversations WHERE queue_id = %s
        ORDER BY (priority = 'high') DESC, created_at, id
        """,
        (queue_id,),
    ).fetchall()
