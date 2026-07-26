from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def smtp_username() -> str:
    """بريد Gmail المستخدم للإرسال.

    يدعم الاسم الواضح SALEEM_EMAIL، مع الإبقاء على SMTP_USERNAME
    للتوافق مع الإصدارات السابقة.
    """
    return _env("SALEEM_EMAIL") or _env("SMTP_USERNAME")


def smtp_password() -> str:
    """كلمة مرور تطبيق Google، وليست كلمة مرور Gmail العادية."""
    raw = _env("SALEEM_EMAIL_APP_PASSWORD") or _env("SMTP_PASSWORD")
    # Google يعرض كلمة مرور التطبيق عادة في مجموعات تفصلها مسافات.
    return raw.replace(" ", "")


def owner_email() -> str:
    """البريد الذي يستقبل الملاحظات.

    عند عدم تحديد APP_OWNER_EMAIL تُرسل الملاحظة إلى بريد الإرسال نفسه،
    وبذلك تكفي قيمتان فقط في Railway عند استخدام Gmail.
    """
    return _env("APP_OWNER_EMAIL") or smtp_username()


def smtp_configured() -> bool:
    return bool(smtp_username() and smtp_password() and owner_email())


def send_note_email(subject: str, message: str) -> bool:
    """إرسال ملاحظة عبر Gmail افتراضيًا أو SMTP مخصص عند الحاجة."""
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
        logging.exception("SaleeM note email delivery failed")
        return False
