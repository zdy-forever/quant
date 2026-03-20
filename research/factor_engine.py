"""
因子研究引擎模块。

这里负责把最底层的数据整理成研究可以直接使用的三张表：
- universe / eligibility 表
- 原始因子表
- 标准化后的因子表

这样后面的 IC、quantile、factor selection 都能复用同一份输入。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from factors import build_factor_panel, get_factor_definitions
from research.standardize import StandardizeConfig, standardize_factor_panel


@dataclass(frozen=True)
class UniverseConfig:
    min_price: float = 8.0
    min_avg_dollar_volume: float = 8_000_000.0
    min_history_days: int = 60


def build_eligible_universe(ohlcv: pd.DataFrame, cfg: UniverseConfig) -> pd.DataFrame:
    df = ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

    grouped = df.groupby("symbol", group_keys=False)
    avg_dollar_volume = (df["close"] * df["volume"]).groupby(df["symbol"]).transform(
        lambda s: s.rolling(20).mean().shift(1)
    )
    history_days = grouped.cumcount() + 1
    eligible = (
        (df["close"] >= float(cfg.min_price))
        & (avg_dollar_volume >= float(cfg.min_avg_dollar_volume))
        & (history_days >= int(cfg.min_history_days))
        & df[["open", "high", "low", "close", "volume"]].notna().all(axis=1)
    )

    return pd.DataFrame(
        {
            "timestamp": df["timestamp"],
            "symbol": df["symbol"],
            "close": df["close"],
            "avg_dollar_volume_20": avg_dollar_volume,
            "history_days": history_days,
            "eligible": eligible.astype(bool),
        }
    )


def _factor_names(panel: pd.DataFrame) -> List[str]:
    return [col for col in panel.columns if col not in {"timestamp", "symbol", "close", "eligible", "avg_dollar_volume_20", "history_days"}]


def build_factor_research_panel(
    ohlcv: pd.DataFrame,
    universe_cfg: UniverseConfig,
    standardize_cfg: StandardizeConfig,
) -> Dict[str, Any]:
    universe = build_eligible_universe(ohlcv, universe_cfg)
    raw_factors = build_factor_panel(ohlcv)
    raw_panel = universe.merge(raw_factors, on=["timestamp", "symbol"], how="left")
    factor_names = _factor_names(raw_panel)

    for factor_name in factor_names:
        raw_panel[factor_name] = raw_panel[factor_name].where(raw_panel["eligible"], np.nan)

    standardized_panel = standardize_factor_panel(
        raw_panel[["timestamp", "symbol", "eligible"] + factor_names],
        factor_names,
        standardize_cfg,
    )
    standardized_panel = raw_panel[["timestamp", "symbol", "close", "eligible", "avg_dollar_volume_20", "history_days"]].merge(
        standardized_panel,
        on=["timestamp", "symbol", "eligible"],
        how="left",
    )

    universe_stats = {
        "avg_daily_eligible_count": float(universe.groupby("timestamp")["eligible"].sum().mean()),
        "min_daily_eligible_count": float(universe.groupby("timestamp")["eligible"].sum().min()),
        "max_daily_eligible_count": float(universe.groupby("timestamp")["eligible"].sum().max()),
    }

    return {
        "config": {
            "universe": asdict(universe_cfg),
            "standardize": asdict(standardize_cfg),
        },
        "factor_definitions": {name: asdict(defn) for name, defn in get_factor_definitions().items()},
        "factor_names": factor_names,
        "universe": universe,
        "raw_panel": raw_panel,
        "standardized_panel": standardized_panel,
        "universe_stats": universe_stats,
    }
