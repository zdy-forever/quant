"""
横截面标准化模块。

不同因子的量纲不同，不能直接相加。
这个文件负责把原始因子值在“每日横截面”上做去极值和标准化，
避免把未来分布信息混进来。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StandardizeConfig:
    method: str = "rank"
    winsorize_lower: float = 0.02
    winsorize_upper: float = 0.98


def _winsorize_series(series: pd.Series, lower: float, upper: float) -> pd.Series:
    sample = series.dropna()
    if sample.empty:
        return series
    lower_bound = sample.quantile(lower)
    upper_bound = sample.quantile(upper)
    return series.clip(lower=lower_bound, upper=upper_bound)


def _zscore_series(series: pd.Series) -> pd.Series:
    std = series.std(ddof=0)
    if pd.isna(std) or std < 1e-12:
        return pd.Series(np.nan, index=series.index, dtype=float)
    return (series - series.mean()) / std


def _rank_series(series: pd.Series) -> pd.Series:
    sample = series.dropna()
    if sample.empty:
        return pd.Series(np.nan, index=series.index, dtype=float)
    ranked = sample.rank(method="average", pct=True) - 0.5
    out = pd.Series(np.nan, index=series.index, dtype=float)
    out.loc[ranked.index] = ranked.astype(float)
    return out


def standardize_factor_panel(
    factor_panel: pd.DataFrame,
    factor_names: List[str],
    cfg: StandardizeConfig,
) -> pd.DataFrame:
    panel = factor_panel.copy()
    for factor_name in factor_names:
        winsorized = panel.groupby("timestamp")[factor_name].transform(
            lambda s: _winsorize_series(s, cfg.winsorize_lower, cfg.winsorize_upper)
        )
        if cfg.method == "zscore":
            panel[factor_name] = panel.groupby("timestamp")[factor_name].transform(
                lambda s: _zscore_series(_winsorize_series(s, cfg.winsorize_lower, cfg.winsorize_upper))
            )
        else:
            panel[factor_name] = winsorized.groupby(panel["timestamp"]).transform(_rank_series)
    return panel


def standardize_summary(cfg: StandardizeConfig) -> Dict[str, float | str]:
    return asdict(cfg)
