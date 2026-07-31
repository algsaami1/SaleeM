from app.engine.renderer import _trade_display_items


def test_watch_axis_shows_two_decision_cards_only():
    analysis = {
        "draw_mode": "watch",
        "buy_scenario_details": {"trigger_price": 4080.0},
        "sell_scenario_details": {"trigger_price": 4075.0},
        "entry": 4078.0,
        "target_1": 4085.0,
    }
    mode, items = _trade_display_items(analysis, 4070.0, 4090.0)
    assert mode == "watch"
    assert [item[0] for item in items] == ["شراء بعد إغلاق", "بيع بعد إغلاق"]
    assert all(item[0] not in {"Entry", "TP1", "TP2", "TP3"} for item in items)
