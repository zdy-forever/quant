"""
单因子检验模块。

这个文件把 IC、Rank IC、quantile spread、hit rate 这些常见检验串起来，
形成一套“先验证因子，再决定要不要保留”的基础流程。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

import pandas as pd

from research.ic_analysis import build_forward_returns, compute_ic_summary
from research.quantile_backtest import compute_quantile_summary


@dataclass(frozen=True)
class FactorTestConfig:
    forward_days: List[int] = field(default_factory=lambda: [1, 2, 3, 5])
    quantiles: int = 5
    primary_horizon: int = 5
    min_cross_section: int = 20


def _factor_names(panel: pd.DataFrame) -> List[str]:
    return [
        col
        for col in panel.columns
        if col not in {"timestamp", "symbol", "close", "eligible", "avg_dollar_volume_20", "history_days"}
    ]


def run_single_factor_validation(
    ohlcv: pd.DataFrame,
    standardized_panel: pd.DataFrame,
    cfg: FactorTestConfig,
) -> Dict[str, Any]:
    forward_panel = build_forward_returns(ohlcv, cfg.forward_days)
    panel = standardized_panel.merge(forward_panel.drop(columns=["close"]), on=["timestamp", "symbol"], how="left")
    panel = panel[panel["eligible"]].copy()
    factor_names = _factor_names(standardized_panel)

    ic_summary = compute_ic_summary(panel, factor_names, cfg.forward_days, cfg.min_cross_section)
    quantile_summary = compute_quantile_summary(
        panel,
        factor_names,
        cfg.primary_horizon,
        cfg.quantiles,
        cfg.min_cross_section,
    )

    factors: Dict[str, Any] = {}
    for factor_name in factor_names:
        factors[factor_name] = {
            "ic": ic_summary[factor_name]["ic"],
            "rank_ic": ic_summary[factor_name]["rank_ic"],
            "icir": ic_summary[factor_name]["icir"],
            "rank_icir": ic_summary[factor_name]["rank_icir"],
            "quantile": quantile_summary[factor_name]["quantile_returns"],
            "top_bottom_spread": quantile_summary[factor_name]["top_bottom_spread"],
            "spread_hit_rate": quantile_summary[factor_name]["spread_hit_rate"],
        }

    return {
        "config": asdict(cfg),
        "factor_names": factor_names,
        "factor_count": len(factor_names),
        "factors": factors,
    }
