from __future__ import annotations

import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class StrategyMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class StrategyStatus(str, Enum):
    ENABLED = "enabled"
    PAUSED = "paused"
    STOPPED = "stopped"


class LogicType(str, Enum):
    AND = "AND"
    OR = "OR"


class RuleBlock(BaseModel):
    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class RuleGroup(BaseModel):
    logic: LogicType = LogicType.AND
    blocks: list[Any] = Field(default_factory=list)


class StrategyDefinition(BaseModel):
    definition_id: str
    name: str
    description: str = ""
    version: int = 1
    candle_seconds: int = 60
    entry: RuleGroup = Field(default_factory=RuleGroup)
    exits: RuleGroup = Field(default_factory=lambda: RuleGroup(logic=LogicType.OR))
    sizing: dict[str, Any] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)
    reentry: dict[str, Any] = Field(default_factory=dict)
    created_ts: float = Field(default_factory=time.time)
    updated_ts: float = Field(default_factory=time.time)


class StrategyInstance(BaseModel):
    strategy_id: str
    definition_id: str
    name: str
    mode: StrategyMode = StrategyMode.PAPER
    status: StrategyStatus = StrategyStatus.STOPPED
    reserved_budget_sol: float = 0.0
    allocation_pct: Optional[float] = None
    overrides: dict[str, Any] = Field(default_factory=dict)
    last_started_ts: Optional[float] = None
    last_stopped_ts: Optional[float] = None
    created_ts: float = Field(default_factory=time.time)
    updated_ts: float = Field(default_factory=time.time)


class StrategyAllocation(BaseModel):
    strategy_id: str
    mode: StrategyMode
    reserved_sol: float
    used_sol: float = 0.0
    realized_pnl_sol: float = 0.0

    def equity_sol(self) -> float:
        return self.reserved_sol + self.realized_pnl_sol

    def free_sol(self) -> float:
        return max(0.0, self.equity_sol() - self.used_sol)


class StrategyStats(BaseModel):
    strategy_id: str
    strategy_name: str
    mode: StrategyMode
    trades: int = 0
    winners: int = 0
    losers: int = 0
    win_rate: float = 0.0
    realized_pnl_sol: float = 0.0
    unrealized_pnl_sol: float = 0.0
    open_positions: int = 0
    used_budget_sol: float = 0.0
    reserved_budget_sol: float = 0.0
    free_budget_sol: float = 0.0
    last_signal: str | None = None
    last_signal_ts: float | None = None


RuleGroup.model_rebuild()
