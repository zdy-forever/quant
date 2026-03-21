import pandas as pd

from pipelines.run_alpha_combo_regime_switch import _build_mix_windows, _select_variant


def test_build_mix_windows_produces_normalized_mixtures():
    dates = pd.date_range("2024-01-01", periods=6, freq="D", tz="UTC")
    regime_frame = pd.DataFrame(
        {
            "timestamp": dates,
            "regime": [
                "trend_low_vol",
                "trend_low_vol",
                "range_low_vol",
                "range_low_vol",
                "trend_high_vol",
                "trend_high_vol",
            ],
        }
    )

    windows = _build_mix_windows(
        regime_frame,
        start="2024-01-01",
        end="2024-01-06",
        window_days=4,
        step_days=2,
        min_sample_days=3,
    )

    assert windows
    assert windows[0]["window_label"] == "2024-01-01__2024-01-04"
    assert abs(sum(windows[0]["mix"].values()) - 1.0) < 1e-9
    assert windows[0]["mix"]["trend_low_vol"] == 0.5
    assert windows[0]["mix"]["range_low_vol"] == 0.5


def test_select_variant_prefers_strategy_that_hits_cagr_floor():
    aggressive = {
        "oos_metrics": {
            "cagr": 0.18,
            "max_dd": -0.17,
            "sharpe": 0.9,
            "calmar": 1.05,
        }
    }
    conservative = {
        "oos_metrics": {
            "cagr": 0.11,
            "max_dd": -0.08,
            "sharpe": 0.8,
            "calmar": 1.10,
        }
    }

    selected = _select_variant(
        aggressive,
        conservative,
        max_drawdown_gap=0.05,
        target_cagr=0.15,
        target_max_dd=0.20,
    )

    assert selected["selected_variant"] == "aggressive"
