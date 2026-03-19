# -*- coding: utf-8 -*-
"""
训练与冻结参数模块。

这个文件只服务于“研究阶段”：
- 调用优化器搜索参数
- 用统一回测引擎评估结果
- 把最优参数冻结到 artifacts 目录

这里的重点不是保证“最好看”的历史收益，
而是尽量用统一、可重复、可审计的方式完成参数研究。
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from backtest.engine import BacktestConfig
from backtest.optimizer import OptimizationSpec, optimize_strategy


ART_DIR = "artifacts"
FROZEN_DIR = os.path.join(ART_DIR, "frozen_params")
REPORT_DIR = os.path.join(ART_DIR, "reports")
MANIFEST_FILE = os.path.join(FROZEN_DIR, "MANIFEST.json")


@dataclass(frozen=True)
class TrainSpec:
    symbols: List[str]
    start: str
    end: str
    objective: str = "sharpe"
    overwrite_frozen: bool = False
    min_trade_count: int = 8
    min_avg_active_positions: float = 1.0
    max_avg_turnover: float = 1.5
    backtest: BacktestConfig = field(default_factory=BacktestConfig)


def _ensure_dirs() -> None:
    os.makedirs(FROZEN_DIR, exist_ok=True)
    os.makedirs(REPORT_DIR, exist_ok=True)


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        digest.update(handle.read())
    return digest.hexdigest()


def _update_manifest() -> None:
    strategies: Dict[str, Dict[str, str]] = {}
    for filename in sorted(os.listdir(FROZEN_DIR)):
        if not filename.endswith(".json") or filename == os.path.basename(MANIFEST_FILE):
            continue
        path = os.path.join(FROZEN_DIR, filename)
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        name = str(payload.get("strategy") or os.path.splitext(filename)[0])
        strategies[name] = {
            "file": path,
            "sha256": _file_sha256(path),
            "frozen_at_utc": str(payload.get("frozen_at_utc", "")),
        }

    manifest = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "strategies": strategies,
    }
    with open(MANIFEST_FILE, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)


def freeze_params(
    strategy_name: str,
    params: Dict[str, Any],
    train_spec: TrainSpec,
    best_metrics: Dict[str, float],
) -> str:
    """
    把训练阶段选出的参数写入 frozen 文件。
    """

    _ensure_dirs()
    path = os.path.join(FROZEN_DIR, f"{strategy_name}.json")

    if (not train_spec.overwrite_frozen) and os.path.exists(path):
        raise FileExistsError(
            f"冻结参数已存在且不允许覆盖：{path}\n"
            "如需覆盖，请显式设置 overwrite_frozen=True。"
        )

    payload = {
        "strategy": strategy_name,
        "params": params,
        "train_spec": asdict(train_spec),
        "best_metrics": best_metrics,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "note": "样本外测试和部署阶段严禁直接修改该文件。",
    }

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    _update_manifest()
    return path


def train(
    ohlcv,
    train_spec: TrainSpec,
    strategies: List[str],
) -> Dict[str, Any]:
    """
    训练阶段：搜索参数并冻结结果。
    """

    _ensure_dirs()

    opt_spec = OptimizationSpec(
        start=train_spec.start,
        end=train_spec.end,
        objective=train_spec.objective,
        min_trade_count=train_spec.min_trade_count,
        min_avg_active_positions=train_spec.min_avg_active_positions,
        max_avg_turnover=train_spec.max_avg_turnover,
        backtest=train_spec.backtest,
    )

    summary = {"train_spec": asdict(train_spec), "results": {}}
    for strategy_name in strategies:
        result = optimize_strategy(ohlcv, strategy_name, opt_spec)
        frozen_path = freeze_params(
            strategy_name,
            result["best_params"],
            train_spec,
            result["best_metrics"],
        )
        summary["results"][strategy_name] = {
            "best_params": result["best_params"],
            "best_metrics": result["best_metrics"],
            "optimization_score": result["score"],
            "frozen_path": frozen_path,
        }

    report_path = os.path.join(
        REPORT_DIR,
        f"train_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)

    return summary
