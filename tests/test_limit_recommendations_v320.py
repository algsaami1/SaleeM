from pathlib import Path

from app.services.analyzer import _build_limit_recommendations


ROOT = Path(__file__).resolve().parents[1]


def _candles(current: float = 4050.0, count: int = 36):
    items = []
    for index in range(count):
        wave = ((index % 9) - 4) * 0.55
        center = current + wave
        items.append(
            {
                "open": center - 0.25,
                "high": center + 0.95,
                "low": center - 0.95,
                "close": center + 0.20,
            }
        )
    items[-1]["close"] = current
    return items


def _analysis(active: bool = True):
    return {
        "draw_mode": "watch" if active else "inactive",
        "market_activity": {"active": active},
        "current_price": 4050.0,
        "candles": _candles(),
        "buy_probability": 63,
        "sell_probability": 37,
        "support_levels": [
            {"price": 4047.1, "strength": 72, "touches": 3, "source": "market"},
            {"price": 4043.2, "strength": 82, "touches": 4, "source": "market"},
        ],
        "resistance_levels": [
            {"price": 4053.0, "strength": 68, "touches": 2, "source": "market"},
            {"price": 4057.4, "strength": 80, "touches": 4, "source": "market"},
        ],
        "frame_directions": {
            "H4": {"direction": "صاعد"},
            "H1": {"direction": "صاعد"},
            "M15": {"direction": "عرضي"},
            "M5": {"direction": "صاعد"},
        },
        "market_data_warnings": [],
    }


def test_limit_recommendations_are_distant_manual_orders_with_far_targets():
    result = _build_limit_recommendations(_analysis())
    assert result["available"] is True
    assert "غير مضمونة" in result["disclaimer"]

    buy = result["buy_limit"]
    sell = result["sell_limit"]
    assert buy["order_type"] == "Buy Limit"
    assert sell["order_type"] == "Sell Limit"
    assert buy["entry"] < result["current_price"] < sell["entry"]
    assert buy["distance_to_entry"] >= 1.8
    assert sell["distance_to_entry"] >= 1.8
    assert buy["stop_loss"] < buy["zone_low"] <= buy["entry"] <= buy["zone_high"]
    assert sell["zone_low"] <= sell["entry"] <= sell["zone_high"] < sell["stop_loss"]
    assert buy["entry"] < buy["target_1"] < buy["target_2"] < buy["target_3"]
    assert sell["entry"] > sell["target_1"] > sell["target_2"] > sell["target_3"]
    assert 38 <= buy["estimated_success"] <= 89
    assert 38 <= sell["estimated_success"] <= 89
    assert buy["guaranteed"] is False
    assert sell["guaranteed"] is False


def test_limit_recommendations_are_disabled_when_market_is_inactive():
    result = _build_limit_recommendations(_analysis(active=False))
    assert result["available"] is False
    assert "غير متاحة" in result["reason"]
    assert "غير مضمونة" in result["disclaimer"]


def test_limit_panel_is_below_why_result_and_contains_required_labels():
    html = (ROOT / "app" / "templates" / "index.html").read_text(encoding="utf-8")
    why_position = html.index("لماذا ظهرت هذه النتيجة؟")
    recommendation_position = html.index("توصية الصفقة")
    feedback_position = html.index("قيّم التحليل السابق")
    assert why_position < recommendation_position < feedback_position
    for required in (
        "Buy Limit",
        "Sell Limit",
        "منطقة الدخول",
        "وقف الخسارة",
        "TP1",
        "TP2",
        "TP3",
        "غير مضمونة",
    ):
        assert required in html
