"""
IC 分析模块。

这个文件负责回答一个最基本的问题：
“因子值越高的股票，未来收益是不是也更高？”

如果这个问题在单因子层面都回答不了，
后面再复杂的策略和参数都不值得继续调。
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd


def build_forward_returns(ohlcv: pd.DataFrame, horizons: List[int]) -> pd.DataFrame:
    df = ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    grouped = df.groupby("symbol", group_keys=False)
    out = df[["timestamp", "symbol", "close"]].copy()
    for horizon in horizons:
        out[f"fwd_ret_{horizon}"] = grouped["close"].shift(-horizon) / df["close"] - 1.0
    return out


def _cross_sectional_corr(one_day: pd.DataFrame, factor_name: str, ret_name: str, method: str, min_obs: int) -> float:
    sample = one_day[[factor_name, ret_name]].dropna()
    if sample.shape[0] < min_obs:
        return np.nan
    if method == "spearman":
        ranked_factor = sample[factor_name].rank(method="average")
        ranked_return = sample[ret_name].rank(method="average")
        return float(ranked_factor.corr(ranked_return, method="pearson"))
    return float(sample[factor_name].corr(sample[ret_name], method=method))


def compute_ic_summary(
    panel: pd.DataFrame,
    factor_names: List[str],
    horizons: List[int],
    min_obs: int = 20,
) -> Dict[str, Dict[str, Dict[str, float]]]:
    summary: Dict[str, Dict[str, Dict[str, float]]] = {}
    for factor_name in factor_names:
        factor_summary: Dict[str, Dict[str, float]] = {"ic": {}, "rank_ic": {}, "icir": {}, "rank_icir": {}}
        for horizon in horizons:
            ret_name = f"fwd_ret_{horizon}"
            ic_series = panel.groupby("timestamp").apply(
                lambda one_day: _cross_sectional_corr(one_day, factor_name, ret_name, "pearson", min_obs)
            )
            rank_ic_series = panel.groupby("timestamp").apply(
                lambda one_day: _cross_sectional_corr(one_day, factor_name, ret_name, "spearman", min_obs)
            )
            factor_summary["ic"][str(horizon)] = float(ic_series.mean())
            factor_summary["rank_ic"][str(horizon)] = float(rank_ic_series.mean())
            factor_summary["icir"][str(horizon)] = float(
                ic_series.mean() / (ic_series.std(ddof=0) + 1e-12)
            )
            factor_summary["rank_icir"][str(horizon)] = float(
                rank_ic_series.mean() / (rank_ic_series.std(ddof=0) + 1e-12)
            )
        summary[factor_name] = factor_summary
    return summary
