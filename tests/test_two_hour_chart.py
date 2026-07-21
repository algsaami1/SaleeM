from app.engine.renderer import _strength_width, render_result
from app.services.analyzer import _validate_analysis


def sample_analysis():
    candles = []
    price = 4000.0
    for index in range(24):
        open_ = price
        close = price + (0.7 if index % 3 != 0 else -0.45)
        high = max(open_, close) + 0.35
        low = min(open_, close) - 0.30
        candles.append({
            "time": f"{14 + (index * 5) // 60:02d}:{(index * 5) % 60:02d}",
            "open": open_, "high": high, "low": low, "close": close,
        })
        price = close
    return {
        "chart_readable": True,
        "candles": candles,
        "direction": "صاعد",
        "buy_probability": 68,
        "sell_probability": 32,
        "setup_state": "مؤكد",
        "entry_kind": "إعادة اختبار",
        "confirmation": "ثبات الدعم وظهور شمعة صاعدة",
        "current_price": candles[-1]["close"],
        "support_levels": [{"price": 4004.0, "strength": 82, "touches": 4}],
        "resistance_levels": [{"price": 4010.0, "strength": 74, "touches": 3}],
        "entry": candles[-1]["close"],
        "stop_loss": candles[-1]["close"] - 2.0,
        "stop_reason": "أسفل آخر قاع",
        "target_1": candles[-1]["close"] + 2.0,
        "target_2": candles[-1]["close"] + 3.5,
        "target_3": candles[-1]["close"] + 5.0,
        "pattern_type": "قاعان",
        "pattern_confidence": 72,
        "pattern_lines": [],
        "pattern_path": [],
        "scenario": "صعود بعد إعادة اختبار الدعم",
        "note": "الزخم الصاعد يحتاج ثباتًا فوق الدخول",
        "memory_matches": [],
    }


def test_strength_width_matches_spec():
    assert _strength_width(90) == 8
    assert _strength_width(75) == 6
    assert _strength_width(60) == 4


def test_validation_accepts_flexible_candles_and_three_targets():
    result = _validate_analysis(sample_analysis())
    assert len(result["candles"]) == len(sample_analysis()["candles"])
    assert result["target_1"] < result["target_2"] < result["target_3"]
    assert len(result["support_levels"]) <= 2
    assert len(result["resistance_levels"]) <= 2


def test_renderer_creates_png():
    result = _validate_analysis(sample_analysis())
    png = render_result(result)
    assert png.startswith(b"\x89PNG")
    assert len(png) > 10_000
