# -*- coding: utf-8 -*-
"""
均值回归策略模块。

这个策略更适合“价格短期偏离后回归均值”的环境，核心思路是：
- 用滚动均值和标准差估计当前价格是否超卖
- 如果 z-score 很低，就把它视为潜在反弹候选
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
            "lookback": 20,
            "entry_z": 2.0,
            "exit_z": 0.5,
            "min_price": 5.0,
            "top_k": 5,
        }

    def param_grid(self) -> Dict[str, Iterable[Any]]:
        return {
            "lookback": [10, 20, 40],
            "entry_z": [1.5, 2.0, 2.5],
            "exit_z": [0.0, 0.5, 1.0],
            "top_k": [3, 5],
        }

    def generate(self, ohlcv: pd.DataFrame, params: Dict[str, Any]) -> StrategyResult:
        self.validate_input(ohlcv)

        df = ohlcv.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

        lookback = int(params["lookback"])
        entry_z = float(params["entry_z"])
        min_price = float(params.get("min_price", 0.0))
        top_k = int(params.get("top_k", 5))

        def _calc(group: pd.DataFrame) -> pd.DataFrame:
            group = group.copy()
            ma = group["close"].rolling(lookback).mean()
            std = group["close"].rolling(lookback).std(ddof=0).replace(0.0, np.nan)
            group["z"] = (group["close"] - ma) / std
            return group

        df = df.groupby("symbol", group_keys=False).apply(_calc)

        entry = (df["z"] < -entry_z) & (df["close"] >= min_price)
        score = (-df["z"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)

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
