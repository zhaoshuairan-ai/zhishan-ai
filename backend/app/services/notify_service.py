"""每日临期摘要通知：邮件（SMTP 或模拟落盘）、企业微信/钉钉 Webhook。

默认不联网：未配置 SMTP / Webhook 时，把摘要写入 data/notifications/*.log，
并在返回结果中标记「simulated」，不会假装已发送。
"""
from __future__ import annotations

import json
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

import requests
from flask import current_app

from ..models import User
from . import pantry_service


def _log_dir() -> Path:
    root = Path(current_app.config.get("PANTRY_NOTIFY_LOG_DIR") or (Path(current_app.root_path).parent / "data" / "notifications"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def build_digest(user_id: int, *, username: str = "") -> dict:
    reminder = pantry_service.reminder_summary(user_id)
    lines = []
    if reminder["expired"]:
        lines.append("已过期：" + "、".join(item["name"] for item in reminder["expired"]))
    if reminder["expiring"]:
        lines.append(
            "临期：" + "、".join(f"{item['name']}（{item['status_text']}）" for item in reminder["expiring"])
        )
    urgent = [item for item in reminder["expiring"] if (item.get("days_left") is not None and item.get("days_left") <= 1)]
    if urgent:
        lines.append("临期拯救：" + "、".join(f"{item['name']} 建议今天吃掉" for item in urgent))
    body = "\n".join(lines) if lines else "今天没有过期或临期食材。"
    return {
        "username": username,
        "counts": reminder["counts"],
        "urgent": urgent,
        "subject": (
            f"【食安卫士】{reminder['counts']['expiring']} 项食材临期、{reminder['counts']['expired']} 项已过期"
            if reminder["counts"]["expiring"] or reminder["counts"]["expired"]
            else "【食安卫士】今日食材状态正常"
        ),
        "body": body,
        "message": reminder["message"],
    }


def _send_email(to_addr: str, subject: str, body: str) -> dict:
    host = str(current_app.config.get("SMTP_HOST") or "").strip()
    sender = str(current_app.config.get("SMTP_FROM") or "").strip()
    if not host or not sender or not to_addr:
        path = _log_dir() / f"email-{datetime.now().strftime('%Y-%m-%d')}.log"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"to": to_addr, "subject": subject, "body": body, "at": datetime.now().isoformat()}, ensure_ascii=False) + "\n")
        return {"channel": "email", "status": "simulated", "detail": f"未配置 SMTP，已写入模拟邮件日志：{path.name}"}
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_addr
        port = int(current_app.config.get("SMTP_PORT") or 587)
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            if current_app.config.get("SMTP_STARTTLS", True):
                smtp.starttls()
            user = current_app.config.get("SMTP_USER")
            password = current_app.config.get("SMTP_PASSWORD")
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
        return {"channel": "email", "status": "sent", "detail": "邮件已发送"}
    except Exception as exc:  # 通知失败不影响其它渠道
        return {"channel": "email", "status": "failed", "detail": f"{exc.__class__.__name__}: {str(exc)[:120]}"}


def _send_webhook(name: str, url: str, subject: str, body: str) -> dict:
    if not url:
        return {"channel": name, "status": "unconfigured", "detail": f"未配置 {name} Webhook"}
    payload = {"msgtype": "text", "text": {"content": f"{subject}\n{body}"}}
    try:
        resp = requests.post(url, json=payload, timeout=8)
        if resp.status_code >= 300:
            raise RuntimeError(f"HTTP {resp.status_code}")
        return {"channel": name, "status": "sent", "detail": "Webhook 已推送"}
    except Exception as exc:
        return {"channel": name, "status": "failed", "detail": f"{exc.__class__.__name__}: {str(exc)[:120]}"}


def send_digest(user_id: int, *, username: str = "", email_to: str = "") -> dict:
    digest = build_digest(user_id, username=username)
    results = [
        _send_email(email_to, digest["subject"], digest["body"]),
        _send_webhook("wecom", str(current_app.config.get("WECOM_WEBHOOK_URL") or ""), digest["subject"], digest["body"]),
        _send_webhook("dingtalk", str(current_app.config.get("DINGTALK_WEBHOOK_URL") or ""), digest["subject"], digest["body"]),
    ]
    return {**digest, "channels": results}


def send_daily_digests(*, dry_run: bool = False) -> dict:
    """供每日 8 点定时脚本调用。dry_run 只统计，不发送。"""
    users = User.query.filter_by(is_active=True).all()
    sent = 0
    simulated = 0
    details = []
    for user in users:
        digest = build_digest(user.id, username=user.username)
        if not digest["counts"]["expiring"] and not digest["counts"]["expired"]:
            continue
        if dry_run:
            sent += 1
            details.append({"username": user.username, "status": "dry_run", "subject": digest["subject"]})
            continue
        result = send_digest(user.id, username=user.username, email_to=str(current_app.config.get("PANTRY_NOTIFY_EMAIL_TO") or ""))
        sent += 1
        if any(channel["status"] == "simulated" for channel in result["channels"]):
            simulated += 1
        details.append({"username": user.username, "status": "done", "subject": result["subject"]})
    return {"users": len(users), "notified": sent, "simulated": simulated, "details": details[:20]}


__all__ = ["build_digest", "send_digest", "send_daily_digests"]
