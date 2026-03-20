"""
因子筛选入口模块。

这里把“train 里看起来有 alpha”的因子，继续拿去看 OOS 是否翻车。
最终输出的不是交易信号，而是一份冻结后的因子名单。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict

from research.factor_selection import FactorSelectionConfig, select_stable_factors

SELECTED_DIR = os.path.join("artifacts", "selected_factors")


@dataclass(frozen=True)
class FactorFreezeSpec:
    overwrite: bool = True


def freeze_stable_factors(
    research_summary: Dict[str, Any],
    selection_summary: Dict[str, Any],
    freeze_spec: FactorFreezeSpec,
) -> str:
    os.makedirs(SELECTED_DIR, exist_ok=True)
    path = os.path.join(SELECTED_DIR, "stable_factor_model.json")
    if os.path.exists(path) and not freeze_spec.overwrite:
        raise FileExistsError(f"已存在冻结因子文件：{path}")

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "research_spec": research_summary["spec"],
        "factor_definitions": {
            name: research_summary["engine"]["factor_definitions"][name]
            for name in selection_summary["stable_factors"]
            if name in research_summary["engine"]["factor_definitions"]
        },
        "selection": selection_summary,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path


def run_factor_selection(
    research_summary: Dict[str, Any],
    cfg: FactorSelectionConfig,
    freeze_spec: FactorFreezeSpec | None = None,
) -> Dict[str, Any]:
    selection = select_stable_factors(research_summary["train"], research_summary["oos"], cfg)
    result = {
        "config": asdict(cfg),
        **selection,
    }
    if freeze_spec is not None:
        result["frozen_path"] = freeze_stable_factors(research_summary, selection, freeze_spec)
    return result
