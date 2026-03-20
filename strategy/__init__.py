"""
策略目录的包入口。

这个目录放的是“从行情数据生成交易信号”的核心逻辑。
如果你将来不断增加策略，这里会成为项目里最常扩展的目录之一。

当前默认导出的“活跃策略池”已经切到更偏短线的版本。
"""

from strategy.mean_reversion.mean_reversion import MeanReversionBollingerStrategy
from strategy.multi_factor_short.multi_factor_short import MultiFactorShortStrategy

__all__ = [
    "MeanReversionBollingerStrategy",
    "MultiFactorShortStrategy",
]
