# Quant 项目说明书

这是一个面向量化交易研究与模拟部署的 Python 工程。  
它现在采用比较严格的流程：

1. `train`
   只在训练区间做研究和调参
2. `freeze`
   把选中的参数冻结成文件
3. `test`
   用样本外区间验证冻结后的结果
4. `walk-forward`
   用多个连续时间窗口检查稳定性
5. `deploy`
   把冻结后的策略部署到 Alpaca Paper 模拟盘

这套流程的核心目的，是减少“看完测试集又回头调参数”这种最常见的回测污染。

---

## 1. 这个项目适合怎么理解

如果你是量化新手，可以把整个项目拆成 5 层来看：

- 数据层
  - 从 Alpaca 拉历史日线
- 策略层
  - 把行情转换成交易信号
- 仓位层
  - 决定每个标的分配多少资金
- 风控层
  - 控制单标的权重、总敞口、回撤等
- 流程层
  - 决定现在是在训练、测试、做 walk-forward 还是部署

你不需要一次把所有代码都看懂。更推荐先按下面顺序读：

1. [main.py](/C:/Users/15350/Desktop/coding/quant/main.py)
2. [strategy/base_strategy.py](/C:/Users/15350/Desktop/coding/quant/strategy/base_strategy.py)
3. [strategy/trend/trend.py](/C:/Users/15350/Desktop/coding/quant/strategy/trend/trend.py)
4. [strategy/mean_reversion/mean_reversion.py](/C:/Users/15350/Desktop/coding/quant/strategy/mean_reversion/mean_reversion.py)
5. [portfolio/position_sizing.py](/C:/Users/15350/Desktop/coding/quant/portfolio/position_sizing.py)
6. [risk/management.py](/C:/Users/15350/Desktop/coding/quant/risk/management.py)
7. [backtest/train.py](/C:/Users/15350/Desktop/coding/quant/backtest/train.py)
8. [backtest/test.py](/C:/Users/15350/Desktop/coding/quant/backtest/test.py)
9. [backtest/walk_forward.py](/C:/Users/15350/Desktop/coding/quant/backtest/walk_forward.py)

---

## 2. 目录结构说明

### 新架构

- [main.py](/C:/Users/15350/Desktop/coding/quant/main.py)
  - 新的统一命令入口
- [strategy/](/C:/Users/15350/Desktop/coding/quant/strategy)
  - 放策略逻辑
- [regime/](/C:/Users/15350/Desktop/coding/quant/regime)
  - 放市场状态识别逻辑
- [portfolio/](/C:/Users/15350/Desktop/coding/quant/portfolio)
  - 放仓位分配逻辑
- [risk/](/C:/Users/15350/Desktop/coding/quant/risk)
  - 放风控逻辑
- [backtest/](/C:/Users/15350/Desktop/coding/quant/backtest)
  - 放训练、测试和 walk-forward 流程
- [config/](/C:/Users/15350/Desktop/coding/quant/config)
  - 放运行期配置
- [artifacts/](/C:/Users/15350/Desktop/coding/quant/artifacts)
  - 放冻结参数和报告
- [tests/](/C:/Users/15350/Desktop/coding/quant/tests)
  - 放测试

### 旧架构

- [main/](/C:/Users/15350/Desktop/coding/quant/main)
  - 旧版扫描和交易脚本
- [utils/](/C:/Users/15350/Desktop/coding/quant/utils)
  - 旧版工具函数

保留旧架构是为了方便你对照和渐进迁移，不是让你同时维护两套完全独立系统。

---

## 3. 每个核心文件大概负责什么

### 统一入口

- [main.py](/C:/Users/15350/Desktop/coding/quant/main.py)
  - 负责接收命令行参数，并分发到 `train`、`test`、`walk-forward`、`deploy`

### 策略

- [strategy/base_strategy.py](/C:/Users/15350/Desktop/coding/quant/strategy/base_strategy.py)
  - 规定所有策略必须实现什么接口
- [strategy/trend/trend.py](/C:/Users/15350/Desktop/coding/quant/strategy/trend/trend.py)
  - 趋势突破策略
- [strategy/mean_reversion/mean_reversion.py](/C:/Users/15350/Desktop/coding/quant/strategy/mean_reversion/mean_reversion.py)
  - 均值回归策略

### 状态识别、仓位、风控

- [regime/detection.py](/C:/Users/15350/Desktop/coding/quant/regime/detection.py)
  - 判断当前更像趋势市还是震荡市
- [portfolio/position_sizing.py](/C:/Users/15350/Desktop/coding/quant/portfolio/position_sizing.py)
  - 根据信号计算资金权重
- [risk/management.py](/C:/Users/15350/Desktop/coding/quant/risk/management.py)
  - 限制单标的权重、总敞口和回撤

### 回测与验证

- [backtest/train.py](/C:/Users/15350/Desktop/coding/quant/backtest/train.py)
  - 用训练集搜索参数并冻结
- [backtest/test.py](/C:/Users/15350/Desktop/coding/quant/backtest/test.py)
  - 用样本外区间做 OOS 测试
- [backtest/walk_forward.py](/C:/Users/15350/Desktop/coding/quant/backtest/walk_forward.py)
  - 用多个连续窗口做稳定性检查

### 配置与产物

- [config/runtime.yaml](/C:/Users/15350/Desktop/coding/quant/config/runtime.yaml)
  - 运行期可以调的参数
- [config/symbols.txt](/C:/Users/15350/Desktop/coding/quant/config/symbols.txt)
  - 股票池
- [artifacts/frozen_params/](/C:/Users/15350/Desktop/coding/quant/artifacts/frozen_params)
  - 冻结后的参数
- [artifacts/reports/](/C:/Users/15350/Desktop/coding/quant/artifacts/reports)
  - 各类报告输出

---

## 4. 环境准备

### Python 环境

你现在已经有一个 conda 环境：

- `quant`

推荐以后都在这个环境里运行项目。

### 安装依赖

如果环境里还没装完整依赖，在项目根目录执行：

```bash
conda activate quant
python -m pip install -r requirements.txt
```

当前 `requirements.txt` 里主要包括：

- `alpaca-py`
- `pandas`
- `numpy`
- `python-dateutil`
- `python-dotenv`
- `PyYAML`
- `pytest`

### `.env` 配置

项目根目录放一个 `.env` 文件。

推荐写法：

```env
ALPACA_API_KEY=你的_paper_key
ALPACA_API_SECRET=你的_paper_secret
```

为了兼容旧脚本，也支持：

```env
ALPACA_PAPER1_API_KEY_ID=你的_paper_key
ALPACA_PAPER1_API_SECRET_KEY=你的_paper_secret
```

如果你还要用邮件模块，再补：

```env
EMAIL_SENDER=你的发件邮箱
EMAIL_PASSWORD=你的邮箱密码或授权码
EMAIL_RECEIVER=你的收件邮箱
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
```

---

## 5. 最重要的配置文件怎么改

### 股票池

文件：

- [config/symbols.txt](/C:/Users/15350/Desktop/coding/quant/config/symbols.txt)

规则：

- 每行一个股票代码
- 自动转大写
- 以 `#` 开头的行会被忽略

示例：

```text
AAPL
MSFT
NVDA
# TSLA
AMZN
```

### 运行期参数

文件：

- [config/runtime.yaml](/C:/Users/15350/Desktop/coding/quant/config/runtime.yaml)

这里允许你调整 3 类内容：

- `regime`
  - 市场状态识别参数
- `position`
  - 仓位方法和目标波动
- `risk`
  - 权重限制、止损止盈、滑点等

如果你是新手，最建议优先微调这些字段：

- `position.method`
- `position.max_positions`
- `position.target_vol_annual`
- `risk.max_weight_per_asset`
- `risk.max_gross_exposure`
- `risk.stop_loss_pct`
- `risk.take_profit_pct`

不建议你一开始就频繁改策略参数本身。

---

## 6. 标准使用流程

### 第一步：训练

作用：

- 在训练区间上搜索参数
- 选出表现较好的组合
- 写入冻结参数文件

命令：

```bash
conda activate quant
python main.py train --start 2016-01-01 --end 2021-12-31 --strategies trend mean_reversion --objective sharpe
```

输出：

- [artifacts/frozen_params/](/C:/Users/15350/Desktop/coding/quant/artifacts/frozen_params)
- [artifacts/reports/](/C:/Users/15350/Desktop/coding/quant/artifacts/reports)

### 第二步：样本外测试

作用：

- 在没有参与训练的数据上验证策略

命令：

```bash
conda activate quant
python main.py test --start 2022-01-01 --end 2024-12-31 --strategies trend mean_reversion
```

重点：

- 这个阶段不应该重新调参数
- 如果结果差，不应该直接改 frozen 参数“再试一次”

### 第三步：Walk-forward

作用：

- 看策略在多个连续时间窗口上是否稳定

命令：

```bash
conda activate quant
python main.py walk-forward --start 2016-01-01 --end 2024-12-31 --strategies trend mean_reversion --train-years 3 --test-months 6 --step-months 3 --gap-days 1
```

### 第四步：部署到 Paper

作用：

- 用冻结后的策略和运行期参数，生成最新目标仓位
- 提交到 Alpaca Paper 模拟盘

先 dry-run：

```bash
conda activate quant
python main.py deploy --dry-run
```

确认输出没问题后再真实提交：

```bash
conda activate quant
python main.py deploy
```

---

## 7. 新手最常改哪些地方

### 场景 1：我想换股票池

改：

- [config/symbols.txt](/C:/Users/15350/Desktop/coding/quant/config/symbols.txt)

### 场景 2：我想让系统少买一点股票

改：

- [config/runtime.yaml](/C:/Users/15350/Desktop/coding/quant/config/runtime.yaml)

重点字段：

- `position.max_positions`
- `risk.max_weight_per_asset`
- `risk.max_gross_exposure`

### 场景 3：我想让趋势策略更慢一点

改：

- [strategy/trend/trend.py](/C:/Users/15350/Desktop/coding/quant/strategy/trend/trend.py)

重点字段：

- `breakout_window`
- `momentum_window`

### 场景 4：我想让均值回归更容易触发

改：

- [strategy/mean_reversion/mean_reversion.py](/C:/Users/15350/Desktop/coding/quant/strategy/mean_reversion/mean_reversion.py)

重点字段：

- `entry_z`
- `lookback`

### 场景 5：我想让风控更严格

改：

- [risk/management.py](/C:/Users/15350/Desktop/coding/quant/risk/management.py)
- [config/runtime.yaml](/C:/Users/15350/Desktop/coding/quant/config/runtime.yaml)

---

## 8. 旧版脚本怎么用

如果你暂时还想用最早那套扫描/下单流程，也可以继续：

- [main/main_scan.py](/C:/Users/15350/Desktop/coding/quant/main/main_scan.py)
  - 生成扫描结果和候选 CSV
- [main/main_trade.py](/C:/Users/15350/Desktop/coding/quant/main/main_trade.py)
  - 读取候选 CSV 并下模拟单

这套旧流程的优点是简单直观，适合入门理解。  
新流程的优点是更工程化、更接近真实研究流程。

---

## 9. 测试文件是干什么的

测试目录：

- [tests/test_splits.py](/C:/Users/15350/Desktop/coding/quant/tests/test_splits.py)
  - 保证时间窗口逻辑没有穿越
- [tests/test_freeze_manifest.py](/C:/Users/15350/Desktop/coding/quant/tests/test_freeze_manifest.py)
  - 保证冻结参数文件和清单能正常生成
- [tests/test_no_lookahead.py](/C:/Users/15350/Desktop/coding/quant/tests/test_no_lookahead.py)
  - 保证趋势策略没有前视偏差

运行方式：

```bash
conda activate quant
python -m pytest -q
```

如果环境没装好，先执行：

```bash
python -m pip install -r requirements.txt
```

---

## 10. 你应该遵守的研究纪律

最关键的不是代码，而是流程纪律：

- 训练集可以调参数
- 样本外测试集不能反过来指导参数微调
- Walk-forward 是稳定性检查，不是再次调参
- 部署阶段默认只调整运行期参数，不调整 frozen 参数

建议你把下面这条记住：

“看到 OOS 不好，不是马上改参数重跑；先判断是运行期配置问题，还是策略整体失效。”

---

## 11. 常见问题

### 为什么要冻结参数

因为如果你看完测试集再改参数，测试集就不再是“真正没见过的数据”了。

### 为什么要做 Walk-forward

因为一次 OOS 好，不代表很多时段都好。Walk-forward 更看重稳定性。

### 为什么先用 Alpaca Paper

因为真实下单前，先让整个流程在模拟环境里跑顺，风险会小很多。

### 为什么还保留旧脚本

因为旧脚本更容易理解，也方便做最小可运行版本；新架构则更适合长期演进。

---

## 12. 下一步建议

如果你想继续把这个项目做稳，我建议下一步优先做这三件事：

1. 在 `quant` 环境里补齐依赖并跑通测试
2. 先只使用 `trend` 策略做一次完整的 `train -> test -> deploy --dry-run`
3. 再逐步微调 `config/runtime.yaml`，不要急着同时改很多策略参数
