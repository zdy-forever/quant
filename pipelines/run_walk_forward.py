"""
因子驱动的 walk-forward 模块。

和旧的“策略参数 walk-forward”不同，这里滚动验证的是：
- train 窗口里选出来的因子
- 这些因子在下一段 OOS 里是否还能维持方向
- 用 train 选中的因子构建的组合，在 OOS 里表现如何
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from backtest.engine import BacktestConfig
from pipelines.run_composite_portfolio import FactorPortfolioSpec, run_composite_portfolio
from research.factor_selection import FactorSelectionConfig, filter_oos_consistent_factors, select_train_factors
from research.factor_tests import FactorTestConfig, run_single_factor_validation

REPORT_DIR = os.path.join("artifacts", "reports")


@dataclass(frozen=True)
class FactorWalkForwardSpec:
    start: str
    end: str
    train_years: int = 3
    test_months: int = 6
    step_months: int = 6
    gap_days: int = 1
    top_n: int = 10


def _to_utc_ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def _month_add(ts: pd.Timestamp, months: int) -> pd.Timestamp:
    return (ts + pd.DateOffset(months=months)).normalize()


def _slice_frame(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    return out[(out["timestamp"] >= start) & (out["timestamp"] <= end)].copy()


def _window_summary(windows: List[Dict[str, Any]]) -> Dict[str, float]:
    if not windows:
        return {"window_count": 0.0}
    sharpes = np.array([float(window["portfolio_metrics"].get("sharpe", np.nan)) for window in windows], dtype=float)
    cagrs = np.array([float(window["portfolio_metrics"].get("cagr", np.nan)) for window in windows], dtype=float)
    drawdowns = np.array([float(window["portfolio_metrics"].get("max_dd", np.nan)) for window in windows], dtype=float)
    valid_sharpes = sharpes[np.isfinite(sharpes)]
    valid_cagrs = cagrs[np.isfinite(cagrs)]
    valid_drawdowns = drawdowns[np.isfinite(drawdowns)]
    return {
        "window_count": float(len(windows)),
        "positive_sharpe_ratio": float(np.mean(valid_sharpes > 0.0)) if valid_sharpes.size else np.nan,
        "median_sharpe": float(np.median(valid_sharpes)) if valid_sharpes.size else np.nan,
        "median_cagr": float(np.median(valid_cagrs)) if valid_cagrs.size else np.nan,
        "worst_window_max_dd": float(np.min(valid_drawdowns)) if valid_drawdowns.size else np.nan,
    }


def run_factor_walk_forward(
    ohlcv: pd.DataFrame,
    standardized_panel: pd.DataFrame,
    test_cfg: FactorTestConfig,
    selection_cfg: FactorSelectionConfig,
    backtest_cfg: BacktestConfig,
    spec: FactorWalkForwardSpec,
) -> Dict[str, Any]:
    os.makedirs(REPORT_DIR, exist_ok=True)
    start_ts = _to_utc_ts(spec.start)
    end_ts = _to_utc_ts(spec.end)
    windows: List[Dict[str, Any]] = []
    selected_frequency: Dict[str, int] = {}

    cursor = start_ts
    while True:
        train_end = _month_add(cursor, spec.train_years * 12)
        test_start = train_end + pd.Timedelta(days=spec.gap_days)
        test_end = _month_add(test_start, spec.test_months)
        if test_end > end_ts:
            break

        train_ohlcv = _slice_frame(ohlcv, cursor, train_end)
        train_panel = _slice_frame(standardized_panel, cursor, train_end)
        test_ohlcv = _slice_frame(ohlcv, test_start, test_end)
        test_panel = _slice_frame(standardized_panel, test_start, test_end)

        train_result = run_single_factor_validation(train_ohlcv, train_panel, test_cfg)
        train_selection = select_train_factors(train_result, selection_cfg)
        test_result = run_single_factor_validation(test_ohlcv, test_panel, test_cfg)
        oos_consistency = filter_oos_consistent_factors(train_selection["selected_factors"], test_result, selection_cfg)

        for factor_name in train_selection["selected_factors"]:
            selected_frequency[factor_name] = selected_frequency.get(factor_name, 0) + 1

        portfolio = run_composite_portfolio(
            test_ohlcv,
            test_panel,
            train_selection["selected_factors"],
            FactorPortfolioSpec(
                start=str(test_start.date()),
                end=str(test_end.date()),
                top_n=spec.top_n,
            ),
            backtest_cfg,
        )

        windows.append(
            {
                "train_window": [str(cursor.date()), str(train_end.date())],
                "test_window": [str(test_start.date()), str(test_end.date())],
                "train_selected_factors": train_selection["selected_factors"],
                "oos_consistent_factors": oos_consistency["oos_consistent_factors"],
                "portfolio_metrics": portfolio["metrics"],
                "latest_picks": portfolio["latest_picks"],
            }
        )
        cursor = _month_add(cursor, spec.step_months)

    result = {
        "spec": asdict(spec),
        "windows": windows,
        "window_summary": _window_summary(windows),
        "selected_factor_frequency": selected_frequency,
    }
    report_path = os.path.join(REPORT_DIR, f"factor_walk_forward_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    result["report_path"] = report_path
    return result
