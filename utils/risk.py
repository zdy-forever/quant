from main.config import RISK_PER_TRADE, STOP_LOSS_PCT, MAX_POSITIONS


def calculate_position_size(
        equity: float,
        entry_price: float,
        stop_loss_pct: float = STOP_LOSS_PCT,
        risk_per_trade: float = RISK_PER_TRADE,
) -> int:
    """
    根据固定风险比例计算仓位股数。

    思路：
    - 假设账户总权益为 equity
    - 单笔最多亏 risk_per_trade * equity
    - 每股最大亏损约为 entry_price * stop_loss_pct
    - 则可以买的股数 ≈ 总允许亏损 / 每股允许亏损

    Parameters
    ----------
    equity : float
        账户总权益
    entry_price : float
        计划入场价格
    stop_loss_pct : float
        止损百分比
    risk_per_trade : float
        单笔风险比例

    Returns
    -------
    int
        计划买入的股数
    """
    if equity <= 0 or entry_price <= 0 or stop_loss_pct <= 0 or risk_per_trade <= 0:
        return 0

    risk_amount = equity * risk_per_trade
    risk_per_share = entry_price * stop_loss_pct

    if risk_per_share <= 0:
        return 0

    qty = int(risk_amount / risk_per_share)
    return max(qty, 0)


def select_top_candidates(candidates_df, max_positions: int = MAX_POSITIONS):
    """
    从所有信号中选出前 max_positions 个候选股票。

    这里默认输入的 candidates_df 已经排好序了，
    所以直接取 signal=True 的前几个。
    """
    if candidates_df.empty:
        return candidates_df

    selected = candidates_df.loc[candidates_df["signal"]].copy()
    selected = selected.head(max_positions).reset_index(drop=True)
    return selected