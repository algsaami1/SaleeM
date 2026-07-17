from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == "2.1.0"
    assert payload["window"] == "2h / 24 candles"
    assert payload["targets"] == 3


def test_fixed_saleem_title():
    payload = client.get("/health").json()
    assert payload["title"] == "تحليل SaleeM - XAUUSD - M5 - آخر ساعتين"
