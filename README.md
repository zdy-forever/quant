# Quant 项目说明书

这是一个面向美股日线量化研究与 Alpaca Paper 模拟部署的 Python 工程。  
当前版本已经支持：

- 100+ 只分散化的大盘优质股票池
- 多策略研究、参数优化、冻结参数
- OOS 测试与 Walk-forward 验证
- 基于市场状态占比的策略混合持仓
- Alpha 因子研究：IC / Rank IC / IC decay / Quantile / 组合因子 / 因子回测

先说明一个非常重要的原则：

**这个项目会尽量追求稳健、可重复、少过拟合，但任何人都不能诚实地保证“每个策略单独运行都稳定盈利”。**  
项目现在做的是把研究流程、风控、验证和因子分析搭得更完整，让你更容易识别哪些结果更可信，哪些只是历史噪声。

---

## 1. 你可以怎么理解这个项目

如果你是量化新手，建议把它拆成 6 层来看：

- 数据层
  - 从 Alpaca 拉历史日线
- 策略层
  - 从 OHLCV 生成交易信号
- 仓位层
  - 决定每只股票买多少
- 策略混合层
  - 根据市场状态给不同策略分资金
- 风控层
  - 控制回撤、止损、止盈、换手和总敞口
- 研究层
  - 回测、参数优化、Walk-forward、Alpha 因子分析

最推荐的阅读顺序：

1. [main.py](main.py)
2. [config/runtime.yaml](config/runtime.yaml)
3. [strategy/base_strategy.py](strategy/base_strategy.py)
4. [backtest/engine.py](backtest/engine.py)
5. [backtest/optimizer.py](backtest/optimizer.py)
6. [regime/detection.py](regime/detection.py)
7. [portfolio/position_sizing.py](portfolio/position_sizing.py)
8. [portfolio/strategy_blend.py](portfolio/strategy_blend.py)
9. [alpha_lab/research.py](alpha_lab/research.py)

---

## 2. 当前目录结构

- [main.py](main.py)
  - 新的统一命令入口
- [strategy/](strategy/)
  - 各个交易策略
- [regime/](regime/)
  - 市场状态识别与状态占比计算
- [portfolio/](portfolio/)
  - 单策略股票仓位和多策略资金分配
- [risk/](risk/)
  - 风控约束
- [backtest/](backtest/)
  - 回测引擎、参数优化、训练、测试、Walk-forward
- [alpha_lab/](alpha_lab/)
  - 因子研究、IC / Rank IC / IC decay / Quantile / 组合因子回测
- [config/](config/)
  - 股票池和运行期配置
- [artifacts/](artifacts/)
  - 冻结参数与各类报告
- [tests/](tests/)
  - 基础测试

---

## 3. 当前已经有哪些策略

### 趋势策略

- [strategy/trend/trend.py](strategy/trend/trend.py)
  - 突破 + 量能 + 动量
- [strategy/turtle/turtle.py](strategy/turtle/turtle.py)
  - Donchian / 海龟风格突破
- [strategy/pullback/pullback.py](strategy/pullback/pullback.py)
  - 大趋势中的回撤再上车
- [strategy/low_vol_momentum/low_vol_momentum.py](strategy/low_vol_momentum/low_vol_momentum.py)
  - 低波动动量

### 震荡/回归策略

- [strategy/mean_reversion/mean_reversion.py](strategy/mean_reversion/mean_reversion.py)
  - 基于 z-score 的均值回归

### 策略设计原则

当前策略尽量遵守这几个原则：

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

当前主要分成 7 组：

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

如果你是新手，最建议先从这些字段开始改：

- `position.max_positions`
- `risk.max_weight_per_asset`
- `risk.max_gross_exposure`
- `backtest.stop_loss_pct`
- `backtest.take_profit_pct`
- `strategy_mix.high_vol_haircut`
- `alpha_lab.top_n`

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
python main.py optimize --start 2016-01-01 --end 2021-12-31 --strategies trend turtle pullback low_vol_momentum mean_reversion --objective sharpe
```

然后再决定要不要用 `train` 去冻结参数。

---

## 8. 训练、测试、Walk-forward

### 训练并冻结参数

```bash
conda activate quant
python main.py train --start 2016-01-01 --end 2021-12-31 --strategies trend turtle pullback low_vol_momentum mean_reversion --objective sharpe
```

输出：

- [artifacts/frozen_params/](artifacts/frozen_params/)
- [artifacts/reports/](artifacts/reports/)

### 样本外测试

```bash
conda activate quant
python main.py test --start 2022-01-01 --end 2024-12-31 --strategies trend turtle pullback low_vol_momentum mean_reversion
```

### Walk-forward

```bash
conda activate quant
python main.py walk-forward --start 2016-01-01 --end 2024-12-31 --strategies trend turtle pullback low_vol_momentum mean_reversion --train-years 3 --test-months 6 --step-months 3 --gap-days 1
```

研究纪律还是一样：

- 训练时可以找参数
- OOS 不能回头调参数
- Walk-forward 是稳定性体检，不是重新优化

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
- 均值回归策略分 30%

你可以在 [config/runtime.yaml](config/runtime.yaml) 的 `strategy_mix` 里调：

- 哪些策略算趋势策略
- 哪些策略算震荡策略
- 哪些策略算防御策略
- 高波动时要不要整体降总仓

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

---

## 10. Alpha 因子研究目录

因子研究目录：

- [alpha_lab/](alpha_lab/)

主要文件：

- [alpha_lab/factors.py](alpha_lab/factors.py)
  - 构造原始 alpha 因子
- [alpha_lab/research.py](alpha_lab/research.py)
  - 做 IC / Rank IC / IC decay / Quantile / 组合因子 / 回测

当前内置了一批基于 OHLCV 的起步因子，例如：

- `momentum_20`
- `momentum_60`
- `short_reversal_5`
- `low_volatility_20`
- `close_vs_ma20`
- `close_vs_ma60`
- `breakout_distance_20`
- `range_position_20`
- `volume_surprise_20`

因子研究流程现在已经支持：

- IC test
- Rank IC test
- IC decay
- Quantile test
- 自动筛选有效因子
- 组合因子
- 组合因子 top-N 股票回测
- 输出最新一批股票候选

运行方式：

```bash
conda activate quant
python main.py alpha-research --start 2016-01-01 --end 2024-12-31
```

如果某些因子通过了 IC / Rank IC 筛选，系统会：

- 自动把它们合成组合因子
- 每天从排名靠前的股票里选前 `N` 只，而不是只买 1 只
- 用组合因子做动态更新的日频回测

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

如果要发邮件，再补：

```env
EMAIL_SENDER=你的发件邮箱
EMAIL_PASSWORD=你的邮箱密码或授权码
EMAIL_RECEIVER=你的收件邮箱
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
```

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

1. 改 [alpha_lab/factors.py](alpha_lab/factors.py)
2. 重新跑 `alpha-research`
3. 看 IC / Rank IC / Quantile 结果
4. 再决定是否纳入组合因子

---

## 14. 最后给你的建议

如果你现在是量化新手，最容易犯的错误不是代码写错，而是研究流程太激进。  
最推荐的推进顺序是：

1. 先只跑 `optimize -> train -> test`
2. 再跑 `walk-forward`
3. 再看 `alpha-research`
4. 最后才去 `deploy --dry-run`

而且每次只改一小块：

- 先改股票池
- 再改仓位
- 再改风控
- 最后才改策略和因子

这样你才知道结果变化到底来自哪一步，而不是一下子把所有变量都搅在一起。
