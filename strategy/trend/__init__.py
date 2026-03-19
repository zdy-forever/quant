"""
趋势策略子包入口。

目前这里只放了一个突破型趋势策略，
后面你也可以继续加别的趋势跟随变体。
"""

from strategy.trend.trend import TrendBreakoutStrategy

__all__ = ["TrendBreakoutStrategy"]
