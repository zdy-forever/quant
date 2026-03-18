import pandas as pd
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from main.clients import data_client


def get_daily_bars(symbols: list[str], lookback_bars: int) -> pd.DataFrame:
    """
    拉取多个股票的日线数据。

    Parameters
    ----------
    symbols : list[str]
        要拉取数据的股票代码列表。
    lookback_bars : int
        希望至少覆盖多少根日线。
        这里不会精确到“正好 N 个交易日”，而是粗略往前多取一些自然日，
        以避免周末和节假日导致数据不够。

    Returns
    -------
    pd.DataFrame
        Alpaca 返回的 MultiIndex DataFrame。
        索引通常是 [symbol, timestamp]。
        列一般包括：
        open, high, low, close, volume, trade_count, vwap
    """
    if not symbols:
        return pd.DataFrame()

    # 为什么乘以 3：
    # 因为 60 根日线不等于 60 个自然日，中间还有周末和假期。
    # 这里往前多取一些，简单粗暴但实用。
    start = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=lookback_bars * 3)

    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=start,
    )

    bars = data_client.get_stock_bars(request).df

    if bars.empty:
        return bars

    # 排序，保证后面计算 rolling / pct_change 时顺序正确。
    return bars.sort_index()