"""Registration request notifications to the administrator's mailbox.

When a visitor submits their email on /dang-ky the request is always stored in
InfluxDB. The notification to NOTIFY_EMAIL is then delivered, in order:

1. by the visitor's own browser through the FormSubmit relay — the page posts
   to https://formsubmit.co directly and reports the outcome back, because
   FormSubmit blocks datacenter IPs (Vercel) but not browsers. The mailbox
   owner must click the one-time activation link FormSubmit emails first;
2. SMTP (Gmail app password) when SMTP_USER/SMTP_PASS are configured;
3. the FormSubmit relay from the server itself — only on local runs (outside
   serverless), where datacenter blocking does not apply;
4. nothing — the request stays pending in the admin panel (with the delivery
   error recorded) if every channel fails.
"""
from __future__ import annotations

import json
import os
import smtplib
import ssl
import urllib.request
from email.message import EmailMessage

from . import db
from .config import NOTIFY_EMAIL, SITE_URL, SMTP_HOST, SMTP_PASS, SMTP_PORT, SMTP_USER

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
        headers={
            "Content-Type": "application/json",
            "User-Agent": "FinVietPro/1.0",
            # FormSubmit blocks server-side calls without these (403 code 1010 / "open through a web server").
            "Origin": SITE_URL,
            "Referer": f"{SITE_URL}/dang-ky",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - fixed https endpoint
        raw = response.read().decode("utf-8", errors="replace")
    # FormSubmit answers HTTP 200 even when it rejects a submission; the body decides.
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError(f"FormSubmit trả về dữ liệu không hợp lệ: {raw[:160]}") from exc
    if str(data.get("success", "")).lower() == "true":
        return True
    message = str(data.get("message") or "").strip()
    raise RuntimeError(f"FormSubmit từ chối: {message or raw[:160]}")


def _on_serverless() -> bool:
    """True on Vercel, where FormSubmit stalls requests from datacenter IPs."""
    return bool(os.environ.get("VERCEL"))


def submit_registration_request(email: str, note: str, formsubmit_ok: bool = False) -> dict:
    """Persist the request, then best-effort notify the admin mailbox.

    ``formsubmit_ok`` reports that the visitor's browser already relayed the
    notice via FormSubmit (see the /dang-ky JS) — the browser is the primary
    channel on Vercel, where server-side FormSubmit calls are blocked.
    """
    email = (email or "").strip().lower()
    note = (note or "").strip()[:500]
    request_id = db.registration_request_create(email, note)

    if formsubmit_ok:
        db.registration_request_set_notified(request_id, "formsubmit")
        return {"ok": True, "id": request_id, "notified": True, "method": "formsubmit", "error": None}

    method, notified, error = "pending", False, None
    if _smtp_configured():
        try:
            _send_via_smtp(email, note)
            method, notified = "smtp", True
        except Exception as exc:  # noqa: BLE001 - notification is best-effort
            error = f"{exc}"
    if not notified and not _on_serverless():
        try:
            _send_via_formsubmit(email, note)
            method, notified = "formsubmit", True
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
