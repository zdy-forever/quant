"""
因子筛选模块。

这里的任务不是“找最会赚钱的参数”，而是：
- 先看 train 里哪些因子方向明确
- 再看 OOS 里方向有没有翻掉
- 只保留不需要复杂调参、方向又稳定的 alpha
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

import numpy as np


@dataclass(frozen=True)
class FactorSelectionConfig:
    primary_horizon: int = 5
    min_train_rank_ic: float = 0.01
    min_oos_rank_ic: float = 0.005
    min_train_spread: float = 0.0
    min_oos_spread: float = 0.0
    min_train_hit_rate: float = 0.50
    min_oos_hit_rate: float = 0.50
    max_factors: int = 6


def _metric(result: Dict[str, Any], factor_name: str, bucket: str, horizon: int | None = None) -> float:
    factor_payload = result["factors"][factor_name]
    if horizon is None:
        value = factor_payload[bucket]
    else:
        value = factor_payload[bucket].get(str(horizon), np.nan)
    return float(value)


def select_train_factors(train_result: Dict[str, Any], cfg: FactorSelectionConfig) -> Dict[str, Any]:
    scored: List[Dict[str, Any]] = []
    dropped: Dict[str, str] = {}

    for factor_name in train_result["factor_names"]:
        train_rank_ic = _metric(train_result, factor_name, "rank_ic", cfg.primary_horizon)
        train_spread = _metric(train_result, factor_name, "top_bottom_spread")
        train_hit_rate = _metric(train_result, factor_name, "spread_hit_rate")

        if train_rank_ic < cfg.min_train_rank_ic:
            dropped[factor_name] = f"train_rank_ic={train_rank_ic:.4f} 低于阈值"
            continue
        if train_spread < cfg.min_train_spread:
            dropped[factor_name] = f"train_spread={train_spread:.4f} 低于阈值"
            continue
        if train_hit_rate < cfg.min_train_hit_rate:
            dropped[factor_name] = f"train_hit_rate={train_hit_rate:.2%} 低于阈值"
            continue

        score = 0.7 * train_rank_ic + 0.3 * train_spread
        scored.append(
            {
                "factor": factor_name,
                "train_rank_ic": train_rank_ic,
                "train_spread": train_spread,
                "train_hit_rate": train_hit_rate,
                "selection_score": float(score),
            }
        )

    ranked = sorted(scored, key=lambda item: item["selection_score"], reverse=True)
    return {
        "config": asdict(cfg),
        "selected_factors": [item["factor"] for item in ranked[: cfg.max_factors]],
        "ranked_factors": ranked,
        "dropped_factors": dropped,
    }


def filter_oos_consistent_factors(
    selected_factors: List[str],
    oos_result: Dict[str, Any],
    cfg: FactorSelectionConfig,
) -> Dict[str, Any]:
    passed: List[str] = []
    failed: Dict[str, str] = {}
    for factor_name in selected_factors:
        oos_rank_ic = _metric(oos_result, factor_name, "rank_ic", cfg.primary_horizon)
        oos_spread = _metric(oos_result, factor_name, "top_bottom_spread")
        oos_hit_rate = _metric(oos_result, factor_name, "spread_hit_rate")

        if oos_rank_ic < cfg.min_oos_rank_ic:
            failed[factor_name] = f"oos_rank_ic={oos_rank_ic:.4f} 低于阈值"
            continue
        if oos_spread < cfg.min_oos_spread:
            failed[factor_name] = f"oos_spread={oos_spread:.4f} 低于阈值"
            continue
        if oos_hit_rate < cfg.min_oos_hit_rate:
            failed[factor_name] = f"oos_hit_rate={oos_hit_rate:.2%} 低于阈值"
            continue
        passed.append(factor_name)

    return {
        "oos_consistent_factors": passed,
        "oos_failed_factors": failed,
    }


def select_stable_factors(
    train_result: Dict[str, Any],
    oos_result: Dict[str, Any],
    cfg: FactorSelectionConfig,
) -> Dict[str, Any]:
    train_selection = select_train_factors(train_result, cfg)
    oos_filter = filter_oos_consistent_factors(train_selection["selected_factors"], oos_result, cfg)
    return {
        "config": asdict(cfg),
        "train_selected_factors": train_selection["selected_factors"],
        "stable_factors": oos_filter["oos_consistent_factors"],
        "ranked_factors": train_selection["ranked_factors"],
        "dropped_factors": train_selection["dropped_factors"],
        "oos_failed_factors": oos_filter["oos_failed_factors"],
    }
