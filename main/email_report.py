"""
邮件报告模块。

它负责把扫描结果和交易结果整理成 HTML 邮件并发送出去。
如果你之后想把结果改成更好看的格式，或者改成企业邮箱 / Telegram / 钉钉通知，
这个文件就是主要入口。
"""

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd

from main.config import (
    EMAIL_SENDER,
    EMAIL_PASSWORD,
    EMAIL_RECEIVER,
    SMTP_HOST,
    SMTP_PORT,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
)


def format_price(value) -> str:
    """
    把价格格式化成两位小数的字符串。
    如果值为空或非法，则返回 '-'
    """
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


def build_buy_range(close_price: float) -> tuple[float, float]:
    """
    生成一个“适合买入区间”。

    这里先给你一个简单版本：
    - 下沿：当前价格的 99%
    - 上沿：当前价格的 101%

    这不是唯一标准，只是给报告里一个参考买入区间。
    后面你可以自己改成：
    - breakout 附近 ±0.5%
    - 支撑位到阻力位
    - ATR 区间
    - MA 回踩区间

    Returns
    -------
    tuple[float, float]
        (buy_lower, buy_upper)
    """
    buy_lower = close_price * 0.99
    buy_upper = close_price * 1.01
    return buy_lower, buy_upper


def build_scan_report_html(signal_df: pd.DataFrame, selected_df: pd.DataFrame) -> str:
    """
    构造“扫描结果邮件”的 HTML 内容。

    邮件中会展示：
    - 所有扫描结果
    - 每只股票的建议买入区间
    - 止损价
    - 止盈价
    - 是否是候选股票

    Parameters
    ----------
    signal_df : pd.DataFrame
        main_scan.py 输出的全部信号表
    selected_df : pd.DataFrame
        main_scan.py 输出的入选候选表

    Returns
    -------
    str
        HTML 格式的邮件正文
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    selected_symbols = set()
    if selected_df is not None and not selected_df.empty:
        selected_symbols = set(selected_df["symbol"].astype(str).tolist())

    rows_html = []

    if signal_df is not None and not signal_df.empty:
        for _, row in signal_df.iterrows():
            symbol = str(row["symbol"])
            close_price = float(row["close"])
            buy_lower, buy_upper = build_buy_range(close_price)
            stop_price = close_price * (1 - STOP_LOSS_PCT)
            take_profit_price = close_price * (1 + TAKE_PROFIT_PCT)

            is_selected = "Yes" if symbol in selected_symbols else "No"
            signal_value = "Yes" if bool(row["signal"]) else "No"

            rows_html.append(
                f"""
                <tr>
                    <td>{symbol}</td>
                    <td>{signal_value}</td>
                    <td>{is_selected}</td>
                    <td>{format_price(close_price)}</td>
                    <td>{format_price(buy_lower)} - {format_price(buy_upper)}</td>
                    <td>{format_price(stop_price)}</td>
                    <td>{format_price(take_profit_price)}</td>
                    <td>{float(row["ret_5"]):.4f}</td>
                    <td>{float(row["ret_20"]):.4f}</td>
                    <td>{float(row["volume_ratio"]):.2f}</td>
                    <td>{float(row["rank_score"]):.4f}</td>
                </tr>
                """
            )
    else:
        rows_html.append(
            """
            <tr>
                <td colspan="11">No signal data available.</td>
            </tr>
            """
        )

    html = f"""
    <html>
    <body>
        <h2>Alpaca Scan Report</h2>
        <p><strong>Generated at:</strong> {now_str}</p>

        <p>
            This report shows each stock's current price, suggested buy range,
            stop loss, take profit, and whether it was selected as a candidate.
        </p>

        <table border="1" cellspacing="0" cellpadding="6">
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Signal</th>
                    <th>Selected</th>
                    <th>Close</th>
                    <th>Buy Range</th>
                    <th>Stop Loss</th>
                    <th>Take Profit</th>
                    <th>Ret 5</th>
                    <th>Ret 20</th>
                    <th>Vol Ratio</th>
                    <th>Rank Score</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows_html)}
            </tbody>
        </table>
    </body>
    </html>
    """

    return html


def build_trade_report_html(trade_results: list[dict]) -> str:
    """
    构造“交易执行结果邮件”的 HTML 内容。

    trade_results 中每个元素可以包含：
    - symbol
    - qty
    - entry_price
    - stop_price
    - take_profit_price
    - submitted
    - status
    - order_id
    - error

    Parameters
    ----------
    trade_results : list[dict]
        每只股票的交易执行结果

    Returns
    -------
    str
        HTML 格式邮件正文
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows_html = []

    if trade_results:
        for item in trade_results:
            rows_html.append(
                f"""
                <tr>
                    <td>{item.get('symbol', '-')}</td>
                    <td>{item.get('qty', '-')}</td>
                    <td>{format_price(item.get('entry_price'))}</td>
                    <td>{format_price(item.get('buy_lower'))} - {format_price(item.get('buy_upper'))}</td>
                    <td>{format_price(item.get('stop_price'))}</td>
                    <td>{format_price(item.get('take_profit_price'))}</td>
                    <td>{item.get('submitted', '-')}</td>
                    <td>{item.get('status', '-')}</td>
                    <td>{item.get('order_id', '-')}</td>
                    <td>{item.get('error', '-')}</td>
                </tr>
                """
            )
    else:
        rows_html.append(
            """
            <tr>
                <td colspan="10">No trade results available.</td>
            </tr>
            """
        )

    html = f"""
    <html>
    <body>
        <h2>Alpaca Trade Execution Report</h2>
        <p><strong>Generated at:</strong> {now_str}</p>

        <p>
            This report shows each trade candidate's suggested buy range,
            stop loss, take profit, and API submission result.
        </p>

        <table border="1" cellspacing="0" cellpadding="6">
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Qty</th>
                    <th>Entry</th>
                    <th>Buy Range</th>
                    <th>Stop Loss</th>
                    <th>Take Profit</th>
                    <th>Submitted</th>
                    <th>Status</th>
                    <th>Order ID</th>
                    <th>Error</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows_html)}
            </tbody>
        </table>
    </body>
    </html>
    """

    return html


def send_email(subject: str, html_body: str) -> None:
    """
    发送 HTML 邮件（支持多个收件人）
    """
    if not EMAIL_SENDER or not EMAIL_PASSWORD or not EMAIL_RECEIVER:
        raise ValueError(
            "Missing email settings. Please set EMAIL_SENDER, "
            "EMAIL_PASSWORD and EMAIL_RECEIVER in .env"
        )

    # =========================
    # 关键：把字符串拆成列表
    # =========================
    # "a@xx.com,b@xx.com" -> ["a@xx.com", "b@xx.com"]
    receivers = [
        email.strip()
        for email in EMAIL_RECEIVER.split(",")
        if email.strip()
    ]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER

    # 显示在邮件里的 To（字符串形式）
    msg["To"] = ", ".join(receivers)

    html_part = MIMEText(html_body, "html")
    msg.attach(html_part)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)

        # ⚠️ 这里必须传 list
        server.sendmail(
            EMAIL_SENDER,
            receivers,   # 不是字符串，是 list
            msg.as_string()
        )


def send_scan_report(signal_df: pd.DataFrame, selected_df: pd.DataFrame) -> None:
    """
    发送扫描结果邮件。
    """
    subject = f"Alpaca Scan Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    html_body = build_scan_report_html(signal_df, selected_df)
    send_email(subject, html_body)


def send_trade_report(trade_results: list[dict]) -> None:
    """
    发送交易执行结果邮件。
    """
    subject = f"Alpaca Trade Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    html_body = build_trade_report_html(trade_results)
    send_email(subject, html_body)
