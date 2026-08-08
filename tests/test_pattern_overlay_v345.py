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


def test_candle_x_detection_and_safe_no_anchor_fallback(tmp_path: Path):
    chart = Image.new("RGBA", (1000, 500), (248, 250, 252, 255))
    draw = ImageDraw.Draw(chart)
    for i in range(12):
        x = 80 + i * 55
        color = (20, 165, 125, 255) if i % 2 == 0 else (235, 70, 70, 255)
        draw.line((x, 120, x, 230), fill=color, width=2)
        draw.rectangle((x - 7, 150, x + 7, 205), fill=color)
    centers = _native_detect_candle_centers(chart)
    assert len(centers) == 12

    # A blank source has no safe candle X anchors. Pattern geometry must be
    # hidden rather than guessed onto a convenient X position.
    blank = Image.new("RGB", (800, 400), "white")
    source = tmp_path / "blank.png"
    blank.save(source)
    analysis = {
        "candles": [],
        "current_price": 100.0,
        "image_axis_labels": [],
        "support_levels": [],
        "resistance_levels": [],
        "pattern_overlays": [{
            "name": "W",
            "timeframe": "M5",
            "status": "confirmed",
            "bias": "صاعد",
            "geometry": {
                "window_size": 20,
                "anchors": [{"index": 10, "price": 99.0, "role": "pivot"}],
                "lines": [],
                "path": [],
                "trigger": 100.0,
                "target": 102.0,
                "breakout_index": 19,
            },
        }],
        "action_summary": {"code": "watch", "primary_side": "wait"},
    }
    rendered = render_result(analysis, chart_background_path=source)
    out = tmp_path / "out.png"
    out.write_bytes(rendered)
    with Image.open(out) as result:
        assert result.convert("RGB").tobytes() == blank.tobytes()
