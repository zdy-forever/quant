"""
顺势回撤策略子包入口。

这个策略在大趋势里等短期回撤后再介入，
比纯突破更克制，也比纯抄底更偏顺势。
"""

from .pullback import PullbackMomentumStrategy
