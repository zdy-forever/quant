"""
反转类因子模块。

这类因子更贴近短线交易风格：
- 先找最近几天跌得比较急的股票
- 再看这些超跌股票后面是否更容易反抽

和策略不同，这里只输出“超跌程度”的分数，不直接决定买卖。
"""
from __future__ import annotations

from typing import Dict

import pandas as pd

from factors.base import FactorDefinition


def reversal_factor_definitions() -> Dict[str, FactorDefinition]:
    return {
        "reversal_3": FactorDefinition(
            name="reversal_3",
            category="reversal",
            description="过去 3 日收益率取负号，值越大代表短期越超跌。",
            source_title="Fads, Martingales, and Market Efficiency",
            source_url="https://www.nber.org/papers/w2533",
            source_note="Lehmann 的短期反转文献线，工程上用 3 日窗口做更贴近 swing 的 proxy。",
        ),
        "reversal_5": FactorDefinition(
            name="reversal_5",
            category="reversal",
            description="过去 5 日收益率取负号，值越大代表短期越超跌。",
            source_title="Fads, Martingales, and Market Efficiency",
            source_url="https://www.nber.org/papers/w2533",
            source_note="短期反转核心 proxy，后续会在横截面里排序验证。",
        ),
    }


def build_reversal_factor_frame(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("symbol", group_keys=False)
    out = df[["timestamp", "symbol"]].copy()
    out["reversal_3"] = -grouped["close"].pct_change(3)
    out["reversal_5"] = -grouped["close"].pct_change(5)
    return out
