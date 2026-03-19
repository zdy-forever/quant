# -*- coding: utf-8 -*-
"""
项目新的统一入口文件。

如果你是量化新手，可以把它理解成“总控制台”：
1. `train` 用训练区间做研究并冻结参数
2. `test` 用样本外区间验证冻结后的策略
3. `walk-forward` 看多个时间窗口上的稳定性
4. `deploy` 把冻结后的策略接到 Alpaca Paper 模拟盘

日后你最常微调的通常不是这里的主流程，而是：
- `config/runtime.yaml` 里的运行期参数
- `strategy/` 里的策略逻辑
- `portfolio/` 和 `risk/` 里的仓位与风控规则
"""
from __future__ import annotations

import argparse
import json
import os
from typing import TYPE_CHECKING, Dict, List
from zoneinfo import ZoneInfo
import pandas as pd

if TYPE_CHECKING:
    from regime.detection import RegimeLabel
    from risk.management import RiskConfig

DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "GOOGL"]
NY_TZ = ZoneInfo("America/New_York")
FREE_PLAN_DELAY_MINUTES = 15


def load_runtime_config(path: str = "config/runtime.yaml") -> dict:
    import yaml

    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_symbols(path: str = "config/symbols.txt") -> List[str]:
    if not os.path.exists(path):
        return DEFAULT_SYMBOLS.copy()

    symbols: List[str] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            symbol = line.strip().upper()
            if symbol and not symbol.startswith("#"):
                symbols.append(symbol)
    return symbols or DEFAULT_SYMBOLS.copy()


def get_alpaca_clients():
    """兼容旧和新的 Alpaca 凭证变量名。"""

    from dotenv import load_dotenv

    load_dotenv()
    key = os.getenv("ALPACA_API_KEY") or os.getenv("ALPACA_PAPER1_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET") or os.getenv("ALPACA_PAPER1_API_SECRET_KEY")
    if not key or not secret:
        raise ValueError(
            "缺少 Alpaca 凭证。请设置 ALPACA_API_KEY / ALPACA_API_SECRET "
            "或旧变量名 ALPACA_PAPER1_API_KEY_ID / ALPACA_PAPER1_API_SECRET_KEY。"
        )

    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.trading.client import TradingClient

    data_client = StockHistoricalDataClient(key, secret)
    trading_client = TradingClient(key, secret, paper=True)
    return data_client, trading_client


def fetch_daily_ohlcv(data_client, symbols: List[str], start: str, end: str) -> pd.DataFrame:


    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    request_kwargs = {
        "symbol_or_symbols": symbols,
        "timeframe": TimeFrame.Day,
        "start": pd.Timestamp(start, tz="UTC"),
        "end": pd.Timestamp(end, tz="UTC"),
    }
    request = StockBarsRequest(**request_kwargs)
    bars = data_client.get_stock_bars(request).df
    if bars is None or bars.empty:
        return pd.DataFrame(columns=["timestamp", "symbol", "open", "high", "low", "close", "volume"])

    df = bars.reset_index()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = df["symbol"].astype(str)
    return df[["timestamp", "symbol", "open", "high", "low", "close", "volume"]].sort_values(
        ["timestamp", "symbol"]
    )


def drop_unconfirmed_daily_bar_for_free_plan(
    ohlcv: pd.DataFrame,
    now_utc: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Alpaca 免费数据常见场景是美股数据存在约 15 分钟延迟。

    对日线策略来说，最危险的地方不是“旧 15 分钟”，而是：
    在美东当日收盘前，或者刚收盘但延迟窗口还没结束时，
    代码把“今天这根尚未完全确认的日线”拿来生成信号。

    这里的处理原则很保守：
    - 如果最新 bar 的日期就是当前美东日期
    - 且现在还没到 16:15 ET
    - 就直接丢弃这一天的数据，只用上一个完整交易日
    """

    if ohlcv.empty:
        return ohlcv

    if now_utc is None:
        now_utc = pd.Timestamp.now(tz="UTC")
    else:
        now_utc = pd.to_datetime(now_utc, utc=True)

    now_ny = now_utc.tz_convert(NY_TZ)
    latest_ts = pd.to_datetime(ohlcv["timestamp"].max(), utc=True)
    latest_ny = latest_ts.tz_convert(NY_TZ)

    market_close_with_delay = now_ny.normalize() + pd.Timedelta(hours=16, minutes=FREE_PLAN_DELAY_MINUTES)
    same_market_day = latest_ny.date() == now_ny.date()
    bar_not_confirmed = now_ny < market_close_with_delay

    if same_market_day and bar_not_confirmed:
        safe_ohlcv = ohlcv[ohlcv["timestamp"] < latest_ts].copy()
        if not safe_ohlcv.empty:
            print(
                "[INFO] Alpaca free data may be delayed by 15 minutes. "
                "Dropped today's unconfirmed daily bar and used the previous completed session."
            )
            return safe_ohlcv

    return ohlcv


def load_frozen_params(strategy_name: str) -> Dict[str, float]:
    path = os.path.join("artifacts", "frozen_params", f"{strategy_name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"缺少冻结参数：{path}（请先运行 train）")
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload["params"]


def choose_strategy_by_regime(regime: RegimeLabel) -> str:
    from regime.detection import RegimeLabel

    if regime in (RegimeLabel.TREND_LOW_VOL, RegimeLabel.TREND_HIGH_VOL):
        return "trend"
    return "mean_reversion"


def submit_bracket_orders(
    trading_client,
    weights: Dict[str, float],
    latest_prices: Dict[str, float],
    equity: float,
    risk_cfg: RiskConfig,
    dry_run: bool = True,
) -> None:
    import numpy as np

    from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest

    for symbol, weight in weights.items():
        price = float(latest_prices.get(symbol, np.nan))
        if not np.isfinite(price) or price <= 0:
            continue

        notional = equity * float(weight)
        qty = int(notional / price)
        if qty <= 0:
            continue

        stop_price = round(price * (1.0 - risk_cfg.stop_loss_pct), 2)
        take_profit = round(price * (1.0 + risk_cfg.take_profit_pct), 2)
        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            stop_loss=StopLossRequest(stop_price=stop_price),
            take_profit=TakeProfitRequest(limit_price=take_profit),
        )

        if dry_run:
            print(
                f"[DRY_RUN] submit {symbol} qty={qty} "
                f"px~{price:.2f} SL={stop_price} TP={take_profit}"
            )
        else:
            response = trading_client.submit_order(order_data=order)
            print(f"SUBMITTED {symbol}: {getattr(response, 'id', '-')}")


def cmd_train(args: argparse.Namespace) -> None:
    from backtest.train import TrainSpec, train

    data_client, _ = get_alpaca_clients()
    symbols = load_symbols()
    ohlcv = fetch_daily_ohlcv(data_client, symbols, args.start, args.end)

    spec = TrainSpec(
        symbols=symbols,
        start=args.start,
        end=args.end,
        objective=args.objective,
        overwrite_frozen=args.overwrite_frozen,
    )
    result = train(ohlcv, spec, strategies=args.strategies)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_test(args: argparse.Namespace) -> None:
    from backtest.test import TestSpec, run_oos_test

    data_client, _ = get_alpaca_clients()
    symbols = load_symbols()
    ohlcv = fetch_daily_ohlcv(data_client, symbols, args.start, args.end)

    spec = TestSpec(symbols=symbols, start=args.start, end=args.end, strategies=args.strategies)
    result = run_oos_test(ohlcv, spec)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_walk_forward(args: argparse.Namespace) -> None:
    from backtest.walk_forward import WalkForwardSpec, run_walk_forward

    data_client, _ = get_alpaca_clients()
    symbols = load_symbols()
    ohlcv = fetch_daily_ohlcv(data_client, symbols, args.start, args.end)

    spec = WalkForwardSpec(
        symbols=symbols,
        start=args.start,
        end=args.end,
        strategies=args.strategies,
        train_years=args.train_years,
        test_months=args.test_months,
        step_months=args.step_months,
        gap_days=args.gap_days,
    )
    result = run_walk_forward(ohlcv, spec)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_deploy(args: argparse.Namespace) -> None:
    import pandas as pd

    from portfolio.position_sizing import PositionConfig, compute_weights_from_signals
    from regime.detection import RegimeConfig, RegimeLabel, detect_regime
    from risk.management import RiskConfig, clamp_weights
    from strategy.mean_reversion.mean_reversion import MeanReversionBollingerStrategy
    from strategy.trend.trend import TrendBreakoutStrategy

    runtime = load_runtime_config()
    regime_cfg = RegimeConfig(**(runtime.get("regime", {}) or {}))
    position_cfg = PositionConfig(**(runtime.get("position", {}) or {}))
    risk_cfg = RiskConfig(**(runtime.get("risk", {}) or {}))

    data_client, trading_client = get_alpaca_clients()
    symbols = load_symbols()

    end = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    start = (pd.Timestamp.utcnow() - pd.Timedelta(days=800)).strftime("%Y-%m-%d")
    fetch_symbols = sorted(set(symbols + [regime_cfg.symbol_for_regime]))
    ohlcv = fetch_daily_ohlcv(data_client, fetch_symbols, start, end)
    ohlcv = drop_unconfirmed_daily_bar_for_free_plan(ohlcv)
    if ohlcv.empty:
        raise RuntimeError("未获取到任何行情数据。")

    regime = detect_regime(ohlcv, regime_cfg)
    print(f"Regime = {regime}")

    if regime == RegimeLabel.RANGE_HIGH_VOL and regime_cfg.no_trade_in_range_high_vol:
        print("Regime=RANGE_HIGH_VOL，按配置不交易。")
        return

    chosen_strategy = choose_strategy_by_regime(regime)
    strategy = (
        TrendBreakoutStrategy() if chosen_strategy == "trend" else MeanReversionBollingerStrategy()
    )
    trade_data = ohlcv[ohlcv["symbol"].isin(symbols)].copy()
    params = load_frozen_params(chosen_strategy)
    generated = strategy.generate(trade_data, params)

    asof_ts = pd.to_datetime(trade_data["timestamp"].max(), utc=True)
    weights = compute_weights_from_signals(trade_data, generated.signals, position_cfg, asof_ts)
    weights = clamp_weights(weights, risk_cfg)
    print("Target weights:", weights)

    if not weights:
        print("当前无可执行目标仓位。")
        return

    latest_prices = (
        trade_data[trade_data["timestamp"] == asof_ts][["symbol", "close"]]
        .set_index("symbol")["close"]
        .to_dict()
    )

    account = trading_client.get_account()
    equity = float(account.equity)
    print(f"Account equity = {equity:.2f}")

    submit_bracket_orders(
        trading_client,
        weights,
        latest_prices,
        equity,
        risk_cfg,
        dry_run=args.dry_run,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Modular Quant Trading Project (train/test/walk-forward/deploy)"
    )
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    train_parser = subparsers.add_parser("train", help="Train on in-sample data and freeze parameters")
    train_parser.add_argument("--start", required=True)
    train_parser.add_argument("--end", required=True)
    train_parser.add_argument("--strategies", nargs="+", default=["trend", "mean_reversion", "pullback"])
    train_parser.add_argument("--objective", default="sharpe", choices=["sharpe", "cagr", "calmar"])
    train_parser.add_argument("--overwrite-frozen", action="store_true")
    train_parser.set_defaults(fn=cmd_train)

    test_parser = subparsers.add_parser("test", help="Run immutable out-of-sample testing")
    test_parser.add_argument("--start", required=True)
    test_parser.add_argument("--end", required=True)
    test_parser.add_argument("--strategies", nargs="+", default=["trend", "mean_reversion", "pullback"])
    test_parser.set_defaults(fn=cmd_test)

    wf_parser = subparsers.add_parser("walk-forward", help="Run walk-forward validation")
    wf_parser.add_argument("--start", required=True)
    wf_parser.add_argument("--end", required=True)
    wf_parser.add_argument("--strategies", nargs="+", default=["trend", "mean_reversion", "pullback"])
    wf_parser.add_argument("--train-years", type=int, default=3)
    wf_parser.add_argument("--test-months", type=int, default=6)
    wf_parser.add_argument("--step-months", type=int, default=3)
    wf_parser.add_argument("--gap-days", type=int, default=1)
    wf_parser.set_defaults(fn=cmd_walk_forward)

    deploy_parser = subparsers.add_parser("deploy", help="Deploy frozen strategy to Alpaca paper trading")
    deploy_parser.add_argument("--dry-run", action="store_true", help="Do not actually submit orders")
    deploy_parser.set_defaults(fn=cmd_deploy)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
