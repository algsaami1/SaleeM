from app.services.analyzer import _validate_analysis


def _frame(direction: str, score: float = 0.8, confidence: int = 80):
    return {"direction": direction, "score": score, "confidence": confidence}


def test_opposing_current_movement_downgrades_to_watch_until_activation():
    candles = [
        {"open": 4088.0, "high": 4088.3, "low": 4087.7, "close": 4088.1},
        {"open": 4088.1, "high": 4088.2, "low": 4087.4, "close": 4087.6},
        {"open": 4087.6, "high": 4087.7, "low": 4086.9, "close": 4087.0},
        {"open": 4087.0, "high": 4087.1, "low": 4086.4, "close": 4086.5},
        {"open": 4086.5, "high": 4086.7, "low": 4085.9, "close": 4086.1},
        {"open": 4086.1, "high": 4086.2, "low": 4085.6, "close": 4085.8},
    ]
    data = {
        "chart_readable": True,
        "candles": candles,
        "direction": "صاعد",
        "buy_probability": 66,
        "sell_probability": 34,
        "setup_state": "مؤكد",
        "entry_kind": "اختراق",
        "confirmation": "إغلاق فوق المقاومة",
        "current_price": 4086.1,
        "support_levels": [{"price": 4083.2, "strength": 75, "touches": 3}],
        "resistance_levels": [{"price": 4086.8, "strength": 78, "touches": 3}],
        "entry": 4086.8,
        "stop_loss": 4083.1,
        "target_1": 4089.5,
        "target_2": 4090.6,
        "target_3": 4093.2,
        "pattern_type": "قاعان",
        "pattern_confidence": 72,
        "pattern_lines": [],
        "pattern_path": [],
        "scenario": "اختراق واضح",
        "note": "",
        "memory_matches": [],
    }
    summary = {
        "direction": "صاعد",
        "alignment": 75,
        "frames": {
            "H4": _frame("صاعد"),
            "H1": _frame("صاعد"),
            "M15": _frame("صاعد", 0.4, 70),
            "M5": _frame("صاعد", 0.3, 66),
        },
        "warnings": [],
    }
    result = _validate_analysis(data, summary)
    assert result["draw_mode"] == "watch"
    assert result["current_movement"] == "هابط"
    assert "تعاكس الاتجاه" in result["confirmation_explanation"]
    assert result["entry_activation_status"] == "waiting"
