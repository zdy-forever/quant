"""
市场状态识别目录的包入口。

这里的目标不是预测涨跌，而是判断当前市场属于哪一类环境，
方便上层去切换策略或收紧风险。
"""

from regime.detection import RegimeConfig, RegimeLabel, classify_regime_history, detect_regime, estimate_regime_mixture

__all__ = ["RegimeConfig", "RegimeLabel", "classify_regime_history", "detect_regime", "estimate_regime_mixture"]
