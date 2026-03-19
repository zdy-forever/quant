"""
旧版脚本使用的集中配置文件。

这里主要保存：
- Alpaca 凭证读取
- 扫描参数
- 风控参数
- 邮件配置

如果你是新手，建议把它理解成“旧系统的控制面板”。
不过新架构里更推荐把运行期参数放到 `config/runtime.yaml`。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 读取 .env 文件中的环境变量
load_dotenv()

# =========================
# Alpaca Paper Account 配置
# =========================
# 同时兼容旧变量名和新的通用变量名。
ALPACA_PAPER1_API_KEY_ID = os.getenv("ALPACA_PAPER1_API_KEY_ID") or os.getenv("ALPACA_API_KEY")
ALPACA_PAPER1_API_SECRET_KEY = os.getenv("ALPACA_PAPER1_API_SECRET_KEY") or os.getenv("ALPACA_API_SECRET")

# 如果没有读取到 key，程序启动时直接报错，避免后面运行一半才出问题。
if not ALPACA_PAPER1_API_KEY_ID or not ALPACA_PAPER1_API_SECRET_KEY:
    raise ValueError(
        "Missing Alpaca paper credentials. "
        "Please set ALPACA_API_KEY / ALPACA_API_SECRET or "
        "ALPACA_PAPER1_API_KEY_ID / ALPACA_PAPER1_API_SECRET_KEY in your .env file."
    )

# =========================
# 交易 / 扫描参数
# =========================

def _load_watchlist() -> list[str]:
    symbols_file = Path("config") / "symbols.txt"
    if symbols_file.exists():
        symbols = [
            line.strip().upper()
            for line in symbols_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if symbols:
            return symbols

    return [
        "AAPL", "MSFT", "NVDA", "AMZN", "META",
        "TSLA", "GOOGL", "AMD", "NFLX", "AVGO",
    ]


WATCHLIST = _load_watchlist()

# 回看多少根 K 线。
# 因为后面会用到 20 日收益率、20 日均量等指标，
# 60 根日线通常够起步使用。
LOOKBACK_BARS = 60

# breakout 的回看窗口。
# 例如 20，表示看“过去 20 天最高价”。
BREAKOUT_WINDOW = 20

# 成交量均值窗口。
VOLUME_WINDOW = 20

# 过滤太便宜的股票，避免很多低价股噪声较大。
MIN_PRICE = 10.0

# 过滤流动性太差的股票。
# 这里用“20日平均成交额”过滤。
MIN_AVG_DOLLAR_VOLUME = 5_000_000

# 成交量放大量比的最低要求。
# 例如 1.5 表示：今天成交量至少是过去 20 天平均成交量的 1.5 倍。
MIN_VOLUME_RATIO = 1.5

# 单笔交易最多允许亏掉总权益的 1%。
RISK_PER_TRADE = 0.01

# 最多同时选多少个候选股票。
MAX_POSITIONS = 5

# 止损和止盈百分比。
STOP_LOSS_PCT = 0.05
TAKE_PROFIT_PCT = 0.10

# 是否只是演练，不真实提交订单。
# 你现在建议保持 True。
DRY_RUN = True

# 输出目录和输出文件名
OUTPUT_DIR = "output"
SIGNALS_CSV = f"{OUTPUT_DIR}/signals.csv"
SELECTED_CSV = f"{OUTPUT_DIR}/selected.csv"

# =========================
# Email 配置
# =========================
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
