from alpaca.trading.requests import (
    MarketOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

from main.clients import trading_client
from main.config import STOP_LOSS_PCT, TAKE_PROFIT_PCT


def build_bracket_order(symbol: str, qty: int, entry_price: float) -> MarketOrderRequest:
    """
    构造一个 bracket order（括号单）。

    bracket order 的意思是：
    - 先提交一个主买单
    - 同时挂一个止盈单
    - 同时挂一个止损单

    这样比较适合你这种不盯盘、提前设置好风控的用法。
    """
    stop_price = round(entry_price * (1 - STOP_LOSS_PCT), 2)
    take_profit_price = round(entry_price * (1 + TAKE_PROFIT_PCT), 2)

    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(limit_price=take_profit_price),
        stop_loss=StopLossRequest(stop_price=stop_price),
    )
    return order


def submit_bracket_order(symbol: str, qty: int, entry_price: float):
    """
    提交 bracket order 到 Alpaca 模拟盘。
    """
    order = build_bracket_order(symbol, qty, entry_price)
    return trading_client.submit_order(order_data=order)