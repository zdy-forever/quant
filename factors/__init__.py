"""
因子注册表入口。

这个包不负责回测，也不负责交易规则，
它只负责一件事：把原子因子定义清楚，并生成统一的横截面因子表。

如果你以后继续扩研究，优先往这个目录加新因子，
而不是直接去 `strategy/` 里写买卖条件。
"""
from __future__ import annotations

from typing import Dict

import pandas as pd

from factors.base import FactorDefinition, merge_factor_frames, prepare_ohlcv
from factors.breakout import breakout_factor_definitions, build_breakout_factor_frame
from factors.flow import build_flow_factor_frame, flow_factor_definitions
from factors.hybrid import build_hybrid_factor_frame, hybrid_factor_definitions
from factors.momentum import build_momentum_factor_frame, momentum_factor_definitions
from factors.microstructure import build_microstructure_factor_frame, microstructure_factor_definitions
from factors.offense import build_offense_factor_frame, offense_factor_definitions
from factors.reversal import build_reversal_factor_frame, reversal_factor_definitions
from factors.risk_structure import build_risk_structure_factor_frame, risk_structure_factor_definitions
from factors.trend_quality import build_trend_quality_factor_frame, trend_quality_factor_definitions
from factors.volatility import build_volatility_factor_frame, volatility_factor_definitions
from factors.volume import build_volume_factor_frame, volume_factor_definitions


def get_factor_definitions() -> Dict[str, FactorDefinition]:
    definitions: Dict[str, FactorDefinition] = {}
    for block in (
        momentum_factor_definitions(),
        trend_quality_factor_definitions(),
        reversal_factor_definitions(),
        volatility_factor_definitions(),
        volume_factor_definitions(),
        breakout_factor_definitions(),
        hybrid_factor_definitions(),
        offense_factor_definitions(),
        microstructure_factor_definitions(),
        flow_factor_definitions(),
        risk_structure_factor_definitions(),
    ):
        definitions.update(block)
    return definitions


def build_factor_panel(ohlcv: pd.DataFrame) -> pd.DataFrame:
    prepared = prepare_ohlcv(ohlcv)
    frames = [
        build_momentum_factor_frame(prepared),
        build_trend_quality_factor_frame(prepared),
        build_reversal_factor_frame(prepared),
        build_volatility_factor_frame(prepared),
        build_volume_factor_frame(prepared),
        build_breakout_factor_frame(prepared),
        build_hybrid_factor_frame(prepared),
        build_offense_factor_frame(prepared),
        build_microstructure_factor_frame(prepared),
        build_flow_factor_frame(prepared),
        build_risk_structure_factor_frame(prepared),
    ]
    return merge_factor_frames(frames)
