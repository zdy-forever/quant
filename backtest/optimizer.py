# -*- coding: utf-8 -*-
"""
参数优化模块。

这个文件专门负责“找参数”，和训练阶段的 freeze 分开：
- 你可以单独运行优化，不立刻冻结
- 可以对不同策略复用同一套打分逻辑
- 可以加上稳健性约束，减少只靠少数交易碰运气的参数
"""
from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List

import numpy as np
import pandas as pd

from backtest.engine import BacktestConfig, run_signal_backtest
from strategy.mean_reversion.mean_reversion import MeanReversionBollingerStrategy
from strategy.multi_factor_short.multi_factor_short import MultiFactorShortStrategy


@dataclass(frozen=True)
class OptimizationSpec:
    start: str
    end: str
    objective: str = "sharpe"
    min_trade_count: int = 8
    min_avg_active_positions: float = 1.0
    max_avg_turnover: float = 1.5
    backtest: BacktestConfig = field(default_factory=BacktestConfig)


def get_strategy_registry() -> Dict[str, Any]:
    return {
        "mean_reversion": MeanReversionBollingerStrategy(),
        "multi_factor_short": MultiFactorShortStrategy(),
    }


def _grid_iter(grid: Dict[str, Iterable[Any]]) -> List[Dict[str, Any]]:
    keys = list(grid.keys())
    values = [list(grid[key]) for key in keys]
    return [{key: value for key, value in zip(keys, combo)} for combo in itertools.product(*values)]


def _slice_ohlcv(ohlcv: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    df = ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    return df[(df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)].copy()


def _score_candidate(metrics: Dict[str, float], spec: OptimizationSpec) -> float:
    if spec.objective == "cagr":
        base = metrics["cagr"]
    elif spec.objective == "calmar":
        base = metrics["calmar"]
    else:
        base = metrics["sharpe"]

    turnover_penalty = max(0.0, metrics["avg_turnover"] - spec.max_avg_turnover)
    drawdown_penalty = max(0.0, abs(metrics["max_dd"]) - 0.25)
    return float(base - 0.25 * turnover_penalty - 2.0 * drawdown_penalty)


def optimize_strategy(
    ohlcv: pd.DataFrame,
    strategy_name: str,
    spec: OptimizationSpec,
) -> Dict[str, Any]:
    registry = get_strategy_registry()
    if strategy_name not in registry:
        raise ValueError(f"未知策略: {strategy_name}")

    strategy = registry[strategy_name]
    sample = _slice_ohlcv(ohlcv, spec.start, spec.end)
    best_score = -1e18
    best_params: Dict[str, Any] | None = None
    best_result: Dict[str, Any] | None = None

    for partial in _grid_iter(strategy.param_grid()):
        params = strategy.default_params()
        params.update(partial)
        generated = strategy.generate(sample, params)
        bt_result = run_signal_backtest(sample, generated.signals, generated.score, spec.backtest)
        metrics = bt_result["metrics"]

        if metrics["trade_count"] < spec.min_trade_count:
            continue
        if metrics["avg_active_positions"] < spec.min_avg_active_positions:
            continue
        if metrics["avg_turnover"] > spec.max_avg_turnover * 3:
            continue

        score = _score_candidate(metrics, spec)
        if np.isnan(score):
            continue
        if score > best_score:
            best_score = score
            best_params = params
            best_result = bt_result

    if best_params is None or best_result is None:
        raise RuntimeError(f"优化失败：{strategy_name} 没有找到满足约束的参数组合")

    return {
        "strategy": strategy_name,
        "spec": asdict(spec),
        "best_params": best_params,
        "best_metrics": best_result["metrics"],
        "score": best_score,
    }


def optimize_strategies(
    ohlcv: pd.DataFrame,
    strategies: List[str],
    spec: OptimizationSpec,
) -> Dict[str, Any]:
    return {
        "spec": asdict(spec),
        "results": {strategy_name: optimize_strategy(ohlcv, strategy_name, spec) for strategy_name in strategies},
    }
