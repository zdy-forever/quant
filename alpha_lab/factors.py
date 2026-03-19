# -*- coding: utf-8 -*-
"""
Alpha 因子定义模块。

这里的因子都只使用 OHLCV，可以在没有基本面数据库的前提下先做起步研究。
如果你以后接入财报、估值、分析师预期等数据，可以继续往这里扩展。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_alpha_factor_panel(ohlcv: pd.DataFrame) -> pd.DataFrame:
    df = ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

    grouped = df.groupby("symbol", group_keys=False)
    df["ret_5"] = grouped["close"].pct_change(5)
    df["ret_20"] = grouped["close"].pct_change(20)
    df["ret_60"] = grouped["close"].pct_change(60)
    df["vol_20"] = grouped["close"].transform(lambda s: s.pct_change().rolling(20).std(ddof=0))
    df["ma_20"] = grouped["close"].transform(lambda s: s.rolling(20).mean())
    df["ma_60"] = grouped["close"].transform(lambda s: s.rolling(60).mean())
    df["high_20"] = grouped["high"].transform(lambda s: s.rolling(20).max().shift(1))
    df["low_20"] = grouped["low"].transform(lambda s: s.rolling(20).min().shift(1))
    df["avg_volume_20"] = grouped["volume"].transform(lambda s: s.rolling(20).mean().shift(1))

    range_width = (df["high_20"] - df["low_20"]).replace(0.0, np.nan)
    factor_df = df[["timestamp", "symbol", "close"]].copy()
    factor_df["momentum_20"] = df["ret_20"]
    factor_df["momentum_60"] = df["ret_60"]
    factor_df["short_reversal_5"] = -df["ret_5"]
    factor_df["low_volatility_20"] = -df["vol_20"]
    factor_df["close_vs_ma20"] = df["close"] / df["ma_20"] - 1.0
    factor_df["close_vs_ma60"] = df["close"] / df["ma_60"] - 1.0
    factor_df["breakout_distance_20"] = df["close"] / df["high_20"] - 1.0
    factor_df["range_position_20"] = (df["close"] - df["low_20"]) / range_width
    factor_df["volume_surprise_20"] = df["volume"] / df["avg_volume_20"]
    factor_df = factor_df.replace([np.inf, -np.inf], np.nan)
    return factor_df
