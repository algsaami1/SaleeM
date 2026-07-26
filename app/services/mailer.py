from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

import httpx


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def smtp_username() -> str:
    """بريد Gmail المستخدم للإرسال عبر SMTP عند تفعيله."""
    return _env("SALEEM_EMAIL") or _env("SMTP_USERNAME")


def smtp_password() -> str:
    """كلمة مرور تطبيق Google، وليست كلمة مرور Gmail العادية."""
    raw = _env("SALEEM_EMAIL_APP_PASSWORD") or _env("SMTP_PASSWORD")
    return raw.replace(" ", "")


def resend_api_key() -> str:
    """مفتاح Resend المستخدم للإرسال عبر HTTPS على جميع خطط Railway."""
    return _env("RESEND_API_KEY")


def owner_email() -> str:
    """البريد الذي يستقبل الملاحظات."""
    return _env("APP_OWNER_EMAIL") or _env("SALEEM_EMAIL") or _env("SMTP_USERNAME")


def delivery_provider() -> str:
    """اسم وسيلة الإرسال المفعلة دون كشف أي أسرار."""
    if resend_api_key() and owner_email():
        return "resend"
    if smtp_username() and smtp_password() and owner_email():
        return "smtp"
    return "none"


def smtp_configured() -> bool:
    """توافق قديم: يعيد True عند تفعيل أي وسيلة بريد."""
    return delivery_provider() != "none"


def _send_via_resend(subject: str, message: str) -> bool:
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
        logging.exception("SaleeM Resend email delivery failed")
        return False


def _send_via_smtp(subject: str, message: str) -> bool:
    username = smtp_username()
    password = smtp_password()
    target = owner_email()
    if not username or not password or not target:
        return False

    host = _env("SMTP_HOST", "smtp.gmail.com") or "smtp.gmail.com"
    try:
        port = int(_env("SMTP_PORT", "587") or "587")
    except ValueError:
        logging.error("Invalid SMTP_PORT; expected an integer")
        return False

    from_address = _env("SMTP_FROM") or username
    use_tls = _env("SMTP_USE_TLS", "true").lower() not in {"0", "false", "no"}

    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = from_address
    email["To"] = target
    email.set_content(message)

    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()
            server.login(username, password)
            server.send_message(email)
        return True
    except Exception:  # pragma: no cover - best effort integration
        logging.exception("SaleeM SMTP email delivery failed")
        return False


def send_note_email(subject: str, message: str) -> bool:
    """يرسل عبر Resend HTTPS أولًا، ثم SMTP كخيار احتياطي."""
    if resend_api_key():
        return _send_via_resend(subject, message)
    return _send_via_smtp(subject, message)
