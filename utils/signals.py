"""
旧版信号生成模块。

它会根据已经算好的因子，判断每只股票是否满足买入条件，
并生成一个排序分数，方便后面只挑少量候选。

简单理解：`factors.py` 负责“算特征”，这个文件负责“下判断”。
"""

import pandas as pd

from main.config import (
    MIN_PRICE,
    MIN_AVG_DOLLAR_VOLUME,
    MIN_VOLUME_RATIO,
)


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    根据因子生成交易信号。

    当前买入信号逻辑：
    1. 当前价格 >= MIN_PRICE
    2. 20日平均成交额 >= MIN_AVG_DOLLAR_VOLUME
    3. 当前收盘价 > 过去N日最高价（breakout）
    4. 当前成交量 / 过去20日平均成交量 >= MIN_VOLUME_RATIO
    5. 20日收益率 > 0（中期趋势向上）

    同时生成一个 rank_score，用于对候选股票排序。
    这里只是一个简单线性组合，后面你可以自己改。

    Returns
    -------
    pd.DataFrame
        每只股票一行，包含 signal 和 rank_score
    """
    if df.empty:
        return pd.DataFrame()

    rows: list[dict] = []

    for symbol, sub_df in df.groupby(level=0):
        if sub_df.empty:
            continue

        latest = sub_df.iloc[-1]

        # 这些列如果有 NaN，说明历史数据还不够，不能做判断
        required_cols = [
            "close",
            "ret_5",
            "ret_20",
            "high_breakout",
            "avg_dollar_volume_20",
            "volume_ratio",
        ]
        if latest[required_cols].isna().any():
            continue

        price_ok = latest["close"] >= MIN_PRICE
        liquidity_ok = latest["avg_dollar_volume_20"] >= MIN_AVG_DOLLAR_VOLUME
        breakout_ok = latest["close"] > latest["high_breakout"]
        volume_ok = latest["volume_ratio"] >= MIN_VOLUME_RATIO
        momentum_ok = latest["ret_20"] > 0

        signal = bool(
            price_ok
            and liquidity_ok
            and breakout_ok
            and volume_ok
            and momentum_ok
        )

        # 简单排序分数
        # 这里只是为了先给候选股排优先级，不代表最优模型。
        rank_score = (
                0.5 * float(latest["ret_20"])
                + 0.3 * float(latest["ret_5"])
                + 0.2 * float(latest["volume_ratio"])
        )

        rows.append(
            {
                "symbol": symbol,
                "close": float(latest["close"]),
                "ret_5": float(latest["ret_5"]),
                "ret_20": float(latest["ret_20"]),
                "volume_ratio": float(latest["volume_ratio"]),
                "avg_dollar_volume_20": float(latest["avg_dollar_volume_20"]),
                "signal": signal,
                "rank_score": rank_score,
            }
        )

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)

    # 先按是否有信号排序，再按 rank_score 从高到低排序
    result = result.sort_values(
        by=["signal", "rank_score"],
        ascending=[False, False],
    ).reset_index(drop=True)

    return result
