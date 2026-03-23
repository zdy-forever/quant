import pandas as pd

from backtest.engine import BacktestConfig, build_daily_target_weights


def _sample_signals_and_scores():
    timestamp = pd.Timestamp("2024-01-02", tz="UTC")
    index = pd.MultiIndex.from_tuples(
        [
            (timestamp, "AAA"),
            (timestamp, "BBB"),
            (timestamp, "CCC"),
        ],
        names=["timestamp", "symbol"],
    )
    signals = pd.Series([1, 1, 1], index=index, name="signal")
    scores = pd.Series([0.40, 0.20, -0.10], index=index, name="score")
    dates = pd.Index([timestamp])
    return signals, scores, dates


def test_build_daily_target_weights_respects_min_score_threshold():
    signals, scores, dates = _sample_signals_and_scores()

    weights = build_daily_target_weights(
        signals,
        scores,
        dates,
        BacktestConfig(max_positions=3, min_score_threshold=0.0),
    )

    assert abs(weights.iloc[0]["AAA"] - 0.5) < 1e-9
    assert abs(weights.iloc[0]["BBB"] - 0.5) < 1e-9
    assert abs(weights.iloc[0]["CCC"]) < 1e-9


def test_build_daily_target_weights_tilts_weights_by_rank():
    signals, scores, dates = _sample_signals_and_scores()

    weights = build_daily_target_weights(
        signals,
        scores,
        dates,
        BacktestConfig(max_positions=2, rank_weight_power=1.0),
    )

    assert abs(weights.iloc[0]["AAA"] - (2.0 / 3.0)) < 1e-9
    assert abs(weights.iloc[0]["BBB"] - (1.0 / 3.0)) < 1e-9


def test_build_daily_target_weights_retains_existing_positions_with_hold_buffer():
    timestamps = [
        pd.Timestamp("2024-01-02", tz="UTC"),
        pd.Timestamp("2024-01-03", tz="UTC"),
    ]
    signal_index = pd.MultiIndex.from_tuples(
        [
            (timestamps[0], "AAA"),
            (timestamps[0], "BBB"),
            (timestamps[1], "AAA"),
            (timestamps[1], "CCC"),
        ],
        names=["timestamp", "symbol"],
    )
    score_index = pd.MultiIndex.from_tuples(
        [
            (timestamps[0], "AAA"),
            (timestamps[0], "BBB"),
            (timestamps[0], "CCC"),
            (timestamps[1], "AAA"),
            (timestamps[1], "BBB"),
            (timestamps[1], "CCC"),
        ],
        names=["timestamp", "symbol"],
    )
    signals = pd.Series([1, 1, 1, 1], index=signal_index, name="signal")
    scores = pd.Series([1.00, 0.90, 0.80, 1.00, 0.94, 0.95], index=score_index, name="score")

    weights = build_daily_target_weights(
        signals,
        scores,
        pd.Index(timestamps),
        BacktestConfig(max_positions=2, hold_rank_buffer=1),
    )

    assert abs(weights.loc[timestamps[0], "AAA"] - 0.5) < 1e-9
    assert abs(weights.loc[timestamps[0], "BBB"] - 0.5) < 1e-9
    assert abs(weights.loc[timestamps[1], "AAA"] - 0.5) < 1e-9
    assert abs(weights.loc[timestamps[1], "BBB"] - 0.5) < 1e-9
    assert abs(weights.loc[timestamps[1], "CCC"]) < 1e-9


def test_build_daily_target_weights_applies_score_hysteresis_to_existing_positions():
    timestamps = [
        pd.Timestamp("2024-01-02", tz="UTC"),
        pd.Timestamp("2024-01-03", tz="UTC"),
    ]
    signal_index = pd.MultiIndex.from_tuples(
        [
            (timestamps[0], "AAA"),
            (timestamps[1], "BBB"),
        ],
        names=["timestamp", "symbol"],
    )
    score_index = pd.MultiIndex.from_tuples(
        [
            (timestamps[0], "AAA"),
            (timestamps[0], "BBB"),
            (timestamps[1], "AAA"),
            (timestamps[1], "BBB"),
        ],
        names=["timestamp", "symbol"],
    )
    signals = pd.Series([1, 1], index=signal_index, name="signal")
    scores = pd.Series([0.10, 0.00, -0.05, -0.02], index=score_index, name="score")

    weights = build_daily_target_weights(
        signals,
        scores,
        pd.Index(timestamps),
        BacktestConfig(
            max_positions=1,
            min_score_threshold=0.0,
            hold_rank_buffer=1,
            score_hysteresis=0.10,
        ),
    )

    assert abs(weights.loc[timestamps[0], "AAA"] - 1.0) < 1e-9
    assert abs(weights.loc[timestamps[1], "AAA"] - 1.0) < 1e-9
    assert abs(weights.loc[timestamps[1], "BBB"]) < 1e-9


def test_build_daily_target_weights_shrinks_breadth_when_few_scores_clear_dynamic_threshold():
    signals, scores, dates = _sample_signals_and_scores()
    scores = scores.copy()
    scores.loc[(pd.Timestamp("2024-01-02", tz="UTC"), "CCC")] = 0.10

    weights = build_daily_target_weights(
        signals,
        scores,
        dates,
        BacktestConfig(
            max_positions=3,
            dynamic_breadth_score_threshold=0.15,
            min_dynamic_positions=0,
        ),
    )

    assert abs(weights.iloc[0]["AAA"] - 0.5) < 1e-9
    assert abs(weights.iloc[0]["BBB"] - 0.5) < 1e-9
    assert abs(weights.iloc[0]["CCC"]) < 1e-9
