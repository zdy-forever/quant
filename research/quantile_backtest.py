"""
分位数检验模块。

这里做的不是最终组合回测，而是更基础的问题：
- 把股票按单因子从低到高分组
- 看 top quantile 和 bottom quantile 的未来收益差

如果 top-minus-bottom spread 都不稳定，
那这个因子通常不值得进入多因子组合。
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd


def compute_quantile_summary(
    panel: pd.DataFrame,
    factor_names: List[str],
    horizon: int,
    quantiles: int,
    min_obs: int = 20,
) -> Dict[str, Dict[str, Any]]:
    ret_name = f"fwd_ret_{horizon}"
    out: Dict[str, Dict[str, Any]] = {}

    for factor_name in factor_names:
        sample = panel[["timestamp", "symbol", factor_name, ret_name]].dropna().copy()
        if sample.empty:
            out[factor_name] = {"quantile_returns": {}, "top_bottom_spread": np.nan, "spread_hit_rate": np.nan}
            continue

        def _assign_quantile(one_day: pd.DataFrame) -> pd.DataFrame:
            if one_day.shape[0] < min_obs or one_day[factor_name].nunique() < quantiles:
                one_day["quantile"] = np.nan
                return one_day
            one_day["quantile"] = pd.qcut(one_day[factor_name], quantiles, labels=False, duplicates="drop")
            return one_day

        tagged_parts = [_assign_quantile(one_day.copy()) for _, one_day in sample.groupby("timestamp", sort=True)]
        tagged = pd.concat(tagged_parts, ignore_index=True) if tagged_parts else sample.iloc[0:0].copy()
        quantile_returns = tagged.dropna(subset=["quantile"]).groupby("quantile")[ret_name].mean()
        per_day_quantile = tagged.dropna(subset=["quantile"]).groupby(["timestamp", "quantile"])[ret_name].mean().unstack("quantile")

        top_label = per_day_quantile.columns.max() if not per_day_quantile.empty else np.nan
        bottom_label = per_day_quantile.columns.min() if not per_day_quantile.empty else np.nan
        spread_series = (
            per_day_quantile[top_label] - per_day_quantile[bottom_label]
            if pd.notna(top_label) and pd.notna(bottom_label)
            else pd.Series(dtype=float)
        )

        out[factor_name] = {
            "quantile_returns": {str(int(idx) + 1): float(value) for idx, value in quantile_returns.items()},
            "top_bottom_spread": float(spread_series.mean()) if not spread_series.empty else np.nan,
            "spread_hit_rate": float((spread_series > 0.0).mean()) if not spread_series.empty else np.nan,
        }
    return out
