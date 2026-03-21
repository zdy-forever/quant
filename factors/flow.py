"""
资金流与流动性变化因子模块。

这组因子更关注：
- 价格变动需要付出多少成交额
- 最近成交有没有明显干涸或加速
- 成交量方向和价格方向有没有同向确认
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from factors.base import FactorDefinition


def flow_factor_definitions() -> Dict[str, FactorDefinition]:
    return {
        "amihud_illiquidity_20": FactorDefinition(
            name="amihud_illiquidity_20",
            category="flow",
            description="20 日 Amihud illiquidity proxy，对价格冲击更敏感的名字数值更高。",
            source_title="Illiquidity and Stock Returns: Cross-Section and Time-Series Effects",
            source_url="https://doi.org/10.1111/0022-1082.00397",
            source_note="使用日收益绝对值相对成交额的比值做简化代理。",
        ),
        "volume_dryup_10_60": FactorDefinition(
            name="volume_dryup_10_60",
            category="flow",
            description="60 日均量相对 10 日均量的比值，越大代表最近越缩量。",
            source_title="Price Momentum and Trading Volume",
            source_url="https://www.jstor.org/stable/222483",
            source_note="常用于辨别“缩量整理”与“放量冲高回落”的不同结构。",
        ),
        "obv_trend_20": FactorDefinition(
            name="obv_trend_20",
            category="flow",
            description="20 日方向性成交量占比，越大代表量价同向确认更强。",
            source_title="Price Momentum and Trading Volume",
            source_url="https://www.jstor.org/stable/222483",
            source_note="把 OBV 思路做成横截面可比较的归一化版本。",
        ),
        "dollar_volume_accel_20_60": FactorDefinition(
            name="dollar_volume_accel_20_60",
            category="flow",
            description="20 日平均成交额相对 60 日基线的加速度，越大代表活跃度升温。",
            source_title="Price Momentum and Trading Volume",
            source_url="https://www.jstor.org/stable/222483",
            source_note="更偏成交活跃度切换，适合与 breakout / trend 因子搭配。",
        ),
    }


def build_flow_factor_frame(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("symbol", group_keys=False)
    dollar_volume = df["close"] * df["volume"]
    daily_ret = grouped["close"].pct_change()
    abs_ret = daily_ret.abs()
    avg_volume_10 = grouped["volume"].transform(lambda s: s.rolling(10).mean())
    avg_volume_60 = grouped["volume"].transform(lambda s: s.rolling(60).mean())
    avg_dollar_volume_20 = dollar_volume.groupby(df["symbol"]).transform(lambda s: s.rolling(20).mean())
    avg_dollar_volume_60 = dollar_volume.groupby(df["symbol"]).transform(lambda s: s.rolling(60).mean())
    signed_volume = np.sign(daily_ret.fillna(0.0)) * df["volume"]
    obv_ratio_20 = signed_volume.groupby(df["symbol"]).transform(lambda s: s.rolling(20).sum()) / grouped["volume"].transform(
        lambda s: s.rolling(20).sum()
    ).replace(0.0, np.nan)
    amihud = (abs_ret / dollar_volume.replace(0.0, np.nan)).groupby(df["symbol"]).transform(lambda s: s.rolling(20).mean())

    out = df[["timestamp", "symbol"]].copy()
    out["amihud_illiquidity_20"] = np.log1p((amihud * 1_000_000.0).clip(lower=0.0))
    out["volume_dryup_10_60"] = avg_volume_60 / avg_volume_10.replace(0.0, np.nan) - 1.0
    out["obv_trend_20"] = obv_ratio_20
    out["dollar_volume_accel_20_60"] = avg_dollar_volume_20 / avg_dollar_volume_60.replace(0.0, np.nan) - 1.0
    return out
