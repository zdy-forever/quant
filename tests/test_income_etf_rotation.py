import pandas as pd

from pipelines.run_income_etf_rotation import (
    _build_income_rotation_panel,
    _build_validation_windows,
    _profile_library,
    _summarize_validation,
)


def test_build_income_rotation_panel_extracts_positive_dividend_carry():
    dates = pd.date_range("2024-01-01", periods=90, freq="D", tz="UTC")
    rows_all = []
    rows_raw = []
    for idx, timestamp in enumerate(dates):
        rows_all.append(
            {
                "timestamp": timestamp,
                "symbol": "AAA",
                "open": 100.0 + idx,
                "high": 101.0 + idx,
                "low": 99.0 + idx,
                "close": 100.0 + idx,
                "volume": 1_000_000,
            }
        )
        rows_raw.append(
            {
                "timestamp": timestamp,
                "symbol": "AAA",
                "open": 100.0 + idx * 0.7,
                "high": 101.0 + idx * 0.7,
                "low": 99.0 + idx * 0.7,
                "close": 100.0 + idx * 0.7,
                "volume": 1_000_000,
            }
        )
        rows_all.append(
            {
                "timestamp": timestamp,
                "symbol": "BBB",
                "open": 100.0 + idx * 0.5,
                "high": 101.0 + idx * 0.5,
                "low": 99.0 + idx * 0.5,
                "close": 100.0 + idx * 0.5,
                "volume": 1_000_000,
            }
        )
        rows_raw.append(
            {
                "timestamp": timestamp,
                "symbol": "BBB",
                "open": 100.0 + idx * 0.5,
                "high": 101.0 + idx * 0.5,
                "low": 99.0 + idx * 0.5,
                "close": 100.0 + idx * 0.5,
                "volume": 1_000_000,
            }
        )

    panel, dividend_summary = _build_income_rotation_panel(
        pd.DataFrame(rows_all),
        pd.DataFrame(rows_raw),
        ["AAA", "BBB"],
    )

    assert not panel.empty
    assert "dividend_carry_10" in panel.columns
    assert "relative_strength_42" in panel.columns
    assert dividend_summary["AAA"]["dividend_carry"] > 0.0
    assert abs(dividend_summary["BBB"]["dividend_carry"]) < 1e-9


def test_profile_library_keeps_price_only_and_dividend_aware_profiles():
    profiles = _profile_library()

    assert any(not row["uses_dividends"] for row in profiles)
    assert any(row["uses_dividends"] for row in profiles)


def test_validation_helpers_build_windows_and_summary():
    panel = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=45, freq="D", tz="UTC").repeat(2),
            "symbol": ["AAA", "BBB"] * 45,
        }
    )

    windows = _build_validation_windows(panel, "2024-01-01", "2024-02-14", 10)
    summary = _summarize_validation(
        [
            {"cagr": 0.10, "sharpe": 1.0, "max_dd": -0.05},
            {"cagr": -0.02, "sharpe": 0.2, "max_dd": -0.03},
        ]
    )

    assert windows
    assert summary["window_count"] == 2
    assert abs(summary["avg_cagr"] - 0.04) < 1e-9


def test_income_rotation_panel_keeps_early_history_when_one_symbol_lists_late():
    dates = pd.date_range("2024-01-01", periods=70, freq="D", tz="UTC")
    rows_all = []
    rows_raw = []
    for idx, timestamp in enumerate(dates):
        for symbol, multiplier in [("AAA", 1.0), ("BBB", 0.8)]:
            rows_all.append(
                {
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "open": 100.0 + idx * multiplier,
                    "high": 101.0 + idx * multiplier,
                    "low": 99.0 + idx * multiplier,
                    "close": 100.0 + idx * multiplier,
                    "volume": 1_000_000,
                }
            )
            rows_raw.append(
                {
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "open": 100.0 + idx * multiplier,
                    "high": 101.0 + idx * multiplier,
                    "low": 99.0 + idx * multiplier,
                    "close": 100.0 + idx * multiplier,
                    "volume": 1_000_000,
                }
            )
        if idx >= 35:
            rows_all.append(
                {
                    "timestamp": timestamp,
                    "symbol": "CCC",
                    "open": 100.0 + idx * 0.6,
                    "high": 101.0 + idx * 0.6,
                    "low": 99.0 + idx * 0.6,
                    "close": 100.0 + idx * 0.6,
                    "volume": 1_000_000,
                }
            )
            rows_raw.append(
                {
                    "timestamp": timestamp,
                    "symbol": "CCC",
                    "open": 100.0 + idx * 0.6,
                    "high": 101.0 + idx * 0.6,
                    "low": 99.0 + idx * 0.6,
                    "close": 100.0 + idx * 0.6,
                    "volume": 1_000_000,
                }
            )

    panel, _ = _build_income_rotation_panel(
        pd.DataFrame(rows_all),
        pd.DataFrame(rows_raw),
        ["AAA", "BBB", "CCC"],
    )

    assert not panel.empty
    assert panel["timestamp"].min() < pd.Timestamp("2024-02-15", tz="UTC")
