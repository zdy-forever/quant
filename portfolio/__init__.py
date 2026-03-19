"""
仓位分配目录的包入口。

这里的逻辑在交易系统里很重要，因为同样的信号，
不同仓位方法会显著改变收益曲线和回撤。
"""

from portfolio.position_sizing import PositionConfig, compute_weights_from_signals
from portfolio.strategy_blend import StrategyBlendConfig, compute_strategy_allocations

__all__ = ["PositionConfig", "compute_weights_from_signals", "StrategyBlendConfig", "compute_strategy_allocations"]
