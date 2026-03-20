"""
成交量与流动性类因子模块。

这条线重点研究：
- 放量是不是后续收益的确认信号
- 当前交易活跃度相对自己的历史基线有没有异常
- 流动性过滤本身是否会改变因子效果
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from factors.base import FactorDefinition


def volume_factor_definitions() -> Dict[str, FactorDefinition]:
    return {
        "volume_surprise_5": FactorDefinition(
            name="volume_surprise_5",
            category="volume",
            description="今日成交量相对过去 5 日均量的放大量级。",
            source_title="Price Momentum and Trading Volume",
            source_url="https://www.jstor.org/stable/222483",
            source_note="Lee 与 Swaminathan 的价格-成交量文献线，工程上用 volume spike 做简化 proxy。",
        ),
        "turnover_shock_20": FactorDefinition(
            name="turnover_shock_20",
            category="volume",
            description="今日成交额相对 20 日平均成交额的异常程度。",
            source_title="Price Momentum and Trading Volume",
            source_url="https://www.jstor.org/stable/222483",
            source_note="把 volume anomaly 转成更稳的 dollar turnover shock。",
        ),
        "liquidity_20": FactorDefinition(
            name="liquidity_20",
            category="volume",
            description="20 日平均成交额取对数，用来刻画可交易性和流动性层级。",
            source_title="Price Momentum and Trading Volume",
            source_url="https://www.jstor.org/stable/222483",
            source_note="严格说更像 universe / filter，但也值得单独做横截面检验。",
        ),
    }


def build_volume_factor_frame(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("symbol", group_keys=False)
    dollar_volume = df["close"] * df["volume"]
    avg_volume_5 = grouped["volume"].transform(lambda s: s.rolling(5).mean().shift(1))
    avg_dollar_volume_20 = dollar_volume.groupby(df["symbol"]).transform(lambda s: s.rolling(20).mean().shift(1))
    out = df[["timestamp", "symbol"]].copy()
    out["volume_surprise_5"] = df["volume"] / avg_volume_5.replace(0.0, np.nan)
    out["turnover_shock_20"] = dollar_volume / avg_dollar_volume_20.replace(0.0, np.nan)
    out["liquidity_20"] = np.log(avg_dollar_volume_20.clip(lower=1.0))
    return out
