# -*- coding: utf-8 -*-
"""
邮件通知模块。

它的目标不是做复杂营销邮件，而是把量化流程里真正重要的事及时发给你：
- 回测/优化/样本外/Walk-forward/因子研究结果
- Alpaca 模拟盘里实际提交了什么
- 你在 IBKR 里应该手动执行什么
- 哪个任务失败了，需要你注意
"""
from __future__ import annotations

import json
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Dict, List

from dotenv import load_dotenv


@dataclass(frozen=True)
class EmailSettings:
    sender_email: str
    sender_password: str
    receiver_email: str
    smtp_host: str
    smtp_port: int = 587
    sender_name: str = "财政小助手mina"
    use_ssl: bool = False
    use_starttls: bool = True


def load_email_settings() -> EmailSettings | None:
    load_dotenv()
    sender_email = os.getenv("EMAIL_SENDER", "").strip()
    sender_password = os.getenv("EMAIL_PASSWORD", "").strip()
    receiver_email = os.getenv("EMAIL_RECEIVER", "").strip()
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    sender_name = os.getenv("EMAIL_SENDER_NAME", "财政小助手mina").strip() or "财政小助手mina"
    use_ssl_env = os.getenv("SMTP_USE_SSL")
    use_starttls_env = os.getenv("SMTP_USE_STARTTLS")
    use_ssl = str(use_ssl_env).lower() in {"1", "true", "yes", "on"} if use_ssl_env is not None else smtp_port == 465
    use_starttls = (
        str(use_starttls_env).lower() in {"1", "true", "yes", "on"}
        if use_starttls_env is not None
        else not use_ssl
    )

    required = [sender_email, sender_password, receiver_email, smtp_host]
    if not all(required):
        return None

    return EmailSettings(
        sender_email=sender_email,
        sender_password=sender_password,
        receiver_email=receiver_email,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        sender_name=sender_name,
        use_ssl=use_ssl,
        use_starttls=use_starttls,
    )


def _send_email(settings: EmailSettings, subject: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((settings.sender_name, settings.sender_email))
    message["To"] = settings.receiver_email
    message.set_content(body)

    smtp_cls = smtplib.SMTP_SSL if settings.use_ssl else smtplib.SMTP
    with smtp_cls(settings.smtp_host, settings.smtp_port, timeout=60) as smtp:
        smtp.ehlo()
        if settings.use_starttls and not settings.use_ssl:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(settings.sender_email, settings.sender_password)
        smtp.send_message(message)


def _send_if_configured(subject: str, body: str) -> bool:
    settings = load_email_settings()
    if settings is None:
        return False
    _send_email(settings, subject, body)
    return True


def _json_preview(payload: Any, max_chars: int = 4000) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 32] + "\n... [truncated for email]"


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _format_metrics(metrics: Dict[str, Any]) -> str:
    if not metrics:
        return "no metrics"

    parts: List[str] = []
    for key in ["sharpe", "sortino", "cagr", "max_dd", "calmar", "annual_vol"]:
        if key not in metrics:
            continue
        value = metrics[key]
        if value is None:
            continue
        if key in {"cagr", "max_dd", "annual_vol"}:
            parts.append(f"{key}={float(value):.2%}")
        else:
            parts.append(f"{key}={float(value):.3f}")
    return ", ".join(parts) if parts else "no metrics"


def _research_subject(command_name: str) -> str:
    mapping = {
        "alpha-research": "因子分析报告",
        "deploy": "Alpaca 模拟盘操作",
    }
    title = mapping.get(command_name, "回测研究报告")
    return f"财政小助手mina | {title} | {command_name}"


def _failure_subject(command_name: str) -> str:
    return f"财政小助手mina | 任务失败告警 | {command_name}"


def _pipeline_highlights(payload: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    selected = payload.get("selected_strategies", []) or []
    if selected:
        lines.append(f"选中的策略: {', '.join(selected)}")

    train_section = payload.get("train", {}).get("strategies", {})
    for name, row in train_section.items():
        metrics = row.get("best_metrics", {})
        lines.append(f"训练结果 {name}: {_format_metrics(metrics)}")

    test_section = payload.get("test", {}).get("strategies", {})
    for name, row in test_section.items():
        metrics = row.get("oos_metrics", {})
        lines.append(f"OOS 结果 {name}: {_format_metrics(metrics)}")

    alpha = payload.get("alpha", {})
    factors = alpha.get("selected_factors", []) or []
    picks = alpha.get("latest_picks", []) or []
    if factors:
        lines.append(f"通过筛选的因子: {', '.join(factors)}")
    if picks:
        lines.append(f"最新 top picks: {', '.join(picks)}")

    report_files = payload.get("report_files", {})
    if report_files:
        lines.append(f"报告文件: {json.dumps(report_files, ensure_ascii=False)}")
    return lines


def _alpha_highlights(payload: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    factors = payload.get("selected_factors", []) or []
    picks = payload.get("latest_picks", []) or []
    lines.append(f"通过筛选的因子: {', '.join(factors) if factors else 'none'}")
    lines.append(f"最新 top picks: {', '.join(picks) if picks else 'none'}")
    lines.append(f"组合因子回测: {_format_metrics(payload.get('composite_backtest_metrics', {}))}")
    return lines


def _generic_research_body(command_name: str, payload: Dict[str, Any]) -> str:
    lines = [
        f"任务: {command_name}",
        "状态: 成功",
        f"时间: {_utc_now_text()}",
        "",
    ]

    if command_name == "pipeline":
        lines.extend(_pipeline_highlights(payload))
    elif command_name == "alpha-research":
        lines.extend(_alpha_highlights(payload))

    if command_name == "pipeline":
        lines.extend(
            [
                "",
                "完整结果已经写入项目里的 pipeline 报告文件。",
                "如果你只想快速看结论，这封邮件上面的 highlights 就是优先阅读内容。",
                "",
                "报告索引:",
                json.dumps(payload.get("report_files", {}), ensure_ascii=False),
                "",
                "这是一封自动通知邮件，由财政小助手mina发出。",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "结果预览:",
                _json_preview(payload),
                "",
                "这是一封自动通知邮件，由财政小助手mina发出。",
            ]
        )
    return "\n".join(lines)


def send_research_notification(command_name: str, payload: Dict[str, Any]) -> bool:
    subject = _research_subject(command_name)
    body = _generic_research_body(command_name, payload)
    return _send_if_configured(subject, body)


def _format_action_lines(actions: List[Dict[str, Any]]) -> List[str]:
    if not actions:
        return ["- 无"]

    lines: List[str] = []
    for action in actions:
        lines.append(
            "- "
            f"{action.get('side', 'BUY')} {action.get('symbol', '?')} "
            f"qty={action.get('qty', 0)} "
            f"ref_px={float(action.get('reference_price', 0.0)):.2f} "
            f"SL={float(action.get('stop_loss', 0.0)):.2f} "
            f"TP={float(action.get('take_profit', 0.0)):.2f} "
            f"weight={float(action.get('weight', 0.0)):.2%} "
            f"mode={action.get('mode', '-')}"
        )
    return lines


def send_deploy_notifications(payload: Dict[str, Any]) -> bool:
    sent_any = False

    simulation_subject = "财政小助手mina | Alpaca 模拟盘操作 | deploy"
    simulation_lines = [
        "任务: deploy",
        "状态: 成功",
        f"时间: {_utc_now_text()}",
        f"当前市场状态: {payload.get('regime', '-')}",
        f"策略层分配: {json.dumps(payload.get('strategy_allocations', {}), ensure_ascii=False)}",
        "",
        "Alpaca 模拟盘动作:",
        *_format_action_lines(payload.get("paper_actions", [])),
        "",
        "结果预览:",
        _json_preview(payload),
    ]
    sent_any = _send_if_configured(simulation_subject, "\n".join(simulation_lines)) or sent_any

    manual_subject = "财政小助手mina | IBKR 手动操作建议 | deploy"
    manual_lines = [
        "任务: deploy",
        "状态: 需要你手动执行",
        f"时间: {_utc_now_text()}",
        "",
        "你在 IBKR 可以按下面建议手动下单：",
        *_format_action_lines(payload.get("manual_actions", [])),
        "",
        "补充说明:",
        "- 这些建议来自当前策略权重、止损和止盈设置。",
        "- 由于你现在主要靠 IBKR App 手动执行，这封邮件就是你的人工执行清单。",
    ]
    sent_any = _send_if_configured(manual_subject, "\n".join(manual_lines)) or sent_any
    return sent_any


def send_failure_notification(command_name: str, error: str) -> bool:
    body = "\n".join(
        [
            f"任务: {command_name}",
            "状态: 失败",
            f"时间: {_utc_now_text()}",
            "",
            "错误信息:",
            error,
            "",
            "这是一封自动失败告警邮件，由财政小助手mina发出。",
        ]
    )
    return _send_if_configured(_failure_subject(command_name), body)
