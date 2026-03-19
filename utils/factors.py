"""
旧版因子计算模块。

它把原始 K 线加工成更容易做决策的字段，比如：
- 5日/20日收益率
- 突破高点
- 平均成交量
- 平均成交额
- 量比

如果你以后想加新的过滤条件，通常就在这里扩展。
"""

import pandas as pd

from main.config import BREAKOUT_WINDOW, VOLUME_WINDOW


def add_factors(bars: pd.DataFrame) -> pd.DataFrame:
    """
    对原始 K 线数据添加因子列。

    当前添加的因子：
    1. ret_5                5日收益率
    2. ret_20               20日收益率
    3. high_breakout        过去 N 日最高价（不含今天）
    4. avg_volume_20        过去 20 日平均成交量（不含今天）
    5. avg_dollar_volume_20 过去 20 日平均成交额（不含今天）
    6. volume_ratio         今天成交量 / 过去20日平均成交量

    Parameters
    ----------
    bars : pd.DataFrame
        原始日线数据，索引通常是 [symbol, timestamp]

    Returns
    -------
    pd.DataFrame
        添加好因子列后的 DataFrame
    """
    if bars.empty:
        return bars

    frames = []

    # bars 是 MultiIndex，第一层通常是 symbol
    # 所以按股票分组后分别计算因子。
    for symbol, sub_df in bars.groupby(level=0):
        df = sub_df.copy()

        # 5日和20日收益率
        df["ret_5"] = df["close"].pct_change(5)
        df["ret_20"] = df["close"].pct_change(20)

        # 过去 BREAKOUT_WINDOW 天最高价，不包含今天，所以要 shift(1)
        df["high_breakout"] = (
            df["high"]
            .rolling(BREAKOUT_WINDOW)
            .max()
            .shift(1)
        )

        # 过去 VOLUME_WINDOW 天平均成交量，不包含今天
        df["avg_volume_20"] = (
            df["volume"]
            .rolling(VOLUME_WINDOW)
            .mean()
            .shift(1)
        )

        # 过去 VOLUME_WINDOW 天平均成交额，不包含今天
        df["avg_dollar_volume_20"] = (
            (df["close"] * df["volume"])
            .rolling(VOLUME_WINDOW)
            .mean()
            .shift(1)
        )

        # 成交量放大倍数
        df["volume_ratio"] = df["volume"] / df["avg_volume_20"]

        frames.append(df)

    result = pd.concat(frames).sort_index()
    return result
