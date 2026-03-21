"""
风险结构类因子模块。

这组因子不直接预测趋势方向，而是刻画：
- 风险主要来自下跌还是普通波动
- 波动是在扩张还是收缩
- 隔夜风险和日内风险是否变得更不稳定
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from factors.base import FactorDefinition


def risk_structure_factor_definitions() -> Dict[str, FactorDefinition]:
    return {
        "downside_risk_20": FactorDefinition(
            name="downside_risk_20",
            category="risk_structure",
            description="过去 20 日负收益波动率取负号，值越大代表下跌风险越低。",
            source_title="Downside Risk",
            source_url="https://doi.org/10.1111/j.1540-6261.2006.00851.x",
            source_note="把总体波动拆成 downside-only 风险，更适合和反转/趋势因子搭配看。",
        ),
        "range_expansion_5_20": FactorDefinition(
            name="range_expansion_5_20",
            category="risk_structure",
            description="5 日 ATR 相对 20 日 ATR 的扩张程度，越大代表近期波动突然放大。",
            source_title="Volatility Trading",
            source_url="https://onlinelibrary.wiley.com/doi/book/10.1002/9781119204198",
            source_note="用于区分安静趋势和高噪音爆发行情。",
        ),
        "gap_volatility_20": FactorDefinition(
            name="gap_volatility_20",
            category="risk_structure",
            description="20 日隔夜跳空波动率，用来衡量消息驱动风险。",
            source_title="Price Momentum and Trading Volume",
            source_url="https://www.jstor.org/stable/222483",
            source_note="隔夜风险高的股票，其次日横截面 alpha 常和普通日内波动不同。",
        ),
        "vol_of_range_20": FactorDefinition(
            name="vol_of_range_20",
            category="risk_structure",
            description="20 日真实波幅占比的波动率，越大代表波动本身更不稳定。",
            source_title="Volatility Trading",
            source_url="https://onlinelibrary.wiley.com/doi/book/10.1002/9781119204198",
            source_note="把“波动水平”和“波动是否稳定”拆成两个维度。",
        ),
    }


def build_risk_structure_factor_frame(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("symbol", group_keys=False)
    prev_close = grouped["close"].shift(1)
    daily_ret = grouped["close"].pct_change()
    overnight_gap = df["open"] / prev_close.replace(0.0, np.nan) - 1.0
    true_range = pd.concat(
        [
            (df["high"] - df["low"]).abs(),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    true_range_pct = true_range / prev_close.replace(0.0, np.nan)
    atr_5 = true_range.groupby(df["symbol"]).transform(lambda s: s.rolling(5).mean())
    atr_20 = true_range.groupby(df["symbol"]).transform(lambda s: s.rolling(20).mean())
    downside_ret = daily_ret.clip(upper=0.0)

    out = df[["timestamp", "symbol"]].copy()
    out["downside_risk_20"] = -downside_ret.groupby(df["symbol"]).transform(lambda s: s.rolling(20).std(ddof=0))
    out["range_expansion_5_20"] = atr_5 / atr_20.replace(0.0, np.nan)
    out["gap_volatility_20"] = overnight_gap.groupby(df["symbol"]).transform(lambda s: s.rolling(20).std(ddof=0))
    out["vol_of_range_20"] = true_range_pct.groupby(df["symbol"]).transform(lambda s: s.rolling(20).std(ddof=0))
    return out
