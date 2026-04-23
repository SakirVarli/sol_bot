from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.models.candle import Candle
from core.models.position import Position
from core.models.strategy import LogicType, RuleBlock, RuleGroup, StrategyDefinition


@dataclass
class StrategyMemory:
    last_exit_ts_by_mint: dict[str, float] = field(default_factory=dict)
    entries_by_mint: dict[str, int] = field(default_factory=dict)


@dataclass
class RuleEvaluationResult:
    matched: bool
    reason: str = ""


class RuleCompiler:
    def compile(self, definition: StrategyDefinition) -> StrategyDefinition:
        return definition

    def summarize(self, group: RuleGroup) -> str:
        parts: list[str] = []
        for block in group.blocks:
            normalized = _normalize_rule_node(block)
            if isinstance(normalized, RuleGroup):
                parts.append(f"({self.summarize(normalized)})")
                continue
            parts.append(self._block_summary(normalized))
        joiner = f" {group.logic.value} "
        return joiner.join(parts) if parts else "No rules"

    def validate(self, definition: StrategyDefinition) -> list[str]:
        errors: list[str] = []
        if definition.candle_seconds <= 0:
            errors.append("Candle timeframe must be greater than zero.")
        if not definition.entry.blocks:
            errors.append("Entry rules must contain at least one block.")
        if not definition.exits.blocks:
            errors.append("Exit rules must contain at least one block.")
        return errors

    def _block_summary(self, block: RuleBlock) -> str:
        p = block.params
        mapping = {
            "candle_color": f"{p.get('target', 'current')} candle is {p.get('color', 'green')}",
            "consecutive_candles": f"{p.get('count', 1)} consecutive {p.get('color', 'red')} candles",
            "first_candle_color": f"first {p.get('color', 'red')} candle",
            "first_candle_after_sequence": f"first {p.get('then_color', 'green')} candle after {p.get('count', 1)} {p.get('after_color', 'red')} candles",
            "profit_pct_gte": f"profit >= {p.get('value', 0)}%",
            "loss_pct_lte": f"loss <= {p.get('value', 0)}%",
            "close_below_previous_low": "current close below previous low",
            "close_above_previous_high": "current close above previous high",
            "time_in_trade_gte_seconds": f"time in trade >= {p.get('value', 0)}s",
        }
        return mapping.get(block.type, block.type.replace("_", " "))


class RuleEvaluator:
    def evaluate_group(
        self,
        group: RuleGroup,
        candles: list[Candle],
        position: Position | None,
        memory: StrategyMemory,
        mint: str,
    ) -> RuleEvaluationResult:
        if not group.blocks:
            return RuleEvaluationResult(False, "")

        results: list[RuleEvaluationResult] = []
        for block in group.blocks:
            normalized = _normalize_rule_node(block)
            if isinstance(normalized, RuleGroup):
                results.append(self.evaluate_group(normalized, candles, position, memory, mint))
            else:
                results.append(self.evaluate_block(normalized, candles, position, memory, mint))

        if group.logic == LogicType.AND:
            matched = all(result.matched for result in results)
            if matched:
                return RuleEvaluationResult(True, " and ".join(r.reason for r in results if r.reason))
            return RuleEvaluationResult(False, "")

        for result in results:
            if result.matched:
                return result
        return RuleEvaluationResult(False, "")

    def evaluate_block(
        self,
        block: RuleBlock,
        candles: list[Candle],
        position: Position | None,
        memory: StrategyMemory,
        mint: str,
    ) -> RuleEvaluationResult:
        params = block.params
        if not candles:
            return RuleEvaluationResult(False, "")

        current = candles[-1]
        previous = candles[-2] if len(candles) > 1 else None

        if block.type == "first_candle_color":
            color = params.get("color", "red")
            return RuleEvaluationResult(
                len(candles) == 1 and current.color == color,
                f"first {color} candle",
            )

        if block.type == "candle_color":
            color = params.get("color", "green")
            target = params.get("target", "current")
            candle = previous if target == "previous" and previous else current
            return RuleEvaluationResult(candle.color == color, f"{target} candle is {color}")

        if block.type == "consecutive_candles":
            count = int(params.get("count", 1))
            color = params.get("color", "red")
            if len(candles) < count:
                return RuleEvaluationResult(False, "")
            matched = all(candle.color == color for candle in candles[-count:])
            return RuleEvaluationResult(matched, f"{count} consecutive {color} candles")

        if block.type == "first_candle_after_sequence":
            count = int(params.get("count", 1))
            after_color = params.get("after_color", "red")
            then_color = params.get("then_color", "green")
            if len(candles) < count + 1:
                return RuleEvaluationResult(False, "")
            prior = candles[-(count + 1):-1]
            matched = current.color == then_color and all(candle.color == after_color for candle in prior)
            return RuleEvaluationResult(
                matched,
                f"first {then_color} after {count} {after_color} candles",
            )

        if block.type == "profit_pct_gte" and position is not None:
            threshold = float(params.get("value", 0))
            return RuleEvaluationResult(position.pnl_pct() >= threshold, f"profit >= {threshold}%")

        if block.type == "loss_pct_lte" and position is not None:
            threshold = -abs(float(params.get("value", 0)))
            return RuleEvaluationResult(position.pnl_pct() <= threshold, f"loss <= {abs(threshold)}%")

        if block.type == "close_below_previous_low" and previous is not None:
            return RuleEvaluationResult(current.close < previous.low, "close below previous low")

        if block.type == "close_above_previous_high" and previous is not None:
            return RuleEvaluationResult(current.close > previous.high, "close above previous high")

        if block.type == "time_in_trade_gte_seconds" and position is not None:
            threshold = float(params.get("value", 0))
            return RuleEvaluationResult(position.hold_seconds() >= threshold, f"time in trade >= {threshold}s")

        if block.type == "max_entries_per_token":
            limit = int(params.get("value", 1))
            return RuleEvaluationResult(memory.entries_by_mint.get(mint, 0) < limit, f"entries < {limit}")

        return RuleEvaluationResult(False, "")


def rule_group_from_payload(payload: dict[str, Any]) -> RuleGroup:
    blocks = []
    for block in payload.get("blocks", []):
        if "logic" in block:
            blocks.append(rule_group_from_payload(block))
        else:
            blocks.append(RuleBlock(type=block["type"], params=block.get("params", {})))
    return RuleGroup(logic=payload.get("logic", "AND"), blocks=blocks)


def _normalize_rule_node(node: Any) -> RuleBlock | RuleGroup:
    if isinstance(node, (RuleBlock, RuleGroup)):
        return node
    if isinstance(node, dict) and "logic" in node:
        return rule_group_from_payload(node)
    if isinstance(node, dict):
        return RuleBlock(type=node["type"], params=node.get("params", {}))
    raise TypeError(f"Unsupported rule node: {type(node)!r}")
