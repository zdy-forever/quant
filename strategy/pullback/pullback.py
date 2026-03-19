# -*- coding: utf-8 -*-
"""
顺势回撤策略模块。

核心思路：
- 先要求标的处于中长期上升趋势
- 再等待短期回撤，而不是追当天最强突破
- 只在出现轻微反弹确认时入场

它介于趋势突破和均值回归之间：
- 比 breakout 更克制
- 比纯抄底更安全
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

import numpy as np
import pandas as pd

from strategy.base_strategy import BaseStrategy, StrategyResult


class PullbackMomentumStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "pullback"

    def required_columns(self) -> set[str]:
        return {"timestamp", "symbol", "open", "high", "low", "close", "volume"}

    def default_params(self) -> Dict[str, Any]:
        return {
            "trend_window": 100,
            "momentum_window": 60,
            "pullback_window": 10,
            "entry_z": 1.0,
            "min_price": 10.0,
            "min_avg_dollar_volume": 10_000_000.0,
            "require_rebound_bar": True,
            "top_k": 3,
        }

    def param_grid(self) -> Dict[str, Iterable[Any]]:
        return {
            "trend_window": [80, 100, 150],
            "momentum_window": [40, 60, 90],
            "pullback_window": [5, 10, 15],
            "entry_z": [0.8, 1.0, 1.2, 1.5],
            "require_rebound_bar": [True, False],
            "top_k": [2, 3, 5],
        }

    def generate(self, ohlcv: pd.DataFrame, params: Dict[str, Any]) -> StrategyResult:
        self.validate_input(ohlcv)

        df = ohlcv.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

        trend_window = int(params.get("trend_window", 100))
        momentum_window = int(params.get("momentum_window", 60))
        pullback_window = int(params.get("pullback_window", 10))
        entry_z = float(params.get("entry_z", 1.0))
        min_price = float(params.get("min_price", 0.0))
        min_avg_dollar_volume = float(params.get("min_avg_dollar_volume", 0.0))
        require_rebound_bar = bool(params.get("require_rebound_bar", True))
        top_k = int(params.get("top_k", 3))

        grouped = df.groupby("symbol", group_keys=False)
        df["trend_ma"] = grouped["close"].transform(lambda s: s.rolling(trend_window).mean())
        df["trend_ret"] = grouped["close"].pct_change(momentum_window)
        df["pullback_ma"] = grouped["close"].transform(lambda s: s.rolling(pullback_window).mean())
        df["pullback_std"] = grouped["close"].transform(
            lambda s: s.rolling(pullback_window).std(ddof=0).replace(0.0, np.nan)
        )
        df["pullback_z"] = (df["close"] - df["pullback_ma"]) / df["pullback_std"]
        df["avg_dollar_volume"] = (df["close"] * df["volume"]).groupby(df["symbol"]).transform(
            lambda s: s.rolling(20).mean().shift(1)
        )
        df["rebound_bar"] = grouped["close"].transform(lambda s: s > s.shift(1))

        signal_mask = (
            (df["close"] >= min_price)
            & (df["avg_dollar_volume"] >= min_avg_dollar_volume)
            & ((df["trend_ma"].isna()) | (df["close"] >= df["trend_ma"]))
            & ((df["trend_ret"].isna()) | (df["trend_ret"] > 0))
            & (df["pullback_z"] <= -entry_z)
        )
        if require_rebound_bar:
            signal_mask &= (df["rebound_bar"].isna()) | df["rebound_bar"]

        score = (
            0.5 * (-df["pullback_z"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
            + 0.5 * df["trend_ret"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        )

        idx = pd.MultiIndex.from_frame(df[["timestamp", "symbol"]], names=["timestamp", "symbol"])
        raw_signal = pd.Series(signal_mask.astype(int).values, index=idx, name="signal_raw")
        score_s = pd.Series(score.values, index=idx, name="score")

        tmp = pd.DataFrame({"signal_raw": raw_signal, "score": score_s})
        eligible = tmp[tmp["signal_raw"] == 1].copy()
        eligible["rank"] = eligible.groupby(level=0)["score"].rank(method="first", ascending=False)

        final_signal = pd.Series(0, index=tmp.index, dtype=int, name="signal")
        chosen_idx = eligible[eligible["rank"] <= top_k].index
        final_signal.loc[chosen_idx] = 1

        return StrategyResult(signals=final_signal.astype(int), score=score_s)
