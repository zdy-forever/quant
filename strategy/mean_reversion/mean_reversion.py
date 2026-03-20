# -*- coding: utf-8 -*-
"""
均值回归策略模块。

这个策略更适合“价格短期偏离后回归均值”的环境，核心思路是：
- 用滚动均值和标准差估计当前价格是否超卖
- 如果 z-score 很低，就把它视为潜在反弹候选
- 加上更短周期、更贴近 swing 的过滤条件
- 每天只保留分数最高的少量标的

如果你以后想让策略更激进或更保守，最常改的是：
- `lookback`
- `entry_z`
- `top_k`
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

import numpy as np
import pandas as pd

from strategy.base_strategy import BaseStrategy, StrategyResult


class MeanReversionBollingerStrategy(BaseStrategy):
    """均值回归策略，提供超卖入场候选。"""

    @property
    def name(self) -> str:
        return "mean_reversion"

    def required_columns(self) -> set[str]:
        return {"timestamp", "symbol", "open", "high", "low", "close", "volume"}

    def default_params(self) -> Dict[str, Any]:
        return {
            "lookback": 7,
            "entry_z": 1.2,
            "exit_z": 0.0,
            "min_price": 8.0,
            "min_avg_dollar_volume": 5_000_000.0,
            "trend_window": 40,
            "require_above_trend_ma": False,
            "require_positive_trend_return": False,
            "require_rebound_bar": True,
            "close_location_min": 0.45,
            "min_volume_surprise": 0.8,
            "max_gap_down": 0.10,
            "top_k": 8,
        }

    def param_grid(self) -> Dict[str, Iterable[Any]]:
        return {
            "lookback": [5, 7],
            "entry_z": [1.0, 1.4],
            "exit_z": [0.0],
            "trend_window": [20, 40],
            "require_above_trend_ma": [False],
            "require_positive_trend_return": [False],
            "require_rebound_bar": [True],
            "close_location_min": [0.45, 0.60],
            "min_volume_surprise": [0.8, 1.1],
            "max_gap_down": [0.08, 0.10],
            "top_k": [5, 8],
        }

    def generate(self, ohlcv: pd.DataFrame, params: Dict[str, Any]) -> StrategyResult:
        self.validate_input(ohlcv)

        df = ohlcv.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

        lookback = int(params["lookback"])
        entry_z = float(params["entry_z"])
        min_price = float(params.get("min_price", 0.0))
        min_avg_dollar_volume = float(params.get("min_avg_dollar_volume", 0.0))
        trend_window = int(params.get("trend_window", 100))
        require_above_trend_ma = bool(params.get("require_above_trend_ma", False))
        require_positive_trend_return = bool(params.get("require_positive_trend_return", False))
        require_rebound_bar = bool(params.get("require_rebound_bar", False))
        close_location_min = float(params.get("close_location_min", 0.60))
        min_volume_surprise = float(params.get("min_volume_surprise", 1.0))
        max_gap_down = float(params.get("max_gap_down", 0.08))
        top_k = int(params.get("top_k", 5))

        grouped = df.groupby("symbol", group_keys=False)
        prev_close = grouped["close"].shift(1)
        bar_range = (df["high"] - df["low"]).replace(0.0, np.nan)
        ma = grouped["close"].transform(lambda s: s.rolling(lookback).mean())
        std = grouped["close"].transform(
            lambda s: s.rolling(lookback).std(ddof=0).replace(0.0, np.nan)
        )
        trend_ma = grouped["close"].transform(lambda s: s.rolling(trend_window).mean())
        trend_ret = grouped["close"].pct_change(trend_window)
        avg_dollar_volume = (df["close"] * df["volume"])
        avg_dollar_volume = avg_dollar_volume.groupby(df["symbol"]).transform(
            lambda s: s.rolling(20).mean().shift(1)
        )
        avg_volume = grouped["volume"].transform(lambda s: s.rolling(5).mean().shift(1))
        rebound_bar = grouped["close"].transform(lambda s: s > s.shift(1))

        df["z"] = (df["close"] - ma) / std
        df["trend_ma"] = trend_ma
        df["trend_ret"] = trend_ret
        df["avg_dollar_volume"] = avg_dollar_volume
        df["volume_surprise"] = df["volume"] / avg_volume
        df["rebound_bar"] = rebound_bar
        df["close_location"] = (df["close"] - df["low"]) / bar_range
        df["gap_down"] = -(df["open"] / prev_close - 1.0)

        entry = (
            (df["z"] < -entry_z)
            & (df["close"] >= min_price)
            & (df["avg_dollar_volume"] >= min_avg_dollar_volume)
            & (df["volume_surprise"] >= min_volume_surprise)
            & (df["close_location"] >= close_location_min)
            & (df["gap_down"].isna() | (df["gap_down"] <= max_gap_down))
        )
        if require_above_trend_ma:
            entry &= (df["trend_ma"].isna()) | (df["close"] >= df["trend_ma"])
        if require_positive_trend_return:
            entry &= (df["trend_ret"].isna()) | (df["trend_ret"] > 0)
        if require_rebound_bar:
            entry &= (df["rebound_bar"].isna()) | (df["rebound_bar"])

        score = (
            0.45 * (-df["z"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
            + 0.20 * df["close_location"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            + 0.20 * df["volume_surprise"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            + 0.15 * df["trend_ret"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        )

        idx = pd.MultiIndex.from_frame(
            df[["timestamp", "symbol"]],
            names=["timestamp", "symbol"],
        )
        entry_s = pd.Series(entry.astype(int).values, index=idx, name="entry")
        score_s = pd.Series(score.values, index=idx, name="score")

        tmp = pd.DataFrame({"entry": entry_s, "score": score_s})
        eligible = tmp[tmp["entry"] == 1].copy()
        eligible["rank"] = eligible.groupby(level=0)["score"].rank(method="first", ascending=False)

        final_signal = pd.Series(0, index=tmp.index, dtype=int, name="signal")
        chosen_idx = eligible[eligible["rank"] <= top_k].index
        final_signal.loc[chosen_idx] = 1

        return StrategyResult(signals=final_signal.astype(int), score=score_s)
