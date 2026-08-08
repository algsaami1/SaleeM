from PIL import Image

from app.engine.renderer import _native_build_expected_scenario_animation_plan


def _candles(count=32):
    out = []
    price = 100.0
    for i in range(count):
        close = price + (0.20 if i % 2 == 0 else -0.08)
        out.append({
            "open": price,
            "high": max(price, close) + 0.45,
            "low": min(price, close) - 0.40,
            "close": close,
        })
        price = close
    return out


def test_watch_buy_animation_is_strict_and_clips_distant_target():
    image = Image.new("RGBA", (1000, 600), (255, 255, 255, 255))
    analysis = {
        "current_price": 100.0,
        "candles": _candles(),
        "action_summary": {
            "code": "watch_buy",
            "primary_side": "buy",
            "trigger": 101.0,
            "target": 112.0,
            "cancel": 98.0,
            "strength": 67,
        },
        "_native_axis_strict_pixel": True,
        "_native_axis_pixel_model": {
            "mode": "pixel_current_grid",
            "current_price": 100.0,
            "current_y": 300,
            "height": 600,
            "pixels_per_price": 12.0,
        },
        "_native_candle_x_map": {i: 600 + i * 18 for i in range(7)},
        "pattern_overlays": [],
    }
    plan = _native_build_expected_scenario_animation_plan(image, analysis, [])
    assert plan["enabled"] is True
    assert plan["state"] == "watch"
    assert plan["direction"] == "up"
    assert analysis["expected_scenario_path"]["break_price"] == 101.0
    assert analysis["expected_scenario_path"]["retest_price"] > 101.0
    assert analysis["expected_scenario_path"]["continuation_price"] < 112.0
    assert len(plan["points"]) == 4


def test_animation_fails_closed_without_calibrated_x():
    image = Image.new("RGBA", (1000, 600), (255, 255, 255, 255))
    analysis = {
        "current_price": 100.0,
        "candles": _candles(),
        "action_summary": {"code": "watch_sell", "primary_side": "sell", "trigger": 99.0},
        "_native_axis_pixel_model": {"mode": "pixel_current_grid"},
    }
    plan = _native_build_expected_scenario_animation_plan(image, analysis, [])
    assert plan["enabled"] is False
    assert plan["reason"] == "untrusted_x"


def test_result_template_contains_live_svg_animation_layer():
    html = open("app/templates/index.html", encoding="utf-8").read()
    js = open("app/static/app.js", encoding="utf-8").read()
    assert 'id="saleem-animation-overlay"' in html
    assert 'id="saleem-animation-plan"' in html
    assert 'id="chart-pan-canvas"' in html
    assert "buildScenarioAnimation" in js
    assert "animated-scenario-path" in js
