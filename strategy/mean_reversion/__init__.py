"""
均值回归策略子包入口。

目前这里只有一个基于 z-score 的简单版本，
后面你可以扩展成布林带、RSI 反转、配对交易等变体。
"""

from strategy.mean_reversion.mean_reversion import MeanReversionBollingerStrategy

__all__ = ["MeanReversionBollingerStrategy"]
