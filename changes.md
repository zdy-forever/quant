# Changes Log

## 2026-03-19 1.0.9（pipeline 与正式研究）

### 工程改动

- 新增 [backtest/pipeline.py](backtest/pipeline.py)
  - 把 `baseline screening -> optimize -> freeze -> OOS -> walk-forward -> alpha research` 串成一条正式研究流水线
- 更新了 [main.py](main.py)
  - 新增 `pipeline` 命令
  - Alpaca 历史日线抓取改成分批请求
  - 新增本地缓存目录 [artifacts/cache/ohlcv/](artifacts/cache/ohlcv/)
- 更新了 [alpha_lab/research.py](alpha_lab/research.py)
  - `Rank IC` 改成不依赖 `scipy` 的实现
  - 修掉组合因子合成时的运行时警告
- 更新了 [backtest/__init__.py](backtest/__init__.py)
  - 去掉会引起循环导入的导出

### 本次正式研究设置

- 股票池：`135` 只
- 优化窗口：`2016-01-01 -> 2021-12-31`
- OOS 窗口：`2022-01-01 -> 2024-12-31`
- Walk-forward 窗口：`2016-01-01 -> 2024-12-31`
- 候选策略：
  - `trend`
  - `turtle`
  - `low_vol_momentum`
  - `mean_reversion`
- 目标函数：`calmar`

### 本次正式研究结果

- 默认参数基线排序：
  - `low_vol_momentum`
  - `mean_reversion`
  - `turtle`
  - `trend`
- 进入正式优化并冻结的策略：
  - `low_vol_momentum`
  - `turtle`
  - `trend`
- OOS 结果里目前相对最值得继续观察的是 `low_vol_momentum`
  - `Sharpe = 0.08`
  - `CAGR = -0.80%`
  - `MaxDD = -37.36%`
- `turtle` 和 `trend` 这轮 OOS 都偏弱，暂时不建议直接当主策略
- Walk-forward 总体上：
  - `low_vol_momentum` 接近走平
  - `turtle`、`trend` 偶尔有亮点窗口，但整体稳定性还不够

### Alpha 研究结果

- 通过当前阈值筛出的因子：
  - `low_volatility_20`
  - `breakout_distance_20`
- 当前最新 top picks：
  - `CSCO`
  - `MA`
  - `BSX`
  - `V`
  - `KO`
  - `AAPL`
  - `TGT`
  - `MCD`
  - `GILD`
  - `ABT`

### 报告产物

- 汇总 JSON：
  - [artifacts/reports/pipeline_20260319_143550.json](artifacts/reports/pipeline_20260319_143550.json)
- 汇总 Markdown：
  - [artifacts/reports/pipeline_20260319_143550.md](artifacts/reports/pipeline_20260319_143550.md)

## 2026-03-19  1.0.7


### Alpaca 免费版延迟保护

- 检查后确认原来的 `deploy` 流程没有显式处理免费版约 15 分钟延迟的问题
- 已在 [main.py](main.py) 新增保护逻辑：如果当前还是美东当日且未到 `16:15 ET`，则自动丢弃当天未确认完成的日线 bar
- 这样部署时默认只基于上一个已完成交易日的日线做决策，避免把延迟中的“今天日线”误当成最终数据

### 量化稳健性改造（本轮）

- 在本机为项目创建了本地 `uv` 虚拟环境：`.venv`
- 安装并补齐了运行依赖，额外补装 `pytz`
- 跑通测试，当前 `pytest` 结果为 `4 passed`
- 先完成了一轮基线回测：`train -> test -> walk-forward`

### 策略层改动

#### trend

- 新增长期趋势过滤参数：`trend_filter_window`
- 新增波动过滤参数：`volatility_window`、`max_daily_volatility`
- 目标是减少高波动环境下的假突破，优先保留更平滑的趋势信号

#### mean_reversion

- 新增流动性过滤：`min_avg_dollar_volume`
- 新增长期趋势过滤：`trend_window`
- 新增三个稳健性开关：
  - `require_above_trend_ma`
  - `require_positive_trend_return`
  - `require_rebound_bar`
- 核心目的：避免在明显下跌趋势里反复抄底，把均值回归收缩成“顺大趋势里的短线回撤反弹”

### 训练评分修正

- 修正了 `calmar` 目标的一个退化问题：
  - 以前参数搜索会偏向“几乎不交易”的组合，因为回撤接近 0，导致 `calmar` 虚高
- 现在做了两层约束：
  - `calmar` 的回撤分母设置最小有效值 `0.02`
  - 新增信号活跃度过滤，过于低频的参数组合会被跳过
- 这样能避免把“躺平不交易”误判成“稳健策略”

### 当前结论（阶段性）

- `trend` 仍然是目前更有交易价值的单策略
- `mean_reversion` 在加了稳健过滤后，回撤明显收敛，但收益也被压得很低，暂时更像辅助/候补策略，而不是主策略
- 仅靠当前这套日线股票逻辑，想把“单策略最大回撤”长期稳定压到 **2% 左右**，现实上比较难；如果硬压，通常会把策略压成低收益甚至接近不交易

### 备注

- 按你的要求，后续我每次做代码修改时都会同步更新这个文件
- 补充接入了 `pullback` 策略框架，并完成了一轮 train/test 评估；当前 OOS 不佳，暂不建议作为主策略
- 新增仓库 `.gitignore`，忽略 `.DS_Store`、`__pycache__/`、`.venv/` 以及 `artifacts/reports/` 这类本地/临时产物

## 2026-03-19 1.0.8（大扩展）

### 股票池扩展

- 把 [config/symbols.txt](config/symbols.txt) 扩展到了 100+ 只大盘优质股票
- 尽量覆盖科技、通信、消费、医疗、金融、工业、能源、公用事业、材料、REITs 等不同大类

### 回测与优化

- 新增 [backtest/engine.py](backtest/engine.py)
  - 支持每日目标权重回测
  - 支持换手成本、止损、止盈、ATR 追踪止损、最大持有天数
  - 输出更完整的绩效指标
- 新增 [backtest/optimizer.py](backtest/optimizer.py)
  - 单独做参数优化
  - 不再只是“顺手训练”
  - 增加最少交易次数、最少活跃仓位、换手约束等稳健性过滤
- 重写了 [backtest/train.py](backtest/train.py)、[backtest/test.py](backtest/test.py)、[backtest/walk_forward.py](backtest/walk_forward.py)
  - 统一走新的回测引擎和优化器

### 新策略

- 新增 [strategy/turtle/turtle.py](strategy/turtle/turtle.py)
  - Donchian / 海龟突破策略
- 新增 [strategy/low_vol_momentum/low_vol_momentum.py](strategy/low_vol_momentum/low_vol_momentum.py)
  - 低波动动量策略
- 当前策略池已经包含：
  - `trend`
  - `turtle`
  - `pullback`
  - `low_vol_momentum`
  - `mean_reversion`

### 市场状态与策略混合

- 扩展了 [regime/detection.py](regime/detection.py)
  - 不只给单一标签
  - 还能估计最近一段时间的状态占比
- 新增 [portfolio/strategy_blend.py](portfolio/strategy_blend.py)
  - 用于根据 `trend_total / range_total / high_vol_total` 这样的状态占比分配策略资金
- 更新了 [main.py](main.py) 的 `deploy`
  - 从单策略切换，升级成多策略混合持仓

### Alpha 因子研究

- 新增 [alpha_lab/](alpha_lab/)
- 新增 [alpha_lab/factors.py](alpha_lab/factors.py)
  - 内置一批 OHLCV 因子
- 新增 [alpha_lab/research.py](alpha_lab/research.py)
  - 支持 IC / Rank IC / IC decay / Quantile / 组合因子 / top-N 回测
- 更新了 [main.py](main.py)
  - 新增 `alpha-research` 命令

### 文档

- 重写了 [README.md](README.md)
  - 加入股票池说明
  - 加入新策略说明
  - 加入回测引擎和优化器说明
  - 加入市场状态混合说明
  - 加入 alpha 因子研究说明

### 说明

- 这次改动的目标是让系统更完整、更稳健、更适合继续研究
- 但我没有也不会虚假承诺“每个策略单独运行都稳定盈利”
- 现在的框架更适合你持续做验证、筛选、迭代，而不是一次性宣布某个策略永远有效
