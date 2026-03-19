# -*- coding: utf-8 -*-
"""
样本外测试模块。

这个文件的职责很单纯：
- 读取已经冻结好的参数
- 在新的时间区间上做 OOS 测试
- 生成测试报告

这里故意不允许重新搜索参数，因为 OOS 的目的就是检验训练结果能不能泛化。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd

from backtest.train import FROZEN_DIR, REPORT_DIR, _file_sha256, _metrics, _simple_backtest
from strategy.mean_reversion.mean_reversion import MeanReversionBollingerStrategy
from strategy.trend.trend import TrendBreakoutStrategy


@dataclass(frozen=True)
class TestSpec:
    symbols: List[str]
    start: str
    end: str
    strategies: List[str]
    forbid_param_write: bool = True


def _to_utc_ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def _load_frozen_params(strategy_name: str) -> Dict[str, Any]:
    path = os.path.join(FROZEN_DIR, f"{strategy_name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"缺少冻结参数文件: {path}（请先运行 train）")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _snapshot_frozen_hashes() -> Dict[str, str]:
    if not os.path.exists(FROZEN_DIR):
        return {}
    return {
        filename: _file_sha256(os.path.join(FROZEN_DIR, filename))
        for filename in os.listdir(FROZEN_DIR)
        if filename.endswith(".json")
    }


def run_oos_test(ohlcv: pd.DataFrame, test_spec: TestSpec) -> Dict[str, Any]:
    os.makedirs(REPORT_DIR, exist_ok=True)

    name_to_strategy = {
        "trend": TrendBreakoutStrategy(),
        "mean_reversion": MeanReversionBollingerStrategy(),
    }

    before_hashes = _snapshot_frozen_hashes() if test_spec.forbid_param_write else {}
    start_ts = _to_utc_ts(test_spec.start)
    end_ts = _to_utc_ts(test_spec.end)

    results = {"test_spec": test_spec.__dict__, "strategies": {}}
    for name in test_spec.strategies:
        if name not in name_to_strategy:
            raise ValueError(f"未知策略: {name}")

        payload = _load_frozen_params(name)
        params = payload["params"]

        strategy = name_to_strategy[name]
        result = strategy.generate(ohlcv, params)
        equity = _simple_backtest(ohlcv, result.signals, start_ts, end_ts)
        metrics = _metrics(equity)

        results["strategies"][name] = {
            "frozen_file": os.path.join(FROZEN_DIR, f"{name}.json"),
            "oos_metrics": metrics,
            "equity_final": float(equity.iloc[-1]) if not equity.empty else float("nan"),
        }

    after_hashes = _snapshot_frozen_hashes() if test_spec.forbid_param_write else {}
    if test_spec.forbid_param_write and before_hashes != after_hashes:
        raise RuntimeError("OOS/test 阶段检测到 frozen 参数文件发生变化。")

    report_path = os.path.join(
        REPORT_DIR,
        f"test_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2)

    return results
