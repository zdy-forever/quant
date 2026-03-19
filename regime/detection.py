# -*- coding: utf-8 -*-
"""
市场状态识别模块。

这里不负责产生买卖信号，而是回答一个更上层的问题：
“现在更像趋势市，还是震荡市？波动大还是小？”

系统会根据这里给出的状态去选择策略，或者决定是否暂时不交易。
如果你想做更复杂的状态识别，这个文件就是最直接的入口。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

import pandas as pd


class RegimeLabel(str, Enum):
    RANGE_LOW_VOL = "range_low_vol"
    RANGE_HIGH_VOL = "range_high_vol"
    TREND_LOW_VOL = "trend_low_vol"
    TREND_HIGH_VOL = "trend_high_vol"


@dataclass(frozen=True)
class RegimeConfig:
    trend_fast: int = 20
    trend_slow: int = 100
    trend_threshold: float = 0.01
    vol_window: int = 20
    vol_threshold: float = 0.02
    mix_lookback_days: int = 60
    symbol_for_regime: str = "SPY"
    no_trade_in_range_high_vol: bool = True


def classify_regime_history(
    ohlcv: pd.DataFrame,
    cfg: RegimeConfig,
    asof_ts: Optional[pd.Timestamp] = None,
) -> pd.Series:
    """生成代表性标的在历史上的逐日市场状态序列。"""

    df = ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["symbol", "timestamp"])

    market = df[df["symbol"] == cfg.symbol_for_regime][["timestamp", "close"]].dropna()
    if market.empty:
        return pd.Series(dtype=object)

    if asof_ts is not None:
        asof_ts = pd.to_datetime(asof_ts, utc=True)
        market = market[market["timestamp"] <= asof_ts]

    market = market.reset_index(drop=True)
    price = market["close"]
    ma_fast = price.rolling(cfg.trend_fast).mean()
    ma_slow = price.rolling(cfg.trend_slow).mean()
    trend_score = (ma_fast / ma_slow - 1.0).abs()

    ret = price.pct_change()
    vol = ret.rolling(cfg.vol_window).std(ddof=0)

    labels = []
    for trend_value, vol_value in zip(trend_score.tolist(), vol.tolist()):
        trend_value = 0.0 if pd.isna(trend_value) else float(trend_value)
        vol_value = 1e9 if pd.isna(vol_value) else float(vol_value)

        is_trend = trend_value >= cfg.trend_threshold
        is_high_vol = vol_value >= cfg.vol_threshold

        if is_trend and is_high_vol:
            labels.append(RegimeLabel.TREND_HIGH_VOL.value)
        elif is_trend:
            labels.append(RegimeLabel.TREND_LOW_VOL.value)
        elif is_high_vol:
            labels.append(RegimeLabel.RANGE_HIGH_VOL.value)
        else:
            labels.append(RegimeLabel.RANGE_LOW_VOL.value)

    return pd.Series(labels, index=market["timestamp"], name="regime")


def detect_regime(
    ohlcv: pd.DataFrame,
    cfg: RegimeConfig,
    asof_ts: Optional[pd.Timestamp] = None,
) -> RegimeLabel:
    """使用代表性标的的均线和波动来粗粒度识别市场状态。"""

    labels = classify_regime_history(ohlcv, cfg, asof_ts=asof_ts)
    if labels.empty:
        return RegimeLabel.RANGE_HIGH_VOL
    return RegimeLabel(labels.iloc[-1])


def estimate_regime_mixture(
    ohlcv: pd.DataFrame,
    cfg: RegimeConfig,
    asof_ts: Optional[pd.Timestamp] = None,
) -> Dict[str, float]:
    """
    返回最近一段时间内不同市场状态的大致占比。

    例如：
    - trend_total = 0.70
    - range_total = 0.30
    这样的输出就可以直接拿去做策略层资金分配。
    """

    labels = classify_regime_history(ohlcv, cfg, asof_ts=asof_ts)
    if labels.empty:
        return {
            RegimeLabel.RANGE_HIGH_VOL.value: 1.0,
            "trend_total": 0.0,
            "range_total": 1.0,
            "high_vol_total": 1.0,
            "low_vol_total": 0.0,
        }

    tail = labels.tail(cfg.mix_lookback_days)
    probs = tail.value_counts(normalize=True).to_dict()
    probs = {str(key): float(value) for key, value in probs.items()}
    probs["trend_total"] = probs.get(RegimeLabel.TREND_LOW_VOL.value, 0.0) + probs.get(RegimeLabel.TREND_HIGH_VOL.value, 0.0)
    probs["range_total"] = probs.get(RegimeLabel.RANGE_LOW_VOL.value, 0.0) + probs.get(RegimeLabel.RANGE_HIGH_VOL.value, 0.0)
    probs["high_vol_total"] = probs.get(RegimeLabel.TREND_HIGH_VOL.value, 0.0) + probs.get(RegimeLabel.RANGE_HIGH_VOL.value, 0.0)
    probs["low_vol_total"] = probs.get(RegimeLabel.TREND_LOW_VOL.value, 0.0) + probs.get(RegimeLabel.RANGE_LOW_VOL.value, 0.0)
    return probs
