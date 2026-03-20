"""
因子基础设施模块。

这里放的是所有因子模块都会复用的基础能力：
- 因子元数据定义
- OHLCV 面板预处理
- 多个因子结果表的安全合并

它的目标是让“因子定义”和“因子实现”都保持统一口径。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

import pandas as pd


@dataclass(frozen=True)
class FactorDefinition:
    name: str
    category: str
    description: str
    source_title: str
    source_url: str
    source_note: str


def prepare_ohlcv(ohlcv: pd.DataFrame) -> pd.DataFrame:
    df = ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)


def merge_factor_frames(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    merged: pd.DataFrame | None = None
    for frame in frames:
        if merged is None:
            merged = frame.copy()
        else:
            merged = merged.merge(frame, on=["timestamp", "symbol"], how="outer")
    if merged is None:
        return pd.DataFrame(columns=["timestamp", "symbol"])
    factor_cols: List[str] = [col for col in merged.columns if col not in {"timestamp", "symbol"}]
    return merged[["timestamp", "symbol"] + factor_cols].sort_values(["timestamp", "symbol"]).reset_index(drop=True)
