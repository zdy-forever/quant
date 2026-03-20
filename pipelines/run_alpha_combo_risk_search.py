"""
低相关 Alpha 组合的风险参数搜索模块。

这个文件专门解决一个更现实的问题：
- 当前 alpha 组合是不是赚钱
- 但回撤会不会太大

所以这里不再搜索“哪个因子最好”，而是固定当前最优组合后，
专门搜索更保守的持仓数、总敞口、硬止损和持有期，
尽量把最大回撤压下来。
"""
from __future__ import annotations

import itertools
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

from backtest.engine import BacktestConfig
from pipelines.run_composite_portfolio import FactorPortfolioSpec, run_composite_portfolio
from pipelines.run_factor_research import FactorResearchSpec, run_factor_research
from research.factor_engine import UniverseConfig
from research.factor_tests import FactorTestConfig
from research.standardize import StandardizeConfig

REPORT_DIR = os.path.join("artifacts", "reports")
SELECTED_DIR = os.path.join("artifacts", "selected_factors")


@dataclass(frozen=True)
class AlphaComboRiskSearchSpec:
    train_start: str
    train_end: str
    oos_start: str
    oos_end: str
    model_path: str = os.path.join("artifacts", "selected_factors", "low_corr_alpha_model.json")
    output_model_path: str | None = None
    target_max_dd: float = 0.15
    trade_filters: Dict[str, float] | None = None
    gross_exposure_grid: List[float] | None = None
    top_n_grid: List[int] | None = None
    stop_loss_grid: List[float] | None = None
    trailing_stop_grid: List[float] | None = None
    max_holding_days_grid: List[int] | None = None
    portfolio_soft_dd_grid: List[float] | None = None
    portfolio_deleverage_grid: List[float] | None = None
    portfolio_hard_dd_grid: List[float] | None = None
    portfolio_cooldown_days_grid: List[int] | None = None


def _load_model(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _extract_model_inputs(model: Dict[str, Any], backtest_cfg: BacktestConfig) -> Dict[str, Any]:
    if "best_combination" in model:
        best_combo = model["best_combination"]
        return {
            "selected_factors": list(best_combo["factors"]),
            "factor_weights": {str(k): float(v) for k, v in best_combo["factor_weights"].items()},
            "trade_filters": model.get("spec", {}).get("trade_filters", {}) or {},
            "base_overrides": {},
            "base_top_n": int(model.get("spec", {}).get("top_n", backtest_cfg.max_positions)),
        }

    best_risk = model.get("best_risk_candidate", {}) or {}
    base_overrides = {str(k): v for k, v in (best_risk.get("risk_overrides", {}) or {}).items()}
    base_top_n = int(base_overrides.pop("top_n", backtest_cfg.max_positions))
    return {
        "selected_factors": list(model.get("factors", [])),
        "factor_weights": {str(k): float(v) for k, v in (model.get("factor_weights", {}) or {}).items()},
        "trade_filters": model.get("trade_filters", {}) or {},
        "base_overrides": base_overrides,
        "base_top_n": base_top_n,
    }


def _metric_value(metrics: Dict[str, Any], name: str) -> float:
    return float(metrics.get(name, 0.0) or 0.0)


def _score_candidate(train_metrics: Dict[str, Any], oos_metrics: Dict[str, Any], target_max_dd: float) -> tuple:
    oos_dd = abs(_metric_value(oos_metrics, "max_dd"))
    train_dd = abs(_metric_value(train_metrics, "max_dd"))
    feasible = oos_dd <= target_max_dd
    if feasible:
        return (
            True,
            _metric_value(oos_metrics, "sharpe"),
            _metric_value(oos_metrics, "cagr"),
            -oos_dd,
            _metric_value(train_metrics, "sharpe"),
            -train_dd,
        )
    return (
        False,
        -oos_dd,
        _metric_value(oos_metrics, "sharpe"),
        _metric_value(oos_metrics, "cagr"),
        -train_dd,
        _metric_value(train_metrics, "sharpe"),
    )


def _write_markdown_report(summary: Dict[str, Any], path: str) -> None:
    best = summary["best_candidate"]
    lines: List[str] = [
        "# Alpha Combo Risk Search Report",
        "",
        "## Goal",
        "",
        f"- Target max drawdown: `{summary['spec']['target_max_dd']:.2%}`",
        f"- Search count: `{summary['candidate_count']}`",
        "",
        "## Best Candidate",
        "",
        f"- Factors: `{', '.join(summary['model']['best_combination']['factors'])}`",
        f"- Factor weights: `{', '.join(f'{name}:{weight:+.3f}' for name, weight in summary['model']['best_combination']['factor_weights'].items())}`",
        f"- Risk overrides: `{json.dumps(best['risk_overrides'], ensure_ascii=False)}`",
        f"- Train metrics: sharpe={best['train_metrics'].get('sharpe', float('nan')):.3f}, "
        f"cagr={best['train_metrics'].get('cagr', float('nan')):.3%}, "
        f"max_dd={best['train_metrics'].get('max_dd', float('nan')):.3%}",
        f"- OOS metrics: sharpe={best['oos_metrics'].get('sharpe', float('nan')):.3f}, "
        f"cagr={best['oos_metrics'].get('cagr', float('nan')):.3%}, "
        f"max_dd={best['oos_metrics'].get('max_dd', float('nan')):.3%}",
        f"- Meets target drawdown: `{best['meets_target_drawdown']}`",
        "",
        "## Top Candidates",
        "",
    ]

    for idx, row in enumerate(summary["top_candidates"], start=1):
        lines.extend(
            [
                f"### Candidate {idx}",
                "",
                f"- Risk overrides: `{json.dumps(row['risk_overrides'], ensure_ascii=False)}`",
                f"- Train sharpe/cagr/maxdd: `{row['train_metrics'].get('sharpe', float('nan')):.3f}` / "
                f"`{row['train_metrics'].get('cagr', float('nan')):.3%}` / "
                f"`{row['train_metrics'].get('max_dd', float('nan')):.3%}`",
                f"- OOS sharpe/cagr/maxdd: `{row['oos_metrics'].get('sharpe', float('nan')):.3f}` / "
                f"`{row['oos_metrics'].get('cagr', float('nan')):.3%}` / "
                f"`{row['oos_metrics'].get('max_dd', float('nan')):.3%}`",
                f"- Meets target drawdown: `{row['meets_target_drawdown']}`",
                "",
            ]
        )

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def run_alpha_combo_risk_search(
    ohlcv: Any,
    spec: AlphaComboRiskSearchSpec,
    universe_cfg: UniverseConfig,
    standardize_cfg: StandardizeConfig,
    test_cfg: FactorTestConfig,
    backtest_cfg: BacktestConfig,
) -> Dict[str, Any]:
    os.makedirs(REPORT_DIR, exist_ok=True)
    os.makedirs(SELECTED_DIR, exist_ok=True)

    model = _load_model(spec.model_path)
    extracted = _extract_model_inputs(model, backtest_cfg)
    selected_factors = extracted["selected_factors"]
    factor_weights = extracted["factor_weights"]
    resolved_trade_filters = spec.trade_filters if spec.trade_filters is not None else extracted["trade_filters"]
    base_overrides = extracted["base_overrides"]
    base_top_n = int(extracted["base_top_n"])

    research = run_factor_research(
        ohlcv,
        FactorResearchSpec(
            train_start=spec.train_start,
            train_end=spec.train_end,
            oos_start=spec.oos_start,
            oos_end=spec.oos_end,
            candidate_factors=selected_factors,
        ),
        universe_cfg,
        standardize_cfg,
        test_cfg,
    )

    gross_grid = spec.gross_exposure_grid or [float(base_overrides.get("gross_exposure", backtest_cfg.gross_exposure))]
    top_n_grid = spec.top_n_grid or [int(base_top_n)]
    stop_grid = spec.stop_loss_grid or [float(base_overrides.get("stop_loss_pct", backtest_cfg.stop_loss_pct))]
    trailing_grid = spec.trailing_stop_grid or [
        float(base_overrides.get("trailing_stop_atr_multiple", backtest_cfg.trailing_stop_atr_multiple))
    ]
    holding_grid = spec.max_holding_days_grid or [int(base_overrides.get("max_holding_days", backtest_cfg.max_holding_days))]
    soft_dd_grid = spec.portfolio_soft_dd_grid or [0.08, 0.10]
    deleverage_grid = spec.portfolio_deleverage_grid or [0.50, 0.65]
    hard_dd_grid = spec.portfolio_hard_dd_grid or [0.15, 0.18]
    cooldown_grid = spec.portfolio_cooldown_days_grid or [5]

    results: List[Dict[str, Any]] = []
    for (
        gross_exposure,
        top_n,
        stop_loss_pct,
        trailing_stop_atr_multiple,
        max_holding_days,
        portfolio_soft_dd_limit,
        portfolio_deleverage_ratio,
        portfolio_hard_dd_limit,
        portfolio_kill_cooldown_days,
    ) in itertools.product(
        gross_grid,
        top_n_grid,
        stop_grid,
        trailing_grid,
        holding_grid,
        soft_dd_grid,
        deleverage_grid,
        hard_dd_grid,
        cooldown_grid,
    ):
        if float(portfolio_hard_dd_limit) <= float(portfolio_soft_dd_limit):
            continue
        risk_overrides = {
            "gross_exposure": float(gross_exposure),
            "stop_loss_pct": float(stop_loss_pct),
            "take_profit_pct": float(base_overrides.get("take_profit_pct", backtest_cfg.take_profit_pct)),
            "trailing_stop_atr_multiple": float(trailing_stop_atr_multiple),
            "max_holding_days": int(max_holding_days),
            "portfolio_soft_dd_limit": float(portfolio_soft_dd_limit),
            "portfolio_deleverage_ratio": float(portfolio_deleverage_ratio),
            "portfolio_hard_dd_limit": float(portfolio_hard_dd_limit),
            "portfolio_kill_cooldown_days": int(portfolio_kill_cooldown_days),
        }

        train_result = run_composite_portfolio(
            ohlcv,
            research["standardized_panel"],
            selected_factors,
            FactorPortfolioSpec(
                start=spec.train_start,
                end=spec.train_end,
                top_n=int(top_n),
                rebalance_every_n_days=backtest_cfg.rebalance_every_n_days,
                factor_weights=factor_weights,
                trade_filters=resolved_trade_filters,
                backtest_overrides=risk_overrides,
            ),
            backtest_cfg,
            raw_panel=research["raw_panel"],
        )
        oos_result = run_composite_portfolio(
            ohlcv,
            research["standardized_panel"],
            selected_factors,
            FactorPortfolioSpec(
                start=spec.oos_start,
                end=spec.oos_end,
                top_n=int(top_n),
                rebalance_every_n_days=backtest_cfg.rebalance_every_n_days,
                factor_weights=factor_weights,
                trade_filters=resolved_trade_filters,
                backtest_overrides=risk_overrides,
            ),
            backtest_cfg,
            raw_panel=research["raw_panel"],
        )

        oos_dd = abs(_metric_value(oos_result["metrics"], "max_dd"))
        results.append(
            {
                "risk_overrides": {
                    **risk_overrides,
                    "top_n": int(top_n),
                },
                "train_metrics": train_result["metrics"],
                "oos_metrics": oos_result["metrics"],
                "meets_target_drawdown": bool(oos_dd <= spec.target_max_dd),
                "score": _score_candidate(train_result["metrics"], oos_result["metrics"], spec.target_max_dd),
            }
        )

    ranked = sorted(results, key=lambda row: row["score"], reverse=True)
    best_candidate = ranked[0] if ranked else {}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(REPORT_DIR, f"alpha_combo_risk_search_{stamp}.json")
    md_path = os.path.join(REPORT_DIR, f"alpha_combo_risk_search_{stamp}.md")
    if spec.output_model_path:
        frozen_path = spec.output_model_path
    elif os.path.basename(spec.model_path) == "low_corr_alpha_risk_model.json":
        frozen_path = os.path.join(SELECTED_DIR, "low_corr_alpha_overlay_model.json")
    else:
        frozen_path = os.path.join(SELECTED_DIR, "low_corr_alpha_risk_model.json")

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "spec": asdict(spec),
        "model": {
            **model,
            "best_combination": model.get(
                "best_combination",
                {
                    "factors": selected_factors,
                    "factor_weights": factor_weights,
                },
            ),
        },
        "candidate_count": len(results),
        "best_candidate": best_candidate,
        "top_candidates": ranked[:10],
        "report_files": {
            "json": json_path,
            "markdown": md_path,
        },
    }

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    _write_markdown_report(summary, md_path)

    os.makedirs(os.path.dirname(frozen_path), exist_ok=True)
    frozen_payload = {
        "generated_at_utc": summary["generated_at_utc"],
        "base_model_path": spec.model_path,
        "factors": selected_factors,
        "factor_weights": factor_weights,
        "trade_filters": resolved_trade_filters or {},
        "best_risk_candidate": best_candidate,
        "report_files": summary["report_files"],
    }
    with open(frozen_path, "w", encoding="utf-8") as handle:
        json.dump(frozen_payload, handle, ensure_ascii=False, indent=2)

    summary["frozen_model_path"] = frozen_path
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    return summary
