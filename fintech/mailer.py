"""Registration request notifications to the administrator's mailbox.

When a visitor submits their email on /dang-ky the request is always stored in
InfluxDB. A notification is then delivered to NOTIFY_EMAIL using, in order:

1. SMTP (Gmail app password) when SMTP_USER/SMTP_PASS are configured;
2. the FormSubmit relay (https://formsubmit.co) otherwise — the mailbox owner
   must click the one-time activation link FormSubmit emails on first use;
3. nothing (request stays pending in the admin panel) if the network fails.
"""
from __future__ import annotations

import json
import smtplib
import ssl
import urllib.request
from email.message import EmailMessage

from . import db
from .config import NOTIFY_EMAIL, SMTP_HOST, SMTP_PASS, SMTP_PORT, SMTP_USER

_FORMSUBMIT_ENDPOINT = "https://formsubmit.co/ajax/"


def _smtp_configured() -> bool:
    return bool(SMTP_USER and SMTP_PASS and SMTP_HOST)


def _send_via_smtp(email: str, note: str) -> bool:
    message = EmailMessage()
    message["Subject"] = f"[FinViet Pro] Yêu cầu đăng ký tài khoản: {email}"
    message["From"] = SMTP_USER
    message["To"] = NOTIFY_EMAIL
    body = [
        "Có người vừa yêu cầu đăng ký tài khoản FinViet Pro.",
        "",
        f"Email: {email}",
        f"Ghi chú: {note or '(không có)'}",
        "",
        "Duyệt yêu cầu và tạo tài khoản tại /quan-tri.",
    ]
    message.set_content("\n".join(body))
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=15) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(message)
    return True


def _send_via_formsubmit(email: str, note: str) -> bool:
    payload = json.dumps(
        {
            "_subject": f"[FinViet Pro] Yêu cầu đăng ký tài khoản: {email}",
            "email": email,
            "ghi_chu": note or "(không có)",
            "_template": "table",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        _FORMSUBMIT_ENDPOINT + NOTIFY_EMAIL,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "FinVietPro/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - fixed https endpoint
        return 200 <= response.status < 300


def submit_registration_request(email: str, note: str) -> dict:
    """Persist the request, then best-effort notify the admin mailbox."""
    email = (email or "").strip().lower()
    note = (note or "").strip()[:500]
    request_id = db.registration_request_create(email, note)

    method, notified, error = "pending", False, None
    for name, sender in (("smtp", _send_via_smtp), ("formsubmit", _send_via_formsubmit)):
        if name == "smtp" and not _smtp_configured():
            continue
        try:
            sender(email, note)
            method, notified = name, True
            break
        except Exception as exc:  # noqa: BLE001 - notification is best-effort
            error = f"{exc}"
    if notified:
        db.registration_request_set_notified(request_id, method)

    return {
        "ok": True,
        "id": request_id,
        "notified": notified,
        "method": method if notified else "pending",
        "error": error,
    }
