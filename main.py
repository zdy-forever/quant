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
import hashlib
import json
import os
from typing import TYPE_CHECKING, Any, Dict, List
from zoneinfo import ZoneInfo
import pandas as pd

if TYPE_CHECKING:
    from regime.detection import RegimeLabel
    from risk.management import RiskConfig

DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "GOOGL"]
NY_TZ = ZoneInfo("America/New_York")
FREE_PLAN_DELAY_MINUTES = 15
OHLCV_CACHE_DIR = os.path.join("artifacts", "cache", "ohlcv")
ALPACA_SYMBOL_CHUNK_SIZE = 50
DEFAULT_BAR_ADJUSTMENT = "all"


def get_research_adjustment(runtime: dict) -> str:
    data_cfg = runtime.get("data", {}) or {}
    return str(data_cfg.get("research_bar_adjustment", data_cfg.get("bar_adjustment", "all")))


def get_execution_adjustment(runtime: dict) -> str:
    data_cfg = runtime.get("data", {}) or {}
    return str(data_cfg.get("execution_bar_adjustment", "raw"))


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


def _chunk_symbols(symbols: List[str], chunk_size: int) -> List[List[str]]:
    return [symbols[idx : idx + chunk_size] for idx in range(0, len(symbols), chunk_size)]


def _ohlcv_cache_path(symbols: List[str], start: str, end: str, adjustment: str) -> str:
    normalized = sorted({symbol.upper() for symbol in symbols})
    key = "|".join([start, end, adjustment.lower(), ",".join(normalized)])
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    os.makedirs(OHLCV_CACHE_DIR, exist_ok=True)
    return os.path.join(OHLCV_CACHE_DIR, f"daily_{start}_{end}_{adjustment.lower()}_{digest}.csv")


def collect_reference_symbols(
    strategy_names: List[str] | None = None,
    use_frozen_params: bool = False,
) -> List[str]:
    """
    收集策略依赖的参考行情符号。

    这些符号只用于生成参考列，例如 VIX 代理，不会被当成可交易股票。
    """

    from backtest.optimizer import get_strategy_registry

    registry = get_strategy_registry()
    refs: set[str] = set()

    for strategy_name in strategy_names or []:
        params: Dict[str, Any] | None = None
        if use_frozen_params:
            try:
                params = load_frozen_params(strategy_name)
            except FileNotFoundError:
                params = None
        if params is None and strategy_name in registry:
            params = registry[strategy_name].default_params()
        if not params:
            continue

        vix_symbol = str(params.get("vix_symbol", "")).strip().upper()
        if vix_symbol:
            refs.add(vix_symbol)

    return sorted(refs)


def prepare_trade_ohlcv(
    full_ohlcv: pd.DataFrame,
    trade_symbols: List[str],
    reference_symbols: List[str] | None = None,
) -> pd.DataFrame:
    """
    把参考行情按日期合并回交易股票面板。

    例如会把 `VIXY` 的收盘价展开成 `ref_close_VIXY` 列，
    这样策略能读到它，但回测不会把它当成可交易股票。
    """

    df = full_ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    trade_set = {symbol.upper() for symbol in trade_symbols}
    result = df[df["symbol"].isin(trade_set)].copy()

    for ref_symbol in reference_symbols or []:
        ref_col = f"ref_close_{ref_symbol.upper()}"
        ref_frame = (
            df[df["symbol"] == ref_symbol.upper()][["timestamp", "close"]]
            .drop_duplicates(subset=["timestamp"])
            .rename(columns={"close": ref_col})
        )
        result = result.merge(ref_frame, on="timestamp", how="left")

    return result.sort_values(["timestamp", "symbol"]).reset_index(drop=True)


def _notify_research(command_name: str, payload: Dict[str, Any]) -> None:
    from notifications import send_research_notification

    try:
        sent = send_research_notification(command_name, payload)
        if not sent:
            print("[WARN] Email notification skipped because SMTP env vars are incomplete.")
    except Exception as exc:
        print(f"[WARN] Failed to send email notification for {command_name}: {exc}")


def _notify_deploy(payload: Dict[str, Any]) -> None:
    from notifications import send_deploy_notifications

    try:
        sent = send_deploy_notifications(payload)
        if not sent:
            print("[WARN] Email notification skipped because SMTP env vars are incomplete.")
    except Exception as exc:
        print(f"[WARN] Failed to send deploy emails: {exc}")


def _notify_failure(command_name: str, exc: Exception) -> None:
    from notifications import send_failure_notification

    try:
        sent = send_failure_notification(command_name, str(exc))
        if not sent:
            print("[WARN] Failure email skipped because SMTP env vars are incomplete.")
    except Exception as email_exc:
        print(f"[WARN] Failed to send failure email for {command_name}: {email_exc}")


def fetch_daily_ohlcv(
    data_client,
    symbols: List[str],
    start: str,
    end: str,
    adjustment: str = DEFAULT_BAR_ADJUSTMENT,
) -> pd.DataFrame:
    """
    抓取日线 OHLCV，并在本地做轻量缓存。

    这样做有两个目的：
    - 100+ 股票池时避免一次请求过大
    - `pipeline`/`train`/`test` 重复跑时尽量复用本地结果
    """

    from alpaca.data.enums import Adjustment
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    clean_symbols = sorted({symbol.upper() for symbol in symbols if str(symbol).strip()})
    if not clean_symbols:
        return pd.DataFrame(columns=["timestamp", "symbol", "open", "high", "low", "close", "volume"])

    adjustment_value = str(adjustment or DEFAULT_BAR_ADJUSTMENT).strip().lower()
    cache_path = _ohlcv_cache_path(clean_symbols, start, end, adjustment_value)
    if os.path.exists(cache_path):
        cached = pd.read_csv(cache_path)
        cached["timestamp"] = pd.to_datetime(cached["timestamp"], utc=True)
        cached["symbol"] = cached["symbol"].astype(str)
        return cached[["timestamp", "symbol", "open", "high", "low", "close", "volume"]].sort_values(
            ["timestamp", "symbol"]
        )

    all_frames: List[pd.DataFrame] = []
    for chunk in _chunk_symbols(clean_symbols, ALPACA_SYMBOL_CHUNK_SIZE):
        request_kwargs = {
            "symbol_or_symbols": chunk,
            "timeframe": TimeFrame.Day,
            "start": pd.Timestamp(start, tz="UTC"),
            "end": pd.Timestamp(end, tz="UTC"),
            "adjustment": Adjustment(adjustment_value),
        }
        request = StockBarsRequest(**request_kwargs)
        bars = data_client.get_stock_bars(request).df
        if bars is None or bars.empty:
            continue

        df = bars.reset_index()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df["symbol"] = df["symbol"].astype(str)
        all_frames.append(df[["timestamp", "symbol", "open", "high", "low", "close", "volume"]])

    if not all_frames:
        return pd.DataFrame(columns=["timestamp", "symbol", "open", "high", "low", "close", "volume"])

    result = (
        pd.concat(all_frames, ignore_index=True)
        .drop_duplicates(subset=["timestamp", "symbol"], keep="last")
        .sort_values(["timestamp", "symbol"])
        .reset_index(drop=True)
    )
    result.to_csv(cache_path, index=False)
    return result


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


def submit_bracket_orders(
    trading_client,
    weights: Dict[str, float],
    latest_prices: Dict[str, float],
    equity: float,
    risk_cfg: RiskConfig,
    dry_run: bool = True,
) -> List[Dict[str, Any]]:
    import numpy as np

    from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest

    actions: List[Dict[str, Any]] = []
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

        action = {
            "symbol": symbol,
            "side": "BUY",
            "qty": qty,
            "reference_price": price,
            "stop_loss": stop_price,
            "take_profit": take_profit,
            "weight": float(weight),
            "mode": "paper_dry_run" if dry_run else "paper_submitted",
        }

        if dry_run:
            print(
                f"[DRY_RUN] submit {symbol} qty={qty} "
                f"px~{price:.2f} SL={stop_price} TP={take_profit}"
            )
        else:
            response = trading_client.submit_order(order_data=order)
            print(f"SUBMITTED {symbol}: {getattr(response, 'id', '-')}")
            action["order_id"] = getattr(response, "id", "")
        actions.append(action)

    return actions


def combine_stock_weights(
    strategy_stock_weights: Dict[str, Dict[str, float]],
    strategy_allocations: Dict[str, float],
) -> Dict[str, float]:
    """
    把多个策略的股票权重按策略层资金配比合成一个组合。
    """

    combined: Dict[str, float] = {}
    for strategy_name, stock_weights in strategy_stock_weights.items():
        strategy_weight = float(strategy_allocations.get(strategy_name, 0.0))
        if strategy_weight <= 0:
            continue
        for symbol, weight in stock_weights.items():
            combined[symbol] = combined.get(symbol, 0.0) + strategy_weight * float(weight)
    return combined


def cmd_train(args: argparse.Namespace) -> None:
    from backtest.train import TrainSpec, train
    from backtest.engine import BacktestConfig

    runtime = load_runtime_config()
    data_client, _ = get_alpaca_clients()
    symbols = load_symbols()
    reference_symbols = collect_reference_symbols(args.strategies, use_frozen_params=False)
    full_ohlcv = fetch_daily_ohlcv(
        data_client,
        sorted(set(symbols + reference_symbols)),
        args.start,
        args.end,
        adjustment=get_research_adjustment(runtime),
    )
    ohlcv = prepare_trade_ohlcv(full_ohlcv, symbols, reference_symbols)
    backtest_cfg = BacktestConfig(**(runtime.get("backtest", {}) or {}))

    spec = TrainSpec(
        symbols=symbols,
        start=args.start,
        end=args.end,
        objective=args.objective,
        overwrite_frozen=args.overwrite_frozen,
        backtest=backtest_cfg,
    )
    result = train(ohlcv, spec, strategies=args.strategies)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    _notify_research("train", result)


def cmd_test(args: argparse.Namespace) -> None:
    from backtest.engine import BacktestConfig
    from backtest.test import TestSpec, run_oos_test

    runtime = load_runtime_config()
    data_client, _ = get_alpaca_clients()
    symbols = load_symbols()
    reference_symbols = collect_reference_symbols(args.strategies, use_frozen_params=True)
    full_ohlcv = fetch_daily_ohlcv(
        data_client,
        sorted(set(symbols + reference_symbols)),
        args.start,
        args.end,
        adjustment=get_research_adjustment(runtime),
    )
    ohlcv = prepare_trade_ohlcv(full_ohlcv, symbols, reference_symbols)
    backtest_cfg = BacktestConfig(**(runtime.get("backtest", {}) or {}))

    spec = TestSpec(
        symbols=symbols,
        start=args.start,
        end=args.end,
        strategies=args.strategies,
        backtest=backtest_cfg,
    )
    result = run_oos_test(ohlcv, spec)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    _notify_research("test", result)


def cmd_walk_forward(args: argparse.Namespace) -> None:
    from backtest.engine import BacktestConfig
    from backtest.walk_forward import WalkForwardSpec, run_walk_forward

    runtime = load_runtime_config()
    data_client, _ = get_alpaca_clients()
    symbols = load_symbols()
    reference_symbols = collect_reference_symbols(args.strategies, use_frozen_params=True)
    full_ohlcv = fetch_daily_ohlcv(
        data_client,
        sorted(set(symbols + reference_symbols)),
        args.start,
        args.end,
        adjustment=get_research_adjustment(runtime),
    )
    ohlcv = prepare_trade_ohlcv(full_ohlcv, symbols, reference_symbols)
    backtest_cfg = BacktestConfig(**(runtime.get("backtest", {}) or {}))

    spec = WalkForwardSpec(
        symbols=symbols,
        start=args.start,
        end=args.end,
        strategies=args.strategies,
        train_years=args.train_years,
        test_months=args.test_months,
        step_months=args.step_months,
        gap_days=args.gap_days,
        backtest=backtest_cfg,
    )
    result = run_walk_forward(ohlcv, spec)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    _notify_research("walk-forward", result)


def cmd_optimize(args: argparse.Namespace) -> None:
    from backtest.engine import BacktestConfig
    from backtest.optimizer import OptimizationSpec, optimize_strategies

    runtime = load_runtime_config()
    data_client, _ = get_alpaca_clients()
    symbols = load_symbols()
    reference_symbols = collect_reference_symbols(args.strategies, use_frozen_params=False)
    full_ohlcv = fetch_daily_ohlcv(
        data_client,
        sorted(set(symbols + reference_symbols)),
        args.start,
        args.end,
        adjustment=get_research_adjustment(runtime),
    )
    ohlcv = prepare_trade_ohlcv(full_ohlcv, symbols, reference_symbols)

    backtest_cfg = BacktestConfig(**(runtime.get("backtest", {}) or {}))
    opt_cfg = runtime.get("optimizer", {}) or {}
    spec = OptimizationSpec(
        start=args.start,
        end=args.end,
        objective=args.objective,
        min_trade_count=int(opt_cfg.get("min_trade_count", 8)),
        min_avg_active_positions=float(opt_cfg.get("min_avg_active_positions", 1.0)),
        max_avg_turnover=float(opt_cfg.get("max_avg_turnover", 1.5)),
        backtest=backtest_cfg,
    )
    result = optimize_strategies(ohlcv, args.strategies, spec)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    _notify_research("optimize", result)


def cmd_alpha_research(args: argparse.Namespace) -> None:
    from alpha_lab.research import AlphaResearchConfig, run_alpha_research
    from backtest.engine import BacktestConfig

    runtime = load_runtime_config()
    data_client, _ = get_alpaca_clients()
    symbols = load_symbols()
    ohlcv = fetch_daily_ohlcv(
        data_client,
        symbols,
        args.start,
        args.end,
        adjustment=get_research_adjustment(runtime),
    )

    alpha_cfg = runtime.get("alpha_lab", {}) or {}
    backtest_cfg = BacktestConfig(**(runtime.get("backtest", {}) or {}))
    research_cfg = AlphaResearchConfig(
        forward_days=list(alpha_cfg.get("forward_days", [1, 5, 10, 20])),
        quantiles=int(alpha_cfg.get("quantiles", 5)),
        top_n=int(alpha_cfg.get("top_n", 10)),
        min_ic=float(alpha_cfg.get("min_ic", 0.02)),
        min_rank_ic=float(alpha_cfg.get("min_rank_ic", 0.03)),
        backtest=backtest_cfg,
    )
    result = run_alpha_research(ohlcv, research_cfg)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    _notify_research("alpha-research", result)


def cmd_pipeline(args: argparse.Namespace) -> None:
    from alpha_lab.research import AlphaResearchConfig
    from backtest.engine import BacktestConfig
    from backtest.pipeline import PipelineSpec, run_pipeline

    runtime = load_runtime_config()
    data_client, _ = get_alpaca_clients()
    symbols = load_symbols()

    backtest_cfg = BacktestConfig(**(runtime.get("backtest", {}) or {}))
    optimizer_cfg = runtime.get("optimizer", {}) or {}
    alpha_cfg = runtime.get("alpha_lab", {}) or {}
    research_cfg = AlphaResearchConfig(
        forward_days=list(alpha_cfg.get("forward_days", [1, 5, 10, 20])),
        quantiles=int(alpha_cfg.get("quantiles", 5)),
        top_n=int(alpha_cfg.get("top_n", 10)),
        min_ic=float(alpha_cfg.get("min_ic", 0.02)),
        min_rank_ic=float(alpha_cfg.get("min_rank_ic", 0.03)),
        backtest=backtest_cfg,
    )

    fetch_start = min(args.optimize_start, args.test_start, args.walk_forward_start)
    fetch_end = max(args.optimize_end, args.test_end, args.walk_forward_end)
    reference_symbols = collect_reference_symbols(args.candidate_strategies, use_frozen_params=False)
    full_ohlcv = fetch_daily_ohlcv(
        data_client,
        sorted(set(symbols + reference_symbols)),
        fetch_start,
        fetch_end,
        adjustment=get_research_adjustment(runtime),
    )
    ohlcv = prepare_trade_ohlcv(full_ohlcv, symbols, reference_symbols)

    spec = PipelineSpec(
        symbols=symbols,
        optimize_start=args.optimize_start,
        optimize_end=args.optimize_end,
        test_start=args.test_start,
        test_end=args.test_end,
        walk_forward_start=args.walk_forward_start,
        walk_forward_end=args.walk_forward_end,
        objective=args.objective,
        candidate_strategies=args.candidate_strategies,
        max_strategies_to_optimize=args.max_strategies,
        overwrite_frozen=args.overwrite_frozen,
        walk_forward_train_years=args.train_years,
        walk_forward_test_months=args.test_months,
        walk_forward_step_months=args.step_months,
        walk_forward_gap_days=args.gap_days,
    )
    result = run_pipeline(ohlcv, spec, backtest_cfg, optimizer_cfg, research_cfg)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    _notify_research("pipeline", result)


def cmd_deploy(args: argparse.Namespace) -> None:
    import pandas as pd

    from portfolio.position_sizing import PositionConfig, compute_weights_from_signals
    from portfolio.strategy_blend import StrategyBlendConfig, compute_strategy_allocations
    from backtest.optimizer import get_strategy_registry
    from regime.detection import RegimeConfig, RegimeLabel, detect_regime, estimate_regime_mixture
    from risk.management import RiskConfig, clamp_weights

    runtime = load_runtime_config()
    regime_cfg = RegimeConfig(**(runtime.get("regime", {}) or {}))
    position_cfg = PositionConfig(**(runtime.get("position", {}) or {}))
    risk_cfg = RiskConfig(**(runtime.get("risk", {}) or {}))
    blend_cfg = StrategyBlendConfig(**(runtime.get("strategy_mix", {}) or {}))

    data_client, trading_client = get_alpaca_clients()
    symbols = load_symbols()

    end = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    start = (pd.Timestamp.utcnow() - pd.Timedelta(days=800)).strftime("%Y-%m-%d")
    registry = get_strategy_registry()
    available_strategies = [name for name in registry if os.path.exists(os.path.join("artifacts", "frozen_params", f"{name}.json"))]
    reference_symbols = collect_reference_symbols(available_strategies, use_frozen_params=True)
    fetch_symbols = sorted(set(symbols + reference_symbols + [regime_cfg.symbol_for_regime]))
    full_ohlcv = fetch_daily_ohlcv(
        data_client,
        fetch_symbols,
        start,
        end,
        adjustment=get_research_adjustment(runtime),
    )
    full_ohlcv = drop_unconfirmed_daily_bar_for_free_plan(full_ohlcv)
    if full_ohlcv.empty:
        raise RuntimeError("未获取到任何行情数据。")

    regime = detect_regime(full_ohlcv, regime_cfg)
    regime_mix = estimate_regime_mixture(full_ohlcv, regime_cfg)
    print(f"Regime = {regime}")
    print("Regime mix:", regime_mix)

    deploy_summary: Dict[str, Any] = {
        "regime": str(regime),
        "regime_mix": regime_mix,
        "strategy_allocations": {},
        "target_weights": {},
        "paper_actions": [],
        "manual_actions": [],
        "dry_run": bool(args.dry_run),
    }

    if regime == RegimeLabel.RANGE_HIGH_VOL and regime_cfg.no_trade_in_range_high_vol:
        print("Regime=RANGE_HIGH_VOL，按配置不交易。")
        _notify_deploy(deploy_summary)
        return

    trade_data = prepare_trade_ohlcv(full_ohlcv, symbols, reference_symbols)
    asof_ts = pd.to_datetime(trade_data["timestamp"].max(), utc=True)
    strategy_allocations = compute_strategy_allocations(regime_mix, available_strategies, blend_cfg)
    deploy_summary["strategy_allocations"] = strategy_allocations
    if not strategy_allocations:
        print("当前没有可用的策略层资金分配。")
        _notify_deploy(deploy_summary)
        return

    strategy_stock_weights: Dict[str, Dict[str, float]] = {}
    for strategy_name, strategy_weight in strategy_allocations.items():
        if strategy_weight <= 0:
            continue
        params = load_frozen_params(strategy_name)
        generated = registry[strategy_name].generate(trade_data, params)
        strategy_stock_weights[strategy_name] = compute_weights_from_signals(
            trade_data,
            generated.signals,
            position_cfg,
            asof_ts,
        )

    weights = combine_stock_weights(strategy_stock_weights, strategy_allocations)
    weights = clamp_weights(weights, risk_cfg)
    print("Strategy allocations:", strategy_allocations)
    print("Target weights:", weights)
    deploy_summary["target_weights"] = weights

    if not weights:
        print("当前无可执行目标仓位。")
        _notify_deploy(deploy_summary)
        return

    execution_fetch_start = (pd.Timestamp.utcnow() - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    raw_trade_ohlcv = fetch_daily_ohlcv(
        data_client,
        symbols,
        execution_fetch_start,
        end,
        adjustment=get_execution_adjustment(runtime),
    )
    raw_trade_ohlcv = drop_unconfirmed_daily_bar_for_free_plan(raw_trade_ohlcv)
    if raw_trade_ohlcv.empty:
        raise RuntimeError("未获取到用于执行定价的 raw 数据。")

    raw_asof_ts = pd.to_datetime(raw_trade_ohlcv["timestamp"].max(), utc=True)
    latest_prices = (
        raw_trade_ohlcv[raw_trade_ohlcv["timestamp"] == raw_asof_ts][["symbol", "close"]]
        .set_index("symbol")["close"]
        .to_dict()
    )
    deploy_summary["execution_reference_date"] = str(raw_asof_ts)
    deploy_summary["execution_price_adjustment"] = get_execution_adjustment(runtime)

    account = trading_client.get_account()
    equity = float(account.equity)
    print(f"Account equity = {equity:.2f}")

    actions = submit_bracket_orders(
        trading_client,
        weights,
        latest_prices,
        equity,
        risk_cfg,
        dry_run=args.dry_run,
    )
    deploy_summary["paper_actions"] = actions
    deploy_summary["manual_actions"] = actions
    _notify_deploy(deploy_summary)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Modular Quant Trading Project (train/optimize/test/walk-forward/alpha-research/pipeline/deploy)"
    )
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    train_parser = subparsers.add_parser("train", help="Train on in-sample data and freeze parameters")
    train_parser.add_argument("--start", required=True)
    train_parser.add_argument("--end", required=True)
    train_parser.add_argument("--strategies", nargs="+", default=["trend", "turtle", "pullback", "low_vol_momentum", "mean_reversion"])
    train_parser.add_argument("--objective", default="sharpe", choices=["sharpe", "cagr", "calmar"])
    train_parser.add_argument("--overwrite-frozen", action="store_true")
    train_parser.set_defaults(fn=cmd_train)

    optimize_parser = subparsers.add_parser("optimize", help="Search for the best strategy parameters")
    optimize_parser.add_argument("--start", required=True)
    optimize_parser.add_argument("--end", required=True)
    optimize_parser.add_argument("--strategies", nargs="+", default=["trend", "turtle", "pullback", "low_vol_momentum", "mean_reversion"])
    optimize_parser.add_argument("--objective", default="sharpe", choices=["sharpe", "cagr", "calmar"])
    optimize_parser.set_defaults(fn=cmd_optimize)

    test_parser = subparsers.add_parser("test", help="Run immutable out-of-sample testing")
    test_parser.add_argument("--start", required=True)
    test_parser.add_argument("--end", required=True)
    test_parser.add_argument("--strategies", nargs="+", default=["trend", "turtle", "pullback", "low_vol_momentum", "mean_reversion"])
    test_parser.set_defaults(fn=cmd_test)

    wf_parser = subparsers.add_parser("walk-forward", help="Run walk-forward validation")
    wf_parser.add_argument("--start", required=True)
    wf_parser.add_argument("--end", required=True)
    wf_parser.add_argument("--strategies", nargs="+", default=["trend", "turtle", "pullback", "low_vol_momentum", "mean_reversion"])
    wf_parser.add_argument("--train-years", type=int, default=3)
    wf_parser.add_argument("--test-months", type=int, default=6)
    wf_parser.add_argument("--step-months", type=int, default=3)
    wf_parser.add_argument("--gap-days", type=int, default=1)
    wf_parser.set_defaults(fn=cmd_walk_forward)

    alpha_parser = subparsers.add_parser("alpha-research", help="Run IC/rank-IC/decay/quantile/composite factor research")
    alpha_parser.add_argument("--start", required=True)
    alpha_parser.add_argument("--end", required=True)
    alpha_parser.set_defaults(fn=cmd_alpha_research)

    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help="Run baseline screening, optimize, freeze, OOS, walk-forward and alpha research in one pass",
    )
    pipeline_parser.add_argument("--optimize-start", required=True)
    pipeline_parser.add_argument("--optimize-end", required=True)
    pipeline_parser.add_argument("--test-start", required=True)
    pipeline_parser.add_argument("--test-end", required=True)
    pipeline_parser.add_argument("--walk-forward-start", required=True)
    pipeline_parser.add_argument("--walk-forward-end", required=True)
    pipeline_parser.add_argument(
        "--candidate-strategies",
        nargs="+",
        default=["trend", "turtle", "pullback", "low_vol_momentum", "mean_reversion"],
    )
    pipeline_parser.add_argument("--objective", default="calmar", choices=["sharpe", "cagr", "calmar"])
    pipeline_parser.add_argument("--max-strategies", type=int, default=3)
    pipeline_parser.add_argument("--train-years", type=int, default=3)
    pipeline_parser.add_argument("--test-months", type=int, default=6)
    pipeline_parser.add_argument("--step-months", type=int, default=3)
    pipeline_parser.add_argument("--gap-days", type=int, default=1)
    pipeline_parser.add_argument("--overwrite-frozen", dest="overwrite_frozen", action="store_true")
    pipeline_parser.add_argument("--no-overwrite-frozen", dest="overwrite_frozen", action="store_false")
    pipeline_parser.set_defaults(fn=cmd_pipeline, overwrite_frozen=True)

    deploy_parser = subparsers.add_parser("deploy", help="Deploy frozen strategy to Alpaca paper trading")
    deploy_parser.add_argument("--dry-run", action="store_true", help="Do not actually submit orders")
    deploy_parser.set_defaults(fn=cmd_deploy)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.fn(args)
    except Exception as exc:
        command_name = getattr(args, "cmd", "unknown")
        _notify_failure(command_name, exc)
        raise


if __name__ == "__main__":
    main()
