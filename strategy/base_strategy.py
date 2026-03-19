# -*- coding: utf-8 -*-
"""
所有策略类的公共接口定义都放在这里。

你可以把这个文件看成“策略开发规范”：
- 新策略必须继承 `BaseStrategy`
- 必须告诉系统默认参数、参数搜索范围、需要哪些字段
- 必须实现 `generate()`，把行情数据变成信号

如果你以后想新增第三个策略，最推荐先读这个文件。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

import pandas as pd


@dataclass(frozen=True)
class StrategyResult:
    """
    统一的策略输出格式。

    - signals: index=(timestamp, symbol) 的信号序列，1=做多，0=空仓，-1=做空
    - score: 可选的排序打分
    """

    signals: pd.Series
    score: Optional[pd.Series] = None


class BaseStrategy(ABC):
    """所有策略都必须遵守的接口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """策略名称，用于 frozen 参数文件命名。"""

    @abstractmethod
    def default_params(self) -> Dict[str, Any]:
        """默认参数。"""

    @abstractmethod
    def param_grid(self) -> Dict[str, Iterable[Any]]:
        """训练阶段的参数搜索空间。"""

    @abstractmethod
    def required_columns(self) -> set[str]:
        """策略所需字段。"""

    @abstractmethod
    def generate(self, ohlcv: pd.DataFrame, params: Dict[str, Any]) -> StrategyResult:
        """从 long-format OHLCV 生成信号。"""

    def validate_input(self, ohlcv: pd.DataFrame) -> None:
        missing = self.required_columns() - set(ohlcv.columns)
        if missing:
            raise ValueError(f"[{self.name}] 缺少必要字段: {sorted(missing)}")

        if "timestamp" not in ohlcv.columns or "symbol" not in ohlcv.columns:
            raise ValueError(f"[{self.name}] 必须包含 timestamp 与 symbol 列")
