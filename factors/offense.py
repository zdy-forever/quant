"""
进攻型收益弹性因子模块。

这组因子不再优先追求“更稳”，而是更关注：
- 趋势是不是在加速
- 上涨压力是不是明显高于下跌压力
- 强势日内推进有没有持续跟随
- 压缩后的突破是不是正在释放
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from factors.base import FactorDefinition


def offense_factor_definitions() -> Dict[str, FactorDefinition]:
    return {
        "momentum_acceleration_20_60": FactorDefinition(
            name="momentum_acceleration_20_60",
            category="offense",
            description="20 日动量减去 60 日动量，越大代表近期趋势相对中期正在加速。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="把趋势拆成“已经很强”和“正在加速变强”两个层次。",
        ),
        "upside_pressure_20": FactorDefinition(
            name="upside_pressure_20",
            category="offense",
            description="20 日正收益均值减去负收益均值，越大代表上涨压力明显占优。",
            source_title="Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency",
            source_url="https://doi.org/10.1111/j.1540-6261.1993.tb04702.x",
            source_note="用收益分布不对称来补充单纯的 total return 动量。",
        ),
        "intraday_followthrough_5_20": FactorDefinition(
            name="intraday_followthrough_5_20",
            category="offense",
            description="5 日日内推进叠加实体强度，越大代表强收盘后的跟随更持续。",
            source_title="Trading Volume and Serial Correlation in Stock Returns",
            source_url="https://academic.oup.com/qje/article/108/4/905/1899978",
            source_note="把 intraday strength 和 K 线实体强度放在一起，强调持续跟随而不是单日冲高。",
        ),
        "squeeze_breakout_5_20_60": FactorDefinition(
            name="squeeze_breakout_5_20_60",
            category="offense",
            description="60 日突破距离叠加 5/20 波动压缩，越大代表压缩后的中期突破更有弹性。",
            source_title="Low-Risk Alpha Without Low Beta",
            source_url="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5005746",
            source_note="沿着 breakout + squeeze release 这条更偏进攻的结构做工程化表达。",
        ),
        "upside_followthrough_10_20": FactorDefinition(
            name="upside_followthrough_10_20",
            category="offense",
            description="10 日强收盘命中率叠加 20 日上涨压力，越大代表强势推进正在持续扩散。",
            source_title="Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency",
            source_url="https://doi.org/10.1111/j.1540-6261.1993.tb04702.x",
            source_note="把上涨压力和强收盘持续性合到一起，专门追求更高收益弹性。",
        ),
        "breakout_thrust_20_60": FactorDefinition(
            name="breakout_thrust_20_60",
            category="offense",
            description="60 日突破距离叠加 20 日动量和实体强度，越大代表突破后的推进更有推力。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="更偏趋势释放，而不是低波稳健。",
        ),
        "gap_trend_acceleration_20_60": FactorDefinition(
            name="gap_trend_acceleration_20_60",
            category="offense",
            description="20 日平均隔夜跳空叠加 20/60 动量加速度，越大代表隔夜趋势确认更强。",
            source_title="Price Momentum and Trading Volume",
            source_url="https://www.jstor.org/stable/222483",
            source_note="沿着 gap continuation 和趋势加速继续做更进攻的表达。",
        ),
        "trend_strength_spread_20_60": FactorDefinition(
            name="trend_strength_spread_20_60",
            category="offense",
            description="20/60 均线结构叠加上涨压力，越大代表中期趋势和短期买盘扩散同时占优。",
            source_title="Momentum Strategies",
            source_url="https://www.nber.org/papers/w5375",
            source_note="把趋势结构和收益分布偏强这两种进攻信号合在一起。",
        ),
        "squeeze_followthrough_5_20_60": FactorDefinition(
            name="squeeze_followthrough_5_20_60",
            category="offense",
            description="60 日突破距离叠加压缩释放和日内跟随，越大代表突破不只是刺穿而是继续跑。",
            source_title="Low-Risk Alpha Without Low Beta",
            source_url="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5005746",
            source_note="专门追求突破后的延续收益，而不是只看干净度。",
        ),
    }


def build_offense_factor_frame(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("symbol", group_keys=False)
    daily_ret = grouped["close"].pct_change()
    momentum_20 = grouped["close"].pct_change(20)
    momentum_60 = grouped["close"].pct_change(60)
    positive_mean_20 = daily_ret.clip(lower=0.0).groupby(df["symbol"]).transform(lambda s: s.rolling(20).mean())
    negative_mean_20 = (-daily_ret.clip(upper=0.0)).groupby(df["symbol"]).transform(lambda s: s.rolling(20).mean())

    intraday_return = df["close"] / df["open"].replace(0.0, np.nan) - 1.0
    bar_range = (df["high"] - df["low"]).replace(0.0, np.nan)
    body_to_range = (df["close"] - df["open"]) / bar_range
    intraday_strength_5 = intraday_return.groupby(df["symbol"]).transform(lambda s: s.rolling(5).mean())
    body_to_range_5 = body_to_range.groupby(df["symbol"]).transform(lambda s: s.rolling(5).mean())
    intraday_hit_rate_10 = intraday_return.gt(0).groupby(df["symbol"]).transform(lambda s: s.rolling(10).mean())
    centered_intraday_hit_rate_10 = 2.0 * intraday_hit_rate_10 - 1.0

    prev_close = grouped["close"].shift(1)
    overnight_gap = df["open"] / prev_close.replace(0.0, np.nan) - 1.0
    overnight_gap_20 = overnight_gap.groupby(df["symbol"]).transform(lambda s: s.rolling(20).mean())
    true_range = pd.concat(
        [
            (df["high"] - df["low"]).abs(),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_5 = true_range.groupby(df["symbol"]).transform(lambda s: s.rolling(5).mean())
    atr_20 = true_range.groupby(df["symbol"]).transform(lambda s: s.rolling(20).mean())
    rolling_high_60 = grouped["high"].transform(lambda s: s.rolling(60).max().shift(1))
    breakout_distance_60 = df["close"] / rolling_high_60.replace(0.0, np.nan) - 1.0
    ma_20 = grouped["close"].transform(lambda s: s.rolling(20).mean())
    ma_60 = grouped["close"].transform(lambda s: s.rolling(60).mean())
    trend_strength_spread_20_60 = ma_20 / ma_60.replace(0.0, np.nan) - 1.0

    out = df[["timestamp", "symbol"]].copy()
    out["momentum_acceleration_20_60"] = momentum_20 - momentum_60
    out["upside_pressure_20"] = positive_mean_20 - negative_mean_20
    out["intraday_followthrough_5_20"] = intraday_strength_5 + body_to_range_5
    out["squeeze_breakout_5_20_60"] = breakout_distance_60 - (atr_5 / atr_20.replace(0.0, np.nan))
    out["upside_followthrough_10_20"] = centered_intraday_hit_rate_10 + out["upside_pressure_20"]
    out["breakout_thrust_20_60"] = breakout_distance_60 + momentum_20 + body_to_range_5
    out["gap_trend_acceleration_20_60"] = overnight_gap_20 + out["momentum_acceleration_20_60"]
    out["trend_strength_spread_20_60"] = trend_strength_spread_20_60 + out["upside_pressure_20"]
    out["squeeze_followthrough_5_20_60"] = out["squeeze_breakout_5_20_60"] + intraday_strength_5
    return out
