# -*- coding: utf-8 -*-
"""
Alpha 因子兼容层。

项目现在已经把因子主实现迁到了新的 `factors/` 包里，
但旧模块名 `alpha_lab.factors` 仍然保留，
避免旧研究脚本和旧策略因为导入路径变化而失效。

如果你要继续扩因子，请优先改 `factors/` 目录。
"""
from __future__ import annotations

import pandas as pd

import factors as project_factors


def build_alpha_factor_panel(ohlcv: pd.DataFrame) -> pd.DataFrame:
    return project_factors.build_factor_panel(ohlcv)


def build_factor_panel(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """
    保留旧名字，方便旧调用方和 IDE 都能找到这个入口。
    """

    return build_alpha_factor_panel(ohlcv)
