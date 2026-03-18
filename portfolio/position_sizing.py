# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal

import numpy as np
import pandas as pd


PositionMethod = Literal["equal", "vol_target", "risk_parity", "kelly"]


@dataclass(frozen=True)
class PositionConfig:
    method: PositionMethod = "vol_target"
    max_positions: int = 5
    target_vol_annual: float = 0.15
    vol_lookback: int = 20
    kelly_fraction: float = 0.25


def _annualize_vol(daily_vol: float, trading_days: int = 252) -> float:
    return float(daily_vol) * np.sqrt(trading_days)


def compute_weights_from_signals(
    ohlcv: pd.DataFrame,
    signals: pd.Series,
    cfg: PositionConfig,
    asof_ts: pd.Timestamp,
) -> Dict[str, float]:
    """根据信号和历史波动估计目标权重。"""

    if signals.empty:
        return {}

    asof_ts = pd.to_datetime(asof_ts, utc=True)
    try:
        day_sig = signals.xs(asof_ts, level="timestamp").rename("signal").reset_index()
    except KeyError:
        return {}

    day_sig = day_sig[day_sig["signal"] != 0].copy()
    if day_sig.empty:
        return {}

    day_sig = day_sig.head(cfg.max_positions)
    symbols = day_sig["symbol"].astype(str).tolist()

    if cfg.method == "equal":
        weight = 1.0 / len(symbols)
        return {symbol: weight for symbol in symbols}

    df = ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["symbol", "timestamp"])
    df = df[df["timestamp"] <= asof_ts]

    vols: Dict[str, float] = {}
    for symbol in symbols:
        sub = df[df["symbol"] == symbol].tail(cfg.vol_lookback + 5)
        if sub.shape[0] < max(5, cfg.vol_lookback):
            continue
        rets = sub["close"].pct_change().dropna()
        if rets.empty:
            continue
        vols[symbol] = float(rets.tail(cfg.vol_lookback).std(ddof=0))

    symbols = [symbol for symbol in symbols if symbol in vols and vols[symbol] > 0]
    if not symbols:
        return {}

    if cfg.method == "vol_target":
        inv_vol = np.array([1.0 / vols[symbol] for symbol in symbols], dtype=float)
        raw_w = inv_vol / inv_vol.sum()
        port_daily_vol = float(
            np.sqrt(np.sum((raw_w ** 2) * np.array([vols[symbol] ** 2 for symbol in symbols])))
        )
        port_ann_vol = _annualize_vol(port_daily_vol)
        scale = 1.0 if port_ann_vol <= 1e-12 else min(1.0, cfg.target_vol_annual / port_ann_vol)
        weights = raw_w * scale
        return {symbol: float(weight) for symbol, weight in zip(symbols, weights)}

    if cfg.method == "risk_parity":
        price = (
            df[df["symbol"].isin(symbols)]
            .pivot(index="timestamp", columns="symbol", values="close")
            .sort_index()
            .tail(cfg.vol_lookback + 1)
        )
        rets = price.pct_change().dropna()
        if rets.empty:
            return {}

        cov = rets.cov().values
        n_assets = cov.shape[0]
        weights = np.ones(n_assets) / n_assets

        def _risk_contrib(w: np.ndarray) -> np.ndarray:
            port_var = float(w.T @ cov @ w)
            if port_var <= 0:
                return np.zeros_like(w)
            marginal = cov @ w
            return w * marginal / np.sqrt(port_var)

        for _ in range(200):
            contrib = _risk_contrib(weights)
            total = contrib.sum()
            if total <= 0:
                break
            target = total / n_assets
            weights = weights * (target / (contrib + 1e-12))
            weights = np.clip(weights, 1e-6, None)
            weights = weights / weights.sum()

        return {symbol: float(weight) for symbol, weight in zip(symbols, weights)}

    if cfg.method == "kelly":
        price = (
            df[df["symbol"].isin(symbols)]
            .pivot(index="timestamp", columns="symbol", values="close")
            .sort_index()
            .tail(cfg.vol_lookback + 1)
        )
        rets = price.pct_change().dropna()
        if rets.empty:
            return {}

        mu = rets.mean().values
        cov = rets.cov().values
        raw = np.maximum(np.linalg.pinv(cov) @ mu, 0.0)
        if raw.sum() <= 0:
            return {}

        weights = raw / raw.sum()
        weights = weights * float(cfg.kelly_fraction)
        return {symbol: float(weight) for symbol, weight in zip(symbols, weights)}

    raise ValueError(f"未知仓位方法: {cfg.method}")
