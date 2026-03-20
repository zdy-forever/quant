"""
动量类因子模块。

这些因子主要来自 cross-sectional momentum / relative strength 这条文献线。
研究层后面会在每日横截面上对它们做排序和标准化，
所以这里先输出“原始可解释值”，不直接写买卖规则。
"""
from __future__ import annotations

from typing import Dict

import pandas as pd

from factors.base import FactorDefinition


def momentum_factor_definitions() -> Dict[str, FactorDefinition]:
    return {
        "momentum_20": FactorDefinition(
            name="momentum_20",
            category="momentum",
            description="过去 20 个交易日收益率，用于做横截面 relative strength 排名。",
            source_title="Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency",
            source_url="https://doi.org/10.1111/j.1540-6261.1993.tb04702.x",
            source_note="Jegadeesh 与 Titman 的横截面动量主线，20 日动量是较短中周期的简化 proxy。",
        ),
        "momentum_60": FactorDefinition(
            name="momentum_60",
            category="momentum",
            description="过去 60 个交易日收益率，用于观察更慢一点的中期趋势强度。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="Chan、Jegadeesh、Lakonishok 的动量延续研究。",
        ),
        "trend_pullback_20_5": FactorDefinition(
            name="trend_pullback_20_5",
            category="momentum",
            description="20 日趋势强度减去近 5 日回撤，用来刻画 trend + pullback。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="属于把中期趋势和短期回撤拆开后再组合的工程化因子，不是论文原公式。",
        ),
    }


def build_momentum_factor_frame(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("symbol", group_keys=False)
    out = df[["timestamp", "symbol"]].copy()
    ret_5 = grouped["close"].pct_change(5)
    out["momentum_20"] = grouped["close"].pct_change(20)
    out["momentum_60"] = grouped["close"].pct_change(60)
    out["trend_pullback_20_5"] = out["momentum_20"] - ret_5
    return out
