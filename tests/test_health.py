from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == "2.8.0"
    assert payload["window"] == "flexible market candle window"
    assert payload["targets"] == 3
    assert payload["market_data"] == "Twelve Data: M5/M15/H1/H4"
    assert payload["cache_policy"] == "M5=4m,M15=14m,H1=55m,H4=4h"


def test_fixed_saleem_title():
    payload = client.get("/health").json()
    assert payload["title"] == "تحليل SaleeM - XAUUSD - M5"
