"""
旧版交易执行主程序。

它读取扫描结果 CSV，然后：
- 获取账户权益
- 计算每只股票下多少股
- 生成 bracket order
- 在 dry run 或真实提交之间切换
- 最后把结果发邮件

如果你想理解“信号如何变成订单”，先读这个文件最直观。
"""

import os
from typing import cast

import pandas as pd

from main.clients import trading_client
from main.config import SELECTED_CSV, DRY_RUN, STOP_LOSS_PCT, TAKE_PROFIT_PCT
from main.email_report import send_trade_report, build_buy_range
from utils.risk import calculate_position_size
from utils.orders import submit_bracket_order


def get_account_equity() -> float:
    """
    获取当前 Alpaca 模拟账户总权益。
    """
    account = trading_client.get_account()
    return float(account.equity)


def main():
    """
    交易执行主程序：
    1. 读取扫描阶段筛出来的候选股票
    2. 获取账户权益
    3. 计算每只股票的仓位大小
    4. 打印订单计划
    5. 如果 DRY_RUN=False，则提交模拟订单
    6. 把执行结果发邮件
    """
    if not os.path.exists(SELECTED_CSV):
        print(f"Missing file: {SELECTED_CSV}")
        print("Run main_scan.py first.")
        return

    df = cast(pd.DataFrame, pd.read_csv(str(SELECTED_CSV)))

    if df.empty:
        print("No trade candidates.")
        return

    equity = get_account_equity()
    print(f"Account equity: {equity:.2f}")

    trade_results: list[dict] = []

    for _, row in df.iterrows():
        symbol = row["symbol"]
        entry_price = float(row["close"])

        qty = calculate_position_size(
            equity=equity,
            entry_price=entry_price,
        )

        if qty <= 0:
            print(f"Skip {symbol}: qty <= 0")
            trade_results.append(
                {
                    "symbol": symbol,
                    "qty": 0,
                    "entry_price": entry_price,
                    "buy_lower": build_buy_range(entry_price)[0],
                    "buy_upper": build_buy_range(entry_price)[1],
                    "stop_price": entry_price * (1 - STOP_LOSS_PCT),
                    "take_profit_price": entry_price * (1 + TAKE_PROFIT_PCT),
                    "submitted": "No",
                    "status": "Skipped",
                    "order_id": "-",
                    "error": "qty <= 0",
                }
            )
            continue

        buy_lower, buy_upper = build_buy_range(entry_price)
        stop_price = entry_price * (1 - STOP_LOSS_PCT)
        take_profit_price = entry_price * (1 + TAKE_PROFIT_PCT)

        print(
            f"{symbol} | qty={qty} | entry={entry_price:.2f} "
            f"| buy_range={buy_lower:.2f}-{buy_upper:.2f} "
            f"| stop={stop_price:.2f} "
            f"| take_profit={take_profit_price:.2f}"
        )

        if DRY_RUN:
            print(f"[DRY RUN] order not submitted for {symbol}")
            trade_results.append(
                {
                    "symbol": symbol,
                    "qty": qty,
                    "entry_price": entry_price,
                    "buy_lower": buy_lower,
                    "buy_upper": buy_upper,
                    "stop_price": stop_price,
                    "take_profit_price": take_profit_price,
                    "submitted": "No",
                    "status": "Dry Run",
                    "order_id": "-",
                    "error": "-",
                }
            )
        else:
            try:
                result = submit_bracket_order(symbol, qty, entry_price)
                print(result)

                trade_results.append(
                    {
                        "symbol": symbol,
                        "qty": qty,
                        "entry_price": entry_price,
                        "buy_lower": buy_lower,
                        "buy_upper": buy_upper,
                        "stop_price": stop_price,
                        "take_profit_price": take_profit_price,
                        "submitted": "Yes",
                        "status": getattr(result, "status", "Submitted"),
                        "order_id": getattr(result, "id", "-"),
                        "error": "-",
                    }
                )
            except Exception as e:
                print(f"Order failed for {symbol}: {e}")

                trade_results.append(
                    {
                        "symbol": symbol,
                        "qty": qty,
                        "entry_price": entry_price,
                        "buy_lower": buy_lower,
                        "buy_upper": buy_upper,
                        "stop_price": stop_price,
                        "take_profit_price": take_profit_price,
                        "submitted": "No",
                        "status": "Failed",
                        "order_id": "-",
                        "error": str(e),
                    }
                )

    send_trade_report(trade_results)
    print("Trade report email sent.")


if __name__ == "__main__":
    main()
