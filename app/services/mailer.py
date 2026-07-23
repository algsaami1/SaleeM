from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage


def owner_email() -> str:
    return os.getenv("APP_OWNER_EMAIL", "algsaami@gmail.com").strip() or "algsaami@gmail.com"


def send_note_email(subject: str, message: str) -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        return False

    port = int(os.getenv("SMTP_PORT", "587").strip() or "587")
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    from_address = os.getenv("SMTP_FROM", username or owner_email()).strip() or owner_email()
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() not in {"0", "false", "no"}

    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = from_address
    email["To"] = owner_email()
    email.set_content(message)

    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()
            if username and password:
                server.login(username, password)
            server.send_message(email)
        return True
    except Exception:  # pragma: no cover - best effort integration
        logging.exception("SaleeM note email delivery failed")
        return False
