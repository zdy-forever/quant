"""
工程化组合因子模块。

这里不是直接做最终策略打分，而是把已经冒头的原子信号
先组合成少量可解释的中层因子，继续交给同样的 train/OOS 流程去验证。
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from factors.base import FactorDefinition


def hybrid_factor_definitions() -> Dict[str, FactorDefinition]:
    return {
        "gap_channel_alignment_20_60": FactorDefinition(
            name="gap_channel_alignment_20_60",
            category="hybrid",
            description="20 日平均隔夜跳空和 60 日通道位置的组合，用来看 gap 是否沿既有趋势方向发生。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="工程化组合因子，用来验证 gap 是否更偏趋势确认而不是孤立噪音。",
        ),
        "intraday_resilience_10_20": FactorDefinition(
            name="intraday_resilience_10_20",
            category="hybrid",
            description="10 日日内推进强度叠加 20 日 downside 风险，强调强收盘且回撤更温和的名字。",
            source_title="Downside Risk",
            source_url="https://doi.org/10.1111/j.1540-6261.2006.00851.x",
            source_note="把 intraday strength 和 downside-only 风险放到同一中层因子里验证。",
        ),
        "quiet_trend_pressure_20": FactorDefinition(
            name="quiet_trend_pressure_20",
            category="hybrid",
            description="20 日均线偏离叠加 20 日低波，强调低噪音趋势压力。",
            source_title="Low-Risk Alpha Without Low Beta",
            source_url="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5005746",
            source_note="用来观察趋势是否只有在低波背景下才更值得参与。",
        ),
        "stable_range_breakout_20_60": FactorDefinition(
            name="stable_range_breakout_20_60",
            category="hybrid",
            description="20/60 日通道位置叠加 20 日波动稳定性，强调更平稳的通道突破结构。",
            source_title="Volatility Trading",
            source_url="https://onlinelibrary.wiley.com/doi/book/10.1002/9781119204198",
            source_note="工程化组合因子，用来验证“高位但不乱”的结构是否更有延续性。",
        ),
        "gap_risk_balance_20": FactorDefinition(
            name="gap_risk_balance_20",
            category="hybrid",
            description="20 日 downside 风险减去 20 日 gap 波动，强调隔夜风险更可控的名字。",
            source_title="Price Momentum and Trading Volume",
            source_url="https://www.jstor.org/stable/222483",
            source_note="把 gap 风险和 downside 风险合并成一个更偏稳健的隔夜结构因子。",
        ),
        "trend_structure_alignment_20_60": FactorDefinition(
            name="trend_structure_alignment_20_60",
            category="hybrid",
            description="20/60 日均线结构叠加 10 日日内命中率，强调趋势结构和收盘行为一致。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="用来观察均线趋势和日内强收盘是否同步出现。",
        ),
        "breakout_quality_60": FactorDefinition(
            name="breakout_quality_60",
            category="hybrid",
            description="60 日突破距离叠加 60 日低波，强调更干净的中期突破质量。",
            source_title="Low-Risk Alpha Without Low Beta",
            source_url="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5005746",
            source_note="工程化组合因子，用来验证中期突破是否需要更低波背景才更稳。",
        ),
        "intraday_quiet_strength_10_60": FactorDefinition(
            name="intraday_quiet_strength_10_60",
            category="hybrid",
            description="10 日日内推进强度叠加 60 日低波，强调安静环境里的持续强收盘。",
            source_title="Low-Risk Alpha Without Low Beta",
            source_url="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5005746",
            source_note="沿着最近 mix-aware 里反复冒头的 intraday strength + low vol 结构继续下钻。",
        ),
        "gap_strength_balance_20_10": FactorDefinition(
            name="gap_strength_balance_20_10",
            category="hybrid",
            description="10 日日内推进叠加 20 日隔夜风险平衡，强调白天强而隔夜更稳的名字。",
            source_title="Price Momentum and Trading Volume",
            source_url="https://www.jstor.org/stable/222483",
            source_note="把 recent winners 里的 gap risk balance 和 intraday strength 合成一个中层结构因子。",
        ),
        "channel_defense_20_60": FactorDefinition(
            name="channel_defense_20_60",
            category="hybrid",
            description="20 日通道位置叠加 60 日 downside 风险，强调通道位置和中期防御性同时占优。",
            source_title="Downside Risk",
            source_url="https://doi.org/10.1111/j.1540-6261.2006.00851.x",
            source_note="沿着 channel + downside risk 这条结构继续做更稳健的中层表达。",
        ),
        "gap_breakout_quality_20_60": FactorDefinition(
            name="gap_breakout_quality_20_60",
            category="hybrid",
            description="20 日 gap 波动叠加 60 日突破质量，强调更像趋势确认的隔夜突破。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="沿着 gap volatility + breakout quality 这条已入选结构做进一步组合。",
        ),
        "upside_breakout_fusion_20_60": FactorDefinition(
            name="upside_breakout_fusion_20_60",
            category="hybrid",
            description="20 日上涨压力叠加 60 日突破质量，强调买盘扩散与突破结构同时占优。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="更偏收益弹性的中层结构，而不是单纯低波确认。",
        ),
        "intraday_breakout_followthrough_10_60": FactorDefinition(
            name="intraday_breakout_followthrough_10_60",
            category="hybrid",
            description="10 日日内推进叠加 60 日突破距离，强调强收盘后的突破延续。",
            source_title="Trading Volume and Serial Correlation in Stock Returns",
            source_url="https://academic.oup.com/qje/article/108/4/905/1899978",
            source_note="把 intraday strength 与 breakout 延续做成一个更进攻的中层信号。",
        ),
        "gap_momentum_balance_20_60": FactorDefinition(
            name="gap_momentum_balance_20_60",
            category="hybrid",
            description="20 日平均隔夜跳空叠加 20/60 趋势结构并扣除 gap 波动，强调更健康的趋势确认。",
            source_title="Price Momentum and Trading Volume",
            source_url="https://www.jstor.org/stable/222483",
            source_note="让 gap 不只是大，而且更偏顺势而不是乱跳。",
        ),
        "trend_pressure_release_20_60": FactorDefinition(
            name="trend_pressure_release_20_60",
            category="hybrid",
            description="20 日均线偏离叠加 60 日突破距离和低波背景，强调低噪音趋势释放。",
            source_title="Low-Risk Alpha Without Low Beta",
            source_url="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5005746",
            source_note="把 quiet trend 和 breakout release 两条有效结构合并。",
        ),
    }


def build_hybrid_factor_frame(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("symbol", group_keys=False)
    prev_close = grouped["close"].shift(1)
    daily_ret = grouped["close"].pct_change()
    overnight_gap = df["open"] / prev_close.replace(0.0, np.nan) - 1.0
    intraday_return = df["close"] / df["open"].replace(0.0, np.nan) - 1.0
    rolling_high_20 = grouped["high"].transform(lambda s: s.rolling(20).max().shift(1))
    rolling_low_20 = grouped["low"].transform(lambda s: s.rolling(20).min().shift(1))
    rolling_high_60 = grouped["high"].transform(lambda s: s.rolling(60).max().shift(1))
    rolling_low_60 = grouped["low"].transform(lambda s: s.rolling(60).min().shift(1))
    ma_20 = grouped["close"].transform(lambda s: s.rolling(20).mean())
    ma_60 = grouped["close"].transform(lambda s: s.rolling(60).mean())

    true_range = pd.concat(
        [
            (df["high"] - df["low"]).abs(),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    true_range_pct = true_range / prev_close.replace(0.0, np.nan)

    channel_position_20 = (df["close"] - rolling_low_20) / (rolling_high_20 - rolling_low_20).replace(0.0, np.nan)
    channel_position_60 = (df["close"] - rolling_low_60) / (rolling_high_60 - rolling_low_60).replace(0.0, np.nan)
    centered_channel_20 = 2.0 * channel_position_20 - 1.0
    centered_channel_60 = 2.0 * channel_position_60 - 1.0

    overnight_gap_20 = overnight_gap.groupby(df["symbol"]).transform(lambda s: s.rolling(20).mean())
    intraday_strength_10 = intraday_return.groupby(df["symbol"]).transform(lambda s: s.rolling(10).mean())
    intraday_hit_rate_10 = intraday_return.gt(0).groupby(df["symbol"]).transform(lambda s: s.rolling(10).mean())
    centered_intraday_hit_rate_10 = 2.0 * intraday_hit_rate_10 - 1.0
    positive_mean_20 = daily_ret.clip(lower=0.0).groupby(df["symbol"]).transform(lambda s: s.rolling(20).mean())
    negative_mean_20 = (-daily_ret.clip(upper=0.0)).groupby(df["symbol"]).transform(lambda s: s.rolling(20).mean())
    upside_pressure_20 = positive_mean_20 - negative_mean_20
    downside_risk_20 = -daily_ret.clip(upper=0.0).groupby(df["symbol"]).transform(lambda s: s.rolling(20).std(ddof=0))
    downside_risk_60 = -daily_ret.clip(upper=0.0).groupby(df["symbol"]).transform(lambda s: s.rolling(60).std(ddof=0))
    low_vol_20 = -daily_ret.groupby(df["symbol"]).transform(lambda s: s.rolling(20).std(ddof=0))
    low_vol_60 = -daily_ret.groupby(df["symbol"]).transform(lambda s: s.rolling(60).std(ddof=0))
    gap_volatility_20 = overnight_gap.groupby(df["symbol"]).transform(lambda s: s.rolling(20).std(ddof=0))
    vol_of_range_20 = true_range_pct.groupby(df["symbol"]).transform(lambda s: s.rolling(20).std(ddof=0))
    ma_distance_20 = df["close"] / ma_20.replace(0.0, np.nan) - 1.0
    ma_gap_20_60 = ma_20 / ma_60.replace(0.0, np.nan) - 1.0
    breakout_distance_60 = df["close"] / rolling_high_60.replace(0.0, np.nan) - 1.0

    out = df[["timestamp", "symbol"]].copy()
    out["gap_channel_alignment_20_60"] = overnight_gap_20 + centered_channel_60
    out["intraday_resilience_10_20"] = intraday_strength_10 + downside_risk_20
    out["quiet_trend_pressure_20"] = ma_distance_20 + low_vol_20
    out["stable_range_breakout_20_60"] = 0.5 * (centered_channel_20 + centered_channel_60) - vol_of_range_20
    out["gap_risk_balance_20"] = downside_risk_20 - gap_volatility_20
    out["trend_structure_alignment_20_60"] = ma_gap_20_60 + centered_intraday_hit_rate_10
    out["breakout_quality_60"] = breakout_distance_60 + low_vol_60
    out["intraday_quiet_strength_10_60"] = intraday_strength_10 + low_vol_60
    out["gap_strength_balance_20_10"] = intraday_strength_10 + downside_risk_20 - gap_volatility_20
    out["channel_defense_20_60"] = centered_channel_20 + downside_risk_60
    out["gap_breakout_quality_20_60"] = gap_volatility_20 + breakout_distance_60 + low_vol_60
    out["upside_breakout_fusion_20_60"] = upside_pressure_20 + breakout_distance_60 + low_vol_60
    out["intraday_breakout_followthrough_10_60"] = intraday_strength_10 + breakout_distance_60 + centered_intraday_hit_rate_10
    out["gap_momentum_balance_20_60"] = overnight_gap_20 + ma_gap_20_60 - gap_volatility_20
    out["trend_pressure_release_20_60"] = ma_distance_20 + breakout_distance_60 + low_vol_20
    return out
