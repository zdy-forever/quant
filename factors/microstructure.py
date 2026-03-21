"""
日线结构与 K 线微观行为因子模块。

这些因子更关注价格在一段时间里的“走法”：
- 跳空更多还是日内推进更多
- 收盘是否持续更强
- 当前价格在过去通道里的位置如何
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from factors.base import FactorDefinition


def microstructure_factor_definitions() -> Dict[str, FactorDefinition]:
    return {
        "overnight_gap_5": FactorDefinition(
            name="overnight_gap_5",
            category="microstructure",
            description="过去 5 日平均隔夜跳空幅度，用来观察信息驱动是否持续发生。",
            source_title="Price Momentum and Trading Volume",
            source_url="https://www.jstor.org/stable/222483",
            source_note="隔夜跳空常和信息冲击有关，这里把它与纯日内走势拆开检验。",
        ),
        "overnight_gap_20": FactorDefinition(
            name="overnight_gap_20",
            category="microstructure",
            description="过去 20 日平均隔夜跳空幅度，用来观察更慢一点的消息驱动偏向。",
            source_title="Price Momentum and Trading Volume",
            source_url="https://www.jstor.org/stable/222483",
            source_note="用更长窗口观察 gap 是否持续偏向同一方向，而不是只看短期噪音。",
        ),
        "intraday_strength_5": FactorDefinition(
            name="intraday_strength_5",
            category="microstructure",
            description="过去 5 日日内收益均值，越大代表收盘推进更持续。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="把趋势拆成日内推进强度，而不是只看收盘对收盘收益。",
        ),
        "intraday_strength_10": FactorDefinition(
            name="intraday_strength_10",
            category="microstructure",
            description="过去 10 日日内收益均值，观察更稳定的日内推进强度。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="和 5 日版本配合，可以判断日内强度是短促还是更持续。",
        ),
        "intraday_hit_rate_10": FactorDefinition(
            name="intraday_hit_rate_10",
            category="microstructure",
            description="过去 10 日日内上涨天数占比，越大代表强收盘更稳定。",
            source_title="Trading Volume and Serial Correlation in Stock Returns",
            source_url="https://academic.oup.com/qje/article/108/4/905/1899978",
            source_note="把 intraday strength 的均值和命中率拆开，避免只被极端大阳线主导。",
        ),
        "body_to_range_5": FactorDefinition(
            name="body_to_range_5",
            category="microstructure",
            description="过去 5 日 K 线实体相对振幅的均值，越大代表强势收盘更持续。",
            source_title="Trading Volume and Serial Correlation in Stock Returns",
            source_url="https://academic.oup.com/qje/article/108/4/905/1899978",
            source_note="比单日 close_location 更稳一点，强调多日持续的强弱收盘结构。",
        ),
        "channel_position_60": FactorDefinition(
            name="channel_position_60",
            category="microstructure",
            description="收盘在过去 60 日价格通道中的位置，越高代表越接近上沿。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="比单纯距离前高更平滑，适合和 pullback / reversal 组合看。",
        ),
        "channel_position_20": FactorDefinition(
            name="channel_position_20",
            category="microstructure",
            description="收盘在过去 20 日价格通道中的位置，越高代表越接近短期上沿。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="和 60 日通道位置一起看，可以拆短中期趋势位置是否一致。",
        ),
    }


def build_microstructure_factor_frame(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("symbol", group_keys=False)
    prev_close = grouped["close"].shift(1)
    overnight_gap = df["open"] / prev_close.replace(0.0, np.nan) - 1.0
    intraday_return = df["close"] / df["open"].replace(0.0, np.nan) - 1.0
    bar_range = (df["high"] - df["low"]).replace(0.0, np.nan)
    body_to_range = (df["close"] - df["open"]) / bar_range
    rolling_high_20 = grouped["high"].transform(lambda s: s.rolling(20).max().shift(1))
    rolling_low_20 = grouped["low"].transform(lambda s: s.rolling(20).min().shift(1))
    rolling_high_60 = grouped["high"].transform(lambda s: s.rolling(60).max().shift(1))
    rolling_low_60 = grouped["low"].transform(lambda s: s.rolling(60).min().shift(1))

    out = df[["timestamp", "symbol"]].copy()
    out["overnight_gap_5"] = overnight_gap.groupby(df["symbol"]).transform(lambda s: s.rolling(5).mean())
    out["overnight_gap_20"] = overnight_gap.groupby(df["symbol"]).transform(lambda s: s.rolling(20).mean())
    out["intraday_strength_5"] = intraday_return.groupby(df["symbol"]).transform(lambda s: s.rolling(5).mean())
    out["intraday_strength_10"] = intraday_return.groupby(df["symbol"]).transform(lambda s: s.rolling(10).mean())
    out["intraday_hit_rate_10"] = intraday_return.gt(0).groupby(df["symbol"]).transform(lambda s: s.rolling(10).mean())
    out["body_to_range_5"] = body_to_range.groupby(df["symbol"]).transform(lambda s: s.rolling(5).mean())
    out["channel_position_20"] = (df["close"] - rolling_low_20) / (rolling_high_20 - rolling_low_20).replace(0.0, np.nan)
    out["channel_position_60"] = (df["close"] - rolling_low_60) / (rolling_high_60 - rolling_low_60).replace(0.0, np.nan)
    return out
