import pandas as pd

from backtest.engine import BacktestConfig
from pipelines.run_alpha_combo_regime_switch import (
    AlphaComboRegimeSwitchSpec,
    _build_execution_overrides_grid,
    _build_top_n_grid,
    _build_mix_windows,
    _build_trade_filter_profiles,
    _select_mix_neighbors,
    _select_engine_for_factors,
    _select_variant,
    _weighted_numeric_dict,
)


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


def test_select_engine_for_factors_falls_back_when_subset_is_missing_required_columns():
    primary_engine = {"factor_names": ["gap_volatility_20", "intraday_strength_10"]}
    fallback_engine = {"factor_names": ["gap_volatility_20", "intraday_strength_10", "reversal_5"]}

    selected = _select_engine_for_factors(primary_engine, fallback_engine, ["gap_volatility_20", "reversal_5"])

    assert selected is fallback_engine


def test_build_execution_overrides_grid_keeps_small_interpretable_default_profiles():
    spec = AlphaComboRegimeSwitchSpec(
        train_start="2020-01-01",
        train_end="2021-12-31",
        oos_start="2022-01-01",
        oos_end="2022-12-31",
        rebalance_every_n_days=1,
    )
    cfg = BacktestConfig(max_holding_days=3)

    rows = _build_execution_overrides_grid(spec, cfg)

    assert {} in rows
    assert {"rebalance_every_n_days": 2} in rows
    assert {
        "min_score_threshold": 0.0,
        "hold_rank_buffer": 1,
        "score_hysteresis": 0.05,
    } in rows
    assert {
        "min_score_threshold": 0.0,
        "rank_weight_power": 1.0,
        "hold_rank_buffer": 1,
        "score_hysteresis": 0.05,
    } in rows
    assert {
        "min_score_threshold": 0.0,
        "hold_rank_buffer": 1,
        "score_hysteresis": 0.05,
        "max_entry_turnover_per_rebalance": 0.35,
    } in rows
    assert {
        "dynamic_breadth_score_threshold": 0.25,
        "min_dynamic_positions": 0,
    } in rows
    assert {
        "max_holding_days": 5,
    } in rows
    assert {
        "rank_weight_power": 1.5,
        "max_holding_days": 5,
        "stop_loss_pct": 0.08,
        "take_profit_pct": 0.25,
        "trailing_stop_atr_multiple": 3.0,
    } in rows
    assert {
        "min_score_threshold": 0.0,
        "rank_weight_power": 2.0,
        "dynamic_breadth_score_threshold": 0.25,
        "min_dynamic_positions": 0,
        "stop_loss_pct": 0.08,
        "take_profit_pct": 0.25,
        "trailing_stop_atr_multiple": 3.0,
        "max_holding_days": 7,
    } in rows
    assert {
        "min_score_threshold": 0.0,
        "rank_weight_power": 2.0,
        "dynamic_breadth_score_threshold": 0.25,
        "min_dynamic_positions": 0,
        "stop_loss_pct": 0.08,
        "take_profit_pct": 0.0,
        "trailing_stop_atr_multiple": 3.0,
        "max_holding_days": 10,
    } in rows
    assert len(rows) == 20


def test_build_execution_overrides_grid_respects_explicit_search_space():
    spec = AlphaComboRegimeSwitchSpec(
        train_start="2020-01-01",
        train_end="2021-12-31",
        oos_start="2022-01-01",
        oos_end="2022-12-31",
        rebalance_every_n_days=1,
        rebalance_every_n_days_grid=[1, 3],
        min_score_threshold_grid=[-0.5, 0.0],
        rank_weight_power_grid=[0.0],
        hold_rank_buffer_grid=[0, 1],
        score_hysteresis_grid=[0.0],
        max_holding_days_grid=[3],
        max_entry_turnover_per_rebalance_grid=[0.0, 0.35],
        dynamic_breadth_score_threshold_grid=[-999.0, 0.25],
        min_dynamic_positions_grid=[0],
    )
    cfg = BacktestConfig(max_holding_days=3)

    rows = _build_execution_overrides_grid(spec, cfg)

    assert len(rows) == 32
    assert {
        "rebalance_every_n_days": 3,
        "min_score_threshold": 0.0,
        "rank_weight_power": 0.0,
        "hold_rank_buffer": 1,
        "score_hysteresis": 0.0,
        "max_holding_days": 3,
        "stop_loss_pct": 0.08,
        "take_profit_pct": 0.25,
        "trailing_stop_atr_multiple": 3.0,
        "max_entry_turnover_per_rebalance": 0.35,
        "dynamic_breadth_score_threshold": 0.25,
        "min_dynamic_positions": 0,
    } in rows


def test_build_trade_filter_profiles_keeps_small_default_profile_set():
    spec = AlphaComboRegimeSwitchSpec(
        train_start="2020-01-01",
        train_end="2021-12-31",
        oos_start="2022-01-01",
        oos_end="2022-12-31",
    )

    rows = _build_trade_filter_profiles(spec, {"min_close_location_1": 0.05, "max_true_range_pct_1": 0.09, "max_volume_surprise_5": 4.0, "max_abs_ma_distance_20": 0.15, "min_liquidity_20": 16.0})

    assert len(rows) == 4
    assert {
        "min_close_location_1": 0.05,
        "max_true_range_pct_1": 0.09,
        "max_volume_surprise_5": 4.0,
        "max_abs_ma_distance_20": 0.15,
        "min_liquidity_20": 16.0,
    } in rows
    assert {
        "min_close_location_1": 0.1,
        "max_true_range_pct_1": 0.09,
        "max_volume_surprise_5": 3.0,
        "max_abs_ma_distance_20": 0.15,
        "min_liquidity_20": 16.0,
    } in rows


def test_build_trade_filter_profiles_respects_explicit_grid():
    spec = AlphaComboRegimeSwitchSpec(
        train_start="2020-01-01",
        train_end="2021-12-31",
        oos_start="2022-01-01",
        oos_end="2022-12-31",
        min_close_location_1_grid=[0.05, 0.1],
        max_true_range_pct_1_grid=[0.08],
        max_volume_surprise_5_grid=[3.0],
        max_abs_ma_distance_20_grid=[0.12],
        min_liquidity_20_grid=[16.0, 18.0],
    )

    rows = _build_trade_filter_profiles(spec, None)

    assert len(rows) == 4
    assert {
        "min_close_location_1": 0.1,
        "max_true_range_pct_1": 0.08,
        "max_volume_surprise_5": 3.0,
        "max_abs_ma_distance_20": 0.12,
        "min_liquidity_20": 18.0,
    } in rows


def test_build_top_n_grid_defaults_to_more_concentrated_candidates():
    spec = AlphaComboRegimeSwitchSpec(
        train_start="2020-01-01",
        train_end="2021-12-31",
        oos_start="2022-01-01",
        oos_end="2022-12-31",
        top_n=10,
    )

    rows = _build_top_n_grid(spec)

    assert rows == [5, 8, 10]


def test_select_mix_neighbors_prefers_closer_windows_and_normalizes_weights():
    mixture_library = [
        {
            "window_label": "near",
            "sample_days": 60,
            "mix": {"trend_low_vol": 0.7, "range_low_vol": 0.3},
            "selection": {"selected_variant": "aggressive"},
            "aggressive": {"factors": ["a"], "factor_weights": {"a": 1.0}},
            "conservative": None,
        },
        {
            "window_label": "mid",
            "sample_days": 55,
            "mix": {"trend_low_vol": 0.5, "range_low_vol": 0.5},
            "selection": {"selected_variant": "aggressive"},
            "aggressive": {"factors": ["b"], "factor_weights": {"b": 1.0}},
            "conservative": None,
        },
        {
            "window_label": "far",
            "sample_days": 50,
            "mix": {"trend_high_vol": 1.0},
            "selection": {"selected_variant": "aggressive"},
            "aggressive": {"factors": ["c"], "factor_weights": {"c": 1.0}},
            "conservative": None,
        },
    ]

    neighbors = _select_mix_neighbors(
        mixture_library,
        {"trend_low_vol": 0.65, "range_low_vol": 0.35},
        neighbor_count=2,
        distance_power=1.0,
    )

    assert [row["window_label"] for row in neighbors] == ["near", "mid"]
    assert abs(sum(row["weight"] for row in neighbors) - 1.0) < 1e-9
    assert neighbors[0]["weight"] > neighbors[1]["weight"]


def test_weighted_numeric_dict_blends_numeric_payloads():
    blended = _weighted_numeric_dict(
        [
            {"blocked_ratio": 0.10, "kept_symbols": 15},
            {"blocked_ratio": 0.30, "kept_symbols": 5},
        ],
        [0.75, 0.25],
    )

    assert abs(blended["blocked_ratio"] - 0.15) < 1e-9
    assert abs(blended["kept_symbols"] - 12.5) < 1e-9
