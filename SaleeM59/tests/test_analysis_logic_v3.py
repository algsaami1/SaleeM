from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.services.analyzer import (
    _choose_direction,
    _current_m5_movement,
    _entry_activation_state,
    _market_activity_status,
    _normalize_probabilities,
    _validate_analysis,
)


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
    assert result["analysis_direction"] == "غير واضح"


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




def test_strong_m15_m5_drop_is_not_hidden_by_bullish_h4_h1():
    candles = _flat_candles(price=4120.0)
    for index, candle in enumerate(candles):
        base = 4132.0 - index * 0.42
        candle.update(open=base + 0.16, high=base + 0.35, low=base - 0.35, close=base - 0.18)
    summary = {
        "direction": "صاعد",
        "alignment": 50,
        "frames": {
            "H4": _frame("صاعد", 0.8, 78),
            "H1": _frame("صاعد", 0.5, 72),
            "M15": _frame("هابط", -1.25, 82),
            "M5": _frame("هابط", -1.45, 86),
        },
        "warnings": [],
    }
    direction, buy, sell = _choose_direction({}, candles, 58, 42, summary)
    assert direction == "هابط"
    assert sell > buy
    # Lower-frame reversal is valid but capped until H1/H4 also turn.
    assert sell <= 68

def test_unreadable_image_uses_market_fallback_without_stopping():
    candles = _flat_candles(price=4120.0)
    data = {
        "chart_readable": False,
        "_image_chart_readable": False,
        "_image_current_price": None,
        "candles": candles,
        "direction": "غير واضح",
        "buy_probability": 50,
        "sell_probability": 50,
        "setup_state": "مراقبة",
        "entry_kind": "مراقبة",
        "confirmation": "",
        "current_price": candles[-1]["close"],
        "image_price_high": None,
        "image_price_low": None,
        "support_levels": [],
        "resistance_levels": [],
        "entry": None,
        "stop_loss": None,
        "stop_reason": "",
        "target_1": None,
        "target_2": None,
        "target_3": None,
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
    assert result["current_price_source"] == "market_fallback"
    assert result["price_range_source"] == "market_candles_fallback"
    assert result["chart_readable"] is False
    assert result["draw_mode"] == "watch"
    assert result["image_price_high"] > result["current_price"]
    assert result["image_price_low"] < result["current_price"]


def test_levels_always_include_two_supports_and_two_resistances():
    candles = _flat_candles(price=4120.0)
    data = {
        "chart_readable": True,
        "candles": candles,
        "direction": "غير واضح",
        "buy_probability": 50,
        "sell_probability": 50,
        "setup_state": "مراقبة",
        "entry_kind": "مراقبة",
        "confirmation": "",
        "current_price": 4120.0,
        "image_price_high": 4123.0,
        "image_price_low": 4117.0,
        "support_levels": [],
        "resistance_levels": [],
        "entry": None,
        "stop_loss": None,
        "stop_reason": "",
        "target_1": None,
        "target_2": None,
        "target_3": None,
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
    assert len(result["support_levels"]) == 2
    assert len(result["resistance_levels"]) == 2


def test_strong_nearby_resistance_prevents_unchecked_buy_confirmation():
    candles = _flat_candles(price=4120.0)
    candles[-1].update(open=4119.8, high=4120.55, low=4119.7, close=4120.0)
    data = {
        "chart_readable": True,
        "candles": candles,
        "direction": "صاعد",
        "buy_probability": 78,
        "sell_probability": 22,
        "setup_state": "مؤكد",
        "entry_kind": "اختراق",
        "confirmation": "إغلاق فوق المقاومة",
        "current_price": 4120.0,
        "image_price_high": 4123.0,
        "image_price_low": 4117.0,
        "support_levels": [{"price": 4119.0, "strength": 70, "touches": 3}],
        "resistance_levels": [{"price": 4120.25, "strength": 88, "touches": 5}],
        "entry": 4120.25,
        "stop_loss": 4119.2,
        "stop_reason": "أسفل الدعم",
        "target_1": 4121.3,
        "target_2": 4122.0,
        "target_3": 4123.0,
        "pattern_type": "لا يوجد",
        "pattern_confidence": 0,
        "pattern_lines": [],
        "pattern_path": [],
        "scenario": "اختراق مشروط",
        "note": "",
        "memory_matches": [],
    }
    summary = {
        "direction": "صاعد",
        "alignment": 100,
        "frames": {
            "H4": _frame("صاعد", 0.8, 80),
            "H1": _frame("صاعد", 0.7, 78),
            "M15": _frame("صاعد", 0.5, 72),
            "M5": _frame("صاعد", 0.4, 68),
        },
        "warnings": [],
    }
    result = _validate_analysis(data, summary)
    assert result["level_pressure"]["resistance_pressure"] > 0
    assert result["draw_mode"] != "confirmed"


def _threshold_data(probability: int) -> tuple[dict, dict]:
    candles = _flat_candles(price=4120.0)
    data = {
        "chart_readable": True,
        "candles": candles,
        "direction": "صاعد",
        "buy_probability": probability,
        "sell_probability": 100 - probability,
        "setup_state": "مؤكد",
        "entry_kind": "اختراق",
        "confirmation": "إغلاق فوق المقاومة",
        "current_price": 4120.0,
        "support_levels": [{"price": 4119.0, "strength": 72, "touches": 3}],
        "resistance_levels": [{"price": 4120.8, "strength": 72, "touches": 3}],
        "entry": 4120.8,
        "stop_loss": 4119.8,
        "stop_reason": "أسفل الدعم",
        "target_1": 4121.8,
        "target_2": 4122.8,
        "target_3": 4123.8,
        "pattern_type": "كسر وإعادة اختبار",
        "pattern_confidence": 75,
        "pattern_lines": [],
        "pattern_path": [],
        "scenario": "اختراق واضح",
        "note": "",
        "memory_matches": [],
    }
    summary = {
        "direction": "صاعد",
        "alignment": 100,
        "frames": {
            "H4": _frame("صاعد", 0.8, 80),
            "H1": _frame("صاعد", 0.7, 78),
            "M15": _frame("صاعد", 0.5, 72),
            "M5": _frame("صاعد", 0.4, 68),
        },
        "warnings": [],
    }
    return data, summary


def test_probability_below_55_is_watch_and_entry_is_current_price():
    data, summary = _threshold_data(54)
    with (
        patch("app.services.analyzer._choose_direction", return_value=("صاعد", 54, 46)),
        patch("app.services.analyzer._apply_level_pressure", return_value=("صاعد", 54, 46, {})),
    ):
        result = _validate_analysis(data, summary)
    assert result["draw_mode"] == "watch"
    assert result["entry"] == result["current_price"]
    assert result["entry_kind"] == "مراقبة"


def test_probability_55_to_69_with_clear_scenario_is_conditional():
    data, summary = _threshold_data(55)
    with (
        patch("app.services.analyzer._choose_direction", return_value=("صاعد", 55, 45)),
        patch("app.services.analyzer._apply_level_pressure", return_value=("صاعد", 55, 45, {})),
    ):
        result = _validate_analysis(data, summary)
    assert result["draw_mode"] == "conditional"


def test_probability_70_with_complete_confirmation_is_confirmed():
    data, summary = _threshold_data(70)
    # Three rising closed M5 candles provide actual continuation confirmation.
    data["candles"][-3].update(open=4119.7, high=4120.0, low=4119.5, close=4119.8)
    data["candles"][-2].update(open=4119.8, high=4120.25, low=4119.7, close=4120.05)
    data["candles"][-1].update(open=4120.1, high=4121.35, low=4120.0, close=4121.15)
    data["current_price"] = 4121.15
    with (
        patch("app.services.analyzer._choose_direction", return_value=("صاعد", 70, 30)),
        patch("app.services.analyzer._apply_level_pressure", return_value=("صاعد", 70, 30, {})),
    ):
        result = _validate_analysis(data, summary)
    assert result["draw_mode"] == "confirmed"
    assert result["trade_side"] == "شراء مؤكد"


def test_old_m5_candle_becomes_closed_or_stale_instead_of_watch():
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    summary = {
        "timezone": "Asia/Muscat",
        "m5_latest_candle_time": "2026-07-26 15:20:00",
        "cache": {"frames": {"M5": {"status": "cached"}}},
    }
    status = _market_activity_status(summary, now_utc=now)
    assert status["active"] is False
    assert status["code"] == "closed_or_stale"
    assert "السوق مغلق" in status["label"]


def test_current_m5_movement_can_be_bearish_while_higher_trend_is_bullish():
    candles = _flat_candles(price=4120.0)
    for index, candle in enumerate(candles[-6:]):
        base = 4121.5 - index * 0.45
        candle.update(open=base + 0.15, high=base + 0.30, low=base - 0.35, close=base - 0.18)
    movement = _current_m5_movement(candles)
    assert movement["direction"] == "هابط"


def test_bullish_conditional_waits_when_closed_m5_is_below_entry():
    candles = _flat_candles(price=4120.0)
    for index, candle in enumerate(candles[-5:]):
        base = 4121.0 - index * 0.30
        candle.update(open=base + 0.10, high=base + 0.22, low=base - 0.30, close=base - 0.12)
    state = _entry_activation_state(candles, "صاعد", 4120.8, "اختراق")
    assert state["active"] is False
    assert state["movement"]["direction"] == "هابط"
    assert "فوق 4120.8" in state["reason"]


def test_bullish_entry_activates_only_after_close_and_m5_confirmation():
    candles = _flat_candles(price=4120.0)
    candles[-3].update(open=4120.0, high=4120.35, low=4119.9, close=4120.25)
    candles[-2].update(open=4120.2, high=4120.85, low=4120.1, close=4120.70)
    candles[-1].update(open=4120.65, high=4121.45, low=4120.55, close=4121.30)
    state = _entry_activation_state(candles, "صاعد", 4120.8, "اختراق")
    assert state["active"] is True
    assert state["status"] == "active"
