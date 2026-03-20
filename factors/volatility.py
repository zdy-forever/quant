"""
波动与压缩类因子模块。

这条线主要服务两个研究问题：
- 低波动股票在横截面上是否更稳
- 波动压缩之后是否更容易出现后续趋势延续

这类因子常常更像“背景条件”，但仍然值得先单独做 alpha 验证。
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from factors.base import FactorDefinition


def volatility_factor_definitions() -> Dict[str, FactorDefinition]:
    return {
        "low_volatility_20": FactorDefinition(
            name="low_volatility_20",
            category="volatility",
            description="过去 20 日收益波动率取负号，值越大代表越低波。",
            source_title="Low-Risk Alpha Without Low Beta",
            source_url="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5005746",
            source_note="低风险异常主线，工程上使用 20 日滚动波动率代理。",
        ),
        "vol_compression_10_40": FactorDefinition(
            name="vol_compression_10_40",
            category="volatility",
            description="10 日 ATR 相对 40 日 ATR 的压缩程度，值越大代表越压缩。",
            source_title="Low-Risk Alpha Without Low Beta",
            source_url="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5005746",
            source_note="更偏工程化的波动压缩 proxy，用来承接 breakout / pullback 研究。",
        ),
        "true_range_pct_1": FactorDefinition(
            name="true_range_pct_1",
            category="volatility",
            description="当日真实波幅占前收盘比重，用来度量单日振幅冲击。",
            source_title="Trading Volume and Serial Correlation in Stock Returns",
            source_url="https://academic.oup.com/qje/article/108/4/905/1899978",
            source_note="高波动与高交易活跃度往往一起出现，这里把单日振幅单独抽出来做检验。",
        ),
    }


def build_volatility_factor_frame(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("symbol", group_keys=False)
    prev_close = grouped["close"].shift(1)
    true_range = pd.concat(
        [
            (df["high"] - df["low"]).abs(),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_10 = true_range.groupby(df["symbol"]).transform(lambda s: s.rolling(10).mean())
    atr_40 = true_range.groupby(df["symbol"]).transform(lambda s: s.rolling(40).mean())
    out = df[["timestamp", "symbol"]].copy()
    out["low_volatility_20"] = -grouped["close"].transform(lambda s: s.pct_change().rolling(20).std(ddof=0))
    out["vol_compression_10_40"] = -(atr_10 / atr_40.replace(0.0, np.nan))
    out["true_range_pct_1"] = true_range / prev_close.replace(0.0, np.nan)
    return out
