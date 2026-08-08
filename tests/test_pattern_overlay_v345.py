from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.engine.pattern_engine import review_market_patterns
from app.engine.renderer import _native_detect_candle_centers, render_result


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


def test_confirmed_m_pattern_has_real_geometry_and_measured_target():
    rows = _double_top_rows()
    review = review_market_patterns({"M5": rows, "M15": rows, "H1": rows})

    m5 = review["overlay_patterns"][0]
    assert m5["name"] == "M"
    assert m5["status"] == "confirmed"
    assert m5["timeframe"] == "M5"
    assert len(m5["geometry"]["anchors"]) >= 3
    assert any(line["role"] == "neckline" for line in m5["geometry"]["lines"])
    assert m5["geometry"]["trigger"] is not None
    assert m5["geometry"]["target"] < m5["geometry"]["trigger"]
    assert m5["geometry"]["stop"] > m5["geometry"]["trigger"]


def test_chart_overlay_list_is_m5_only_and_never_exceeds_two():
    rows = _double_top_rows()
    review = review_market_patterns({"M5": rows, "M15": rows, "H1": rows})
    assert len(review["overlay_patterns"]) <= 2
    assert all(item["timeframe"] == "M5" for item in review["overlay_patterns"])


def test_original_renderer_keeps_blank_upload_when_geometry_cannot_be_anchored(tmp_path: Path):
    # v3.67 keeps the exact upload. A blank screenshot cannot support truthful
    # candle anchors, so the renderer must not invent/rebuild a pattern.
    blank = Image.new("RGB", (800, 1200), "white")
    source = tmp_path / "blank.png"
    blank.save(source)
    rows = _double_top_rows()
    review = review_market_patterns({"M5": rows, "M15": rows, "H1": rows})
    analysis = {
        "candles": rows,
        "current_price": float(rows[-1]["close"]),
        "visual_current_price": float(rows[-1]["close"]),
        "support_levels": [],
        "resistance_levels": [],
        "pattern_overlays": review["overlay_patterns"],
        "reference_scenario_available": False,
        "chart_reference_meta": {
            "reference_aspect_ratio": 800 / 1200,
            "reference_orientation": "portrait",
            "reference_theme": "light",
        },
    }
    rendered = render_result(analysis, chart_background_path=source)
    out = tmp_path / "out.png"
    out.write_bytes(rendered)
    with Image.open(out) as result:
        assert result.size == blank.size
        assert result.convert("RGB").tobytes() == blank.tobytes()
