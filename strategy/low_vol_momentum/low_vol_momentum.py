# -*- coding: utf-8 -*-
"""
低波动动量策略。

思路很直接：
- 要求中期和长期收益率为正
- 要求价格在长期均线之上
- 优先选择波动较低、趋势更平滑的标的

这个策略通常不如突破策略“猛”，但往往更适合做稳健补充。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

import numpy as np
import pandas as pd

from strategy.base_strategy import BaseStrategy, StrategyResult


class LowVolMomentumStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "low_vol_momentum"

    def required_columns(self) -> set[str]:
        return {"timestamp", "symbol", "open", "high", "low", "close", "volume"}

    def default_params(self) -> Dict[str, Any]:
        return {
            "short_momentum_window": 20,
            "long_momentum_window": 120,
            "trend_window": 150,
            "vol_window": 20,
            "max_daily_volatility": 0.04,
            "min_price": 10.0,
            "min_avg_dollar_volume": 10_000_000.0,
            "top_k": 5,
        }

    def param_grid(self) -> Dict[str, Iterable[Any]]:
        return {
            "short_momentum_window": [20, 40],
            "long_momentum_window": [80, 120, 160],
            "trend_window": [100, 150, 200],
            "vol_window": [20, 40],
            "max_daily_volatility": [0.03, 0.04, 0.05],
            "top_k": [3, 5, 8],
        }

    def generate(self, ohlcv: pd.DataFrame, params: Dict[str, Any]) -> StrategyResult:
        self.validate_input(ohlcv)

        df = ohlcv.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

        short_window = int(params["short_momentum_window"])
        long_window = int(params["long_momentum_window"])
        trend_window = int(params["trend_window"])
        vol_window = int(params["vol_window"])
        max_daily_volatility = float(params["max_daily_volatility"])
        min_price = float(params["min_price"])
        min_avg_dollar_volume = float(params["min_avg_dollar_volume"])
        top_k = int(params["top_k"])

        grouped = df.groupby("symbol", group_keys=False)
        df["momentum_short"] = grouped["close"].pct_change(short_window)
        df["momentum_long"] = grouped["close"].pct_change(long_window)
        df["trend_ma"] = grouped["close"].transform(lambda s: s.rolling(trend_window).mean())
        df["daily_volatility"] = grouped["close"].transform(
            lambda s: s.pct_change().rolling(vol_window).std(ddof=0)
        )
        df["avg_dollar_volume"] = (df["close"] * df["volume"]).groupby(df["symbol"]).transform(
            lambda s: s.rolling(20).mean().shift(1)
        )

        signal_mask = (
            (df["close"] >= min_price)
            & (df["avg_dollar_volume"] >= min_avg_dollar_volume)
            & (df["momentum_short"] > 0)
            & (df["momentum_long"] > 0)
            & ((df["trend_ma"].isna()) | (df["close"] >= df["trend_ma"]))
            & ((df["daily_volatility"].isna()) | (df["daily_volatility"] <= max_daily_volatility))
        )

        score = (
            0.45 * df["momentum_short"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            + 0.45 * df["momentum_long"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            + 0.10 * (1.0 - df["daily_volatility"].replace([np.inf, -np.inf], np.nan).fillna(1.0))
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
