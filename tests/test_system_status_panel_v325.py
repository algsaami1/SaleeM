from fastapi.testclient import TestClient

from app.main import app
from app.services.system_status import system_status_store


client = TestClient(app)


def test_system_status_button_and_arabic_code_panel_are_present():
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "حالة التطبيق" in html
    assert "حالة تطبيق SaleeM" in html
    assert "المتبقي اليوم" in html
    assert "الرصيد المتبقي" in html
    assert "system-code-panel" in html
    assert "رمز الإدارة" not in html
    assert "system-admin-pin" not in html


def test_system_status_opens_without_pin(monkeypatch, tmp_path):
    monkeypatch.delenv("SALEEM_ADMIN_PIN", raising=False)
    monkeypatch.setenv("OPENAI_CREDIT_USD", "10")
    monkeypatch.delenv("OPENAI_ADMIN_KEY", raising=False)
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    system_status_store.path = tmp_path / "system-status.json"

    response = client.get("/api/system-status")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"app", "users", "market", "openai", "system"}
    assert payload["app"]["version"] == "3.49.0"
    assert payload["market"]["daily_limit"] == 800
    assert payload["market"]["minute_limit"] == 8
    assert payload["openai"]["balance_usd"] == 10.0
    assert "OPENAI_API_KEY" not in response.text
    assert "TWELVE_DATA_API_KEY" not in response.text


def test_pin_header_is_not_required(monkeypatch, tmp_path):
    monkeypatch.setenv("SALEEM_ADMIN_PIN", "2468")
    system_status_store.path = tmp_path / "system-status.json"
    response = client.get("/api/system-status")
    assert response.status_code == 200
