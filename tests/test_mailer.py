from app.services import mailer


class FakeSMTP:
    last_instance = None

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.events = []
        self.sent_message = None
        FakeSMTP.last_instance = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def ehlo(self):
        self.events.append("ehlo")

    def starttls(self):
        self.events.append("starttls")

    def login(self, username, password):
        self.events.append(("login", username, password))

    def send_message(self, message):
        self.sent_message = message


def test_gmail_requires_only_two_variables(monkeypatch):
    monkeypatch.delenv("APP_OWNER_EMAIL", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.setenv("SALEEM_EMAIL", "owner@example.com")
    monkeypatch.setenv("SALEEM_EMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)

    assert mailer.smtp_configured() is True
    assert mailer.owner_email() == "owner@example.com"
    assert mailer.send_note_email("اختبار", "رسالة") is True

    smtp = FakeSMTP.last_instance
    assert smtp.host == "smtp.gmail.com"
    assert smtp.port == 587
    assert ("login", "owner@example.com", "abcdefghijklmnop") in smtp.events
    assert smtp.sent_message["To"] == "owner@example.com"


def test_mail_not_configured_without_password(monkeypatch):
    monkeypatch.setenv("SALEEM_EMAIL", "owner@example.com")
    monkeypatch.delenv("SALEEM_EMAIL_APP_PASSWORD", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    assert mailer.smtp_configured() is False
    assert mailer.send_note_email("اختبار", "رسالة") is False
