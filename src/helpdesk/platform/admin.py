"""API de administração: filas e regras de roteamento, com efeito no atendimento seguinte.

Filas e regras não são apagadas, só desativadas: a auditoria antiga continua apontando para elas.
"""
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from helpdesk.contracts import Brand, Category, Channel, Priority
from helpdesk.platform.deps import get_conn

FirstResponder = Literal["agent", "human"]
Name = Annotated[str, Field(min_length=1, max_length=120)]

QUEUE_FIELDS = ("name", "team_id", "first_responder", "is_default", "active", "escalation_queue_id")
RULE_FIELDS = ("name", "position", "brand_id", "channel", "category", "priority", "queue_id", "active")


class QueueIn(BaseModel):
    name: Name
    brand_id: Brand
    team_id: str
    first_responder: FirstResponder
    is_default: bool = False
    escalation_queue_id: UUID | None = None   # para onde vão as escalações; nulo = a própria fila


class QueuePatch(BaseModel):
    name: Name | None = None
    team_id: str | None = None
    first_responder: FirstResponder | None = None
    is_default: bool | None = None
    active: bool | None = None
    escalation_queue_id: UUID | None = None   # null limpa


class RuleIn(BaseModel):
    name: Name
    position: int
    # Condições: nulo casa qualquer valor
    brand_id: Brand | None = None
    channel: Channel | None = None
    category: Category | None = None
    priority: Priority | None = None
    queue_id: UUID
    active: bool = True


class RulePatch(BaseModel):
    name: Name | None = None
    position: int | None = None
    brand_id: Brand | None = None
    channel: Channel | None = None
    category: Category | None = None
    priority: Priority | None = None
    queue_id: UUID | None = None
    active: bool | None = None


router = APIRouter(prefix="/api/admin", tags=["administração"])


def unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


@router.get("/teams")
def list_teams(conn: psycopg.Connection = Depends(get_conn)) -> list[dict]:
    return conn.execute("SELECT * FROM teams ORDER BY name").fetchall()


@router.get("/analysts")
def list_analysts(team_id: str | None = None, conn: psycopg.Connection = Depends(get_conn)) -> list[dict]:
    return conn.execute(
        "SELECT * FROM analysts WHERE %(team)s::text IS NULL OR team_id = %(team)s ORDER BY name",
        {"team": team_id},
    ).fetchall()


# Filas

@router.get("/queues")
def list_queues(brand: Brand | None = None, active: bool | None = None,
                conn: psycopg.Connection = Depends(get_conn)) -> list[dict]:
    return conn.execute(
        """
        SELECT * FROM queues
        WHERE (%(brand)s::text IS NULL OR brand_id = %(brand)s)
          AND (%(active)s::boolean IS NULL OR active = %(active)s)
        ORDER BY brand_id, name
        """,
        {"brand": brand, "active": active},
    ).fetchall()


@router.post("/queues", status_code=201)
def create_queue(body: QueueIn, conn: psycopg.Connection = Depends(get_conn)) -> dict:
    with conn.transaction():
        _check_team(conn, body.team_id)
        if body.escalation_queue_id is not None:
            _check_escalation_target(conn, body.brand_id, body.escalation_queue_id)
        if body.is_default:
            _clear_default(conn, body.brand_id)
        try:
            return conn.execute(
                """
                INSERT INTO queues (name, brand_id, team_id, first_responder, is_default, escalation_queue_id)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING *
                """,
                (body.name, body.brand_id, body.team_id, body.first_responder, body.is_default,
                 body.escalation_queue_id),
            ).fetchone()
        except psycopg.errors.UniqueViolation:
            raise HTTPException(status_code=409, detail="já existe uma fila com esse nome")


@router.patch("/queues/{queue_id}")
def update_queue(queue_id: UUID, body: QueuePatch, conn: psycopg.Connection = Depends(get_conn)) -> dict:
    changes = body.model_dump(exclude_unset=True)
    with conn.transaction():
        current = conn.execute("SELECT * FROM queues WHERE id = %s FOR UPDATE", (queue_id,)).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="fila não encontrada")
        # Nulo em escalation_queue_id limpa o destino; nos outros campos, nulo é ignorado
        new = {**current, **{k: v for k, v in changes.items() if v is not None or k == "escalation_queue_id"}}

        if "team_id" in changes:
            _check_team(conn, new["team_id"])
        if new["escalation_queue_id"] is not None and "escalation_queue_id" in changes:
            _check_escalation_target(conn, current["brand_id"], new["escalation_queue_id"], queue_id)
        if current["is_default"] and current["active"] and not (new["is_default"] and new["active"]):
            raise unprocessable("esta é a fila padrão da marca: marque outra fila como padrão antes")
        if new["is_default"] and not new["active"]:
            raise unprocessable("a fila padrão precisa estar ativa")
        if new["is_default"] and not current["is_default"]:
            _clear_default(conn, current["brand_id"])

        try:
            return conn.execute(
                """
                UPDATE queues SET name = %s, team_id = %s, first_responder = %s, is_default = %s, active = %s,
                                  escalation_queue_id = %s, updated_at = now()
                WHERE id = %s RETURNING *
                """,
                (*(new[f] for f in QUEUE_FIELDS), queue_id),
            ).fetchone()
        except psycopg.errors.UniqueViolation:
            raise HTTPException(status_code=409, detail="já existe uma fila com esse nome")


def _check_team(conn: psycopg.Connection, team_id: str) -> None:
    if conn.execute("SELECT 1 FROM teams WHERE id = %s", (team_id,)).fetchone() is None:
        raise unprocessable(f"equipe inexistente: {team_id}")


def _check_escalation_target(conn: psycopg.Connection, brand_id: str, target_id: UUID,
                             queue_id: UUID | None = None) -> None:
    if target_id == queue_id:
        raise unprocessable("a fila de escalas não pode ser a própria fila; deixe nulo para escalar nela")
    target = conn.execute("SELECT brand_id, active FROM queues WHERE id = %s", (target_id,)).fetchone()
    if target is None:
        raise unprocessable(f"fila de escalas inexistente: {target_id}")
    if not target["active"]:
        raise unprocessable("a fila de escalas está desativada")
    if target["brand_id"] != brand_id:
        raise unprocessable("a fila de escalas é de outra marca")


def _clear_default(conn: psycopg.Connection, brand_id: str) -> None:
    conn.execute(
        "UPDATE queues SET is_default = false, updated_at = now() WHERE brand_id = %s AND is_default",
        (brand_id,),
    )


# Regras

@router.get("/routing-rules")
def list_rules(brand: Brand | None = None, active: bool | None = None,
               conn: psycopg.Connection = Depends(get_conn)) -> list[dict]:
    # A marca da regra é a da fila de destino: só ela pode receber o atendimento
    return conn.execute(
        """
        SELECT r.* FROM routing_rules r JOIN queues q ON q.id = r.queue_id
        WHERE (%(brand)s::text IS NULL OR q.brand_id = %(brand)s)
          AND (%(active)s::boolean IS NULL OR r.active = %(active)s)
        ORDER BY r.position, r.created_at, r.id
        """,
        {"brand": brand, "active": active},
    ).fetchall()


@router.post("/routing-rules", status_code=201)
def create_rule(body: RuleIn, conn: psycopg.Connection = Depends(get_conn)) -> dict:
    with conn.transaction():
        _check_rule_target(conn, body.brand_id, body.queue_id)
        return conn.execute(
            """
            INSERT INTO routing_rules (name, position, brand_id, channel, category, priority, queue_id, active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *
            """,
            tuple(getattr(body, f) for f in RULE_FIELDS),
        ).fetchone()


@router.patch("/routing-rules/{rule_id}")
def update_rule(rule_id: UUID, body: RulePatch, conn: psycopg.Connection = Depends(get_conn)) -> dict:
    # exclude_unset: um campo enviado como null limpa a condição; um campo ausente fica como está
    changes = body.model_dump(exclude_unset=True)
    for required in ("name", "position", "queue_id", "active"):
        if required in changes and changes[required] is None:
            raise unprocessable(f"{required} não pode ser nulo")
    with conn.transaction():
        current = conn.execute("SELECT * FROM routing_rules WHERE id = %s FOR UPDATE", (rule_id,)).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="regra não encontrada")
        new = {**current, **changes}
        if {"brand_id", "queue_id"} & changes.keys():
            _check_rule_target(conn, new["brand_id"], new["queue_id"])
        return conn.execute(
            """
            UPDATE routing_rules SET name = %s, position = %s, brand_id = %s, channel = %s, category = %s,
                                     priority = %s, queue_id = %s, active = %s, updated_at = now()
            WHERE id = %s RETURNING *
            """,
            (*(new[f] for f in RULE_FIELDS), rule_id),
        ).fetchone()


def _check_rule_target(conn: psycopg.Connection, brand_id: str | None, queue_id: UUID) -> None:
    queue = conn.execute("SELECT brand_id, active FROM queues WHERE id = %s", (queue_id,)).fetchone()
    if queue is None:
        raise unprocessable(f"fila inexistente: {queue_id}")
    if not queue["active"]:
        raise unprocessable("a fila de destino está desativada")
    if brand_id is not None and brand_id != queue["brand_id"]:
        raise unprocessable("a marca da regra é diferente da marca da fila de destino")
