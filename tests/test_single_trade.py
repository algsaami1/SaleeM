from app.services.analyzer import _validate_single_trade


def base_analysis():
    return {
        "chart_readable": True,
        "chart_box": [0.01, 0.12, 0.87, 0.90],
        "axis_top_price": 4020.0,
        "axis_top_y": 0.14,
        "axis_bottom_price": 3960.0,
        "axis_bottom_y": 0.88,
        "direction": "صاعد",
        "buy_probability": 68,
        "sell_probability": 32,
        "setup_state": "مؤكد",
        "entry_kind": "إعادة اختبار",
        "confirmation": "ثبات الدعم وظهور شمعة صاعدة",
        "current_price": 4006.6,
        "support": 4004.5,
        "resistance": 4011.2,
        "entry": 4005.5,
        "stop_loss": 4002.8,
        "stop_reason": "تحت آخر قاع",
        "target_1": 4011.2,
        "target_2": 4014.5,
        "target_3": 4017.9,
        "fvg_boxes": [],
        "pattern_type": "قاعان",
        "pattern_confidence": 72,
        "pattern_lines": [],
        "pattern_path": [],
        "retest_box": None,
        "path_points": [],
        "scenario": "شراء بعد إعادة الاختبار",
        "note": "فرصة شراء",
        "memory_matches": [],
    }


def test_confirmed_near_entry_is_kept():
    result = _validate_single_trade(base_analysis())
    assert result["draw_mode"] == "confirmed"
    assert result["trade_valid"] is True
    assert result["entry"] == 4005.5
    assert result["selected_target"] == 4011.2


def test_far_historical_entry_is_not_drawn_and_is_replaced_with_nearest_trigger():
    data = base_analysis()
    data["entry"] = 3974.0
    data["setup_state"] = "مشروط"
    result = _validate_single_trade(data)
    assert abs(result["entry"] - data["current_price"]) <= 6.0
    assert result["draw_mode"] in {"conditional", "watch"}
    assert result["entry"] != 3974.0


def test_unreadable_axis_is_the_only_no_setup_case():
    data = base_analysis()
    data["chart_readable"] = False
    result = _validate_single_trade(data)
    assert result["draw_mode"] == "none"
    assert result["entry"] is None


def test_wrong_side_stop_is_removed_or_replaced_structurally():
    data = base_analysis()
    data["stop_loss"] = 4010.0
    result = _validate_single_trade(data)
    assert result["stop_loss"] is None or result["stop_loss"] < result["entry"]
