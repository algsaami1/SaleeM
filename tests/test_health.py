import io

from fastapi.testclient import TestClient
from PIL import Image

from app.engine.renderer import AxisCalibrationError
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == "3.8.0"
    assert payload["window"] == "flexible market candle window"
    assert payload["targets"] == 3
    assert payload["market_data"] == "Twelve Data: M5/M15/H1/H4"
    assert payload["cache_policy"] == "M5=4m,M15=14m,H1=55m,H4=4h"


def test_fixed_saleem_title():
    payload = client.get("/health").json()
    assert payload["title"] == "تحليل SaleeM - XAUUSD - M5"


def test_home_has_no_autoscale_confirmation():
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "autoscale-modal" not in html
    assert "تم تفعيل Auto-scale" not in html
    assert "قبل كل رفع" not in html


def test_axis_failure_requests_autoscale_only_after_failed_analysis(monkeypatch):
    def fail_axis(*_args, **_kwargs):
        raise AxisCalibrationError(
            "تعذر ضبط محور الأسعار بدقة. فعّل Auto-scale أو «الضبط التلقائي» ثم أعد المحاولة."
        )

    monkeypatch.setattr("app.main.analyze_chart_image", fail_axis)
    payload = io.BytesIO()
    Image.new("RGB", (240, 400), "white").save(payload, format="PNG")
    response = client.post(
        "/analyze",
        files={"image": ("chart.png", payload.getvalue(), "image/png")},
    )
    assert response.status_code == 422
    assert "تعذر ضبط محور الأسعار" in response.text
    assert "Auto-scale" in response.text
    assert "اختيار صورة جديدة" in response.text
