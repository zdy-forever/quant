"""
交易过滤模块。

这个文件不负责决定“哪个股票分数更高”，
它只负责在真正下单前做更严格的安全筛选，比如：
- 波动是不是过大
- 放量是不是过于极端
- 收盘位置是不是太差
- 离均线是不是太远
- 流动性是不是足够

你可以把它理解成“因子选股之后的最后一道风控筛子”。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TradeFilterConfig:
    min_close_location_1: float = 0.05
    max_true_range_pct_1: float = 0.09
    max_volume_surprise_5: float = 4.0
    max_abs_ma_distance_20: float = 0.15
    min_liquidity_20: float = 16.0


def build_trade_filter_frame(raw_panel: pd.DataFrame, cfg: TradeFilterConfig) -> pd.DataFrame:
    if raw_panel.empty:
        return pd.DataFrame(columns=["timestamp", "symbol", "trade_filter_pass"])

    panel = raw_panel.copy()
    mask = pd.Series(True, index=panel.index, dtype=bool)

    if "close_location_1" in panel.columns:
        mask &= panel["close_location_1"].ge(cfg.min_close_location_1).fillna(False)
    if "true_range_pct_1" in panel.columns:
        mask &= panel["true_range_pct_1"].le(cfg.max_true_range_pct_1).fillna(False)
    if "volume_surprise_5" in panel.columns:
        mask &= panel["volume_surprise_5"].le(cfg.max_volume_surprise_5).fillna(False)
    if "ma_distance_20" in panel.columns:
        mask &= panel["ma_distance_20"].abs().le(cfg.max_abs_ma_distance_20).fillna(False)
    if "liquidity_20" in panel.columns:
        mask &= panel["liquidity_20"].ge(cfg.min_liquidity_20).fillna(False)

    out = panel[["timestamp", "symbol"]].copy()
    out["trade_filter_pass"] = mask.astype(bool)
    return out


def apply_trade_filters(
    score_frame: pd.DataFrame,
    raw_panel: pd.DataFrame,
    cfg: TradeFilterConfig,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if score_frame.empty:
        return score_frame.copy(), {"config": asdict(cfg), "row_count_before": 0, "row_count_after": 0}

    filter_frame = build_trade_filter_frame(raw_panel, cfg)
    merged = score_frame.merge(filter_frame, on=["timestamp", "symbol"], how="left")
    merged["trade_filter_pass"] = merged["trade_filter_pass"].fillna(False)
    filtered = merged[merged["trade_filter_pass"]].copy()

    before = int(score_frame.shape[0])
    after = int(filtered.shape[0])
    grouped = merged.groupby("timestamp", sort=True)["trade_filter_pass"]
    pass_counts = grouped.sum() if grouped.ngroups else pd.Series(dtype=float)
    total_counts = grouped.size() if grouped.ngroups else pd.Series(dtype=float)
    block_counts = total_counts.sub(pass_counts, fill_value=0.0)
    diagnostics = {
        "config": asdict(cfg),
        "row_count_before": before,
        "row_count_after": after,
        "blocked_ratio": float(1.0 - after / before) if before else np.nan,
        "avg_daily_pass_count": float(pass_counts.mean()) if not pass_counts.empty else np.nan,
        "avg_daily_block_count": float(block_counts.mean()) if not block_counts.empty else np.nan,
    }
    return filtered.drop(columns=["trade_filter_pass"]), diagnostics
