"""
低波动动量策略子包入口。

这个策略偏向挑选“涨得稳、波动不大”的股票，
适合作为趋势策略之外的稳健补充。
"""

from strategy.low_vol_momentum.low_vol_momentum import LowVolMomentumStrategy

__all__ = ["LowVolMomentumStrategy"]
