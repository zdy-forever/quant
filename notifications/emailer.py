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
        "alpha-combo-search": "低相关Alpha组合报告",
        "alpha-combo-walk-forward": "低相关Alpha滚动验证",
        "alpha-combo-risk-search": "低相关Alpha风控搜索",
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


def _format_factor_weights(weights: Dict[str, Any]) -> str:
    if not weights:
        return "无"
    return ", ".join(f"{name}={float(weight):+.3f}" for name, weight in weights.items())


def _judgement_text(sharpe: float, cagr: float) -> str:
    if sharpe > 0.5 and cagr > 0:
        return "偏强，可以继续重点研究"
    if sharpe > 0 and cagr > 0:
        return "偏正，但还不算特别稳"
    if sharpe > 0 and cagr <= 0:
        return "表面还行，但收益质量一般"
    return "这轮结果偏弱，不建议直接采用"


def _alpha_combo_search_highlights(payload: Dict[str, Any]) -> List[str]:
    best = payload.get("best_combination") or {}
    oos_metrics = best.get("oos_metrics", {}) or {}
    train_metrics = best.get("train_metrics", {}) or {}
    filter_diag = best.get("oos_filter_diagnostics", {}) or {}
    picks = best.get("oos_latest_picks", []) or []
    sharpe = float(oos_metrics.get("sharpe", 0.0) or 0.0)
    cagr = float(oos_metrics.get("cagr", 0.0) or 0.0)

    return [
        "先看结论：",
        f"- 判断：{_judgement_text(sharpe, cagr)}",
        f"- 最优组合：{', '.join(best.get('factors', [])) if best.get('factors') else '无'}",
        f"- 因子权重：{_format_factor_weights(best.get('factor_weights', {}))}",
        f"- 训练期：{_format_metrics(train_metrics)}",
        f"- 样本外：{_format_metrics(oos_metrics)}",
        f"- 因子相关性上限：{float(best.get('max_abs_corr', 0.0) or 0.0):.3f}",
        f"- 最新候选股票：{', '.join(picks) if picks else '无'}",
        f"- 过滤后拦掉比例：{float(filter_diag.get('blocked_ratio', 0.0) or 0.0):.1%}",
        "",
        "你可以怎么理解：",
        "- 这是当前最值得继续跟踪的一组大 alpha，但还不能直接当成永远有效。",
        "- 如果样本外 Sharpe 和 CAGR 都是正的，说明这轮至少不是只在训练期好看。",
    ]


def _alpha_combo_walk_forward_highlights(payload: Dict[str, Any]) -> List[str]:
    summary = payload.get("window_summary", {}) or {}
    best_window = payload.get("best_window") or {}
    test_metrics = best_window.get("test_metrics", {}) or {}
    picks = best_window.get("test_latest_picks", []) or []
    positive_sharpe_ratio = float(summary.get("positive_test_sharpe_ratio", 0.0) or 0.0)
    median_sharpe = float(summary.get("median_test_sharpe", 0.0) or 0.0)
    median_cagr = float(summary.get("median_test_cagr", 0.0) or 0.0)

    verdict = "整体开始有稳定性，但还没稳到可以无脑执行"
    if positive_sharpe_ratio >= 0.8 and median_sharpe > 0.5 and median_cagr > 0:
        verdict = "滚动窗口里也比较稳，可以继续往实战化方向推进"
    elif positive_sharpe_ratio < 0.5:
        verdict = "滚动窗口稳定性还不够，先别急着实盘化"

    return [
        "先看结论：",
        f"- 判断：{verdict}",
        f"- 窗口数：{int(float(summary.get('window_count', 0.0) or 0.0))}",
        f"- 正 Sharpe 占比：{positive_sharpe_ratio:.1%}",
        f"- 正 CAGR 占比：{float(summary.get('positive_test_cagr_ratio', 0.0) or 0.0):.1%}",
        f"- 中位测试 Sharpe：{median_sharpe:.3f}",
        f"- 中位测试 CAGR：{median_cagr:.2%}",
        f"- 最差测试回撤：{float(summary.get('worst_test_max_dd', 0.0) or 0.0):.2%}",
        "",
        "表现最好的那个窗口：",
        f"- 窗口：{' -> '.join(best_window.get('test_window', [])) if best_window.get('test_window') else '无'}",
        f"- 组合：{', '.join((best_window.get('selected_combo') or {}).get('factors', [])) if best_window.get('selected_combo') else '无'}",
        f"- 权重：{_format_factor_weights((best_window.get('selected_combo') or {}).get('factor_weights', {}))}",
        f"- 该窗口测试结果：{_format_metrics(test_metrics)}",
        f"- 该窗口候选股票：{', '.join(picks) if picks else '无'}",
    ]


def _alpha_combo_risk_highlights(payload: Dict[str, Any]) -> List[str]:
    best = payload.get("best_candidate") or {}
    oos_metrics = best.get("oos_metrics", {}) or {}
    train_metrics = best.get("train_metrics", {}) or {}
    risk_overrides = best.get("risk_overrides", {}) or {}
    sharpe = float(oos_metrics.get("sharpe", 0.0) or 0.0)
    cagr = float(oos_metrics.get("cagr", 0.0) or 0.0)
    max_dd = float(oos_metrics.get("max_dd", 0.0) or 0.0)
    meets_target = bool(best.get("meets_target_drawdown"))

    verdict = "回撤确实压下来了，但收益也被一起压缩了"
    if meets_target and sharpe > 0.15 and cagr > 0:
        verdict = "这是目前更像样的低回撤版本，可以当保守基准继续跟踪"
    elif not meets_target:
        verdict = "这轮还没压到目标回撤，不能当最终风控模板"

    return [
        "先看结论：",
        f"- 判断：{verdict}",
        f"- 是否达到回撤目标：{'是' if meets_target else '否'}",
        f"- 样本外最大回撤：{max_dd:.2%}",
        f"- 样本外 Sharpe：{sharpe:.3f}",
        f"- 样本外 CAGR：{cagr:.2%}",
        "",
        "当前建议采用的风控参数：",
        f"- 总敞口 gross_exposure：{float(risk_overrides.get('gross_exposure', 0.0) or 0.0):.2f}",
        f"- 持仓数 top_n：{int(risk_overrides.get('top_n', 0) or 0)}",
        f"- 硬止损 stop_loss_pct：{float(risk_overrides.get('stop_loss_pct', 0.0) or 0.0):.2%}",
        f"- ATR 追踪止损：{float(risk_overrides.get('trailing_stop_atr_multiple', 0.0) or 0.0):.2f} ATR",
        f"- 最大持有天数：{int(risk_overrides.get('max_holding_days', 0) or 0)} 天",
        "",
        "补充说明：",
        f"- 训练期结果：{_format_metrics(train_metrics)}",
        f"- 样本外结果：{_format_metrics(oos_metrics)}",
        "- 这个版本适合拿来当“低回撤保守版”，不是收益最大化版本。",
    ]


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
    elif command_name == "alpha-combo-search":
        lines.extend(_alpha_combo_search_highlights(payload))
    elif command_name == "alpha-combo-walk-forward":
        lines.extend(_alpha_combo_walk_forward_highlights(payload))
    elif command_name == "alpha-combo-risk-search":
        lines.extend(_alpha_combo_risk_highlights(payload))

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
    elif command_name in {"alpha-combo-search", "alpha-combo-walk-forward", "alpha-combo-risk-search"}:
        lines.extend(
            [
                "",
                "报告文件：",
                json.dumps(payload.get("report_files", {}), ensure_ascii=False),
                "",
                "如果你后面还是觉得难懂，我可以继续把邮件再压缩成“只看结论 + 只看操作建议”的版本。",
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
