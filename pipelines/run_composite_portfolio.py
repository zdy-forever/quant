"""
组合因子回测入口模块。

单因子筛选通过之后，才来到这里把多个稳定因子组合成一个总分，
再用最简单的 top-N 组合方式回测。

这里故意保持朴素：
- 等权组合因子
- top-N 持仓
- 用接近“纯因子组合”的方式回测
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

import pandas as pd

from backtest.engine import BacktestConfig, run_signal_backtest
from factors.composite import CompositeConfig, build_composite_score, build_top_n_signal, latest_top_picks
from portfolio.trade_filters import TradeFilterConfig, apply_trade_filters


@dataclass(frozen=True)
class FactorPortfolioSpec:
    start: str
    end: str
    top_n: int = 10
    weighting: str = "equal"
    rebalance_every_n_days: int = 1
    factor_weights: Dict[str, float] | None = None
    trade_filters: Dict[str, float] | None = None
    backtest_overrides: Dict[str, Any] | None = None


def _slice_frame(frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    return out[(out["timestamp"] >= start_ts) & (out["timestamp"] <= end_ts)].copy()


def _clean_factor_backtest_cfg(
    base_cfg: BacktestConfig,
    top_n: int,
    rebalance_every_n_days: int,
    overrides: Dict[str, Any] | None = None,
) -> BacktestConfig:
    cfg_dict = asdict(base_cfg)
    cfg_dict["max_positions"] = top_n
    cfg_dict["rebalance_every_n_days"] = rebalance_every_n_days
    if overrides:
        cfg_dict.update(overrides)
    return BacktestConfig(**cfg_dict)


def run_composite_portfolio(
    ohlcv: pd.DataFrame,
    standardized_panel: pd.DataFrame,
    selected_factors: List[str],
    spec: FactorPortfolioSpec,
    backtest_cfg: BacktestConfig,
    raw_panel: pd.DataFrame | None = None,
) -> Dict[str, Any]:
    window_ohlcv = _slice_frame(ohlcv, spec.start, spec.end)
    window_panel = _slice_frame(standardized_panel, spec.start, spec.end)
    window_raw_panel = _slice_frame(raw_panel, spec.start, spec.end) if raw_panel is not None else None

    composite_cfg = CompositeConfig(
        top_n=spec.top_n,
        weighting="custom" if spec.factor_weights else spec.weighting,
        rebalance_every_n_days=spec.rebalance_every_n_days,
    )
    score_frame = build_composite_score(
        window_panel,
        selected_factors,
        composite_cfg,
        custom_weights=spec.factor_weights,
    )
    filter_diagnostics: Dict[str, Any] | None = None
    if spec.trade_filters and window_raw_panel is not None:
        score_frame, filter_diagnostics = apply_trade_filters(
            score_frame,
            window_raw_panel,
            TradeFilterConfig(**spec.trade_filters),
        )
    signal = build_top_n_signal(score_frame, spec.top_n)
    result = run_signal_backtest(
        window_ohlcv,
        signal,
        score_frame.set_index(["timestamp", "symbol"])["score"] if not score_frame.empty else None,
        _clean_factor_backtest_cfg(
            backtest_cfg,
            spec.top_n,
            spec.rebalance_every_n_days,
            spec.backtest_overrides,
        ),
    )
    return {
        "spec": asdict(spec),
        "selected_factors": selected_factors,
        "factor_weights": spec.factor_weights or {},
        "filter_diagnostics": filter_diagnostics or {},
        "latest_picks": latest_top_picks(score_frame, spec.top_n),
        "metrics": result["metrics"],
    }
