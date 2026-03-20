# -*- coding: utf-8 -*-
"""
短线反转 swing 策略。

这条策略是给“1 到 3 天可能有几次交易”的风格准备的，核心思路是：
- 先找最近几天跌得比较急的股票
- 再要求当天出现反抽确认，而不是继续阴跌
- 最后加上流动性、量能和趋势过滤，尽量避免接飞刀
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

import numpy as np
import pandas as pd

from strategy.base_strategy import BaseStrategy, StrategyResult


class ShortReversalSwingStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "short_reversal"

    def required_columns(self) -> set[str]:
        return {"timestamp", "symbol", "open", "high", "low", "close", "volume"}

    def default_params(self) -> Dict[str, Any]:
        return {
            "drop_window": 3,
            "min_drop": -0.03,
            "trend_window": 40,
            "min_volume_surprise": 0.8,
            "close_location_min": 0.55,
            "max_gap_down": 0.10,
            "min_price": 8.0,
            "min_avg_dollar_volume": 5_000_000.0,
            "top_k": 8,
        }

    def param_grid(self) -> Dict[str, Iterable[Any]]:
        return {
            "drop_window": [2, 3],
            "min_drop": [-0.02, -0.04],
            "trend_window": [20, 40],
            "min_volume_surprise": [0.8, 1.1],
            "close_location_min": [0.45, 0.60],
            "max_gap_down": [0.08, 0.10],
            "top_k": [5, 8],
        }

    def generate(self, ohlcv: pd.DataFrame, params: Dict[str, Any]) -> StrategyResult:
        self.validate_input(ohlcv)

        df = ohlcv.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

        drop_window = int(params["drop_window"])
        min_drop = float(params["min_drop"])
        trend_window = int(params["trend_window"])
        min_volume_surprise = float(params["min_volume_surprise"])
        close_location_min = float(params["close_location_min"])
        max_gap_down = float(params["max_gap_down"])
        min_price = float(params["min_price"])
        min_avg_dollar_volume = float(params["min_avg_dollar_volume"])
        top_k = int(params["top_k"])

        grouped = df.groupby("symbol", group_keys=False)
        prev_close = grouped["close"].shift(1)
        bar_range = (df["high"] - df["low"]).replace(0.0, np.nan)

        df["ret_drop"] = grouped["close"].pct_change(drop_window)
        df["trend_ma"] = grouped["close"].transform(lambda s: s.rolling(trend_window).mean())
        df["avg_volume_5"] = grouped["volume"].transform(lambda s: s.rolling(5).mean().shift(1))
        df["volume_surprise"] = df["volume"] / df["avg_volume_5"]
        df["avg_dollar_volume"] = (df["close"] * df["volume"]).groupby(df["symbol"]).transform(
            lambda s: s.rolling(20).mean().shift(1)
        )
        df["close_location"] = (df["close"] - df["low"]) / bar_range
        df["gap_down"] = -(df["open"] / prev_close - 1.0)
        df["rebound_bar"] = df["close"] > df["open"]
        df["trend_buffer"] = df["close"] / df["trend_ma"] - 1.0

        signal_mask = (
            (df["close"] >= min_price)
            & (df["avg_dollar_volume"] >= min_avg_dollar_volume)
            & (df["ret_drop"] <= min_drop)
            & (df["volume_surprise"] >= min_volume_surprise)
            & (df["close_location"] >= close_location_min)
            & (df["gap_down"].isna() | (df["gap_down"] <= max_gap_down))
            & (df["rebound_bar"])
            & (df["trend_ma"].isna() | (df["trend_buffer"] >= -0.08))
        )

        score = (
            0.40 * (-df["ret_drop"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
            + 0.25 * df["close_location"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            + 0.20 * df["volume_surprise"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            + 0.15 * df["trend_buffer"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
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
