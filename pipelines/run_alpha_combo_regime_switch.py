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

from backtest.engine import BacktestConfig, build_daily_target_weights, combine_strategy_weight_frames, run_signal_backtest, run_weight_backtest
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
from research.factor_tests import FactorTestConfig, build_factor_validation_payload
from research.ml_factor_weights import RidgeWeightConfig, fit_oriented_ridge_factor_weights
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
    top_n_grid: List[int] | None = None
    rebalance_every_n_days: int = 1
    trade_filters: Dict[str, float] | None = None
    max_drawdown_gap: float = 0.05
    target_max_dd: float = 0.15
    target_cagr: float = 0.15
    mix_window_days: int = 63
    mix_step_days: int = 21
    min_mix_sample_days: int = 40
    mixture_neighbor_count: int = 3
    mixture_distance_power: float = 1.0
    gross_exposure_grid: List[float] | None = None
    portfolio_soft_dd_grid: List[float] | None = None
    portfolio_deleverage_grid: List[float] | None = None
    portfolio_hard_dd_grid: List[float] | None = None
    portfolio_cooldown_days_grid: List[int] | None = None
    rebalance_every_n_days_grid: List[int] | None = None
    min_score_threshold_grid: List[float] | None = None
    rank_weight_power_grid: List[float] | None = None
    hold_rank_buffer_grid: List[int] | None = None
    score_hysteresis_grid: List[float] | None = None
    max_holding_days_grid: List[int] | None = None
    stop_loss_pct_grid: List[float] | None = None
    take_profit_pct_grid: List[float] | None = None
    trailing_stop_atr_multiple_grid: List[float] | None = None
    max_entry_turnover_per_rebalance_grid: List[float] | None = None
    dynamic_breadth_score_threshold_grid: List[float] | None = None
    min_dynamic_positions_grid: List[int] | None = None
    min_close_location_1_grid: List[float] | None = None
    max_true_range_pct_1_grid: List[float] | None = None
    max_volume_surprise_5_grid: List[float] | None = None
    max_abs_ma_distance_20_grid: List[float] | None = None
    min_liquidity_20_grid: List[float] | None = None
    enable_ml_weight_search: bool = True


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


def _select_engine_for_factors(
    primary_engine: Dict[str, Any],
    fallback_engine: Dict[str, Any],
    selected_factors: List[str],
) -> Dict[str, Any]:
    primary_names = set(primary_engine.get("factor_names", []))
    if all(name in primary_names for name in selected_factors):
        return primary_engine
    return fallback_engine


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


def _passes_targets(metrics: Dict[str, Any], target_cagr: float, target_max_dd: float) -> bool:
    cagr = _metric_value(metrics, "cagr")
    max_dd = abs(_metric_value(metrics, "max_dd"))
    return np.isfinite(cagr) and np.isfinite(max_dd) and cagr >= float(target_cagr) and max_dd <= float(target_max_dd)


def _metric_priority(metrics: Dict[str, Any], target_cagr: float, target_max_dd: float) -> tuple:
    cagr = _metric_value(metrics, "cagr")
    max_dd = abs(_metric_value(metrics, "max_dd"))
    sharpe = _metric_value(metrics, "sharpe")
    calmar = _metric_value(metrics, "calmar")
    return (
        int(max_dd <= float(target_max_dd)),
        cagr,
        sharpe,
        calmar,
        -max_dd,
        -max(float(target_cagr) - cagr, 0.0),
    )


def _combo_stability_score(
    train_metrics: Dict[str, Any],
    oos_metrics: Dict[str, Any],
    max_abs_corr: float,
    target_cagr: float,
    target_max_dd: float,
) -> float:
    oos_dd_gap = max(abs(_metric_value(oos_metrics, "max_dd")) - float(target_max_dd), 0.0)
    within_dd_bonus = 1.5 if abs(_metric_value(oos_metrics, "max_dd")) <= float(target_max_dd) else 0.0
    return (
        within_dd_bonus
        + 0.20 * _metric_value(train_metrics, "sharpe")
        + 0.45 * _metric_value(oos_metrics, "sharpe")
        + 0.50 * _metric_value(train_metrics, "cagr")
        + 5.0 * _metric_value(oos_metrics, "cagr")
        - 0.70 * abs(_metric_value(oos_metrics, "max_dd"))
        - 0.08 * _metric_value(oos_metrics, "avg_turnover")
        - 0.20 * max_abs_corr
        - 3.0 * oos_dd_gap
    )


def _overlay_candidate_score(
    train_metrics: Dict[str, Any],
    oos_metrics: Dict[str, Any],
    target_max_dd: float,
    target_cagr: float,
    train_filter_diagnostics: Dict[str, Any] | None = None,
    oos_filter_diagnostics: Dict[str, Any] | None = None,
) -> tuple:
    oos_dd = abs(_metric_value(oos_metrics, "max_dd"))
    train_dd = abs(_metric_value(train_metrics, "max_dd"))
    oos_turnover = _metric_value(oos_metrics, "avg_turnover")
    train_blocked_ratio = float((train_filter_diagnostics or {}).get("blocked_ratio", 0.0) or 0.0)
    oos_blocked_ratio = float((oos_filter_diagnostics or {}).get("blocked_ratio", 0.0) or 0.0)
    feasible = oos_dd <= target_max_dd
    if feasible:
        return (
            True,
            _metric_value(oos_metrics, "cagr"),
            _metric_value(oos_metrics, "sharpe"),
            -oos_turnover,
            -oos_blocked_ratio,
            -oos_dd,
            _metric_value(train_metrics, "sharpe"),
            _metric_value(train_metrics, "cagr"),
            -train_blocked_ratio,
            -train_dd,
        )
    return (
        False,
        -max(oos_dd - float(target_max_dd), 0.0),
        _metric_value(oos_metrics, "cagr"),
        _metric_value(oos_metrics, "sharpe"),
        -oos_turnover,
        -oos_blocked_ratio,
        -oos_dd,
        _metric_value(train_metrics, "cagr"),
        -train_blocked_ratio,
        -train_dd,
        _metric_value(train_metrics, "sharpe"),
    )


def _dedupe_override_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        payload = {str(k): row[k] for k in sorted(row)}
        unique[json.dumps(payload, ensure_ascii=False, sort_keys=True)] = payload
    return list(unique.values())


def _build_top_n_grid(spec: AlphaComboRegimeSwitchSpec) -> List[int]:
    if spec.top_n_grid:
        return sorted({max(1, int(value)) for value in spec.top_n_grid})

    base = max(1, int(spec.top_n))
    candidates = {
        base,
        max(4, base - 2),
        max(3, base // 2),
    }
    return sorted(candidates)


def _build_aggressive_gross_grid(spec: AlphaComboRegimeSwitchSpec, backtest_cfg: BacktestConfig) -> List[float]:
    if spec.gross_exposure_grid:
        return sorted({float(value) for value in spec.gross_exposure_grid if float(value) > 0.0})

    base = max(0.1, float(backtest_cfg.gross_exposure))
    candidates = {base}
    if base < 1.25:
        candidates.add(1.25)
    return sorted(candidates)


def _build_execution_overrides_grid(
    spec: AlphaComboRegimeSwitchSpec,
    backtest_cfg: BacktestConfig,
) -> List[Dict[str, Any]]:
    explicit_grid = any(
        grid is not None
        for grid in [
            spec.rebalance_every_n_days_grid,
            spec.min_score_threshold_grid,
            spec.rank_weight_power_grid,
            spec.hold_rank_buffer_grid,
            spec.score_hysteresis_grid,
            spec.max_holding_days_grid,
            spec.stop_loss_pct_grid,
            spec.take_profit_pct_grid,
            spec.trailing_stop_atr_multiple_grid,
            spec.max_entry_turnover_per_rebalance_grid,
            spec.dynamic_breadth_score_threshold_grid,
            spec.min_dynamic_positions_grid,
        ]
    )

    if explicit_grid:
        rows: List[Dict[str, Any]] = []
        for (
            rebalance_every_n_days,
            min_score_threshold,
            rank_weight_power,
            hold_rank_buffer,
            score_hysteresis,
            max_holding_days,
            stop_loss_pct,
            take_profit_pct,
            trailing_stop_atr_multiple,
            max_entry_turnover_per_rebalance,
            dynamic_breadth_score_threshold,
            min_dynamic_positions,
        ) in itertools.product(
            spec.rebalance_every_n_days_grid or [int(spec.rebalance_every_n_days)],
            spec.min_score_threshold_grid or [float(backtest_cfg.min_score_threshold)],
            spec.rank_weight_power_grid or [float(backtest_cfg.rank_weight_power)],
            spec.hold_rank_buffer_grid or [int(backtest_cfg.hold_rank_buffer)],
            spec.score_hysteresis_grid or [float(backtest_cfg.score_hysteresis)],
            spec.max_holding_days_grid or [int(backtest_cfg.max_holding_days)],
            spec.stop_loss_pct_grid or [float(backtest_cfg.stop_loss_pct)],
            spec.take_profit_pct_grid or [float(backtest_cfg.take_profit_pct)],
            spec.trailing_stop_atr_multiple_grid or [float(backtest_cfg.trailing_stop_atr_multiple)],
            spec.max_entry_turnover_per_rebalance_grid or [float(backtest_cfg.max_entry_turnover_per_rebalance)],
            spec.dynamic_breadth_score_threshold_grid or [float(backtest_cfg.dynamic_breadth_score_threshold)],
            spec.min_dynamic_positions_grid or [int(backtest_cfg.min_dynamic_positions)],
        ):
            rows.append(
                {
                    "rebalance_every_n_days": int(rebalance_every_n_days),
                    "min_score_threshold": float(min_score_threshold),
                    "rank_weight_power": float(rank_weight_power),
                    "hold_rank_buffer": int(hold_rank_buffer),
                    "score_hysteresis": float(score_hysteresis),
                    "max_holding_days": int(max_holding_days),
                    "stop_loss_pct": float(stop_loss_pct),
                    "take_profit_pct": float(take_profit_pct),
                    "trailing_stop_atr_multiple": float(trailing_stop_atr_multiple),
                    "max_entry_turnover_per_rebalance": float(max_entry_turnover_per_rebalance),
                    "dynamic_breadth_score_threshold": float(dynamic_breadth_score_threshold),
                    "min_dynamic_positions": int(min_dynamic_positions),
                }
            )
        return _dedupe_override_rows(rows)

    selective_floor = max(0.0, float(backtest_cfg.min_score_threshold))
    runner_stop_loss = max(float(backtest_cfg.stop_loss_pct), 0.05)
    runner_take_profit = max(float(backtest_cfg.take_profit_pct), 0.12)
    runner_trailing_stop = max(float(backtest_cfg.trailing_stop_atr_multiple), 2.0)
    profiles = [
        {},
        {
            "min_score_threshold": selective_floor,
            "hold_rank_buffer": max(1, int(backtest_cfg.hold_rank_buffer)),
            "score_hysteresis": max(0.05, float(backtest_cfg.score_hysteresis)),
        },
        {
            "rank_weight_power": max(1.0, float(backtest_cfg.rank_weight_power)),
        },
        {
            "min_score_threshold": selective_floor,
            "rank_weight_power": max(1.0, float(backtest_cfg.rank_weight_power)),
            "hold_rank_buffer": max(1, int(backtest_cfg.hold_rank_buffer)),
            "score_hysteresis": max(0.05, float(backtest_cfg.score_hysteresis)),
        },
        {
            "min_score_threshold": selective_floor,
            "hold_rank_buffer": max(1, int(backtest_cfg.hold_rank_buffer)),
            "score_hysteresis": max(0.05, float(backtest_cfg.score_hysteresis)),
            "max_entry_turnover_per_rebalance": 0.35,
        },
        {
            "dynamic_breadth_score_threshold": 0.25,
            "min_dynamic_positions": 0,
        },
        {
            "max_holding_days": max(int(backtest_cfg.max_holding_days), 5),
        },
        {
            "rank_weight_power": max(1.5, float(backtest_cfg.rank_weight_power)),
            "max_holding_days": max(int(backtest_cfg.max_holding_days), 5),
            "stop_loss_pct": runner_stop_loss,
            "take_profit_pct": runner_take_profit,
            "trailing_stop_atr_multiple": runner_trailing_stop,
        },
        {
            "min_score_threshold": max(selective_floor, 0.0),
            "rank_weight_power": max(2.0, float(backtest_cfg.rank_weight_power)),
            "dynamic_breadth_score_threshold": 0.25,
            "min_dynamic_positions": 0,
            "stop_loss_pct": runner_stop_loss,
            "take_profit_pct": max(float(backtest_cfg.take_profit_pct), 0.16),
            "trailing_stop_atr_multiple": max(float(backtest_cfg.trailing_stop_atr_multiple), 2.5),
            "max_holding_days": max(int(backtest_cfg.max_holding_days), 7),
        },
        {
            "min_score_threshold": max(selective_floor, 0.0),
            "rank_weight_power": max(2.0, float(backtest_cfg.rank_weight_power)),
            "dynamic_breadth_score_threshold": 0.25,
            "min_dynamic_positions": 0,
            "stop_loss_pct": runner_stop_loss,
            "take_profit_pct": 0.0,
            "trailing_stop_atr_multiple": max(float(backtest_cfg.trailing_stop_atr_multiple), 2.5),
            "max_holding_days": max(int(backtest_cfg.max_holding_days), 10),
        },
    ]
    rebalance_grid = sorted({int(spec.rebalance_every_n_days), 2})
    rows = []
    for profile in profiles:
        for rebalance_every_n_days in rebalance_grid:
            row = dict(profile)
            if int(rebalance_every_n_days) != int(spec.rebalance_every_n_days):
                row["rebalance_every_n_days"] = int(rebalance_every_n_days)
            rows.append(row)
    return _dedupe_override_rows(rows)


def _build_trade_filter_profiles(
    spec: AlphaComboRegimeSwitchSpec,
    base_trade_filters: Dict[str, float] | None,
) -> List[Dict[str, float] | None]:
    base = {
        "min_close_location_1": 0.05,
        "max_true_range_pct_1": 0.09,
        "max_volume_surprise_5": 4.0,
        "max_abs_ma_distance_20": 0.15,
        "min_liquidity_20": 16.0,
    }
    if base_trade_filters:
        base.update({str(k): float(v) for k, v in base_trade_filters.items()})

    explicit_grid = any(
        grid is not None
        for grid in [
            spec.min_close_location_1_grid,
            spec.max_true_range_pct_1_grid,
            spec.max_volume_surprise_5_grid,
            spec.max_abs_ma_distance_20_grid,
            spec.min_liquidity_20_grid,
        ]
    )
    if explicit_grid:
        rows: List[Dict[str, float] | None] = []
        for min_close_location_1, max_true_range_pct_1, max_volume_surprise_5, max_abs_ma_distance_20, min_liquidity_20 in itertools.product(
            spec.min_close_location_1_grid or [base["min_close_location_1"]],
            spec.max_true_range_pct_1_grid or [base["max_true_range_pct_1"]],
            spec.max_volume_surprise_5_grid or [base["max_volume_surprise_5"]],
            spec.max_abs_ma_distance_20_grid or [base["max_abs_ma_distance_20"]],
            spec.min_liquidity_20_grid or [base["min_liquidity_20"]],
        ):
            rows.append(
                {
                    "min_close_location_1": float(min_close_location_1),
                    "max_true_range_pct_1": float(max_true_range_pct_1),
                    "max_volume_surprise_5": float(max_volume_surprise_5),
                    "max_abs_ma_distance_20": float(max_abs_ma_distance_20),
                    "min_liquidity_20": float(min_liquidity_20),
                }
            )
        deduped = _dedupe_override_rows([row for row in rows if row is not None])
        return deduped or [base]

    profiles = [
        base,
        {
            **base,
            "max_true_range_pct_1": min(base["max_true_range_pct_1"], 0.07),
            "max_abs_ma_distance_20": min(base["max_abs_ma_distance_20"], 0.12),
        },
        {
            **base,
            "min_close_location_1": max(base["min_close_location_1"], 0.10),
            "max_volume_surprise_5": min(base["max_volume_surprise_5"], 3.0),
        },
        {
            **base,
            "max_true_range_pct_1": min(base["max_true_range_pct_1"], 0.08),
            "max_volume_surprise_5": min(base["max_volume_surprise_5"], 3.0),
            "max_abs_ma_distance_20": min(base["max_abs_ma_distance_20"], 0.12),
        },
    ]
    return _dedupe_override_rows(profiles)


def _select_variant(
    aggressive: Dict[str, Any] | None,
    conservative: Dict[str, Any] | None,
    max_drawdown_gap: float,
    target_cagr: float,
    target_max_dd: float,
) -> Dict[str, Any]:
    if aggressive is None and conservative is None:
        return {"selected_variant": "none", "selection_reason": "没有可用组合"}
    if aggressive is None:
        return {"selected_variant": "conservative", "selection_reason": "只有低回撤版本可用"}
    if conservative is None:
        return {"selected_variant": "aggressive", "selection_reason": "只有激进版本可用"}

    aggressive_pass = _passes_targets(aggressive["oos_metrics"], target_cagr, target_max_dd)
    conservative_pass = _passes_targets(conservative["oos_metrics"], target_cagr, target_max_dd)
    if aggressive_pass and not conservative_pass:
        return {
            "selected_variant": "aggressive",
            "selection_reason": (
                f"激进版先满足 OOS CAGR>={float(target_cagr):.2%} 且 MaxDD<={float(target_max_dd):.2%}，"
                "低回撤版未同时满足。"
            ),
        }
    if conservative_pass and not aggressive_pass:
        return {
            "selected_variant": "conservative",
            "selection_reason": (
                f"低回撤版先满足 OOS CAGR>={float(target_cagr):.2%} 且 MaxDD<={float(target_max_dd):.2%}，"
                "激进版未同时满足。"
            ),
        }

    aggressive_dd = abs(_metric_value(aggressive["oos_metrics"], "max_dd"))
    conservative_dd = abs(_metric_value(conservative["oos_metrics"], "max_dd"))
    if aggressive_pass and conservative_pass and aggressive_dd <= conservative_dd + float(max_drawdown_gap):
        return {
            "selected_variant": "aggressive",
            "selection_reason": (
                f"激进版 OOS MaxDD={aggressive_dd:.2%}，未超过低回撤版 {conservative_dd:.2%} "
                f"+ 容忍差 {float(max_drawdown_gap):.2%}"
            ),
        }
    if aggressive_pass and conservative_pass:
        return {
            "selected_variant": "conservative",
            "selection_reason": (
                f"激进版 OOS MaxDD={aggressive_dd:.2%}，超过低回撤版 {conservative_dd:.2%} "
                f"+ 容忍差 {float(max_drawdown_gap):.2%}"
            ),
        }

    aggressive_priority = _metric_priority(aggressive["oos_metrics"], target_cagr, target_max_dd)
    conservative_priority = _metric_priority(conservative["oos_metrics"], target_cagr, target_max_dd)
    if aggressive_priority >= conservative_priority:
        return {
            "selected_variant": "aggressive",
            "selection_reason": "两者都未完整达标，按 CAGR 缺口、回撤超额和风险调整收益综合后激进版更优。",
        }
    return {
        "selected_variant": "conservative",
        "selection_reason": "两者都未完整达标，按 CAGR 缺口、回撤超额和风险调整收益综合后低回撤版更优。",
    }


def _run_regime_factor_validation(
    ohlcv: pd.DataFrame,
    standardized_panel: pd.DataFrame,
    regime_frame: pd.DataFrame | None,
    regime_label: str | None,
    start: str,
    end: str,
    cfg: FactorTestConfig,
) -> Dict[str, Any]:
    window_ohlcv = _slice_frame(ohlcv, start, end)
    window_panel = _slice_frame(standardized_panel, start, end)
    from research.ic_analysis import build_forward_returns

    forward_panel = build_forward_returns(window_ohlcv, cfg.forward_days)
    panel = window_panel.merge(forward_panel.drop(columns=["close"]), on=["timestamp", "symbol"], how="left")
    if regime_frame is not None and regime_label:
        panel = _filter_by_regime(panel, regime_frame, regime_label)
    panel = panel[panel["eligible"]].copy()
    factor_names = _factor_names(window_panel)
    return build_factor_validation_payload(panel, factor_names, cfg)


def _fit_ml_combo_weights(
    ohlcv: pd.DataFrame,
    standardized_panel: pd.DataFrame,
    selected_factors: List[str],
    factor_weights: Dict[str, float],
    start: str,
    end: str,
    primary_horizon: int,
    regime_frame: pd.DataFrame | None = None,
    regime_label: str | None = None,
) -> Dict[str, Any] | None:
    if not selected_factors:
        return None

    window_ohlcv = _slice_frame(ohlcv, start, end)
    window_panel = _slice_frame(standardized_panel, start, end)
    if window_panel.empty or window_ohlcv.empty:
        return None

    from research.ic_analysis import build_forward_returns

    forward_panel = build_forward_returns(window_ohlcv, [primary_horizon])
    ret_col = f"fwd_ret_{int(primary_horizon)}"
    panel = window_panel.merge(
        forward_panel[["timestamp", "symbol", ret_col]],
        on=["timestamp", "symbol"],
        how="left",
    )
    if regime_frame is not None and regime_label:
        panel = _filter_by_regime(panel, regime_frame, regime_label)
    if panel.empty:
        return None

    directions = {
        name: 1 if float(factor_weights.get(name, 0.0) or 0.0) >= 0.0 else -1
        for name in selected_factors
    }
    return fit_oriented_ridge_factor_weights(
        panel,
        selected_factors,
        directions,
        ret_col,
        RidgeWeightConfig(),
    )


def _build_combo_weight_variants(
    combo: Dict[str, Any],
    ohlcv: pd.DataFrame,
    standardized_panel: pd.DataFrame,
    spec: AlphaComboRegimeSwitchSpec,
    combo_cfg: FactorComboSearchConfig,
    regime_frame: pd.DataFrame | None = None,
    regime_label: str | None = None,
) -> List[Dict[str, Any]]:
    variants = [
        {
            "factor_weights": dict(combo["factor_weights"]),
            "weighting_method": "heuristic",
            "ml_weight_metadata": {},
        }
    ]
    if not bool(spec.enable_ml_weight_search):
        return variants

    ml_payload = _fit_ml_combo_weights(
        ohlcv,
        standardized_panel,
        combo["factors"],
        combo["factor_weights"],
        spec.train_start,
        spec.train_end,
        combo_cfg.primary_horizon,
        regime_frame=regime_frame,
        regime_label=regime_label,
    )
    if ml_payload is None:
        return variants

    heuristic = combo["factor_weights"]
    ml_weights = ml_payload["factor_weights"]
    diff = sum(abs(float(ml_weights.get(name, 0.0)) - float(heuristic.get(name, 0.0))) for name in combo["factors"])
    if diff <= 0.05:
        return variants

    variants.append(
        {
            "factor_weights": ml_weights,
            "weighting_method": "ridge_ml",
            "ml_weight_metadata": {
                key: value
                for key, value in ml_payload.items()
                if key not in {"factor_weights", "selection_score"}
            },
        }
    )
    return variants


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


def _score_frame_cache_key(
    selected_factors: List[str],
    factor_weights: Dict[str, float],
    top_n: int,
    rebalance_every_n_days: int,
    trade_filters: Dict[str, float] | None,
) -> str:
    return json.dumps(
        {
            "factors": list(selected_factors),
            "factor_weights": {str(k): float(v) for k, v in (factor_weights or {}).items()},
            "top_n": int(top_n),
            "rebalance_every_n_days": int(rebalance_every_n_days),
            "trade_filters": trade_filters or {},
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _build_combo_score_frame_cached(
    cache: Dict[str, Dict[str, Any]],
    standardized_panel: pd.DataFrame,
    raw_panel: pd.DataFrame | None,
    selected_factors: List[str],
    factor_weights: Dict[str, float],
    top_n: int,
    rebalance_every_n_days: int,
    trade_filters: Dict[str, float] | None,
) -> Dict[str, Any]:
    key = _score_frame_cache_key(
        selected_factors,
        factor_weights,
        top_n,
        rebalance_every_n_days,
        trade_filters,
    )
    if key not in cache:
        composite_cfg = CompositeConfig(
            top_n=top_n,
            weighting="custom" if factor_weights else "equal",
            rebalance_every_n_days=rebalance_every_n_days,
        )
        score_frame = build_composite_score(
            standardized_panel,
            selected_factors,
            composite_cfg,
            custom_weights=factor_weights or None,
        )
        filter_diagnostics: Dict[str, Any] = {}
        if trade_filters and raw_panel is not None:
            score_frame, filter_diagnostics = apply_trade_filters(
                score_frame,
                raw_panel,
                TradeFilterConfig(**trade_filters),
            )
        cache[key] = {
            "score_frame": score_frame,
            "filter_diagnostics": filter_diagnostics,
        }
    return cache[key]


def _run_backtest_from_score_frame(
    ohlcv: pd.DataFrame,
    score_frame: pd.DataFrame,
    filter_diagnostics: Dict[str, Any],
    start: str,
    end: str,
    top_n: int,
    rebalance_every_n_days: int,
    backtest_cfg: BacktestConfig,
    backtest_overrides: Dict[str, Any] | None = None,
    regime_frame: pd.DataFrame | None = None,
    regime_label: str | None = None,
    include_latest_picks: bool = False,
) -> Dict[str, Any]:
    window_ohlcv = _slice_frame(ohlcv, start, end)
    window_score_frame = _slice_frame(score_frame, start, end)
    if regime_frame is not None and regime_label:
        window_score_frame = _filter_by_regime(window_score_frame, regime_frame, regime_label)

    signal = build_top_n_signal(window_score_frame, top_n)
    result = run_signal_backtest(
        window_ohlcv,
        signal,
        window_score_frame.set_index(["timestamp", "symbol"])["score"] if not window_score_frame.empty else None,
        _clean_backtest_cfg(backtest_cfg, top_n, rebalance_every_n_days, backtest_overrides),
    )
    return {
        "metrics": result["metrics"],
        "latest_picks": latest_top_picks(window_score_frame, top_n) if include_latest_picks else [],
        "filter_diagnostics": filter_diagnostics,
        "risk_overlay": result.get("risk_overlay", {}),
        "signal_days": int(window_score_frame["timestamp"].nunique()) if not window_score_frame.empty else 0,
    }


def _search_overlay_variant(
    backtest_cache: Dict[str, Dict[str, Any]],
    score_frame_cache: Dict[str, Dict[str, Any]],
    ohlcv: pd.DataFrame,
    standardized_panel: pd.DataFrame,
    raw_panel: pd.DataFrame,
    regime_frame: pd.DataFrame | None,
    regime_label: str | None,
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
    execution_grid = _build_execution_overrides_grid(spec, backtest_cfg)
    trade_filter_profiles = _build_trade_filter_profiles(spec, spec.trade_filters)

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
        for trade_filters in trade_filter_profiles:
            for top_n in _build_top_n_grid(spec):
                for execution_overrides in execution_grid:
                    backtest_overrides = {**risk_overrides, **execution_overrides}
                    train_result = _run_combo_backtest_cached(
                        backtest_cache,
                        score_frame_cache,
                        ohlcv,
                        standardized_panel,
                        raw_panel,
                        selected_factors,
                        factor_weights,
                        spec.train_start,
                        spec.train_end,
                        top_n,
                        spec.rebalance_every_n_days,
                        trade_filters,
                        backtest_cfg,
                        backtest_overrides=backtest_overrides,
                        regime_frame=regime_frame,
                        regime_label=regime_label,
                    )
                    oos_result = _run_combo_backtest_cached(
                        backtest_cache,
                        score_frame_cache,
                        ohlcv,
                        standardized_panel,
                        raw_panel,
                        selected_factors,
                        factor_weights,
                        spec.oos_start,
                        spec.oos_end,
                        top_n,
                        spec.rebalance_every_n_days,
                        trade_filters,
                        backtest_cfg,
                        backtest_overrides=backtest_overrides,
                        regime_frame=regime_frame,
                        regime_label=regime_label,
                    )
                    candidates.append(
                        {
                            "factors": selected_factors,
                            "factor_weights": factor_weights,
                            "top_n": int(top_n),
                            "trade_filters": trade_filters,
                            "risk_overrides": risk_overrides,
                            "execution_overrides": execution_overrides,
                            "backtest_overrides": backtest_overrides,
                            "train_metrics": train_result["metrics"],
                            "oos_metrics": oos_result["metrics"],
                            "train_latest_picks": train_result["latest_picks"],
                            "oos_latest_picks": oos_result["latest_picks"],
                            "train_filter_diagnostics": train_result["filter_diagnostics"],
                            "oos_filter_diagnostics": oos_result["filter_diagnostics"],
                            "risk_overlay": oos_result["risk_overlay"],
                            "score": _overlay_candidate_score(
                                train_result["metrics"],
                                oos_result["metrics"],
                                spec.target_max_dd,
                                spec.target_cagr,
                                train_result["filter_diagnostics"],
                                oos_result["filter_diagnostics"],
                            ),
                        }
                    )

    ranked = sorted(candidates, key=lambda row: row["score"], reverse=True)
    return ranked[0] if ranked else None


def _search_execution_variant(
    backtest_cache: Dict[str, Dict[str, Any]],
    score_frame_cache: Dict[str, Dict[str, Any]],
    ohlcv: pd.DataFrame,
    standardized_panel: pd.DataFrame,
    raw_panel: pd.DataFrame,
    regime_frame: pd.DataFrame | None,
    regime_label: str | None,
    selected_factors: List[str],
    factor_weights: Dict[str, float],
    max_abs_corr: float,
    avg_abs_corr: float,
    spec: AlphaComboRegimeSwitchSpec,
    backtest_cfg: BacktestConfig,
) -> Dict[str, Any] | None:
    candidates: List[Dict[str, Any]] = []
    trade_filter_profiles = _build_trade_filter_profiles(spec, spec.trade_filters)
    gross_grid = _build_aggressive_gross_grid(spec, backtest_cfg)
    for trade_filters in trade_filter_profiles:
        for top_n in _build_top_n_grid(spec):
            for gross_exposure in gross_grid:
                for execution_overrides in _build_execution_overrides_grid(spec, backtest_cfg):
                    backtest_overrides = {
                        **execution_overrides,
                        "gross_exposure": float(gross_exposure),
                    }
                    train_result = _run_combo_backtest_cached(
                        backtest_cache,
                        score_frame_cache,
                        ohlcv,
                        standardized_panel,
                        raw_panel,
                        selected_factors,
                        factor_weights,
                        spec.train_start,
                        spec.train_end,
                        top_n,
                        spec.rebalance_every_n_days,
                        trade_filters,
                        backtest_cfg,
                        backtest_overrides=backtest_overrides,
                        regime_frame=regime_frame,
                        regime_label=regime_label,
                    )
                    oos_result = _run_combo_backtest_cached(
                        backtest_cache,
                        score_frame_cache,
                        ohlcv,
                        standardized_panel,
                        raw_panel,
                        selected_factors,
                        factor_weights,
                        spec.oos_start,
                        spec.oos_end,
                        top_n,
                        spec.rebalance_every_n_days,
                        trade_filters,
                        backtest_cfg,
                        backtest_overrides=backtest_overrides,
                        regime_frame=regime_frame,
                        regime_label=regime_label,
                    )
                    candidates.append(
                        {
                            "factors": selected_factors,
                            "factor_weights": factor_weights,
                            "top_n": int(top_n),
                            "trade_filters": trade_filters,
                            "max_abs_corr": max_abs_corr,
                            "avg_abs_corr": avg_abs_corr,
                            "execution_overrides": execution_overrides,
                            "backtest_overrides": backtest_overrides,
                            "train_metrics": train_result["metrics"],
                            "oos_metrics": oos_result["metrics"],
                            "train_latest_picks": train_result["latest_picks"],
                            "oos_latest_picks": oos_result["latest_picks"],
                            "train_filter_diagnostics": train_result["filter_diagnostics"],
                            "oos_filter_diagnostics": oos_result["filter_diagnostics"],
                            "stability_score": _combo_stability_score(
                                train_result["metrics"],
                                oos_result["metrics"],
                                max_abs_corr,
                                spec.target_cagr,
                                spec.target_max_dd,
                            ) - 0.10 * float(oos_result["filter_diagnostics"].get("blocked_ratio", 0.0) or 0.0),
                        }
                    )

    ranked = sorted(candidates, key=lambda row: row["stability_score"], reverse=True)
    return ranked[0] if ranked else None


def _regime_window_mix(regime_frame: pd.DataFrame, start: str, end: str) -> Dict[str, float]:
    sample = _slice_frame(regime_frame, start, end)
    if sample.empty:
        return {}
    counts = sample["regime"].value_counts(normalize=True).to_dict()
    return {str(k): float(v) for k, v in counts.items()}


def _normalize_mix(mix: Dict[str, float]) -> Dict[str, float]:
    normalized = {label: float(mix.get(label, 0.0) or 0.0) for label in REGIME_ORDER}
    total = sum(normalized.values())
    if total <= 0:
        return {label: 0.0 for label in REGIME_ORDER}
    return {label: value / total for label, value in normalized.items()}


def _mix_distance(left: Dict[str, float], right: Dict[str, float]) -> float:
    left_norm = _normalize_mix(left)
    right_norm = _normalize_mix(right)
    return float(sum(abs(left_norm[label] - right_norm[label]) for label in REGIME_ORDER))


def _resolve_selected_model(window_row: Dict[str, Any]) -> tuple[str, Dict[str, Any] | None]:
    selected_variant = window_row.get("selection", {}).get("selected_variant", "aggressive")
    selected_model = window_row.get(selected_variant) or window_row.get("aggressive") or window_row.get("conservative")
    return selected_variant, selected_model


def _select_mix_neighbors(
    mixture_library: List[Dict[str, Any]],
    target_mix: Dict[str, float],
    neighbor_count: int,
    distance_power: float,
) -> List[Dict[str, Any]]:
    if not mixture_library:
        return []

    ranked = sorted(
        (
            {
                "window": row,
                "distance": _mix_distance(target_mix, row.get("mix", {})),
            }
            for row in mixture_library
        ),
        key=lambda item: (item["distance"], -int(item["window"].get("sample_days", 0))),
    )[: max(1, int(neighbor_count))]

    zero_distance = [item for item in ranked if item["distance"] <= 1e-12]
    if zero_distance:
        weights = [1.0 / float(len(zero_distance)) if item in zero_distance else 0.0 for item in ranked]
    else:
        exponent = max(float(distance_power), 1e-6)
        raw_weights = [1.0 / max(float(item["distance"]), 1e-6) ** exponent for item in ranked]
        total_weight = max(sum(raw_weights), 1e-12)
        weights = [value / total_weight for value in raw_weights]

    neighbors: List[Dict[str, Any]] = []
    for item, weight in zip(ranked, weights):
        selected_variant, selected_model = _resolve_selected_model(item["window"])
        if selected_model is None or weight <= 0.0:
            continue
        neighbors.append(
            {
                "window_label": item["window"].get("window_label", ""),
                "distance": float(item["distance"]),
                "weight": float(weight),
                "selected_variant": selected_variant,
                "selected_model": selected_model,
            }
        )
    return neighbors


def _weighted_int(values: List[int], weights: List[float]) -> int:
    if not values:
        return 1
    return max(1, int(round(sum(float(value) * float(weight) for value, weight in zip(values, weights)))))


def _weighted_numeric_dict(dicts: List[Dict[str, Any]], weights: List[float]) -> Dict[str, float]:
    numeric_keys = sorted(
        {
            key
            for payload in dicts
            for key, value in payload.items()
            if isinstance(value, (int, float, np.integer, np.floating))
        }
    )
    blended: Dict[str, float] = {}
    for key in numeric_keys:
        blended[key] = float(
            sum(float(payload.get(key, 0.0) or 0.0) * float(weight) for payload, weight in zip(dicts, weights))
        )
    return blended


def _build_mix_windows(
    regime_frame: pd.DataFrame,
    start: str,
    end: str,
    window_days: int,
    step_days: int,
    min_sample_days: int,
) -> List[Dict[str, Any]]:
    sample = _slice_frame(regime_frame, start, end)
    if sample.empty:
        return []

    unique_days = sample["timestamp"].drop_duplicates().sort_values().tolist()
    if len(unique_days) < max(1, int(min_sample_days)):
        return []

    windows: List[Dict[str, Any]] = []
    seen_ranges: set[tuple[str, str]] = set()
    end_positions = list(range(max(int(window_days), 1) - 1, len(unique_days), max(int(step_days), 1)))
    if end_positions and end_positions[-1] != len(unique_days) - 1:
        end_positions.append(len(unique_days) - 1)

    for end_pos in end_positions:
        start_pos = max(0, end_pos - max(int(window_days), 1) + 1)
        window_days_slice = unique_days[start_pos : end_pos + 1]
        if len(window_days_slice) < max(1, int(min_sample_days)):
            continue
        window_start = pd.to_datetime(window_days_slice[0], utc=True)
        window_end = pd.to_datetime(window_days_slice[-1], utc=True)
        range_key = (window_start.strftime("%Y-%m-%d"), window_end.strftime("%Y-%m-%d"))
        if range_key in seen_ranges:
            continue
        seen_ranges.add(range_key)
        window_sample = sample[(sample["timestamp"] >= window_start) & (sample["timestamp"] <= window_end)].copy()
        mix = _normalize_mix(window_sample["regime"].value_counts(normalize=True).to_dict())
        windows.append(
            {
                "window_label": f"{range_key[0]}__{range_key[1]}",
                "start": range_key[0],
                "end": range_key[1],
                "sample_days": int(window_sample["timestamp"].nunique()),
                "mix": mix,
            }
        )
    return windows


def _combo_cache_key(
    selected_factors: List[str],
    factor_weights: Dict[str, float],
    start: str,
    end: str,
    top_n: int,
    rebalance_every_n_days: int,
    trade_filters: Dict[str, float] | None,
    backtest_overrides: Dict[str, Any] | None,
    regime_label: str | None,
) -> str:
    return json.dumps(
        {
            "factors": list(selected_factors),
            "factor_weights": {str(k): float(v) for k, v in (factor_weights or {}).items()},
            "start": start,
            "end": end,
            "top_n": int(top_n),
            "rebalance_every_n_days": int(rebalance_every_n_days),
            "trade_filters": trade_filters or {},
            "backtest_overrides": backtest_overrides or {},
            "regime_label": regime_label or "",
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _run_combo_backtest_cached(
    cache: Dict[str, Dict[str, Any]],
    score_frame_cache: Dict[str, Dict[str, Any]],
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
    key = _combo_cache_key(
        selected_factors,
        factor_weights,
        start,
        end,
        top_n,
        rebalance_every_n_days,
        trade_filters,
        backtest_overrides,
        regime_label,
    )
    if key not in cache:
        score_payload = _build_combo_score_frame_cached(
            score_frame_cache,
            standardized_panel,
            raw_panel,
            selected_factors,
            factor_weights,
            top_n,
            rebalance_every_n_days,
            trade_filters,
        )
        cache[key] = _run_backtest_from_score_frame(
            ohlcv,
            score_payload["score_frame"],
            score_payload["filter_diagnostics"],
            start,
            end,
            top_n,
            rebalance_every_n_days,
            backtest_cfg,
            backtest_overrides=backtest_overrides,
            regime_frame=regime_frame,
            regime_label=regime_label,
        )
    return cache[key]


def _window_candidate_score(metrics: Dict[str, Any], target_cagr: float, target_max_dd: float, corr_penalty: float = 0.0) -> tuple:
    return _metric_priority(metrics, target_cagr, target_max_dd) + (-float(corr_penalty),)


def _select_from_window_rows(
    aggressive_rows: List[Dict[str, Any]],
    conservative_rows: List[Dict[str, Any]],
    spec: AlphaComboRegimeSwitchSpec,
) -> Dict[str, Any]:
    aggressive_best = sorted(
        aggressive_rows,
        key=lambda row: row["window_score"],
        reverse=True,
    )[0] if aggressive_rows else None
    conservative_best = sorted(
        conservative_rows,
        key=lambda row: row["window_score"],
        reverse=True,
    )[0] if conservative_rows else None
    selection = _select_variant(
        aggressive_best,
        conservative_best,
        spec.max_drawdown_gap,
        spec.target_cagr,
        spec.target_max_dd,
    )
    return {
        "aggressive": aggressive_best,
        "conservative": conservative_best,
        "selection": selection,
    }


def _summarize_oos_window_validation(rows: List[Dict[str, Any]], target_cagr: float, target_max_dd: float) -> Dict[str, Any]:
    if not rows:
        return {
            "window_count": 0,
            "cagr_hit_rate": 0.0,
            "target_pass_rate": 0.0,
            "avg_cagr": 0.0,
            "avg_cagr_gap": 0.0,
            "avg_cagr_target_met": False,
            "avg_max_dd": 0.0,
            "avg_sharpe": 0.0,
            "avg_mix_distance": 0.0,
        }

    cagr_values = [float(row["realized_metrics"].get("cagr", 0.0) or 0.0) for row in rows]
    max_dd_values = [abs(float(row["realized_metrics"].get("max_dd", 0.0) or 0.0)) for row in rows]
    sharpe_values = [float(row["realized_metrics"].get("sharpe", 0.0) or 0.0) for row in rows]
    mix_distances = [float(row["mix_distance"]) for row in rows]
    cagr_hits = [value >= float(target_cagr) for value in cagr_values]
    target_hits = [
        cagr >= float(target_cagr) and max_dd <= float(target_max_dd)
        for cagr, max_dd in zip(cagr_values, max_dd_values)
    ]
    return {
        "window_count": len(rows),
        "cagr_hit_rate": float(np.mean(cagr_hits)),
        "target_pass_rate": float(np.mean(target_hits)),
        "avg_cagr": float(np.mean(cagr_values)),
        "avg_cagr_gap": float(np.mean(cagr_values) - float(target_cagr)),
        "avg_cagr_target_met": bool(float(np.mean(cagr_values)) >= float(target_cagr)),
        "median_cagr": float(np.median(cagr_values)),
        "avg_max_dd": -float(np.mean(max_dd_values)),
        "median_max_dd": -float(np.median(max_dd_values)),
        "avg_sharpe": float(np.mean(sharpe_values)),
        "avg_mix_distance": float(np.mean(mix_distances)),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, np.floating):
        converted = float(value)
        return converted if np.isfinite(converted) else None
    return value


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
        f"- Target OOS CAGR floor: `{summary['spec']['target_cagr']:.2%}`",
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
                f"weighting={aggressive.get('weighting_method', 'heuristic')}, "
                f"top_n={int(aggressive.get('top_n', summary['spec']['top_n']))}, "
                f"OOS sharpe={aggressive['oos_metrics'].get('sharpe', float('nan')):.3f}, "
                f"cagr={aggressive['oos_metrics'].get('cagr', float('nan')):.3%}, "
                f"max_dd={aggressive['oos_metrics'].get('max_dd', float('nan')):.3%}"
            )
        if conservative:
            lines.append(
                f"- Conservative factors: `{', '.join(conservative.get('factors', []))}` | "
                f"weighting={conservative.get('weighting_method', 'heuristic')}, "
                f"top_n={int(conservative.get('top_n', summary['spec']['top_n']))}, "
                f"OOS sharpe={conservative['oos_metrics'].get('sharpe', float('nan')):.3f}, "
                f"cagr={conservative['oos_metrics'].get('cagr', float('nan')):.3%}, "
                f"max_dd={conservative['oos_metrics'].get('max_dd', float('nan')):.3%}"
            )
        if row.get("fallback_used"):
            lines.append("- Note: 该 regime 样本不足，沿用了当前冻结模型对比结果。")
        lines.append("")

    lines.extend(
        [
            "## Mixture-Aware Research",
            "",
            f"- OOS mixture selection: `top-{summary.get('mixture_research', {}).get('mixture_neighbor_count', 1)} inverse-distance ensemble`",
            f"- Train mixture windows: `{summary.get('mixture_research', {}).get('train_window_count', 0)}`",
            f"- OOS mixture windows: `{summary.get('mixture_research', {}).get('oos_window_count', 0)}`",
            f"- Mixture candidate combos: `{summary.get('mixture_research', {}).get('combo_candidate_count', 0)}`",
            f"- OOS window target pass rate: `{summary.get('mixture_research', {}).get('oos_validation_summary', {}).get('target_pass_rate', 0.0):.2%}`",
            f"- OOS window avg CAGR: `{summary.get('mixture_research', {}).get('oos_validation_summary', {}).get('avg_cagr', 0.0):.2%}`",
            f"- OOS avg CAGR target met: `{summary.get('mixture_research', {}).get('oos_validation_summary', {}).get('avg_cagr_target_met', False)}`",
            f"- OOS window avg MaxDD: `{summary.get('mixture_research', {}).get('oos_validation_summary', {}).get('avg_max_dd', 0.0):.2%}`",
            "",
            "## Notes",
            "",
            "- 这里同时保留了单一 regime 对比和新的 mixture-aware 研究；后者以滚动窗口内的 regime mix 作为研究单元。",
            "- 组合级风控只搜索总敞口和组合回撤闸门，不继续默认收紧单票止损，尽量避免把结果调成样本内好看。",
            "- mixture-aware 选择先只用 train 窗口生成原型，再拿 OOS 窗口做最近 mix 邻居加权验证，避免直接拿 OOS 反推组合。",
            "- 如果某个 regime 或 mix 窗口样本天数太少，报告会直接退回到当前冻结模型，不会强行编一个新组合。",
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

    full_engine = build_factor_research_panel(ohlcv, universe_cfg, standardize_cfg)
    engine = _subset_engine(full_engine, spec.candidate_factors)
    regime_frame = _build_regime_frame(regime_ohlcv, regime_cfg)
    backtest_cache: Dict[str, Dict[str, Any]] = {}
    score_frame_cache: Dict[str, Dict[str, Any]] = {}

    aggressive_payload = _extract_model_inputs(_load_model(spec.aggressive_model_path), backtest_cfg)
    conservative_payload = _extract_model_inputs(_load_model(spec.conservative_model_path), backtest_cfg)
    aggressive_engine = _select_engine_for_factors(engine, full_engine, aggressive_payload["factors"])
    conservative_engine = _select_engine_for_factors(engine, full_engine, conservative_payload["factors"])

    frozen_comparison: Dict[str, Any] = {}
    for regime_label in REGIME_ORDER:
        aggressive = {
            "factors": aggressive_payload["factors"],
            "factor_weights": aggressive_payload["factor_weights"],
            "top_n": aggressive_payload["top_n"],
            "trade_filters": spec.trade_filters or aggressive_payload["trade_filters"],
            "backtest_overrides": aggressive_payload["backtest_overrides"],
            "train_metrics": _run_combo_backtest_cached(
                backtest_cache,
                score_frame_cache,
                ohlcv,
                aggressive_engine["standardized_panel"],
                aggressive_engine["raw_panel"],
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
            "oos_metrics": _run_combo_backtest_cached(
                backtest_cache,
                score_frame_cache,
                ohlcv,
                aggressive_engine["standardized_panel"],
                aggressive_engine["raw_panel"],
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
            "top_n": conservative_payload["top_n"],
            "trade_filters": spec.trade_filters or conservative_payload["trade_filters"],
            "backtest_overrides": conservative_payload["backtest_overrides"],
            "risk_overrides": conservative_payload["backtest_overrides"],
            "train_metrics": _run_combo_backtest_cached(
                backtest_cache,
                score_frame_cache,
                ohlcv,
                conservative_engine["standardized_panel"],
                conservative_engine["raw_panel"],
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
            "oos_metrics": _run_combo_backtest_cached(
                backtest_cache,
                score_frame_cache,
                ohlcv,
                conservative_engine["standardized_panel"],
                conservative_engine["raw_panel"],
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
            "selection": _select_variant(aggressive, conservative, spec.max_drawdown_gap, spec.target_cagr, spec.target_max_dd),
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
            for weight_variant in _build_combo_weight_variants(
                combo,
                ohlcv,
                engine["standardized_panel"],
                spec,
                combo_cfg,
                regime_frame=regime_frame,
                regime_label=regime_label,
            ):
                aggressive_row = _search_execution_variant(
                    backtest_cache,
                    score_frame_cache,
                    ohlcv,
                    engine["standardized_panel"],
                    engine["raw_panel"],
                    regime_frame,
                    regime_label,
                    combo["factors"],
                    weight_variant["factor_weights"],
                    combo["max_abs_corr"],
                    combo["avg_abs_corr"],
                    spec,
                    backtest_cfg,
                )
                if aggressive_row is not None:
                    aggressive_rows.append(
                        {
                            **aggressive_row,
                            "weighting_method": weight_variant["weighting_method"],
                            "ml_weight_metadata": weight_variant["ml_weight_metadata"],
                        }
                    )

        aggressive_ranked = sorted(aggressive_rows, key=lambda row: row["stability_score"], reverse=True)
        aggressive_best = aggressive_ranked[0] if aggressive_ranked else None
        conservative_best = None
        fallback_used = False

        if aggressive_best is not None:
            conservative_best = _search_overlay_variant(
                backtest_cache,
                score_frame_cache,
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
                "trade_filters": spec.trade_filters or conservative_payload["trade_filters"],
                "backtest_overrides": conservative_payload["backtest_overrides"],
                "risk_overrides": conservative_payload["backtest_overrides"],
            }

        selection = _select_variant(
            aggressive_best,
            conservative_best,
            spec.max_drawdown_gap,
            spec.target_cagr,
            spec.target_max_dd,
        )
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

    overall_train_validation = _run_regime_factor_validation(
        ohlcv,
        engine["standardized_panel"],
        None,
        None,
        spec.train_start,
        spec.train_end,
        test_cfg,
    )
    overall_oos_validation = _run_regime_factor_validation(
        ohlcv,
        engine["standardized_panel"],
        None,
        None,
        spec.oos_start,
        spec.oos_end,
        test_cfg,
    )
    overall_pool = select_oriented_factor_pool(
        overall_train_validation,
        overall_oos_validation,
        engine["factor_definitions"],
        combo_cfg,
    )
    overall_candidate_names = [item["factor"] for item in overall_pool["candidate_factors"]]
    overall_corr = compute_train_factor_correlation(
        engine["standardized_panel"],
        overall_candidate_names,
        spec.train_start,
        spec.train_end,
    )
    overall_combo_candidates = generate_low_correlation_combinations(
        overall_pool["candidate_factors"],
        engine["factor_definitions"],
        overall_corr,
        combo_cfg,
    )

    combo_catalog: List[Dict[str, Any]] = []
    for combo in overall_combo_candidates["shortlisted_combinations"]:
        for weight_variant in _build_combo_weight_variants(
            combo,
            ohlcv,
            engine["standardized_panel"],
            spec,
            combo_cfg,
        ):
            aggressive_row = _search_execution_variant(
                backtest_cache,
                score_frame_cache,
                ohlcv,
                engine["standardized_panel"],
                engine["raw_panel"],
                None,
                None,
                combo["factors"],
                weight_variant["factor_weights"],
                combo["max_abs_corr"],
                combo["avg_abs_corr"],
                spec,
                backtest_cfg,
            )
            conservative_row = _search_overlay_variant(
                backtest_cache,
                score_frame_cache,
                ohlcv,
                engine["standardized_panel"],
                engine["raw_panel"],
                None,
                None,
                combo["factors"],
                weight_variant["factor_weights"],
                spec,
                backtest_cfg,
            )
            if aggressive_row is not None:
                combo_catalog.append(
                    {
                        "aggressive": {
                            **aggressive_row,
                            "weighting_method": weight_variant["weighting_method"],
                            "ml_weight_metadata": weight_variant["ml_weight_metadata"],
                        },
                        "conservative": (
                            {
                                **conservative_row,
                                "weighting_method": weight_variant["weighting_method"],
                                "ml_weight_metadata": weight_variant["ml_weight_metadata"],
                            }
                            if conservative_row is not None
                            else None
                        ),
                    }
                )

    train_mix_windows = _build_mix_windows(
        regime_frame,
        spec.train_start,
        spec.train_end,
        spec.mix_window_days,
        spec.mix_step_days,
        spec.min_mix_sample_days,
    )
    oos_mix_windows = _build_mix_windows(
        regime_frame,
        spec.oos_start,
        spec.oos_end,
        spec.mix_window_days,
        spec.mix_step_days,
        spec.min_mix_sample_days,
    )

    mixture_library: List[Dict[str, Any]] = []
    for window in train_mix_windows:
        aggressive_rows: List[Dict[str, Any]] = []
        conservative_rows: List[Dict[str, Any]] = []
        for catalog in combo_catalog:
            aggressive_source = catalog["aggressive"]
            aggressive_result = _run_combo_backtest_cached(
                backtest_cache,
                score_frame_cache,
                ohlcv,
                engine["standardized_panel"],
                engine["raw_panel"],
                aggressive_source["factors"],
                aggressive_source["factor_weights"],
                window["start"],
                window["end"],
                int(aggressive_source.get("top_n", spec.top_n)),
                spec.rebalance_every_n_days,
                aggressive_source.get("trade_filters", spec.trade_filters),
                backtest_cfg,
                backtest_overrides=aggressive_source.get("backtest_overrides"),
            )
            aggressive_rows.append(
                {
                    **aggressive_source,
                    "oos_metrics": aggressive_result["metrics"],
                    "window_metrics": aggressive_result["metrics"],
                    "window_score": _window_candidate_score(
                        aggressive_result["metrics"],
                        spec.target_cagr,
                        spec.target_max_dd,
                        aggressive_source["max_abs_corr"],
                    ),
                }
            )
            conservative_source = catalog["conservative"]
            if conservative_source is None:
                continue
            conservative_result = _run_combo_backtest_cached(
                backtest_cache,
                score_frame_cache,
                ohlcv,
                engine["standardized_panel"],
                engine["raw_panel"],
                conservative_source["factors"],
                conservative_source["factor_weights"],
                window["start"],
                window["end"],
                int(conservative_source.get("top_n", spec.top_n)),
                spec.rebalance_every_n_days,
                conservative_source.get("trade_filters", spec.trade_filters),
                backtest_cfg,
                backtest_overrides=conservative_source.get("backtest_overrides") or conservative_source.get("risk_overrides"),
            )
            conservative_rows.append(
                {
                    **conservative_source,
                    "oos_metrics": conservative_result["metrics"],
                    "window_metrics": conservative_result["metrics"],
                    "window_score": _window_candidate_score(
                        conservative_result["metrics"],
                        spec.target_cagr,
                        spec.target_max_dd,
                    ),
                }
            )
        selected = _select_from_window_rows(aggressive_rows, conservative_rows, spec)
        mixture_library.append(
            {
                "window_label": window["window_label"],
                "start": window["start"],
                "end": window["end"],
                "sample_days": window["sample_days"],
                "mix": window["mix"],
                "aggressive": selected["aggressive"],
                "conservative": selected["conservative"],
                "selection": selected["selection"],
            }
        )

    oos_window_validation: List[Dict[str, Any]] = []
    for window in oos_mix_windows:
        if not mixture_library:
            break
        neighbors = _select_mix_neighbors(
            mixture_library,
            window["mix"],
            spec.mixture_neighbor_count,
            spec.mixture_distance_power,
        )
        if not neighbors:
            continue

        lead_neighbor = neighbors[0]
        lead_model = lead_neighbor["selected_model"]
        ensemble_weights = [float(item["weight"]) for item in neighbors]
        component_top_n = [int(item["selected_model"].get("top_n", spec.top_n)) for item in neighbors]
        blended_top_n = _weighted_int(component_top_n, ensemble_weights)
        filter_diagnostics_list: List[Dict[str, Any]] = []
        strategy_weight_frames: Dict[str, pd.DataFrame] = {}
        window_ohlcv = _slice_frame(ohlcv, window["start"], window["end"])
        rebalance_dates = pd.Index(window_ohlcv["timestamp"].drop_duplicates().sort_values())

        for idx, neighbor in enumerate(neighbors):
            model = neighbor["selected_model"]
            score_payload = _build_combo_score_frame_cached(
                score_frame_cache,
                engine["standardized_panel"],
                engine["raw_panel"],
                model["factors"],
                model["factor_weights"],
                int(model.get("top_n", spec.top_n)),
                spec.rebalance_every_n_days,
                model.get("trade_filters", spec.trade_filters),
            )
            window_score_frame = _slice_frame(score_payload["score_frame"], window["start"], window["end"])
            filter_diagnostics_list.append(score_payload["filter_diagnostics"])
            model_top_n = int(model.get("top_n", spec.top_n))
            model_cfg = _clean_backtest_cfg(
                backtest_cfg,
                model_top_n,
                spec.rebalance_every_n_days,
                model.get("backtest_overrides") or model.get("risk_overrides"),
            )
            model_signal = build_top_n_signal(window_score_frame, model_top_n)
            strategy_weight_frames[f"neighbor_{idx}"] = build_daily_target_weights(
                model_signal,
                window_score_frame.set_index(["timestamp", "symbol"])["score"] if not window_score_frame.empty else None,
                rebalance_dates,
                model_cfg,
            )

        blended_filter_diagnostics = _weighted_numeric_dict(filter_diagnostics_list, ensemble_weights)
        blended_cfg = _clean_backtest_cfg(
            backtest_cfg,
            blended_top_n,
            spec.rebalance_every_n_days,
            lead_model.get("backtest_overrides") or lead_model.get("risk_overrides"),
        )
        allocation_frame = pd.DataFrame(
            {
                f"neighbor_{idx}": float(weight)
                for idx, weight in enumerate(ensemble_weights)
            },
            index=rebalance_dates,
        ).reindex(columns=sorted(strategy_weight_frames)).fillna(0.0)
        combined_weights = combine_strategy_weight_frames(
            strategy_weight_frames,
            allocation_frame,
            gross_exposure=float(blended_cfg.gross_exposure),
        )
        realized = run_weight_backtest(
            window_ohlcv,
            combined_weights,
            blended_cfg,
        )
        oos_window_validation.append(
            {
                "window_label": window["window_label"],
                "start": window["start"],
                "end": window["end"],
                "mix": window["mix"],
                "sample_days": window["sample_days"],
                "matched_train_window": lead_neighbor["window_label"],
                "matched_train_windows": [item["window_label"] for item in neighbors],
                "mix_distance": float(sum(item["distance"] * item["weight"] for item in neighbors)),
                "ensemble_member_count": len(neighbors),
                "mixture_neighbor_weights": [
                    {
                        "window_label": item["window_label"],
                        "distance": float(item["distance"]),
                        "weight": float(item["weight"]),
                        "selected_variant": item["selected_variant"],
                    }
                    for item in neighbors
                ],
                "selected_variant": "mixture_ensemble" if len(neighbors) > 1 else lead_neighbor["selected_variant"],
                "selected_factors": [item["selected_model"]["factors"] for item in neighbors],
                "selected_factor_weights": [item["selected_model"]["factor_weights"] for item in neighbors],
                "weighting_method": (
                    "mixture_ensemble"
                    if len({item["selected_model"].get("weighting_method", "heuristic") for item in neighbors}) > 1
                    else lead_model.get("weighting_method", "heuristic")
                ),
                "ml_weight_metadata": {
                    "neighbor_weighting": "inverse_mix_distance",
                    "lead_model": lead_model.get("ml_weight_metadata", {}),
                    "neighbors": [item["selected_model"].get("ml_weight_metadata", {}) for item in neighbors],
                },
                "top_n": blended_top_n,
                "trade_filters": lead_model.get("trade_filters", spec.trade_filters),
                "backtest_overrides": lead_model.get("backtest_overrides") or lead_model.get("risk_overrides", {}),
                "risk_overrides": lead_model.get("risk_overrides", {}),
                "execution_overrides": lead_model.get("execution_overrides", {}),
                "filter_diagnostics": blended_filter_diagnostics,
                "realized_metrics": realized["metrics"],
            }
        )

    mixture_research = {
        "mix_window_days": int(spec.mix_window_days),
        "mix_step_days": int(spec.mix_step_days),
        "min_mix_sample_days": int(spec.min_mix_sample_days),
        "mixture_neighbor_count": int(spec.mixture_neighbor_count),
        "mixture_distance_power": float(spec.mixture_distance_power),
        "train_window_count": len(train_mix_windows),
        "oos_window_count": len(oos_mix_windows),
        "candidate_pool": overall_pool["candidate_factors"],
        "dropped_factors": overall_pool["dropped_factors"],
        "combo_candidate_count": len(combo_catalog),
        "mixture_library": mixture_library,
        "oos_window_validation": oos_window_validation,
        "oos_validation_summary": _summarize_oos_window_validation(
            oos_window_validation,
            spec.target_cagr,
            spec.target_max_dd,
        ),
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
        "mixture_research": mixture_research,
        "report_files": {
            "json": json_path,
            "markdown": md_path,
        },
        "frozen_model_path": frozen_path,
    }

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(_json_safe(summary), handle, ensure_ascii=False, indent=2)
    _write_markdown_report(summary, md_path)

    with open(frozen_path, "w", encoding="utf-8") as handle:
        json.dump(
            _json_safe({
                "generated_at_utc": summary["generated_at_utc"],
                "spec": summary["spec"],
                "train_regime_mix": summary["train_regime_mix"],
                "oos_regime_mix": summary["oos_regime_mix"],
                "regime_models": summary["regime_models"],
                "mixture_research": summary["mixture_research"],
                "report_files": summary["report_files"],
            }),
            handle,
            ensure_ascii=False,
            indent=2,
        )

    return summary
