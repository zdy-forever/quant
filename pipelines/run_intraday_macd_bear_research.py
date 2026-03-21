"""
15 分钟 MACD + 日线 MACD 过滤的单标的研究脚本。

策略定义（严格无前视）：
- 入场：15m MACD 金叉，且金叉附近的 DIF 低谷是最近 100 根 15m bar 的最低值
- 过滤：只允许在“上一根已完成日线”满足 DIF > DEA 时开仓
- 出场：止盈 / 止损 / 上一根已完成日线转为 DIF < DEA

这里先做单标的研究，避免把它和横截面多因子混在一起。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from main import fetch_daily_ohlcv, get_alpaca_clients, get_research_adjustment, load_runtime_config

REPORT_DIR = os.path.join("artifacts", "reports")
INTRADAY_CACHE_DIR = os.path.join("artifacts", "cache", "intraday")
NY_TZ = "America/New_York"


@dataclass(frozen=True)
class IntradayMacdSpec:
    symbols: List[str]
    start: str
    end: str
    benchmark_symbol: str = "QQQ"
    timeframe_minutes: int = 15
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    trough_lookback_bars: int = 100
    trough_near_bars: int = 8
    stop_loss_pct: float = 0.03
    take_profit_pct: float = 0.08


def _intraday_cache_path(symbols: List[str], start: str, end: str, minutes: int, adjustment: str) -> str:
    key = "_".join(sorted(symbols))
    safe_key = f"{key[:80]}_{abs(hash((tuple(sorted(symbols)), start, end, minutes, adjustment))) & 0xffffffffffff:012x}"
    os.makedirs(INTRADAY_CACHE_DIR, exist_ok=True)
    return os.path.join(INTRADAY_CACHE_DIR, f"bars_{minutes}m_{start}_{end}_{adjustment}_{safe_key}.csv")


def fetch_intraday_ohlcv(
    data_client,
    symbols: List[str],
    start: str,
    end: str,
    timeframe_minutes: int,
    adjustment: str,
) -> pd.DataFrame:
    from alpaca.data.enums import Adjustment
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    cache_path = _intraday_cache_path(symbols, start, end, timeframe_minutes, adjustment)
    if os.path.exists(cache_path):
        cached = pd.read_csv(cache_path)
        cached["timestamp"] = pd.to_datetime(cached["timestamp"], utc=True)
        return cached.sort_values(["timestamp", "symbol"]).reset_index(drop=True)

    request = StockBarsRequest(
        symbol_or_symbols=sorted({symbol.upper() for symbol in symbols}),
        timeframe=TimeFrame(timeframe_minutes, TimeFrameUnit.Minute),
        start=pd.Timestamp(start, tz="UTC"),
        end=pd.Timestamp(end, tz="UTC"),
        adjustment=Adjustment(str(adjustment).lower()),
    )
    bars = data_client.get_stock_bars(request).df
    if bars is None or bars.empty:
        return pd.DataFrame(columns=["timestamp", "symbol", "open", "high", "low", "close", "volume"])

    df = bars.reset_index()[["timestamp", "symbol", "open", "high", "low", "close", "volume"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df.to_csv(cache_path, index=False)
    return df.sort_values(["timestamp", "symbol"]).reset_index(drop=True)


def _compute_macd(close: pd.Series, fast: int, slow: int, signal: int) -> pd.DataFrame:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = dif - dea
    return pd.DataFrame({"dif": dif, "dea": dea, "hist": hist})


def _build_daily_gate(daily: pd.DataFrame, spec: IntradayMacdSpec) -> pd.DataFrame:
    out_frames: List[pd.DataFrame] = []
    for symbol, frame in daily.groupby("symbol", sort=False):
        row = frame.copy().sort_values("timestamp")
        macd = _compute_macd(row["close"], spec.macd_fast, spec.macd_slow, spec.macd_signal)
        row = pd.concat([row.reset_index(drop=True), macd.reset_index(drop=True)], axis=1)
        row["session_date"] = row["timestamp"].dt.tz_convert(NY_TZ).dt.normalize()
        row["daily_red"] = row["dif"] > row["dea"]
        row["daily_green"] = row["dif"] < row["dea"]
        out_frames.append(row[["symbol", "session_date", "daily_red", "daily_green", "dif", "dea", "hist"]])
    return pd.concat(out_frames, ignore_index=True)


def _attach_previous_daily_gate(intraday: pd.DataFrame, daily_gate: pd.DataFrame) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for symbol, frame in intraday.groupby("symbol", sort=False):
        intra = frame.copy().sort_values("timestamp")
        intra["session_date"] = intra["timestamp"].dt.tz_convert(NY_TZ).dt.normalize()

        daily = daily_gate[daily_gate["symbol"] == symbol].copy().sort_values("session_date")
        if daily.empty:
            intra["daily_red_prev"] = False
            intra["daily_green_prev"] = False
            frames.append(intra)
            continue

        merged = pd.merge_asof(
            intra.sort_values("session_date"),
            daily[["session_date", "daily_red", "daily_green"]].sort_values("session_date"),
            on="session_date",
            direction="backward",
            allow_exact_matches=False,
        )
        merged = merged.rename(columns={"daily_red": "daily_red_prev", "daily_green": "daily_green_prev"})
        frames.append(merged.sort_values("timestamp"))
    return pd.concat(frames, ignore_index=True).sort_values(["timestamp", "symbol"]).reset_index(drop=True)


def _build_intraday_signals(intraday: pd.DataFrame, spec: IntradayMacdSpec) -> pd.DataFrame:
    out_frames: List[pd.DataFrame] = []
    for symbol, frame in intraday.groupby("symbol", sort=False):
        row = frame.copy().sort_values("timestamp")
        macd = _compute_macd(row["close"], spec.macd_fast, spec.macd_slow, spec.macd_signal)
        row = pd.concat([row.reset_index(drop=True), macd.reset_index(drop=True)], axis=1)
        row["bull_cross"] = (row["dif"] > row["dea"]) & (row["dif"].shift(1) <= row["dea"].shift(1))
        rolling_min_100 = row["dif"].rolling(spec.trough_lookback_bars).min()
        recent_min_near = row["dif"].shift(1).rolling(spec.trough_near_bars).min()
        row["trough_extreme"] = recent_min_near <= (rolling_min_100.shift(1) + 1e-12)
        row["entry_signal"] = row["bull_cross"] & row["trough_extreme"] & row["daily_red_prev"].fillna(False)
        out_frames.append(row)
    return pd.concat(out_frames, ignore_index=True).sort_values(["timestamp", "symbol"]).reset_index(drop=True)


def _run_single_symbol_backtest(frame: pd.DataFrame, spec: IntradayMacdSpec) -> Dict[str, Any]:
    row = frame.copy().sort_values("timestamp").reset_index(drop=True)
    trades: List[Dict[str, Any]] = []
    equity = 1.0
    equity_curve: List[Dict[str, Any]] = [{"timestamp": row.loc[0, "timestamp"], "equity": equity}]

    position: Dict[str, Any] | None = None
    pending_entry = False

    for idx in range(1, len(row)):
        current = row.loc[idx]
        prev = row.loc[idx - 1]

        if pending_entry and position is None:
            entry_price = float(current["open"])
            if np.isfinite(entry_price) and entry_price > 0:
                position = {
                    "entry_ts": current["timestamp"],
                    "entry_price": entry_price,
                    "entry_daily_red_prev": bool(current.get("daily_red_prev", False)),
                }
            pending_entry = False

        if position is not None:
            stop_price = position["entry_price"] * (1.0 - spec.stop_loss_pct)
            take_price = position["entry_price"] * (1.0 + spec.take_profit_pct)
            exit_reason = None
            exit_price = None

            low_price = float(current["low"])
            high_price = float(current["high"])
            open_price = float(current["open"])
            close_price = float(current["close"])

            # 保守处理：同一根 bar 同时碰到止盈止损时先按止损算
            if np.isfinite(low_price) and low_price <= stop_price:
                exit_reason = "stop_loss"
                exit_price = stop_price
            elif np.isfinite(high_price) and high_price >= take_price:
                exit_reason = "take_profit"
                exit_price = take_price
            elif bool(current.get("daily_green_prev", False)):
                exit_reason = "daily_macd_green"
                exit_price = open_price if np.isfinite(open_price) else close_price

            marked_price = close_price if np.isfinite(close_price) else position["entry_price"]
            marked_equity = equity * (marked_price / position["entry_price"])
            equity_curve.append({"timestamp": current["timestamp"], "equity": marked_equity})

            if exit_reason is not None and exit_price is not None and np.isfinite(exit_price):
                trade_return = exit_price / position["entry_price"] - 1.0
                equity *= 1.0 + trade_return
                trades.append(
                    {
                        "entry_ts": str(position["entry_ts"]),
                        "exit_ts": str(current["timestamp"]),
                        "entry_price": position["entry_price"],
                        "exit_price": float(exit_price),
                        "return": float(trade_return),
                        "reason": exit_reason,
                    }
                )
                equity_curve[-1]["equity"] = equity
                position = None
        else:
            equity_curve.append({"timestamp": current["timestamp"], "equity": equity})

        if position is None and bool(prev.get("entry_signal", False)):
            pending_entry = True

    if position is not None:
        final_close = float(row.iloc[-1]["close"])
        if np.isfinite(final_close) and final_close > 0:
            trade_return = final_close / position["entry_price"] - 1.0
            equity *= 1.0 + trade_return
            trades.append(
                {
                    "entry_ts": str(position["entry_ts"]),
                    "exit_ts": str(row.iloc[-1]["timestamp"]),
                    "entry_price": position["entry_price"],
                    "exit_price": final_close,
                    "return": float(trade_return),
                    "reason": "end_of_test",
                }
            )
            equity_curve.append({"timestamp": row.iloc[-1]["timestamp"], "equity": equity})

    curve = pd.DataFrame(equity_curve).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    curve["timestamp"] = pd.to_datetime(curve["timestamp"], utc=True)
    curve = curve.set_index("timestamp")
    metrics = _compute_equity_metrics(curve["equity"], len(trades))
    return {
        "symbol": str(frame.iloc[0]["symbol"]),
        "metrics": metrics,
        "trade_count": len(trades),
        "trades": trades[:25],
    }


def _compute_equity_metrics(equity_curve: pd.Series, trade_count: int) -> Dict[str, float]:
    if equity_curve.empty or len(equity_curve) < 2:
        return {"cagr": 0.0, "max_dd": 0.0, "sharpe": 0.0, "total_return": 0.0, "trade_count": float(trade_count)}
    returns = equity_curve.pct_change().dropna()
    if returns.empty:
        return {"cagr": 0.0, "max_dd": 0.0, "sharpe": 0.0, "total_return": 0.0, "trade_count": float(trade_count)}
    years = max((equity_curve.index[-1] - equity_curve.index[0]).days / 365.25, 1e-9)
    total_return = float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1.0)
    cagr = float((equity_curve.iloc[-1] / equity_curve.iloc[0]) ** (1.0 / years) - 1.0)
    peak = equity_curve.cummax()
    max_dd = float((equity_curve / peak - 1.0).min())
    sharpe = float(returns.mean() / (returns.std(ddof=0) + 1e-12) * np.sqrt(252.0 * 26.0))
    return {
        "cagr": cagr,
        "max_dd": max_dd,
        "sharpe": sharpe,
        "total_return": total_return,
        "trade_count": float(trade_count),
    }


def _buy_hold_drawdown(daily: pd.DataFrame, symbol: str, start: str, end: str) -> Dict[str, float]:
    row = daily[(daily["symbol"] == symbol) & (daily["timestamp"] >= pd.Timestamp(start, tz="UTC")) & (daily["timestamp"] <= pd.Timestamp(end, tz="UTC"))].copy()
    row = row.sort_values("timestamp")
    if row.empty:
        return {"total_return": 0.0, "max_dd": 0.0}
    equity = row["close"] / row["close"].iloc[0]
    peak = equity.cummax()
    return {
        "total_return": float(equity.iloc[-1] - 1.0),
        "max_dd": float((equity / peak - 1.0).min()),
    }


def run_intraday_macd_research(spec: IntradayMacdSpec) -> Dict[str, Any]:
    runtime = load_runtime_config()
    data_client, _ = get_alpaca_clients()
    adjustment = get_research_adjustment(runtime)

    daily = fetch_daily_ohlcv(data_client, sorted(set(spec.symbols + [spec.benchmark_symbol])), spec.start, spec.end, adjustment=adjustment)
    intraday = fetch_intraday_ohlcv(data_client, spec.symbols, spec.start, spec.end, spec.timeframe_minutes, adjustment)

    daily_gate = _build_daily_gate(daily, spec)
    merged = _attach_previous_daily_gate(intraday, daily_gate)
    merged = _build_intraday_signals(merged, spec)

    symbol_results = [_run_single_symbol_backtest(frame, spec) for _, frame in merged.groupby("symbol", sort=False)]
    symbol_results = sorted(symbol_results, key=lambda row: row["metrics"]["total_return"], reverse=True)

    benchmark = _buy_hold_drawdown(daily, spec.benchmark_symbol, spec.start, spec.end)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "spec": asdict(spec),
        "benchmark": {
            "symbol": spec.benchmark_symbol,
            **benchmark,
        },
        "symbol_results": symbol_results,
        "best_symbol": symbol_results[0] if symbol_results else None,
        "median_total_return": float(np.median([row["metrics"]["total_return"] for row in symbol_results])) if symbol_results else 0.0,
        "positive_ratio": float(np.mean([row["metrics"]["total_return"] > 0 for row in symbol_results])) if symbol_results else 0.0,
    }

    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(REPORT_DIR, f"intraday_macd_bear_research_{stamp}.json")
    md_path = os.path.join(REPORT_DIR, f"intraday_macd_bear_research_{stamp}.md")
    summary["report_files"] = {"json": json_path, "markdown": md_path}

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)

    lines = [
        "# Intraday MACD Bear Research",
        "",
        f"- Generated at: `{summary['generated_at_utc']}`",
        f"- Symbols: `{', '.join(spec.symbols)}`",
        f"- Window: `{spec.start}` -> `{spec.end}`",
        f"- Benchmark `{spec.benchmark_symbol}` total return: `{benchmark['total_return']:.2%}`",
        f"- Benchmark `{spec.benchmark_symbol}` max drawdown: `{benchmark['max_dd']:.2%}`",
        f"- Positive ratio: `{summary['positive_ratio']:.2%}`",
        f"- Median total return: `{summary['median_total_return']:.2%}`",
        "",
    ]
    if summary["best_symbol"]:
        best = summary["best_symbol"]
        lines.extend(
            [
                "## Best Symbol",
                "",
                f"- Symbol: `{best['symbol']}`",
                f"- Total return: `{best['metrics']['total_return']:.2%}`",
                f"- CAGR: `{best['metrics']['cagr']:.2%}`",
                f"- MaxDD: `{best['metrics']['max_dd']:.2%}`",
                f"- Sharpe: `{best['metrics']['sharpe']:.3f}`",
                f"- Trades: `{int(best['trade_count'])}`",
            ]
        )
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest 15m MACD + daily MACD gate strategy on selected symbols")
    parser.add_argument("--symbols", nargs="+", default=["QQQ", "SPY"])
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--benchmark-symbol", default="QQQ")
    parser.add_argument("--stop-loss-pct", type=float, default=0.03)
    parser.add_argument("--take-profit-pct", type=float, default=0.08)
    args = parser.parse_args()

    summary = run_intraday_macd_research(
        IntradayMacdSpec(
            symbols=[str(x).upper() for x in args.symbols],
            start=args.start,
            end=args.end,
            benchmark_symbol=args.benchmark_symbol.upper(),
            stop_loss_pct=args.stop_loss_pct,
            take_profit_pct=args.take_profit_pct,
        )
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
