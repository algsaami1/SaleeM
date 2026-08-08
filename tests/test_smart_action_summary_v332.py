from app.services.analyzer import _build_action_summary


def _base():
    return {
        "draw_mode": "watch",
        "market_status": "active",
        "candles": [
            {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5},
            {"open": 100.5, "high": 101.4, "low": 100.2, "close": 101.0},
            {"open": 101.0, "high": 101.3, "low": 100.4, "close": 100.7},
        ],
        "frame_directions": {
            "H4": {"direction": "صاعد"},
            "H1": {"direction": "صاعد"},
            "M15": {"direction": "صاعد"},
            "M5": {"direction": "صاعد"},
        },
        "buy_scenario_details": {
            "state_code": "watch",
            "score": 68,
            "distance_to_trigger": 0.4,
            "lower_frames_aligned": True,
            "trigger_price": 101.2,
            "display_target": 103.0,
            "cancel_price": 99.8,
            "display_activation": "إغلاق M5 فوق 101.20",
            "display_reason": "توافق H4 وH1 مع M15 وM5",
        },
        "sell_scenario_details": {
            "state_code": "watch",
            "score": 42,
            "distance_to_trigger": 1.8,
            "lower_frames_aligned": False,
            "trigger_price": 99.2,
            "display_target": 97.8,
            "cancel_price": 101.5,
            "display_activation": "إغلاق M5 تحت 99.20",
            "display_reason": "البيع ما زال ضعيفًا",
        },
    }


def test_action_summary_prefers_monitoring_side_without_claiming_confirmation():
    summary = _build_action_summary(_base())
    assert summary["code"] == "watch_buy"
    assert summary["title"] == "مراقبة شراء"
    assert summary["primary_side"] == "buy"
    assert summary["is_confirmed"] is False
    assert summary["trigger"] == 101.2


def test_action_summary_marks_only_closed_m5_confirmed_setup_as_confirmed():
    analysis = _base()
    analysis["draw_mode"] = "confirmed"
    analysis["buy_scenario_details"].update(
        {
            "state_code": "confirmed",
            "activation_candle_close": 101.35,
            "activation_reason": "تفعيل مؤكد",
        }
    )
    summary = _build_action_summary(analysis)
    assert summary["code"] == "buy"
    assert summary["title"] == "شراء مؤكد"
    assert summary["is_confirmed"] is True
    assert "إغلاق M5" in summary["instruction"]


def test_action_summary_returns_no_trade_for_weak_contradictory_reading():
    analysis = _base()
    analysis["frame_directions"] = {
        "H4": {"direction": "صاعد"},
        "H1": {"direction": "هابط"},
        "M15": {"direction": "صاعد"},
        "M5": {"direction": "هابط"},
    }
    analysis["buy_scenario_details"].update({"score": 44, "lower_frames_aligned": False})
    analysis["sell_scenario_details"].update({"score": 46, "lower_frames_aligned": False})
    summary = _build_action_summary(analysis)
    assert summary["code"] == "no_trade"
    assert summary["title"] == "عدم دخول الآن"
    assert summary["primary_side"] == "wait"
