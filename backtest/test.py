# -*- coding: utf-8 -*-
"""
样本外测试模块。

这里的职责是：
- 读取冻结参数
- 用统一回测引擎跑 OOS
- 输出每个策略的样本外表现
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
from backtest.train import FROZEN_DIR, REPORT_DIR, _file_sha256


@dataclass(frozen=True)
class TestSpec:
    symbols: List[str]
    start: str
    end: str
    strategies: List[str]
    forbid_param_write: bool = True
    backtest: BacktestConfig = field(default_factory=BacktestConfig)


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
    registry = get_strategy_registry()

    before_hashes = _snapshot_frozen_hashes() if test_spec.forbid_param_write else {}
    start_ts = _to_utc_ts(test_spec.start)
    end_ts = _to_utc_ts(test_spec.end)

    sample = ohlcv.copy()
    sample["timestamp"] = pd.to_datetime(sample["timestamp"], utc=True)
    sample = sample[(sample["timestamp"] >= start_ts) & (sample["timestamp"] <= end_ts)].copy()

    results = {"test_spec": asdict(test_spec), "strategies": {}}
    for name in test_spec.strategies:
        if name not in registry:
            raise ValueError(f"未知策略: {name}")

        payload = _load_frozen_params(name)
        params = payload["params"]
        strategy = registry[name]
        generated = strategy.generate(sample, params)
        bt_result = run_signal_backtest(sample, generated.signals, generated.score, test_spec.backtest)

        results["strategies"][name] = {
            "frozen_file": os.path.join(FROZEN_DIR, f"{name}.json"),
            "oos_metrics": bt_result["metrics"],
            "equity_final": float(bt_result["equity_curve"].iloc[-1]) if not bt_result["equity_curve"].empty else float("nan"),
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
