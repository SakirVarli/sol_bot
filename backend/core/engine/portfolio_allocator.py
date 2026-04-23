from __future__ import annotations

from core.models.strategy import StrategyAllocation, StrategyInstance, StrategyMode


class PortfolioAllocator:
    def __init__(self, paper_balance_sol: float, live_balance_sol: float) -> None:
        self._master = {
            StrategyMode.PAPER: {"initial": paper_balance_sol},
            StrategyMode.LIVE: {"initial": live_balance_sol},
        }
        self._allocations: dict[str, StrategyAllocation] = {}

    def upsert_strategy(self, instance: StrategyInstance) -> StrategyAllocation:
        allocation = self._allocations.get(instance.strategy_id)
        if allocation is None:
            allocation = StrategyAllocation(
                strategy_id=instance.strategy_id,
                mode=instance.mode,
                reserved_sol=instance.reserved_budget_sol,
            )
            self._allocations[instance.strategy_id] = allocation
        else:
            allocation.mode = instance.mode
            allocation.reserved_sol = instance.reserved_budget_sol
        return allocation

    def can_allocate(self, strategy_id: str, size_sol: float) -> bool:
        allocation = self._allocations[strategy_id]
        return allocation.free_sol() >= size_sol

    def reserve(self, strategy_id: str, size_sol: float) -> None:
        self._allocations[strategy_id].used_sol += size_sol

    def release(self, strategy_id: str, size_sol: float, realized_pnl_sol: float = 0.0) -> None:
        allocation = self._allocations[strategy_id]
        allocation.used_sol = max(0.0, allocation.used_sol - size_sol)
        allocation.realized_pnl_sol += realized_pnl_sol

    def snapshot(self) -> dict:
        ledgers = []
        for mode, meta in self._master.items():
            allocations = [a for a in self._allocations.values() if a.mode == mode]
            realized = sum(a.realized_pnl_sol for a in allocations)
            used = sum(a.used_sol for a in allocations)
            reserved = sum(a.reserved_sol for a in allocations)
            ledgers.append(
                {
                    "mode": mode.value,
                    "initial_balance_sol": meta["initial"],
                    "balance_sol": round(meta["initial"] + realized, 6),
                    "reserved_sol": round(reserved, 6),
                    "used_sol": round(used, 6),
                    "free_sol": round(max(0.0, meta["initial"] + realized - used), 6),
                }
            )
        strategy_allocations = {
            strategy_id: {
                "mode": allocation.mode.value,
                "reserved_sol": round(allocation.reserved_sol, 6),
                "used_sol": round(allocation.used_sol, 6),
                "free_sol": round(allocation.free_sol(), 6),
                "realized_pnl_sol": round(allocation.realized_pnl_sol, 6),
            }
            for strategy_id, allocation in self._allocations.items()
        }
        return {"ledgers": ledgers, "strategies": strategy_allocations}
