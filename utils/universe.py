"""
旧版股票池模块。

当前实现很简单：直接返回配置里的观察列表。
以后如果你想升级成从文件、数据库、指数成分或筛选器自动生成股票池，
优先改这里。
"""

from main.config import WATCHLIST


def get_universe() -> list[str]:
    """
    返回当前使用的股票池。

    现在先直接返回 config.py 中手动写死的 WATCHLIST。
    后面你可以把这里升级成：
    1. 从 CSV 读取股票池
    2. 按成交额筛选
    3. 按行业筛选
    4. 按指数成分股筛选
    """
    return WATCHLIST.copy()
