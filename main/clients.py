from alpaca.data.historical import StockHistoricalDataClient
from alpaca.trading.client import TradingClient

from main.config import (
    ALPACA_PAPER1_API_KEY_ID,
    ALPACA_PAPER1_API_SECRET_KEY,
)

# =========================
# Alpaca 客户端初始化
# =========================
# data_client:
#   用来获取历史行情数据，例如日线、分钟线。
#
# trading_client:
#   用来获取账户信息、查看持仓、提交订单等。
#   这里明确写 paper=True，因为你现在只使用模拟盘。
data_client = StockHistoricalDataClient(
    ALPACA_PAPER1_API_KEY_ID,
    ALPACA_PAPER1_API_SECRET_KEY,
)

trading_client = TradingClient(
    ALPACA_PAPER1_API_KEY_ID,
    ALPACA_PAPER1_API_SECRET_KEY,
    paper=True,
)
