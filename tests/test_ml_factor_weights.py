import pandas as pd

from research.ml_factor_weights import RidgeWeightConfig, fit_oriented_ridge_factor_weights


def test_fit_oriented_ridge_factor_weights_prefers_stronger_signal():
    rows = []
    dates = pd.date_range("2023-01-01", periods=90, freq="D", tz="UTC")
    for ts in dates:
        for rank, symbol in enumerate(["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]):
            strength = 3 - rank
            rows.append(
                {
                    "timestamp": ts,
                    "symbol": symbol,
                    "eligible": True,
                    "strong_factor": float(strength),
                    "weak_factor": float((rank % 3) - 1),
                    "fwd_ret_5": float(strength) * 0.01,
                }
            )
    panel = pd.DataFrame(rows)

    result = fit_oriented_ridge_factor_weights(
        panel,
        ["strong_factor", "weak_factor"],
        {"strong_factor": 1, "weak_factor": 1},
        "fwd_ret_5",
        RidgeWeightConfig(
            alpha_grid=(0.25, 0.5, 1.0),
            min_validation_days=15,
            min_train_days=30,
            min_sample_rows=200,
            min_daily_samples=4,
        ),
    )

    assert result is not None
    assert result["factor_weights"]["strong_factor"] > result["factor_weights"]["weak_factor"]
    assert abs(sum(abs(v) for v in result["factor_weights"].values()) - 1.0) < 1e-9
    assert result["validation_rank_ic"] > 0.5
