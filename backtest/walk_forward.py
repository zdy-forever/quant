# -*- coding: utf-8 -*-
"""
Walk-forward 验证模块。

单次 OOS 测试看的是“某一段时间”；
Walk-forward 看的是“很多连续时间窗口”里是否都还能站得住。

如果你发现单次测试很好，但不同窗口差异很大，通常意味着策略稳定性不足。
所以这个文件更像是策略上线前的体检工具。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd

from backtest.test import _load_frozen_params
from backtest.train import REPORT_DIR, _metrics, _simple_backtest
from strategy.mean_reversion.mean_reversion import MeanReversionBollingerStrategy
from strategy.pullback.pullback import PullbackMomentumStrategy
from strategy.trend.trend import TrendBreakoutStrategy


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


def _to_utc_ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def _month_add(ts: pd.Timestamp, months: int) -> pd.Timestamp:
    return (ts + pd.DateOffset(months=months)).normalize()


def run_walk_forward(ohlcv: pd.DataFrame, wf: WalkForwardSpec) -> Dict[str, Any]:
    """参数冻结后做连续 OOS 窗口体检。"""

    os.makedirs(REPORT_DIR, exist_ok=True)

    name_to_strategy = {
        "trend": TrendBreakoutStrategy(),
        "mean_reversion": MeanReversionBollingerStrategy(),
        "pullback": PullbackMomentumStrategy(),
    }

    start_ts = _to_utc_ts(wf.start)
    end_ts = _to_utc_ts(wf.end)
    results = {"walk_forward_spec": wf.__dict__, "strategies": {}}

    for name in wf.strategies:
        if name not in name_to_strategy:
            raise ValueError(f"未知策略: {name}")

        payload = _load_frozen_params(name)
        params = payload["params"]
        strategy = name_to_strategy[name]
        generated = strategy.generate(ohlcv, params)

        windows = []
        equity_all = pd.Series(dtype=float)
        cursor = start_ts

        while True:
            train_end = _month_add(cursor, wf.train_years * 12)
            test_start = train_end + pd.Timedelta(days=wf.gap_days)
            test_end = _month_add(test_start, wf.test_months)
            if test_end > end_ts:
                break

            equity = _simple_backtest(ohlcv, generated.signals, test_start, test_end)
            metrics = _metrics(equity)
            windows.append(
                {
                    "train_window": [str(cursor.date()), str(train_end.date())],
                    "test_window": [str(test_start.date()), str(test_end.date())],
                    "metrics": metrics,
                    "equity_final": float(equity.iloc[-1]) if not equity.empty else float("nan"),
                }
            )

            if not equity.empty:
                equity_all = pd.concat([equity_all, equity])
                equity_all = equity_all[~equity_all.index.duplicated(keep="last")]

            cursor = _month_add(cursor, wf.step_months)

        results["strategies"][name] = {
            "frozen_file": os.path.join("artifacts", "frozen_params", f"{name}.json"),
            "windows": windows,
            "overall_metrics": _metrics(equity_all) if not equity_all.empty else {},
        }

    report_path = os.path.join(
        REPORT_DIR,
        f"walk_forward_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2)

    return results
