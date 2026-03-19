"""
风险控制目录的包入口。

这个目录里的代码主要负责把“可以交易”变成“可以安全地交易”，
属于策略之外非常重要的一层保护。
"""

from risk.management import (
    RiskConfig,
    apply_drawdown_kill_switch,
    clamp_weights,
    estimate_trade_cost_multiplier,
)

__all__ = [
    "RiskConfig",
    "apply_drawdown_kill_switch",
    "clamp_weights",
    "estimate_trade_cost_multiplier",
]
