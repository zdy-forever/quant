# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import pandas as pd


@dataclass(frozen=True)
class RiskConfig:
    max_weight_per_asset: float = 0.25
    max_gross_exposure: float = 1.0
    max_drawdown: float = 0.25
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    slippage_bps: float = 5.0
    commission_bps: float = 0.0


def clamp_weights(weights: Dict[str, float], cfg: RiskConfig) -> Dict[str, float]:
    """对权重做单标的和总敞口限制。"""

    if not weights:
        return {}

    clamped = {
        symbol: min(max(0.0, float(weight)), cfg.max_weight_per_asset)
        for symbol, weight in weights.items()
    }
    gross = sum(clamped.values())
    if gross > cfg.max_gross_exposure and gross > 1e-12:
        scale = cfg.max_gross_exposure / gross
        clamped = {symbol: weight * scale for symbol, weight in clamped.items()}
    return clamped


def apply_drawdown_kill_switch(equity_curve: pd.Series, cfg: RiskConfig) -> bool:
    """超过最大回撤阈值时返回 True。"""

    if equity_curve.empty:
        return False
    peak = equity_curve.cummax()
    max_drawdown = (equity_curve / peak - 1.0).min()
    return float(max_drawdown) <= -float(cfg.max_drawdown)


def estimate_trade_cost_multiplier(cfg: RiskConfig) -> float:
    """把滑点和佣金合并为一个换仓成本比例。"""

    return (float(cfg.slippage_bps) + float(cfg.commission_bps)) / 10_000.0
