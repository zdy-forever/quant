# -*- coding: utf-8 -*-
"""
策略层资金分配模块。

这个文件解决的问题不是“股票权重”，而是“策略权重”。
例如市场最近 70% 更像趋势市、30% 更像震荡市时，
可以把更多资金给趋势策略，少量资金给均值回归策略。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable


@dataclass(frozen=True)
class StrategyBlendConfig:
    lookback_days: int = 60
    max_total_exposure: float = 1.0
    min_strategy_weight: float = 0.05
    high_vol_haircut: float = 0.35
    trend_strategies: tuple[str, ...] = ()
    range_strategies: tuple[str, ...] = ("mean_reversion",)
    defensive_strategies: tuple[str, ...] = ("multi_factor_short",)


def _distribute_equally(total_weight: float, strategies: Iterable[str]) -> Dict[str, float]:
    strategies = list(strategies)
    if total_weight <= 0 or not strategies:
        return {}
    per = total_weight / len(strategies)
    return {name: per for name in strategies}


def compute_strategy_allocations(
    regime_mix: Dict[str, float],
    available_strategies: Iterable[str],
    cfg: StrategyBlendConfig,
) -> Dict[str, float]:
    """
    根据市场状态混合比例，给各策略分配资金。
    """

    available = set(available_strategies)
    trend_bucket = [name for name in cfg.trend_strategies if name in available]
    range_bucket = [name for name in cfg.range_strategies if name in available]
    defensive_bucket = [name for name in cfg.defensive_strategies if name in available]

    trend_weight = float(regime_mix.get("trend_total", 0.0))
    range_weight = float(regime_mix.get("range_total", 0.0))
    high_vol_weight = float(regime_mix.get("high_vol_total", 0.0))

    exposure = cfg.max_total_exposure * max(0.25, 1.0 - cfg.high_vol_haircut * high_vol_weight)

    allocations: Dict[str, float] = {}
    for name, weight in _distribute_equally(trend_weight * exposure, trend_bucket).items():
        allocations[name] = allocations.get(name, 0.0) + weight
    for name, weight in _distribute_equally(range_weight * exposure, range_bucket).items():
        allocations[name] = allocations.get(name, 0.0) + weight
    for name, weight in _distribute_equally(high_vol_weight * 0.25 * exposure, defensive_bucket).items():
        allocations[name] = allocations.get(name, 0.0) + weight

    allocations = {name: weight for name, weight in allocations.items() if weight > 0}
    if not allocations:
        return {}

    total = sum(allocations.values())
    allocations = {name: weight / total * exposure for name, weight in allocations.items()}
    allocations = {
        name: weight
        for name, weight in allocations.items()
        if weight >= cfg.min_strategy_weight or len(allocations) == 1
    }
    if not allocations:
        return {}

    total = sum(allocations.values())
    return {name: weight / total * exposure for name, weight in allocations.items()}
