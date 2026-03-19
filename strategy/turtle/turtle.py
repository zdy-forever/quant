# -*- coding: utf-8 -*-
"""
海龟交易法风格的 Donchian 突破策略。

核心思想来自经典趋势跟随：
- 价格突破过去一段时间高点才入场
- 用 ATR 和波动过滤避免过于混乱的标的
- 适合中期趋势比较干净的市场
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

import numpy as np
import pandas as pd

from strategy.base_strategy import BaseStrategy, StrategyResult


class TurtleBreakoutStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "turtle"

    def required_columns(self) -> set[str]:
        return {"timestamp", "symbol", "open", "high", "low", "close", "volume"}

    def default_params(self) -> Dict[str, Any]:
        return {
            "entry_window": 55,
            "trend_window": 120,
            "atr_window": 20,
            "max_atr_pct": 0.08,
            "min_price": 10.0,
            "min_avg_dollar_volume": 10_000_000.0,
            "top_k": 4,
        }

    def param_grid(self) -> Dict[str, Iterable[Any]]:
        return {
            "entry_window": [20, 55, 80],
            "trend_window": [80, 120, 160],
            "atr_window": [14, 20],
            "max_atr_pct": [0.05, 0.08, 0.12],
            "top_k": [3, 4, 6],
        }

    def generate(self, ohlcv: pd.DataFrame, params: Dict[str, Any]) -> StrategyResult:
        self.validate_input(ohlcv)

        df = ohlcv.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

        entry_window = int(params["entry_window"])
        trend_window = int(params["trend_window"])
        atr_window = int(params["atr_window"])
        max_atr_pct = float(params["max_atr_pct"])
        min_price = float(params["min_price"])
        min_avg_dollar_volume = float(params["min_avg_dollar_volume"])
        top_k = int(params["top_k"])

        grouped = df.groupby("symbol", group_keys=False)
        prev_close = grouped["close"].shift(1)
        tr_components = pd.concat(
            [
                (df["high"] - df["low"]).abs(),
                (df["high"] - prev_close).abs(),
                (df["low"] - prev_close).abs(),
            ],
            axis=1,
        )
        df["tr"] = tr_components.max(axis=1)
        df["atr"] = grouped["tr"].transform(lambda s: s.rolling(atr_window).mean())
        df["donchian_high"] = grouped["high"].transform(lambda s: s.rolling(entry_window).max().shift(1))
        df["trend_ma"] = grouped["close"].transform(lambda s: s.rolling(trend_window).mean())
        df["avg_dollar_volume"] = (df["close"] * df["volume"]).groupby(df["symbol"]).transform(
            lambda s: s.rolling(20).mean().shift(1)
        )
        df["atr_pct"] = df["atr"] / df["close"].replace(0.0, np.nan)
        df["momentum"] = grouped["close"].pct_change(entry_window)

        signal_mask = (
            (df["close"] >= min_price)
            & (df["avg_dollar_volume"] >= min_avg_dollar_volume)
            & (df["close"] > df["donchian_high"])
            & ((df["trend_ma"].isna()) | (df["close"] >= df["trend_ma"]))
            & ((df["atr_pct"].isna()) | (df["atr_pct"] <= max_atr_pct))
        )

        score = (
            0.5 * df["momentum"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            + 0.5 * (1.0 - df["atr_pct"].replace([np.inf, -np.inf], np.nan).fillna(1.0))
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
