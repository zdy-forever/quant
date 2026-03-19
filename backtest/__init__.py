"""
回测相关模块的包入口。

这个目录下面分别放训练、样本外测试和 walk-forward 验证逻辑，
方便你把“研究”与“部署”明确拆开。
"""

from backtest.engine import BacktestConfig, combine_strategy_weight_frames, run_signal_backtest, run_weight_backtest
from backtest.optimizer import OptimizationSpec, optimize_strategies, optimize_strategy
from backtest.test import TestSpec, run_oos_test
from backtest.train import TrainSpec, train
from backtest.walk_forward import WalkForwardSpec, run_walk_forward

__all__ = [
    "BacktestConfig",
    "run_signal_backtest",
    "run_weight_backtest",
    "combine_strategy_weight_frames",
    "OptimizationSpec",
    "optimize_strategy",
    "optimize_strategies",
    "TrainSpec",
    "train",
    "TestSpec",
    "run_oos_test",
    "WalkForwardSpec",
    "run_walk_forward",
]
