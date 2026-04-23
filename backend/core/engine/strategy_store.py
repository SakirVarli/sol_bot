from __future__ import annotations

import json
import time

from core.engine.rule_engine import rule_group_from_payload
from core.models.strategy import StrategyDefinition, StrategyInstance, StrategyStatus
from core.utils.ids import strategy_definition_id, strategy_instance_id


class StrategyStore:
    def __init__(self, db) -> None:
        self._db = db

    async def list_definitions(self) -> list[StrategyDefinition]:
        rows = await self._db.fetchall("SELECT * FROM strategy_definitions ORDER BY updated_ts DESC")
        return [self._definition_from_row(row["data"]) for row in rows]

    async def list_instances(self) -> list[StrategyInstance]:
        rows = await self._db.fetchall("SELECT * FROM strategy_instances ORDER BY created_ts ASC")
        return [StrategyInstance.model_validate(json.loads(row["data"])) for row in rows]

    async def get_definition(self, definition_id: str) -> StrategyDefinition | None:
        row = await self._db.fetchone(
            "SELECT data FROM strategy_definitions WHERE definition_id = ?",
            (definition_id,),
        )
        return self._definition_from_row(row["data"]) if row else None

    async def get_instance(self, strategy_id: str) -> StrategyInstance | None:
        row = await self._db.fetchone(
            "SELECT data FROM strategy_instances WHERE strategy_id = ?",
            (strategy_id,),
        )
        return StrategyInstance.model_validate(json.loads(row["data"])) if row else None

    async def count_instances_for_definition(self, definition_id: str) -> int:
        row = await self._db.fetchone(
            "SELECT COUNT(*) AS count FROM strategy_instances WHERE definition_id = ?",
            (definition_id,),
        )
        return int(row["count"]) if row else 0

    async def delete_instance(self, strategy_id: str) -> bool:
        existing = await self.get_instance(strategy_id)
        if existing is None:
            return False
        await self._db.execute("DELETE FROM strategy_instances WHERE strategy_id = ?", (strategy_id,))
        return True

    async def delete_definition(self, definition_id: str) -> bool:
        existing = await self.get_definition(definition_id)
        if existing is None:
            return False
        await self._db.execute("DELETE FROM strategy_definitions WHERE definition_id = ?", (definition_id,))
        return True

    async def upsert_definition(self, definition: StrategyDefinition) -> StrategyDefinition:
        definition.updated_ts = time.time()
        await self._db.execute(
            """
            INSERT OR REPLACE INTO strategy_definitions
                (definition_id, name, version, updated_ts, data)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                definition.definition_id,
                definition.name,
                definition.version,
                definition.updated_ts,
                definition.model_dump_json(),
            ),
        )
        return definition

    async def upsert_instance(self, instance: StrategyInstance) -> StrategyInstance:
        instance.updated_ts = time.time()
        await self._db.execute(
            """
            INSERT OR REPLACE INTO strategy_instances
                (strategy_id, definition_id, name, mode, status, reserved_budget_sol, updated_ts, created_ts, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                instance.strategy_id,
                instance.definition_id,
                instance.name,
                instance.mode.value,
                instance.status.value,
                instance.reserved_budget_sol,
                instance.updated_ts,
                instance.created_ts,
                instance.model_dump_json(),
            ),
        )
        return instance

    async def ensure_seed_data(self, config: dict) -> tuple[list[StrategyDefinition], list[StrategyInstance]]:
        definitions = await self.list_definitions()
        instances = await self.list_instances()
        if definitions and instances:
            return definitions, instances

        candle_seconds = int(config.get("strategy", {}).get("first_pullback", {}).get("watch_window_seconds", 60))
        trade_size_sol = float(config.get("paper", {}).get("trade_size_sol", 0.1))
        reserved_budget_sol = float(config.get("paper", {}).get("initial_balance_sol", 10.0))

        definition = StrategyDefinition(
            definition_id=strategy_definition_id(),
            name="First Green After 5 Red",
            description="Seed strategy generated from legacy config.",
            version=1,
            candle_seconds=max(5, candle_seconds),
            entry=rule_group_from_payload(
                {
                    "logic": "AND",
                    "blocks": [
                        {"type": "first_candle_after_sequence", "params": {"count": 5, "after_color": "red", "then_color": "green"}},
                    ],
                }
            ),
            exits=rule_group_from_payload(
                {
                    "logic": "OR",
                    "blocks": [
                        {"type": "profit_pct_gte", "params": {"value": 5}},
                        {"type": "loss_pct_lte", "params": {"value": 3}},
                        {"type": "consecutive_candles", "params": {"count": 5, "color": "red"}},
                    ],
                }
            ),
            sizing={"kind": "fixed_sol", "value": trade_size_sol, "max_size_sol": trade_size_sol},
            risk={"max_concurrent_positions": config.get("risk", {}).get("max_concurrent_positions", 1)},
            reentry={"allow_repeat_entries": True, "cooldown_seconds": 0},
        )
        await self.upsert_definition(definition)

        instance = StrategyInstance(
            strategy_id=strategy_instance_id(),
            definition_id=definition.definition_id,
            name="Seed Paper Strategy",
            mode="paper",
            status=StrategyStatus.STOPPED,
            reserved_budget_sol=reserved_budget_sol,
        )
        await self.upsert_instance(instance)
        return [definition], [instance]

    def _definition_from_row(self, raw_json: str) -> StrategyDefinition:
        payload = json.loads(raw_json)
        payload["entry"] = rule_group_from_payload(payload.get("entry", {"logic": "AND", "blocks": []}))
        payload["exits"] = rule_group_from_payload(payload.get("exits", {"logic": "OR", "blocks": []}))
        return StrategyDefinition.model_validate(payload)
