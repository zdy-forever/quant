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
    step_months: int = 3
    gap_days: int = 1
    backtest: BacktestConfig = field(default_factory=BacktestConfig)


def _to_utc_ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def _month_add(ts: pd.Timestamp, months: int) -> pd.Timestamp:
    return (ts + pd.DateOffset(months=months)).normalize()


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
        equity_all = pd.Series(dtype=float)
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

            if not equity.empty:
                equity_all = pd.concat([equity_all, equity])
                equity_all = equity_all[~equity_all.index.duplicated(keep="last")]

            cursor = _month_add(cursor, wf.step_months)

        overall_metrics = {}
        if not equity_all.empty:
            overall_returns = equity_all.pct_change().dropna()
            peak = equity_all.cummax()
            max_dd = float((equity_all / peak - 1.0).min())
            years = max((equity_all.index[-1] - equity_all.index[0]).days / 365.25, 1e-9)
            cagr = float((equity_all.iloc[-1] / equity_all.iloc[0]) ** (1.0 / years) - 1.0)
            overall_metrics = {
                "sharpe": float(overall_returns.mean() / (overall_returns.std(ddof=0) + 1e-12) * (252.0 ** 0.5)),
                "cagr": cagr,
                "max_dd": max_dd,
                "calmar": float(cagr / (abs(max_dd) + 1e-12)),
            }

        results["strategies"][name] = {
            "frozen_file": os.path.join("artifacts", "frozen_params", f"{name}.json"),
            "windows": windows,
            "overall_metrics": overall_metrics,
        }

    report_path = os.path.join(
        REPORT_DIR,
        f"walk_forward_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2)

    return results
