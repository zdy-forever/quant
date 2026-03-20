# Changes Log

## 2026-03-20 1.0.12（从策略驱动切到因子驱动）

### 因子来源与因子目录

- 新增 [factors/](factors/)
- 新增：
  - [factors/base.py](factors/base.py)
  - [factors/momentum.py](factors/momentum.py)
  - [factors/reversal.py](factors/reversal.py)
  - [factors/volatility.py](factors/volatility.py)
  - [factors/volume.py](factors/volume.py)
  - [factors/breakout.py](factors/breakout.py)
  - [factors/composite.py](factors/composite.py)
- 现在项目不再把“短线想法”直接写成策略，优先先拆成原子因子
- 当前已经落地的核心因子来源包括：
  - cross-sectional momentum / relative strength
  - short-term reversal
  - volume anomaly / turnover shock
  - low volatility / volatility compression
  - gap + continuation / trend + pullback 的工程化拆解
- 新增因子来源说明：
  - [report/alpha-factor-sources.md](report/alpha-factor-sources.md)

### 研究层重构

- 新增 [research/](research/)
- 新增：
  - [research/standardize.py](research/standardize.py)
  - [research/factor_engine.py](research/factor_engine.py)
  - [research/ic_analysis.py](research/ic_analysis.py)
  - [research/quantile_backtest.py](research/quantile_backtest.py)
  - [research/factor_tests.py](research/factor_tests.py)
  - [research/factor_selection.py](research/factor_selection.py)
- 现在研究流程已经拆成：
  - universe / eligibility
  - 横截面标准化
  - 单因子 IC / Rank IC / quantile spread / hit rate
  - train / OOS 稳定因子筛选
- 更新了 [alpha_lab/factors.py](alpha_lab/factors.py)
  - 现在它只是兼容层
  - 真正的因子主实现已经迁到新的 [factors/](factors/) 目录

### 新的因子流水线入口

- 新增 [pipelines/](pipelines/)
- 新增：
  - [pipelines/run_factor_research.py](pipelines/run_factor_research.py)
  - [pipelines/run_factor_selection.py](pipelines/run_factor_selection.py)
  - [pipelines/run_composite_portfolio.py](pipelines/run_composite_portfolio.py)
  - [pipelines/run_walk_forward.py](pipelines/run_walk_forward.py)
  - [pipelines/run_factor_pipeline.py](pipelines/run_factor_pipeline.py)
- 更新了 [main.py](main.py)
  - 新增命令：
    - `factor-research`
    - `factor-select`
    - `composite-backtest`
    - `factor-walk-forward`
    - `factor-pipeline`

### 配置层扩展

- 更新了 [config/runtime.yaml](config/runtime.yaml)
- 新增：
  - `universe`
  - `standardize`
  - `factor_research`
  - `factor_selection`
  - `composite_model`

### 第一版正式因子研究结果

- 运行了新的正式因子流水线
- 新报告：
  - [artifacts/reports/factor_pipeline_20260320_035221.json](artifacts/reports/factor_pipeline_20260320_035221.json)
  - [artifacts/reports/factor_pipeline_20260320_035221.md](artifacts/reports/factor_pipeline_20260320_035221.md)
- 当前通过 train / OOS 双重筛选并被冻结的稳定因子是：
  - `reversal_5`
  - `true_range_pct_1`
  - `reversal_3`
- 冻结文件：
  - [artifacts/selected_factors/stable_factor_model.json](artifacts/selected_factors/stable_factor_model.json)
- 这轮研究说明：
  - 动量和 breakout 这条线在当前样本里方向更偏负
  - 短期反转和单日振幅冲击更值得继续追
  - OOS composite 目前接近走平，`Sharpe` 略正但 `CAGR` 仍为负，说明还需要继续收紧因子集合和组合规则
  - factor walk-forward 的窗口稳定性比旧策略流程更清楚，当前 `positive Sharpe ratio = 72.7%`

### 文档

- 更新了 [README.md](README.md)
  - 现在把 `factor-pipeline` 放到第一推荐路径
  - 把旧的策略驱动流程降成次要路径
  - 补上新的 `factors/ research/ pipelines/` 目录说明
  - 补上新的命令说明和当前稳定因子名单

## 2026-03-20 1.0.11（短线多因子、Walk-forward 修正、默认池收缩）

### 短线研究方向收口

- 更新了 [alpha_lab/factors.py](alpha_lab/factors.py)
  - 新增一批更适合 1 到 3 天持有周期的 OHLCV 因子
  - 重点补充了：
    - `momentum_3`
    - `momentum_5`
    - `momentum_10`
    - `short_reversal_3`
    - `overnight_gap_1`
    - `intraday_return_1`
    - `close_location_1`
    - `true_range_pct_1`
    - `breakout_distance_5`
    - `volume_surprise_5`
- 新增 [strategy/multi_factor_short/](strategy/multi_factor_short/)
  - 作为当前默认的短线多因子主研究策略
- 新增 [strategy/short_reversal/](strategy/short_reversal/)
  - 做过一轮短线反转研究
- 更新了 [strategy/mean_reversion/mean_reversion.py](strategy/mean_reversion/mean_reversion.py)
  - 收窄成更偏短线反抽的均值回归版本

### 参数搜索与性能优化

- 更新了：
  - [strategy/mean_reversion/mean_reversion.py](strategy/mean_reversion/mean_reversion.py)
  - [strategy/short_reversal/short_reversal.py](strategy/short_reversal/short_reversal.py)
  - [strategy/multi_factor_short/multi_factor_short.py](strategy/multi_factor_short/multi_factor_short.py)
- 收窄了参数网格
  - 让搜索更像“验证研究假设”，而不是暴力扫参
- 给 [strategy/multi_factor_short/multi_factor_short.py](strategy/multi_factor_short/multi_factor_short.py) 加了因子面板缓存
  - 避免同一份样本在优化阶段重复重算多因子特征
  - 把完整 `pipeline` 的运行时间压回可接受范围

### Walk-forward 口径修正

- 更新了 [backtest/walk_forward.py](backtest/walk_forward.py)
  - 修正了旧版本把重叠测试窗口拼接成一个 overall equity 的问题
  - 现在默认：
    - `test_months = 6`
    - `step_months = 6`
  - 也就是说默认不再使用重叠窗口
  - 新输出改成窗口稳定性摘要：
    - `positive_sharpe_ratio`
    - `positive_calmar_ratio`
    - `median_sharpe`
    - `median_cagr`
    - `worst_window_max_dd`
- 同步更新了：
  - [backtest/pipeline.py](backtest/pipeline.py)
  - [main.py](main.py)

### 默认活跃池调整

- 更新了 [strategy/__init__.py](strategy/__init__.py)
- 更新了 [backtest/optimizer.py](backtest/optimizer.py)
- 更新了 [main.py](main.py)
- 更新了 [config/runtime.yaml](config/runtime.yaml)
- `short_reversal` 这轮训练、OOS 和整体稳定性都不够理想，已经从默认活跃池中移除
- 当前默认研究重点只保留：
  - `multi_factor_short`
  - `mean_reversion`

### 最新正式短线研究结果

- 重新运行了短线正式流水线
- 新报告：
  - [artifacts/reports/pipeline_20260320_030253.json](artifacts/reports/pipeline_20260320_030253.json)
  - [artifacts/reports/pipeline_20260320_030253.md](artifacts/reports/pipeline_20260320_030253.md)
- 这轮候选策略是：
  - `mean_reversion`
  - `short_reversal`
  - `multi_factor_short`
- 结论摘要：
  - `multi_factor_short`
    - 训练期最好，Walk-forward 窗口稳定性也最好
    - 但最近 OOS 仍然为负，说明还不能直接当最终实盘模板
  - `mean_reversion`
    - 训练期一般，但最新 OOS 明显转强
    - 值得继续保留观察
  - `short_reversal`
    - 训练和 OOS 都不够理想
    - 已从默认活跃池降级
- Alpha 研究这轮筛出的有效短线因子主要集中在：
  - 短期反转
  - bar 位置
  - 短期波动冲击
  - 近端突破距离

### 文档

- 更新了 [README.md](README.md)
  - 改成以当前短线研究状态为准
  - 删掉了默认策略仍是旧长周期池的写法
  - 加入最新短线报告位置
  - 写清楚 `walk-forward` 现在默认不重叠
  - 写清楚当前还没到“最终组合策略上线”的阶段

## 2026-03-20 1.0.10（VIX 过滤、all/raw 拆分、邮件通知）

### 策略与数据口径

- 更新了 [strategy/trend/trend.py](strategy/trend/trend.py)
  - 趋势策略新增 `VIX` 代理过滤
  - 默认使用 `VIXY` 作为可交易波动率 proxy
  - 新增参数：
    - `use_vix_filter`
    - `vix_symbol`
    - `vix_window`
    - `max_vix_close`
    - `max_vix_ma_ratio`
- 更新了 [main.py](main.py)
  - 研究类命令统一走 `research_bar_adjustment = all`
  - `deploy` 里真正用于执行定价、止损、止盈的价格，单独走 `execution_bar_adjustment = raw`
  - 现在是：
    - 研究/回测/因子分析：优先 `all`
    - 第二天委托价格与风控价格：改用 `raw`
- 更新了 [config/runtime.yaml](config/runtime.yaml)
  - 新增：
    - `data.research_bar_adjustment`
    - `data.execution_bar_adjustment`

### 参考行情与邮件通知

- 新增 [notifications/](notifications/)
- 新增 [notifications/emailer.py](notifications/emailer.py)
  - 回测研究结果自动邮件通知
  - 因子研究结果自动邮件通知
  - `deploy` 自动拆成两封邮件：
    - Alpaca 模拟盘动作
    - IBKR 手动执行建议
  - 默认发件人显示名：`财政小助手mina`
- 更新了 [main.py](main.py)
  - 各命令完成后自动尝试发邮件
  - 命令失败时自动尝试发失败告警邮件
  - 优化了邮件内容长度，减少超时概率
- 更新了 [notifications/emailer.py](notifications/emailer.py)
  - 自动识别 `465 -> SSL`
  - 已用你当前的 `QQ SMTP` 配置完成一封测试邮件验证

### 本次重新回测（VIX + all）

- 重新运行了正式研究流水线
- 新报告：
  - [artifacts/reports/pipeline_20260319_231349.json](artifacts/reports/pipeline_20260319_231349.json)
  - [artifacts/reports/pipeline_20260319_231349.md](artifacts/reports/pipeline_20260319_231349.md)
- 当前基线排序仍然是：
  - `low_vol_momentum`
  - `mean_reversion`
  - `turtle`
  - `trend`
- 进入正式优化的仍然是：
  - `low_vol_momentum`
  - `turtle`
  - `trend`

### 这次回测后的结论

- `trend` 加入 `VIX` 代理过滤后，训练期表现比上一版略有改善，但 OOS 依然偏弱
- `low_vol_momentum` 训练期最强，但这次 OOS 明显走弱，说明它对数据口径和样本窗口仍然比较敏感
- Alpha 因子筛选结果仍然主要指向：
  - `low_volatility_20`
  - `breakout_distance_20`
- 说明这套系统更像“研究筛选器”，还没有到“稳定执行模板”的状态

### 文档

- 更新了 [README.md](README.md)
  - 写清楚 `all` 和 `raw` 的分工
  - 写清楚趋势里的 `VIX` 代理过滤
  - 写清楚自动邮件通知和邮件标题类型

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
