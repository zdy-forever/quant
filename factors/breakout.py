"""
突破、K 线位置与趋势回踩类因子模块。

这类因子不是直接下单规则，而是把“gap + continuation”“trend + pullback”
这些主观描述拆成能单独检验的数值特征。
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from factors.base import FactorDefinition


def breakout_factor_definitions() -> Dict[str, FactorDefinition]:
    return {
        "breakout_distance_20": FactorDefinition(
            name="breakout_distance_20",
            category="breakout",
            description="当前收盘相对 20 日前高的距离，越靠近突破越高。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="把中短期趋势延续拆成“距离突破位有多近”的原子因子。",
        ),
        "breakout_distance_60": FactorDefinition(
            name="breakout_distance_60",
            category="breakout",
            description="当前收盘相对 60 日前高的距离，越靠近中期突破越高。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="把 breakout 观察窗从 20 日拉到 60 日，用来区分短突破和中期趋势延续。",
        ),
        "close_location_1": FactorDefinition(
            name="close_location_1",
            category="breakout",
            description="收盘在当日高低区间中的位置，越靠近高点越高。",
            source_title="Trading Volume and Serial Correlation in Stock Returns",
            source_url="https://academic.oup.com/qje/article/108/4/905/1899978",
            source_note="bar 位置常和信息冲击、成交活跃度一起出现，这里把它单独拆出来。",
        ),
        "gap_continuation_1": FactorDefinition(
            name="gap_continuation_1",
            category="breakout",
            description="跳空幅度乘以强势收盘位置，用来刻画 gap + continuation。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="属于工程化组合因子，用来验证 gap 后强收盘是否更容易延续。",
        ),
        "ma_distance_20": FactorDefinition(
            name="ma_distance_20",
            category="breakout",
            description="收盘相对 20 日均线的偏离度。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="趋势与 pullback 常会通过 MA 偏离度来体现。",
        ),
        "ma_distance_60": FactorDefinition(
            name="ma_distance_60",
            category="breakout",
            description="收盘相对 60 日均线的偏离度，用来刻画更慢的趋势位置。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="和 20 日均线偏离一起看，可以拆出短中期趋势位置差异。",
        ),
        "ma_gap_20_60": FactorDefinition(
            name="ma_gap_20_60",
            category="breakout",
            description="20 日均线相对 60 日均线的偏离度，越大代表趋势斜率越陡。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="把价格相对均线的位置，进一步拆成均线自身的斜率结构。",
        ),
    }


def build_breakout_factor_frame(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("symbol", group_keys=False)
    prev_close = grouped["close"].shift(1)
    rolling_high_20 = grouped["high"].transform(lambda s: s.rolling(20).max().shift(1))
    rolling_high_60 = grouped["high"].transform(lambda s: s.rolling(60).max().shift(1))
    ma_20 = grouped["close"].transform(lambda s: s.rolling(20).mean())
    ma_60 = grouped["close"].transform(lambda s: s.rolling(60).mean())
    bar_range = (df["high"] - df["low"]).replace(0.0, np.nan)
    close_location = (df["close"] - df["low"]) / bar_range
    overnight_gap = df["open"] / prev_close.replace(0.0, np.nan) - 1.0
    out = df[["timestamp", "symbol"]].copy()
    out["breakout_distance_20"] = df["close"] / rolling_high_20.replace(0.0, np.nan) - 1.0
    out["breakout_distance_60"] = df["close"] / rolling_high_60.replace(0.0, np.nan) - 1.0
    out["close_location_1"] = close_location
    out["gap_continuation_1"] = overnight_gap * close_location
    out["ma_distance_20"] = df["close"] / ma_20.replace(0.0, np.nan) - 1.0
    out["ma_distance_60"] = df["close"] / ma_60.replace(0.0, np.nan) - 1.0
    out["ma_gap_20_60"] = ma_20 / ma_60.replace(0.0, np.nan) - 1.0
    return out
