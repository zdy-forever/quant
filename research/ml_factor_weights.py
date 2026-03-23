"""
轻量机器学习因子权重模块。

这里不做黑箱预测，也不做复杂在线学习，
只做一件事：
- 对已经通过研究筛选的小规模因子组合
- 用训练期的正则化线性模型学习一组更合适的固定权重
- 再把这组固定权重拿到样本外做严格验证

这样可以把 ML 约束在“学组合权重”这一层，
尽量降低过拟合风险。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RidgeWeightConfig:
    alpha_grid: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 4.0)
    validation_ratio: float = 0.25
    min_validation_days: int = 20
    min_train_days: int = 40
    min_sample_rows: int = 400
    min_daily_samples: int = 20


def _daily_rank_ic(one_day: pd.DataFrame, score_col: str, ret_col: str, min_obs: int) -> float:
    sample = one_day[[score_col, ret_col]].dropna()
    if sample.shape[0] < int(min_obs):
        return np.nan
    ranked_score = sample[score_col].rank(method="average")
    ranked_ret = sample[ret_col].rank(method="average")
    return float(ranked_score.corr(ranked_ret, method="pearson"))


def _daily_top_bottom_spread(one_day: pd.DataFrame, score_col: str, ret_col: str, min_obs: int) -> float:
    sample = one_day[[score_col, ret_col]].dropna().sort_values(score_col, ascending=False)
    if sample.shape[0] < int(min_obs):
        return np.nan
    bucket = max(int(sample.shape[0] * 0.2), 1)
    top_mean = float(sample.head(bucket)[ret_col].mean())
    bottom_mean = float(sample.tail(bucket)[ret_col].mean())
    return top_mean - bottom_mean


def _validation_summary(
    sample: pd.DataFrame,
    score_col: str,
    ret_col: str,
    min_daily_samples: int,
) -> Dict[str, float]:
    rank_ic = sample.groupby("timestamp").apply(
        lambda one_day: _daily_rank_ic(one_day, score_col, ret_col, min_daily_samples)
    )
    spread = sample.groupby("timestamp").apply(
        lambda one_day: _daily_top_bottom_spread(one_day, score_col, ret_col, min_daily_samples)
    )
    spread_hit = spread.dropna()
    return {
        "rank_ic": float(rank_ic.mean()) if not rank_ic.empty else float("nan"),
        "spread": float(spread.mean()) if not spread.empty else float("nan"),
        "spread_hit_rate": float((spread_hit > 0.0).mean()) if not spread_hit.empty else float("nan"),
    }


def fit_oriented_ridge_factor_weights(
    panel: pd.DataFrame,
    factor_names: List[str],
    factor_directions: Dict[str, int],
    ret_col: str,
    cfg: RidgeWeightConfig | None = None,
) -> Dict[str, Any] | None:
    if cfg is None:
        cfg = RidgeWeightConfig()
    if not factor_names or ret_col not in panel.columns:
        return None

    use_cols = ["timestamp", ret_col] + list(factor_names)
    if "eligible" in panel.columns:
        sample = panel.loc[panel["eligible"], use_cols].copy()
    else:
        sample = panel[use_cols].copy()
    sample = sample.dropna()
    if sample.empty or sample.shape[0] < int(cfg.min_sample_rows):
        return None

    sample["timestamp"] = pd.to_datetime(sample["timestamp"], utc=True)
    unique_days = sorted(sample["timestamp"].drop_duplicates().tolist())
    validation_days = max(int(len(unique_days) * float(cfg.validation_ratio)), int(cfg.min_validation_days))
    if len(unique_days) <= validation_days or (len(unique_days) - validation_days) < int(cfg.min_train_days):
        return None

    train_days = set(unique_days[:-validation_days])
    valid_days = set(unique_days[-validation_days:])
    train = sample[sample["timestamp"].isin(train_days)].copy()
    valid = sample[sample["timestamp"].isin(valid_days)].copy()
    if train.empty or valid.empty:
        return None

    direction_vec = np.array([1.0 if int(factor_directions.get(name, 1)) >= 0 else -1.0 for name in factor_names], dtype=float)
    x_train = train[factor_names].to_numpy(dtype=float) * direction_vec
    y_train = train[ret_col].to_numpy(dtype=float)
    x_valid = valid[factor_names].to_numpy(dtype=float) * direction_vec

    best_payload: Dict[str, Any] | None = None
    for alpha in cfg.alpha_grid:
        xtx = x_train.T @ x_train
        ridge = xtx + np.eye(len(factor_names), dtype=float) * float(alpha)
        xty = x_train.T @ y_train
        coef = np.linalg.pinv(ridge) @ xty
        coef = np.clip(coef, 0.0, None)
        coef_sum = float(np.abs(coef).sum())
        if coef_sum <= 1e-12:
            continue
        coef = coef / coef_sum

        valid = valid.copy()
        valid["ml_score"] = x_valid @ coef
        validation = _validation_summary(valid, "ml_score", ret_col, cfg.min_daily_samples)
        rank_ic = float(validation.get("rank_ic", np.nan))
        spread = float(validation.get("spread", np.nan))
        hit_rate = float(validation.get("spread_hit_rate", np.nan))
        if not np.isfinite(rank_ic):
            continue

        payload = {
            "alpha": float(alpha),
            "factor_weights": {
                name: float(weight * direction)
                for name, weight, direction in zip(factor_names, coef.tolist(), direction_vec.tolist())
            },
            "validation_rank_ic": rank_ic,
            "validation_spread": spread if np.isfinite(spread) else 0.0,
            "validation_hit_rate": hit_rate if np.isfinite(hit_rate) else 0.5,
            "train_days": int(len(train_days)),
            "validation_days": int(len(valid_days)),
        }
        payload["selection_score"] = (
            payload["validation_rank_ic"],
            payload["validation_spread"],
            payload["validation_hit_rate"],
            -payload["alpha"],
        )
        if best_payload is None or payload["selection_score"] > best_payload["selection_score"]:
            best_payload = payload

    if best_payload is None:
        return None
    return best_payload
