"""
防前视偏差测试。

这个测试的目的很重要：确认趋势策略用的是“过去窗口”的高点，
而不是把当天未来才知道的数据偷偷用进来。

如果这个测试失败，说明策略可能存在 lookahead bias，回测结果就不可信。
"""

import pandas as pd

from strategy.trend.trend import TrendBreakoutStrategy


def test_trend_breakout_uses_prior_high_only():
    dates = pd.date_range("2024-01-01", periods=25, tz="UTC")
    df = pd.DataFrame(
        {
            "timestamp": dates,
            "symbol": ["AAA"] * len(dates),
            "open": [10.0] * 24 + [15.0],
            "high": [10.0] * 24 + [20.0],
            "low": [9.5] * 24 + [14.5],
            "close": [10.0] * 24 + [15.0],
            "volume": [100_000] * 24 + [300_000],
        }
    )

    strategy = TrendBreakoutStrategy()
    params = strategy.default_params()
    params.update(
        {
            "breakout_window": 20,
            "volume_window": 20,
            "momentum_window": 20,
            "min_avg_dollar_volume": 0.0,
            "min_volume_ratio": 1.0,
            "top_k": 1,
        }
    )

    result = strategy.generate(df, params)
    signal = result.signals.xs(dates[-1], level="timestamp").loc["AAA"]
    assert signal == 1
