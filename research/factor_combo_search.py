"""
低相关多因子组合搜索模块。

这个文件专门解决一个更偏组合研究的问题：
- 单因子先确认方向是否稳定
- 再把方向稳定、相关性又不高的因子放到一起
- 最后输出几组候选“大 alpha 因子”供后续回测

如果你是量化新手，可以把它理解成：
先挑“各自有用”的零件，再避免把太像的零件重复装进同一个模型里。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Any, Dict, List, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FactorComboSearchConfig:
    primary_horizon: int = 5
    min_train_rank_ic: float = 0.01
    min_oos_rank_ic: float = 0.005
    min_train_spread: float = 0.0
    min_oos_spread: float = 0.0
    min_train_hit_rate: float = 0.50
    min_oos_hit_rate: float = 0.50
    candidate_pool_size: int = 8
    min_combo_size: int = 2
    max_combo_size: int = 4
    max_pairwise_correlation: float = 0.30
    max_combinations: int = 12


def _factor_payload(result: Dict[str, Any], factor_name: str) -> Dict[str, Any]:
    return result["factors"][factor_name]


def _oriented_factor_summary(
    factor_name: str,
    train_result: Dict[str, Any],
    oos_result: Dict[str, Any],
    factor_definitions: Dict[str, Dict[str, Any]],
    cfg: FactorComboSearchConfig,
) -> Dict[str, Any]:
    horizon = str(cfg.primary_horizon)
    train_payload = _factor_payload(train_result, factor_name)
    oos_payload = _factor_payload(oos_result, factor_name)

    raw_train_rank_ic = float(train_payload["rank_ic"].get(horizon, np.nan))
    raw_oos_rank_ic = float(oos_payload["rank_ic"].get(horizon, np.nan))
    raw_train_spread = float(train_payload["top_bottom_spread"])
    raw_oos_spread = float(oos_payload["top_bottom_spread"])
    raw_train_hit_rate = float(train_payload["spread_hit_rate"])
    raw_oos_hit_rate = float(oos_payload["spread_hit_rate"])

    direction = 1.0 if raw_train_rank_ic >= 0 else -1.0
    train_rank_ic = direction * raw_train_rank_ic
    oos_rank_ic = direction * raw_oos_rank_ic
    train_spread = direction * raw_train_spread
    oos_spread = direction * raw_oos_spread
    train_hit_rate = raw_train_hit_rate if direction > 0 else 1.0 - raw_train_hit_rate
    oos_hit_rate = raw_oos_hit_rate if direction > 0 else 1.0 - raw_oos_hit_rate

    meta = factor_definitions.get(factor_name, {})
    selection_score = (
        0.45 * train_rank_ic
        + 0.30 * oos_rank_ic
        + 0.15 * train_spread
        + 0.10 * oos_spread
    )
    return {
        "factor": factor_name,
        "category": str(meta.get("category", "unknown")),
        "description": str(meta.get("description", "")),
        "direction": int(direction),
        "direction_label": "positive" if direction > 0 else "inverse",
        "train_rank_ic": train_rank_ic,
        "oos_rank_ic": oos_rank_ic,
        "train_spread": train_spread,
        "oos_spread": oos_spread,
        "train_hit_rate": train_hit_rate,
        "oos_hit_rate": oos_hit_rate,
        "selection_score": float(selection_score),
    }


def select_oriented_factor_pool(
    train_result: Dict[str, Any],
    oos_result: Dict[str, Any],
    factor_definitions: Dict[str, Dict[str, Any]],
    cfg: FactorComboSearchConfig,
) -> Dict[str, Any]:
    selected: List[Dict[str, Any]] = []
    dropped: Dict[str, str] = {}

    for factor_name in train_result["factor_names"]:
        summary = _oriented_factor_summary(factor_name, train_result, oos_result, factor_definitions, cfg)
        core_values = [
            summary["train_rank_ic"],
            summary["oos_rank_ic"],
            summary["train_spread"],
            summary["oos_spread"],
            summary["train_hit_rate"],
            summary["oos_hit_rate"],
        ]
        if not np.isfinite(core_values).all():
            dropped[factor_name] = "train/oos regime 样本不足，核心统计为 NaN"
            continue

        if summary["train_rank_ic"] < cfg.min_train_rank_ic:
            dropped[factor_name] = f"oriented_train_rank_ic={summary['train_rank_ic']:.4f} 低于阈值"
            continue
        if summary["oos_rank_ic"] < cfg.min_oos_rank_ic:
            dropped[factor_name] = f"oriented_oos_rank_ic={summary['oos_rank_ic']:.4f} 低于阈值"
            continue
        if summary["train_spread"] < cfg.min_train_spread:
            dropped[factor_name] = f"oriented_train_spread={summary['train_spread']:.4f} 低于阈值"
            continue
        if summary["oos_spread"] < cfg.min_oos_spread:
            dropped[factor_name] = f"oriented_oos_spread={summary['oos_spread']:.4f} 低于阈值"
            continue
        if summary["train_hit_rate"] < cfg.min_train_hit_rate:
            dropped[factor_name] = f"oriented_train_hit_rate={summary['train_hit_rate']:.2%} 低于阈值"
            continue
        if summary["oos_hit_rate"] < cfg.min_oos_hit_rate:
            dropped[factor_name] = f"oriented_oos_hit_rate={summary['oos_hit_rate']:.2%} 低于阈值"
            continue
        selected.append(summary)

    ranked = sorted(selected, key=lambda item: item["selection_score"], reverse=True)
    pool = ranked[: cfg.candidate_pool_size]
    return {
        "config": asdict(cfg),
        "candidate_factors": pool,
        "dropped_factors": dropped,
    }


def select_train_only_oriented_factor_pool(
    train_result: Dict[str, Any],
    factor_definitions: Dict[str, Dict[str, Any]],
    cfg: FactorComboSearchConfig,
) -> Dict[str, Any]:
    selected: List[Dict[str, Any]] = []
    dropped: Dict[str, str] = {}

    for factor_name in train_result["factor_names"]:
        train_payload = _factor_payload(train_result, factor_name)
        raw_train_rank_ic = float(train_payload["rank_ic"].get(str(cfg.primary_horizon), np.nan))
        raw_train_spread = float(train_payload["top_bottom_spread"])
        raw_train_hit_rate = float(train_payload["spread_hit_rate"])
        direction = 1.0 if raw_train_rank_ic >= 0 else -1.0

        train_rank_ic = direction * raw_train_rank_ic
        train_spread = direction * raw_train_spread
        train_hit_rate = raw_train_hit_rate if direction > 0 else 1.0 - raw_train_hit_rate
        meta = factor_definitions.get(factor_name, {})
        summary = {
            "factor": factor_name,
            "category": str(meta.get("category", "unknown")),
            "description": str(meta.get("description", "")),
            "direction": int(direction),
            "direction_label": "positive" if direction > 0 else "inverse",
            "train_rank_ic": train_rank_ic,
            "oos_rank_ic": np.nan,
            "train_spread": train_spread,
            "oos_spread": np.nan,
            "train_hit_rate": train_hit_rate,
            "oos_hit_rate": np.nan,
            "selection_score": float(0.70 * train_rank_ic + 0.20 * train_spread + 0.10 * (train_hit_rate - 0.50)),
        }
        core_values = [train_rank_ic, train_spread, train_hit_rate]
        if not np.isfinite(core_values).all():
            dropped[factor_name] = "train regime 样本不足，核心统计为 NaN"
            continue

        if train_rank_ic < cfg.min_train_rank_ic:
            dropped[factor_name] = f"train_rank_ic={train_rank_ic:.4f} 低于阈值"
            continue
        if train_spread < cfg.min_train_spread:
            dropped[factor_name] = f"train_spread={train_spread:.4f} 低于阈值"
            continue
        if train_hit_rate < cfg.min_train_hit_rate:
            dropped[factor_name] = f"train_hit_rate={train_hit_rate:.2%} 低于阈值"
            continue
        selected.append(summary)

    ranked = sorted(selected, key=lambda item: item["selection_score"], reverse=True)
    return {
        "config": asdict(cfg),
        "candidate_factors": ranked[: cfg.candidate_pool_size],
        "dropped_factors": dropped,
    }


def compute_train_factor_correlation(
    standardized_panel: pd.DataFrame,
    factor_names: Sequence[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    if not factor_names:
        return pd.DataFrame()

    panel = standardized_panel.copy()
    panel["timestamp"] = pd.to_datetime(panel["timestamp"], utc=True)
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    sample = panel[
        (panel["timestamp"] >= start_ts)
        & (panel["timestamp"] <= end_ts)
        & panel["eligible"]
    ][list(factor_names)].copy()

    if sample.empty:
        return pd.DataFrame(np.eye(len(factor_names)), index=list(factor_names), columns=list(factor_names))

    corr = sample.corr().fillna(0.0)
    for factor_name in factor_names:
        if factor_name in corr.index:
            corr.loc[factor_name, factor_name] = 1.0
    return corr


def _pairwise_abs_corr(combo: Sequence[str], corr: pd.DataFrame) -> List[float]:
    values: List[float] = []
    for left, right in combinations(combo, 2):
        if left not in corr.index or right not in corr.columns:
            values.append(0.0)
            continue
        values.append(abs(float(corr.loc[left, right])))
    return values


def generate_low_correlation_combinations(
    candidate_factors: List[Dict[str, Any]],
    factor_definitions: Dict[str, Dict[str, Any]],
    corr: pd.DataFrame,
    cfg: FactorComboSearchConfig,
) -> Dict[str, Any]:
    lookup = {item["factor"]: item for item in candidate_factors}
    factor_names = [item["factor"] for item in candidate_factors]
    combos: List[Dict[str, Any]] = []

    for combo_size in range(cfg.min_combo_size, cfg.max_combo_size + 1):
        for combo in combinations(factor_names, combo_size):
            pairwise_abs = _pairwise_abs_corr(combo, corr)
            max_abs_corr = max(pairwise_abs) if pairwise_abs else 0.0
            if max_abs_corr > cfg.max_pairwise_correlation:
                continue

            avg_abs_corr = float(np.mean(pairwise_abs)) if pairwise_abs else 0.0
            categories = [str(factor_definitions.get(name, {}).get("category", "unknown")) for name in combo]
            factor_quality = float(np.mean([lookup[name]["selection_score"] for name in combo]))
            diversity_bonus = 0.001 * len(set(categories))
            research_score = factor_quality - 0.25 * avg_abs_corr + diversity_bonus
            weight_scale = sum(max(lookup[name]["selection_score"], 1e-12) for name in combo)
            factor_weights = {
                name: float(lookup[name]["direction"]) * max(lookup[name]["selection_score"], 1e-12) / weight_scale
                for name in combo
            }

            combos.append(
                {
                    "factors": list(combo),
                    "factor_details": [lookup[name] for name in combo],
                    "categories": categories,
                    "factor_weights": factor_weights,
                    "avg_abs_corr": avg_abs_corr,
                    "max_abs_corr": max_abs_corr,
                    "research_score": research_score,
                }
            )

    ranked = sorted(
        combos,
        key=lambda item: (
            len(item["factors"]),
            item["research_score"],
            -item["avg_abs_corr"],
        ),
        reverse=True,
    )
    shortlisted = ranked[: cfg.max_combinations]
    return {
        "config": asdict(cfg),
        "candidate_count": len(candidate_factors),
        "raw_combo_count": len(combos),
        "shortlisted_combinations": shortlisted,
    }
