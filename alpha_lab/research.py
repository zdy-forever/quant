# -*- coding: utf-8 -*-
"""
Alpha 因子研究主模块。

它会完成一整套常见的因子研究流程：
- 算 forward return
- 做 IC / Rank IC
- 做 IC decay
- 做 Quantile test
- 选出有效因子
- 合成组合因子
- 用组合因子做 top-N 股票组合回测
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from alpha_lab.factors import build_alpha_factor_panel
from backtest.engine import BacktestConfig, run_signal_backtest


@dataclass(frozen=True)
class AlphaResearchConfig:
    forward_days: List[int] = field(default_factory=lambda: [1, 5, 10, 20])
    quantiles: int = 5
    top_n: int = 10
    min_ic: float = 0.02
    min_rank_ic: float = 0.03
    backtest: BacktestConfig = field(default_factory=lambda: BacktestConfig(max_positions=10))


def _cross_sectional_corr(one_day: pd.DataFrame, factor_name: str, ret_name: str, method: str) -> float:
    sample = one_day[[factor_name, ret_name]].dropna()
    if sample.shape[0] < 5:
        return np.nan
    if method == "spearman":
        ranked_factor = sample[factor_name].rank(method="average")
        ranked_return = sample[ret_name].rank(method="average")
        return float(ranked_factor.corr(ranked_return, method="pearson"))
    return float(sample[factor_name].corr(sample[ret_name], method=method))


def _build_forward_returns(ohlcv: pd.DataFrame, horizons: List[int]) -> pd.DataFrame:
    df = ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    grouped = df.groupby("symbol", group_keys=False)

    out = df[["timestamp", "symbol", "close"]].copy()
    for horizon in horizons:
        out[f"fwd_ret_{horizon}"] = grouped["close"].shift(-horizon) / df["close"] - 1.0
    return out


def _factor_names(factor_panel: pd.DataFrame) -> List[str]:
    return [col for col in factor_panel.columns if col not in {"timestamp", "symbol", "close"}]


def _ic_table(panel: pd.DataFrame, factors: List[str], horizons: List[int]) -> Dict[str, Any]:
    tables: Dict[str, Any] = {}
    for factor_name in factors:
        factor_result: Dict[str, Any] = {"ic": {}, "rank_ic": {}}
        for horizon in horizons:
            ret_name = f"fwd_ret_{horizon}"
            ic_series = panel.groupby("timestamp").apply(
                lambda x: _cross_sectional_corr(x, factor_name, ret_name, "pearson")
            )
            rank_ic_series = panel.groupby("timestamp").apply(
                lambda x: _cross_sectional_corr(x, factor_name, ret_name, "spearman")
            )
            factor_result["ic"][str(horizon)] = float(ic_series.mean())
            factor_result["rank_ic"][str(horizon)] = float(rank_ic_series.mean())
        tables[factor_name] = factor_result
    return tables


def _ic_decay(panel: pd.DataFrame, factors: List[str], horizons: List[int]) -> Dict[str, List[float]]:
    result: Dict[str, List[float]] = {}
    for factor_name in factors:
        result[factor_name] = []
        for horizon in horizons:
            ret_name = f"fwd_ret_{horizon}"
            ic_series = panel.groupby("timestamp").apply(
                lambda x: _cross_sectional_corr(x, factor_name, ret_name, "spearman")
            )
            result[factor_name].append(float(ic_series.mean()))
    return result


def _quantile_table(
    panel: pd.DataFrame,
    factors: List[str],
    quantiles: int,
    horizon: int,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    ret_name = f"fwd_ret_{horizon}"

    for factor_name in factors:
        sample = panel[["timestamp", "symbol", factor_name, ret_name]].dropna().copy()
        if sample.empty:
            out[factor_name] = {}
            continue

        def _tag_quantile(one_day: pd.DataFrame) -> pd.DataFrame:
            if one_day[factor_name].nunique() < quantiles:
                one_day["quantile"] = np.nan
                return one_day
            one_day["quantile"] = pd.qcut(one_day[factor_name], quantiles, labels=False, duplicates="drop")
            return one_day

        sample = sample.groupby("timestamp", group_keys=False).apply(_tag_quantile)
        grouped = sample.dropna(subset=["quantile"]).groupby("quantile")[ret_name].mean()
        out[factor_name] = {str(int(idx) + 1): float(value) for idx, value in grouped.items()}
    return out


def _select_effective_factors(ic_stats: Dict[str, Any], cfg: AlphaResearchConfig) -> List[str]:
    selected = []
    for factor_name, stat in ic_stats.items():
        best_ic = max(abs(float(v)) for v in stat["ic"].values())
        best_rank_ic = max(abs(float(v)) for v in stat["rank_ic"].values())
        if best_ic >= cfg.min_ic and best_rank_ic >= cfg.min_rank_ic:
            selected.append(factor_name)
    return selected


def _build_composite_factor(panel: pd.DataFrame, selected_factors: List[str]) -> pd.Series:
    if not selected_factors:
        empty_index = pd.MultiIndex.from_arrays([[], []], names=["timestamp", "symbol"])
        return pd.Series(dtype=float, index=empty_index, name="composite_factor")

    df = panel[["timestamp", "symbol"] + selected_factors].copy()
    normalized_parts = []
    for factor_name in selected_factors:
        part = df.groupby("timestamp")[factor_name].transform(
            lambda s: (s - s.mean()) / (s.std(ddof=0) + 1e-12)
        )
        normalized_parts.append(part.rename(factor_name))
    normalized_df = pd.concat(normalized_parts, axis=1)
    composite = normalized_df.mean(axis=1, skipna=True).to_numpy()
    return pd.Series(
        composite,
        index=pd.MultiIndex.from_frame(df[["timestamp", "symbol"]], names=["timestamp", "symbol"]),
        name="composite_factor",
    )


def _build_signals_from_factor_score(score: pd.Series, top_n: int) -> pd.Series:
    if score.empty:
        empty_index = pd.MultiIndex.from_arrays([[], []], names=["timestamp", "symbol"])
        return pd.Series(dtype=int, index=empty_index, name="signal")

    score_df = score.rename("score").reset_index()
    score_df["rank"] = score_df.groupby("timestamp")["score"].rank(method="first", ascending=False)
    return pd.Series(
        (score_df["rank"] <= top_n).astype(int).values,
        index=pd.MultiIndex.from_frame(score_df[["timestamp", "symbol"]], names=["timestamp", "symbol"]),
        name="signal",
    )


def run_alpha_research(
    ohlcv: pd.DataFrame,
    cfg: AlphaResearchConfig,
) -> Dict[str, Any]:
    factor_panel = build_alpha_factor_panel(ohlcv)
    forward_panel = _build_forward_returns(ohlcv, cfg.forward_days)
    panel = factor_panel.merge(forward_panel.drop(columns=["close"]), on=["timestamp", "symbol"], how="left")
    factors = _factor_names(factor_panel)

    ic_stats = _ic_table(panel, factors, cfg.forward_days)
    ic_decay = _ic_decay(panel, factors, cfg.forward_days)
    quantile_stats = _quantile_table(panel, factors, cfg.quantiles, cfg.forward_days[-1])
    selected_factors = _select_effective_factors(ic_stats, cfg)
    composite_factor = _build_composite_factor(panel, selected_factors)
    composite_signal = _build_signals_from_factor_score(composite_factor, cfg.top_n)

    latest_picks: List[str] = []
    if not composite_factor.empty:
        latest_ts = composite_factor.index.get_level_values("timestamp").max()
        latest_slice = composite_factor.xs(latest_ts, level="timestamp").sort_values(ascending=False).head(cfg.top_n)
        latest_picks = latest_slice.index.astype(str).tolist()

    backtest_result = run_signal_backtest(ohlcv, composite_signal, composite_factor, cfg.backtest)
    return {
        "config": asdict(cfg),
        "selected_factors": selected_factors,
        "ic": ic_stats,
        "ic_decay": ic_decay,
        "quantile": quantile_stats,
        "latest_picks": latest_picks,
        "composite_backtest_metrics": backtest_result["metrics"],
    }
