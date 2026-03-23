import json

from notifications.emailer import _generic_research_body


def test_regime_switch_email_includes_readable_summary_and_bilingual_metrics():
    payload = {
        "mixture_research": {
            "oos_validation_summary": {
                "window_count": 17,
                "target_pass_rate": 0.0588,
                "avg_cagr": 0.0296,
                "avg_max_dd": -0.0572,
                "avg_sharpe": 0.55,
            },
            "oos_window_validation": [
                {
                    "selected_variant": "mixture_ensemble",
                    "selected_factors": [
                        [
                            "intraday_quiet_strength_10_60",
                            "upside_pressure_20",
                        ],
                        [
                            "gap_breakout_quality_20_60",
                            "momentum_acceleration_20_60",
                        ],
                    ],
                    "weighting_method": "ridge_ml",
                    "ensemble_member_count": 2,
                    "matched_train_windows": [
                        "2021-01-01__2021-03-31",
                        "2021-02-12__2021-05-12",
                    ],
                    "top_n": 6,
                    "execution_overrides": {
                        "hold_rank_buffer": 1,
                        "rebalance_every_n_days": 2,
                    },
                    "trade_filters": {
                        "min_close_location_1": 0.05,
                        "max_true_range_pct_1": 0.09,
                    },
                    "realized_metrics": {
                        "sharpe": 0.61,
                        "cagr": 0.082,
                        "max_dd": -0.071,
                        "avg_turnover": 0.18,
                    },
                }
            ],
        },
        "report_files": {
            "json": "/tmp/alpha_combo_regime_switch.json",
            "markdown": "/tmp/alpha_combo_regime_switch.md",
        },
    }

    body = _generic_research_body("alpha-combo-regime-switch", payload)

    assert "先看结论：" in body
    assert "target_pass_rate(达标窗口占比)：5.88%" in body
    assert "avg_cagr(平均年化收益率)：2.96%" in body
    assert "selected_factors(选中因子)：intraday_quiet_strength_10_60, upside_pressure_20 | gap_breakout_quality_20_60, momentum_acceleration_20_60" in body
    assert "weighting_method(权重生成方式)：ridge_ml" in body
    assert "ensemble_member_count(融合近邻数)：2" in body
    assert "matched_train_windows(匹配训练窗口)：2021-01-01__2021-03-31, 2021-02-12__2021-05-12" in body
    assert "top_n(持仓数)：6" in body
    assert "sharpe(夏普比率)=0.610" in body
    assert "cagr(年化收益率)=8.20%" in body
    assert "avg_turnover(平均换手)=0.180" in body
    assert "报告文件：" in body
    assert "- json: /tmp/alpha_combo_regime_switch.json" in body
    assert "- markdown: /tmp/alpha_combo_regime_switch.md" in body


def test_regime_switch_emailer_imports_without_python_dotenv():
    payload = {
        "mixture_research": {
            "oos_validation_summary": {},
            "oos_window_validation": [],
        },
        "report_files": {},
    }

    body = _generic_research_body("alpha-combo-regime-switch", payload)

    assert isinstance(body, str)
    assert "alpha-combo-regime-switch" in body
