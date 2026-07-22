from datetime import datetime, timedelta, timezone

from app.services.analyzer import _choose_direction, _normalize_probabilities, _validate_analysis


def _flat_candles(price: float = 4120.0, count: int = 30):
    start = datetime(2026, 7, 22, 5, 0, tzinfo=timezone.utc)
    candles = []
    for index in range(count):
        offset = 0.06 if index % 2 == 0 else -0.06
        open_ = price - offset
        close = price + offset
        candles.append(
            {
                "time": (start + timedelta(minutes=5 * index)).isoformat(),
                "open": open_,
                "high": price + 0.35,
                "low": price - 0.35,
                "close": close,
            }
        )
    return candles


def _frame(direction="عرضي", score=0.0, confidence=58):
    return {"direction": direction, "score": score, "confidence": confidence}


def test_probabilities_use_both_values_without_buy_default():
    assert _normalize_probabilities({"buy_probability": 30, "sell_probability": 70}) == (30, 70)
    assert _normalize_probabilities({}) == (50, 50)


def test_flat_conflicting_signal_returns_unclear_instead_of_forced_buy_or_sell():
    candles = _flat_candles()
    summary = {
        "direction": "عرضي",
        "alignment": 50,
        "frames": {frame: _frame() for frame in ("H4", "H1", "M15", "M5")},
        "warnings": [],
    }
    direction, buy, sell = _choose_direction({}, candles, 50, 50, summary)
    assert direction == "غير واضح"
    assert abs(buy - sell) <= 12


def test_unclear_analysis_is_watch_and_not_confirmed():
    candles = _flat_candles()
    data = {
        "chart_readable": True,
        "candles": candles,
        "direction": "صاعد",
        "buy_probability": 51,
        "sell_probability": 49,
        "setup_state": "مؤكد",
        "entry_kind": "مباشر",
        "confirmation": "دخول مباشر",
        "current_price": 4120.0,
        "support_levels": [{"price": 4119.2, "strength": 75, "touches": 3}],
        "resistance_levels": [{"price": 4120.8, "strength": 75, "touches": 3}],
        "entry": 4120.0,
        "stop_loss": 4118.8,
        "stop_reason": "أسفل الدعم",
        "target_1": 4121.2,
        "target_2": 4122.0,
        "target_3": 4123.0,
        "pattern_type": "لا يوجد",
        "pattern_confidence": 0,
        "pattern_lines": [],
        "pattern_path": [],
        "scenario": "",
        "note": "",
        "memory_matches": [],
    }
    summary = {
        "direction": "عرضي",
        "alignment": 50,
        "frames": {frame: _frame() for frame in ("H4", "H1", "M15", "M5")},
        "warnings": [],
    }
    result = _validate_analysis(data, summary)
    assert result["draw_mode"] == "watch"
    assert result["trade_side"] == "مراقبة"
    assert result["direction"] == "غير واضح"


def test_bearish_frames_can_produce_sell_without_buy_bias():
    candles = _flat_candles()
    # اجعل حركة M5 الأخيرة هابطة بوضوح.
    for index, candle in enumerate(candles):
        base = 4122.0 - index * 0.12
        candle.update(open=base + 0.08, high=base + 0.25, low=base - 0.25, close=base - 0.08)
    summary = {
        "direction": "هابط",
        "alignment": 100,
        "frames": {
            "H4": _frame("هابط", -1.1, 82),
            "H1": _frame("هابط", -1.0, 80),
            "M15": _frame("هابط", -0.8, 76),
            "M5": _frame("هابط", -0.7, 72),
        },
        "warnings": [],
    }
    direction, buy, sell = _choose_direction({}, candles, 28, 72, summary)
    assert direction == "هابط"
    assert sell > buy
    assert sell >= 65
