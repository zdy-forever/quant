import os

from main.config import LOOKBACK_BARS, OUTPUT_DIR, SIGNALS_CSV, SELECTED_CSV
from main.email_report import send_scan_report
from utils.universe import get_universe
from utils.data_loader import get_daily_bars
from utils.factors import add_factors
from utils.signals import generate_signals
from utils.risk import select_top_candidates


def main():
    """
    扫描流程主程序：
    1. 获取股票池
    2. 拉日线数据
    3. 计算因子
    4. 生成信号
    5. 选出优先候选股票
    6. 保存结果到 CSV
    7. 发送扫描邮件
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    symbols = get_universe()
    bars = get_daily_bars(symbols, LOOKBACK_BARS)

    if bars.empty:
        print("No market data returned.")
        return

    factor_df = add_factors(bars)
    signal_df = generate_signals(factor_df)

    if signal_df.empty:
        print("No valid signals generated.")
        return

    selected_df = select_top_candidates(signal_df)

    signal_df.to_csv(SIGNALS_CSV, index=False)
    selected_df.to_csv(SELECTED_CSV, index=False)

    print("\n=== All Signals ===")
    print(signal_df.to_string(index=False))

    print("\n=== Selected Candidates ===")
    if selected_df.empty:
        print("No selected candidates.")
    else:
        print(selected_df.to_string(index=False))

    print(f"\nSaved: {SIGNALS_CSV}")
    print(f"Saved: {SELECTED_CSV}")

    # 发送邮件报告
    send_scan_report(signal_df, selected_df)
    print("Scan report email sent.")


if __name__ == "__main__":
    main()
