"""
低相关多因子 Alpha 的 walk-forward 验证模块。

这个文件和普通的因子 walk-forward 不一样：
- 每个训练窗口里先重新做低相关组合搜索
- 组合选择只看训练窗口，不偷看下一段测试窗口
- 然后把该窗口最优组合拿到下一段 OOS 里验证

如果你想判断“这个大 alpha 是不是只是碰巧”，这里就是关键体检环节。
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
from research.factor_combo_search import (
    FactorComboSearchConfig,
    compute_train_factor_correlation,
    generate_low_correlation_combinations,
    select_train_only_oriented_factor_pool,
)
from research.factor_engine import UniverseConfig, build_factor_research_panel
from research.factor_tests import FactorTestConfig, run_single_factor_validation
from research.standardize import StandardizeConfig

REPORT_DIR = os.path.join("artifacts", "reports")


@dataclass(frozen=True)
class AlphaComboWalkForwardSpec:
    start: str
    end: str
    train_years: int = 3
    test_months: int = 6
    step_months: int = 6
    gap_days: int = 1
    candidate_factors: List[str] | None = None
    top_n: int = 10
    rebalance_every_n_days: int = 1
    trade_filters: Dict[str, float] | None = None


def _to_utc_ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def _month_add(ts: pd.Timestamp, months: int) -> pd.Timestamp:
    return (ts + pd.DateOffset(months=months)).normalize()


def _slice_frame(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    return out[(out["timestamp"] >= start) & (out["timestamp"] <= end)].copy()


def _metric_value(metrics: Dict[str, Any], name: str) -> float:
    return float(metrics.get(name, 0.0) or 0.0)


def _train_combo_score(metrics: Dict[str, Any], max_abs_corr: float) -> float:
    return (
        0.65 * _metric_value(metrics, "sharpe")
        + 1.5 * _metric_value(metrics, "cagr")
        - 0.50 * abs(_metric_value(metrics, "max_dd"))
        - 0.25 * max_abs_corr
    )


def _window_summary(windows: List[Dict[str, Any]]) -> Dict[str, float]:
    if not windows:
        return {"window_count": 0.0}

    test_sharpes = np.array([_metric_value(row["test_metrics"], "sharpe") for row in windows], dtype=float)
    test_cagrs = np.array([_metric_value(row["test_metrics"], "cagr") for row in windows], dtype=float)
    test_dd = np.array([_metric_value(row["test_metrics"], "max_dd") for row in windows], dtype=float)
    valid_sharpes = test_sharpes[np.isfinite(test_sharpes)]
    valid_cagrs = test_cagrs[np.isfinite(test_cagrs)]
    valid_dd = test_dd[np.isfinite(test_dd)]
    return {
        "window_count": float(len(windows)),
        "positive_test_sharpe_ratio": float(np.mean(valid_sharpes > 0.0)) if valid_sharpes.size else np.nan,
        "positive_test_cagr_ratio": float(np.mean(valid_cagrs > 0.0)) if valid_cagrs.size else np.nan,
        "median_test_sharpe": float(np.median(valid_sharpes)) if valid_sharpes.size else np.nan,
        "median_test_cagr": float(np.median(valid_cagrs)) if valid_cagrs.size else np.nan,
        "worst_test_max_dd": float(np.min(valid_dd)) if valid_dd.size else np.nan,
    }


def _subset_candidate_factors(engine: Dict[str, Any], candidate_factors: List[str] | None) -> Dict[str, Any]:
    if not candidate_factors:
        return engine

    keep = [name for name in engine["factor_names"] if name in set(candidate_factors)]
    std_meta = [col for col in engine["standardized_panel"].columns if col not in engine["factor_names"]]
    raw_meta = [col for col in engine["raw_panel"].columns if col not in engine["factor_names"]]
    return {
        **engine,
        "factor_names": keep,
        "factor_definitions": {name: engine["factor_definitions"][name] for name in keep if name in engine["factor_definitions"]},
        "standardized_panel": engine["standardized_panel"][std_meta + keep].copy(),
        "raw_panel": engine["raw_panel"][raw_meta + keep].copy(),
    }


def _write_markdown_report(summary: Dict[str, Any], path: str) -> None:
    best_window = summary.get("best_window")
    windows = summary["windows"]
    lines: List[str] = [
        "# Low-Correlation Alpha Combo Walk-Forward Report",
        "",
        "## Summary",
        "",
        f"- Generated at UTC: `{summary['generated_at_utc']}`",
        f"- Window count: `{int(summary['window_summary'].get('window_count', 0.0))}`",
        f"- Positive test Sharpe ratio: `{summary['window_summary'].get('positive_test_sharpe_ratio', float('nan')):.1%}`",
        f"- Positive test CAGR ratio: `{summary['window_summary'].get('positive_test_cagr_ratio', float('nan')):.1%}`",
        f"- Median test Sharpe: `{summary['window_summary'].get('median_test_sharpe', float('nan')):.3f}`",
        f"- Median test CAGR: `{summary['window_summary'].get('median_test_cagr', float('nan')):.3%}`",
        f"- Worst test MaxDD: `{summary['window_summary'].get('worst_test_max_dd', float('nan')):.3%}`",
        "",
        "## Best Window",
        "",
    ]

    if best_window:
        lines.extend(
            [
                f"- Train window: `{best_window['train_window'][0]}` -> `{best_window['train_window'][1]}`",
                f"- Test window: `{best_window['test_window'][0]}` -> `{best_window['test_window'][1]}`",
                f"- Factors: `{', '.join(best_window['selected_combo']['factors'])}`",
                f"- Weights: `{', '.join(f'{name}:{weight:+.3f}' for name, weight in best_window['selected_combo']['factor_weights'].items())}`",
                f"- Max abs corr: `{best_window['selected_combo']['max_abs_corr']:.3f}`",
                f"- Test metrics: sharpe={best_window['test_metrics'].get('sharpe', float('nan')):.3f}, "
                f"cagr={best_window['test_metrics'].get('cagr', float('nan')):.3%}, "
                f"max_dd={best_window['test_metrics'].get('max_dd', float('nan')):.3%}",
            ]
        )
    else:
        lines.append("- 当前没有可用窗口。")

    lines.extend(["", "## Windows", ""])
    for idx, row in enumerate(windows, start=1):
        lines.extend(
            [
                f"### Window {idx}",
                "",
                f"- Train window: `{row['train_window'][0]}` -> `{row['train_window'][1]}`",
                f"- Test window: `{row['test_window'][0]}` -> `{row['test_window'][1]}`",
                f"- Factors: `{', '.join(row['selected_combo']['factors']) if row['selected_combo'] else 'none'}`",
                f"- Test sharpe/cagr: `{row['test_metrics'].get('sharpe', float('nan')):.3f}` / `{row['test_metrics'].get('cagr', float('nan')):.3%}`",
                f"- Latest picks: `{', '.join(row.get('test_latest_picks', [])) if row.get('test_latest_picks') else 'none'}`",
                "",
            ]
        )

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def run_alpha_combo_walk_forward(
    ohlcv: Any,
    spec: AlphaComboWalkForwardSpec,
    universe_cfg: UniverseConfig,
    standardize_cfg: StandardizeConfig,
    test_cfg: FactorTestConfig,
    combo_cfg: FactorComboSearchConfig,
    backtest_cfg: BacktestConfig,
) -> Dict[str, Any]:
    os.makedirs(REPORT_DIR, exist_ok=True)
    engine = build_factor_research_panel(ohlcv, universe_cfg, standardize_cfg)
    engine = _subset_candidate_factors(engine, spec.candidate_factors)

    start_ts = _to_utc_ts(spec.start)
    end_ts = _to_utc_ts(spec.end)
    windows: List[Dict[str, Any]] = []
    combo_frequency: Dict[str, int] = {}

    cursor = start_ts
    while True:
        train_end = _month_add(cursor, spec.train_years * 12)
        test_start = train_end + pd.Timedelta(days=spec.gap_days)
        test_end = _month_add(test_start, spec.test_months)
        if test_end > end_ts:
            break

        train_ohlcv = _slice_frame(ohlcv, cursor, train_end)
        train_std = _slice_frame(engine["standardized_panel"], cursor, train_end)
        train_raw = _slice_frame(engine["raw_panel"], cursor, train_end)
        test_ohlcv = _slice_frame(ohlcv, test_start, test_end)
        test_std = _slice_frame(engine["standardized_panel"], test_start, test_end)
        test_raw = _slice_frame(engine["raw_panel"], test_start, test_end)

        train_result = run_single_factor_validation(train_ohlcv, train_std, test_cfg)
        candidate_pool = select_train_only_oriented_factor_pool(
            train_result,
            engine["factor_definitions"],
            combo_cfg,
        )
        candidate_names = [item["factor"] for item in candidate_pool["candidate_factors"]]
        corr = compute_train_factor_correlation(engine["standardized_panel"], candidate_names, str(cursor.date()), str(train_end.date()))
        combo_candidates = generate_low_correlation_combinations(
            candidate_pool["candidate_factors"],
            engine["factor_definitions"],
            corr,
            combo_cfg,
        )

        shortlisted = combo_candidates["shortlisted_combinations"][:4]
        best_train_combo: Dict[str, Any] | None = None
        best_train_result: Dict[str, Any] | None = None
        best_train_score = -np.inf

        for combo in shortlisted:
            train_portfolio = run_composite_portfolio(
                train_ohlcv,
                train_std,
                combo["factors"],
                FactorPortfolioSpec(
                    start=str(cursor.date()),
                    end=str(train_end.date()),
                    top_n=spec.top_n,
                    rebalance_every_n_days=spec.rebalance_every_n_days,
                    factor_weights=combo["factor_weights"],
                    trade_filters=spec.trade_filters,
                ),
                backtest_cfg,
                raw_panel=train_raw,
            )
            train_score = _train_combo_score(train_portfolio["metrics"], combo["max_abs_corr"])
            if train_score > best_train_score:
                best_train_score = train_score
                best_train_combo = combo
                best_train_result = train_portfolio

        if best_train_combo is None or best_train_result is None:
            cursor = _month_add(cursor, spec.step_months)
            continue

        test_portfolio = run_composite_portfolio(
            test_ohlcv,
            test_std,
            best_train_combo["factors"],
            FactorPortfolioSpec(
                start=str(test_start.date()),
                end=str(test_end.date()),
                top_n=spec.top_n,
                rebalance_every_n_days=spec.rebalance_every_n_days,
                factor_weights=best_train_combo["factor_weights"],
                trade_filters=spec.trade_filters,
            ),
            backtest_cfg,
            raw_panel=test_raw,
        )

        combo_key = " | ".join(best_train_combo["factors"])
        combo_frequency[combo_key] = combo_frequency.get(combo_key, 0) + 1
        windows.append(
            {
                "train_window": [str(cursor.date()), str(train_end.date())],
                "test_window": [str(test_start.date()), str(test_end.date())],
                "selected_combo": best_train_combo,
                "candidate_pool": candidate_pool["candidate_factors"],
                "train_metrics": best_train_result["metrics"],
                "train_filter_diagnostics": best_train_result.get("filter_diagnostics", {}),
                "test_metrics": test_portfolio["metrics"],
                "test_filter_diagnostics": test_portfolio.get("filter_diagnostics", {}),
                "test_latest_picks": test_portfolio["latest_picks"],
            }
        )
        cursor = _month_add(cursor, spec.step_months)

    window_summary = _window_summary(windows)
    best_window = None
    if windows:
        best_window = sorted(
            windows,
            key=lambda row: (
                _metric_value(row["test_metrics"], "sharpe"),
                _metric_value(row["test_metrics"], "cagr"),
            ),
            reverse=True,
        )[0]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(REPORT_DIR, f"alpha_combo_walk_forward_{stamp}.json")
    md_path = os.path.join(REPORT_DIR, f"alpha_combo_walk_forward_{stamp}.md")
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "spec": asdict(spec),
        "combo_search_config": asdict(combo_cfg),
        "windows": windows,
        "window_summary": window_summary,
        "selected_combo_frequency": combo_frequency,
        "best_window": best_window,
        "report_files": {
            "json": json_path,
            "markdown": md_path,
        },
    }
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    _write_markdown_report(summary, md_path)
    return summary
