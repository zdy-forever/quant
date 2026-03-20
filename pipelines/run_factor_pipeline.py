"""
因子驱动总流水线模块。

这是新的核心入口：
- 先做单因子研究
- 再做稳定因子筛选与冻结
- 再做 composite factor 组合回测
- 最后做 factor walk-forward

它代表项目从“策略驱动”转向“研究驱动”的主流程。
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
from pipelines.run_factor_selection import FactorFreezeSpec, run_factor_selection
from pipelines.run_walk_forward import FactorWalkForwardSpec, run_factor_walk_forward
from research.factor_engine import UniverseConfig
from research.factor_selection import FactorSelectionConfig
from research.factor_tests import FactorTestConfig
from research.standardize import StandardizeConfig

REPORT_DIR = os.path.join("artifacts", "reports")


@dataclass(frozen=True)
class FactorPipelineSpec:
    train_start: str
    train_end: str
    oos_start: str
    oos_end: str
    walk_forward_start: str
    walk_forward_end: str
    candidate_factors: List[str] | None = None
    top_n: int = 10
    rebalance_every_n_days: int = 1
    overwrite_frozen: bool = True
    walk_forward_train_years: int = 3
    walk_forward_test_months: int = 6
    walk_forward_step_months: int = 6
    walk_forward_gap_days: int = 1


def _write_markdown_report(summary: Dict[str, Any], path: str) -> None:
    research = summary["research"]
    selection = summary["selection"]
    composite = summary["composite_oos"]
    walk_forward = summary["walk_forward"]
    train_factors = research["train"]["factors"]
    oos_factors = research["oos"]["factors"]
    definitions = research["engine"]["factor_definitions"]

    lines: List[str] = [
        "# Factor Research Report",
        "",
        "## Run Summary",
        "",
        f"- Generated at UTC: `{summary['generated_at_utc']}`",
        f"- Universe avg daily eligible count: `{research['engine']['universe_stats']['avg_daily_eligible_count']:.1f}`",
        f"- Train window: `{summary['spec']['train_start']}` -> `{summary['spec']['train_end']}`",
        f"- OOS window: `{summary['spec']['oos_start']}` -> `{summary['spec']['oos_end']}`",
        f"- Candidate factor count: `{len(research['engine']['factor_names'])}`",
        f"- Train selected factors: `{', '.join(selection['train_selected_factors']) if selection['train_selected_factors'] else 'none'}`",
        f"- Stable factors: `{', '.join(selection['stable_factors']) if selection['stable_factors'] else 'none'}`",
        "",
        "## Factor Sources",
        "",
    ]

    for factor_name in research["engine"]["factor_names"]:
        meta = definitions[factor_name]
        lines.append(
            f"- `{factor_name}`: {meta['description']} "
            f"(source: [{meta['source_title']}]({meta['source_url']}), {meta['source_note']})"
        )

    lines.extend(["", "## Single-Factor Validation", ""])
    for factor_name in research["engine"]["factor_names"]:
        train_rank_ic = train_factors[factor_name]["rank_ic"][str(research["train"]["config"]["primary_horizon"])]
        oos_rank_ic = oos_factors[factor_name]["rank_ic"][str(research["oos"]["config"]["primary_horizon"])]
        train_spread = train_factors[factor_name]["top_bottom_spread"]
        oos_spread = oos_factors[factor_name]["top_bottom_spread"]
        lines.append(
            f"- `{factor_name}`: train_rank_ic={train_rank_ic:.4f}, "
            f"oos_rank_ic={oos_rank_ic:.4f}, train_spread={train_spread:.4f}, oos_spread={oos_spread:.4f}"
        )

    lines.extend(["", "## Factor Selection", ""])
    if selection["stable_factors"]:
        for factor_name in selection["stable_factors"]:
            lines.append(f"- 保留 `{factor_name}`")
    else:
        lines.append("- 当前没有因子同时通过 train 与 OOS 的稳定性阈值")

    if selection["oos_failed_factors"]:
        lines.append("")
        lines.append("### Dropped In OOS")
        lines.append("")
        for factor_name, reason in selection["oos_failed_factors"].items():
            lines.append(f"- `{factor_name}`: {reason}")

    lines.extend(
        [
            "",
            "## Composite Portfolio",
            "",
            f"- OOS selected factors: `{', '.join(composite['selected_factors']) if composite['selected_factors'] else 'none'}`",
            f"- Latest top picks: `{', '.join(composite['latest_picks']) if composite['latest_picks'] else 'none'}`",
            f"- OOS metrics: sharpe={composite['metrics'].get('sharpe', float('nan')):.3f}, "
            f"cagr={composite['metrics'].get('cagr', float('nan')):.3%}, "
            f"max_dd={composite['metrics'].get('max_dd', float('nan')):.3%}, "
            f"calmar={composite['metrics'].get('calmar', float('nan')):.3f}",
            "",
            "## Walk-Forward",
            "",
            f"- Window count: `{int(walk_forward['window_summary'].get('window_count', 0.0))}`",
            f"- Positive Sharpe ratio: `{walk_forward['window_summary'].get('positive_sharpe_ratio', float('nan')):.1%}`",
            f"- Median Sharpe: `{walk_forward['window_summary'].get('median_sharpe', float('nan')):.3f}`",
            f"- Median CAGR: `{walk_forward['window_summary'].get('median_cagr', float('nan')):.3%}`",
            f"- Worst window MaxDD: `{walk_forward['window_summary'].get('worst_window_max_dd', float('nan')):.3%}`",
            "",
            "## Notes",
            "",
            "- 这份报告优先回答“因子有没有 alpha”，再回答“组合怎么交易”。",
            "- 如果单因子在 train 和 OOS 方向不一致，就不应该急着把它映射成策略。",
            "- 下一步优先继续收紧 stable factor 集合，而不是继续堆更多交易规则。",
            "",
        ]
    )

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _public_research_summary(research: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "spec": research["spec"],
        "engine": research["engine"],
        "train": research["train"],
        "oos": research["oos"],
        "panel_stats": {
            "raw_rows": int(research["raw_panel"].shape[0]),
            "standardized_rows": int(research["standardized_panel"].shape[0]),
        },
    }


def run_factor_pipeline(
    ohlcv: Any,
    spec: FactorPipelineSpec,
    universe_cfg: UniverseConfig,
    standardize_cfg: StandardizeConfig,
    test_cfg: FactorTestConfig,
    selection_cfg: FactorSelectionConfig,
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

    selection = run_factor_selection(
        research,
        selection_cfg,
        freeze_spec=FactorFreezeSpec(overwrite=spec.overwrite_frozen),
    )

    composite = run_composite_portfolio(
        ohlcv,
        research["standardized_panel"],
        selection["stable_factors"] or selection["train_selected_factors"],
        FactorPortfolioSpec(
            start=spec.oos_start,
            end=spec.oos_end,
            top_n=spec.top_n,
            rebalance_every_n_days=spec.rebalance_every_n_days,
        ),
        backtest_cfg,
    )

    walk_forward = run_factor_walk_forward(
        ohlcv,
        research["standardized_panel"],
        test_cfg,
        selection_cfg,
        backtest_cfg,
        FactorWalkForwardSpec(
            start=spec.walk_forward_start,
            end=spec.walk_forward_end,
            train_years=spec.walk_forward_train_years,
            test_months=spec.walk_forward_test_months,
            step_months=spec.walk_forward_step_months,
            gap_days=spec.walk_forward_gap_days,
            top_n=spec.top_n,
        ),
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(REPORT_DIR, f"factor_pipeline_{stamp}.json")
    md_path = os.path.join(REPORT_DIR, f"factor_pipeline_{stamp}.md")
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "spec": asdict(spec),
        "research": _public_research_summary(research),
        "selection": selection,
        "composite_oos": composite,
        "walk_forward": walk_forward,
        "report_files": {
            "json": json_path,
            "markdown": md_path,
        },
    }
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    _write_markdown_report(summary, md_path)
    return summary
