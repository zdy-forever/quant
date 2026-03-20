"""
单因子研究入口模块。

它把新的研究主线固定成：
- 先定义 universe
- 再生成横截面因子表
- 再做 train / OOS 的单因子验证

如果单因子自己都站不住，这里就会直接暴露出来，
不会让你继续浪费时间在策略调参上。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

import pandas as pd

from research.factor_engine import UniverseConfig, build_factor_research_panel
from research.factor_tests import FactorTestConfig, run_single_factor_validation
from research.standardize import StandardizeConfig


@dataclass(frozen=True)
class FactorResearchSpec:
    train_start: str
    train_end: str
    oos_start: str
    oos_end: str
    candidate_factors: List[str] | None = None


def _slice_frame(frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    return out[(out["timestamp"] >= start_ts) & (out["timestamp"] <= end_ts)].copy()


def _filter_candidate_factors(summary: Dict[str, Any], candidate_factors: List[str] | None) -> Dict[str, Any]:
    if not candidate_factors:
        return summary
    keep = [name for name in summary["factor_names"] if name in set(candidate_factors)]

    def _subset_panel(panel: pd.DataFrame) -> pd.DataFrame:
        base_cols = [col for col in panel.columns if col not in summary["factor_names"]]
        return panel[base_cols + keep].copy()

    return {
        **summary,
        "factor_names": keep,
        "factor_definitions": {name: summary["factor_definitions"][name] for name in keep if name in summary["factor_definitions"]},
        "raw_panel": _subset_panel(summary["raw_panel"]),
        "standardized_panel": _subset_panel(summary["standardized_panel"]),
    }


def run_factor_research(
    ohlcv: pd.DataFrame,
    spec: FactorResearchSpec,
    universe_cfg: UniverseConfig,
    standardize_cfg: StandardizeConfig,
    test_cfg: FactorTestConfig,
) -> Dict[str, Any]:
    engine_summary = build_factor_research_panel(ohlcv, universe_cfg, standardize_cfg)
    engine_summary = _filter_candidate_factors(engine_summary, spec.candidate_factors)

    train_ohlcv = _slice_frame(ohlcv, spec.train_start, spec.train_end)
    train_panel = _slice_frame(engine_summary["standardized_panel"], spec.train_start, spec.train_end)
    oos_ohlcv = _slice_frame(ohlcv, spec.oos_start, spec.oos_end)
    oos_panel = _slice_frame(engine_summary["standardized_panel"], spec.oos_start, spec.oos_end)

    train_result = run_single_factor_validation(train_ohlcv, train_panel, test_cfg)
    oos_result = run_single_factor_validation(oos_ohlcv, oos_panel, test_cfg)

    return {
        "spec": asdict(spec),
        "engine": {
            "config": engine_summary["config"],
            "factor_names": engine_summary["factor_names"],
            "factor_definitions": engine_summary["factor_definitions"],
            "universe_stats": engine_summary["universe_stats"],
        },
        "train": train_result,
        "oos": oos_result,
        "raw_panel": engine_summary["raw_panel"],
        "standardized_panel": engine_summary["standardized_panel"],
    }
