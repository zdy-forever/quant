# -*- coding: utf-8 -*-
"""
趋势突破策略模块。

这个策略更适合“上涨有延续性”的市场环境，核心思路是：
- 价格突破过去一段时间高点
- 当天成交量明显放大
- 中期收益率为正，说明趋势不是随机噪声
- 用 VIX 代理过滤掉恐慌明显抬升的环境

如果你想微调趋势策略，最先看的通常是：
- `breakout_window`
- `volume_window`
- `momentum_window`
- `min_volume_ratio`
- `max_vix_ma_ratio`
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
            "trend_filter_window": 100,
            "volatility_window": 20,
            "max_daily_volatility": 0.15,
            "min_price": 10.0,
            "min_avg_dollar_volume": 5_000_000.0,
            "min_volume_ratio": 1.5,
            "use_vix_filter": True,
            "vix_symbol": "VIXY",
            "vix_window": 20,
            "max_vix_close": 0.0,
            "max_vix_ma_ratio": 1.10,
            "top_k": 5,
        }

    def param_grid(self) -> Dict[str, Iterable[Any]]:
        return {
            "breakout_window": [20, 55],
            "volume_window": [20],
            "momentum_window": [20, 60],
            "trend_filter_window": [50, 100],
            "volatility_window": [20],
            "max_daily_volatility": [0.04, 0.06, 0.08, 0.12, 0.15],
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
        trend_filter_window = int(params.get("trend_filter_window", 100))
        volatility_window = int(params.get("volatility_window", 20))
        max_daily_volatility = float(params.get("max_daily_volatility", 1.0))
        use_vix_filter = bool(params.get("use_vix_filter", True))
        vix_symbol = str(params.get("vix_symbol", "VIXY")).upper()
        vix_window = int(params.get("vix_window", 20))
        max_vix_close = float(params.get("max_vix_close", 0.0))
        max_vix_ma_ratio = float(params.get("max_vix_ma_ratio", 1.10))

        vix_col = f"ref_close_{vix_symbol}"
        trade_df = df[df["symbol"] != vix_symbol].copy()
        grouped = trade_df.groupby("symbol", group_keys=False)

        trade_df["ret_m"] = grouped["close"].pct_change(momentum_window)
        trade_df["high_breakout"] = grouped["high"].transform(
            lambda s: s.rolling(breakout_window).max().shift(1)
        )
        trade_df["avg_volume"] = grouped["volume"].transform(
            lambda s: s.rolling(volume_window).mean().shift(1)
        )
        trade_df["dollar_volume"] = trade_df["close"] * trade_df["volume"]
        grouped = trade_df.groupby("symbol", group_keys=False)
        trade_df["avg_dollar_volume"] = grouped["dollar_volume"].transform(
            lambda s: s.rolling(volume_window).mean().shift(1)
        )
        trade_df["volume_ratio"] = trade_df["volume"] / trade_df["avg_volume"]
        trade_df["trend_ma"] = grouped["close"].transform(lambda s: s.rolling(trend_filter_window).mean())
        trade_df["daily_volatility"] = grouped["close"].transform(
            lambda s: s.pct_change().rolling(volatility_window).std(ddof=0)
        )
        if use_vix_filter and vix_col in trade_df.columns:
            trade_df["vix_close"] = pd.to_numeric(trade_df[vix_col], errors="coerce")
            vix_frame = (
                trade_df[["timestamp", "vix_close"]]
                .drop_duplicates(subset=["timestamp"])
                .sort_values("timestamp")
            )
            vix_frame["vix_ma"] = vix_frame["vix_close"].rolling(vix_window).mean()
            vix_frame["vix_ma_ratio"] = vix_frame["vix_close"] / vix_frame["vix_ma"].replace(0.0, np.nan)
            trade_df = trade_df.drop(columns=["vix_close"], errors="ignore").merge(
                vix_frame,
                on="timestamp",
                how="left",
            )
        else:
            trade_df["vix_close"] = np.nan
            trade_df["vix_ma"] = np.nan
            trade_df["vix_ma_ratio"] = np.nan

        min_price = float(params.get("min_price", 0.0))
        min_avg_dollar_volume = float(params.get("min_avg_dollar_volume", 0.0))
        min_volume_ratio = float(params["min_volume_ratio"])
        top_k = int(params["top_k"])

        signal_mask = (
            (trade_df["close"] >= min_price)
            & (trade_df["avg_dollar_volume"] >= min_avg_dollar_volume)
            & (trade_df["close"] > trade_df["high_breakout"])
            & (trade_df["volume_ratio"] >= min_volume_ratio)
            & (trade_df["ret_m"] > 0)
            & ((trade_df["trend_ma"].isna()) | (trade_df["close"] >= trade_df["trend_ma"]))
            & ((trade_df["daily_volatility"].isna()) | (trade_df["daily_volatility"] <= max_daily_volatility))
        )
        if use_vix_filter:
            vix_ok = trade_df["vix_ma_ratio"].isna() | (trade_df["vix_ma_ratio"] <= max_vix_ma_ratio)
            if max_vix_close > 0:
                vix_ok &= trade_df["vix_close"].isna() | (trade_df["vix_close"] <= max_vix_close)
            signal_mask &= vix_ok

        score = (
            0.55 * trade_df["ret_m"].fillna(0.0)
            + 0.20 * trade_df["volume_ratio"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            + 0.15 * (1.0 - trade_df["daily_volatility"].replace([np.inf, -np.inf], np.nan).fillna(1.0))
            + 0.10 * (1.0 - trade_df["vix_ma_ratio"].replace([np.inf, -np.inf], np.nan).fillna(1.0))
        )

        idx = pd.MultiIndex.from_frame(
            trade_df[["timestamp", "symbol"]],
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
