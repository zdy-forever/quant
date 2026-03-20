# Alpha 因子来源整理

这个文件的目标不是堆很多论文名字，而是把“我们当前正在研究的因子”对应到更清晰的来源线索。

## 1. 已经落地到代码里的来源

### Cross-Sectional Momentum / Relative Strength

- 代表文献：
  - [Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x)
  - [Momentum Strategies](https://www.nber.org/papers/w5375)
- 当前映射到代码里的因子：
  - `momentum_20`
  - `momentum_60`
  - `trend_pullback_20_5`
- 说明：
  - `relative strength` 在工程上就是“过去一段时间收益率做横截面排序”，所以它并不需要单独再写成一个完全不同的因子公式。

### Short-Term Reversal

- 代表文献：
  - [Fads, Martingales, and Market Efficiency](https://www.nber.org/papers/w2533)
- 当前映射到代码里的因子：
  - `reversal_3`
  - `reversal_5`

### Volume / Turnover Anomaly

- 代表文献：
  - [Price Momentum and Trading Volume](https://www.jstor.org/stable/222483)
  - [Trading Volume and Serial Correlation in Stock Returns](https://academic.oup.com/qje/article/108/4/905/1899978)
- 当前映射到代码里的因子：
  - `volume_surprise_5`
  - `turnover_shock_20`
  - `liquidity_20`

### Low Volatility / Volatility Compression

- 代表文献：
  - [Low-Risk Alpha Without Low Beta](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5005746)
- 当前映射到代码里的因子：
  - `low_volatility_20`
  - `vol_compression_10_40`
  - `true_range_pct_1`

### Gap / Continuation / Trend + Pullback

- 这一块更偏工程化拆解，没有单一论文公式可以完全照搬
- 当前映射到代码里的因子：
  - `gap_continuation_1`
  - `breakout_distance_20`
  - `close_location_1`
  - `ma_distance_20`
- 说明：
  - 这里的目标不是“复刻一条现成策略”，而是把 `gap + continuation`、`trend + pullback` 这类主观描述拆成可单独检验的原子因子。

## 2. 暂时没落地，但应该继续研究的来源

### Post-Earnings Announcement Drift

- 代表文献：
  - [Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?](https://www.sciencedirect.com/science/article/abs/pii/0304405X89900232)
- 当前没有落地到代码的原因：
  - 你现在主要数据来自 Alpaca 日线 bars，缺少稳定的 earnings event 时间戳和 surprise 数据
- 以后如果你接入财报发布日期和预期差数据，可以优先补：
  - `earnings_surprise`
  - `post_earnings_drift`
  - `gap_after_earnings`

## 3. 这份来源表怎么用

- 如果你想继续加因子，优先先在这里补“来源线”和“为什么值得研究”
- 然后再去 `factors/` 里写原子因子函数
- 最后通过新的 `factor-research / factor-select / factor-pipeline` 跑单因子验证
