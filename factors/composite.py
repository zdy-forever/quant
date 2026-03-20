"""
组合因子模块。

单因子研究通过之后，才会来到这里把多个稳定 alpha 组合成一个总分。
这里仍然不负责复杂出场逻辑，只负责：
- 按因子分数生成 composite score
- 从 score 映射到 top-N 候选股票
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CompositeConfig:
    top_n: int = 10
    weighting: str = "equal"
    rebalance_every_n_days: int = 1


def build_composite_score(
    standardized_panel: pd.DataFrame,
    selected_factors: List[str],
    cfg: CompositeConfig,
    custom_weights: Dict[str, float] | None = None,
) -> pd.DataFrame:
    if not selected_factors:
        return pd.DataFrame(columns=["timestamp", "symbol", "eligible", "score"])

    panel = standardized_panel[["timestamp", "symbol", "eligible"] + selected_factors].copy()
    panel = panel[panel["eligible"]].copy()
    if panel.empty:
        return pd.DataFrame(columns=["timestamp", "symbol", "eligible", "score"])

    if cfg.weighting == "custom" and custom_weights:
        weights = {name: float(custom_weights.get(name, 0.0)) for name in selected_factors}
    else:
        equal_weight = 1.0 / len(selected_factors)
        weights = {name: equal_weight for name in selected_factors}

    score = pd.Series(0.0, index=panel.index, dtype=float)
    weight_sum = 0.0
    for factor_name, weight in weights.items():
        score = score.add(panel[factor_name].fillna(0.0) * weight, fill_value=0.0)
        weight_sum += abs(weight)
    if weight_sum > 0:
        score = score / weight_sum

    out = panel[["timestamp", "symbol", "eligible"]].copy()
    out["score"] = score
    out["composite_config"] = str(asdict(cfg))
    return out


def build_top_n_signal(score_frame: pd.DataFrame, top_n: int) -> pd.Series:
    if score_frame.empty:
        empty_index = pd.MultiIndex.from_arrays([[], []], names=["timestamp", "symbol"])
        return pd.Series(dtype=int, index=empty_index, name="signal")

    ranked = score_frame.copy()
    ranked["rank"] = ranked.groupby("timestamp")["score"].rank(method="first", ascending=False)
    signal_df = ranked[ranked["rank"] <= top_n][["timestamp", "symbol"]].copy()
    signal_df["signal"] = 1
    idx = pd.MultiIndex.from_frame(signal_df[["timestamp", "symbol"]], names=["timestamp", "symbol"])
    return pd.Series(signal_df["signal"].values, index=idx, name="signal")


def latest_top_picks(score_frame: pd.DataFrame, top_n: int) -> List[str]:
    if score_frame.empty:
        return []
    latest_ts = pd.to_datetime(score_frame["timestamp"], utc=True).max()
    latest_slice = score_frame[score_frame["timestamp"] == latest_ts].copy()
    latest_slice = latest_slice.sort_values("score", ascending=False).head(top_n)
    return latest_slice["symbol"].astype(str).tolist()
