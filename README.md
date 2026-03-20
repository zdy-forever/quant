# Quant 项目说明书

这是一个面向美股日线量化研究与 Alpaca Paper 模拟部署的 Python 工程。  
当前版本已经支持：

- 100+ 只分散化的大盘优质股票池
- 新的因子驱动研究主线：`factor-research -> factor-select -> composite-backtest -> factor-walk-forward -> factor-pipeline`
- 默认活跃研究方向已经切到更贴近 1 到 3 天持有周期的短线 alpha
- 多策略研究、参数优化、冻结参数
- OOS 测试与 Walk-forward 验证
- 一键 `pipeline` 研究流程
- 趋势策略里的 `VIX` 代理过滤
- 基于市场状态占比的策略混合持仓
- Alpha 因子研究：IC / Rank IC / IC decay / Quantile / 组合因子 / 因子回测
- 自动邮件通知：研究报告、因子分析、模拟盘动作、IBKR 手动执行建议

先说明一个非常重要的原则：

**这个项目会尽量追求稳健、可重复、少过拟合，但任何人都不能诚实地保证“每个策略单独运行都稳定盈利”。**  
项目现在做的是把研究流程、风控、验证和因子分析搭得更完整，让你更容易识别哪些结果更可信，哪些只是历史噪声。

---

## 1. 你可以怎么理解这个项目

如果你是量化新手，建议把它拆成 7 层来看：

- 数据层
  - 从 Alpaca 拉历史日线
- Universe / Eligibility 层
  - 先决定每天哪些股票有资格进入研究样本
- 因子层
  - 从 OHLCV 生成原子因子，而不是直接写买卖规则
- 研究层
  - 做标准化、IC、Rank IC、quantile、spread、因子筛选
- 仓位层
  - 把 composite factor score 映射成 top-N 组合
- 策略混合层
  - 这层现在是次要层，等单因子和组合因子稳定后再考虑
- 风控层
  - 控制回撤、止损、止盈、换手和总敞口
- 执行层
  - 把研究结果映射到 Alpaca Paper / IBKR 手动操作

最推荐的阅读顺序：

1. [main.py](main.py)
2. [config/runtime.yaml](config/runtime.yaml)
3. [factors/](factors/)
4. [research/factor_engine.py](research/factor_engine.py)
5. [research/factor_tests.py](research/factor_tests.py)
6. [research/factor_selection.py](research/factor_selection.py)
7. [pipelines/run_factor_pipeline.py](pipelines/run_factor_pipeline.py)
8. [backtest/engine.py](backtest/engine.py)
9. [report/alpha-factor-sources.md](report/alpha-factor-sources.md)

---

## 2. 当前目录结构

- [main.py](main.py)
  - 新的统一命令入口
- [factors/](factors/)
  - 原子因子定义与因子来源映射
- [research/](research/)
  - eligibility、标准化、IC / quantile / 因子筛选
- [pipelines/](pipelines/)
  - 因子驱动研究入口
- [strategy/](strategy/)
  - 旧策略与辅助策略，当前不是研究主线
- [regime/](regime/)
  - 市场状态识别与状态占比计算
- [portfolio/](portfolio/)
  - 因子分数到权重，以及多策略资金分配
- [risk/](risk/)
  - 风控约束
- [backtest/](backtest/)
  - 回测引擎、参数优化、训练、测试、Walk-forward
- [alpha_lab/](alpha_lab/)
  - 旧 alpha 接口兼容层
- [config/](config/)
  - 股票池和运行期配置
- [report/](report/)
  - 研究报告和因子来源说明
- [artifacts/](artifacts/)
  - 冻结参数与各类报告
- [artifacts/cache/](artifacts/cache/)
  - 历史日线缓存
- [tests/](tests/)
  - 基础测试

---

## 3. 当前主线是什么

### 因子驱动主线

现在项目的第一优先级已经不是“继续堆策略”，而是：

1. 先定义 universe
2. 再生成原子因子
3. 再做 train / OOS 单因子验证
4. 再冻结稳定因子
5. 最后才做 composite portfolio 和 walk-forward

最近一轮正式因子研究报告在：

- [artifacts/reports/factor_pipeline_20260320_035221.md](artifacts/reports/factor_pipeline_20260320_035221.md)
- [artifacts/reports/factor_pipeline_20260320_035221.json](artifacts/reports/factor_pipeline_20260320_035221.json)

当前通过 train 与 OOS 双重验证、并被冻结的稳定因子是：

- `reversal_5`
- `true_range_pct_1`
- `reversal_3`

冻结结果文件在：

- [artifacts/selected_factors/stable_factor_model.json](artifacts/selected_factors/stable_factor_model.json)

这意味着目前更值得继续研究的是：

- 短期反转
- 单日振幅冲击

而不是继续往旧的趋势/突破策略里盲目加参数。

### 策略层现在处于次要位置

策略源码仍然保留，因为它们可以继续拆成原子因子或做辅助比较。

当前默认活跃策略池：

- [strategy/multi_factor_short/multi_factor_short.py](strategy/multi_factor_short/multi_factor_short.py)
- [strategy/mean_reversion/mean_reversion.py](strategy/mean_reversion/mean_reversion.py)

已降级但保留源码的策略：

- [strategy/short_reversal/short_reversal.py](strategy/short_reversal/short_reversal.py)
  - 这轮短线研究里训练和 OOS 都不够稳，已经从默认活跃池移除
- [strategy/trend/trend.py](strategy/trend/trend.py)
  - 旧的中周期趋势突破，保留作后续研究素材
- [strategy/turtle/turtle.py](strategy/turtle/turtle.py)
  - 旧的 Donchian / 海龟风格突破，保留作后续研究素材
- [strategy/pullback/pullback.py](strategy/pullback/pullback.py)
  - 旧的趋势回撤策略，当前不是默认研究重点
- [strategy/low_vol_momentum/low_vol_momentum.py](strategy/low_vol_momentum/low_vol_momentum.py)
  - 旧的低波动动量策略，当前不是默认研究重点

### 策略设计原则

当前无论是策略研究还是因子研究，都尽量遵守这几个原则：

- 尽量少参数
- 参数网格不要过大
- 尽量只用 OHLCV 可获得信息
- 使用训练 / OOS / Walk-forward 分层验证
- 不以“历史最优”作为唯一标准

---

## 4. 股票池说明

股票池文件：

- [config/symbols.txt](config/symbols.txt)

当前已经扩展到 **100+ 只** 大盘优质股，主要来自：

- Nasdaq 大市值龙头
- S&P 500 大盘蓝筹
- 尽量覆盖不同板块

覆盖的大类包括：

- 科技
- 通信服务
- 可选消费
- 必需消费
- 医疗
- 金融
- 工业
- 能源
- 公用事业
- 材料
- REITs

这样做的目标不是完全摆脱大盘，而是减少“全仓集中在单一风格、单一行业”的问题。

如果你要继续扩股票池，建议规则是：

- 优先大盘高流动性
- 避免过多小盘高噪声标的
- 保持行业分散
- 不要为了“凑数量”加入太多质量差的股票

---

## 5. 最重要的配置文件

### 股票池

- [config/symbols.txt](config/symbols.txt)

规则：

- 每行一个股票代码
- 自动转大写
- `#` 开头会被忽略

### 运行期配置

- [config/runtime.yaml](config/runtime.yaml)

当前主要分成 13 组：

- `data`
  - 历史 bars 的研究/执行价格口径

- `regime`
  - 市场状态识别参数
- `position`
  - 单策略内部的股票仓位方法
- `risk`
  - 风控约束
- `backtest`
  - 回测引擎参数
- `optimizer`
  - 参数优化约束
- `strategy_mix`
  - 按状态混合多策略
- `alpha_lab`
  - Alpha 因子研究参数
- `universe`
  - 每天哪些股票有资格进入样本
- `standardize`
  - 因子横截面标准化方法
- `factor_research`
  - 单因子检验窗口和 quantile 参数
- `factor_selection`
  - train / OOS 稳定因子筛选阈值
- `composite_model`
  - factor portfolio 的 top-N 和 rebalance 规则

如果你是新手，最建议先从这些字段开始改：

- `universe.min_price`
- `universe.min_avg_dollar_volume`
- `factor_selection.min_train_rank_ic`
- `factor_selection.min_oos_rank_ic`
- `composite_model.top_n`
- `composite_model.rebalance_every_n_days`
- `backtest.slippage_bps`

---

## 6. 回测系统现在做到了什么

底层回测文件：

- [backtest/engine.py](backtest/engine.py)

当前回测引擎已经支持：

- 每日目标权重回测
- 信号到持仓的转换
- 换手成本
- 固定止损
- 固定止盈
- ATR 追踪止损
- 最大持有天数
- 更完整的指标输出

输出指标包括：

- Sharpe
- Sortino
- CAGR
- Max Drawdown
- Calmar
- 年化波动
- 平均换手
- 平均持仓数量
- 交易次数

注意：

- 这仍然是日频近似，不是逐笔撮合
- 止损/止盈是用日线 high/low/close 做近似
- 对于免费版 Alpaca，部署阶段已经额外处理了 15 分钟延迟导致的“当日日线未确认”问题
- 研究和回测默认使用 `adjustment="all"`
- 真正给第二天委托价格、止损价、止盈价定价时，`deploy` 会额外拉一份 `raw` 数据，避免和真实市场价格错位

---

## 7. 参数优化程序

参数优化文件：

- [backtest/optimizer.py](backtest/optimizer.py)

它不是简单地“找历史最赚钱参数”，还加入了约束：

- 最少交易次数
- 最低平均活跃仓位
- 最大平均换手约束
- 对高回撤和过高换手做惩罚

你可以单独运行：

```bash
conda activate quant
python main.py optimize --start 2016-01-01 --end 2021-12-31 --strategies mean_reversion multi_factor_short --objective calmar
```

然后再决定要不要用 `train` 去冻结参数。

---

## 8. 一键研究流程 + 训练、测试、Walk-forward

如果你想正式做一轮完整研究，当前最推荐的已经不是旧的策略 `pipeline`，而是新的 `factor-pipeline`：

```bash
conda activate quant
python main.py factor-pipeline --train-start 2016-01-01 --train-end 2021-12-31 --oos-start 2022-01-01 --oos-end 2024-12-31 --walk-forward-start 2016-01-01 --walk-forward-end 2024-12-31
```

这个命令会按顺序做：

- 先定义每日 eligible universe
- 生成原子因子横截面
- 做 train / OOS 单因子验证
- 筛选并冻结稳定因子
- 把稳定因子组合成 composite score
- 做 OOS factor portfolio backtest
- 做 factor walk-forward
- 最后输出汇总报告

输出位置主要有：

- [artifacts/reports/](artifacts/reports/)
- [artifacts/selected_factors/](artifacts/selected_factors/)
- [artifacts/cache/ohlcv/](artifacts/cache/ohlcv/)

说明：

- `factor-pipeline` 会尽量复用本地缓存，减少重复请求 Alpaca 历史数据
- 它的核心问题不是“哪个策略最好”，而是“哪个因子真的有 alpha”
- `factor-walk-forward` 现在默认 `--step-months 6`，和 `--test-months 6` 一样长，默认不再使用重叠窗口
- 新版因子 walk-forward 会输出窗口稳定性摘要，而不是拼接成一个不严谨的 overall 曲线

下面这些单独命令也已经接好，适合做局部研究。

### 单因子研究

```bash
conda activate quant
python main.py factor-research --train-start 2016-01-01 --train-end 2021-12-31 --oos-start 2022-01-01 --oos-end 2024-12-31
```

### 因子筛选与冻结

```bash
conda activate quant
python main.py factor-select --train-start 2016-01-01 --train-end 2021-12-31 --oos-start 2022-01-01 --oos-end 2024-12-31
```

### Composite Portfolio 回测

```bash
conda activate quant
python main.py composite-backtest --train-start 2016-01-01 --train-end 2021-12-31 --oos-start 2022-01-01 --oos-end 2024-12-31
```

### Factor Walk-Forward

```bash
conda activate quant
python main.py factor-walk-forward --start 2016-01-01 --end 2024-12-31
```

旧的策略 `pipeline / train / test / walk-forward` 仍然保留，适合做对照研究，但现在不是主线路。

### 训练并冻结参数

```bash
conda activate quant
python main.py train --start 2016-01-01 --end 2021-12-31 --strategies mean_reversion multi_factor_short --objective calmar
```

输出：

- [artifacts/frozen_params/](artifacts/frozen_params/)
- [artifacts/reports/](artifacts/reports/)

### 样本外测试

```bash
conda activate quant
python main.py test --start 2022-01-01 --end 2024-12-31 --strategies mean_reversion multi_factor_short
```

### Walk-forward

```bash
conda activate quant
python main.py walk-forward --start 2016-01-01 --end 2024-12-31 --strategies mean_reversion multi_factor_short --train-years 3 --test-months 6 --step-months 6 --gap-days 1
```

因子研究纪律：

- 先看单因子，再看组合因子
- train 里方向明确，OOS 里不能翻向
- 先冻结因子集合和组合方法，再看 OOS 组合收益
- Walk-forward 是稳定性体检，不是重新偷偷调因子

策略研究仍然保留，最近一轮旧策略报告在：

- [artifacts/reports/pipeline_20260320_030253.md](artifacts/reports/pipeline_20260320_030253.md)
- [artifacts/reports/pipeline_20260320_030253.json](artifacts/reports/pipeline_20260320_030253.json)

当前阶段性的解读是：

- `multi_factor_short` 是最值得继续保留的短线主研究策略
- `mean_reversion` 是保留观察的次候选
- `short_reversal` 已经从默认活跃池移除
- 现在还没有进入“把多条单策略稳定组合成最终实盘模板”的阶段

---

## 9. 市场状态和多策略混合

状态识别文件：

- [regime/detection.py](regime/detection.py)

策略混合文件：

- [portfolio/strategy_blend.py](portfolio/strategy_blend.py)

现在系统不只会给出单一状态标签，还会估计最近一段时间的状态占比，例如：

- `trend_total = 0.70`
- `range_total = 0.30`

然后根据这个占比去分配策略层资金，比如：

- 趋势策略合计分 70%
- 震荡/回归策略分 30%

你可以在 [config/runtime.yaml](config/runtime.yaml) 的 `strategy_mix` 里调：

- 哪些策略算趋势策略
- 哪些策略算震荡策略
- 哪些策略算防御策略
- 高波动时要不要整体降总仓

当前默认混合配置已经只保留：

- `mean_reversion`
- `multi_factor_short`

如果你想完全遵守“单策略先跑稳，再组合”的原则，最简单的做法是：

- 先只跑 `train / test / walk-forward`
- 暂时不要直接 `deploy`
- 等你确认两条单策略都持续稳定，再恢复更积极的多策略混合

部署命令：

```bash
conda activate quant
python main.py deploy --dry-run
```

这时候输出会包括：

- 当前单一 regime
- 最近一段时间的 regime mix
- 各策略资金分配
- 最终合成的股票目标权重
- 以及一封自动邮件：
  - 一封写 Alpaca 模拟盘里做了什么
  - 一封写你在 IBKR App 里可以手动照着做什么

---

## 10. 因子研究目录

当前真正的因子研究主线在：

- [factors/](factors/)
- [research/](research/)
- [pipelines/](pipelines/)
- [report/alpha-factor-sources.md](report/alpha-factor-sources.md)

主要文件：

- [factors/momentum.py](factors/momentum.py)
  - 动量 / relative strength / trend + pullback 原子因子
- [factors/reversal.py](factors/reversal.py)
  - 短期反转因子
- [factors/volatility.py](factors/volatility.py)
  - 低波、波动压缩、单日振幅冲击
- [factors/volume.py](factors/volume.py)
  - volume surprise、turnover shock、liquidity
- [factors/breakout.py](factors/breakout.py)
  - breakout distance、close location、gap continuation
- [research/factor_engine.py](research/factor_engine.py)
  - universe / eligibility + 因子面板 + 标准化因子面板
- [research/factor_tests.py](research/factor_tests.py)
  - 单因子 IC / Rank IC / quantile / spread 检验
- [research/factor_selection.py](research/factor_selection.py)
  - train / OOS 稳定因子筛选
- [pipelines/run_factor_pipeline.py](pipelines/run_factor_pipeline.py)
  - 新的因子驱动总流水线

[alpha_lab/](alpha_lab/) 现在主要是兼容层，避免旧代码失效。

当前内置了一批基于 OHLCV 的起步因子，例如：

- `momentum_20`
- `momentum_60`
- `reversal_3`
- `reversal_5`
- `trend_pullback_20_5`
- `true_range_pct_1`
- `volume_surprise_5`
- `turnover_shock_20`
- `low_volatility_20`
- `close_location_1`
- `breakout_distance_20`
- `gap_continuation_1`
- `ma_distance_20`

因子研究流程现在已经支持：

- 每日 eligible universe
- 因子来源元数据
- 横截面 winsorize + rank 标准化
- 单因子 IC / Rank IC
- quantile spread / hit rate
- train / OOS 因子筛选与冻结
- composite factor top-N 组合回测
- factor walk-forward

运行方式：

```bash
conda activate quant
python main.py factor-pipeline --train-start 2016-01-01 --train-end 2021-12-31 --oos-start 2022-01-01 --oos-end 2024-12-31 --walk-forward-start 2016-01-01 --walk-forward-end 2024-12-31
```

如果某些因子通过了 train / OOS 双重验证，系统会：

- 冻结到 [artifacts/selected_factors/](artifacts/selected_factors/)
- 自动把它们合成 composite factor
- 每天从排名靠前的股票里选前 `N` 只，而不是只买 1 只
- 再做 OOS 和 walk-forward，而不是直接当成最终实盘策略

---

## 11. 环境准备

推荐使用你的 conda 环境：

- `quant`

安装依赖：

```bash
conda activate quant
python -m pip install -r requirements.txt
```

### `.env`

推荐：

```env
ALPACA_API_KEY=你的_paper_key
ALPACA_API_SECRET=你的_paper_secret
```

### 自动邮件通知

如果你把下面这些变量配好：

```env
EMAIL_SENDER=你的发件邮箱
EMAIL_PASSWORD=你的邮箱密码或授权码
EMAIL_RECEIVER=你的收件邮箱
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
```

补充说明：

- 如果你用的是 `QQ 邮箱 + 465`，现在代码会自动按 `SSL` 方式发送
- 如果你以后想手动指定，也可以加：
  - `SMTP_USE_SSL=true`
  - `SMTP_USE_STARTTLS=false`

那么项目会在这些命令完成后自动发邮件：

- `optimize`
- `train`
- `test`
- `walk-forward`
- `alpha-research`
- `pipeline`
- `deploy`

默认发件人显示名就是：`财政小助手mina`。  
不同主体会用不同标题，例如：

- 回测研究报告
- 因子分析报告
- Alpaca 模拟盘操作
- IBKR 手动操作建议
- 任务失败告警

---

## 12. 测试

测试目录：

- [tests/test_splits.py](tests/test_splits.py)
- [tests/test_freeze_manifest.py](tests/test_freeze_manifest.py)
- [tests/test_no_lookahead.py](tests/test_no_lookahead.py)

运行：

```bash
conda activate quant
python -m pytest -q
```

---

## 13. 你最可能会改哪些地方

### 想扩股票池

改：

- [config/symbols.txt](config/symbols.txt)

### 想改多策略混合比例

改：

- [config/runtime.yaml](config/runtime.yaml) 里的 `strategy_mix`

### 想改止损止盈和动态持仓

改：

- [config/runtime.yaml](config/runtime.yaml) 里的 `backtest`
- [backtest/engine.py](backtest/engine.py)

### 想新增一个策略

按这个顺序：

1. 参考 [strategy/base_strategy.py](strategy/base_strategy.py)
2. 在 [strategy/](strategy/) 下新建一个子目录
3. 实现 `default_params()`、`param_grid()`、`generate()`
4. 把它接进 [backtest/optimizer.py](backtest/optimizer.py) 的策略注册表
5. 再接进 [config/runtime.yaml](config/runtime.yaml) 的 `strategy_mix`

### 想新增一个因子

按这个顺序：

1. 先在 [report/alpha-factor-sources.md](report/alpha-factor-sources.md) 记下来源线和研究理由
2. 再去 [factors/](factors/) 里加原子因子函数
3. 跑 `factor-research`
4. 看 train / OOS 的 rank IC、spread、hit rate
5. 只有通过筛选，才进入 `factor-select` 和 `factor-pipeline`

---

## 14. 最后给你的建议

如果你现在是量化新手，最容易犯的错误不是代码写错，而是研究流程太激进。  
最推荐的推进顺序是：

1. 先跑一次 `factor-pipeline`
2. 看哪些单因子在 train / OOS 方向一致
3. 只保留最稳定的 2 到 4 个因子
4. 再看 composite portfolio 的 OOS 和 walk-forward
5. 最后才去考虑策略化和 `deploy --dry-run`

而且每次只改一小块：

- 先改股票池
- 再改仓位
- 再改风控
- 最后才改策略和因子

这样你才知道结果变化到底来自哪一步，而不是一下子把所有变量都搅在一起。
