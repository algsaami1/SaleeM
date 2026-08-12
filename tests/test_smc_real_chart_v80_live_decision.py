from pathlib import Path

from app import __version__
from app.services import analyzer


def _base_analysis():
    candles = [
        {"time":"2026-08-12 21:35:00","open":4400.2,"high":4400.8,"low":4399.5,"close":4400.0},
        {"time":"2026-08-12 21:40:00","open":4400.0,"high":4400.4,"low":4398.9,"close":4399.2},
        {"time":"2026-08-12 21:45:00","open":4399.0,"high":4400.0,"low":4398.5,"close":4399.4},
        {"time":"2026-08-12 21:50:00","open":4399.4,"high":4400.1,"low":4398.7,"close":4399.0},
        {"time":"2026-08-12 21:55:00","open":4399.0,"high":4399.6,"low":4397.8,"close":4398.4},
        {"time":"2026-08-12 22:00:00","open":4398.4,"high":4399.2,"low":4397.9,"close":4398.6},
    ]
    return {
        "current_price": 4398.61,
        "market_timezone":"Asia/Muscat",
        "analysis_last_closed_m5_time":"2026-08-12 22:00:00",
        "candles": candles,
        "render_candles": candles,
        "render_visible_candle_count": 36,
        "direction":"هابط",
        "higher_timeframe_direction":"هابط",
        "current_movement":"هابط",
        "current_movement_strength":"متوسط",
        "frame_directions":{"H4":{"direction":"هابط"},"H1":{"direction":"هابط"},"M15":{"direction":"هابط"},"M5":{"direction":"هابط"}},
        "support_levels":[{"price":4397.24,"strength":76,"touches":2},{"price":4395.5,"strength":85,"touches":3}],
        "resistance_levels":[{"price":4400.60,"strength":64,"touches":2},{"price":4405.2,"strength":78,"touches":2},{"price":4408.4,"strength":82,"touches":3}],
        "confirmed_limit_swings":{"peaks":[],"troughs":[]},
        "buy_probability":36,
        "sell_probability":64,
        "buy_scenario_details":{"trigger_price":4400.60,"score":36,"state_code":"watch","display_target":4405.2},
        "sell_scenario_details":{"trigger_price":4396.95,"score":64,"state_code":"watch","display_target":4395.5},
        "market_status":"active",
        "draw_mode":"watch",
    }


def test_v80_version_and_markers():
    assert __version__ == "3.80.0"
    source = Path("app/services/analyzer.py").read_text()
    html = Path("app/templates/index.html").read_text()
    js = Path("app/static/app.js").read_text()
    assert "_refresh_final_live_m5" in source
    assert 'analysis["smc_real_chart_style_version"] = "v8.0"' in source
    assert "انتهت صلاحية قراءة M5" in html
    assert "decisionValidUntilMs" in js


def test_v80_live_price_crossing_buy_trigger_parks_old_sell_direction(monkeypatch):
    analysis = _base_analysis()
    live = {
        "timezone":"Asia/Muscat",
        "fetched_at":"2026-08-12T18:10:20+00:00",
        "latest_candle_time":"2026-08-12 22:10:00",
        "frames":{"M5":[
            {"time":"2026-08-12 21:35:00","open":4400.2,"high":4400.8,"low":4399.5,"close":4400.0},
            {"time":"2026-08-12 21:40:00","open":4400.0,"high":4400.4,"low":4398.9,"close":4399.2},
            {"time":"2026-08-12 21:45:00","open":4399.0,"high":4400.0,"low":4398.5,"close":4399.4},
            {"time":"2026-08-12 21:50:00","open":4399.4,"high":4400.1,"low":4398.7,"close":4399.0},
            {"time":"2026-08-12 21:55:00","open":4399.0,"high":4399.6,"low":4397.8,"close":4398.4},
            {"time":"2026-08-12 22:00:00","open":4398.4,"high":4399.2,"low":4397.9,"close":4398.6},
            {"time":"2026-08-12 22:05:00","open":4398.6,"high":4404.2,"low":4398.5,"close":4403.9},
            {"time":"2026-08-12 22:10:00","open":4403.9,"high":4404.7,"low":4403.7,"close":4404.13},
        ]},
    }
    monkeypatch.setattr(analyzer, "_closed_frame_candles", lambda *args, **kwargs: live["frames"]["M5"][:-1])
    result = analyzer._apply_final_live_m5_snapshot(analysis, live)
    override = result["live_trigger_override"]
    assert result["current_price"] == 4404.13
    assert override["active"] is True
    assert override["side"] == "buy"
    action = analyzer._build_action_summary(result)
    assert action["code"] == "watch_buy_live"
    assert action["primary_side"] == "buy"
    assert "تجاوز شرط الصعود" in action["badge"]
    assert "إغلاق M5" in action["instruction"]


def test_v80_target_landmarks_never_stay_behind_live_price():
    analysis = _base_analysis()
    analysis["current_price"] = 4404.13
    analysis["action_summary"] = {"primary_side":"buy","trigger":4400.60,"title":"مراقبة شراء","strength":70}
    landmarks = analyzer._build_m5_target_landmarks(analysis)
    assert landmarks
    assert all(item["price"] > 4404.13 for item in landmarks)
    assert landmarks[0]["price"] == 4405.2


def test_v80_renderer_header_uses_action_side_before_old_pattern_bias():
    source = Path("app/engine/renderer.py").read_text()
    body = source[source.index("lifecycle_state ="):source.index("model = str(analysis.get(\"pattern_type\")")]
    assert 'action_side = str(action.get("primary_side") or "wait")' in body
    assert 'if action_side == "buy"' in body
    assert 'scenario_bias = "صاعد"' in body


def test_v80_ui_separates_structure_from_live_m5_movement():
    html = Path("app/templates/index.html").read_text()
    assert "الهيكل السابق" in html
    assert "M5 الآن" in html
    assert "السعر عند التحليل" in html
    assert "محدث قبل إخراج النتيجة" in html
