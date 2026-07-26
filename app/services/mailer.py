from __future__ import annotations

import logging
import os

import httpx


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def resend_api_key() -> str:
    """مفتاح Resend المستخدم للإرسال عبر HTTPS."""
    return _env("RESEND_API_KEY")


def owner_email() -> str:
    """البريد الذي يستقبل الملاحظات."""
    return _env("APP_OWNER_EMAIL") or _env("SALEEM_EMAIL")


def delivery_provider() -> str:
    """اسم وسيلة الإرسال المفعلة دون كشف أي أسرار."""
    if resend_api_key() and owner_email():
        return "resend"
    return "none"


def email_configured() -> bool:
    """يعيد True فقط عند توفر بريد الاستقبال ومفتاح Resend."""
    return delivery_provider() == "resend"


def smtp_configured() -> bool:
    """توافق برمجي قديم: لا يوجد SMTP في هذه النسخة."""
    return False


def send_note_email(subject: str, message: str) -> bool:
    """يرسل الملاحظة عبر Resend HTTPS فقط، دون أي اتصال SMTP."""
    api_key = resend_api_key()
    target = owner_email()
    if not api_key or not target:
        return False

    from_address = _env("RESEND_FROM", "SaleeM <onboarding@resend.dev>")
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_address,
                "to": [target],
                "subject": subject,
                "text": message,
            },
            timeout=20.0,
        )
        response.raise_for_status()
        return True
    except Exception:  # pragma: no cover - best effort integration
        logging.exception("SaleeM Resend HTTPS email delivery failed")
        return False
