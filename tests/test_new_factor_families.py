import pandas as pd

from factors import build_factor_panel, get_factor_definitions


def _sample_ohlcv() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2023-01-01", periods=140, freq="D", tz="UTC")
    for symbol, offset in [("AAA", 0.0), ("BBB", 10.0)]:
        for i, ts in enumerate(dates):
            close = 100.0 + offset + i * 0.4 + ((i % 7) - 3) * 0.2
            open_ = close * (0.997 + 0.0005 * (i % 5))
            high = max(open_, close) * 1.01
            low = min(open_, close) * 0.99
            volume = 1_000_000 + i * 2_000 + (5_000 if symbol == "BBB" else 0)
            rows.append(
                {
                    "timestamp": ts,
                    "symbol": symbol,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
            )
    return pd.DataFrame(rows)


def test_new_factor_families_are_registered_and_built():
    panel = build_factor_panel(_sample_ohlcv())
    definitions = get_factor_definitions()

    expected = {
        "momentum_120_skip_5",
        "trend_consistency_20",
        "efficiency_ratio_20",
        "risk_adjusted_momentum_60",
        "overnight_gap_5",
        "intraday_strength_5",
        "intraday_strength_10",
        "intraday_hit_rate_10",
        "body_to_range_5",
        "overnight_gap_20",
        "channel_position_20",
        "channel_position_60",
        "amihud_illiquidity_20",
        "volume_dryup_10_60",
        "obv_trend_20",
        "dollar_volume_accel_20_60",
        "downside_risk_20",
        "downside_risk_60",
        "downside_to_total_vol_20",
        "range_expansion_5_20",
        "gap_volatility_20",
        "gap_volatility_60",
        "gap_downside_vol_20",
        "vol_of_range_20",
        "vol_of_range_60",
        "breakout_distance_60",
        "ma_distance_60",
        "ma_gap_20_60",
        "low_volatility_60",
        "vol_compression_5_20",
    }

    assert expected.issubset(definitions.keys())
    assert expected.issubset(panel.columns)
    latest = panel.dropna(subset=list(expected)).sort_values(["timestamp", "symbol"]).tail(2)
    assert len(latest) == 2
