# -*- coding: utf-8 -*-
"""
训练与冻结参数模块。

这个文件只服务于“研究阶段”：
- 遍历参数网格
- 用训练区间做简单回测
- 选出表现最好的参数
- 把参数写入 `artifacts/frozen_params/`

对量化新手来说，最重要的原则是：
训练可以调参数，但训练结束后要冻结，不能把测试集看完再回头改。
"""
from __future__ import annotations

import hashlib
import itertools
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from strategy.mean_reversion.mean_reversion import MeanReversionBollingerStrategy
from strategy.trend.trend import TrendBreakoutStrategy


ART_DIR = "artifacts"
FROZEN_DIR = os.path.join(ART_DIR, "frozen_params")
REPORT_DIR = os.path.join(ART_DIR, "reports")
MANIFEST_FILE = os.path.join(FROZEN_DIR, "MANIFEST.json")


@dataclass(frozen=True)
class TrainSpec:
    symbols: List[str]
    start: str
    end: str
    objective: str = "sharpe"
    bars_timeframe: str = "1D"
    overwrite_frozen: bool = False


def _ensure_dirs() -> None:
    os.makedirs(FROZEN_DIR, exist_ok=True)
    os.makedirs(REPORT_DIR, exist_ok=True)


def _to_utc_ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def _grid_iter(grid: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    keys = list(grid.keys())
    values = [list(grid[key]) for key in keys]
    return [{key: value for key, value in zip(keys, combo)} for combo in itertools.product(*values)]


def _simple_backtest(
    ohlcv: pd.DataFrame,
    signals: pd.Series,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    cost_bps: float = 5.0,
) -> pd.Series:
    """
    极简回测：
    - 信号在 t 收盘产生
    - 在 t+1 开盘建仓，并近似用 next open -> next close 收益
    """

    df = ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["timestamp", "symbol"])
    df = df[(df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)].copy()

    open_px = df.pivot(index="timestamp", columns="symbol", values="open").sort_index()
    close_px = df.pivot(index="timestamp", columns="symbol", values="close").sort_index()
    if open_px.empty or close_px.empty:
        return pd.Series(dtype=float)

    sig_df = signals.rename("signal").reset_index()
    sig_df["timestamp"] = pd.to_datetime(sig_df["timestamp"], utc=True)

    day_positions = sig_df[sig_df["signal"] != 0].groupby("timestamp")["symbol"].apply(list)
    day_positions = day_positions.reindex(open_px.index).shift(1)
    day_positions = day_positions.apply(lambda value: value if isinstance(value, list) else [])

    oc_ret = (close_px / open_px - 1.0).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    cost_ratio = cost_bps / 10_000.0

    equity = []
    current_equity = 1.0
    previous_set: set[str] = set()

    for ts in open_px.index:
        current_list = [symbol for symbol in day_positions.loc[ts] if symbol in oc_ret.columns]
        current_set = set(current_list)
        if not current_list:
            equity.append(current_equity)
            previous_set = current_set
            continue

        day_ret = float(oc_ret.loc[ts, current_list].mean())
        universe = current_set | previous_set
        turnover = 0.0 if not universe else len(current_set.symmetric_difference(previous_set)) / len(universe)
        current_equity = current_equity * (1.0 + day_ret - turnover * cost_ratio)
        equity.append(current_equity)
        previous_set = current_set

    return pd.Series(equity, index=open_px.index, name="equity")


def _metrics(equity: pd.Series) -> Dict[str, float]:
    if equity.empty:
        return {"sharpe": np.nan, "cagr": np.nan, "max_dd": np.nan, "calmar": np.nan}

    returns = equity.pct_change().dropna()
    if returns.empty:
        return {"sharpe": np.nan, "cagr": np.nan, "max_dd": np.nan, "calmar": np.nan}

    sharpe = float(returns.mean() / (returns.std(ddof=0) + 1e-12) * np.sqrt(252.0))
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0)
    peak = equity.cummax()
    max_dd = float((equity / peak - 1.0).min())
    calmar = float(cagr / (abs(max_dd) + 1e-12))
    return {"sharpe": sharpe, "cagr": cagr, "max_dd": max_dd, "calmar": calmar}


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        digest.update(handle.read())
    return digest.hexdigest()


def _update_manifest() -> None:
    strategies: Dict[str, Dict[str, str]] = {}
    for filename in sorted(os.listdir(FROZEN_DIR)):
        if not filename.endswith(".json") or filename == os.path.basename(MANIFEST_FILE):
            continue
        path = os.path.join(FROZEN_DIR, filename)
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        name = str(payload.get("strategy") or os.path.splitext(filename)[0])
        strategies[name] = {
            "file": path,
            "sha256": _file_sha256(path),
            "frozen_at_utc": str(payload.get("frozen_at_utc", "")),
        }

    payload = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "strategies": strategies,
    }
    with open(MANIFEST_FILE, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def freeze_params(
    strategy_name: str,
    params: Dict[str, Any],
    train_spec: TrainSpec,
    best_metrics: Dict[str, float],
) -> str:
    """仅允许在 train 阶段写入 frozen 参数文件。"""

    _ensure_dirs()
    path = os.path.join(FROZEN_DIR, f"{strategy_name}.json")

    if (not train_spec.overwrite_frozen) and os.path.exists(path):
        raise FileExistsError(
            f"冻结参数已存在且不允许覆盖：{path}\n"
            "如需覆盖，请显式设置 overwrite_frozen=True。"
        )

    payload = {
        "strategy": strategy_name,
        "params": params,
        "train_spec": asdict(train_spec),
        "best_metrics": best_metrics,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "note": "OOS/test 阶段严禁修改该文件；如策略失效，请整体重做。",
    }

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    _update_manifest()
    return path


def train_one_strategy(
    ohlcv: pd.DataFrame,
    train_spec: TrainSpec,
    strategy,
) -> Tuple[Dict[str, Any], Dict[str, float]]:
    start_ts = _to_utc_ts(train_spec.start)
    end_ts = _to_utc_ts(train_spec.end)

    grid = _grid_iter({key: list(value) for key, value in strategy.param_grid().items()})
    best_params = None
    best_metrics = None
    best_score = -1e18

    for partial in grid:
        params = strategy.default_params()
        params.update(partial)

        result = strategy.generate(ohlcv, params)
        equity = _simple_backtest(ohlcv, result.signals, start_ts, end_ts, cost_bps=5.0)
        metrics = _metrics(equity)

        if train_spec.objective == "sharpe":
            score = metrics["sharpe"]
        elif train_spec.objective == "cagr":
            score = metrics["cagr"]
        else:
            score = metrics["calmar"]

        if np.isnan(score):
            continue
        if score > best_score:
            best_score = score
            best_params = params
            best_metrics = metrics

    if best_params is None or best_metrics is None:
        raise RuntimeError(f"训练失败：{strategy.name} 无可用参数组合")

    return best_params, best_metrics


def train(
    ohlcv: pd.DataFrame,
    train_spec: TrainSpec,
    strategies: List[str],
) -> Dict[str, Any]:
    """训练阶段允许参数搜索，并在结束后冻结参数。"""

    _ensure_dirs()

    name_to_strategy = {
        "trend": TrendBreakoutStrategy(),
        "mean_reversion": MeanReversionBollingerStrategy(),
    }

    selected = []
    for name in strategies:
        if name not in name_to_strategy:
            raise ValueError(f"未知策略: {name}")
        selected.append(name_to_strategy[name])

    summary = {"train_spec": asdict(train_spec), "results": {}}
    for strategy in selected:
        best_params, best_metrics = train_one_strategy(ohlcv, train_spec, strategy)
        frozen_path = freeze_params(strategy.name, best_params, train_spec, best_metrics)
        summary["results"][strategy.name] = {
            "best_params": best_params,
            "best_metrics": best_metrics,
            "frozen_path": frozen_path,
        }

    report_path = os.path.join(
        REPORT_DIR,
        f"train_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)

    return summary
