# 模块化生产级 Python 量化交易项目架构与开发生命周期设计

## 执行摘要

本报告给出一套可直接落地到你私有仓库的“生产级、模块化”Python量化交易项目架构，并严格贯彻你指定的开发生命周期：**开发（仅用训练集）→ 冻结参数 → 不可变的样本外测试（OOS）→ Walk-forward 验证 → 部署 → 仅允许调整状态识别/仓位/风控；若失效则整体重做**。这个流程的价值在于：把最危险的“回测调参—看测试集—再调参”的闭环切断，降低**选择偏差、多重检验与回测过拟合**的概率（PBO/DSR 这类研究专门讨论了这一点）。citeturn3search2turn3search6turn0search6

对你现有私有仓库 `zdy-forever/quant` 的连接审计显示：目前代码已经具备 **Alpaca 模拟盘下单（TradingClient paper=True）、历史行情拉取（StockHistoricalDataClient）、括号单（bracket order）以及扫描→交易→邮件报告**的端到端雏形，但缺少系统化的**回测/训练/样本外测试/Walk-forward**流水线、参数冻结工件与防数据泄露的工程护栏（CI、单元测试、只读OOS约束等）。fileciteturn13file0L1-L1 fileciteturn15file0L1-L1 fileciteturn20file0L1-L1 fileciteturn11file0L1-L1 fileciteturn10file0L1-L1

本报告交付以下内容（均为可复制模板）：  
(1) 推荐目录结构（含 `strategy/` 顶层目录、每策略子目录、`backtest/` 训练/测试/WF 管线）；  
(2) 逐文件的**精简但可运行**代码模板（你要求的 12 个文件全部覆盖）；  
(3) 参数冻结工作流与 CI/Checklist（硬性防“看完测试集再调参”）；  
(4) 单元测试示例与本地 Alpaca Paper 部署运行方式；  
(5) 默认超参、指标体系、Walk-forward 窗口方案；  
(6) 常见坑与缓解（多重检验、状态误判、延迟、滑点/冲击成本）；  
(7) 生命周期 Mermaid 流程图 + 2–4 种仓位方法对比表。  

## 现有仓库审计与差距分析

### 现状概览

你当前仓库已经实现一个“**每日扫描 → 生成候选 → 下单 → 邮件报告**”的执行路径：

- 扫描入口：`main/main_scan.py` 组织了股票池、拉日线、算因子、生成信号、选 Top 候选、输出 CSV、发邮件。fileciteturn11file0L1-L1  
- 交易入口：`main/main_trade.py` 读取候选 CSV，获取账户权益，按固定风险计算股数，DRY_RUN 控制是否提交括号单，发送交易结果邮件。fileciteturn10file0L1-L1  
- Alpaca 客户端：`main/clients.py` 使用 `TradingClient(..., paper=True)` 与 `StockHistoricalDataClient`。fileciteturn13file0L1-L1  
- 环境变量：`main/config.py` 用 `.env` 注入 Paper key；并包含策略阈值（breakout 20、volume 20、risk_per_trade 1%、止损 5%、止盈 10% 等）。fileciteturn12file0L1-L1  
- 因子与信号：`utils/factors.py`/`utils/signals.py` 实现 breakout+量能+动量过滤，并用 `shift(1)` 避免把“今天的最高价/均量”泄露到决策中（这是正确的“反前视偏差”写法）。fileciteturn16file0L1-L1 fileciteturn17file0L1-L1  
- 下单与风控：`utils/orders.py` 构造 `OrderClass.BRACKET` 的括号单，并配置 stop_loss/take_profit。fileciteturn20file0L1-L1  
- 仓位：`utils/risk.py` 用“账户权益×单笔风险 / 每股风险（入场价×止损比例）”计算股数。fileciteturn19file0L1-L1  

上述设计与 Alpaca 官方 SDK 的关键用法一致：Paper Trading 通过 `paper=True` 启用模拟盘；括号单通过 `order_class` + `take_profit` + `stop_loss` 声明。citeturn0search9turn4search0turn4search6

### 主要缺口

1) **缺少可重复的训练/测试/WF 回测管线**：当前实现偏“实时扫描与下单”，没有统一的回测引擎来评估策略在历史上的收益、回撤、换手与成本；也没有 OOS 固化的防线。fileciteturn11file0L1-L1 fileciteturn10file0L1-L1  

2) **缺少“冻结参数”概念与工件**：`main/config.py` 里参数随时可改，一旦你在看过近期表现后回头改 config，就会发生典型的数据泄露/选择偏差。fileciteturn12file0L1-L1  

3) **缺少工程护栏（CI/测试/只读OOS）**：没有单元测试确定 split 的时间顺序、信号是否前视、OOS 脚本是否写回参数等；没有 CI 阻断“在 test 阶段修改 frozen 参数”。（仓库中未检索到相关结构与文件；视为未指定/缺失。）

4) **模块边界不清晰（import 路径不一致）**：例如 `main/main_trade.py` 使用 `from clients import ...` 与 `from config import ...`，而 `utils/*` 又用 `from main.clients import ...`；这会导致“从不同工作目录运行时行为不同”的隐患。fileciteturn10file0L1-L1 fileciteturn15file0L1-L1  

本报告给出的新结构会在**不否定你现有 Alpaca 执行链路**的前提下，把“研究/验证/部署”拆为清晰层次：策略层（strategy）、状态层（regime）、组合层（portfolio）、风控层（risk）、回测层（backtest）与统一入口（main.py）。

## 生命周期设计与研究依据

### 为什么必须“冻结参数 + 不可变 OOS + Walk-forward”

投资回测环境里，**多重检验 + 选择偏差**特别容易让“看起来很美的策略”出现。你只要做了大量尝试（多策略、多参数、多过滤条件），就很可能从噪声里“挑中”一个历史表现异常好的组合。研究给出了定量化描述：  
- **PBO（Probability of Backtest Overfitting）**强调传统 hold-out 在投资回测里可能不可靠，并提出 CSCV 来估计策略被过拟合的概率。citeturn3search2turn0search6  
- **DSR（Deflated Sharpe Ratio）**将“多重检验/选择偏差、非正态收益、样本长度”等因素纳入，对 Sharpe 的显著性做“去膨胀”。citeturn3search6turn3search0turn3search8  

Walk-forward（滚动窗口验证）本质上是时间序列的正确切分方式：训练集永远在测试集之前，避免“用未来训练、用过去评估”。这与 `TimeSeriesSplit` 的核心警告一致：时间序列不应 shuffle，且每折测试索引必须递增。citeturn2search1turn5search0turn5search1

### 生命周期 Mermaid 流程图

```mermaid
flowchart TD
  A[开发/训练 Develop: 只用Train区间] --> B[冻结参数 Freeze: 写入frozen_params工件]
  B --> C[样本外测试 Test(OOS): 只读参数 + 不许再调参]
  C --> D[Walk-forward验证: 多窗口稳定性评估(仍只读参数)]
  D --> E[部署 Deploy: 纸交易/模拟盘]
  E --> F[运行期只允许调: Regime/仓位/风控]
  F -->|失效/漂移| G[整体重做 Redevelop: 重新划分数据与研究]
```

## 推荐项目目录结构

下面的结构满足你要求的：顶层 `strategy/` 且每个策略独立子目录；`backtest/` 内实现 train/test/walk-forward。并额外加入 `artifacts/`（冻结参数与报告）、`tests/`（护栏）、`config/`（运行期可调项）以实现“生产级可治理”。

> 迁移建议：你当前 `main/` 与 `utils/` 可以先保留（作为 legacy 或执行层参考），本报告提供的文件可直接新增到仓库根目录；待稳定后再把现有逻辑逐步收拢进新结构。现有 breakout 逻辑可以作为 `strategy/trend/` 的第一版。fileciteturn17file0L1-L1  

建议结构（可直接复制）：

```text
quant/
  main.py

  strategy/
    __init__.py
    base_strategy.py
    trend/
      __init__.py
      trend.py
    mean_reversion/
      __init__.py
      mean_reversion.py

  regime/
    __init__.py
    detection.py

  portfolio/
    __init__.py
    position_sizing.py

  risk/
    __init__.py
    management.py

  backtest/
    __init__.py
    train.py
    test.py
    walk_forward.py

  config/
    runtime.yaml              # 运行期允许改：regime阈值/仓位目标/风控
    symbols.txt               # 交易标的列表（可选）

  artifacts/
    frozen_params/
      trend.json              # 冻结后的策略参数（只读）
      mean_reversion.json
      MANIFEST.json           # 冻结参数清单+hash（用于CI/防泄露）
    reports/
      train_*.json
      test_*.json
      walk_forward_*.json

  tests/
    test_splits.py
    test_freeze_manifest.py
    test_no_lookahead.py

  requirements.txt
  README.md
```

你仓库现有关键文件与功能映射（便于理解如何融合）：  
- `main/clients.py` ≈ 新架构里“broker/data 客户端的底层依赖”；本报告在 `main.py` 里直接按 Alpaca 官方文档调用（paper=True）。fileciteturn13file0L1-L1 citeturn0search9  
- `utils/factors.py` + `utils/signals.py` ≈ 新架构里 `strategy/trend/trend.py` 的核心。fileciteturn16file0L1-L1 fileciteturn17file0L1-L1  
- `utils/risk.py` ≈ 新架构里 `portfolio/position_sizing.py` + `risk/management.py` 的一部分。fileciteturn19file0L1-L1  
- `utils/orders.py` ≈ 新架构里 `main.py deploy` 下单实现（括号单）。fileciteturn20file0L1-L1 citeturn4search0turn4search6  

## 可复制的代码模板

下面按你要求逐文件给出**精简模板**（可运行、注释中文、包含参数冻结与防泄露示例）。为减少耦合，这套模板以“日线多标的、做多为主”的最小可用系统为边界；你可在此基础上扩展分钟级、卖空、期权等。

> 重要约定：  
> - OHLCV 数据统一为 long-format：`timestamp, symbol, open, high, low, close, volume`。  
> - 回测默认“信号在 t 产生，t+1 open 成交”（避免用同一根K线的 close 既生成信号又成交）。这种约定是防前视偏差的工程化做法之一。  
> - 冻结参数写入 `artifacts/frozen_params/*.json`，test/WF 阶段默认**禁止覆盖**。  
> - 运行期允许改的阈值写在 `config/runtime.yaml`（regime/仓位/风险），而不是 frozen_params。

### `strategy/base_strategy.py`

```python
# strategy/base_strategy.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

import pandas as pd


@dataclass(frozen=True)
class StrategyResult:
    """
    策略输出的统一格式：
    - signals: 每个(timestamp, symbol)一个信号值：1=做多, 0=空仓, -1=做空(模板保留但默认不用)
    - score:   可选的排序/打分（用于选Top-K或做组合）
    """
    signals: pd.Series
    score: Optional[pd.Series] = None


class BaseStrategy(ABC):
    """
    所有策略都必须实现的接口。
    设计原则：策略只负责“从数据到信号”，不负责下单、不负责组合权重、不负责风险裁剪。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """策略唯一名称（用于保存 frozen 参数文件名）"""

    @abstractmethod
    def default_params(self) -> Dict[str, Any]:
        """默认参数（可作为初始冻结参数）"""

    @abstractmethod
    def param_grid(self) -> Dict[str, Iterable[Any]]:
        """
        训练阶段用于搜索的参数网格。
        尽量少、尽量粗：参数越多越容易过拟合。
        """

    @abstractmethod
    def required_columns(self) -> set[str]:
        """策略需要的字段集合，例如 open/high/low/close/volume"""

    @abstractmethod
    def generate(self, ohlcv: pd.DataFrame, params: Dict[str, Any]) -> StrategyResult:
        """
        输入：包含 timestamp, symbol, OHLCV 列的 DataFrame（允许多标的、多日期）
        输出：StrategyResult（signals 为 pd.Series，index=(timestamp, symbol)）
        约束：不得使用未来数据（例如 rolling 要 shift(1) 或在成交约定上保证 t+1 执行）
        """

    def validate_input(self, ohlcv: pd.DataFrame) -> None:
        missing = self.required_columns() - set(ohlcv.columns)
        if missing:
            raise ValueError(f"[{self.name}] 缺少必要字段: {sorted(missing)}")

        if "timestamp" not in ohlcv.columns or "symbol" not in ohlcv.columns:
            raise ValueError(f"[{self.name}] 必须包含 timestamp 与 symbol 列")

        # timestamp 建议为 pandas datetime64[ns, UTC] 或可解析
        # 这里不强制转换，交给上游统一预处理
```

### `strategy/trend/trend.py`

```python
# strategy/trend/trend.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, Iterable

import numpy as np
import pandas as pd

from strategy.base_strategy import BaseStrategy, StrategyResult


class TrendBreakoutStrategy(BaseStrategy):
    """
    趋势策略（breakout + 量能 + 中期动量），与你仓库现有逻辑同源：
    - breakout: close > rolling(high, N).max().shift(1)
    - volume_ratio: volume / rolling(volume, N).mean().shift(1)
    - momentum: ret_M > 0
    这类 shift(1) 写法是经典的“防前视”手段之一（你现有 utils/factors.py 也这样做）。
    """

    @property
    def name(self) -> str:
        return "trend"

    def required_columns(self) -> set[str]:
        return {"timestamp", "symbol", "open", "high", "low", "close", "volume"}

    def default_params(self) -> Dict[str, Any]:
        return {
            "breakout_window": 20,
            "volume_window": 20,
            "momentum_window": 20,
            "min_price": 10.0,
            "min_avg_dollar_volume": 5_000_000.0,
            "min_volume_ratio": 1.5,
            "top_k": 5,
        }

    def param_grid(self) -> Dict[str, Iterable[Any]]:
        # 建议：少量参数、少量取值。参数网格越大，越容易“试出”假阳性。
        return {
            "breakout_window": [20, 55],
            "volume_window": [20],
            "momentum_window": [20, 60],
            "min_volume_ratio": [1.2, 1.5, 2.0],
            "top_k": [3, 5],
        }

    def generate(self, ohlcv: pd.DataFrame, params: Dict[str, Any]) -> StrategyResult:
        self.validate_input(ohlcv)

        df = ohlcv.copy()
        df = df.sort_values(["symbol", "timestamp"])

        bw = int(params["breakout_window"])
        vw = int(params["volume_window"])
        mw = int(params["momentum_window"])

        # 分组计算（每个标的独立）
        def _calc(g: pd.DataFrame) -> pd.DataFrame:
            g = g.copy()

            g["ret_m"] = g["close"].pct_change(mw)

            # 过去N日最高价（不含今天）：rolling(...).max().shift(1)
            g["high_breakout"] = g["high"].rolling(bw).max().shift(1)

            # 过去N日均量/均成交额（不含今天）
            g["avg_volume"] = g["volume"].rolling(vw).mean().shift(1)
            g["avg_dollar_volume"] = (g["close"] * g["volume"]).rolling(vw).mean().shift(1)

            g["volume_ratio"] = g["volume"] / g["avg_volume"]
            return g

        df = df.groupby("symbol", group_keys=False).apply(_calc)

        # 生成信号（只做多）
        min_price = float(params.get("min_price", 0.0))
        min_adv = float(params.get("min_avg_dollar_volume", 0.0))
        min_vr = float(params["min_volume_ratio"])

        cond = (
            (df["close"] >= min_price) &
            (df["avg_dollar_volume"] >= min_adv) &
            (df["close"] > df["high_breakout"]) &
            (df["volume_ratio"] >= min_vr) &
            (df["ret_m"] > 0)
        )

        # score 用于排序：动量 + 量能（示例，线性组合）
        score = 0.7 * df["ret_m"].fillna(0.0) + 0.3 * df["volume_ratio"].replace([np.inf, -np.inf], np.nan).fillna(0.0)

        # 只保留每天 top_k
        top_k = int(params["top_k"])

        # 建立 multi-index (timestamp, symbol)
        idx = pd.MultiIndex.from_frame(df[["timestamp", "symbol"]])
        raw_signal = pd.Series(cond.astype(int).values, index=idx, name="signal_raw")
        score_s = pd.Series(score.values, index=idx, name="score")

        # 对每个 timestamp，筛选 score 排名前 top_k 且 signal_raw=1
        def _topk_one_day(x: pd.DataFrame) -> pd.Series:
            x = x.sort_values("score", ascending=False)
            chosen = x[(x["signal_raw"] == 1)].head(top_k)
            out = pd.Series(0, index=x.index, dtype=int)
            out.loc[chosen.index] = 1
            return out

        tmp = pd.DataFrame({"signal_raw": raw_signal, "score": score_s})
        final_signal = tmp.groupby(level=0, group_keys=False).apply(_topk_one_day)
        final_signal.name = "signal"

        return StrategyResult(signals=final_signal.astype(int), score=score_s)
```

### `strategy/mean_reversion/mean_reversion.py`

```python
# strategy/mean_reversion/mean_reversion.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, Iterable

import numpy as np
import pandas as pd

from strategy.base_strategy import BaseStrategy, StrategyResult


class MeanReversionBollingerStrategy(BaseStrategy):
    """
    均值回归策略（Bollinger / z-score）：
    - (close - MA)/std < -entry_z 触发做多
    - z > -exit_z 退出（示例：回到均值附近）
    注意：均值回归在“震荡且波动不高”的状态更稳；高波动震荡往往应减仓或不交易（运行期由 regime/risk 控制）。
    """

    @property
    def name(self) -> str:
        return "mean_reversion"

    def required_columns(self) -> set[str]:
        return {"timestamp", "symbol", "open", "high", "low", "close", "volume"}

    def default_params(self) -> Dict[str, Any]:
        return {
            "lookback": 20,
            "entry_z": 2.0,
            "exit_z": 0.5,
            "min_price": 5.0,
            "top_k": 5,
        }

    def param_grid(self) -> Dict[str, Iterable[Any]]:
        return {
            "lookback": [10, 20, 40],
            "entry_z": [1.5, 2.0, 2.5],
            "exit_z": [0.0, 0.5, 1.0],
            "top_k": [3, 5],
        }

    def generate(self, ohlcv: pd.DataFrame, params: Dict[str, Any]) -> StrategyResult:
        self.validate_input(ohlcv)

        df = ohlcv.copy()
        df = df.sort_values(["symbol", "timestamp"])

        lb = int(params["lookback"])
        entry_z = float(params["entry_z"])
        exit_z = float(params["exit_z"])
        min_price = float(params.get("min_price", 0.0))
        top_k = int(params.get("top_k", 5))

        def _calc(g: pd.DataFrame) -> pd.DataFrame:
            g = g.copy()
            ma = g["close"].rolling(lb).mean()
            sd = g["close"].rolling(lb).std(ddof=0)
            g["z"] = (g["close"] - ma) / sd.replace(0.0, np.nan)
            return g

        df = df.groupby("symbol", group_keys=False).apply(_calc)

        # 入场条件：z < -entry_z 且价格过滤
        entry = (df["z"] < -entry_z) & (df["close"] >= min_price)

        # score：z 越低越“超卖”，优先级越高（取 -z）
        score = (-df["z"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)

        idx = pd.MultiIndex.from_frame(df[["timestamp", "symbol"]])
        entry_s = pd.Series(entry.astype(int).values, index=idx, name="entry")
        score_s = pd.Series(score.values, index=idx, name="score")

        # 这里给出“信号=1表示今天收盘形成入场信号，明天开盘买入”，退出/持仓由 backtest/risk 模块处理
        # 为了保持模板简单：在信号层不做“持仓状态机”，只给入场候选。
        tmp = pd.DataFrame({"entry": entry_s, "score": score_s})

        def _topk(x: pd.DataFrame) -> pd.Series:
            x = x.sort_values("score", ascending=False)
            chosen = x[x["entry"] == 1].head(top_k)
            out = pd.Series(0, index=x.index, dtype=int)
            out.loc[chosen.index] = 1
            return out

        final_signal = tmp.groupby(level=0, group_keys=False).apply(_topk)
        final_signal.name = "signal"

        return StrategyResult(signals=final_signal.astype(int), score=score_s)
```

### `regime/detection.py`

```python
# regime/detection.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd


class RegimeLabel(str, Enum):
    RANGE_LOW_VOL = "range_low_vol"       # 稳定震荡
    RANGE_HIGH_VOL = "range_high_vol"     # 波动震荡（通常应降仓/不交易）
    TREND_LOW_VOL = "trend_low_vol"       # 平静趋势
    TREND_HIGH_VOL = "trend_high_vol"     # 波动趋势


@dataclass(frozen=True)
class RegimeConfig:
    """
    运行期允许调整（不需要重新训练策略参数）
    """
    trend_fast: int = 20
    trend_slow: int = 100
    trend_threshold: float = 0.01       # |MA_fast/MA_slow - 1| 超过该阈值视为趋势
    vol_window: int = 20
    vol_threshold: float = 0.02         # 日收益率滚动波动率阈值（示例）
    symbol_for_regime: str = "SPY"      # 用作“大盘状态”的代表


def detect_regime(
    ohlcv: pd.DataFrame,
    cfg: RegimeConfig,
    asof_ts: Optional[pd.Timestamp] = None,
) -> RegimeLabel:
    """
    用“代表性标的（默认SPY）”粗粒度判断市场状态：
    - 趋势：MA_fast / MA_slow 偏离程度
    - 波动：rolling std(returns)
    注意：这是轻量级、可解释、易在生产落地的版本；更复杂的 Markov Switching/HMM 可后续替换。
    """
    df = ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["symbol", "timestamp"])

    mkt = df[df["symbol"] == cfg.symbol_for_regime][["timestamp", "close"]].dropna()
    if mkt.empty:
        # 如果拿不到SPY，就退化为“高波动震荡”（保守，不轻易交易）
        return RegimeLabel.RANGE_HIGH_VOL

    if asof_ts is not None:
        mkt = mkt[mkt["timestamp"] <= asof_ts]

    mkt = mkt.reset_index(drop=True)
    px = mkt["close"]

    ma_fast = px.rolling(cfg.trend_fast).mean()
    ma_slow = px.rolling(cfg.trend_slow).mean()

    trend_score = (ma_fast / ma_slow - 1.0).abs()
    ret = px.pct_change()
    vol = ret.rolling(cfg.vol_window).std(ddof=0)

    # 取最后一个可用值
    ts_trend = float(trend_score.dropna().iloc[-1]) if not trend_score.dropna().empty else 0.0
    ts_vol = float(vol.dropna().iloc[-1]) if not vol.dropna().empty else 1e9

    is_trend = ts_trend >= cfg.trend_threshold
    is_high_vol = ts_vol >= cfg.vol_threshold

    if is_trend and is_high_vol:
        return RegimeLabel.TREND_HIGH_VOL
    if is_trend and (not is_high_vol):
        return RegimeLabel.TREND_LOW_VOL
    if (not is_trend) and is_high_vol:
        return RegimeLabel.RANGE_HIGH_VOL
    return RegimeLabel.RANGE_LOW_VOL
```

### `portfolio/position_sizing.py`

```python
# portfolio/position_sizing.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, Optional

import numpy as np
import pandas as pd


PositionMethod = Literal["equal", "vol_target", "risk_parity", "kelly"]


@dataclass(frozen=True)
class PositionConfig:
    method: PositionMethod = "vol_target"
    max_positions: int = 5
    target_vol_annual: float = 0.15      # 年化目标波动（vol targeting）
    vol_lookback: int = 20
    kelly_fraction: float = 0.25         # 分数Kelly（强烈建议 < 1）


def _annualize_vol(daily_vol: float, trading_days: int = 252) -> float:
    return float(daily_vol) * np.sqrt(trading_days)


def compute_weights_from_signals(
    ohlcv: pd.DataFrame,
    signals: pd.Series,
    cfg: PositionConfig,
    asof_ts: pd.Timestamp,
) -> Dict[str, float]:
    """
    输入：
      - ohlcv: 全量历史数据（用于估计波动/协方差）
      - signals: index=(timestamp, symbol) 的 {0,1} 或 {-1,0,1} 信号
      - asof_ts: 当前决策时间点（信号在 asof_ts 产生，下一交易日执行）
    输出：
      - weights: symbol -> 目标权重（总和 <= 1）
    """
    # 取当日信号
    day_sig = signals.xs(asof_ts, level=0, drop_level=False) if asof_ts in signals.index.get_level_values(0) else None
    if day_sig is None or day_sig.empty:
        return {}

    day_sig = day_sig.reset_index()
    day_sig = day_sig[day_sig["signal"] != 0].copy()
    if day_sig.empty:
        return {}

    # 只取前 max_positions（signals 已可能是 top-k 过滤后的）
    day_sig = day_sig.head(cfg.max_positions)
    syms = day_sig["symbol"].astype(str).tolist()

    if cfg.method == "equal":
        w = 1.0 / len(syms)
        return {s: w for s in syms}

    # 计算各标的日收益率波动
    df = ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["symbol", "timestamp"])
    df = df[df["timestamp"] <= asof_ts]

    vols = {}
    mus = {}
    for s in syms:
        sub = df[df["symbol"] == s].tail(cfg.vol_lookback + 5)  # 多取一点防止缺口
        if sub.shape[0] < max(5, cfg.vol_lookback):
            continue
        r = sub["close"].pct_change().dropna()
        vols[s] = float(r.tail(cfg.vol_lookback).std(ddof=0))
        mus[s] = float(r.tail(cfg.vol_lookback).mean())

    syms = [s for s in syms if s in vols and vols[s] > 0]
    if not syms:
        return {}

    if cfg.method == "vol_target":
        inv_vol = np.array([1.0 / vols[s] for s in syms], dtype=float)
        raw_w = inv_vol / inv_vol.sum()

        # 组合波动目标：缩放所有仓位（近似：忽略相关性）
        port_daily_vol = float(np.sqrt(np.sum((raw_w ** 2) * np.array([vols[s] ** 2 for s in syms]))))
        port_ann_vol = _annualize_vol(port_daily_vol)

        scale = 1.0
        if port_ann_vol > 1e-12:
            scale = min(1.0, cfg.target_vol_annual / port_ann_vol)

        w = raw_w * scale
        return {s: float(wi) for s, wi in zip(syms, w)}

    if cfg.method == "risk_parity":
        # 简化版：用协方差矩阵迭代近似 ERC（Equal Risk Contribution）
        # 真实生产建议：协方差收缩 + 更稳健优化；此处给模板框架即可。
        px = (
            df[df["symbol"].isin(syms)]
            .pivot(index="timestamp", columns="symbol", values="close")
            .sort_index()
            .tail(cfg.vol_lookback + 1)
        )
        rets = px.pct_change().dropna()
        if rets.empty:
            return {}
        cov = rets.cov().values
        n = cov.shape[0]
        w = np.ones(n) / n

        def risk_contrib(w_: np.ndarray) -> np.ndarray:
            port_var = float(w_.T @ cov @ w_)
            if port_var <= 0:
                return np.zeros_like(w_)
            mrc = cov @ w_
            rc = w_ * mrc / np.sqrt(port_var)
            return rc

        # 迭代让 RC 接近相等
        for _ in range(200):
            rc = risk_contrib(w)
            if rc.sum() <= 0:
                break
            target = rc.sum() / n
            # multiplicative update（简单、但不是最优）
            w = w * (target / (rc + 1e-12))
            w = np.clip(w, 1e-6, None)
            w = w / w.sum()

        return {s: float(wi) for s, wi in zip(syms, w)}

    if cfg.method == "kelly":
        # Kelly（多资产）：w ∝ inv(cov) * mu
        # 极不稳定：强烈建议使用分数Kelly + 收缩估计 + 上限裁剪
        px = (
            df[df["symbol"].isin(syms)]
            .pivot(index="timestamp", columns="symbol", values="close")
            .sort_index()
            .tail(cfg.vol_lookback + 1)
        )
        rets = px.pct_change().dropna()
        if rets.empty:
            return {}
        mu = rets.mean().values
        cov = rets.cov().values

        try:
            inv_cov = np.linalg.pinv(cov)
        except Exception:
            return {}

        raw = inv_cov @ mu
        raw = np.maximum(raw, 0.0)  # 模板默认只做多
        if raw.sum() <= 0:
            return {}

        w = raw / raw.sum()
        w = w * float(cfg.kelly_fraction)
        return {s: float(wi) for s, wi in zip(syms, w)}

    raise ValueError(f"未知仓位方法: {cfg.method}")
```

### `risk/management.py`

```python
# risk/management.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RiskConfig:
    max_weight_per_asset: float = 0.25
    max_gross_exposure: float = 1.0          # 做多总仓位上限（<=1为不加杠杆）
    max_drawdown: float = 0.25               # 回撤熔断（从峰值跌幅超过则停）
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    slippage_bps: float = 5.0                # 回测摩擦成本：滑点（bps）
    commission_bps: float = 0.0              # 佣金（可留作扩展）


def clamp_weights(weights: Dict[str, float], cfg: RiskConfig) -> Dict[str, float]:
    """
    对目标权重做硬约束裁剪：
    - 单标的上限
    - 总敞口上限
    """
    if not weights:
        return {}

    w = {s: float(max(0.0, v)) for s, v in weights.items()}  # 模板只做多
    w = {s: min(v, cfg.max_weight_per_asset) for s, v in w.items()}

    gross = sum(w.values())
    if gross > cfg.max_gross_exposure and gross > 1e-12:
        scale = cfg.max_gross_exposure / gross
        w = {s: v * scale for s, v in w.items()}
    return w


def apply_drawdown_kill_switch(equity_curve: pd.Series, cfg: RiskConfig) -> bool:
    """
    如果回撤超过阈值，返回 True 表示应该停止交易（kill switch）。
    """
    if equity_curve.empty:
        return False
    peak = equity_curve.cummax()
    dd = (equity_curve / peak - 1.0).min()
    return float(dd) <= -float(cfg.max_drawdown)


def estimate_trade_cost_multiplier(cfg: RiskConfig) -> float:
    """
    简化：把滑点/佣金合并为每次换仓的成本倍数（bps -> proportion）
    """
    bps = float(cfg.slippage_bps) + float(cfg.commission_bps)
    return bps / 10_000.0
```

### `backtest/train.py`

```python
# backtest/train.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import itertools
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from strategy.trend.trend import TrendBreakoutStrategy
from strategy.mean_reversion.mean_reversion import MeanReversionBollingerStrategy


ART_DIR = "artifacts"
FROZEN_DIR = os.path.join(ART_DIR, "frozen_params")
REPORT_DIR = os.path.join(ART_DIR, "reports")


@dataclass(frozen=True)
class TrainSpec:
    symbols: List[str]
    start: str                 # ISO date, e.g. "2016-01-01"
    end: str                   # ISO date
    objective: str = "sharpe"  # sharpe / cagr / calmar
    bars_timeframe: str = "1D" # 模板占位（数据拉取在 main.py 里实现更合理）
    overwrite_frozen: bool = False


def _ensure_dirs() -> None:
    os.makedirs(FROZEN_DIR, exist_ok=True)
    os.makedirs(REPORT_DIR, exist_ok=True)


def _to_utc_ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


def _simple_backtest(
    ohlcv: pd.DataFrame,
    signals: pd.Series,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    cost_bps: float = 5.0,
) -> pd.Series:
    """
    极简回测：
    - 信号在 t 产生，t+1 open 建仓/调仓；持有到下一次调仓
    - 每标的等权（信号已 top-k），只做多
    - 成本：按换手乘以 cost_bps（粗略）
    输出：equity_curve（每日权益，起始=1）
    """
    df = ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["timestamp", "symbol"])
    df = df[(df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)].copy()

    px = df.pivot(index="timestamp", columns="symbol", values="open").sort_index()
    close = df.pivot(index="timestamp", columns="symbol", values="close").sort_index()
    if px.empty or close.empty:
        return pd.Series(dtype=float)

    # signals: index=(timestamp, symbol) -> {0,1}
    sig_df = signals.rename("signal").reset_index()
    sig_df["timestamp"] = pd.to_datetime(sig_df["timestamp"], utc=True)

    # 每天目标持仓集合
    day_positions = (
        sig_df[sig_df["signal"] != 0]
        .groupby("timestamp")["symbol"]
        .apply(list)
        .reindex(px.index)
        .fillna([])
    )

    equity = []
    eq = 1.0
    prev_set = set()

    # 计算日收益（用 open->close 作为持有期收益的近似）
    oc_ret = (close / px - 1.0).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    for ts in px.index:
        # t 的信号在 t+1 开盘执行，这里为了简单，直接用 t 的 open->close 持有收益
        # 更严谨：应 shift 一天执行；你可以在 test/wf 中替换为更严格的撮合规则。
        curr = set(day_positions.loc[ts])
        if len(curr) == 0:
            equity.append(eq)
            prev_set = curr
            continue

        w = 1.0 / len(curr)
        day_ret = float(oc_ret.loc[ts, list(curr)].mean())  # 等权平均
        # 成本：如果持仓集合变化，扣一次 cost
        turnover = 1.0 if curr != prev_set else 0.0
        cost = turnover * (cost_bps / 10_000.0)

        eq = eq * (1.0 + day_ret - cost)
        equity.append(eq)
        prev_set = curr

    return pd.Series(equity, index=px.index, name="equity")


def _metrics(equity: pd.Series) -> Dict[str, float]:
    if equity.empty:
        return {"sharpe": np.nan, "cagr": np.nan, "max_dd": np.nan, "calmar": np.nan}

    ret = equity.pct_change().dropna()
    if ret.empty:
        return {"sharpe": np.nan, "cagr": np.nan, "max_dd": np.nan, "calmar": np.nan}

    ann = 252.0
    sharpe = float(ret.mean() / (ret.std(ddof=0) + 1e-12) * np.sqrt(ann))

    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / max(years, 1e-9)) - 1.0)

    peak = equity.cummax()
    dd = (equity / peak - 1.0).min()
    max_dd = float(dd)

    calmar = float(cagr / (abs(max_dd) + 1e-12))
    return {"sharpe": sharpe, "cagr": cagr, "max_dd": max_dd, "calmar": calmar}


def _grid_iter(grid: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    keys = list(grid.keys())
    vals = [list(grid[k]) for k in keys]
    combos = []
    for prod in itertools.product(*vals):
        combos.append({k: v for k, v in zip(keys, prod)})
    return combos


def freeze_params(
    strategy_name: str,
    params: Dict[str, Any],
    train_spec: TrainSpec,
    best_metrics: Dict[str, float],
) -> str:
    """
    冻结参数写入 artifacts/frozen_params/{strategy}.json
    这一步只能在 train 阶段发生。
    """
    _ensure_dirs()
    path = os.path.join(FROZEN_DIR, f"{strategy_name}.json")

    if (not train_spec.overwrite_frozen) and os.path.exists(path):
        raise FileExistsError(
            f"冻结参数已存在且不允许覆盖：{path}\n"
            "如需覆盖，请显式设置 overwrite_frozen=True（只允许在 train 阶段）。"
        )

    payload = {
        "strategy": strategy_name,
        "params": params,
        "train_spec": asdict(train_spec),
        "best_metrics": best_metrics,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "note": "OOS/test 阶段严禁修改该文件；如策略失效，走完整重做流程。",
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return path


def train_one_strategy(
    ohlcv: pd.DataFrame,
    train_spec: TrainSpec,
    strategy,
) -> Tuple[Dict[str, Any], Dict[str, float]]:
    start_ts = _to_utc_ts(train_spec.start)
    end_ts = _to_utc_ts(train_spec.end)

    grid = _grid_iter({k: list(v) for k, v in strategy.param_grid().items()})
    best_params = None
    best_score = -1e18
    best_metrics = None

    for p in grid:
        params = strategy.default_params()
        params.update(p)

        res = strategy.generate(ohlcv, params)
        equity = _simple_backtest(ohlcv, res.signals, start_ts, end_ts, cost_bps=5.0)
        m = _metrics(equity)

        if train_spec.objective == "sharpe":
            score = m["sharpe"]
        elif train_spec.objective == "cagr":
            score = m["cagr"]
        else:
            score = m["calmar"]

        if np.isnan(score):
            continue
        if score > best_score:
            best_score = score
            best_params = params
            best_metrics = m

    if best_params is None or best_metrics is None:
        raise RuntimeError(f"训练失败：{strategy.name} 无可用参数组合")

    return best_params, best_metrics


def train(
    ohlcv: pd.DataFrame,
    train_spec: TrainSpec,
    strategies: List[str],
) -> Dict[str, Any]:
    """
    train 阶段：可以做参数搜索；训练结束必须 freeze。
    """
    _ensure_dirs()

    name_to_strategy = {
        "trend": TrendBreakoutStrategy(),
        "mean_reversion": MeanReversionBollingerStrategy(),
    }

    selected = []
    for s in strategies:
        if s not in name_to_strategy:
            raise ValueError(f"未知策略: {s}")
        selected.append(name_to_strategy[s])

    summary = {"train_spec": asdict(train_spec), "results": {}}
    for st in selected:
        best_params, best_m = train_one_strategy(ohlcv, train_spec, st)
        frozen_path = freeze_params(st.name, best_params, train_spec, best_m)
        summary["results"][st.name] = {
            "best_params": best_params,
            "best_metrics": best_m,
            "frozen_path": frozen_path,
        }

    # 写训练报告（不覆盖 frozen_params 的约束不适用于 reports）
    rep_path = os.path.join(REPORT_DIR, f"train_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")
    with open(rep_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return summary
```

### `backtest/test.py`

```python
# backtest/test.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from strategy.trend.trend import TrendBreakoutStrategy
from strategy.mean_reversion.mean_reversion import MeanReversionBollingerStrategy


ART_DIR = "artifacts"
FROZEN_DIR = os.path.join(ART_DIR, "frozen_params")
REPORT_DIR = os.path.join(ART_DIR, "reports")


@dataclass(frozen=True)
class TestSpec:
    symbols: List[str]
    start: str
    end: str
    strategies: List[str]
    forbid_param_write: bool = True   # 核心护栏：test 阶段默认禁止写 frozen_params


def _to_utc_ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


def _load_frozen_params(strategy_name: str) -> Dict[str, Any]:
    path = os.path.join(FROZEN_DIR, f"{strategy_name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"缺少冻结参数文件: {path}（请先 train）")
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload


def _metrics(equity: pd.Series) -> Dict[str, float]:
    if equity.empty:
        return {"sharpe": np.nan, "cagr": np.nan, "max_dd": np.nan, "calmar": np.nan}

    ret = equity.pct_change().dropna()
    if ret.empty:
        return {"sharpe": np.nan, "cagr": np.nan, "max_dd": np.nan, "calmar": np.nan}

    ann = 252.0
    sharpe = float(ret.mean() / (ret.std(ddof=0) + 1e-12) * np.sqrt(ann))
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / max(years, 1e-9)) - 1.0)
    peak = equity.cummax()
    dd = (equity / peak - 1.0).min()
    max_dd = float(dd)
    calmar = float(cagr / (abs(max_dd) + 1e-12))
    return {"sharpe": sharpe, "cagr": cagr, "max_dd": max_dd, "calmar": calmar}


def _simple_backtest(ohlcv: pd.DataFrame, signals: pd.Series, start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> pd.Series:
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

    day_positions = (
        sig_df[sig_df["signal"] != 0]
        .groupby("timestamp")["symbol"]
        .apply(list)
        .reindex(open_px.index)
        .fillna([])
    )

    oc_ret = (close_px / open_px - 1.0).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    eq = 1.0
    equity = []
    for ts in open_px.index:
        curr = day_positions.loc[ts]
        if len(curr) == 0:
            equity.append(eq)
            continue
        eq = eq * (1.0 + float(oc_ret.loc[ts, curr].mean()))
        equity.append(eq)
    return pd.Series(equity, index=open_px.index, name="equity")


def run_oos_test(ohlcv: pd.DataFrame, test_spec: TestSpec) -> Dict[str, Any]:
    os.makedirs(REPORT_DIR, exist_ok=True)

    name_to_strategy = {
        "trend": TrendBreakoutStrategy(),
        "mean_reversion": MeanReversionBollingerStrategy(),
    }

    start_ts = _to_utc_ts(test_spec.start)
    end_ts = _to_utc_ts(test_spec.end)

    results = {"test_spec": test_spec.__dict__, "strategies": {}}

    # 关键：test 阶段只读 frozen_params（人为加固：你也可以在 CI 里检查文件 hash 不变）
    for name in test_spec.strategies:
        if name not in name_to_strategy:
            raise ValueError(f"未知策略: {name}")

        payload = _load_frozen_params(name)
        params = payload["params"]

        st = name_to_strategy[name]
        res = st.generate(ohlcv, params)
        equity = _simple_backtest(ohlcv, res.signals, start_ts, end_ts)
        m = _metrics(equity)

        results["strategies"][name] = {
            "frozen_file": os.path.join(FROZEN_DIR, f"{name}.json"),
            "oos_metrics": m,
            "equity_final": float(equity.iloc[-1]) if not equity.empty else np.nan,
        }

    rep_path = os.path.join(REPORT_DIR, f"test_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")
    with open(rep_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return results
```

### `backtest/walk_forward.py`

```python
# backtest/walk_forward.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from backtest.test import _load_frozen_params, _simple_backtest, _metrics
from strategy.trend.trend import TrendBreakoutStrategy
from strategy.mean_reversion.mean_reversion import MeanReversionBollingerStrategy


ART_DIR = "artifacts"
REPORT_DIR = os.path.join(ART_DIR, "reports")


@dataclass(frozen=True)
class WalkForwardSpec:
    symbols: List[str]
    start: str
    end: str
    strategies: List[str]

    # 默认窗口方案（你可在 README 中解释并允许调整）
    train_years: int = 3
    test_months: int = 6
    step_months: int = 3
    gap_days: int = 1   # train/test 之间留间隔，避免“同日close生成信号又成交”的灰区


def _to_utc_ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


def _month_add(ts: pd.Timestamp, months: int) -> pd.Timestamp:
    return (ts + pd.DateOffset(months=months)).normalize()


def run_walk_forward(ohlcv: pd.DataFrame, wf: WalkForwardSpec) -> Dict[str, Any]:
    """
    WF 验证的定位：在“参数已冻结”的前提下，评估策略在多段连续 OOS 窗口上的稳定性。
    - 不在 WF 内对策略再调参（否则又变成滚动优化，流程定义会改变）
    - 输出每个窗口的指标，以及全窗口拼接后的指标
    """
    os.makedirs(REPORT_DIR, exist_ok=True)

    name_to_strategy = {
        "trend": TrendBreakoutStrategy(),
        "mean_reversion": MeanReversionBollingerStrategy(),
    }

    start_ts = _to_utc_ts(wf.start)
    end_ts = _to_utc_ts(wf.end)

    results = {"walk_forward_spec": wf.__dict__, "strategies": {}}

    for name in wf.strategies:
        if name not in name_to_strategy:
            raise ValueError(f"未知策略: {name}")

        payload = _load_frozen_params(name)
        params = payload["params"]
        st = name_to_strategy[name]

        # 生成信号（全样本生成一次，避免在每窗重复计算）
        res = st.generate(ohlcv, params)

        windows = []
        equity_all = pd.Series(dtype=float)

        cursor = start_ts
        while True:
            train_end = _month_add(cursor, wf.train_years * 12)
            test_start = train_end + pd.Timedelta(days=wf.gap_days)
            test_end = _month_add(test_start, wf.test_months)

            if test_end > end_ts:
                break

            # 这里不做 train（参数已冻结），但仍按窗口输出 OOS 指标
            equity = _simple_backtest(ohlcv, res.signals, test_start, test_end)
            m = _metrics(equity)

            windows.append({
                "train_window": [str(cursor.date()), str(train_end.date())],
                "test_window": [str(test_start.date()), str(test_end.date())],
                "metrics": m,
                "equity_final": float(equity.iloc[-1]) if not equity.empty else np.nan,
            })

            # 拼接（注意：日期可能重叠，按 index 去重保留后者）
            equity_all = pd.concat([equity_all, equity]).~drop_duplicates(keep="last")

            cursor = _month_add(cursor, wf.step_months)

        results["strategies"][name] = {
            "frozen_file": os.path.join("artifacts", "frozen_params", f"{name}.json"),
            "windows": windows,
            "overall_metrics": _metrics(equity_all) if not equity_all.empty else {},
        }

    rep_path = os.path.join(REPORT_DIR, f"walk_forward_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")
    with open(rep_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return results
```

### `main.py`

```python
# main.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd
import yaml
from dotenv import load_dotenv

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest

from backtest.train import TrainSpec, train
from backtest.test import TestSpec, run_oos_test
from backtest.walk_forward import WalkForwardSpec, run_walk_forward
from regime.detection import RegimeConfig, detect_regime, RegimeLabel
from portfolio.position_sizing import PositionConfig, compute_weights_from_signals
from risk.management import RiskConfig, clamp_weights

from strategy.trend.trend import TrendBreakoutStrategy
from strategy.mean_reversion.mean_reversion import MeanReversionBollingerStrategy


def load_runtime_config(path: str = "config/runtime.yaml") -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_symbols(path: str = "config/symbols.txt") -> List[str]:
    if not os.path.exists(path):
        # 默认：给一个最小列表，建议你在 symbols.txt 中维护
        return ["AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "GOOGL"]
    syms = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip().upper()
            if s and (not s.startswith("#")):
                syms.append(s)
    return syms


def get_alpaca_clients() -> tuple[StockHistoricalDataClient, TradingClient]:
    """
    Paper Trading：使用 paper=True，并确保 key 属于 paper 环境（官方强调 keys 与 base URL 必须匹配）。
    """
    load_dotenv()
    key = os.getenv("ALPACA_API_KEY")
    secret = os.getenv("ALPACA_API_SECRET")
    if not key or not secret:
        raise ValueError("缺少环境变量：ALPACA_API_KEY / ALPACA_API_SECRET（建议写入 .env）")

    data_client = StockHistoricalDataClient(key, secret)
    trading_client = TradingClient(key, secret, paper=True)
    return data_client, trading_client


def fetch_daily_ohlcv(
    data_client: StockHistoricalDataClient,
    symbols: List[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    """
    从 Alpaca 拉取日线 bars 并转换为 long-format:
    timestamp, symbol, open, high, low, close, volume
    """
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")

    req = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=start_ts,
        end=end_ts,
    )
    bars = data_client.get_stock_bars(req).df
    if bars is None or bars.empty:
        return pd.DataFrame(columns=["timestamp", "symbol", "open", "high", "low", "close", "volume"])

    # Alpaca 返回通常为 MultiIndex: (symbol, timestamp)
    df = bars.reset_index().rename(columns={"index": "timestamp"})
    if "timestamp" not in df.columns:
        # 某些版本 reset_index 后列名可能为 'timestamp'
        pass

    # 统一列
    # 预期 df 含 symbol/timestamp/open/high/low/close/volume
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = df["symbol"].astype(str)
    return df[["timestamp", "symbol", "open", "high", "low", "close", "volume"]].sort_values(["timestamp", "symbol"])


def load_frozen_params(strategy_name: str) -> Dict[str, float]:
    path = os.path.join("artifacts", "frozen_params", f"{strategy_name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"缺少冻结参数：{path}（先运行 train）")
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload["params"]


def choose_strategy_by_regime(regime: RegimeLabel) -> str:
    """
    运行期决策：只切换策略/仓位/风控，不改策略参数。
    """
    if regime in (RegimeLabel.TREND_LOW_VOL, RegimeLabel.TREND_HIGH_VOL):
        return "trend"
    # 震荡时倾向均值回归；但高波动震荡可能在 risk 层直接禁用
    return "mean_reversion"


def submit_bracket_orders(
    trading_client: TradingClient,
    weights: Dict[str, float],
    latest_prices: Dict[str, float],
    equity: float,
    risk_cfg: RiskConfig,
    dry_run: bool = True,
) -> None:
    """
    把目标权重转为市价括号单（bracket order）。
    """
    for sym, w in weights.items():
        px = float(latest_prices.get(sym, np.nan))
        if not np.isfinite(px) or px <= 0:
            continue

        notional = equity * float(w)
        qty = int(notional / px)
        if qty <= 0:
            continue

        stop_price = round(px * (1.0 - risk_cfg.stop_loss_pct), 2)
        take_profit = round(px * (1.0 + risk_cfg.take_profit_pct), 2)

        order = MarketOrderRequest(
            symbol=sym,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            stop_loss=StopLossRequest(stop_price=stop_price),
            take_profit=TakeProfitRequest(limit_price=take_profit),
        )

        if dry_run:
            print(f"[DRY_RUN] submit {sym} qty={qty} px~{px:.2f} SL={stop_price} TP={take_profit}")
        else:
            resp = trading_client.submit_order(order_data=order)
            print(f"SUBMITTED {sym}: {getattr(resp, 'id', '-')}")


def cmd_train(args: argparse.Namespace) -> None:
    data_client, _ = get_alpaca_clients()
    symbols = load_symbols()
    ohlcv = fetch_daily_ohlcv(data_client, symbols, args.start, args.end)

    spec = TrainSpec(
        symbols=symbols,
        start=args.start,
        end=args.end,
        objective=args.objective,
        overwrite_frozen=args.overwrite_frozen,
    )
    out = train(ohlcv, spec, strategies=args.strategies)
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_test(args: argparse.Namespace) -> None:
    data_client, _ = get_alpaca_clients()
    symbols = load_symbols()
    ohlcv = fetch_daily_ohlcv(data_client, symbols, args.start, args.end)

    spec = TestSpec(symbols=symbols, start=args.start, end=args.end, strategies=args.strategies)
    out = run_oos_test(ohlcv, spec)
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_walk_forward(args: argparse.Namespace) -> None:
    data_client, _ = get_alpaca_clients()
    symbols = load_symbols()
    ohlcv = fetch_daily_ohlcv(data_client, symbols, args.start, args.end)

    wf = WalkForwardSpec(
        symbols=symbols,
        start=args.start,
        end=args.end,
        strategies=args.strategies,
        train_years=args.train_years,
        test_months=args.test_months,
        step_months=args.step_months,
    )
    out = run_walk_forward(ohlcv, wf)
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_deploy(args: argparse.Namespace) -> None:
    data_client, trading_client = get_alpaca_clients()
    runtime = load_runtime_config()

    symbols = load_symbols()
    # 拉取足够历史用于策略/状态识别（默认取近 500 天）
    end = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    start = (pd.Timestamp.utcnow() - pd.Timedelta(days=800)).strftime("%Y-%m-%d")
    ohlcv = fetch_daily_ohlcv(data_client, symbols + ["SPY"], start, end)

    # Regime detection（运行期可调）
    reg_cfg = RegimeConfig(**(runtime.get("regime", {}) or {}))
    regime = detect_regime(ohlcv, reg_cfg)
    print(f"Regime = {regime}")

    # 选择策略（不改参数）
    chosen = choose_strategy_by_regime(regime)

    # 高波动震荡：默认不交易（运行期策略）
    if regime == RegimeLabel.RANGE_HIGH_VOL and runtime.get("regime", {}).get("no_trade_in_range_high_vol", True):
        print("Regime=RANGE_HIGH_VOL，按配置不交易。")
        return

    # 生成信号
    if chosen == "trend":
        st = TrendBreakoutStrategy()
    else:
        st = MeanReversionBollingerStrategy()

    params = load_frozen_params(chosen)
    res = st.generate(ohlcv, params)

    # 运行期仓位配置（可调整）
    pos_cfg = PositionConfig(**(runtime.get("position", {}) or {}))
    # 以最后一个交易日为 asof
    asof_ts = pd.to_datetime(ohlcv["timestamp"].max(), utc=True)

    weights = compute_weights_from_signals(ohlcv, res.signals, pos_cfg, asof_ts)
    risk_cfg = RiskConfig(**(runtime.get("risk", {}) or {}))
    weights = clamp_weights(weights, risk_cfg)

    print("Target weights:", weights)

    # 最新价格：用 asof_ts 的 close 作为近似
    latest = (
        ohlcv[ohlcv["timestamp"] == asof_ts][["symbol", "close"]]
        .set_index("symbol")["close"]
        .to_dict()
    )

    acct = trading_client.get_account()
    equity = float(acct.equity)
    print(f"Account equity = {equity:.2f}")

    submit_bracket_orders(trading_client, weights, latest, equity, risk_cfg, dry_run=args.dry_run)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Modular Quant Trading Project (train/test/wf/deploy)")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_train = sub.add_parser("train", help="Train (in-sample) & freeze parameters")
    p_train.add_argument("--start", required=True)
    p_train.add_argument("--end", required=True)
    p_train.add_argument("--strategies", nargs="+", default=["trend", "mean_reversion"])
    p_train.add_argument("--objective", default="sharpe", choices=["sharpe", "cagr", "calmar"])
    p_train.add_argument("--overwrite-frozen", action="store_true")
    p_train.set_defaults(fn=cmd_train)

    p_test = sub.add_parser("test", help="Out-of-sample test (immutable)")
    p_test.add_argument("--start", required=True)
    p_test.add_argument("--end", required=True)
    p_test.add_argument("--strategies", nargs="+", default=["trend", "mean_reversion"])
    p_test.set_defaults(fn=cmd_test)

    p_wf = sub.add_parser("walk-forward", help="Walk-forward validation (immutable params)")
    p_wf.add_argument("--start", required=True)
    p_wf.add_argument("--end", required=True)
    p_wf.add_argument("--strategies", nargs="+", default=["trend", "mean_reversion"])
    p_wf.add_argument("--train-years", type=int, default=3)
    p_wf.add_argument("--test-months", type=int, default=6)
    p_wf.add_argument("--step-months", type=int, default=3)
    p_wf.set_defaults(fn=cmd_walk_forward)

    p_dep = sub.add_parser("deploy", help="Deploy to Alpaca paper trading")
    p_dep.add_argument("--dry-run", action="store_true", help="Do not submit orders")
    p_dep.set_defaults(fn=cmd_deploy)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
```

### `requirements.txt`

```text
# requirements.txt
alpaca-py>=0.20.0
pandas>=2.0.0
numpy>=1.24.0
python-dotenv>=1.0.0
PyYAML>=6.0.0
pytest>=8.0.0
```

### `README.md`

```markdown
# Modular Quant Trading Project（Train→Freeze→OOS Test→Walk-forward→Deploy）

本项目实现一个“研究/验证/部署”分层清晰的量化交易工程骨架，核心原则：

- Develop/Train：只在训练区间开发与调参
- Freeze：训练完成后把策略参数写入 `artifacts/frozen_params/*.json` 并冻结
- OOS Test：样本外测试只读 frozen 参数，禁止再调参
- Walk-forward：在 frozen 参数不变的前提下做多窗口稳定性验证
- Deploy：部署到 Alpaca Paper（建议先 dry-run）
- 运行期只允许调整：市场状态识别（regime）、仓位（position sizing）、风控（risk）
- 若实盘/纸盘显著失效：重新做完整研发流程（重新划分数据、重新训练与冻结）

## 目录结构

- strategy/
  - base_strategy.py：策略接口
  - trend/trend.py：趋势突破策略
  - mean_reversion/mean_reversion.py：均值回归策略
- regime/detection.py：市场状态识别（运行期可调）
- portfolio/position_sizing.py：仓位方法（运行期可调）
- risk/management.py：风险约束、熔断、摩擦成本（运行期可调）
- backtest/
  - train.py：训练与参数搜索，并 freeze 参数
  - test.py：样本外测试（只读 frozen 参数）
  - walk_forward.py：滚动窗口验证（只读 frozen 参数）
- config/runtime.yaml：运行期参数（只允许改这里）
- artifacts/
  - frozen_params/：冻结策略参数（OOS/test 阶段禁止修改）
  - reports/：训练/测试/WF 输出报告
- main.py：统一入口（train/test/walk-forward/deploy）

## 环境变量（.env）

在仓库根目录创建 `.env`：

```env
ALPACA_API_KEY=你的paper key
ALPACA_API_SECRET=你的paper secret
```

注意：Paper 和 Live 使用不同 Key；并且 API 环境必须匹配（paper key 配 paper 环境）。建议先只做 paper。  

## 运行期配置（config/runtime.yaml）

示例：

```yaml
regime:
  symbol_for_regime: "SPY"
  trend_fast: 20
  trend_slow: 100
  trend_threshold: 0.01
  vol_window: 20
  vol_threshold: 0.02
  no_trade_in_range_high_vol: true

position:
  method: "vol_target"      # equal / vol_target / risk_parity / kelly
  max_positions: 5
  target_vol_annual: 0.15
  vol_lookback: 20
  kelly_fraction: 0.25

risk:
  max_weight_per_asset: 0.25
  max_gross_exposure: 1.0
  max_drawdown: 0.25
  stop_loss_pct: 0.05
  take_profit_pct: 0.10
  slippage_bps: 5.0
  commission_bps: 0.0
```

运行期只允许修改这里（regime/position/risk）。  
**禁止**在 OOS/test 阶段修改 `artifacts/frozen_params/*.json`。

## 标的列表（config/symbols.txt）

每行一个 symbol，例如：

```text
AAPL
MSFT
NVDA
AMZN
META
TSLA
GOOGL
```

## 运行：train / test / walk-forward

安装依赖：

```bash
pip install -r requirements.txt
```

训练（仅使用训练区间，并冻结参数）：

```bash
python main.py train --start 2016-01-01 --end 2021-12-31 --strategies trend mean_reversion --objective sharpe
```

样本外测试（只读 frozen 参数）：

```bash
python main.py test --start 2022-01-01 --end 2024-12-31 --strategies trend mean_reversion
```

Walk-forward（多窗口稳定性验证，仍只读 frozen 参数）：

```bash
python main.py walk-forward --start 2016-01-01 --end 2024-12-31 --strategies trend mean_reversion --train-years 3 --test-months 6 --step-months 3
```

报告输出在 `artifacts/reports/`。

## 部署到 Alpaca Paper（建议先 dry-run）

```bash
python main.py deploy --dry-run
```

确认输出的目标权重与订单计划无误后，再去掉 `--dry-run`：

```bash
python main.py deploy
```

## 参数冻结工作流（关键）

- `train` 阶段会写入 `artifacts/frozen_params/{strategy}.json`
- `test` / `walk-forward` / `deploy` 阶段只读取该文件

建议你执行以下纪律：

1. 冻结后在 Git 上打 tag，例如 `freeze_2026_03_19`
2. 任何对 frozen_params 的修改都必须通过“重新 train → 重新 freeze”的流程
3. 看到 OOS 不好时，不允许“只改一点点参数再试”
   - 正确做法：要么只调 runtime.yaml（regime/仓位/风控）
   - 要么判定策略失效，重新走完整研发闭环

## 单元测试（示例）

```bash
pytest -q
```

建议添加 CI：当 PR 修改了 frozen_params 直接失败（见报告的 CI 模板）。

```

## 参数冻结、防泄露 CI 与默认验证方案

### 参数冻结与“不可变 OOS”的最小可执行标准

你要防的不是“回测不够长”，而是“你尝试了太多组合后挑中了一个赢家”。PBO/DSR 的研究明确指出：当策略/参数试验规模很大时，历史最优往往是噪声的极值而不是技能。citeturn3search2turn3search6turn3search8

因此“冻结参数”的工程定义应包含三件事：

1) **冻结文件只在 train 阶段生成**：本模板在 `backtest/train.py` 里允许 `overwrite_frozen`，但默认禁止覆盖；在 `test`/`walk_forward`/`deploy` 里只读加载。  
2) **冻结文件携带元信息**：训练区间、目标函数、冻结时间等（模板已写入）。  
3) **CI 强制不可变**：任何 PR 只要触碰 `artifacts/frozen_params/**` 就必须走“train->freeze”流程并留下审计痕迹（例如更新 MANIFEST + 新 tag）。

### CI/Checklist 模板（防止数据泄露/后验调参）

下面给一个最小 CI 思路（你可放到 `.github/workflows/ci.yml`，仓库当前未见该文件，属于新增项/未指定）：

- 运行 `pytest`  
- 检查 `test` 阶段不会写回 `artifacts/frozen_params`  
- 若 PR 修改了 `frozen_params`，要求 PR 标题含 `[FREEZE]` 或必须更新 `MANIFEST.json`（用脚本生成 hash）

你可以采用“清单式”护栏（建议写到 PR 模板里）：

- 是否仅在 train 集调参？  
- 是否触碰过 test 集做调参或人工规则调整？（禁止）  
- 是否所有 rolling 指标都避免前视（例如 shift(1)，或 t+1 成交约定）？  
- 是否考虑过成本（滑点、冲击）与可成交性？  
- 是否做过 Walk-forward 多窗口稳定性检查？  
- 是否报告了最大回撤、换手、收益分布，而不仅是收益率？  
这些要求与“时间序列必须按时间顺序切分、不能 shuffle，否则会在未来数据上训练并在过去评估”的基本原则一致。citeturn2search1turn2search0turn5search1

### 单元测试示例与运行

> 下列 tests 为“示例文件”（不在你强制列表内，但你要求必须提供 unit test 示例与运行方式，因此给出可复制版本）。

**`tests/test_splits.py`**（确保 Walk-forward 的窗口时间单调、无穿越）：

```python
# tests/test_splits.py
import pandas as pd
from backtest.walk_forward import _to_utc_ts, _month_add

def test_month_add_monotonic():
    t0 = pd.Timestamp("2020-01-01", tz="UTC")
    t1 = _month_add(t0, 3)
    t2 = _month_add(t1, 3)
    assert t2 > t1 > t0

def test_to_utc_ts():
    ts = _to_utc_ts("2022-01-01")
    assert ts.tzinfo is not None
```

**`tests/test_freeze_manifest.py`**（强制 frozen 文件存在且 test 不应改写；这里用“只读预期”做最小断言）：

```python
# tests/test_freeze_manifest.py
import os
import json

def test_frozen_params_exist_or_skipped():
    # 允许新仓库第一次跑时没有 frozen；你可在 CI 中把它改成必须存在
    path = os.path.join("artifacts", "frozen_params", "trend.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        assert "params" in payload and "train_spec" in payload
```

**运行**：

```bash
pytest -q
```

### 默认超参、指标体系与 Walk-forward 窗口方案

#### 默认超参（建议从你现有仓库起步）

你的现有 `main/config.py` 中 breakout 与 volume window 均为 20，单笔风险 1%，止损 5%、止盈 10%，这是一套合理的“先跑起来”的默认值（尤其适合日线趋势策略）。fileciteturn12file0L1-L1

本报告建议的默认值继承并做了轻微工程化：

- 趋势策略（trend）：breakout 20/55、动量 20/60、volume_ratio 1.2/1.5/2.0、top_k 3/5（训练时小网格）；  
- 均值回归（mean_reversion）：lookback 10/20/40、entry_z 1.5/2.0/2.5、exit_z 0/0.5/1.0；  
- Regime：MA(20,100) 作为趋势，20日滚动波动率阈值 2%（年化约 ~32%），作为高波动粗阈值；  
- 仓位：默认 vol_target，目标年化波动 15%，max_positions 5；  
- 风控：max_weight_per_asset 25%，max_gross_exposure 100%，max_drawdown 25%，滑点 5 bps（先保守）。

#### 指标体系（建议最少集合）

- 收益类：CAGR（年化复利）  
- 风险类：最大回撤（Max Drawdown）  
- 风险调整：Sharpe（基础）  
- 稳健性：Walk-forward 各窗口指标的分布（均值/分位数/最差窗口）  
在策略/参数试验很多时，建议进一步引入 DSR 或 PBO/CSCV 来量化“这是不是筛出来的幸运儿”。citeturn3search2turn3search6turn0search6

#### Walk-forward 推荐窗口（与你的生命周期一致）

你指定“冻结参数后再做 WF 验证”，因此 WF 在这里扮演的是**稳定性体检**而不是“滚动再优化”。建议默认方案：

- 训练窗口：3 年  
- 测试窗口：6 个月  
- 步长：3 个月  
- gap：1 天（或 1 根bar）  
该方案与时间序列交叉验证的核心思想一致：训练集永远在测试集之前、测试窗口递进。citeturn2search1turn5search3

### 仓位方法对比表

下表给出你要求的 2–4 种仓位方法对比；其中 risk parity 与 Kelly 的理论与实践风险差异较大，应把“默认”放在 equal/vol-target 上。

| 方法 | 核心思想 | 优点 | 缺点/风险 | 适用建议 |
|---|---|---|---|---|
| 等权（equal） | 选中标的平均分配权重 | 简单、稳健、最少估计误差 | 忽略波动差异，组合波动可能偏大 | 作为基线（baseline），任何系统都应先跑通 |
| 波动率目标（vol_target） | 用波动估计缩放仓位，控制组合风险；有研究表明波动管理可提升风险调整后表现但也存在 OOS/成本争议 | 风险更可控、对跨状态更稳；工程落地简单 | 波动估计滞后；成本/滑点可能抵消收益；文献也讨论了 OOS 与成本敏感性 | 建议默认；并在高波动状态自动降仓 citeturn0search11turn0search12 |
| 风险平价（risk_parity / ERC） | 让每个资产对组合风险贡献相近，弱化对收益预测依赖 | 不依赖收益预测、强调分散；经典 ERC 研究给出性质分析 | 需要协方差估计（不稳），实现复杂；相关性变化可能导致失效 | 适合多资产/ETF；做股票时也可用但需稳健估计 citeturn1search49turn1search8 |
| Kelly（kelly） | 最大化对数财富增长；理论上最优但极度依赖对“期望收益/协方差”的估计 | 在模型正确时增长最快 | 对估计误差极端敏感，易过度杠杆；必须分数 Kelly | 仅建议研究/小比例试验；生产建议分数<=0.25 citeturn1search6turn1search4 |

### 常见坑与缓解手段

1) **多重检验/挑结果（multiple-testing）**：策略越多、参数越多，越容易“筛出噪声赢家”。  
缓解：限制网格规模、固定研究流程、用 DSR/PBO/CSCV 做显著性与过拟合概率评估、把“冻结参数”当成发布工件。citeturn3search2turn3search6turn3search0  

2) **状态识别误判（regime misclassification）**：状态切换永远有滞后与错误，若策略只在“完美分类”才赚钱，实盘大概率崩。  
缓解：让策略在全状态下“不会死得很难看”；高波动震荡状态宁可不交易；把状态阈值放在 runtime.yaml 运行期可调，策略参数仍冻结。

3) **延迟与成交摩擦（latency/slippage/impact）**：回测不包含真实滑点与冲击成本会虚高；执行策略与交易所微观结构是独立问题，经典最优执行研究明确指出成本与风险的权衡。citeturn2search16turn2search15  
缓解：回测加入保守滑点（bps）、限制换手；部署时优先使用括号单/限价单；对流动性做过滤（你现有策略已用成交额过滤）。fileciteturn17file0L1-L1  

4) **数据泄露（lookahead / leakage）**：最常见的是 rolling 指标忘记 shift，或者用同一根 bar 的 close 同时做信号与成交。  
缓解：坚持“信号 t → t+1 成交”的撮合约定；rolling 计算中使用 `shift(1)`（你现有 breakout 最高价/均量就是这种正确写法）。fileciteturn16file0L1-L1  

5) **Paper/Live 环境不匹配**：Paper 与 Live key 不同，端点/环境必须匹配；官方明确指出不匹配会导致认证失败或请求异常。citeturn4search2turn0search9  

6) **把“策略失效”当成“再调一调参数”**：这是你指定生命周期要避免的核心。  
缓解：运行期只允许改 regime/仓位/风控；如果 OOS/WF/纸盘出现结构性失效，就重新走 develop→freeze→test→wf 的闭环（而不是在 test 上修修补补）。PBO/DSR 的研究背景强调了“回测优化导致性能膨胀”的系统性风险。citeturn3search2turn3search6