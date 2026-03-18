# Modular Quant Trading Project

这个项目现在按 `Train -> Freeze -> OOS Test -> Walk-forward -> Deploy` 的流程组织，目标是把研究、验证和部署拆开，并且明确限制样本外阶段不能回头调参数。

## 新结构

- `strategy/`
  - `base_strategy.py`：统一策略接口
  - `trend/`：趋势突破策略
  - `mean_reversion/`：均值回归策略
- `regime/`
  - `detection.py`：运行期状态识别
- `portfolio/`
  - `position_sizing.py`：仓位方法
- `risk/`
  - `management.py`：风险约束
- `backtest/`
  - `train.py`：训练和冻结参数
  - `test.py`：只读 frozen 参数做 OOS
  - `walk_forward.py`：冻结参数下做多窗口稳定性验证
- `config/`
  - `runtime.yaml`：运行期允许调整的 regime/position/risk 参数
  - `symbols.txt`：交易股票池
- `artifacts/`
  - `frozen_params/`：冻结后的参数文件和 `MANIFEST.json`
  - `reports/`：训练、测试和 walk-forward 报告
- `main.py`
  - 新的统一入口，支持 `train`、`test`、`walk-forward`、`deploy`

原来的 `main/` 和 `utils/` 目录保留为 legacy 链路，方便你继续对照原始扫描和下单逻辑。

## 环境变量

根目录 `.env` 里推荐使用：

```env
ALPACA_API_KEY=your_paper_key
ALPACA_API_SECRET=your_paper_secret
```

为了兼容老代码，也仍然支持：

```env
ALPACA_PAPER1_API_KEY_ID=your_paper_key
ALPACA_PAPER1_API_SECRET_KEY=your_paper_secret
```

## 运行方式

安装依赖：

```bash
pip install -r requirements.txt
```

训练并冻结参数：

```bash
python main.py train --start 2016-01-01 --end 2021-12-31 --strategies trend mean_reversion --objective sharpe
```

样本外测试：

```bash
python main.py test --start 2022-01-01 --end 2024-12-31 --strategies trend mean_reversion
```

Walk-forward：

```bash
python main.py walk-forward --start 2016-01-01 --end 2024-12-31 --strategies trend mean_reversion --train-years 3 --test-months 6 --step-months 3
```

部署到 Alpaca Paper：

```bash
python main.py deploy --dry-run
```

## 参数纪律

- `train` 阶段可以搜索参数
- 训练结束后写入 `artifacts/frozen_params/*.json`
- `test`、`walk-forward`、`deploy` 只读取 frozen 参数
- 运行期只建议调整 `config/runtime.yaml`
- 如果策略失效，不要在 OOS 上回头修参数，而是重新走完整研发流程
