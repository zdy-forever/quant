# -*- coding: utf-8 -*-
"""
通知模块入口。

这个目录专门放“任务完成后怎么通知你”的逻辑，
目前主要支持邮件通知，后面如果你想接企业微信或 Telegram，
也可以继续往这里扩。
"""

from notifications.emailer import (
    send_deploy_notifications,
    send_failure_notification,
    send_research_notification,
)

__all__ = [
    "send_research_notification",
    "send_deploy_notifications",
    "send_failure_notification",
]
