# -*- coding: utf-8 -*-
"""
Walk-forward 验证模块。

单次 OOS 测试看的是“某一段时间”；
Walk-forward 看的是“很多连续时间窗口”里是否都还能站得住。

它和 train 最大的区别是：
- 不重新优化参数
- 只拿冻结参数在不同连续窗口上做稳定性体检
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from backtest.engine import BacktestConfig, run_signal_backtest
from backtest.optimizer import get_strategy_registry
from backtest.test import _load_frozen_params
from backtest.train import REPORT_DIR


@dataclass(frozen=True)
class WalkForwardSpec:
    symbols: List[str]
    start: str
    end: str
    strategies: List[str]
    train_years: int = 3
    test_months: int = 6
    step_months: int = 6
    gap_days: int = 1
    backtest: BacktestConfig = field(default_factory=BacktestConfig)


def _to_utc_ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def _month_add(ts: pd.Timestamp, months: int) -> pd.Timestamp:
    return (ts + pd.DateOffset(months=months)).normalize()


def _window_summary(windows: List[Dict[str, Any]], wf: WalkForwardSpec) -> Dict[str, float]:
    if not windows:
        return {
            "window_count": 0.0,
            "overlapping_windows": float(wf.step_months < wf.test_months),
        }

    sharpes = np.array([float(window["metrics"].get("sharpe", np.nan)) for window in windows], dtype=float)
    cagrs = np.array([float(window["metrics"].get("cagr", np.nan)) for window in windows], dtype=float)
    drawdowns = np.array([float(window["metrics"].get("max_dd", np.nan)) for window in windows], dtype=float)
    calmars = np.array([float(window["metrics"].get("calmar", np.nan)) for window in windows], dtype=float)

    valid_sharpes = sharpes[np.isfinite(sharpes)]
    valid_cagrs = cagrs[np.isfinite(cagrs)]
    valid_drawdowns = drawdowns[np.isfinite(drawdowns)]
    valid_calmars = calmars[np.isfinite(calmars)]

    return {
        "window_count": float(len(windows)),
        "overlapping_windows": float(wf.step_months < wf.test_months),
        "positive_sharpe_ratio": float(np.mean(valid_sharpes > 0.0)) if valid_sharpes.size else np.nan,
        "positive_calmar_ratio": float(np.mean(valid_calmars > 0.0)) if valid_calmars.size else np.nan,
        "median_sharpe": float(np.median(valid_sharpes)) if valid_sharpes.size else np.nan,
        "median_cagr": float(np.median(valid_cagrs)) if valid_cagrs.size else np.nan,
        "median_max_dd": float(np.median(valid_drawdowns)) if valid_drawdowns.size else np.nan,
        "mean_sharpe": float(np.mean(valid_sharpes)) if valid_sharpes.size else np.nan,
        "mean_cagr": float(np.mean(valid_cagrs)) if valid_cagrs.size else np.nan,
        "worst_window_max_dd": float(np.min(valid_drawdowns)) if valid_drawdowns.size else np.nan,
    }


def run_walk_forward(ohlcv: pd.DataFrame, wf: WalkForwardSpec) -> Dict[str, Any]:
    os.makedirs(REPORT_DIR, exist_ok=True)
    registry = get_strategy_registry()

    sample = ohlcv.copy()
    sample["timestamp"] = pd.to_datetime(sample["timestamp"], utc=True)

    start_ts = _to_utc_ts(wf.start)
    end_ts = _to_utc_ts(wf.end)
    results = {"walk_forward_spec": asdict(wf), "strategies": {}}

    for name in wf.strategies:
        if name not in registry:
            raise ValueError(f"未知策略: {name}")

        payload = _load_frozen_params(name)
        params = payload["params"]
        strategy = registry[name]
        generated = strategy.generate(sample, params)

        windows = []
        cursor = start_ts

        while True:
            train_end = _month_add(cursor, wf.train_years * 12)
            test_start = train_end + pd.Timedelta(days=wf.gap_days)
            test_end = _month_add(test_start, wf.test_months)
            if test_end > end_ts:
                break

            window_sample = sample[(sample["timestamp"] >= test_start) & (sample["timestamp"] <= test_end)].copy()
            bt_result = run_signal_backtest(window_sample, generated.signals, generated.score, wf.backtest)
            equity = bt_result["equity_curve"]

            windows.append(
                {
                    "train_window": [str(cursor.date()), str(train_end.date())],
                    "test_window": [str(test_start.date()), str(test_end.date())],
                    "metrics": bt_result["metrics"],
                    "equity_final": float(equity.iloc[-1]) if not equity.empty else float("nan"),
                }
            )

            cursor = _month_add(cursor, wf.step_months)

        results["strategies"][name] = {
            "frozen_file": os.path.join("artifacts", "frozen_params", f"{name}.json"),
            "windows": windows,
            "window_summary": _window_summary(windows, wf),
        }

    report_path = os.path.join(
        REPORT_DIR,
        f"walk_forward_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2)

    return results
