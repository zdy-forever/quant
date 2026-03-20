"""
低相关 Alpha 组合的 regime 切换研究模块。

这里把两件事合在一起做：
- 先按不同市场状态比较现有激进版 / 低回撤版
- 再为每个 regime 单独搜索更贴合的组合，并补一个组合级降杠杆/熔断版本

目标不是把参数越搜越碎，而是把“不同市场状态用不同组合”的规则做成
一套简单、可复现、能解释的选择逻辑。
"""
from __future__ import annotations

import itertools
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from backtest.engine import BacktestConfig, run_signal_backtest
from factors.composite import CompositeConfig, build_composite_score, build_top_n_signal, latest_top_picks
from portfolio.trade_filters import TradeFilterConfig, apply_trade_filters
from regime.detection import RegimeConfig, RegimeLabel, classify_regime_history
from research.factor_combo_search import (
    FactorComboSearchConfig,
    compute_train_factor_correlation,
    generate_low_correlation_combinations,
    select_oriented_factor_pool,
)
from research.factor_engine import UniverseConfig, build_factor_research_panel
from research.factor_tests import FactorTestConfig
from research.ic_analysis import build_forward_returns, compute_ic_summary
from research.quantile_backtest import compute_quantile_summary
from research.standardize import StandardizeConfig

REPORT_DIR = os.path.join("artifacts", "reports")
SELECTED_DIR = os.path.join("artifacts", "selected_factors")
REGIME_ORDER = [label.value for label in RegimeLabel]


@dataclass(frozen=True)
class AlphaComboRegimeSwitchSpec:
    train_start: str
    train_end: str
    oos_start: str
    oos_end: str
    aggressive_model_path: str = os.path.join("artifacts", "selected_factors", "low_corr_alpha_model.json")
    conservative_model_path: str = os.path.join("artifacts", "selected_factors", "low_corr_alpha_risk_model.json")
    candidate_factors: List[str] | None = None
    top_n: int = 10
    rebalance_every_n_days: int = 1
    trade_filters: Dict[str, float] | None = None
    max_drawdown_gap: float = 0.05
    target_max_dd: float = 0.15
    gross_exposure_grid: List[float] | None = None
    portfolio_soft_dd_grid: List[float] | None = None
    portfolio_deleverage_grid: List[float] | None = None
    portfolio_hard_dd_grid: List[float] | None = None
    portfolio_cooldown_days_grid: List[int] | None = None


def _slice_frame(frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    return out[(out["timestamp"] >= start_ts) & (out["timestamp"] <= end_ts)].copy()


def _subset_engine(engine: Dict[str, Any], candidate_factors: List[str] | None) -> Dict[str, Any]:
    if not candidate_factors:
        return engine

    keep = [name for name in engine["factor_names"] if name in set(candidate_factors)]
    raw_meta = [col for col in engine["raw_panel"].columns if col not in engine["factor_names"]]
    std_meta = [col for col in engine["standardized_panel"].columns if col not in engine["factor_names"]]
    return {
        **engine,
        "factor_names": keep,
        "factor_definitions": {name: engine["factor_definitions"][name] for name in keep if name in engine["factor_definitions"]},
        "raw_panel": engine["raw_panel"][raw_meta + keep].copy(),
        "standardized_panel": engine["standardized_panel"][std_meta + keep].copy(),
    }


def _factor_names(panel: pd.DataFrame) -> List[str]:
    return [
        col
        for col in panel.columns
        if col not in {"timestamp", "symbol", "close", "eligible", "avg_dollar_volume_20", "history_days"}
    ]


def _load_model(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _extract_model_inputs(payload: Dict[str, Any], backtest_cfg: BacktestConfig) -> Dict[str, Any]:
    if "best_combination" in payload:
        best_combo = payload["best_combination"]
        return {
            "factors": list(best_combo["factors"]),
            "factor_weights": {str(k): float(v) for k, v in best_combo["factor_weights"].items()},
            "trade_filters": payload.get("spec", {}).get("trade_filters", {}) or {},
            "backtest_overrides": {},
            "top_n": int(payload.get("spec", {}).get("top_n", backtest_cfg.max_positions)),
        }

    best_risk = payload.get("best_risk_candidate", {}) or {}
    risk_overrides = {str(k): v for k, v in (best_risk.get("risk_overrides", {}) or {}).items()}
    top_n = int(risk_overrides.pop("top_n", backtest_cfg.max_positions))
    return {
        "factors": list(payload.get("factors", [])),
        "factor_weights": {str(k): float(v) for k, v in (payload.get("factor_weights", {}) or {}).items()},
        "trade_filters": payload.get("trade_filters", {}) or {},
        "backtest_overrides": risk_overrides,
        "top_n": top_n,
    }


def _build_regime_frame(ohlcv: pd.DataFrame, regime_cfg: RegimeConfig) -> pd.DataFrame:
    labels = classify_regime_history(ohlcv, regime_cfg)
    if labels.empty:
        return pd.DataFrame(columns=["timestamp", "regime"])
    return pd.DataFrame({"timestamp": labels.index, "regime": labels.astype(str).values})


def _filter_by_regime(frame: pd.DataFrame, regime_frame: pd.DataFrame, regime_label: str) -> pd.DataFrame:
    if frame.empty or regime_frame.empty:
        return frame.iloc[0:0].copy()
    merged = frame.copy()
    merged["timestamp"] = pd.to_datetime(merged["timestamp"], utc=True)
    return (
        merged.merge(regime_frame, on="timestamp", how="left")
        .loc[lambda x: x["regime"] == regime_label]
        .drop(columns=["regime"])
        .copy()
    )


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


def _overlay_candidate_score(train_metrics: Dict[str, Any], oos_metrics: Dict[str, Any], target_max_dd: float) -> tuple:
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


def _select_variant(
    aggressive: Dict[str, Any] | None,
    conservative: Dict[str, Any] | None,
    max_drawdown_gap: float,
) -> Dict[str, Any]:
    if aggressive is None and conservative is None:
        return {"selected_variant": "none", "selection_reason": "没有可用组合"}
    if aggressive is None:
        return {"selected_variant": "conservative", "selection_reason": "只有低回撤版本可用"}
    if conservative is None:
        return {"selected_variant": "aggressive", "selection_reason": "只有激进版本可用"}

    aggressive_dd = abs(_metric_value(aggressive["oos_metrics"], "max_dd"))
    conservative_dd = abs(_metric_value(conservative["oos_metrics"], "max_dd"))
    if aggressive_dd <= conservative_dd + float(max_drawdown_gap):
        return {
            "selected_variant": "aggressive",
            "selection_reason": (
                f"激进版 OOS MaxDD={aggressive_dd:.2%}，未超过低回撤版 {conservative_dd:.2%} "
                f"+ 容忍差 {float(max_drawdown_gap):.2%}"
            ),
        }
    return {
        "selected_variant": "conservative",
        "selection_reason": (
            f"激进版 OOS MaxDD={aggressive_dd:.2%}，超过低回撤版 {conservative_dd:.2%} "
            f"+ 容忍差 {float(max_drawdown_gap):.2%}"
        ),
    }


def _run_regime_factor_validation(
    ohlcv: pd.DataFrame,
    standardized_panel: pd.DataFrame,
    regime_frame: pd.DataFrame,
    regime_label: str,
    start: str,
    end: str,
    cfg: FactorTestConfig,
) -> Dict[str, Any]:
    window_ohlcv = _slice_frame(ohlcv, start, end)
    window_panel = _slice_frame(standardized_panel, start, end)
    forward_panel = build_forward_returns(window_ohlcv, cfg.forward_days)
    panel = window_panel.merge(forward_panel.drop(columns=["close"]), on=["timestamp", "symbol"], how="left")
    panel = _filter_by_regime(panel, regime_frame, regime_label)
    panel = panel[panel["eligible"]].copy()

    factor_names = _factor_names(window_panel)
    if panel.empty:
        factors = {
            factor_name: {
                "ic": {str(horizon): np.nan for horizon in cfg.forward_days},
                "rank_ic": {str(horizon): np.nan for horizon in cfg.forward_days},
                "icir": {str(horizon): np.nan for horizon in cfg.forward_days},
                "rank_icir": {str(horizon): np.nan for horizon in cfg.forward_days},
                "quantile": {},
                "top_bottom_spread": np.nan,
                "spread_hit_rate": np.nan,
            }
            for factor_name in factor_names
        }
        return {
            "config": asdict(cfg),
            "factor_names": factor_names,
            "factor_count": len(factor_names),
            "sample_days": 0,
            "factors": factors,
        }

    ic_summary = compute_ic_summary(panel, factor_names, cfg.forward_days, cfg.min_cross_section)
    quantile_summary = compute_quantile_summary(
        panel,
        factor_names,
        cfg.primary_horizon,
        cfg.quantiles,
        cfg.min_cross_section,
    )

    factors: Dict[str, Any] = {}
    for factor_name in factor_names:
        factors[factor_name] = {
            "ic": ic_summary[factor_name]["ic"],
            "rank_ic": ic_summary[factor_name]["rank_ic"],
            "icir": ic_summary[factor_name]["icir"],
            "rank_icir": ic_summary[factor_name]["rank_icir"],
            "quantile": quantile_summary[factor_name]["quantile_returns"],
            "top_bottom_spread": quantile_summary[factor_name]["top_bottom_spread"],
            "spread_hit_rate": quantile_summary[factor_name]["spread_hit_rate"],
        }

    return {
        "config": asdict(cfg),
        "factor_names": factor_names,
        "factor_count": len(factor_names),
        "sample_days": int(panel["timestamp"].nunique()) if not panel.empty else 0,
        "factors": factors,
    }


def _clean_backtest_cfg(
    base_cfg: BacktestConfig,
    top_n: int,
    rebalance_every_n_days: int,
    overrides: Dict[str, Any] | None = None,
) -> BacktestConfig:
    cfg_dict = asdict(base_cfg)
    cfg_dict["max_positions"] = int(top_n)
    cfg_dict["rebalance_every_n_days"] = int(rebalance_every_n_days)
    if overrides:
        cfg_dict.update(overrides)
    return BacktestConfig(**cfg_dict)


def _run_combo_backtest(
    ohlcv: pd.DataFrame,
    standardized_panel: pd.DataFrame,
    raw_panel: pd.DataFrame | None,
    selected_factors: List[str],
    factor_weights: Dict[str, float],
    start: str,
    end: str,
    top_n: int,
    rebalance_every_n_days: int,
    trade_filters: Dict[str, float] | None,
    backtest_cfg: BacktestConfig,
    backtest_overrides: Dict[str, Any] | None = None,
    regime_frame: pd.DataFrame | None = None,
    regime_label: str | None = None,
) -> Dict[str, Any]:
    window_ohlcv = _slice_frame(ohlcv, start, end)
    window_panel = _slice_frame(standardized_panel, start, end)
    window_raw_panel = _slice_frame(raw_panel, start, end) if raw_panel is not None else None

    composite_cfg = CompositeConfig(
        top_n=top_n,
        weighting="custom" if factor_weights else "equal",
        rebalance_every_n_days=rebalance_every_n_days,
    )
    score_frame = build_composite_score(
        window_panel,
        selected_factors,
        composite_cfg,
        custom_weights=factor_weights or None,
    )

    filter_diagnostics: Dict[str, Any] = {}
    if trade_filters and window_raw_panel is not None:
        score_frame, filter_diagnostics = apply_trade_filters(
            score_frame,
            window_raw_panel,
            TradeFilterConfig(**trade_filters),
        )

    if regime_frame is not None and regime_label:
        score_frame = _filter_by_regime(score_frame, regime_frame, regime_label)

    signal = build_top_n_signal(score_frame, top_n)
    result = run_signal_backtest(
        window_ohlcv,
        signal,
        score_frame.set_index(["timestamp", "symbol"])["score"] if not score_frame.empty else None,
        _clean_backtest_cfg(backtest_cfg, top_n, rebalance_every_n_days, backtest_overrides),
    )
    return {
        "metrics": result["metrics"],
        "latest_picks": latest_top_picks(score_frame, top_n),
        "filter_diagnostics": filter_diagnostics,
        "risk_overlay": result.get("risk_overlay", {}),
        "signal_days": int(score_frame["timestamp"].nunique()) if not score_frame.empty else 0,
    }


def _search_overlay_variant(
    ohlcv: pd.DataFrame,
    standardized_panel: pd.DataFrame,
    raw_panel: pd.DataFrame,
    regime_frame: pd.DataFrame,
    regime_label: str,
    selected_factors: List[str],
    factor_weights: Dict[str, float],
    spec: AlphaComboRegimeSwitchSpec,
    backtest_cfg: BacktestConfig,
) -> Dict[str, Any] | None:
    gross_grid = spec.gross_exposure_grid or [0.75, 1.0]
    soft_grid = spec.portfolio_soft_dd_grid or [0.08, 0.10]
    deleverage_grid = spec.portfolio_deleverage_grid or [0.50, 0.65]
    hard_grid = spec.portfolio_hard_dd_grid or [0.15, 0.18]
    cooldown_grid = spec.portfolio_cooldown_days_grid or [5]

    candidates: List[Dict[str, Any]] = []
    for gross_exposure, soft_dd, deleverage_ratio, hard_dd, cooldown_days in itertools.product(
        gross_grid,
        soft_grid,
        deleverage_grid,
        hard_grid,
        cooldown_grid,
    ):
        if float(hard_dd) <= float(soft_dd):
            continue
        risk_overrides = {
            "gross_exposure": float(gross_exposure),
            "portfolio_soft_dd_limit": float(soft_dd),
            "portfolio_deleverage_ratio": float(deleverage_ratio),
            "portfolio_hard_dd_limit": float(hard_dd),
            "portfolio_kill_cooldown_days": int(cooldown_days),
        }
        train_result = _run_combo_backtest(
            ohlcv,
            standardized_panel,
            raw_panel,
            selected_factors,
            factor_weights,
            spec.train_start,
            spec.train_end,
            spec.top_n,
            spec.rebalance_every_n_days,
            spec.trade_filters,
            backtest_cfg,
            backtest_overrides=risk_overrides,
            regime_frame=regime_frame,
            regime_label=regime_label,
        )
        oos_result = _run_combo_backtest(
            ohlcv,
            standardized_panel,
            raw_panel,
            selected_factors,
            factor_weights,
            spec.oos_start,
            spec.oos_end,
            spec.top_n,
            spec.rebalance_every_n_days,
            spec.trade_filters,
            backtest_cfg,
            backtest_overrides=risk_overrides,
            regime_frame=regime_frame,
            regime_label=regime_label,
        )
        candidates.append(
            {
                "factors": selected_factors,
                "factor_weights": factor_weights,
                "risk_overrides": risk_overrides,
                "train_metrics": train_result["metrics"],
                "oos_metrics": oos_result["metrics"],
                "train_latest_picks": train_result["latest_picks"],
                "oos_latest_picks": oos_result["latest_picks"],
                "risk_overlay": oos_result["risk_overlay"],
                "score": _overlay_candidate_score(train_result["metrics"], oos_result["metrics"], spec.target_max_dd),
            }
        )

    ranked = sorted(candidates, key=lambda row: row["score"], reverse=True)
    return ranked[0] if ranked else None


def _regime_window_mix(regime_frame: pd.DataFrame, start: str, end: str) -> Dict[str, float]:
    sample = _slice_frame(regime_frame, start, end)
    if sample.empty:
        return {}
    counts = sample["regime"].value_counts(normalize=True).to_dict()
    return {str(k): float(v) for k, v in counts.items()}


def _write_markdown_report(summary: Dict[str, Any], path: str) -> None:
    lines: List[str] = [
        "# Alpha Combo Regime Switch Report",
        "",
        "## Summary",
        "",
        f"- Generated at UTC: `{summary['generated_at_utc']}`",
        f"- Train window: `{summary['spec']['train_start']}` -> `{summary['spec']['train_end']}`",
        f"- OOS window: `{summary['spec']['oos_start']}` -> `{summary['spec']['oos_end']}`",
        f"- Max drawdown gap rule: `{summary['spec']['max_drawdown_gap']:.2%}`",
        f"- Overlay target max drawdown: `{summary['spec']['target_max_dd']:.2%}`",
        f"- Train regime mix: `{json.dumps(summary['train_regime_mix'], ensure_ascii=False)}`",
        f"- OOS regime mix: `{json.dumps(summary['oos_regime_mix'], ensure_ascii=False)}`",
        "",
        "## Selected Models By Regime",
        "",
    ]

    for regime_label in REGIME_ORDER:
        row = summary["regime_models"].get(regime_label, {})
        selection = row.get("selection", {})
        lines.extend(
            [
                f"### {regime_label}",
                "",
                f"- Selection: `{selection.get('selected_variant', 'none')}`",
                f"- Reason: `{selection.get('selection_reason', '-')}`",
            ]
        )
        aggressive = row.get("aggressive")
        conservative = row.get("conservative")
        if aggressive:
            lines.append(
                f"- Aggressive factors: `{', '.join(aggressive.get('factors', []))}` | "
                f"OOS sharpe={aggressive['oos_metrics'].get('sharpe', float('nan')):.3f}, "
                f"cagr={aggressive['oos_metrics'].get('cagr', float('nan')):.3%}, "
                f"max_dd={aggressive['oos_metrics'].get('max_dd', float('nan')):.3%}"
            )
        if conservative:
            lines.append(
                f"- Conservative factors: `{', '.join(conservative.get('factors', []))}` | "
                f"OOS sharpe={conservative['oos_metrics'].get('sharpe', float('nan')):.3f}, "
                f"cagr={conservative['oos_metrics'].get('cagr', float('nan')):.3%}, "
                f"max_dd={conservative['oos_metrics'].get('max_dd', float('nan')):.3%}"
            )
        if row.get("fallback_used"):
            lines.append("- Note: 该 regime 样本不足，沿用了当前冻结模型对比结果。")
        lines.append("")

    lines.extend(
        [
            "## Notes",
            "",
            "- 这里的 regime 研究用的是简单规则：先比较同一 regime 下激进版和低回撤版，再按 OOS 回撤差阈值决定选谁。",
            "- 组合级风控只搜索总敞口和组合回撤闸门，不继续默认收紧单票止损，尽量避免把结果调成样本内好看。",
            "- 如果某个 regime 的样本天数太少，报告会直接退回到当前冻结模型，不会强行编一个新组合。",
            "",
        ]
    )

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def run_alpha_combo_regime_switch(
    ohlcv: pd.DataFrame,
    regime_ohlcv: pd.DataFrame,
    spec: AlphaComboRegimeSwitchSpec,
    universe_cfg: UniverseConfig,
    standardize_cfg: StandardizeConfig,
    test_cfg: FactorTestConfig,
    combo_cfg: FactorComboSearchConfig,
    backtest_cfg: BacktestConfig,
    regime_cfg: RegimeConfig,
) -> Dict[str, Any]:
    os.makedirs(REPORT_DIR, exist_ok=True)
    os.makedirs(SELECTED_DIR, exist_ok=True)

    engine = build_factor_research_panel(ohlcv, universe_cfg, standardize_cfg)
    engine = _subset_engine(engine, spec.candidate_factors)
    regime_frame = _build_regime_frame(regime_ohlcv, regime_cfg)

    aggressive_payload = _extract_model_inputs(_load_model(spec.aggressive_model_path), backtest_cfg)
    conservative_payload = _extract_model_inputs(_load_model(spec.conservative_model_path), backtest_cfg)

    frozen_comparison: Dict[str, Any] = {}
    for regime_label in REGIME_ORDER:
        aggressive = {
            "factors": aggressive_payload["factors"],
            "factor_weights": aggressive_payload["factor_weights"],
            "train_metrics": _run_combo_backtest(
                ohlcv,
                engine["standardized_panel"],
                engine["raw_panel"],
                aggressive_payload["factors"],
                aggressive_payload["factor_weights"],
                spec.train_start,
                spec.train_end,
                aggressive_payload["top_n"],
                spec.rebalance_every_n_days,
                spec.trade_filters or aggressive_payload["trade_filters"],
                backtest_cfg,
                backtest_overrides=aggressive_payload["backtest_overrides"],
                regime_frame=regime_frame,
                regime_label=regime_label,
            )["metrics"],
            "oos_metrics": _run_combo_backtest(
                ohlcv,
                engine["standardized_panel"],
                engine["raw_panel"],
                aggressive_payload["factors"],
                aggressive_payload["factor_weights"],
                spec.oos_start,
                spec.oos_end,
                aggressive_payload["top_n"],
                spec.rebalance_every_n_days,
                spec.trade_filters or aggressive_payload["trade_filters"],
                backtest_cfg,
                backtest_overrides=aggressive_payload["backtest_overrides"],
                regime_frame=regime_frame,
                regime_label=regime_label,
            )["metrics"],
        }
        conservative = {
            "factors": conservative_payload["factors"],
            "factor_weights": conservative_payload["factor_weights"],
            "train_metrics": _run_combo_backtest(
                ohlcv,
                engine["standardized_panel"],
                engine["raw_panel"],
                conservative_payload["factors"],
                conservative_payload["factor_weights"],
                spec.train_start,
                spec.train_end,
                conservative_payload["top_n"],
                spec.rebalance_every_n_days,
                spec.trade_filters or conservative_payload["trade_filters"],
                backtest_cfg,
                backtest_overrides=conservative_payload["backtest_overrides"],
                regime_frame=regime_frame,
                regime_label=regime_label,
            )["metrics"],
            "oos_metrics": _run_combo_backtest(
                ohlcv,
                engine["standardized_panel"],
                engine["raw_panel"],
                conservative_payload["factors"],
                conservative_payload["factor_weights"],
                spec.oos_start,
                spec.oos_end,
                conservative_payload["top_n"],
                spec.rebalance_every_n_days,
                spec.trade_filters or conservative_payload["trade_filters"],
                backtest_cfg,
                backtest_overrides=conservative_payload["backtest_overrides"],
                regime_frame=regime_frame,
                regime_label=regime_label,
            )["metrics"],
        }
        frozen_comparison[regime_label] = {
            "aggressive": aggressive,
            "conservative": conservative,
            "selection": _select_variant(aggressive, conservative, spec.max_drawdown_gap),
        }

    regime_models: Dict[str, Any] = {}
    for regime_label in REGIME_ORDER:
        train_validation = _run_regime_factor_validation(
            ohlcv,
            engine["standardized_panel"],
            regime_frame,
            regime_label,
            spec.train_start,
            spec.train_end,
            test_cfg,
        )
        oos_validation = _run_regime_factor_validation(
            ohlcv,
            engine["standardized_panel"],
            regime_frame,
            regime_label,
            spec.oos_start,
            spec.oos_end,
            test_cfg,
        )
        candidate_pool = select_oriented_factor_pool(
            train_validation,
            oos_validation,
            engine["factor_definitions"],
            combo_cfg,
        )
        candidate_names = [item["factor"] for item in candidate_pool["candidate_factors"]]
        corr_input = _filter_by_regime(_slice_frame(engine["standardized_panel"], spec.train_start, spec.train_end), regime_frame, regime_label)
        corr = compute_train_factor_correlation(corr_input, candidate_names, spec.train_start, spec.train_end)
        combo_candidates = generate_low_correlation_combinations(
            candidate_pool["candidate_factors"],
            engine["factor_definitions"],
            corr,
            combo_cfg,
        )

        aggressive_rows: List[Dict[str, Any]] = []
        for combo in combo_candidates["shortlisted_combinations"]:
            train_result = _run_combo_backtest(
                ohlcv,
                engine["standardized_panel"],
                engine["raw_panel"],
                combo["factors"],
                combo["factor_weights"],
                spec.train_start,
                spec.train_end,
                spec.top_n,
                spec.rebalance_every_n_days,
                spec.trade_filters,
                backtest_cfg,
                regime_frame=regime_frame,
                regime_label=regime_label,
            )
            oos_result = _run_combo_backtest(
                ohlcv,
                engine["standardized_panel"],
                engine["raw_panel"],
                combo["factors"],
                combo["factor_weights"],
                spec.oos_start,
                spec.oos_end,
                spec.top_n,
                spec.rebalance_every_n_days,
                spec.trade_filters,
                backtest_cfg,
                regime_frame=regime_frame,
                regime_label=regime_label,
            )
            aggressive_rows.append(
                {
                    "factors": combo["factors"],
                    "factor_weights": combo["factor_weights"],
                    "max_abs_corr": combo["max_abs_corr"],
                    "avg_abs_corr": combo["avg_abs_corr"],
                    "train_metrics": train_result["metrics"],
                    "oos_metrics": oos_result["metrics"],
                    "train_latest_picks": train_result["latest_picks"],
                    "oos_latest_picks": oos_result["latest_picks"],
                    "stability_score": _combo_stability_score(train_result["metrics"], oos_result["metrics"], combo["max_abs_corr"]),
                }
            )

        aggressive_ranked = sorted(aggressive_rows, key=lambda row: row["stability_score"], reverse=True)
        aggressive_best = aggressive_ranked[0] if aggressive_ranked else None
        conservative_best = None
        fallback_used = False

        if aggressive_best is not None:
            conservative_best = _search_overlay_variant(
                ohlcv,
                engine["standardized_panel"],
                engine["raw_panel"],
                regime_frame,
                regime_label,
                aggressive_best["factors"],
                aggressive_best["factor_weights"],
                spec,
                backtest_cfg,
            )

        if aggressive_best is None:
            fallback_used = True
            aggressive_best = {
                **frozen_comparison[regime_label]["aggressive"],
                "factors": aggressive_payload["factors"],
                "factor_weights": aggressive_payload["factor_weights"],
            }
            conservative_best = {
                **frozen_comparison[regime_label]["conservative"],
                "factors": conservative_payload["factors"],
                "factor_weights": conservative_payload["factor_weights"],
                "risk_overrides": conservative_payload["backtest_overrides"],
            }

        selection = _select_variant(aggressive_best, conservative_best, spec.max_drawdown_gap)
        regime_models[regime_label] = {
            "candidate_pool": candidate_pool["candidate_factors"],
            "dropped_factors": candidate_pool["dropped_factors"],
            "train_sample_days": train_validation["sample_days"],
            "oos_sample_days": oos_validation["sample_days"],
            "aggressive_candidate_count": len(aggressive_rows),
            "aggressive": aggressive_best,
            "conservative": conservative_best,
            "selection": selection,
            "fallback_used": fallback_used,
        }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(REPORT_DIR, f"alpha_combo_regime_switch_{stamp}.json")
    md_path = os.path.join(REPORT_DIR, f"alpha_combo_regime_switch_{stamp}.md")
    frozen_path = os.path.join(SELECTED_DIR, "regime_switch_alpha_model.json")

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "spec": asdict(spec),
        "combo_search_config": asdict(combo_cfg),
        "train_regime_mix": _regime_window_mix(regime_frame, spec.train_start, spec.train_end),
        "oos_regime_mix": _regime_window_mix(regime_frame, spec.oos_start, spec.oos_end),
        "frozen_model_comparison": frozen_comparison,
        "regime_models": regime_models,
        "report_files": {
            "json": json_path,
            "markdown": md_path,
        },
        "frozen_model_path": frozen_path,
    }

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    _write_markdown_report(summary, md_path)

    with open(frozen_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "generated_at_utc": summary["generated_at_utc"],
                "spec": summary["spec"],
                "train_regime_mix": summary["train_regime_mix"],
                "oos_regime_mix": summary["oos_regime_mix"],
                "regime_models": summary["regime_models"],
                "report_files": summary["report_files"],
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )

    return summary
