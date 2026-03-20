# -*- coding: utf-8 -*-
"""
短线多因子选股策略。

这条策略直接把多个适合短线的 OHLCV 因子组合起来：
- 短期反转
- 波动/振幅冲击
- 放量
- 偏离均线后的反抽空间
- 偏离近端高点后的回归空间

如果你之后想继续做“多因子模型”，最值得优先读的就是这个文件。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

import numpy as np
import pandas as pd

from alpha_lab.factors import build_alpha_factor_panel
from strategy.base_strategy import BaseStrategy, StrategyResult

_MERGED_FACTOR_CACHE: Dict[int, pd.DataFrame] = {}


class MultiFactorShortStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "multi_factor_short"

    def required_columns(self) -> set[str]:
        return {"timestamp", "symbol", "open", "high", "low", "close", "volume"}

    def default_params(self) -> Dict[str, Any]:
        return {
            "min_price": 8.0,
            "min_avg_dollar_volume": 5_000_000.0,
            "max_gap_abs": 0.10,
            "max_true_range_pct": 0.18,
            "require_above_ma20": False,
            "score_threshold": 0.00,
            "top_k": 10,
        }

    def param_grid(self) -> Dict[str, Iterable[Any]]:
        return {
            "max_gap_abs": [0.08, 0.10],
            "max_true_range_pct": [0.12, 0.18],
            "require_above_ma20": [False, True],
            "score_threshold": [-0.05, 0.05],
            "top_k": [8, 10],
        }

    def generate(self, ohlcv: pd.DataFrame, params: Dict[str, Any]) -> StrategyResult:
        self.validate_input(ohlcv)
        cache_key = id(ohlcv)
        cached = _MERGED_FACTOR_CACHE.get(cache_key)
        if cached is None:
            base = ohlcv.copy()
            base["timestamp"] = pd.to_datetime(base["timestamp"], utc=True)
            base = base.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

            factor_panel = build_alpha_factor_panel(base)
            cached = base.merge(
                factor_panel.drop(columns=["close"]),
                on=["timestamp", "symbol"],
                how="left",
            )
            _MERGED_FACTOR_CACHE[cache_key] = cached
        df = cached.copy()

        min_price = float(params["min_price"])
        min_avg_dollar_volume = float(params["min_avg_dollar_volume"])
        max_gap_abs = float(params["max_gap_abs"])
        max_true_range_pct = float(params["max_true_range_pct"])
        require_above_ma20 = bool(params["require_above_ma20"])
        score_threshold = float(params["score_threshold"])
        top_k = int(params["top_k"])

        def _cross_section_zscore(series: pd.Series) -> pd.Series:
            return (series - series.mean()) / (series.std(ddof=0) + 1e-12)

        score_cols = {
            "short_reversal_3": 0.25,
            "short_reversal_5": 0.20,
            "true_range_pct_1": 0.15,
            "volume_surprise_20": 0.10,
            "close_vs_ma5": -0.15,
            "breakout_distance_5": -0.10,
            "close_location_1": -0.05,
        }

        weighted_parts = []
        for col, weight in score_cols.items():
            part = df.groupby("timestamp")[col].transform(_cross_section_zscore)
            weighted_parts.append(weight * part.fillna(0.0))
        df["score"] = sum(weighted_parts)

        signal_mask = (
            (df["close"] >= min_price)
            & (df["liquidity_20"] >= np.log(min_avg_dollar_volume))
            & (df["overnight_gap_1"].abs() <= max_gap_abs)
            & (df["true_range_pct_1"] <= max_true_range_pct)
            & (df["intraday_return_1"] > -0.05)
            & (df["score"] >= score_threshold)
        )
        if require_above_ma20:
            signal_mask &= (df["close_vs_ma20"].isna()) | (df["close_vs_ma20"] >= -0.02)

        idx = pd.MultiIndex.from_frame(df[["timestamp", "symbol"]], names=["timestamp", "symbol"])
        raw_signal = pd.Series(signal_mask.astype(int).values, index=idx, name="signal_raw")
        score_s = pd.Series(df["score"].values, index=idx, name="score")

        tmp = pd.DataFrame({"signal_raw": raw_signal, "score": score_s})
        eligible = tmp[tmp["signal_raw"] == 1].copy()
        eligible["rank"] = eligible.groupby(level=0)["score"].rank(method="first", ascending=False)

        final_signal = pd.Series(0, index=tmp.index, dtype=int, name="signal")
        final_signal.loc[eligible[eligible["rank"] <= top_k].index] = 1
        return StrategyResult(signals=final_signal.astype(int), score=score_s)
