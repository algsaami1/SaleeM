from app.services.analyzer import _validate_single_trade


def base_analysis():
    return {
        "direction": "هابط",
        "buy_probability": 32,
        "sell_probability": 68,
        "current_price": 3972.0,
        "support": 3960.0,
        "resistance": 3978.0,
        "entry": 3973.0,
        "stop_loss": 3978.5,
        "stop_reason": "فوق آخر قمة",
        "target_1": 3968.0,
        "target_2": 3962.0,
        "target_3": 3958.0,
        "support_y": 0.72,
        "resistance_y": 0.49,
        "entry_y": 0.58,
        "stop_loss_y": 0.50,
        "target_1_y": 0.64,
        "target_2_y": 0.71,
        "target_3_y": 0.78,
        "fvg_boxes": [],
        "pattern_type": "قمتان",
        "pattern_lines": [],
        "pattern_path": [],
        "retest_box": None,
        "path_points": [[0.7, 0.58], [0.8, 0.64]],
        "scenario": "كسر هابط وإعادة اختبار",
        "note": "صفقة بيع مرجحة",
        "memory_matches": [],
    }


def test_selects_one_highest_probability_trade_and_keeps_structure_stop():
    result = _validate_single_trade(base_analysis())
    assert result["trade_valid"] is True
    assert result["trade_side"] == "بيع"
    assert result["trade_probability"] == 68
    assert result["stop_loss"] == 3978.5
    assert result["selected_target"] == 3968.0


def test_rejects_trade_when_stop_is_on_wrong_side():
    data = base_analysis()
    data["stop_loss"] = 3970.0
    result = _validate_single_trade(data)
    assert result["trade_valid"] is False
    assert result["path_points"] == []


def test_rejects_unclear_market():
    data = base_analysis()
    data["direction"] = "غير واضح"
    result = _validate_single_trade(data)
    assert result["trade_valid"] is False
    assert result["note"] == "لا توجد صفقة واضحة الآن"
