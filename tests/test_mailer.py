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

class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")


def test_resend_is_preferred_and_uses_https(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse(200)

    monkeypatch.setenv("SALEEM_EMAIL", "owner@example.com")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("SALEEM_EMAIL_APP_PASSWORD", "smtp-secret")
    monkeypatch.setattr(mailer.httpx, "post", fake_post)

    assert mailer.delivery_provider() == "resend"
    assert mailer.smtp_configured() is True
    assert mailer.send_note_email("اختبار", "رسالة") is True
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer re_test"
    assert captured["json"]["to"] == ["owner@example.com"]
    assert captured["json"]["from"] == "SaleeM <onboarding@resend.dev>"


def test_resend_failure_returns_false(monkeypatch):
    monkeypatch.setenv("SALEEM_EMAIL", "owner@example.com")
    monkeypatch.setenv("RESEND_API_KEY", "re_bad")
    monkeypatch.setattr(mailer.httpx, "post", lambda *a, **k: FakeResponse(403))
    assert mailer.send_note_email("اختبار", "رسالة") is False
