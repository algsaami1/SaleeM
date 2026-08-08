from __future__ import annotations

from app.engine.pattern_engine import review_market_patterns
from app.engine.renderer import _native_index_x, _native_pattern_execution_allowed


def _candle(value: float, index: int) -> dict[str, float | str]:
    return {
        "time": f"2026-08-07T20:{index:02d}:00",
        "open": value + 0.12,
        "high": value + 0.30,
        "low": value - 0.30,
        "close": value,
    }


def _double_top_rows() -> list[dict[str, float | str]]:
    rows = [_candle(100 + (index % 4) * 0.1, index) for index in range(20)]
    sequence = [
        100.2, 100.8, 101.8, 103.0, 104.8, 103.8, 102.2, 101.0,
        102.0, 103.4, 104.7, 103.7, 102.0, 100.5, 99.8, 99.2,
    ]
    rows.extend(_candle(value, 20 + index) for index, value in enumerate(sequence))
    return rows


def test_m_core_has_no_decorative_pre_leg_and_ends_at_real_breakout():
    rows = _double_top_rows()
    review = review_market_patterns({"M5": rows, "M15": rows, "H1": rows})
    m = next(item for item in review["overlay_patterns"] if item["name"] == "M")
    geometry = m["geometry"]
    path = geometry["path"]
    anchors = geometry["anchors"]
    assert path[0][0] == anchors[0]["index"]
    assert path[1][0] == anchors[1]["index"]
    assert path[2][0] == anchors[2]["index"]
    assert len(path) == 4
    assert path[-1][0] == geometry["breakout_index"]


def test_uploaded_chart_index_projection_has_no_trailing_window_fallback():
    candles = [_candle(100 + i * 0.1, i) for i in range(12)]
    analysis = {"candles": candles}
    geometry = {"window_size": len(candles)}
    centers = [50 + i * 20 for i in range(12)]
    assert _native_index_x(analysis, geometry, 6, centers) is None
    analysis["_native_candle_x_map"] = {6: 170}
    assert _native_index_x(analysis, geometry, 6, centers) == 170


def test_only_primary_direction_compatible_active_pattern_can_show_execution():
    overlay = {"bias": "صاعد"}
    base = {
        "market_status": "active",
        "draw_mode": "conditional",
        "direction": "صاعد",
        "action_summary": {"primary_side": "buy"},
    }
    assert _native_pattern_execution_allowed(base, overlay, 0) is True
    assert _native_pattern_execution_allowed(base, overlay, 1) is False

    closed = dict(base, market_status="closed")
    assert _native_pattern_execution_allowed(closed, overlay, 0) is False

    watch = dict(base, draw_mode="watch")
    assert _native_pattern_execution_allowed(watch, overlay, 0) is False

    mismatch = dict(base, direction="هابط", action_summary={"primary_side": "sell"})
    assert _native_pattern_execution_allowed(mismatch, overlay, 0) is False
