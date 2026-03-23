"""
单因子检验模块。

这个文件把 IC、Rank IC、quantile spread、hit rate 这些常见检验串起来，
形成一套“先验证因子，再决定要不要保留”的基础流程。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from research.ic_analysis import build_forward_returns, compute_ic_summary
from research.quantile_backtest import compute_quantile_summary


@dataclass(frozen=True)
class FactorTestConfig:
    forward_days: List[int] = field(default_factory=lambda: [1, 2, 3, 5])
    quantiles: int = 5
    primary_horizon: int = 5
    min_cross_section: int = 20
    stability_segments: int = 4
    min_stability_segment_days: int = 20


def _factor_names(panel: pd.DataFrame) -> List[str]:
    return [
        col
        for col in panel.columns
        if col not in {"timestamp", "symbol", "close", "eligible", "avg_dollar_volume_20", "history_days"}
    ]


def _empty_factor_payload(cfg: FactorTestConfig) -> Dict[str, Any]:
    return {
        "ic": {str(horizon): np.nan for horizon in cfg.forward_days},
        "rank_ic": {str(horizon): np.nan for horizon in cfg.forward_days},
        "icir": {str(horizon): np.nan for horizon in cfg.forward_days},
        "rank_icir": {str(horizon): np.nan for horizon in cfg.forward_days},
        "quantile": {},
        "top_bottom_spread": np.nan,
        "spread_hit_rate": np.nan,
        "segment_rank_ic": [],
        "segment_spread": [],
        "stability_segment_count": 0,
    }


def _compute_segment_stability(
    panel: pd.DataFrame,
    factor_names: List[str],
    cfg: FactorTestConfig,
) -> Dict[str, Dict[str, Any]]:
    empty = {
        factor_name: {
            "segment_rank_ic": [],
            "segment_spread": [],
            "stability_segment_count": 0,
        }
        for factor_name in factor_names
    }
    if panel.empty or not factor_names:
        return empty

    segment_count = max(int(cfg.stability_segments), 1)
    min_days = max(int(cfg.min_stability_segment_days), 1)
    unique_days = pd.to_datetime(panel["timestamp"], utc=True).drop_duplicates().sort_values().tolist()
    if len(unique_days) < segment_count * min_days:
        return empty

    segments = [list(chunk) for chunk in np.array_split(unique_days, segment_count) if len(chunk) >= min_days]
    if len(segments) < 2:
        return empty

    out = {
        factor_name: {
            "segment_rank_ic": [],
            "segment_spread": [],
            "stability_segment_count": len(segments),
        }
        for factor_name in factor_names
    }
    horizon = [int(cfg.primary_horizon)]
    horizon_key = str(cfg.primary_horizon)
    for segment_days in segments:
        segment_panel = panel[panel["timestamp"].isin(segment_days)].copy()
        ic_summary = compute_ic_summary(segment_panel, factor_names, horizon, cfg.min_cross_section)
        quantile_summary = compute_quantile_summary(
            segment_panel,
            factor_names,
            cfg.primary_horizon,
            cfg.quantiles,
            cfg.min_cross_section,
        )
        for factor_name in factor_names:
            out[factor_name]["segment_rank_ic"].append(float(ic_summary[factor_name]["rank_ic"].get(horizon_key, np.nan)))
            out[factor_name]["segment_spread"].append(float(quantile_summary[factor_name]["top_bottom_spread"]))
    return out


def build_factor_validation_payload(
    panel: pd.DataFrame,
    factor_names: List[str],
    cfg: FactorTestConfig,
) -> Dict[str, Any]:
    if panel.empty:
        factors = {factor_name: _empty_factor_payload(cfg) for factor_name in factor_names}
        return {
            "config": asdict(cfg),
            "factor_names": factor_names,
            "factor_count": len(factor_names),
            "sample_days": 0,
            "factors": factors,
        }

    ic_summary = compute_ic_summary(panel, factor_names, cfg.forward_days, cfg.min_cross_section)
    quantile_summary = compute_quantile_summary(
        panel,
        factor_names,
        cfg.primary_horizon,
        cfg.quantiles,
        cfg.min_cross_section,
    )
    segment_stability = _compute_segment_stability(panel, factor_names, cfg)

    factors: Dict[str, Any] = {}
    for factor_name in factor_names:
        stability = segment_stability.get(
            factor_name,
            {"segment_rank_ic": [], "segment_spread": [], "stability_segment_count": 0},
        )
        factors[factor_name] = {
            "ic": ic_summary[factor_name]["ic"],
            "rank_ic": ic_summary[factor_name]["rank_ic"],
            "icir": ic_summary[factor_name]["icir"],
            "rank_icir": ic_summary[factor_name]["rank_icir"],
            "quantile": quantile_summary[factor_name]["quantile_returns"],
            "top_bottom_spread": quantile_summary[factor_name]["top_bottom_spread"],
            "spread_hit_rate": quantile_summary[factor_name]["spread_hit_rate"],
            "segment_rank_ic": stability["segment_rank_ic"],
            "segment_spread": stability["segment_spread"],
            "stability_segment_count": stability["stability_segment_count"],
        }

    return {
        "config": asdict(cfg),
        "factor_names": factor_names,
        "factor_count": len(factor_names),
        "sample_days": int(panel["timestamp"].nunique()) if not panel.empty else 0,
        "factors": factors,
    }


def run_single_factor_validation(
    ohlcv: pd.DataFrame,
    standardized_panel: pd.DataFrame,
    cfg: FactorTestConfig,
) -> Dict[str, Any]:
    forward_panel = build_forward_returns(ohlcv, cfg.forward_days)
    panel = standardized_panel.merge(forward_panel.drop(columns=["close"]), on=["timestamp", "symbol"], how="left")
    panel = panel[panel["eligible"]].copy()
    factor_names = _factor_names(standardized_panel)
    return build_factor_validation_payload(panel, factor_names, cfg)
