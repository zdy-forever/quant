from research.factor_combo_search import FactorComboSearchConfig, select_oriented_factor_pool


def _factor_payload(
    rank_ic: float,
    spread: float,
    hit_rate: float,
    segment_rank_ic: list[float],
    segment_spread: list[float],
) -> dict:
    return {
        "rank_ic": {"5": rank_ic},
        "top_bottom_spread": spread,
        "spread_hit_rate": hit_rate,
        "segment_rank_ic": segment_rank_ic,
        "segment_spread": segment_spread,
        "stability_segment_count": len(segment_rank_ic),
    }


def test_select_oriented_factor_pool_prefers_consistent_signals():
    train_result = {
        "factor_names": ["stable_factor", "noisy_factor"],
        "factors": {
            "stable_factor": _factor_payload(0.03, 0.01, 0.56, [0.02, 0.03, 0.01, 0.02], [0.01, 0.01, 0.00, 0.01]),
            "noisy_factor": _factor_payload(0.03, 0.01, 0.56, [0.06, -0.04, 0.05, -0.03], [0.02, -0.01, 0.02, -0.01]),
        },
    }
    oos_result = {
        "factor_names": ["stable_factor", "noisy_factor"],
        "factors": {
            "stable_factor": _factor_payload(0.02, 0.004, 0.53, [0.01, 0.02, 0.01, 0.01], [0.003, 0.004, 0.002, 0.003]),
            "noisy_factor": _factor_payload(0.02, 0.004, 0.53, [0.03, -0.02, 0.02, -0.01], [0.01, -0.01, 0.01, -0.01]),
        },
    }

    result = select_oriented_factor_pool(
        train_result,
        oos_result,
        factor_definitions={},
        cfg=FactorComboSearchConfig(candidate_pool_size=4),
    )

    selected_names = [item["factor"] for item in result["candidate_factors"]]
    assert selected_names == ["stable_factor"]
    assert "noisy_factor" in result["dropped_factors"]
