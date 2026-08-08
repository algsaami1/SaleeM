from __future__ import annotations

from pathlib import Path

from app.engine.renderer import _native_piecewise_price_ratio
from app.services.analyzer import _shift_pattern_overlays

ROOT = Path(__file__).resolve().parents[1]


def test_native_piecewise_axis_hits_literal_broker_ticks_exactly():
    analysis = {
        "image_axis_labels": [
            {"price": 4350.0, "y_ratio": 0.20},
            {"price": 4340.0, "y_ratio": 0.50},
            {"price": 4330.0, "y_ratio": 0.80},
        ],
        "current_price": 4335.0,
        "current_price_y_ratio": 0.65,
    }
    assert _native_piecewise_price_ratio(analysis, 4350.0) == 0.20
    assert _native_piecewise_price_ratio(analysis, 4340.0) == 0.50
    assert _native_piecewise_price_ratio(analysis, 4330.0) == 0.80
    assert abs(_native_piecewise_price_ratio(analysis, 4345.0) - 0.35) < 1e-9
    assert abs(_native_piecewise_price_ratio(analysis, 4335.0) - 0.65) < 1e-9


def test_pattern_overlay_prices_shift_with_broker_offset_but_indices_do_not():
    overlays = [{
        "name": "W",
        "timeframe": "M5",
        "geometry": {
            "window_size": 20,
            "anchors": [{"index": 4, "price": 100.0, "role": "low"}],
            "lines": [{"p1": [4, 100.0], "p2": [9, 105.0], "role": "neckline"}],
            "path": [[4, 100.0], [9, 105.0]],
            "trigger": 105.0,
            "stop": 98.0,
            "target": 112.0,
            "breakout_index": 12,
        },
    }]
    shifted = _shift_pattern_overlays(overlays, 7.25)
    geometry = shifted[0]["geometry"]
    assert geometry["anchors"][0]["index"] == 4
    assert geometry["anchors"][0]["price"] == 107.25
    assert geometry["lines"][0]["p1"] == [4, 107.25]
    assert geometry["lines"][0]["p2"] == [9, 112.25]
    assert geometry["path"][1] == [9, 112.25]
    assert geometry["trigger"] == 112.25
    assert geometry["stop"] == 105.25
    assert geometry["target"] == 119.25
    assert geometry["breakout_index"] == 12
    # Input is not mutated.
    assert overlays[0]["geometry"]["trigger"] == 105.0


def test_result_page_has_real_zoom_controls_and_pinch_support():
    html = (ROOT / "app" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "app" / "static" / "style.css").read_text(encoding="utf-8")
    assert 'id="chart-zoom-in"' in html
    assert 'id="chart-zoom-out"' in html
    assert 'id="chart-zoom-reset"' in html
    assert "touchstart" in js and "touchmove" in js
    assert "MAX_ZOOM = 3.5" in js
    assert "overflow:auto" in css
    assert "touch-action:none" in css
