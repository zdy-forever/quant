# -*- coding: utf-8 -*-
"""
趋势突破策略模块。

这个策略更适合“上涨有延续性”的市场环境，核心思路是：
- 价格突破过去一段时间高点
- 当天成交量明显放大
- 中期收益率为正，说明趋势不是随机噪声

如果你想微调趋势策略，最先看的通常是：
- `breakout_window`
- `volume_window`
- `momentum_window`
- `min_volume_ratio`
- `top_k`
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

import numpy as np
import pandas as pd

from strategy.base_strategy import BaseStrategy, StrategyResult


class TrendBreakoutStrategy(BaseStrategy):
    """
    趋势突破策略。

    核心逻辑与当前仓库现有扫描逻辑保持一致：
    - 突破过去 N 日最高价（不含今天）
    - 成交量放大
    - 中期动量为正
    """

    @property
    def name(self) -> str:
        return "trend"

    def required_columns(self) -> set[str]:
        return {"timestamp", "symbol", "open", "high", "low", "close", "volume"}

    def default_params(self) -> Dict[str, Any]:
        return {
            "breakout_window": 20,
            "volume_window": 20,
            "momentum_window": 20,
            "min_price": 10.0,
            "min_avg_dollar_volume": 5_000_000.0,
            "min_volume_ratio": 1.5,
            "top_k": 5,
        }

    def param_grid(self) -> Dict[str, Iterable[Any]]:
        return {
            "breakout_window": [20, 55],
            "volume_window": [20],
            "momentum_window": [20, 60],
            "min_volume_ratio": [1.2, 1.5, 2.0],
            "top_k": [3, 5],
        }

    def generate(self, ohlcv: pd.DataFrame, params: Dict[str, Any]) -> StrategyResult:
        self.validate_input(ohlcv)

        df = ohlcv.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

        breakout_window = int(params["breakout_window"])
        volume_window = int(params["volume_window"])
        momentum_window = int(params["momentum_window"])

        def _calc(group: pd.DataFrame) -> pd.DataFrame:
            group = group.copy()
            group["ret_m"] = group["close"].pct_change(momentum_window)
            group["high_breakout"] = group["high"].rolling(breakout_window).max().shift(1)
            group["avg_volume"] = group["volume"].rolling(volume_window).mean().shift(1)
            group["avg_dollar_volume"] = (
                (group["close"] * group["volume"]).rolling(volume_window).mean().shift(1)
            )
            group["volume_ratio"] = group["volume"] / group["avg_volume"]
            return group

        df = df.groupby("symbol", group_keys=False).apply(_calc)

        min_price = float(params.get("min_price", 0.0))
        min_avg_dollar_volume = float(params.get("min_avg_dollar_volume", 0.0))
        min_volume_ratio = float(params["min_volume_ratio"])
        top_k = int(params["top_k"])

        signal_mask = (
            (df["close"] >= min_price)
            & (df["avg_dollar_volume"] >= min_avg_dollar_volume)
            & (df["close"] > df["high_breakout"])
            & (df["volume_ratio"] >= min_volume_ratio)
            & (df["ret_m"] > 0)
        )

        score = (
            0.7 * df["ret_m"].fillna(0.0)
            + 0.3 * df["volume_ratio"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        )

        idx = pd.MultiIndex.from_frame(
            df[["timestamp", "symbol"]],
            names=["timestamp", "symbol"],
        )
        raw_signal = pd.Series(signal_mask.astype(int).values, index=idx, name="signal_raw")
        score_s = pd.Series(score.values, index=idx, name="score")

        tmp = pd.DataFrame({"signal_raw": raw_signal, "score": score_s})
        eligible = tmp[tmp["signal_raw"] == 1].copy()
        eligible["rank"] = eligible.groupby(level=0)["score"].rank(method="first", ascending=False)

        final_signal = pd.Series(0, index=tmp.index, dtype=int, name="signal")
        chosen_idx = eligible[eligible["rank"] <= top_k].index
        final_signal.loc[chosen_idx] = 1

        return StrategyResult(signals=final_signal.astype(int), score=score_s)
