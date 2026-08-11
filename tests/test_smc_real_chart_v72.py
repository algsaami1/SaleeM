from io import BytesIO

from PIL import Image

from app.services.analyzer import (
    _apply_scenario_freshness_guard,
    _bind_market_analysis_to_image,
    _build_action_summary,
)
from app.engine.renderer import (
    _reconstructed_window,
    _reference_trade_lifecycle,
    render_result,
)


def _candles(n=80, start=4385.0):
    rows = []
    price = start
    for i in range(n):
        open_ = price
        close = open_ + (0.35 if i % 3 else -0.15)
        rows.append({
            "time": f"2026-08-11T{10 + (i * 5) // 60:02d}:{(i * 5) % 60:02d}:00",
            "open": open_, "high": max(open_, close) + 0.35,
            "low": min(open_, close) - 0.35, "close": close,
        })
        price = close
    return rows


def test_v72_trusted_image_current_price_is_locked_without_shifting_history():
    candles = _candles()
    canonical = {
        "candles": candles,
        "current_price": 4394.78,
        "provider_live_price": 4395.31,
        "entry": 4389.05,
        "target_1": 4395.12,
    }
    result = _bind_market_analysis_to_image(
        canonical,
        {"chart_readable": True, "current_price": 4395.42},
        snapshot_key="x",
        snapshot_reused=False,
    )
    assert result["current_price"] == 4395.42
    assert result["current_price_source"] == "chart_image_locked"
    assert result["current_price_reference_locked"] is True
    # Historical numeric geometry is not translated by the screenshot gap.
    assert result["entry"] == 4389.05
    assert result["target_1"] == 4395.12


def test_v72_stale_image_price_is_rejected():
    candles = _candles()
    canonical = {"candles": candles, "current_price": 4394.78, "provider_live_price": 4395.10}
    result = _bind_market_analysis_to_image(
        canonical,
        {"chart_readable": True, "current_price": 4450.0},
        snapshot_key="x",
        snapshot_reused=False,
    )
    assert result["current_price"] == 4395.10
    assert result["current_price_reference_locked"] is False


def test_v72_target_reached_forces_watch_and_removes_stale_side_target():
    analysis = {
        "candles": _candles(),
        "current_price": 4395.42,
        "direction": "صاعد",
        "higher_timeframe_direction": "صاعد",
        "entry": 4389.05,
        "target_1": 4395.12,
        "target_2": 4398.0,
        "target_3": 4401.0,
        "buy_scenario_details": {
            "trigger_price": 4389.05, "display_target": 4395.12,
            "score": 75, "state": "مؤكد", "state_code": "confirmed", "is_active": True,
        },
        "sell_scenario_details": {"score": 40, "state_code": "watch"},
        "market_status": "active",
    }
    _apply_scenario_freshness_guard(analysis)
    assert analysis["scenario_expired"] is True
    assert analysis["draw_mode"] == "watch"
    assert analysis["buy_scenario_details"]["retest_only"] is True
    assert analysis["buy_scenario_details"]["display_target"] is None
    action = _build_action_summary(analysis)
    assert action["code"] == "watch_fresh_setup"
    assert action["target"] is None
    assert action["primary_side"] == "wait"


def test_v72_renderer_uses_recent_viewport_not_full_analysis_history():
    analysis = {"candles": _candles(100), "render_visible_candle_count": 36}
    window, offset = _reconstructed_window(analysis)
    assert len(window) == 36
    assert offset == 64


def test_v72_expired_pattern_plan_not_drawn_as_fresh_trade():
    candles = _candles(60)
    analysis = {
        "candles": candles,
        "reconstructed_market_chart": True,
        "current_price": 4395.42,
        "pattern_type": "W",
        "pattern_status": "confirmed",
        "pattern_confidence": 90,
        "reference_match_score": 90,
        "visual_template_id": "multiple_bottoms",
        "pattern_bias": "صاعد",
        "pattern_overlays": [{
            "name": "W", "status": "confirmed", "bias": "صاعد", "confidence": 90,
            "geometry": {
                "window_size": len(candles),
                "anchors": [
                    {"index": 45, "price": 4385.0, "role": "pivot"},
                    {"index": 50, "price": 4388.0, "role": "neck"},
                    {"index": 53, "price": 4385.5, "role": "pivot"},
                ],
                "lines": [], "path": [],
                "trigger": 4389.05, "stop": 4381.05, "target": 4395.12,
            },
        }],
        "support_levels": [{"price": 4389.0}],
        "resistance_levels": [{"price": 4398.5}],
        "action_summary": {"primary_side": "wait", "is_confirmed": False},
    }
    state = _reference_trade_lifecycle(analysis)
    assert state["state"] == "expired"
    png = render_result(analysis)
    with Image.open(BytesIO(png)) as image:
        assert image.size == (1600, 900)
