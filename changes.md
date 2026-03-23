# Changes Log

## 2026-03-23 1.0.39（Mixture 邻居加权融合）

### 把 OOS 的 mix-aware 选择从“最近邻单模型”升级成“多邻居加权组合”

- 更新了 [pipelines/run_alpha_combo_regime_switch.py](pipelines/run_alpha_combo_regime_switch.py)
  - 新增 `mixture_neighbor_count` 和 `mixture_distance_power`
  - OOS mix 窗口不再只匹配一个最近训练窗口，而是会选最近的多个训练 mix 邻居
  - 每个邻居先按自己的因子、权重、`top_n` 和执行门槛生成目标持仓
  - 再按 mix 距离做反比加权，在组合层合成最终权重后回测
  - 报告里新增：
    - 邻居数量
    - 邻居权重
    - 匹配到的训练窗口列表
  - Markdown 报告现在会明确标注 `top-N inverse-distance ensemble`
- 更新了 [main.py](main.py)
  - `alpha-combo-regime-switch` 新增命令行参数：
    - `--mixture-neighbor-count`
    - `--mixture-distance-power`
- 更新了 [notifications/emailer.py](notifications/emailer.py)
  - `selected_factors(选中因子)` 现在支持展示多组 ensemble 因子
  - 邮件会显示：
    - `ensemble_member_count(融合近邻数)`
    - `matched_train_windows(匹配训练窗口)`

### 测试

- 更新了 [tests/test_regime_mixture_research.py](tests/test_regime_mixture_research.py)
  - 新增 mix 邻居选择和权重归一化测试
  - 新增数值型诊断信息加权聚合测试
- 更新了 [tests/test_emailer.py](tests/test_emailer.py)
  - 新增多组 ensemble 因子邮件展示测试
- 当前相关测试通过：`12 passed`

## 2026-03-22 1.0.38（轻量 ML 权重学习接入 Regime Switch）

### 开始把机器学习约束在“学组合权重”这一层

- 新增了 [research/ml_factor_weights.py](research/ml_factor_weights.py)
  - 使用轻量 `ridge` 正则化线性模型
  - 只在训练期学习小规模候选因子的固定权重
  - 样本外只拿固定权重打分，不做在线再训练
  - 会强制沿用单因子研究已经确认的方向，不让 ML 随意翻多空方向
- 更新了 [pipelines/run_alpha_combo_regime_switch.py](pipelines/run_alpha_combo_regime_switch.py)
  - 每个候选组合现在会同时比较：
    - `heuristic` 启发式权重
    - `ridge_ml` 训练期机器学习权重
  - 只有当 `ridge_ml` 学出来的权重与启发式权重确实有明显差异时，才会作为新候选进入正式搜索，尽量避免只是徒增复杂度
- 更新了 [notifications/emailer.py](notifications/emailer.py)
  - 邮件里现在会直接显示 `weighting_method(权重生成方式)`，便于区分结果到底来自启发式还是 ML 权重

### 测试

- 新增了 [tests/test_ml_factor_weights.py](tests/test_ml_factor_weights.py)
  - 覆盖 `ridge` 权重学习的基础行为
- 更新了 [tests/test_emailer.py](tests/test_emailer.py)
- 当前相关测试通过：`11 passed`

## 2026-03-22 1.0.37（允许不开固定止盈的进攻型执行搜索）

### 继续排查是不是策略层把赢家提前砍掉了

- 更新了 [backtest/engine.py](backtest/engine.py)
  - 当 `take_profit_pct <= 0` 时，固定止盈会被显式关闭
  - 当 `stop_loss_pct <= 0` 时，固定止损会被显式关闭
  - 当 `trailing_stop_atr_multiple <= 0` 时，ATR 追踪止损会被显式关闭
- 更新了 [pipelines/run_alpha_combo_regime_switch.py](pipelines/run_alpha_combo_regime_switch.py)
  - 默认执行 profile 现在会正式搜索一类：
    - 不开固定止盈
    - 更长持有
    - 更强 rank tilt
    - 更集中的动态持仓

### 测试

- 更新了 [tests/test_portfolio_risk_overlay.py](tests/test_portfolio_risk_overlay.py)
  - 新增“不启用固定止盈”测试
- 更新了 [tests/test_regime_mixture_research.py](tests/test_regime_mixture_research.py)
  - 新增无固定止盈 profile 断言
- 当前相关测试通过：`12 passed`

## 2026-03-22 1.0.36（Regime Switch 目标函数改为平均年化优先）

### 修正了研究目标，不再把“单窗口达标率”误当成最终目标

- 更新了 [pipelines/run_alpha_combo_regime_switch.py](pipelines/run_alpha_combo_regime_switch.py)
  - `regime-switch` 的候选评分现在更偏向：
    - 在控制回撤的前提下提高 `OOS CAGR`
    - 用 `avg_cagr` 作为更核心的结果口径
  - aggressive / conservative 的窗口内选择不再要求“单窗口先达到 15% 年化”才算可用
  - `mixture_research.oos_validation_summary` 新增：
    - `avg_cagr_gap`
    - `avg_cagr_target_met`
- 更新了 [notifications/emailer.py](notifications/emailer.py)
  - 状态切换邮件现在会直接告诉你“平均年化目标是否达成”

### 测试

- 更新了 [tests/test_regime_mixture_research.py](tests/test_regime_mixture_research.py)
- 更新了 [tests/test_emailer.py](tests/test_emailer.py)
- 当前相关测试通过：`10 passed`

## 2026-03-22 1.0.35（收益率优先的激进搜索扩展）

### 继续把 regime-switch 从“稳”往“更有收益弹性”推

- 更新了 [factors/offense.py](factors/offense.py)
  - 新增更偏进攻的因子：
    - `upside_followthrough_10_20`
    - `breakout_thrust_20_60`
    - `gap_trend_acceleration_20_60`
    - `trend_strength_spread_20_60`
    - `squeeze_followthrough_5_20_60`
- 更新了 [factors/hybrid.py](factors/hybrid.py)
  - 新增更偏突破延续/买盘扩散的中层组合因子：
    - `upside_breakout_fusion_20_60`
    - `intraday_breakout_followthrough_10_60`
    - `gap_momentum_balance_20_60`
    - `trend_pressure_release_20_60`

### 正式把“更激进的持仓和退出策略”接进 regime-switch 搜索

- 更新了 [pipelines/run_alpha_combo_regime_switch.py](pipelines/run_alpha_combo_regime_switch.py)
  - aggressive 搜索现在会正式比较：
    - 更集中的 `top_n`
    - 更高的 `gross_exposure`
    - 更长持有周期
    - 更宽松的 `stop_loss_pct`
    - 更高的 `take_profit_pct`
    - 更松的 `trailing_stop_atr_multiple`
  - conservative overlay 现在也会一起比较不同 `top_n`，不再固定持仓广度
  - 新增默认 `top_n` 候选，会自动尝试比当前更集中的持仓数
- 更新了 [main.py](main.py)
  - `alpha-combo-regime-switch` 新增：
    - `--top-n-grid`
    - `--stop-loss-pct-grid`
    - `--take-profit-pct-grid`
    - `--trailing-stop-atr-multiple-grid`
  - 修复了若干执行参数只暴露命令行但没有真正写回 `BacktestConfig` 的问题

### 测试

- 更新了 [tests/test_new_factor_families.py](tests/test_new_factor_families.py)
- 更新了 [tests/test_regime_mixture_research.py](tests/test_regime_mixture_research.py)
- 当前相关测试通过：`9 passed`

## 2026-03-22 1.0.34（邮件通知可读性修复）

### 修复了 Regime Switch 邮件只发 JSON 文件名的问题

- 更新了 [notifications/emailer.py](notifications/emailer.py)
  - `alpha-combo-regime-switch` 现在会直接发：
    - 样本外窗口数
    - 达标窗口占比
    - 平均年化收益率
    - 平均最大回撤
    - 平均夏普比率
    - 最新窗口选中的版本、因子、执行参数和交易过滤
  - 邮件里的核心英文指标现在会带中文名，例如：
    - `sharpe(夏普比率)`
    - `cagr(年化收益率)`
    - `max_dd(最大回撤)`
  - 报告文件列表改成逐行展示，不再直接塞一整段 JSON
- 兼容了缺少 `python-dotenv` 的环境
  - 没装 `dotenv` 时本地补发邮件和正文渲染也不会直接崩掉

### 测试

- 新增了 [tests/test_emailer.py](tests/test_emailer.py)
  - 覆盖 `regime-switch` 邮件正文摘要
  - 覆盖双语指标显示
  - 覆盖无 `dotenv` 环境下的导入

## 2026-03-22 1.0.32（组合级新增仓位限速）

### 继续优化交易执行，不再默认一步跳到目标仓位

- 更新了 [backtest/engine.py](backtest/engine.py)
  - 新增 `max_entry_turnover_per_rebalance`
  - 这个限制只约束“新增仓位”的速度，不阻碍卖出、止损和去杠杆
  - 目的不是把收益硬调好看，而是减少高噪音环境下的猛切仓
- 更新了 [config/runtime.yaml](config/runtime.yaml)
  - 把该执行参数接入默认回测配置
- 更新了 [pipelines/run_alpha_combo_regime_switch.py](pipelines/run_alpha_combo_regime_switch.py)
  - 该参数已接入执行策略搜索 profile
- 更新了 [main.py](main.py)
  - `alpha-combo-regime-switch` 新增 `--max-entry-turnover-per-rebalance-grid`

## 2026-03-22 1.0.33（动态持仓广度 + blocked ratio 入评分）

### 继续把非因子层的真实交易约束接进研究

- 更新了 [backtest/engine.py](backtest/engine.py)
  - 新增 `dynamic_breadth_score_threshold`
  - 新增 `min_dynamic_positions`
  - 允许按当日强信号数量动态收缩持仓广度，而不是始终机械持有固定 `top_n`
- 更新了 [pipelines/run_alpha_combo_regime_switch.py](pipelines/run_alpha_combo_regime_switch.py)
  - 执行 profile 现在会搜索动态广度和更长持有周期
  - `trade filter` 的 `blocked_ratio` 已直接进入候选评分，不再只是诊断信息
- 更新了 [main.py](main.py)
  - `alpha-combo-regime-switch` 新增：
    - `--dynamic-breadth-score-threshold-grid`
    - `--min-dynamic-positions-grid`

### 测试

- 更新了 [tests/test_execution_controls.py](tests/test_execution_controls.py)
  - 新增动态持仓广度测试
- 更新了 [tests/test_regime_mixture_research.py](tests/test_regime_mixture_research.py)
  - 新增动态广度执行 profile 测试

### 测试

- 更新了 [tests/test_portfolio_risk_overlay.py](tests/test_portfolio_risk_overlay.py)
  - 新增新增仓位限速测试

## 2026-03-22 1.0.30（执行策略正式接入 Regime Switch 搜索）

### 把“选股/交易执行”从手动调参变成正式研究对象

- 更新了 [pipelines/run_alpha_combo_regime_switch.py](pipelines/run_alpha_combo_regime_switch.py)
  - 新增了一套窄而可解释的执行 profile 搜索：
    - `min_score_threshold`
    - `rank_weight_power`
    - `hold_rank_buffer`
    - `score_hysteresis`
    - `rebalance_every_n_days`
  - aggressive 组合现在也会先过一轮执行策略筛选，不再默认只比较“因子 + 风控”
  - conservative overlay 现在会联合搜索“组合级风控 + 执行策略”，不是只搜回撤闸门
  - 评分里加入了轻量 `avg_turnover` 惩罚，避免因为高频噪音换仓把样本内结果抬得太好看
- 更新了 [main.py](main.py)
  - `alpha-combo-regime-switch` 新增执行策略搜索网格参数：
    - `--rebalance-every-n-days-grid`
    - `--min-score-threshold-grid`
    - `--rank-weight-power-grid`
    - `--hold-rank-buffer-grid`
    - `--score-hysteresis-grid`
    - `--max-holding-days-grid`

### 测试

- 更新了 [tests/test_regime_mixture_research.py](tests/test_regime_mixture_research.py)
  - 新增执行策略搜索网格的默认行为测试
  - 新增显式搜索空间测试

## 2026-03-22 1.0.31（Trade Filter 正式接入 Regime Switch 搜索）

### 把下单前过滤也变成正式研究对象

- 更新了 [pipelines/run_alpha_combo_regime_switch.py](pipelines/run_alpha_combo_regime_switch.py)
  - aggressive / conservative 搜索现在都会同时比较 `trade_filters`
  - mixture library 与 OOS window 验证不再丢失已选过滤配置
  - 默认只搜索一小组可解释的过滤 profile，避免无边界扩大搜索空间
- 更新了 [main.py](main.py)
  - `alpha-combo-regime-switch` 新增过滤网格参数：
    - `--min-close-location-1-grid`
    - `--max-true-range-pct-1-grid`
    - `--max-volume-surprise-5-grid`
    - `--max-abs-ma-distance-20-grid`
    - `--min-liquidity-20-grid`

### 测试

- 更新了 [tests/test_regime_mixture_research.py](tests/test_regime_mixture_research.py)
  - 新增 trade filter profile 默认行为测试
  - 新增显式过滤搜索空间测试

## 2026-03-21 1.0.29（独立后台报告 watcher）

### 不再依赖会话存活来做轮询

- 新增了 [scripts/regime_report_watch.sh](scripts/regime_report_watch.sh)
  - 增加了 `check-once` 模式，便于接系统级调度
  - 状态、PID、日志统一落到 `artifacts/runtime/`
  - 发现新的 `alpha_combo_regime_switch_*.json` 时会记录摘要，macOS 环境下还会尝试弹本地通知

## 2026-03-21 1.0.28（持仓保留 buffer + 滞后退出）

### 继续往选股和交易执行层优化

- 更新了 [backtest/engine.py](backtest/engine.py)
  - 新增 `hold_rank_buffer`
  - 新增 `score_hysteresis`
  - 现在可以让已有持仓在“略微掉出 top-N”或“短暂跌破进场阈值”时继续保留，不再被噪音信号立刻洗掉
- 更新了 [main.py](main.py)
  - `alpha-combo-regime-switch` 新增：
    - `--hold-rank-buffer`
    - `--score-hysteresis`
- 更新了 [config/runtime.yaml](config/runtime.yaml)
  - 把这两个执行参数接进默认回测配置

### 测试

- 更新了 [tests/test_execution_controls.py](tests/test_execution_controls.py)
- 新增了“持仓保留 buffer”和“滞后退出”两类执行层测试

## 2026-03-21 1.0.27（Regime Switch 接入执行参数）

### 正式搜索现在可以直接研究选股和交易执行参数

- 更新了 [main.py](main.py)
  - `alpha-combo-regime-switch` 新增：
    - `--min-score-threshold`
    - `--rank-weight-power`
  - 这样可以在正式 regime-switch 搜索里直接比较“少持弱信号”和“高分重仓”这类执行策略，而不只是继续换因子

### 当前方向

- 因子层继续追求更强收益弹性
- 选股层开始允许低信号日少持仓
- 交易层开始允许按排名强度倾斜仓位

## 2026-03-21 1.0.26（选股阈值 + 强度加权仓位）

### 给选股和交易执行补了两个直接可控的杠杆

- 更新了 [backtest/engine.py](backtest/engine.py)
  - 新增 `min_score_threshold`，允许在低信号日期少持仓，不再默认硬塞满 `top-N`
  - 新增 `rank_weight_power`，允许按排名强度倾斜仓位，而不是始终等权
- 更新了 [config/runtime.yaml](config/runtime.yaml)
  - 把这两个执行参数接进默认回测配置

### 测试

- 新增了 [tests/test_execution_controls.py](tests/test_execution_controls.py)
- 当前相关测试共 `7` 项通过

## 2026-03-21 1.0.25（进攻型因子族扩展）

### 新增一组更偏收益弹性的因子

- 新增了 [factors/offense.py](factors/offense.py)
  - `momentum_acceleration_20_60`
  - `upside_pressure_20`
  - `intraday_followthrough_5_20`
  - `squeeze_breakout_5_20_60`
- 更新了 [factors/__init__.py](factors/__init__.py)
  - 把新的 `offense` 因子族接入统一注册表和 `build_factor_panel`

### 这轮扩展的目标

- 不再优先给组合补“更稳”的因子
- 开始直接补收益弹性、趋势加速、强收盘跟随和压缩释放这类更偏进攻的信号
- 后续组合搜索会在保持低相关约束的前提下，允许更复杂的 4 因子组合去争取更高收益

### 测试

- 更新了 [tests/test_new_factor_families.py](tests/test_new_factor_families.py)
- 当前相关测试继续通过

## 2026-03-21 1.0.24（稳定性筛选 + 新中层组合因子）

### 给因子筛选补了分段稳定性约束

- 更新了 [research/factor_tests.py](research/factor_tests.py)
  - 单因子验证现在会额外记录分段 `rank_ic` / `spread` 稳定性
  - 新增 `stability_segments` 和 `min_stability_segment_days`
- 更新了 [research/factor_combo_search.py](research/factor_combo_search.py)
  - 因子池筛选会检查 train / OOS 的分段一致性，不再只看整体均值
  - `selection_score` 也加入了稳定性奖励，尽量减少“均值好看但分段来回翻”的信号
- 更新了 [main.py](main.py)
  - 把新的稳定性配置接进运行时配置和 regime-switch 命令入口

### 继续沿着最近反复冒头的结构扩中层组合因子

- 更新了 [factors/hybrid.py](factors/hybrid.py)
  - 新增：
    - `intraday_quiet_strength_10_60`
    - `gap_strength_balance_20_10`
    - `channel_defense_20_60`
    - `gap_breakout_quality_20_60`

### 测试

- 新增了 [tests/test_factor_combo_stability.py](tests/test_factor_combo_stability.py)
- 更新了 [tests/test_new_factor_families.py](tests/test_new_factor_families.py)
- 当前相关测试共 `5` 项通过

## 2026-03-21 1.0.23（Regime Switch 候选池缩小回归修复）

### 修复了聚焦搜索时冻结模型对比会缺列的问题

- 更新了 [pipelines/run_alpha_combo_regime_switch.py](pipelines/run_alpha_combo_regime_switch.py)
  - 当 `--candidate-factors` 缩小研究候选池时，冻结的激进版 / 保守版对比会自动回退到完整因子面板
  - 避免在对比旧模型时因为 `reversal_5`、`trend_pullback_20_5` 这类未纳入本轮候选池的因子缺失而直接报错

### 测试

- 更新了 [tests/test_regime_mixture_research.py](tests/test_regime_mixture_research.py)
- 当前 `regime mixture` 与新增因子测试共 `4` 项通过

## 2026-03-21 1.0.22（工程化组合因子扩展）

### 新增一组可解释的中层组合因子

- 新增了 [factors/hybrid.py](factors/hybrid.py)
  - `gap_channel_alignment_20_60`
  - `intraday_resilience_10_20`
  - `quiet_trend_pressure_20`
  - `stable_range_breakout_20_60`
  - `gap_risk_balance_20`
  - `trend_structure_alignment_20_60`
  - `breakout_quality_60`
- 更新了 [factors/__init__.py](factors/__init__.py)
  - 把新的 `hybrid` 因子族接入统一注册表和 `build_factor_panel`

### 这轮组合因子的设计原则

- 不直接把很多主题混成黑箱总分
- 只围绕已经在 mix-aware 研究里冒头的方向做少量中层组合
- 每个组合因子都保持可解释，方便继续做 train / OOS 严格验证

### 测试

- 更新了 [tests/test_new_factor_families.py](tests/test_new_factor_families.py)
- 当前新增组合因子注册与生成测试通过

## 2026-03-21 1.0.21（冒头因子家族二次拆分）

### 继续围绕已经冒头的信号做定向扩展

- 更新了 [factors/breakout.py](factors/breakout.py)
  - 新增：
    - `breakout_distance_60`
    - `ma_distance_60`
    - `ma_gap_20_60`
- 更新了 [factors/microstructure.py](factors/microstructure.py)
  - 新增：
    - `overnight_gap_20`
    - `intraday_strength_10`
    - `intraday_hit_rate_10`
    - `channel_position_20`
- 更新了 [factors/risk_structure.py](factors/risk_structure.py)
  - 新增：
    - `downside_risk_60`
    - `downside_to_total_vol_20`
    - `gap_volatility_60`
    - `gap_downside_vol_20`
    - `vol_of_range_60`
- 更新了 [factors/volatility.py](factors/volatility.py)
  - 新增：
    - `low_volatility_60`
    - `vol_compression_5_20`

### 这轮扩展的原则

- 不再广撒网加新主题
- 只围绕已经在最新 report 里冒头的：
  - `gap_volatility_20`
  - `intraday_strength_5`
  - `ma_distance_20`
  - `vol_of_range_20`
  - `downside_risk_20`
  - `channel_position_60`
- 把它们拆成：
  - 短中期不同窗口
  - 均值和命中率
  - 总波动和 downside-only 风险
  - 价格位置和均线斜率

### 测试

- 更新了 [tests/test_new_factor_families.py](tests/test_new_factor_families.py)
- 当前新增因子注册与生成测试继续通过

## 2026-03-21 1.0.20（新因子族扩展 + Mix-Aware 搜索提速）

### 新增了四组原子因子族

- 新增 [factors/trend_quality.py](factors/trend_quality.py)
  - `momentum_120_skip_5`
  - `trend_consistency_20`
  - `efficiency_ratio_20`
  - `risk_adjusted_momentum_60`
- 新增 [factors/microstructure.py](factors/microstructure.py)
  - `overnight_gap_5`
  - `intraday_strength_5`
  - `body_to_range_5`
  - `channel_position_60`
- 新增 [factors/flow.py](factors/flow.py)
  - `amihud_illiquidity_20`
  - `volume_dryup_10_60`
  - `obv_trend_20`
  - `dollar_volume_accel_20_60`
- 新增 [factors/risk_structure.py](factors/risk_structure.py)
  - `downside_risk_20`
  - `range_expansion_5_20`
  - `gap_volatility_20`
  - `vol_of_range_20`
- 更新了 [factors/__init__.py](factors/__init__.py)
  - 把这些新因子正式接进统一注册表和 `build_factor_panel`

### Mix-aware 研究链路做了缓存提速

- 更新了 [pipelines/run_alpha_combo_regime_switch.py](pipelines/run_alpha_combo_regime_switch.py)
- 新增了两层缓存：
  - `score_frame` 级缓存
  - 组合级风控 overlay 搜索缓存
- 目的不是改研究逻辑，而是减少窗口回测里的重复算分
- 这样后面做“多轮扩因子 -> 严格筛选 -> 再扩因子”的循环时，不会把时间都浪费在重复计算上

### Regime 搜索参数现在可以从命令行覆盖

- 更新了 [main.py](main.py)
- `alpha-combo-regime-switch` 现在支持：
  - `--candidate-pool-size`
  - `--min-combo-size`
  - `--max-combo-size`
  - `--max-combinations`
  - `--max-pairwise-correlation`
  - `--min-train-rank-ic`
  - `--min-oos-rank-ic`
  - `--min-train-hit-rate`
  - `--min-oos-hit-rate`
- 这样后续做更广的搜索时，不需要去改全局 `runtime.yaml`

### 测试

- 新增 [tests/test_new_factor_families.py](tests/test_new_factor_families.py)
- 已验证：
  - 新因子家族已注册
  - 新因子列能正常生成
- 现有 [tests/test_regime_mixture_research.py](tests/test_regime_mixture_research.py) 继续通过

## 2026-03-21 1.0.19（Regime Mix 研究 + 严格 CAGR 门槛）

### Regime 研究从“硬切四类”升级成“窗口 mix 驱动”

- 更新了 [pipelines/run_alpha_combo_regime_switch.py](pipelines/run_alpha_combo_regime_switch.py)
- 更新了 [main.py](main.py)
- `alpha-combo-regime-switch` 现在不只支持单日硬分类的：
  - `trend_low_vol`
  - `range_low_vol`
  - `trend_high_vol`
  - `range_high_vol`
- 还新增了基于滚动窗口的 mixture-aware 研究：
  - 用一段时间内的 regime 占比作为研究单元，例如 `trend_low_vol 70% + range_low_vol 30%`
  - 先在 train 窗口里生成 mix 原型和对应组合
  - 再拿 OOS 窗口按“最近 mix”做严格匹配验证

### 把 `年化 >= 15%` 写进选择规则

- `AlphaComboRegimeSwitchSpec` 新增了：
  - `target_cagr`
  - `mix_window_days`
  - `mix_step_days`
  - `min_mix_sample_days`
- CLI 新增参数：
  - `--target-cagr`
  - `--mix-window-days`
  - `--mix-step-days`
  - `--min-mix-sample-days`
- 当前选择逻辑不再只看“激进版回撤是否比保守版多 5%”
- 现在会先检查：
  - OOS `CAGR >= target_cagr`
  - OOS `MaxDD <= target_max_dd`
- 只有两者都达标时，才再用回撤容忍差决定选激进还是保守
- 如果两者都不达标，就按：
  - CAGR 缺口
  - 回撤超额
  - Sharpe / Calmar
  做固定优先级比较，避免主观挑数

### 严格性补丁

- 新增测试：
  - [tests/test_regime_mixture_research.py](tests/test_regime_mixture_research.py)
- 补上了 JSON 导出清洗：
  - 非有限浮点数不再写成非法的 `NaN`
  - 会统一转成 `null`

## 2026-03-21 1.0.18（组合级风控 + Regime 切换因子）

### 组合级风控不再继续砍单票止损

- 更新了 [backtest/engine.py](backtest/engine.py)
- 组合回测引擎新增了组合级风险闸门：
  - `portfolio_soft_dd_limit`
  - `portfolio_deleverage_ratio`
  - `portfolio_hard_dd_limit`
  - `portfolio_kill_cooldown_days`
- 逻辑改成：
  - 先保留当前单票止损参数
  - 再额外在组合层做“回撤触发降杠杆 / 熔断冷却”
- 更新了 [config/runtime.yaml](config/runtime.yaml)
  - 把这些组合级风控参数暴露到运行期配置里

### 风控搜索改成“保留当前参数 + 叠加组合级闸门”

- 更新了 [pipelines/run_alpha_combo_risk_search.py](pipelines/run_alpha_combo_risk_search.py)
- 更新了 [main.py](main.py)
- `alpha-combo-risk-search` 现在支持：
  - `--model-path`
  - `--output-model-path`
  - `--portfolio-soft-dd-grid`
  - `--portfolio-deleverage-grid`
  - `--portfolio-hard-dd-grid`
  - `--portfolio-cooldown-days-grid`
- 默认行为也改了：
  - 会优先保留当前模型已有的 `top_n / stop_loss / trailing_stop / max_holding_days`
  - 不再默认继续把单票止损越砍越紧
  - 主要搜索组合级降杠杆 / 熔断参数

### 新的 Overlay 保守版结果

- 新报告：
  - [artifacts/reports/alpha_combo_risk_search_20260320_135146.json](artifacts/reports/alpha_combo_risk_search_20260320_135146.json)
  - [artifacts/reports/alpha_combo_risk_search_20260320_135146.md](artifacts/reports/alpha_combo_risk_search_20260320_135146.md)
- 新冻结文件：
  - [artifacts/selected_factors/low_corr_alpha_overlay_model.json](artifacts/selected_factors/low_corr_alpha_overlay_model.json)
- 这版仍然保留原先的：
  - 因子组合：`-low_volatility_20 + reversal_5 + -trend_pullback_20_5`
  - 单票参数：`gross_exposure=0.40 / stop_loss_pct=2.5% / trailing_stop=1.25 ATR / max_holding_days=3 / top_n=10`
- 额外叠加的组合级风控是：
  - `portfolio_soft_dd_limit = 10%`
  - `portfolio_deleverage_ratio = 0.65`
  - `portfolio_hard_dd_limit = 15%`
  - `portfolio_kill_cooldown_days = 5`
- 结果变化：
  - 旧低回撤版 OOS：`Sharpe 0.189 / CAGR 1.27% / MaxDD -13.48%`
  - 新 overlay 版 OOS：`Sharpe 0.172 / CAGR 1.11% / MaxDD -12.76%`
- 结论：
  - 收益略降
  - 但回撤确实继续被压下来了
  - 而且不是靠进一步砍单票止损做到的

### Regime 切换主线

- 新增 [pipelines/run_alpha_combo_regime_switch.py](pipelines/run_alpha_combo_regime_switch.py)
- 更新了 [main.py](main.py)
- 新增命令：
  - `alpha-combo-regime-switch`
- 新增测试：
  - [tests/test_portfolio_risk_overlay.py](tests/test_portfolio_risk_overlay.py)
  - 已验证组合级降杠杆与熔断冷却行为生效

### Regime 研究结果

- 轻量 frozen-model 对比报告：
  - [artifacts/reports/alpha_combo_regime_compare_20260320_140006.json](artifacts/reports/alpha_combo_regime_compare_20260320_140006.json)
  - [artifacts/reports/alpha_combo_regime_compare_20260320_140006.md](artifacts/reports/alpha_combo_regime_compare_20260320_140006.md)
- 更完整的 regime-switch 报告：
  - [artifacts/reports/alpha_combo_regime_switch_20260320_140012.json](artifacts/reports/alpha_combo_regime_switch_20260320_140012.json)
  - [artifacts/reports/alpha_combo_regime_switch_20260320_140012.md](artifacts/reports/alpha_combo_regime_switch_20260320_140012.md)
- 当前冻结的切换模型：
  - [artifacts/selected_factors/regime_switch_alpha_model.json](artifacts/selected_factors/regime_switch_alpha_model.json)

### 当前切换结论

- `range_low_vol`
  - 找到了新的 regime 组合：`-low_volatility_20 + -momentum_60`
  - 激进版 OOS：`Sharpe 0.459 / CAGR 3.73% / MaxDD -20.88%`
  - 保守版 OOS：`Sharpe 0.478 / CAGR 2.83% / MaxDD -14.48%`
  - 由于激进版回撤超过保守版 `5%` 底线，当前选 `conservative`
- `trend_low_vol`
  - 新候选因子太弱，最终回退到当前冻结主组合
  - 激进版 OOS：`Sharpe 0.173 / CAGR 1.44% / MaxDD -28.96%`
  - 保守版 OOS：`Sharpe -0.007 / CAGR -0.39% / MaxDD -13.14%`
  - 虽然收益被压低，但激进版回撤超出底线太多，当前仍选 `conservative`
- `trend_high_vol`
  - OOS 样本较少，回退到当前冻结主组合
  - 激进版 OOS：`Sharpe 0.094 / CAGR 0.30% / MaxDD -5.21%`
  - 保守版 OOS：`Sharpe 0.185 / CAGR 0.29% / MaxDD -2.00%`
  - 因为激进版只比保守版多 `3.21%` 回撤，仍在 `5%` 底线内，当前选 `aggressive`
- `range_high_vol`
  - OOS 样本太少，当前不强行生成新组合
  - 先沿用冻结模型结果，视作 `fallback`

### 过拟合控制

- 这轮明确收紧了搜索空间，避免为了报表好看乱扫参：
  - regime 搜索只允许很小的候选池和组合数
  - 组合级风控只搜索少量可解释阈值
  - 某个 regime 样本太薄时直接 `fallback`
  - 选择规则固定成“激进版回撤是否超过保守版 + 5%”
- 这意味着当前结论更像“先得到可重复的切换规则”，而不是“把历史最好看的数字调出来”

## 2026-03-21 1.0.17（清理重构后无关文件）

### 项目结构清理

- 重新恢复了根目录主文档：
  - [README.md](README.md)
  - [changes.md](changes.md)
- 删除了重复文档目录：
  - `md_documents/`
- 删除了空目录和缓存：
  - `logs/`
  - `output/`
  - 各层 `__pycache__/`

### 旧策略与旧参数清理

- 保留当前仍接在主命令链路里的策略：
  - [strategy/mean_reversion/mean_reversion.py](strategy/mean_reversion/mean_reversion.py)
  - [strategy/multi_factor_short/multi_factor_short.py](strategy/multi_factor_short/multi_factor_short.py)
- 删除已经退役、且不再被当前注册表和默认配置使用的旧策略目录：
  - `strategy/compression_breakout/`
  - `strategy/low_vol_momentum/`
  - `strategy/pullback/`
  - `strategy/short_reversal/`
  - `strategy/trend/`
  - `strategy/turtle/`
- 同时删除了对应的旧 frozen params，只保留当前仍可能被 `deploy` 使用的：
  - `mean_reversion`
  - `multi_factor_short`

### 历史附加文件清理

- 删除了已被新版结果替代的旧报告：
  - 旧 `pipeline_*`
  - 旧 `train_*`
  - 旧 `test_*`
  - 旧 `walk_forward_*`
  - 旧探索版 `alpha_combo_search_*`
  - 旧探索版 `alpha_combo_risk_search_*`
- 当前保留的核心研究结果只剩：
  - 最新正式因子主线报告
  - 当前激进版 low-corr alpha 组合报告
  - 当前 low-corr alpha walk-forward 报告
  - 当前低回撤 risk-search 报告

## 2026-03-20 1.0.16（低相关 Alpha 风控搜索 + 硬止损实盘化）

### 风控搜索与硬止损

- 更新了 [pipelines/run_composite_portfolio.py](pipelines/run_composite_portfolio.py)
- 之前因子组合路径里会把很多风控参数钝化，现在已经改成真正继承并启用：
  - `hard stop_loss_pct`
  - `take_profit_pct`
  - `trailing_stop_atr_multiple`
  - `max_holding_days`
- 这意味着低相关 alpha 组合现在不只是“研究分数”，而是真的能在组合回测里测试硬止损

### 新的低回撤搜索命令

- 新增 [pipelines/run_alpha_combo_risk_search.py](pipelines/run_alpha_combo_risk_search.py)
- 更新了 [main.py](main.py)
- 现在新增命令：
  - `alpha-combo-risk-search`
- 这个命令会固定当前冻结的大 alpha 组合，然后专门搜索：
  - 总敞口 `gross_exposure`
  - 持仓数 `top_n`
  - 硬止损 `stop_loss_pct`
  - ATR 追踪止损
  - 最大持有天数
- 命令行现在也支持直接传自定义网格：
  - `--gross-exposure-grid`
  - `--top-n-grid`
  - `--stop-loss-grid`
  - `--trailing-stop-grid`
  - `--max-holding-days-grid`

### 本轮正式结果

- 新报告：
  - [artifacts/reports/alpha_combo_risk_search_20260320_122021.json](artifacts/reports/alpha_combo_risk_search_20260320_122021.json)
  - [artifacts/reports/alpha_combo_risk_search_20260320_122021.md](artifacts/reports/alpha_combo_risk_search_20260320_122021.md)
- 新冻结文件：
  - [artifacts/selected_factors/low_corr_alpha_risk_model.json](artifacts/selected_factors/low_corr_alpha_risk_model.json)
- 当前更平衡的低回撤方案是：
  - `gross_exposure = 0.40`
  - `top_n = 10`
  - `hard stop_loss_pct = 2.5%`
  - `trailing stop = 1.25 ATR`
  - `max_holding_days = 3`
- 这组结果：
  - train: `Sharpe 0.696 / CAGR 5.35% / MaxDD -11.19%`
  - OOS: `Sharpe 0.189 / CAGR 1.27% / MaxDD -13.48%`
- 它不是收益最大化版本，但已经把样本外最大回撤压进了 `15%` 以内

### 邮件可读性继续增强

- 更新了 [notifications/emailer.py](notifications/emailer.py)
- 现在 `alpha-combo-risk-search` 邮件也会用“先看结论 -> 再看关键数字 -> 再看建议参数”的人话模板发送

## 2026-03-20 1.0.15（邮件改成易读版）

### 邮件模板重写

- 更新了 [notifications/emailer.py](notifications/emailer.py)
- 现在 `alpha-combo-search` 和 `alpha-combo-walk-forward` 的邮件不再直接塞大段 JSON
- 新结构改成：
  - 先看结论
  - 再看核心数字
  - 再看当前最优组合/权重/候选股票
  - 最后给你一句人话判断
- 目标就是让你打开邮件后 10 秒内能知道：
  - 这轮结果是强还是弱
  - 当前最优因子组合是什么
  - 样本外是不是还在赚钱
  - 是否值得继续研究

### 说明

- 这次没有改研究逻辑，只改了邮件表达方式
- 我会继续沿用这个更易读的邮件模板发后续报告

## 2026-03-20 1.0.14（低相关 Alpha 加过滤并做 Walk-Forward）

### 交易过滤层

- 新增 [portfolio/trade_filters.py](portfolio/trade_filters.py)
- 现在低相关 alpha 组合在真正进组合前会先过一层交易过滤
- 当前过滤重点是：
  - 避开过大单日振幅
  - 避开过于极端的放量
  - 避开离均线过远的票
  - 要求更高一点的流动性
- 第一版过滤过严，实验后已经调成更适合短线反转的“中等强度”配置

### 低相关组合回测增强

- 更新了 [pipelines/run_composite_portfolio.py](pipelines/run_composite_portfolio.py)
- 现在支持：
  - 传入 `raw_panel`
  - 传入 `trade_filters`
  - 输出 `filter_diagnostics`
- 更新了 [research/factor_combo_search.py](research/factor_combo_search.py)
  - 新增 train-only 因子池筛选
  - 组合权重不再只是简单 `+1 / -1`
  - 现在按因子质量分配权重，再叠加方向符号

### 低相关组合 Walk-Forward

- 新增 [pipelines/run_alpha_combo_walk_forward.py](pipelines/run_alpha_combo_walk_forward.py)
- 更新了 [main.py](main.py)
  - 新增命令：
    - `alpha-combo-walk-forward`
- 更新了 [config/runtime.yaml](config/runtime.yaml)
  - 新增：
    - `alpha_trade_filters`

### 本轮正式实验结果

- 新的低相关组合报告：
  - [artifacts/reports/alpha_combo_search_20260320_102529.json](artifacts/reports/alpha_combo_search_20260320_102529.json)
  - [artifacts/reports/alpha_combo_search_20260320_102529.md](artifacts/reports/alpha_combo_search_20260320_102529.md)
- 这轮新的最优组合变成：
  - `-low_volatility_20 + reversal_5 + -trend_pullback_20_5`
- 当前权重大致是：
  - `low_volatility_20 = -0.427`
  - `reversal_5 = +0.321`
  - `trend_pullback_20_5 = -0.252`
- 这轮结果：
  - train: `Sharpe 0.855 / CAGR 20.28% / MaxDD -42.56%`
  - OOS: `Sharpe 0.419 / CAGR 8.00% / MaxDD -30.10%`
- 当前过滤只拦掉了大约 `7%` 的候选行，明显比第一版更健康
- 最新冻结文件仍然写到：
  - [artifacts/selected_factors/low_corr_alpha_model.json](artifacts/selected_factors/low_corr_alpha_model.json)

- 新的 walk-forward 报告：
  - [artifacts/reports/alpha_combo_walk_forward_20260320_110155.json](artifacts/reports/alpha_combo_walk_forward_20260320_110155.json)
  - [artifacts/reports/alpha_combo_walk_forward_20260320_110155.md](artifacts/reports/alpha_combo_walk_forward_20260320_110155.md)
- walk-forward 摘要：
  - 窗口数 `5`
  - 测试窗正 Sharpe 占比 `60%`
  - 测试窗正 CAGR 占比 `60%`
  - 测试窗中位 Sharpe `0.602`
  - 测试窗中位 CAGR `17.97%`
  - 最差测试窗 MaxDD `-43.44%`

## 2026-03-20 1.0.13（低相关多因子 Alpha 组合搜索）

### 低相关组合研究层

- 新增 [research/factor_combo_search.py](research/factor_combo_search.py)
- 新增 [pipelines/run_alpha_combo_search.py](pipelines/run_alpha_combo_search.py)
- 现在支持：
  - 先从单因子结果里识别稳定方向
  - 对稳定负向因子先反号，再进入组合
  - 组合前先检查训练期两两相关性
  - 强制限制 `abs(corr) <= 0.30`
  - 自动尝试多组 2 到 4 因子组合
  - 分别输出 train / OOS 组合回测结果

### 组合回测增强

- 更新了 [pipelines/run_composite_portfolio.py](pipelines/run_composite_portfolio.py)
- `FactorPortfolioSpec` 现在支持 `factor_weights`
- 这意味着 composite alpha 不再只能“全部同方向等权”
- 现在可以显式写成：
  - `low_volatility_20: -1`
  - `reversal_3: +1`

### 主入口与配置

- 更新了 [main.py](main.py)
  - 新增命令：
    - `alpha-combo-search`
- 更新了 [config/runtime.yaml](config/runtime.yaml)
  - 新增：
    - `factor_combo_search`

### 兼容层与 IDE 友好性

- 更新了 [alpha_lab/factors.py](alpha_lab/factors.py)
- 兼容层现在额外暴露 `build_factor_panel(...)`
- 这样旧调用路径和 IDE 静态检查更容易找到入口

### 本轮正式实验结果

- 新报告：
  - [artifacts/reports/alpha_combo_search_20260320_092222.json](artifacts/reports/alpha_combo_search_20260320_092222.json)
  - [artifacts/reports/alpha_combo_search_20260320_092222.md](artifacts/reports/alpha_combo_search_20260320_092222.md)
- 当前最优的低相关大 alpha 组合是：
  - `-low_volatility_20 + reversal_3`
- 训练期相关性非常低：
  - `abs(corr) = 0.0068`
- 这轮回测结果：
  - train: `Sharpe 0.834 / CAGR 22.54% / MaxDD -48.89%`
  - OOS: `Sharpe 0.530 / CAGR 11.80% / MaxDD -31.48%`
- 当前最优组合已经冻结到：
  - [artifacts/selected_factors/low_corr_alpha_model.json](artifacts/selected_factors/low_corr_alpha_model.json)

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

- 更新了 [README.md](md_documents/README.md)
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

- 更新了 [README.md](md_documents/README.md)
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

- 重写了 [README.md](md_documents/README.md)
  - 加入股票池说明
  - 加入新策略说明
  - 加入回测引擎和优化器说明
  - 加入市场状态混合说明
  - 加入 alpha 因子研究说明

### 说明

- 这次改动的目标是让系统更完整、更稳健、更适合继续研究
- 但我没有也不会虚假承诺“每个策略单独运行都稳定盈利”
- 现在的框架更适合你持续做验证、筛选、迭代，而不是一次性宣布某个策略永远有效

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
