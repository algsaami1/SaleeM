from app.services import mailer


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")


def test_mail_not_configured_without_resend_key(monkeypatch):
    monkeypatch.setenv("SALEEM_EMAIL", "owner@example.com")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("SALEEM_EMAIL_APP_PASSWORD", "unused-old-secret")

    assert mailer.delivery_provider() == "none"
    assert mailer.email_configured() is False
    assert mailer.smtp_configured() is False
    assert mailer.send_note_email("اختبار", "رسالة") is False


def test_resend_uses_https_only(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse(200)

    monkeypatch.setenv("SALEEM_EMAIL", "owner@example.com")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("SALEEM_EMAIL_APP_PASSWORD", "must-not-be-used")
    monkeypatch.setattr(mailer.httpx, "post", fake_post)

    assert mailer.delivery_provider() == "resend"
    assert mailer.email_configured() is True
    assert mailer.smtp_configured() is False
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
