# -*- coding: utf-8 -*-
"""
组合回测引擎。

这个文件比之前的“极简回测”更完整，主要负责：
- 把信号转换成每日目标权重
- 按日频做组合级收益计算
- 计入换手成本
- 支持固定止损、止盈、ATR 追踪止损、最大持有天数
- 输出更完整的绩效指标

如果你之后想继续提高回测真实性，这里会是最核心的底层模块。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestConfig:
    max_positions: int = 10
    gross_exposure: float = 1.0
    rebalance_every_n_days: int = 1
    min_score_threshold: float = -999.0
    rank_weight_power: float = 0.0
    hold_rank_buffer: int = 0
    score_hysteresis: float = 0.0
    max_entry_turnover_per_rebalance: float = 0.0
    dynamic_breadth_score_threshold: float = -999.0
    min_dynamic_positions: int = 0
    slippage_bps: float = 5.0
    commission_bps: float = 0.0
    stop_loss_pct: float = 0.08
    take_profit_pct: float = 0.25
    trailing_stop_atr_multiple: float = 3.0
    atr_window: int = 20
    max_holding_days: int = 120
    portfolio_soft_dd_limit: float = 0.0
    portfolio_deleverage_ratio: float = 1.0
    portfolio_hard_dd_limit: float = 0.0
    portfolio_kill_cooldown_days: int = 0


def _prepare_ohlcv(ohlcv: pd.DataFrame) -> pd.DataFrame:
    df = ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values(["timestamp", "symbol"]).reset_index(drop=True)


def _compute_atr_panel(ohlcv: pd.DataFrame, window: int) -> pd.DataFrame:
    df = _prepare_ohlcv(ohlcv)
    grouped = df.groupby("symbol", group_keys=False)
    prev_close = grouped["close"].shift(1)

    tr_components = pd.concat(
        [
            (df["high"] - df["low"]).abs(),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    df["tr"] = tr_components.max(axis=1)
    df["atr"] = grouped["tr"].transform(lambda s: s.rolling(window).mean())

    return (
        df.pivot(index="timestamp", columns="symbol", values="atr")
        .sort_index()
        .astype(float)
    )


def build_daily_target_weights(
    signals: pd.Series,
    score: pd.Series | None,
    dates: pd.Index,
    cfg: BacktestConfig,
) -> pd.DataFrame:
    """
    把信号序列转换成按天的目标权重矩阵。
    """

    sig_df = signals.rename("signal").reset_index()
    sig_df["timestamp"] = pd.to_datetime(sig_df["timestamp"], utc=True)
    sig_df["signal"] = sig_df["signal"].astype(float)

    if score is not None:
        score_df = score.rename("score").reset_index()
        score_df["timestamp"] = pd.to_datetime(score_df["timestamp"], utc=True)
        universe_df = score_df.merge(sig_df, on=["timestamp", "symbol"], how="left")
        universe_df["signal"] = universe_df["signal"].fillna(0.0).astype(float)
    else:
        universe_df = sig_df.copy()
        universe_df["score"] = universe_df["signal"]

    universe_df = universe_df[universe_df["score"].notna()].copy()
    if universe_df.empty:
        return pd.DataFrame(index=dates)

    date_index = pd.DatetimeIndex(pd.to_datetime(pd.Index(dates), utc=True))
    if date_index.empty:
        return pd.DataFrame(index=date_index)
    all_symbols = sorted(universe_df["symbol"].astype(str).unique())

    entry_threshold = float(cfg.min_score_threshold)
    hold_threshold = entry_threshold - max(float(cfg.score_hysteresis), 0.0)

    selected_symbols: list[str] = []
    weight_rows: list[pd.DataFrame] = []

    for timestamp in date_index:
        daily_df = universe_df[universe_df["timestamp"] == timestamp].copy()
        if daily_df.empty:
            selected_symbols = []
            continue

        daily_df = daily_df.sort_values(["score", "symbol"], ascending=[False, True]).reset_index(drop=True)
        daily_df["rank"] = np.arange(1, len(daily_df) + 1, dtype=float)

        entry_df = daily_df[
            (daily_df["signal"] > 0.0) & (daily_df["score"] >= entry_threshold)
        ].copy()
        effective_max_positions = int(cfg.max_positions)
        dynamic_breadth_threshold = float(cfg.dynamic_breadth_score_threshold)
        if dynamic_breadth_threshold > -998.0:
            strong_count = int(entry_df["score"].ge(dynamic_breadth_threshold).sum())
            effective_max_positions = min(
                effective_max_positions,
                max(int(cfg.min_dynamic_positions), strong_count),
            )
        hold_rank_limit = max(effective_max_positions + max(int(cfg.hold_rank_buffer), 0), effective_max_positions)

        retained_symbols: list[str] = []
        if selected_symbols:
            retain_df = daily_df[daily_df["symbol"].isin(selected_symbols)].copy()
            retain_df = retain_df[
                (retain_df["score"] >= hold_threshold) & (retain_df["rank"] <= float(hold_rank_limit))
            ]
            retained_symbols = retain_df.sort_values(["rank", "symbol"])["symbol"].astype(str).tolist()

        next_symbols = list(retained_symbols)
        for symbol in entry_df["symbol"].astype(str):
            if len(next_symbols) >= int(effective_max_positions):
                break
            if symbol in next_symbols:
                continue
            next_symbols.append(symbol)

        if not next_symbols:
            selected_symbols = []
            continue

        selected_df = daily_df[daily_df["symbol"].isin(next_symbols)].copy()
        if selected_df.empty:
            selected_symbols = []
            continue

        if float(cfg.rank_weight_power) > 0.0:
            selected_df["rank_weight"] = (
                (float(max(effective_max_positions, 1)) - selected_df["rank"] + 1.0).clip(lower=1.0) ** float(cfg.rank_weight_power)
            )
            rank_weight_sum = float(selected_df["rank_weight"].sum())
            selected_df["weight"] = selected_df["rank_weight"] / max(rank_weight_sum, 1e-12)
        else:
            selected_df["weight"] = 1.0 / float(len(selected_df))

        selected_df["weight"] = selected_df["weight"] * float(cfg.gross_exposure)
        weight_rows.append(selected_df[["timestamp", "symbol", "weight"]].copy())
        selected_symbols = selected_df.sort_values(["rank", "symbol"])["symbol"].astype(str).tolist()

    if not weight_rows:
        return pd.DataFrame(index=date_index)

    weight_df = pd.concat(weight_rows, ignore_index=True)
    weights = (
        weight_df.pivot(index="timestamp", columns="symbol", values="weight")
        .reindex(index=date_index, columns=all_symbols)
        .fillna(0.0)
        .astype(float)
    )
    return weights


def combine_strategy_weight_frames(
    strategy_weights: Dict[str, pd.DataFrame],
    strategy_allocations: pd.DataFrame,
    gross_exposure: float = 1.0,
) -> pd.DataFrame:
    """
    把多个策略的股票权重按“策略层权重”混合成一个组合。
    """

    if not strategy_weights:
        return pd.DataFrame(index=strategy_allocations.index)

    all_dates = strategy_allocations.index
    all_symbols = sorted({symbol for frame in strategy_weights.values() for symbol in frame.columns})
    combined = pd.DataFrame(0.0, index=all_dates, columns=all_symbols)

    for strategy_name, frame in strategy_weights.items():
        if strategy_name not in strategy_allocations.columns:
            continue
        alloc = strategy_allocations[strategy_name]
        aligned = frame.reindex(index=all_dates, columns=all_symbols).fillna(0.0)
        combined = combined.add(aligned.mul(alloc, axis=0), fill_value=0.0)

    gross = combined.abs().sum(axis=1).replace(0.0, np.nan)
    combined = combined.div(gross, axis=0).mul(gross_exposure).fillna(0.0)
    return combined


def _compute_metrics(
    equity_curve: pd.Series,
    turnover: pd.Series,
    active_positions: pd.Series,
    trade_count: int,
) -> Dict[str, float]:
    if equity_curve.empty:
        return {
            "sharpe": np.nan,
            "sortino": np.nan,
            "cagr": np.nan,
            "max_dd": np.nan,
            "calmar": np.nan,
            "annual_vol": np.nan,
            "avg_turnover": np.nan,
            "avg_active_positions": np.nan,
            "trade_count": float(trade_count),
        }

    returns = equity_curve.pct_change().dropna()
    if returns.empty:
        return {
            "sharpe": np.nan,
            "sortino": np.nan,
            "cagr": np.nan,
            "max_dd": np.nan,
            "calmar": np.nan,
            "annual_vol": np.nan,
            "avg_turnover": float(turnover.mean()) if not turnover.empty else np.nan,
            "avg_active_positions": float(active_positions.mean()) if not active_positions.empty else np.nan,
            "trade_count": float(trade_count),
        }

    annual_vol = float(returns.std(ddof=0) * np.sqrt(252.0))
    downside = returns[returns < 0]
    downside_vol = float(downside.std(ddof=0) * np.sqrt(252.0)) if not downside.empty else np.nan
    sharpe = float(returns.mean() / (returns.std(ddof=0) + 1e-12) * np.sqrt(252.0))
    sortino = float(returns.mean() / (downside_vol / np.sqrt(252.0) + 1e-12) * np.sqrt(252.0))
    years = max((equity_curve.index[-1] - equity_curve.index[0]).days / 365.25, 1e-9)
    cagr = float((equity_curve.iloc[-1] / equity_curve.iloc[0]) ** (1.0 / years) - 1.0)
    peak = equity_curve.cummax()
    max_dd = float((equity_curve / peak - 1.0).min())
    calmar = float(cagr / (abs(max_dd) + 1e-12))

    return {
        "sharpe": sharpe,
        "sortino": sortino,
        "cagr": cagr,
        "max_dd": max_dd,
        "calmar": calmar,
        "annual_vol": annual_vol,
        "avg_turnover": float(turnover.mean()) if not turnover.empty else np.nan,
        "avg_active_positions": float(active_positions.mean()) if not active_positions.empty else np.nan,
        "trade_count": float(trade_count),
    }


def run_weight_backtest(
    ohlcv: pd.DataFrame,
    target_weights: pd.DataFrame,
    cfg: BacktestConfig,
) -> Dict[str, Any]:
    """
    用每日目标权重做组合回测。
    """

    df = _prepare_ohlcv(ohlcv)
    close_px = df.pivot(index="timestamp", columns="symbol", values="close").sort_index()
    high_px = df.pivot(index="timestamp", columns="symbol", values="high").sort_index()
    low_px = df.pivot(index="timestamp", columns="symbol", values="low").sort_index()
    atr_px = _compute_atr_panel(df, cfg.atr_window).reindex(close_px.index)

    weights = target_weights.reindex(index=close_px.index, columns=close_px.columns).fillna(0.0)
    cost_ratio = (cfg.slippage_bps + cfg.commission_bps) / 10_000.0

    equity = 1.0
    equity_values = [equity]
    turnover_values = [0.0]
    active_values = [0.0]
    drawdown_values = [0.0]
    gross_cap_values = [float(cfg.gross_exposure)]

    current_weights = pd.Series(0.0, index=close_px.columns)
    executed_weight_rows = [current_weights.copy()]
    current_states: Dict[str, Dict[str, Any]] = {}
    trade_count = 0
    peak_equity = equity
    hard_kill_count = 0
    soft_deleverage_days = 0
    cooldown_days_applied = 0
    kill_cooldown_remaining = 0

    for idx in range(1, len(close_px.index)):
        prev_ts = close_px.index[idx - 1]
        curr_ts = close_px.index[idx]

        prev_close = close_px.loc[prev_ts]
        curr_close = close_px.loc[curr_ts]
        close_ret = (curr_close / prev_close - 1.0).replace([np.inf, -np.inf], 0.0).fillna(0.0)
        equity *= 1.0 + float((current_weights * close_ret).sum())
        peak_equity = max(peak_equity, equity)
        current_drawdown = equity / max(peak_equity, 1e-12) - 1.0

        next_weights = weights.loc[curr_ts].copy()
        if cfg.rebalance_every_n_days > 1 and idx % cfg.rebalance_every_n_days != 0:
            next_weights = current_weights.copy()

        for symbol, state in list(current_states.items()):
            if symbol not in close_px.columns:
                next_weights[symbol] = 0.0
                current_states.pop(symbol, None)
                continue

            high_value = float(high_px.at[curr_ts, symbol]) if pd.notna(high_px.at[curr_ts, symbol]) else np.nan
            low_value = float(low_px.at[curr_ts, symbol]) if pd.notna(low_px.at[curr_ts, symbol]) else np.nan
            close_value = float(curr_close[symbol]) if pd.notna(curr_close[symbol]) else state["last_close"]
            atr_value = float(atr_px.at[curr_ts, symbol]) if symbol in atr_px.columns and pd.notna(atr_px.at[curr_ts, symbol]) else np.nan

            state["days_held"] += 1
            state["peak_price"] = max(state["peak_price"], high_value if np.isfinite(high_value) else close_value)

            hard_stop = state["entry_price"] * (1.0 - cfg.stop_loss_pct) if float(cfg.stop_loss_pct) > 0.0 else -np.inf
            take_profit = state["entry_price"] * (1.0 + cfg.take_profit_pct) if float(cfg.take_profit_pct) > 0.0 else np.inf
            trailing_stop = (
                state["peak_price"] - cfg.trailing_stop_atr_multiple * atr_value
                if float(cfg.trailing_stop_atr_multiple) > 0.0 and np.isfinite(atr_value)
                else -np.inf
            )
            effective_stop = max(hard_stop, trailing_stop)

            stop_hit = np.isfinite(low_value) and low_value <= effective_stop
            take_profit_hit = np.isfinite(high_value) and high_value >= take_profit
            time_exit = state["days_held"] >= cfg.max_holding_days

            if stop_hit or take_profit_hit or time_exit:
                next_weights[symbol] = 0.0
                current_states.pop(symbol, None)
                trade_count += 1
            else:
                state["last_close"] = close_value

        next_weights = next_weights.where(curr_close.notna(), 0.0).fillna(0.0)
        allowed_gross = float(cfg.gross_exposure)
        hard_limit = max(0.0, float(cfg.portfolio_hard_dd_limit))
        soft_limit = max(0.0, float(cfg.portfolio_soft_dd_limit))
        deleverage_ratio = min(max(float(cfg.portfolio_deleverage_ratio), 0.0), 1.0)

        if kill_cooldown_remaining > 0:
            next_weights = next_weights * 0.0
            kill_cooldown_remaining -= 1
            cooldown_days_applied += 1
        elif hard_limit > 0.0 and current_drawdown <= -hard_limit:
            next_weights = next_weights * 0.0
            hard_kill_count += 1
            kill_cooldown_remaining = max(int(cfg.portfolio_kill_cooldown_days), 0)
        elif soft_limit > 0.0 and deleverage_ratio < 1.0 and current_drawdown <= -soft_limit:
            allowed_gross = float(cfg.gross_exposure) * deleverage_ratio

        gross = float(next_weights.abs().sum())
        if gross > allowed_gross and gross > 1e-12:
            next_weights = next_weights * (allowed_gross / gross)
            if allowed_gross < float(cfg.gross_exposure):
                soft_deleverage_days += 1

        max_entry_turnover = max(float(cfg.max_entry_turnover_per_rebalance), 0.0)
        if max_entry_turnover > 0.0:
            delta = next_weights - current_weights
            buy_delta = delta.clip(lower=0.0)
            buy_turnover = float(buy_delta.sum())
            if buy_turnover > max_entry_turnover and buy_turnover > 1e-12:
                scaled_buy_delta = buy_delta * (max_entry_turnover / buy_turnover)
                next_weights = current_weights + delta.clip(upper=0.0) + scaled_buy_delta
                next_weights = next_weights.clip(lower=0.0)

        turnover = float((next_weights - current_weights).abs().sum())
        equity *= max(0.0, 1.0 - turnover * cost_ratio)

        for symbol, weight in next_weights[next_weights > 0].items():
            if symbol not in current_states:
                entry_price = float(curr_close[symbol])
                current_states[symbol] = {
                    "entry_price": entry_price,
                    "peak_price": entry_price,
                    "days_held": 0,
                    "last_close": entry_price,
                }

        current_weights = next_weights
        equity_values.append(equity)
        turnover_values.append(turnover)
        active_values.append(float((current_weights > 0).sum()))
        drawdown_values.append(float(current_drawdown))
        gross_cap_values.append(float(allowed_gross))
        executed_weight_rows.append(current_weights.copy())

    equity_curve = pd.Series(equity_values, index=close_px.index, name="equity")
    turnover_series = pd.Series(turnover_values, index=close_px.index, name="turnover")
    active_series = pd.Series(active_values, index=close_px.index, name="active_positions")
    drawdown_series = pd.Series(drawdown_values, index=close_px.index, name="portfolio_drawdown")
    gross_cap_series = pd.Series(gross_cap_values, index=close_px.index, name="gross_exposure_cap")
    executed_weights = pd.DataFrame(executed_weight_rows, index=close_px.index).reindex(columns=close_px.columns).fillna(0.0)

    return {
        "config": asdict(cfg),
        "equity_curve": equity_curve,
        "turnover": turnover_series,
        "active_positions": active_series,
        "daily_weights": weights,
        "executed_weights": executed_weights,
        "portfolio_drawdown": drawdown_series,
        "gross_exposure_cap": gross_cap_series,
        "risk_overlay": {
            "soft_deleverage_days": float(soft_deleverage_days),
            "hard_kill_count": float(hard_kill_count),
            "cooldown_days_applied": float(cooldown_days_applied),
        },
        "metrics": _compute_metrics(equity_curve, turnover_series, active_series, trade_count),
    }


def run_signal_backtest(
    ohlcv: pd.DataFrame,
    signals: pd.Series,
    score: pd.Series | None = None,
    cfg: BacktestConfig | None = None,
) -> Dict[str, Any]:
    if cfg is None:
        cfg = BacktestConfig()

    dates = (
        _prepare_ohlcv(ohlcv)["timestamp"]
        .drop_duplicates()
        .sort_values()
        .reset_index(drop=True)
    )
    target_weights = build_daily_target_weights(signals, score, pd.Index(dates), cfg)
    return run_weight_backtest(ohlcv, target_weights, cfg)
