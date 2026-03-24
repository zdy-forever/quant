"""
高分红 ETF 小池子轮动研究。

这条线专门给少量 ETF 做研究，不复用大横截面 alpha 因子筛选逻辑，
避免因为样本只有 4 只资产就把原来的低相关因子框架硬套上去。

核心思路：
- 用 `adjustment="all"` 的收盘价代表含分红总回报
- 用 `adjustment="raw"` 的收盘价代表裸价格走势
- 两者的回报差近似成“分红 carry”
- 再把 total return 动量、price 动量、dividend carry 和风险惩罚做成少量可解释 profile
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from backtest.engine import BacktestConfig, run_signal_backtest, run_weight_backtest
from factors.composite import build_top_n_signal, latest_top_picks

REPORT_DIR = os.path.join("artifacts", "reports")


@dataclass(frozen=True)
class IncomeEtfRotationSpec:
    symbols: List[str]
    start: str
    end: str
    train_end: str
    top_n_grid: List[int] | None = None
    rebalance_every_n_days_grid: List[int] | None = None
    stop_loss_pct_grid: List[float] | None = None
    min_score_threshold_grid: List[float] | None = None
    rank_weight_power_grid: List[float] | None = None
    validation_window_days: int = 21
    target_excess_cagr_vs_best_hold: float = 0.02


def _slice_frame(frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    return out[(out["timestamp"] >= start_ts) & (out["timestamp"] <= end_ts)].copy()


def _aligned_close_panels(adjusted_ohlcv: pd.DataFrame, raw_ohlcv: pd.DataFrame, symbols: List[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    adjusted_close = (
        adjusted_ohlcv[adjusted_ohlcv["symbol"].isin(symbols)]
        .pivot(index="timestamp", columns="symbol", values="close")
        .sort_index()
    )
    raw_close = (
        raw_ohlcv[raw_ohlcv["symbol"].isin(symbols)]
        .pivot(index="timestamp", columns="symbol", values="close")
        .sort_index()
    )
    all_index = adjusted_close.index.union(raw_close.index).sort_values()
    all_columns = sorted(set(adjusted_close.columns).union(set(raw_close.columns)))
    return (
        adjusted_close.reindex(index=all_index, columns=all_columns),
        raw_close.reindex(index=all_index, columns=all_columns),
    )


def _cross_sectional_rank(panel: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    out = panel.copy()
    for column in columns:
        ranked = out.groupby("timestamp")[column].rank(method="average", pct=True)
        out[column] = ranked.sub(0.5).mul(2.0)
    return out


def _build_income_rotation_panel(
    adjusted_ohlcv: pd.DataFrame,
    raw_ohlcv: pd.DataFrame,
    symbols: List[str],
) -> tuple[pd.DataFrame, Dict[str, Dict[str, float]]]:
    adjusted_close, raw_close = _aligned_close_panels(adjusted_ohlcv, raw_ohlcv, symbols)
    adjusted_ret_1 = adjusted_close.pct_change()
    total_ret_10 = adjusted_close.pct_change(10)
    total_ret_21 = adjusted_close.pct_change(21)
    total_ret_42 = adjusted_close.pct_change(42)
    price_ret_10 = raw_close.pct_change(10)
    price_ret_21 = raw_close.pct_change(21)
    price_ret_42 = raw_close.pct_change(42)
    dividend_carry_10 = total_ret_10 - price_ret_10
    dividend_carry_21 = total_ret_21 - price_ret_21
    dividend_carry_42 = total_ret_42 - price_ret_42
    carry_acceleration = dividend_carry_21 - dividend_carry_10
    relative_strength_21 = total_ret_21.sub(total_ret_21.mean(axis=1), axis=0)
    relative_strength_42 = total_ret_42.sub(total_ret_42.mean(axis=1), axis=0)
    vol_10 = adjusted_ret_1.rolling(10).std(ddof=0)
    vol_20 = adjusted_ret_1.rolling(20).std(ddof=0)
    downside_ret = adjusted_ret_1.where(adjusted_ret_1 < 0.0, 0.0)
    downside_10 = downside_ret.rolling(10).std(ddof=0).abs()
    downside_20 = downside_ret.rolling(20).std(ddof=0).abs()

    feature_frames = {
        "tr_momentum_10": total_ret_10.stack().rename("tr_momentum_10"),
        "tr_momentum_21": total_ret_21.stack().rename("tr_momentum_21"),
        "tr_momentum_42": total_ret_42.stack().rename("tr_momentum_42"),
        "price_momentum_10": price_ret_10.stack().rename("price_momentum_10"),
        "price_momentum_21": price_ret_21.stack().rename("price_momentum_21"),
        "price_momentum_42": price_ret_42.stack().rename("price_momentum_42"),
        "dividend_carry_10": dividend_carry_10.stack().rename("dividend_carry_10"),
        "dividend_carry_21": dividend_carry_21.stack().rename("dividend_carry_21"),
        "dividend_carry_42": dividend_carry_42.stack().rename("dividend_carry_42"),
        "carry_acceleration": carry_acceleration.stack().rename("carry_acceleration"),
        "relative_strength_21": relative_strength_21.stack().rename("relative_strength_21"),
        "relative_strength_42": relative_strength_42.stack().rename("relative_strength_42"),
        "volatility_10": vol_10.stack().rename("volatility_10"),
        "volatility_20": vol_20.stack().rename("volatility_20"),
        "downside_10": downside_10.stack().rename("downside_10"),
        "downside_20": downside_20.stack().rename("downside_20"),
    }

    panel = pd.concat(feature_frames.values(), axis=1).reset_index()
    panel.columns = ["timestamp", "symbol"] + list(feature_frames)
    panel = panel.dropna().copy()
    available_count = panel.groupby("timestamp")["symbol"].transform("nunique")
    panel = panel[available_count >= 2].copy()
    factor_columns = list(feature_frames)
    panel = _cross_sectional_rank(panel, factor_columns)

    dividend_rows: Dict[str, Dict[str, float]] = {}
    for symbol in symbols:
        adj_series = adjusted_close[symbol].dropna()
        raw_series = raw_close[symbol].dropna()
        if adj_series.empty or raw_series.empty:
            continue
        total_return = float(adj_series.iloc[-1] / adj_series.iloc[0] - 1.0)
        price_return = float(raw_series.iloc[-1] / raw_series.iloc[0] - 1.0)
        dividend_rows[str(symbol)] = {
            "total_return": total_return,
            "price_return": price_return,
            "dividend_carry": total_return - price_return,
        }
    dividend_summary = pd.DataFrame.from_dict(dividend_rows, orient="index")
    return panel, {
        str(symbol): {key: float(value) for key, value in row.items()}
        for symbol, row in dividend_summary.to_dict(orient="index").items()
    }


def _profile_library() -> List[Dict[str, Any]]:
    return [
        {
            "name": "price_trend",
            "uses_dividends": False,
            "factor_weights": {
                "price_momentum_21": 0.35,
                "price_momentum_42": 0.45,
                "volatility_20": -0.20,
            },
        },
        {
            "name": "total_return_trend",
            "uses_dividends": False,
            "factor_weights": {
                "tr_momentum_21": 0.35,
                "tr_momentum_42": 0.45,
                "volatility_20": -0.20,
            },
        },
        {
            "name": "income_tilted_trend",
            "uses_dividends": True,
            "factor_weights": {
                "tr_momentum_10": 0.15,
                "tr_momentum_21": 0.25,
                "tr_momentum_42": 0.20,
                "dividend_carry_21": 0.15,
                "dividend_carry_42": 0.15,
                "volatility_20": -0.10,
            },
        },
        {
            "name": "income_defensive",
            "uses_dividends": True,
            "factor_weights": {
                "tr_momentum_21": 0.15,
                "dividend_carry_21": 0.20,
                "dividend_carry_42": 0.25,
                "downside_20": -0.20,
                "volatility_20": -0.10,
            },
        },
        {
            "name": "yield_trend_balance",
            "uses_dividends": True,
            "factor_weights": {
                "relative_strength_21": 0.10,
                "price_momentum_21": 0.15,
                "tr_momentum_42": 0.25,
                "dividend_carry_42": 0.25,
                "downside_20": -0.15,
                "volatility_20": -0.10,
            },
        },
        {
            "name": "carry_acceleration",
            "uses_dividends": True,
            "factor_weights": {
                "tr_momentum_10": 0.15,
                "price_momentum_10": 0.10,
                "dividend_carry_10": 0.20,
                "dividend_carry_21": 0.20,
                "carry_acceleration": 0.15,
                "downside_10": -0.10,
                "volatility_10": -0.10,
            },
        },
        {
            "name": "short_term_leader",
            "uses_dividends": False,
            "factor_weights": {
                "tr_momentum_10": 0.30,
                "tr_momentum_21": 0.30,
                "relative_strength_21": 0.25,
                "volatility_10": -0.15,
            },
        },
        {
            "name": "income_breakout",
            "uses_dividends": True,
            "factor_weights": {
                "tr_momentum_10": 0.15,
                "tr_momentum_21": 0.20,
                "dividend_carry_10": 0.15,
                "dividend_carry_42": 0.20,
                "carry_acceleration": 0.15,
                "downside_20": -0.20,
            },
        },
    ]


def _score_frame(panel: pd.DataFrame, factor_weights: Dict[str, float]) -> pd.DataFrame:
    score = pd.Series(0.0, index=panel.index, dtype=float)
    weight_sum = 0.0
    for factor_name, weight in factor_weights.items():
        score = score.add(panel[factor_name].fillna(0.0) * float(weight), fill_value=0.0)
        weight_sum += abs(float(weight))
    out = panel[["timestamp", "symbol"]].copy()
    out["eligible"] = True
    out["score"] = score / max(weight_sum, 1e-12)
    return out


def _clean_cfg(
    base_cfg: BacktestConfig,
    top_n: int,
    rebalance_every_n_days: int,
    stop_loss_pct: float,
    min_score_threshold: float,
    rank_weight_power: float,
) -> BacktestConfig:
    cfg_dict = asdict(base_cfg)
    cfg_dict.update(
        {
            "max_positions": int(top_n),
            "rebalance_every_n_days": int(rebalance_every_n_days),
            "max_holding_days": 252,
            "stop_loss_pct": float(stop_loss_pct),
            "take_profit_pct": 0.0,
            "trailing_stop_atr_multiple": 0.0,
            "min_score_threshold": float(min_score_threshold),
            "rank_weight_power": float(rank_weight_power),
        }
    )
    return BacktestConfig(**cfg_dict)


def _metric_score(metrics: Dict[str, Any]) -> tuple:
    return (
        float(metrics.get("cagr", -1.0) or -1.0),
        float(metrics.get("sharpe", -99.0) or -99.0),
        float(metrics.get("calmar", -99.0) or -99.0),
        float(metrics.get("max_dd", -1.0) or -1.0),
    )


def _selection_frequency(score_frame: pd.DataFrame, start: str, end: str, top_n: int) -> Dict[str, float]:
    window_score = _slice_frame(score_frame, start, end)
    if window_score.empty:
        return {}
    signal = build_top_n_signal(window_score, top_n)
    signal_frame = signal.rename("signal").reset_index()
    total_days = max(window_score["timestamp"].nunique(), 1)
    counts = signal_frame.groupby("symbol")["signal"].sum().sort_values(ascending=False)
    return {str(symbol): float(value) / float(total_days) for symbol, value in counts.items()}


def _build_validation_windows(panel: pd.DataFrame, start: str, end: str, window_days: int) -> List[Dict[str, str]]:
    window_panel = _slice_frame(panel[["timestamp", "symbol"]], start, end)
    unique_days = sorted(pd.to_datetime(window_panel["timestamp"], utc=True).drop_duplicates().tolist())
    if not unique_days:
        return []
    step = max(int(window_days), 1)
    windows: List[Dict[str, str]] = []
    for idx in range(0, len(unique_days), step):
        days = unique_days[idx : idx + step]
        if len(days) < max(5, step // 2):
            continue
        windows.append(
            {
                "start": pd.Timestamp(days[0]).tz_convert("UTC").strftime("%Y-%m-%d"),
                "end": pd.Timestamp(days[-1]).tz_convert("UTC").strftime("%Y-%m-%d"),
            }
        )
    return windows


def _summarize_validation(metrics_rows: List[Dict[str, Any]]) -> Dict[str, float]:
    if not metrics_rows:
        return {"window_count": 0, "avg_cagr": 0.0, "avg_sharpe": 0.0, "avg_max_dd": 0.0, "cagr_hit_rate": 0.0}
    cagrs = [float(row.get("cagr", 0.0) or 0.0) for row in metrics_rows]
    sharpes = [float(row.get("sharpe", 0.0) or 0.0) for row in metrics_rows]
    max_dds = [float(row.get("max_dd", 0.0) or 0.0) for row in metrics_rows]
    return {
        "window_count": len(metrics_rows),
        "avg_cagr": float(np.mean(cagrs)),
        "avg_sharpe": float(np.mean(sharpes)),
        "avg_max_dd": float(np.mean(max_dds)),
        "cagr_hit_rate": float(np.mean([value > 0.0 for value in cagrs])),
    }


def _candidate_score(row: Dict[str, Any], benchmark_cagr: float, target_excess: float) -> tuple:
    validation = row.get("train_validation_summary", {}) or {}
    validation_excess = float(validation.get("avg_cagr", -1.0) or -1.0) - float(benchmark_cagr)
    train_excess = float(row["train_metrics"].get("cagr", -1.0) or -1.0) - float(benchmark_cagr)
    return (
        float(validation_excess >= float(target_excess)),
        validation_excess,
        float(validation.get("avg_sharpe", -99.0) or -99.0),
        float(validation.get("cagr_hit_rate", -1.0) or -1.0),
        train_excess,
        float(row["train_metrics"].get("max_dd", -1.0) or -1.0),
    )


def _run_candidate(
    adjusted_ohlcv: pd.DataFrame,
    score_frame: pd.DataFrame,
    profile: Dict[str, Any],
    start: str,
    end: str,
    top_n: int,
    rebalance_every_n_days: int,
    stop_loss_pct: float,
    min_score_threshold: float,
    rank_weight_power: float,
    backtest_cfg: BacktestConfig,
) -> Dict[str, Any]:
    window_score = _slice_frame(score_frame, start, end)
    signal = build_top_n_signal(window_score, top_n)
    result = run_signal_backtest(
        _slice_frame(adjusted_ohlcv, start, end),
        signal,
        window_score.set_index(["timestamp", "symbol"])["score"] if not window_score.empty else None,
        _clean_cfg(backtest_cfg, top_n, rebalance_every_n_days, stop_loss_pct, min_score_threshold, rank_weight_power),
    )
    return {
        "profile_name": profile["name"],
        "uses_dividends": bool(profile["uses_dividends"]),
        "factor_weights": dict(profile["factor_weights"]),
        "top_n": int(top_n),
        "rebalance_every_n_days": int(rebalance_every_n_days),
        "stop_loss_pct": float(stop_loss_pct),
        "min_score_threshold": float(min_score_threshold),
        "rank_weight_power": float(rank_weight_power),
        "metrics": result["metrics"],
        "latest_picks": latest_top_picks(window_score, top_n),
    }


def _buy_and_hold_benchmarks(
    adjusted_ohlcv: pd.DataFrame,
    symbols: List[str],
    start: str,
    end: str,
    backtest_cfg: BacktestConfig,
) -> Dict[str, Dict[str, float]]:
    window = _slice_frame(adjusted_ohlcv, start, end)
    close_panel = window.pivot(index="timestamp", columns="symbol", values="close").sort_index()
    metrics: Dict[str, Dict[str, float]] = {}
    for symbol in symbols:
        weights = pd.DataFrame(0.0, index=close_panel.index, columns=close_panel.columns)
        if symbol in weights.columns:
            weights[symbol] = float(backtest_cfg.gross_exposure)
        result = run_weight_backtest(
            window,
            weights,
            BacktestConfig(
                **{
                    **asdict(backtest_cfg),
                    "max_positions": 1,
                    "max_holding_days": 252,
                    "stop_loss_pct": 0.0,
                    "take_profit_pct": 0.0,
                    "trailing_stop_atr_multiple": 0.0,
                }
            ),
        )
        metrics[str(symbol)] = {key: float(value) for key, value in result["metrics"].items()}
    return metrics


def _write_markdown_report(summary: Dict[str, Any], path: str) -> None:
    lines = [
        "# Income ETF Rotation Report",
        "",
        "## Summary",
        "",
        f"- Generated at UTC: `{summary['generated_at_utc']}`",
        f"- Symbols: `{', '.join(summary['spec']['symbols'])}`",
        f"- Common window: `{summary['common_window']['start']}` -> `{summary['common_window']['end']}`",
        f"- Train window: `{summary['spec']['start']}` -> `{summary['spec']['train_end']}`",
        f"- OOS window: `{summary['oos_window']['start']}` -> `{summary['oos_window']['end']}`",
        f"- Target excess CAGR vs best hold: `{summary['spec']['target_excess_cagr_vs_best_hold']:.2%}`",
        f"- Selected profile: `{summary['selected_strategy']['profile_name']}`",
        f"- Selected profile uses dividends: `{summary['selected_strategy']['uses_dividends']}`",
        f"- Selected top_n: `{summary['selected_strategy']['top_n']}`",
        f"- Selected rebalance_every_n_days: `{summary['selected_strategy']['rebalance_every_n_days']}`",
        f"- Selected min_score_threshold: `{summary['selected_strategy']['min_score_threshold']}`",
        f"- Selected rank_weight_power: `{summary['selected_strategy']['rank_weight_power']}`",
        f"- OOS excess CAGR vs best hold: `{summary['selected_strategy'].get('oos_excess_cagr_vs_best_hold', 0.0):.2%}`",
        f"- OOS beats best hold by target: `{summary['selected_strategy'].get('oos_excess_target_met', False)}`",
        "",
        "## Dividend Carry Snapshot",
        "",
    ]
    for symbol, row in summary["dividend_summary"].items():
        lines.append(
            f"- {symbol}: total_return={row['total_return']:.2%}, price_return={row['price_return']:.2%}, dividend_carry={row['dividend_carry']:.2%}"
        )
    lines.extend(
        [
            "",
            "## Best Price-Only Baseline",
            "",
            f"- Profile: `{summary['price_only_best']['profile_name']}`",
            f"- Train validation summary: `{json.dumps(summary['price_only_best'].get('train_validation_summary', {}))}`",
            f"- Train metrics: `{json.dumps(summary['price_only_best']['train_metrics'])}`",
            f"- OOS metrics: `{json.dumps(summary['price_only_best']['oos_metrics'])}`",
            f"- OOS selection frequency: `{json.dumps(summary['price_only_best']['oos_selection_frequency'])}`",
            "",
            "## Best Dividend-Aware Strategy",
            "",
            f"- Profile: `{summary['dividend_aware_best']['profile_name']}`",
            f"- Train validation summary: `{json.dumps(summary['dividend_aware_best'].get('train_validation_summary', {}))}`",
            f"- Train metrics: `{json.dumps(summary['dividend_aware_best']['train_metrics'])}`",
            f"- OOS metrics: `{json.dumps(summary['dividend_aware_best']['oos_metrics'])}`",
            f"- OOS selection frequency: `{json.dumps(summary['dividend_aware_best']['oos_selection_frequency'])}`",
            "",
            "## Buy And Hold Benchmarks",
            "",
        ]
    )
    for symbol, metrics in summary["oos_buy_and_hold"].items():
        lines.append(f"- {symbol}: `{json.dumps(metrics)}`")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


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


def run_income_etf_rotation(
    adjusted_ohlcv: pd.DataFrame,
    raw_ohlcv: pd.DataFrame,
    spec: IncomeEtfRotationSpec,
    backtest_cfg: BacktestConfig,
) -> Dict[str, Any]:
    os.makedirs(REPORT_DIR, exist_ok=True)

    panel, dividend_summary = _build_income_rotation_panel(adjusted_ohlcv, raw_ohlcv, spec.symbols)
    common_start = panel["timestamp"].min().strftime("%Y-%m-%d")
    common_end = panel["timestamp"].max().strftime("%Y-%m-%d")
    oos_start = (pd.Timestamp(spec.train_end, tz="UTC") + timedelta(days=1)).strftime("%Y-%m-%d")
    profile_library = _profile_library()

    top_n_grid = spec.top_n_grid or [1, 2]
    rebalance_grid = spec.rebalance_every_n_days_grid or [5, 10, 21]
    stop_loss_grid = spec.stop_loss_pct_grid or [0.0, 0.08]
    min_score_threshold_grid = spec.min_score_threshold_grid or [-999.0, 0.0, 0.15]
    rank_weight_power_grid = spec.rank_weight_power_grid or [0.0, 1.5]
    validation_windows = _build_validation_windows(panel, spec.start, spec.train_end, spec.validation_window_days)

    candidates: List[Dict[str, Any]] = []
    for profile in profile_library:
        score_frame = _score_frame(panel, profile["factor_weights"])
        for top_n in top_n_grid:
            for rebalance_every_n_days in rebalance_grid:
                for stop_loss_pct in stop_loss_grid:
                    for min_score_threshold in min_score_threshold_grid:
                        for rank_weight_power in rank_weight_power_grid:
                            train_result = _run_candidate(
                                adjusted_ohlcv,
                                score_frame,
                                profile,
                                spec.start,
                                spec.train_end,
                                top_n,
                                rebalance_every_n_days,
                                stop_loss_pct,
                                min_score_threshold,
                                rank_weight_power,
                                backtest_cfg,
                            )
                            validation_rows = []
                            for window in validation_windows:
                                validation_rows.append(
                                    _run_candidate(
                                        adjusted_ohlcv,
                                        score_frame,
                                        profile,
                                        window["start"],
                                        window["end"],
                                        top_n,
                                        rebalance_every_n_days,
                                        stop_loss_pct,
                                        min_score_threshold,
                                        rank_weight_power,
                                        backtest_cfg,
                                    )["metrics"]
                                )
                            oos_result = _run_candidate(
                                adjusted_ohlcv,
                                score_frame,
                                profile,
                                oos_start,
                                spec.end,
                                top_n,
                                rebalance_every_n_days,
                                stop_loss_pct,
                                min_score_threshold,
                                rank_weight_power,
                                backtest_cfg,
                            )
                            candidates.append(
                                {
                                    "profile_name": profile["name"],
                                    "uses_dividends": bool(profile["uses_dividends"]),
                                    "factor_weights": dict(profile["factor_weights"]),
                                    "top_n": int(top_n),
                                    "rebalance_every_n_days": int(rebalance_every_n_days),
                                    "stop_loss_pct": float(stop_loss_pct),
                                    "min_score_threshold": float(min_score_threshold),
                                    "rank_weight_power": float(rank_weight_power),
                                    "train_metrics": train_result["metrics"],
                                    "train_validation_summary": _summarize_validation(validation_rows),
                                    "oos_metrics": oos_result["metrics"],
                                    "train_latest_picks": train_result["latest_picks"],
                                    "oos_latest_picks": oos_result["latest_picks"],
                                    "train_selection_frequency": _selection_frequency(score_frame, spec.start, spec.train_end, top_n),
                                    "oos_selection_frequency": _selection_frequency(score_frame, oos_start, spec.end, top_n),
                                }
                            )

    train_buy_and_hold = _buy_and_hold_benchmarks(adjusted_ohlcv, spec.symbols, spec.start, spec.train_end, backtest_cfg)
    best_train_hold_symbol, best_train_hold_metrics = max(
        train_buy_and_hold.items(),
        key=lambda item: float(item[1].get("cagr", -1.0) or -1.0),
    )
    best_train_hold_cagr = float(best_train_hold_metrics.get("cagr", -1.0) or -1.0)

    for row in candidates:
        row["train_excess_cagr_vs_best_hold"] = float(row["train_metrics"].get("cagr", -1.0) or -1.0) - best_train_hold_cagr
        row["train_validation_excess_cagr_vs_best_hold"] = float(
            (row.get("train_validation_summary", {}) or {}).get("avg_cagr", -1.0) or -1.0
        ) - best_train_hold_cagr

    ranked = sorted(
        candidates,
        key=lambda row: _candidate_score(row, best_train_hold_cagr, spec.target_excess_cagr_vs_best_hold),
        reverse=True,
    )
    price_only_rows = [row for row in ranked if not row["uses_dividends"]]
    dividend_rows = [row for row in ranked if row["uses_dividends"]]
    selected_strategy = ranked[0]
    price_only_best = price_only_rows[0] if price_only_rows else ranked[0]
    dividend_aware_best = dividend_rows[0] if dividend_rows else ranked[0]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(REPORT_DIR, f"income_etf_rotation_{stamp}.json")
    md_path = os.path.join(REPORT_DIR, f"income_etf_rotation_{stamp}.md")

    oos_buy_and_hold = _buy_and_hold_benchmarks(adjusted_ohlcv, spec.symbols, oos_start, spec.end, backtest_cfg)
    best_oos_hold_symbol, best_oos_hold_metrics = max(
        oos_buy_and_hold.items(),
        key=lambda item: float(item[1].get("cagr", -1.0) or -1.0),
    )
    best_oos_hold_cagr = float(best_oos_hold_metrics.get("cagr", -1.0) or -1.0)
    for row in [selected_strategy, price_only_best, dividend_aware_best]:
        row["oos_excess_cagr_vs_best_hold"] = float(row["oos_metrics"].get("cagr", -1.0) or -1.0) - best_oos_hold_cagr
        row["oos_excess_target_met"] = bool(row["oos_excess_cagr_vs_best_hold"] >= float(spec.target_excess_cagr_vs_best_hold))

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "spec": asdict(spec),
        "common_window": {"start": common_start, "end": common_end},
        "oos_window": {"start": oos_start, "end": spec.end},
        "dividend_summary": dividend_summary,
        "train_best_buy_and_hold": {"symbol": best_train_hold_symbol, "metrics": best_train_hold_metrics},
        "oos_best_buy_and_hold": {"symbol": best_oos_hold_symbol, "metrics": best_oos_hold_metrics},
        "selected_strategy": selected_strategy,
        "price_only_best": price_only_best,
        "dividend_aware_best": dividend_aware_best,
        "candidate_count": len(candidates),
        "oos_buy_and_hold": oos_buy_and_hold,
        "report_files": {"json": json_path, "markdown": md_path},
    }

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(_json_safe(summary), handle, ensure_ascii=False, indent=2)
    _write_markdown_report(summary, md_path)
    return summary
