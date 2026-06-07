from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Iterable

from .main_site import SmtpSettings


def _status_label(status: str) -> str:
    return {
        "ok": "正常",
        "degraded": "资源异常",
        "down": "不可访问",
        "error": "异常",
        "pending": "等待检测",
    }.get(str(status or "").strip(), "异常")


def send_email(settings: SmtpSettings, recipients: Iterable[str], subject: str, text_body: str, html_body: str = "") -> None:
    safe_recipients = [str(item or "").strip() for item in recipients if str(item or "").strip()]
    if not safe_recipients:
        raise RuntimeError("没有可用的收件人")
    if not settings.configured:
        raise RuntimeError("主站发信配置不完整")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((settings.from_name, settings.from_email))
    msg["To"] = ", ".join(safe_recipients)
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    if settings.use_ssl:
        with smtplib.SMTP_SSL(settings.host, settings.port, timeout=20, context=context) as server:
            server.login(settings.username, settings.password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(settings.host, settings.port, timeout=20) as server:
            if settings.use_tls:
                server.starttls(context=context)
            server.login(settings.username, settings.password)
            server.send_message(msg)


def check_smtp_connection(settings: SmtpSettings, *, timeout: int = 12) -> dict:
    if not settings.configured:
        return {
            "ok": False,
            "status": "missing",
            "message": "主站发信配置不完整",
        }

    context = ssl.create_default_context()
    try:
        if settings.use_ssl:
            with smtplib.SMTP_SSL(settings.host, settings.port, timeout=timeout, context=context) as server:
                server.ehlo()
                server.login(settings.username, settings.password)
        else:
            with smtplib.SMTP(settings.host, settings.port, timeout=timeout) as server:
                server.ehlo()
                if settings.use_tls:
                    server.starttls(context=context)
                    server.ehlo()
                server.login(settings.username, settings.password)
    except smtplib.SMTPAuthenticationError:
        return {
            "ok": False,
            "status": "error",
            "message": "SMTP 账号或授权码验证失败",
        }
    except (smtplib.SMTPException, OSError) as exc:
        detail = str(exc).strip()
        return {
            "ok": False,
            "status": "error",
            "message": f"SMTP 服务连接失败：{detail or '网络或服务异常'}",
        }
    return {
        "ok": True,
        "status": "ok",
        "message": "SMTP 服务连接和登录正常",
    }


def send_login_code(settings: SmtpSettings, email: str, code: str) -> None:
    subject = "元芯传感监测站登录验证码"
    text = f"您的监测后台登录验证码是：{code}\n\n验证码 5 分钟内有效。如非本人操作，请忽略本邮件。"
    html = f"""
    <div style="font-family:Arial,'Microsoft YaHei',sans-serif;color:#10233d;line-height:1.7">
      <h2 style="color:#003764">元芯传感监测站登录验证码</h2>
      <p>您的验证码是：</p>
      <p style="font-size:28px;font-weight:700;letter-spacing:6px;color:#f37021">{code}</p>
      <p>验证码 5 分钟内有效。如非本人操作，请忽略本邮件。</p>
    </div>
    """
    send_email(settings, [email], subject, text, html)


def send_alert(settings: SmtpSettings, recipients: list[str], payload: dict) -> None:
    target_name = payload.get("target_name") or "未命名目标"
    status = _status_label(payload.get("status") or "异常")
    subject = f"【元芯监测告警】{target_name} 仍不可用"
    text = "\n".join(
        [
            f"监测目标：{target_name}",
            f"网址：{payload.get('url') or ''}",
            f"状态：{status}",
            f"延迟：{payload.get('latency_ms') or '-'} 毫秒",
            f"响应状态码：{payload.get('http_status') or '-'}",
            f"失败资源数：{payload.get('resource_failed') or 0}",
            f"错误摘要：{payload.get('error_summary') or '-'}",
            f"检测时间：{payload.get('finished_at') or ''}",
            "",
            "系统已经按 1 分钟、2 分钟复测策略确认异常仍存在。",
        ]
    )
    html = f"""
    <div style="font-family:Arial,'Microsoft YaHei',sans-serif;color:#10233d;line-height:1.7">
      <h2 style="color:#c84658">元芯传感主站监测告警</h2>
      <p><strong>{target_name}</strong> 在连续复测后仍不可用或存在关键资源异常。</p>
      <table style="border-collapse:collapse;width:100%;max-width:720px">
        <tr><td style="padding:8px;border:1px solid #e6e6e6">网址</td><td style="padding:8px;border:1px solid #e6e6e6">{payload.get('url') or ''}</td></tr>
        <tr><td style="padding:8px;border:1px solid #e6e6e6">状态</td><td style="padding:8px;border:1px solid #e6e6e6">{status}</td></tr>
        <tr><td style="padding:8px;border:1px solid #e6e6e6">延迟</td><td style="padding:8px;border:1px solid #e6e6e6">{payload.get('latency_ms') or '-'} 毫秒</td></tr>
        <tr><td style="padding:8px;border:1px solid #e6e6e6">响应状态码</td><td style="padding:8px;border:1px solid #e6e6e6">{payload.get('http_status') or '-'}</td></tr>
        <tr><td style="padding:8px;border:1px solid #e6e6e6">失败资源数</td><td style="padding:8px;border:1px solid #e6e6e6">{payload.get('resource_failed') or 0}</td></tr>
        <tr><td style="padding:8px;border:1px solid #e6e6e6">错误摘要</td><td style="padding:8px;border:1px solid #e6e6e6">{payload.get('error_summary') or '-'}</td></tr>
      </table>
      <p>系统已经按 1 分钟、2 分钟复测策略确认异常仍存在。</p>
    </div>
    """
    send_email(settings, recipients, subject, text, html)
