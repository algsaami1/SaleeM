from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == "2.0.0"
    assert payload["window"] == "2h / 24 candles"
    assert payload["targets"] == 3
