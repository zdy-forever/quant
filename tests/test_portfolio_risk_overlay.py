import pandas as pd

from backtest.engine import BacktestConfig, run_weight_backtest


def _sample_ohlcv(closes: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(closes), tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": list(dates),
            "symbol": ["AAA"] * len(closes),
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [100_000] * len(closes),
        }
    )


def _target_weights(ohlcv: pd.DataFrame, weight: float = 1.0) -> pd.DataFrame:
    dates = pd.Index(pd.to_datetime(ohlcv["timestamp"], utc=True).drop_duplicates().sort_values())
    return pd.DataFrame({"AAA": [weight] * len(dates)}, index=dates)


def test_soft_drawdown_limit_deleverages_portfolio():
    ohlcv = _sample_ohlcv([100.0, 100.0, 90.0, 90.0, 90.0])
    result = run_weight_backtest(
        ohlcv,
        _target_weights(ohlcv),
        BacktestConfig(
            gross_exposure=1.0,
            stop_loss_pct=1.0,
            take_profit_pct=10.0,
            trailing_stop_atr_multiple=100.0,
            max_holding_days=999,
            portfolio_soft_dd_limit=0.05,
            portfolio_deleverage_ratio=0.5,
        ),
    )

    executed = result["executed_weights"]
    assert executed.loc[pd.Timestamp("2024-01-03", tz="UTC"), "AAA"] == 0.5
    assert result["risk_overlay"]["soft_deleverage_days"] >= 1.0


def test_hard_drawdown_limit_kills_and_cools_down():
    ohlcv = _sample_ohlcv([100.0, 100.0, 90.0, 95.0, 96.0, 97.0])
    result = run_weight_backtest(
        ohlcv,
        _target_weights(ohlcv),
        BacktestConfig(
            gross_exposure=1.0,
            stop_loss_pct=1.0,
            take_profit_pct=10.0,
            trailing_stop_atr_multiple=100.0,
            max_holding_days=999,
            portfolio_hard_dd_limit=0.08,
            portfolio_kill_cooldown_days=2,
        ),
    )

    executed = result["executed_weights"]
    assert executed.loc[pd.Timestamp("2024-01-03", tz="UTC"), "AAA"] == 0.0
    assert executed.loc[pd.Timestamp("2024-01-04", tz="UTC"), "AAA"] == 0.0
    assert executed.loc[pd.Timestamp("2024-01-05", tz="UTC"), "AAA"] == 0.0
    assert result["risk_overlay"]["hard_kill_count"] >= 1.0
    assert result["risk_overlay"]["cooldown_days_applied"] >= 2.0


def test_entry_turnover_cap_scales_new_buys_without_blocking_exits():
    dates = pd.date_range("2024-01-01", periods=3, tz="UTC")
    ohlcv = pd.DataFrame(
        {
            "timestamp": list(dates) * 2,
            "symbol": ["AAA"] * 3 + ["BBB"] * 3,
            "open": [100.0] * 6,
            "high": [100.0] * 6,
            "low": [100.0] * 6,
            "close": [100.0] * 6,
            "volume": [100_000] * 6,
        }
    )
    target_weights = pd.DataFrame(
        {
            "AAA": [0.0, 0.5, 0.0],
            "BBB": [0.0, 0.5, 0.0],
        },
        index=dates,
    )

    result = run_weight_backtest(
        ohlcv,
        target_weights,
        BacktestConfig(
            gross_exposure=1.0,
            stop_loss_pct=1.0,
            take_profit_pct=10.0,
            trailing_stop_atr_multiple=100.0,
            max_holding_days=999,
            max_entry_turnover_per_rebalance=0.25,
        ),
    )

    executed = result["executed_weights"]
    assert abs(executed.loc[pd.Timestamp("2024-01-02", tz="UTC"), "AAA"] - 0.125) < 1e-9
    assert abs(executed.loc[pd.Timestamp("2024-01-02", tz="UTC"), "BBB"] - 0.125) < 1e-9
    assert executed.loc[pd.Timestamp("2024-01-03", tz="UTC"), "AAA"] == 0.0
    assert executed.loc[pd.Timestamp("2024-01-03", tz="UTC"), "BBB"] == 0.0


def test_take_profit_nonpositive_disables_fixed_profit_cap():
    ohlcv = _sample_ohlcv([100.0, 106.0, 110.0, 112.0])
    result = run_weight_backtest(
        ohlcv,
        _target_weights(ohlcv),
        BacktestConfig(
            gross_exposure=1.0,
            stop_loss_pct=1.0,
            take_profit_pct=0.0,
            trailing_stop_atr_multiple=0.0,
            max_holding_days=999,
        ),
    )

    executed = result["executed_weights"]
    assert executed.loc[pd.Timestamp("2024-01-02", tz="UTC"), "AAA"] == 1.0
    assert executed.loc[pd.Timestamp("2024-01-03", tz="UTC"), "AAA"] == 1.0
    assert executed.loc[pd.Timestamp("2024-01-04", tz="UTC"), "AAA"] == 1.0
