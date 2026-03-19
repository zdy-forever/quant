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
from typing import Optional

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
    symbol_for_regime: str = "SPY"
    no_trade_in_range_high_vol: bool = True


def detect_regime(
    ohlcv: pd.DataFrame,
    cfg: RegimeConfig,
    asof_ts: Optional[pd.Timestamp] = None,
) -> RegimeLabel:
    """使用代表性标的的均线和波动来粗粒度识别市场状态。"""

    df = ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["symbol", "timestamp"])

    market = df[df["symbol"] == cfg.symbol_for_regime][["timestamp", "close"]].dropna()
    if market.empty:
        return RegimeLabel.RANGE_HIGH_VOL

    if asof_ts is not None:
        asof_ts = pd.to_datetime(asof_ts, utc=True)
        market = market[market["timestamp"] <= asof_ts]

    price = market["close"].reset_index(drop=True)
    ma_fast = price.rolling(cfg.trend_fast).mean()
    ma_slow = price.rolling(cfg.trend_slow).mean()
    trend_score = (ma_fast / ma_slow - 1.0).abs()

    ret = price.pct_change()
    vol = ret.rolling(cfg.vol_window).std(ddof=0)

    trend_value = float(trend_score.dropna().iloc[-1]) if not trend_score.dropna().empty else 0.0
    vol_value = float(vol.dropna().iloc[-1]) if not vol.dropna().empty else 1e9

    is_trend = trend_value >= cfg.trend_threshold
    is_high_vol = vol_value >= cfg.vol_threshold

    if is_trend and is_high_vol:
        return RegimeLabel.TREND_HIGH_VOL
    if is_trend:
        return RegimeLabel.TREND_LOW_VOL
    if is_high_vol:
        return RegimeLabel.RANGE_HIGH_VOL
    return RegimeLabel.RANGE_LOW_VOL
