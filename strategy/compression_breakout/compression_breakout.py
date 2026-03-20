# -*- coding: utf-8 -*-
"""
短线压缩突破策略。

它更适合这种场景：
- 前面已经有一点上行动能
- 最近几天波动明显收敛
- 当天放量并突破近端高点

这个思路很适合日线上的 1 到 3 天 swing continuation。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

import numpy as np
import pandas as pd

from strategy.base_strategy import BaseStrategy, StrategyResult


class CompressionBreakoutStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "compression_breakout"

    def required_columns(self) -> set[str]:
        return {"timestamp", "symbol", "open", "high", "low", "close", "volume"}

    def default_params(self) -> Dict[str, Any]:
        return {
            "breakout_window": 5,
            "compression_window": 5,
            "trend_window": 40,
            "max_vol_ratio": 0.75,
            "min_volume_surprise": 1.2,
            "close_location_min": 0.70,
            "min_price": 8.0,
            "min_avg_dollar_volume": 8_000_000.0,
            "top_k": 5,
        }

    def param_grid(self) -> Dict[str, Iterable[Any]]:
        return {
            "breakout_window": [3, 5],
            "compression_window": [3, 5],
            "trend_window": [20, 40],
            "max_vol_ratio": [0.65, 0.75],
            "min_volume_surprise": [1.1, 1.3],
            "close_location_min": [0.60, 0.70],
            "top_k": [3, 5],
        }

    def generate(self, ohlcv: pd.DataFrame, params: Dict[str, Any]) -> StrategyResult:
        self.validate_input(ohlcv)

        df = ohlcv.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

        breakout_window = int(params["breakout_window"])
        compression_window = int(params["compression_window"])
        trend_window = int(params["trend_window"])
        max_vol_ratio = float(params["max_vol_ratio"])
        min_volume_surprise = float(params["min_volume_surprise"])
        close_location_min = float(params["close_location_min"])
        min_price = float(params["min_price"])
        min_avg_dollar_volume = float(params["min_avg_dollar_volume"])
        top_k = int(params["top_k"])

        grouped = df.groupby("symbol", group_keys=False)
        bar_range = (df["high"] - df["low"]).replace(0.0, np.nan)

        df["vol_5"] = grouped["close"].transform(lambda s: s.pct_change().rolling(compression_window).std(ddof=0))
        df["vol_20"] = grouped["close"].transform(lambda s: s.pct_change().rolling(20).std(ddof=0))
        df["vol_ratio"] = df["vol_5"] / df["vol_20"].replace(0.0, np.nan)
        df["breakout_level"] = grouped["high"].transform(lambda s: s.rolling(breakout_window).max().shift(1))
        df["trend_ma"] = grouped["close"].transform(lambda s: s.rolling(trend_window).mean())
        df["momentum_5"] = grouped["close"].pct_change(5)
        df["avg_volume_20"] = grouped["volume"].transform(lambda s: s.rolling(20).mean().shift(1))
        df["volume_surprise"] = df["volume"] / df["avg_volume_20"]
        df["avg_dollar_volume"] = (df["close"] * df["volume"]).groupby(df["symbol"]).transform(
            lambda s: s.rolling(20).mean().shift(1)
        )
        df["close_location"] = (df["close"] - df["low"]) / bar_range
        df["breakout_strength"] = df["close"] / df["breakout_level"] - 1.0

        signal_mask = (
            (df["close"] >= min_price)
            & (df["avg_dollar_volume"] >= min_avg_dollar_volume)
            & (df["close"] > df["breakout_level"])
            & (df["volume_surprise"] >= min_volume_surprise)
            & (df["close_location"] >= close_location_min)
            & ((df["trend_ma"].isna()) | (df["close"] >= df["trend_ma"]))
            & ((df["momentum_5"].isna()) | (df["momentum_5"] > 0))
            & ((df["vol_ratio"].isna()) | (df["vol_ratio"] <= max_vol_ratio))
        )

        score = (
            0.35 * df["breakout_strength"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            + 0.30 * df["volume_surprise"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            + 0.20 * (1.0 - df["vol_ratio"].replace([np.inf, -np.inf], np.nan).fillna(1.0))
            + 0.15 * df["close_location"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        )

        idx = pd.MultiIndex.from_frame(df[["timestamp", "symbol"]], names=["timestamp", "symbol"])
        raw_signal = pd.Series(signal_mask.astype(int).values, index=idx, name="signal_raw")
        score_s = pd.Series(score.values, index=idx, name="score")

        tmp = pd.DataFrame({"signal_raw": raw_signal, "score": score_s})
        eligible = tmp[tmp["signal_raw"] == 1].copy()
        eligible["rank"] = eligible.groupby(level=0)["score"].rank(method="first", ascending=False)

        final_signal = pd.Series(0, index=tmp.index, dtype=int, name="signal")
        final_signal.loc[eligible[eligible["rank"] <= top_k].index] = 1
        return StrategyResult(signals=final_signal.astype(int), score=score_s)
