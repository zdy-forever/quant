"""
趋势质量类因子模块。

这组因子不只是问“涨了多少”，还会问：
- 这段趋势有没有刻意避开最近几天的噪音
- 趋势走得顺不顺
- 同样的涨幅，承担了多少波动
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from factors.base import FactorDefinition


def trend_quality_factor_definitions() -> Dict[str, FactorDefinition]:
    return {
        "momentum_120_skip_5": FactorDefinition(
            name="momentum_120_skip_5",
            category="trend_quality",
            description="跳过最近 5 日后的 120 日动量，用来降低短期反转噪音。",
            source_title="Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency",
            source_url="https://doi.org/10.1111/j.1540-6261.1993.tb04702.x",
            source_note="经典 12-1 动量思路在日线上的简化实现，尽量避免把最近几天的噪音也算进趋势。",
        ),
        "trend_consistency_20": FactorDefinition(
            name="trend_consistency_20",
            category="trend_quality",
            description="过去 20 日上涨天数占比映射到 [-1, 1]，越大代表趋势越平滑。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="把趋势延续拆成“总涨跌幅”和“路径是否平滑”两个维度。",
        ),
        "efficiency_ratio_20": FactorDefinition(
            name="efficiency_ratio_20",
            category="trend_quality",
            description="20 日净位移相对路径总波动的效率比，越大代表趋势更干净。",
            source_title="Adaptive Moving Averages",
            source_url="https://technical.traders.com/tradersonline/display.asp?art=302",
            source_note="Kaufman efficiency ratio 的横截面化实现，用来衡量趋势信号质量。",
        ),
        "risk_adjusted_momentum_60": FactorDefinition(
            name="risk_adjusted_momentum_60",
            category="trend_quality",
            description="60 日动量除以 20 日波动缩放后的风险调整趋势强度。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="工程化的风险调整动量 proxy，避免只偏好高波动强弹的名字。",
        ),
    }


def build_trend_quality_factor_frame(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("symbol", group_keys=False)
    out = df[["timestamp", "symbol"]].copy()
    daily_ret = grouped["close"].pct_change()
    momentum_20 = grouped["close"].pct_change(20)
    momentum_60 = grouped["close"].pct_change(60)
    abs_ret_sum_20 = daily_ret.abs().groupby(df["symbol"]).transform(lambda s: s.rolling(20).sum())
    positive_ratio_20 = daily_ret.gt(0).groupby(df["symbol"]).transform(lambda s: s.rolling(20).mean())
    vol_20 = daily_ret.groupby(df["symbol"]).transform(lambda s: s.rolling(20).std(ddof=0))

    out["momentum_120_skip_5"] = grouped["close"].shift(5) / grouped["close"].shift(125).replace(0.0, np.nan) - 1.0
    out["trend_consistency_20"] = 2.0 * positive_ratio_20 - 1.0
    out["efficiency_ratio_20"] = momentum_20.abs() / abs_ret_sum_20.replace(0.0, np.nan)
    out["risk_adjusted_momentum_60"] = momentum_60 / (vol_20 * np.sqrt(60.0)).replace(0.0, np.nan)
    return out
