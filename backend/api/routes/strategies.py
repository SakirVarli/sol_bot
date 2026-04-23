from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.runtime import runtime_state
from core.engine.rule_engine import rule_group_from_payload
from core.engine.strategy_store import StrategyStore
from core.models.strategy import StrategyDefinition, StrategyInstance, StrategyStatus
from core.storage.db import Database
from core.utils.ids import strategy_definition_id, strategy_instance_id

router = APIRouter()


class StrategyDefinitionPayload(BaseModel):
    definition_id: str | None = None
    name: str
    description: str = ""
    version: int = 1
    candle_seconds: int = 60
    entry: dict[str, Any]
    exits: dict[str, Any]
    sizing: dict[str, Any] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)
    reentry: dict[str, Any] = Field(default_factory=dict)


class StrategyInstancePayload(BaseModel):
    strategy_id: str | None = None
    definition_id: str
    name: str
    mode: str = "paper"
    status: str = "stopped"
    reserved_budget_sol: float = 0.0
    allocation_pct: float | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)


def _supervisor():
    if runtime_state.supervisor is None:
        raise HTTPException(status_code=400, detail="Workspace must be running for strategy operations.")
    return runtime_state.supervisor


@asynccontextmanager
async def _strategy_store_context():
    supervisor = runtime_state.supervisor
    if supervisor and supervisor._store:
        yield supervisor._store
        return

    data_dir = Path(runtime_state.config.get("bot", {}).get("data_dir", "data"))
    db = Database(data_dir / "trades" / "workspace.db")
    await db.connect()
    try:
        yield StrategyStore(db)
    finally:
        await db.close()


@router.get("")
async def list_strategies():
    async with _strategy_store_context() as store:
        definitions = await store.list_definitions()
        instances = await store.list_instances()

    if runtime_state.supervisor:
        supervisor = runtime_state.supervisor
        validation = {definition.definition_id: supervisor.validate_definition(definition) for definition in definitions}
    else:
        compiler_validation = {}
        temp_supervisor = None
        try:
            from core.engine.supervisor import EngineSupervisor
            temp_supervisor = EngineSupervisor(runtime_state.config)
            compiler_validation = {
                definition.definition_id: temp_supervisor.validate_definition(definition)
                for definition in definitions
            }
        finally:
            temp_supervisor = None
        validation = compiler_validation

    return {
        "definitions": [definition.model_dump() for definition in definitions],
        "instances": [instance.model_dump() for instance in instances],
        "validation": validation,
    }


@router.post("/definitions")
async def save_definition(payload: StrategyDefinitionPayload):
    definition = StrategyDefinition(
        definition_id=payload.definition_id or strategy_definition_id(),
        name=payload.name,
        description=payload.description,
        version=payload.version,
        candle_seconds=payload.candle_seconds,
        entry=rule_group_from_payload(payload.entry),
        exits=rule_group_from_payload(payload.exits),
        sizing=payload.sizing,
        risk=payload.risk,
        reentry=payload.reentry,
    )
    if runtime_state.supervisor:
        definition = await runtime_state.supervisor.save_definition(definition)
        validation = runtime_state.supervisor.validate_definition(definition)
    else:
        async with _strategy_store_context() as store:
            definition = await store.upsert_definition(definition)
        from core.engine.supervisor import EngineSupervisor
        validation = EngineSupervisor(runtime_state.config).validate_definition(definition)
    return {
        "definition": definition.model_dump(),
        "validation": validation,
    }


@router.post("/instances")
async def save_instance(payload: StrategyInstancePayload):
    instance = StrategyInstance(
        strategy_id=payload.strategy_id or strategy_instance_id(),
        definition_id=payload.definition_id,
        name=payload.name,
        mode=payload.mode,
        status=payload.status,
        reserved_budget_sol=payload.reserved_budget_sol,
        allocation_pct=payload.allocation_pct,
        overrides=payload.overrides,
    )
    if runtime_state.supervisor:
        instance = await runtime_state.supervisor.save_instance(instance)
    else:
        async with _strategy_store_context() as store:
            instance = await store.upsert_instance(instance)
    return instance.model_dump()


@router.delete("/instances/{strategy_id}")
async def delete_instance(strategy_id: str):
    if runtime_state.supervisor:
        try:
            deleted = await runtime_state.supervisor.delete_instance(strategy_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    else:
        async with _strategy_store_context() as store:
            instance = await store.get_instance(strategy_id)
            if instance is None:
                deleted = False
            else:
                deleted = await store.delete_instance(strategy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Strategy instance not found")
    return {"ok": True}


@router.delete("/definitions/{definition_id}")
async def delete_definition(definition_id: str):
    if runtime_state.supervisor:
        try:
            deleted = await runtime_state.supervisor.delete_definition(definition_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    else:
        async with _strategy_store_context() as store:
            in_use = await store.count_instances_for_definition(definition_id)
            if in_use > 0:
                raise HTTPException(
                    status_code=409,
                    detail="Delete all strategy instances using this definition before deleting the definition.",
                )
            deleted = await store.delete_definition(definition_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Strategy definition not found")
    return {"ok": True}


@router.post("/{strategy_id}/start")
async def start_strategy(strategy_id: str):
    supervisor = _supervisor()
    instance = await supervisor.set_strategy_status(strategy_id, StrategyStatus.ENABLED)
    if instance is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return instance.model_dump()


@router.post("/{strategy_id}/stop")
async def stop_strategy(strategy_id: str):
    supervisor = _supervisor()
    instance = await supervisor.set_strategy_status(strategy_id, StrategyStatus.STOPPED)
    if instance is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return instance.model_dump()


@router.post("/validate")
async def validate_definition(payload: StrategyDefinitionPayload):
    supervisor = _supervisor()
    definition = StrategyDefinition(
        definition_id=payload.definition_id or "preview",
        name=payload.name,
        description=payload.description,
        version=payload.version,
        candle_seconds=payload.candle_seconds,
        entry=rule_group_from_payload(payload.entry),
        exits=rule_group_from_payload(payload.exits),
        sizing=payload.sizing,
        risk=payload.risk,
        reentry=payload.reentry,
    )
    return supervisor.validate_definition(definition)


@router.post("/preview")
async def preview_definition(payload: StrategyDefinitionPayload):
    supervisor = _supervisor()
    definition = StrategyDefinition(
        definition_id=payload.definition_id or "preview",
        name=payload.name,
        description=payload.description,
        version=payload.version,
        candle_seconds=payload.candle_seconds,
        entry=rule_group_from_payload(payload.entry),
        exits=rule_group_from_payload(payload.exits),
        sizing=payload.sizing,
        risk=payload.risk,
        reentry=payload.reentry,
    )
    return {
        "validation": supervisor.validate_definition(definition),
        "preview": await supervisor.preview_definition(definition),
    }
