# -*- coding: utf-8 -*-
"""
一键研究流水线模块。

这个文件把“默认基线体检 -> 正式优化 -> 冻结参数 -> OOS -> Walk-forward -> Alpha 研究”
串成一次完整流程，适合你在扩展股票池后统一跑一轮正式研究。

如果你是量化新手，可以把它理解成“研究总导演”：
- 先看哪些策略连默认参数都站不住
- 再把更值得深挖的策略送去优化
- 最后统一输出一份可以复盘的结果报告
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from alpha_lab.research import AlphaResearchConfig, run_alpha_research
from backtest.engine import BacktestConfig, run_signal_backtest
from backtest.optimizer import OptimizationSpec, get_strategy_registry, optimize_strategy
from backtest.test import TestSpec, run_oos_test
from backtest.train import REPORT_DIR, TrainSpec, freeze_params
from backtest.walk_forward import WalkForwardSpec, run_walk_forward


@dataclass(frozen=True)
class PipelineSpec:
    symbols: List[str]
    optimize_start: str
    optimize_end: str
    test_start: str
    test_end: str
    walk_forward_start: str
    walk_forward_end: str
    objective: str = "calmar"
    candidate_strategies: List[str] | None = None
    max_strategies_to_optimize: int = 3
    overwrite_frozen: bool = True
    walk_forward_train_years: int = 3
    walk_forward_test_months: int = 6
    walk_forward_step_months: int = 6
    walk_forward_gap_days: int = 1


def _slice_ohlcv(ohlcv: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    df = ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    return df[(df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)].copy()


def _objective_value(metrics: Dict[str, float], objective: str) -> float:
    key = "calmar" if objective == "calmar" else ("cagr" if objective == "cagr" else "sharpe")
    value = float(metrics.get(key, np.nan))
    if not np.isfinite(value):
        return -1e12
    return value


def _baseline_score(metrics: Dict[str, float], objective: str) -> float:
    base = _objective_value(metrics, objective)
    trade_penalty = max(0.0, 4.0 - float(metrics.get("trade_count", 0.0))) * 0.1
    activity_penalty = max(0.0, 0.5 - float(metrics.get("avg_active_positions", 0.0))) * 0.2
    drawdown_penalty = max(0.0, abs(float(metrics.get("max_dd", 0.0))) - 0.25) * 2.0
    return float(base - trade_penalty - activity_penalty - drawdown_penalty)


def evaluate_strategy_baselines(
    ohlcv: pd.DataFrame,
    start: str,
    end: str,
    strategies: List[str],
    backtest: BacktestConfig,
    objective: str,
) -> Dict[str, Any]:
    registry = get_strategy_registry()
    sample = _slice_ohlcv(ohlcv, start, end)
    results: Dict[str, Any] = {}

    for name in strategies:
        if name not in registry:
            continue
        strategy = registry[name]
        params = strategy.default_params()
        try:
            generated = strategy.generate(sample, params)
            backtest_result = run_signal_backtest(sample, generated.signals, generated.score, backtest)
            metrics = backtest_result["metrics"]
            results[name] = {
                "default_params": params,
                "baseline_metrics": metrics,
                "baseline_score": _baseline_score(metrics, objective),
            }
        except Exception as exc:  # pragma: no cover - 研究流程里更关心不中断
            results[name] = {
                "default_params": params,
                "baseline_metrics": {},
                "baseline_score": -1e12,
                "error": str(exc),
            }

    ranked = sorted(
        results.items(),
        key=lambda item: float(item[1]["baseline_score"]),
        reverse=True,
    )
    return {
        "window": {"start": start, "end": end},
        "objective": objective,
        "ranked": [name for name, _ in ranked],
        "strategies": results,
    }


def _select_strategies(baseline: Dict[str, Any], max_count: int) -> List[str]:
    selected: List[str] = []
    for name in baseline["ranked"]:
        metrics = baseline["strategies"][name]["baseline_metrics"]
        if float(metrics.get("trade_count", 0.0)) < 4:
            continue
        if float(metrics.get("avg_active_positions", 0.0)) < 0.5:
            continue
        selected.append(name)
        if len(selected) >= max_count:
            break

    if selected:
        return selected
    return list(baseline["ranked"][:max_count])


def _write_markdown_report(summary: Dict[str, Any], path: str) -> None:
    baseline = summary["baseline"]
    selected = summary["selected_strategies"]
    optimized = summary["train"]["strategies"]
    test_results = summary["test"]["strategies"]
    alpha = summary["alpha"]

    lines: List[str] = [
        "# Research Pipeline Report",
        "",
        "## Run Summary",
        "",
        f"- Generated at UTC: `{summary['generated_at_utc']}`",
        f"- Universe size: `{summary['universe_size']}`",
        f"- Optimization window: `{summary['spec']['optimize_start']}` -> `{summary['spec']['optimize_end']}`",
        f"- OOS window: `{summary['spec']['test_start']}` -> `{summary['spec']['test_end']}`",
        f"- Walk-forward window: `{summary['spec']['walk_forward_start']}` -> `{summary['spec']['walk_forward_end']}`",
        f"- Baseline ranking: `{', '.join(baseline['ranked'])}`",
        f"- Selected strategies: `{', '.join(selected)}`",
        "",
        "## Baseline Screening",
        "",
    ]

    for name in baseline["ranked"]:
        metrics = baseline["strategies"][name]["baseline_metrics"]
        lines.append(
            f"- `{name}`: score={baseline['strategies'][name]['baseline_score']:.3f}, "
            f"sharpe={metrics.get('sharpe', float('nan')):.3f}, "
            f"cagr={metrics.get('cagr', float('nan')):.3%}, "
            f"max_dd={metrics.get('max_dd', float('nan')):.3%}, "
            f"trades={metrics.get('trade_count', float('nan')):.0f}"
        )

    lines.extend(["", "## Optimized Strategies", ""])
    for name in selected:
        train_row = optimized[name]
        train_metrics = train_row["best_metrics"]
        test_metrics = test_results[name]["oos_metrics"]
        lines.append(f"### `{name}`")
        lines.append("")
        lines.append(f"- Frozen params file: `{train_row['frozen_path']}`")
        lines.append(f"- Best params: `{json.dumps(train_row['best_params'], ensure_ascii=False)}`")
        lines.append(
            f"- Train metrics: sharpe={train_metrics.get('sharpe', float('nan')):.3f}, "
            f"cagr={train_metrics.get('cagr', float('nan')):.3%}, "
            f"max_dd={train_metrics.get('max_dd', float('nan')):.3%}, "
            f"calmar={train_metrics.get('calmar', float('nan')):.3f}"
        )
        lines.append(
            f"- OOS metrics: sharpe={test_metrics.get('sharpe', float('nan')):.3f}, "
            f"cagr={test_metrics.get('cagr', float('nan')):.3%}, "
            f"max_dd={test_metrics.get('max_dd', float('nan')):.3%}, "
            f"calmar={test_metrics.get('calmar', float('nan')):.3f}"
        )
        wf_metrics = summary["walk_forward"]["strategies"][name].get("window_summary", {})
        if wf_metrics:
            lines.append(
                f"- Walk-forward stability: +Sharpe窗口占比={wf_metrics.get('positive_sharpe_ratio', float('nan')):.1%}, "
                f"+Calmar窗口占比={wf_metrics.get('positive_calmar_ratio', float('nan')):.1%}, "
                f"中位Sharpe={wf_metrics.get('median_sharpe', float('nan')):.3f}, "
                f"中位CAGR={wf_metrics.get('median_cagr', float('nan')):.3%}, "
                f"最差窗口MaxDD={wf_metrics.get('worst_window_max_dd', float('nan')):.3%}"
            )
        lines.append("")

    lines.extend(
        [
            "## Alpha Research",
            "",
            f"- Selected factors: `{', '.join(alpha['selected_factors']) if alpha['selected_factors'] else 'none'}`",
            f"- Latest top picks: `{', '.join(alpha['latest_picks']) if alpha['latest_picks'] else 'none'}`",
        ]
    )
    factor_metrics = alpha["composite_backtest_metrics"]
    lines.append(
        f"- Composite factor backtest: sharpe={factor_metrics.get('sharpe', float('nan')):.3f}, "
        f"cagr={factor_metrics.get('cagr', float('nan')):.3%}, "
        f"max_dd={factor_metrics.get('max_dd', float('nan')):.3%}, "
        f"calmar={factor_metrics.get('calmar', float('nan')):.3f}"
    )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- 这份结果是研究报告，不是收益承诺。",
            "- 如果某个策略只在少数窗口表现很好，要优先怀疑样本依赖，而不是直接上实盘。",
            "- 下一步更值得做的是持续复跑同一流程，观察结果是否稳定，而不是继续盲目加更多参数。",
            "",
        ]
    )

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def run_pipeline(
    ohlcv: pd.DataFrame,
    spec: PipelineSpec,
    backtest_cfg: BacktestConfig,
    optimizer_cfg: Dict[str, Any],
    alpha_cfg: AlphaResearchConfig,
) -> Dict[str, Any]:
    os.makedirs(REPORT_DIR, exist_ok=True)
    strategies = spec.candidate_strategies or list(get_strategy_registry().keys())

    baseline = evaluate_strategy_baselines(
        ohlcv,
        spec.optimize_start,
        spec.optimize_end,
        strategies,
        backtest_cfg,
        spec.objective,
    )
    selected = _select_strategies(baseline, spec.max_strategies_to_optimize)

    opt_spec = OptimizationSpec(
        start=spec.optimize_start,
        end=spec.optimize_end,
        objective=spec.objective,
        min_trade_count=int(optimizer_cfg.get("min_trade_count", 8)),
        min_avg_active_positions=float(optimizer_cfg.get("min_avg_active_positions", 1.0)),
        max_avg_turnover=float(optimizer_cfg.get("max_avg_turnover", 1.5)),
        backtest=backtest_cfg,
    )

    train_summary: Dict[str, Any] = {"objective": spec.objective, "strategies": {}, "failed_strategies": {}}
    trained_selected: List[str] = []
    for name in selected:
        try:
            optimized = optimize_strategy(ohlcv, name, opt_spec)
            frozen_path = freeze_params(
                name,
                optimized["best_params"],
                train_spec=TrainSpec(
                    symbols=spec.symbols,
                    start=spec.optimize_start,
                    end=spec.optimize_end,
                    objective=spec.objective,
                    overwrite_frozen=spec.overwrite_frozen,
                    min_trade_count=int(optimizer_cfg.get("min_trade_count", 8)),
                    min_avg_active_positions=float(optimizer_cfg.get("min_avg_active_positions", 1.0)),
                    max_avg_turnover=float(optimizer_cfg.get("max_avg_turnover", 1.5)),
                    backtest=backtest_cfg,
                ),
                best_metrics=optimized["best_metrics"],
            )
            train_summary["strategies"][name] = {
                "best_params": optimized["best_params"],
                "best_metrics": optimized["best_metrics"],
                "optimization_score": optimized["score"],
                "frozen_path": frozen_path,
            }
            trained_selected.append(name)
        except Exception as exc:  # pragma: no cover - 研究流程里更关心不中断
            train_summary["failed_strategies"][name] = str(exc)

    if not trained_selected:
        raise RuntimeError("pipeline 没有任何策略成功完成优化。")

    test_summary = run_oos_test(
        ohlcv,
        TestSpec(
            symbols=spec.symbols,
            start=spec.test_start,
            end=spec.test_end,
            strategies=trained_selected,
            forbid_param_write=True,
            backtest=backtest_cfg,
        ),
    )

    walk_forward_summary = run_walk_forward(
        ohlcv,
        WalkForwardSpec(
            symbols=spec.symbols,
            start=spec.walk_forward_start,
            end=spec.walk_forward_end,
            strategies=trained_selected,
            train_years=spec.walk_forward_train_years,
            test_months=spec.walk_forward_test_months,
            step_months=spec.walk_forward_step_months,
            gap_days=spec.walk_forward_gap_days,
            backtest=backtest_cfg,
        ),
    )

    alpha_summary = run_alpha_research(
        _slice_ohlcv(ohlcv, spec.walk_forward_start, spec.walk_forward_end),
        alpha_cfg,
    )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(REPORT_DIR, f"pipeline_{stamp}.json")
    md_path = os.path.join(REPORT_DIR, f"pipeline_{stamp}.md")

    summary = {
        "generated_at_utc": generated_at,
        "universe_size": len(spec.symbols),
        "spec": asdict(spec),
        "baseline": baseline,
        "selected_strategies": trained_selected,
        "train": train_summary,
        "test": test_summary,
        "walk_forward": walk_forward_summary,
        "alpha": alpha_summary,
        "report_files": {
            "json": json_path,
            "markdown": md_path,
        },
    }

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    _write_markdown_report(summary, md_path)
    return summary
