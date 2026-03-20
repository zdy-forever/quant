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
