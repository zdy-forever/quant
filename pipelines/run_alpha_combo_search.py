"""
低相关多因子 Alpha 搜索入口模块。

这个模块负责把研究流程再往前推一步：
- 先从单因子研究结果里挑出“方向稳定”的因子
- 再限制因子两两相关性不能太高
- 最后把多组候选组合都回测一遍，看看哪个大 alpha 更稳

如果你以后还想继续扩展，这里就是“多因子模型实验室”的主入口。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

from backtest.engine import BacktestConfig
from pipelines.run_composite_portfolio import FactorPortfolioSpec, run_composite_portfolio
from pipelines.run_factor_research import FactorResearchSpec, run_factor_research
from research.factor_combo_search import (
    FactorComboSearchConfig,
    compute_train_factor_correlation,
    generate_low_correlation_combinations,
    select_oriented_factor_pool,
)
from research.factor_engine import UniverseConfig
from research.factor_tests import FactorTestConfig
from research.standardize import StandardizeConfig

REPORT_DIR = os.path.join("artifacts", "reports")
SELECTED_DIR = os.path.join("artifacts", "selected_factors")


@dataclass(frozen=True)
class AlphaComboSearchSpec:
    train_start: str
    train_end: str
    oos_start: str
    oos_end: str
    candidate_factors: List[str] | None = None
    top_n: int = 10
    rebalance_every_n_days: int = 1
    trade_filters: Dict[str, float] | None = None


def _metric_value(metrics: Dict[str, Any], name: str) -> float:
    return float(metrics.get(name, 0.0) or 0.0)


def _combo_stability_score(train_metrics: Dict[str, Any], oos_metrics: Dict[str, Any], max_abs_corr: float) -> float:
    return (
        0.35 * _metric_value(train_metrics, "sharpe")
        + 0.50 * _metric_value(oos_metrics, "sharpe")
        + 2.5 * _metric_value(oos_metrics, "cagr")
        - 0.75 * abs(_metric_value(oos_metrics, "max_dd"))
        - 0.25 * max_abs_corr
    )


def _direction_text(weights: Dict[str, float]) -> str:
    return ", ".join(f"{name}:{'+' if weight > 0 else '-'}" for name, weight in weights.items())


def _weight_text(weights: Dict[str, float]) -> str:
    return ", ".join(f"{name}:{weight:+.3f}" for name, weight in weights.items())


def _freeze_best_combo(summary: Dict[str, Any]) -> str | None:
    best = summary.get("best_combination")
    if not best:
        return None

    os.makedirs(SELECTED_DIR, exist_ok=True)
    path = os.path.join(SELECTED_DIR, "low_corr_alpha_model.json")
    payload = {
        "generated_at_utc": summary["generated_at_utc"],
        "spec": summary["spec"],
        "combo_search_config": summary["combo_search"]["config"],
        "best_combination": best,
        "report_files": summary["report_files"],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path


def _write_markdown_report(summary: Dict[str, Any], path: str) -> None:
    candidate_pool = summary["combo_search"]["candidate_pool"]
    evaluated = summary["combo_search"]["evaluated_combinations"]
    best = summary["best_combination"]

    lines: List[str] = [
        "# Low-Correlation Alpha Combo Report",
        "",
        "## Run Summary",
        "",
        f"- Generated at UTC: `{summary['generated_at_utc']}`",
        f"- Train window: `{summary['spec']['train_start']}` -> `{summary['spec']['train_end']}`",
        f"- OOS window: `{summary['spec']['oos_start']}` -> `{summary['spec']['oos_end']}`",
        f"- Candidate factor count: `{len(candidate_pool)}`",
        f"- Shortlisted combo count: `{len(evaluated)}`",
        f"- Corr ceiling: `{summary['combo_search']['config']['max_pairwise_correlation']:.2f}`",
        "",
        "## Candidate Pool",
        "",
    ]

    if candidate_pool:
        for item in candidate_pool:
            lines.append(
                f"- `{item['factor']}` ({item['category']}, {item['direction_label']}): "
                f"train_rank_ic={item['train_rank_ic']:.4f}, "
                f"oos_rank_ic={item['oos_rank_ic']:.4f}, "
                f"train_spread={item['train_spread']:.4f}, "
                f"oos_spread={item['oos_spread']:.4f}"
            )
    else:
        lines.append("- 当前没有足够稳定的单因子能进入低相关组合搜索。")

    lines.extend(["", "## Best Combination", ""])
    if best:
        lines.extend(
            [
                f"- Factors: `{', '.join(best['factors'])}`",
                f"- Directions: `{_direction_text(best['factor_weights'])}`",
                f"- Weights: `{_weight_text(best['factor_weights'])}`",
                f"- Max abs corr: `{best['max_abs_corr']:.3f}`",
                f"- Avg abs corr: `{best['avg_abs_corr']:.3f}`",
                f"- Train metrics: sharpe={best['train_metrics'].get('sharpe', float('nan')):.3f}, "
                f"cagr={best['train_metrics'].get('cagr', float('nan')):.3%}, "
                f"max_dd={best['train_metrics'].get('max_dd', float('nan')):.3%}",
                f"- OOS metrics: sharpe={best['oos_metrics'].get('sharpe', float('nan')):.3f}, "
                f"cagr={best['oos_metrics'].get('cagr', float('nan')):.3%}, "
                f"max_dd={best['oos_metrics'].get('max_dd', float('nan')):.3%}, "
                f"calmar={best['oos_metrics'].get('calmar', float('nan')):.3f}",
                f"- OOS filter diagnostics: `{json.dumps(best.get('oos_filter_diagnostics', {}), ensure_ascii=False)}`",
                f"- Latest top picks: `{', '.join(best['oos_latest_picks']) if best['oos_latest_picks'] else 'none'}`",
            ]
        )
    else:
        lines.append("- 没有找到满足相关性上限的可回测组合。")

    lines.extend(["", "## All Shortlisted Combinations", ""])
    for idx, combo in enumerate(evaluated, start=1):
        lines.extend(
            [
                f"### Combo {idx}",
                "",
                f"- Factors: `{', '.join(combo['factors'])}`",
                f"- Directions: `{_direction_text(combo['factor_weights'])}`",
                f"- Weights: `{_weight_text(combo['factor_weights'])}`",
                f"- Max abs corr: `{combo['max_abs_corr']:.3f}`",
                f"- Avg abs corr: `{combo['avg_abs_corr']:.3f}`",
                f"- Train sharpe/cagr: `{combo['train_metrics'].get('sharpe', float('nan')):.3f}` / `{combo['train_metrics'].get('cagr', float('nan')):.3%}`",
                f"- OOS sharpe/cagr: `{combo['oos_metrics'].get('sharpe', float('nan')):.3f}` / `{combo['oos_metrics'].get('cagr', float('nan')):.3%}`",
                f"- Stable on train+OOS: `{combo['stable_on_train_and_oos']}`",
                "",
            ]
        )

    lines.extend(
        [
            "## Notes",
            "",
            "- 这里允许把稳定负向因子翻转后加入组合，所以 `direction=-1` 表示先反号再进入 composite score。",
            "- 相关性约束是按训练期标准化因子值做的 Pearson 相关，目的是避免把太像的因子重复堆进模型。",
            "- 这份报告适合先做研究筛选，不代表已经达到了可以直接实盘的稳定程度。",
            "",
        ]
    )

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def run_alpha_combo_search(
    ohlcv: Any,
    spec: AlphaComboSearchSpec,
    universe_cfg: UniverseConfig,
    standardize_cfg: StandardizeConfig,
    test_cfg: FactorTestConfig,
    combo_cfg: FactorComboSearchConfig,
    backtest_cfg: BacktestConfig,
) -> Dict[str, Any]:
    os.makedirs(REPORT_DIR, exist_ok=True)

    research = run_factor_research(
        ohlcv,
        FactorResearchSpec(
            train_start=spec.train_start,
            train_end=spec.train_end,
            oos_start=spec.oos_start,
            oos_end=spec.oos_end,
            candidate_factors=spec.candidate_factors,
        ),
        universe_cfg,
        standardize_cfg,
        test_cfg,
    )

    candidate_pool = select_oriented_factor_pool(
        research["train"],
        research["oos"],
        research["engine"]["factor_definitions"],
        combo_cfg,
    )

    candidate_names = [item["factor"] for item in candidate_pool["candidate_factors"]]
    corr = compute_train_factor_correlation(
        research["standardized_panel"],
        candidate_names,
        spec.train_start,
        spec.train_end,
    )
    combos = generate_low_correlation_combinations(
        candidate_pool["candidate_factors"],
        research["engine"]["factor_definitions"],
        corr,
        combo_cfg,
    )

    evaluated: List[Dict[str, Any]] = []
    for combo in combos["shortlisted_combinations"]:
        weights = combo["factor_weights"]
        train_result = run_composite_portfolio(
            ohlcv,
            research["standardized_panel"],
            combo["factors"],
            FactorPortfolioSpec(
                start=spec.train_start,
                end=spec.train_end,
                top_n=spec.top_n,
                rebalance_every_n_days=spec.rebalance_every_n_days,
                factor_weights=weights,
                trade_filters=spec.trade_filters,
            ),
            backtest_cfg,
            raw_panel=research["raw_panel"],
        )
        oos_result = run_composite_portfolio(
            ohlcv,
            research["standardized_panel"],
            combo["factors"],
            FactorPortfolioSpec(
                start=spec.oos_start,
                end=spec.oos_end,
                top_n=spec.top_n,
                rebalance_every_n_days=spec.rebalance_every_n_days,
                factor_weights=weights,
                trade_filters=spec.trade_filters,
            ),
            backtest_cfg,
            raw_panel=research["raw_panel"],
        )
        stable = (
            _metric_value(train_result["metrics"], "sharpe") > 0.0
            and _metric_value(oos_result["metrics"], "sharpe") > 0.0
            and _metric_value(oos_result["metrics"], "cagr") > 0.0
        )
        evaluated.append(
            {
                **combo,
                "train_metrics": train_result["metrics"],
                "train_latest_picks": train_result["latest_picks"],
                "train_filter_diagnostics": train_result.get("filter_diagnostics", {}),
                "oos_metrics": oos_result["metrics"],
                "oos_latest_picks": oos_result["latest_picks"],
                "oos_filter_diagnostics": oos_result.get("filter_diagnostics", {}),
                "stable_on_train_and_oos": stable,
                "stability_score": _combo_stability_score(
                    train_result["metrics"],
                    oos_result["metrics"],
                    combo["max_abs_corr"],
                ),
            }
        )

    evaluated = sorted(
        evaluated,
        key=lambda item: (
            item["stable_on_train_and_oos"],
            item["stability_score"],
            _metric_value(item["oos_metrics"], "sharpe"),
            _metric_value(item["oos_metrics"], "cagr"),
        ),
        reverse=True,
    )

    best = evaluated[0] if evaluated else None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(REPORT_DIR, f"alpha_combo_search_{stamp}.json")
    md_path = os.path.join(REPORT_DIR, f"alpha_combo_search_{stamp}.md")
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "spec": asdict(spec),
        "research": {
            "engine": research["engine"],
            "train": research["train"],
            "oos": research["oos"],
        },
        "combo_search": {
            "config": asdict(combo_cfg),
            "candidate_pool": candidate_pool["candidate_factors"],
            "dropped_factors": candidate_pool["dropped_factors"],
            "candidate_correlation_matrix": corr.round(4).to_dict(),
            "raw_combo_count": combos["raw_combo_count"],
            "evaluated_combinations": evaluated,
        },
        "best_combination": best,
        "report_files": {
            "json": json_path,
            "markdown": md_path,
        },
    }
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    _write_markdown_report(summary, md_path)
    frozen_path = _freeze_best_combo(summary)
    summary["frozen_model_path"] = frozen_path

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    return summary
