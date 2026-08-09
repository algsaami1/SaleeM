from io import BytesIO
from pathlib import Path
from PIL import Image

from app.engine.renderer import render_result, _v368_safe_text


def _base_analysis():
    return {
        "candles": [],
        "current_price": 100.0,
        "visual_current_price": 100.0,
        "image_axis_labels": [
            {"price": 110.0, "y_ratio": 0.10},
            {"price": 100.0, "y_ratio": 0.50},
            {"price": 90.0, "y_ratio": 0.90},
        ],
        "support_levels": [{"price": 96.0, "strength": 82, "touches": 4}, {"price": 93.0, "strength": 70, "touches": 3}],
        "resistance_levels": [{"price": 104.0, "strength": 85, "touches": 4}, {"price": 107.0, "strength": 72, "touches": 3}],
        "pattern_type": "M",
        "pattern_confidence": 85,
        "pattern_status": "candidate",
        "pattern_bias": "هابط",
        "visual_geometry_score": 90,
        "visual_chart_plot_bounds": [0.05,0.08,0.95,0.92],
        "visual_pattern_path": [[0.18,0.65],[0.34,0.25],[0.50,0.64],[0.66,0.27],[0.78,0.64]],
        "visual_pattern_lines": [[0.18,0.64,0.79,0.64]],
        "visual_structure_lines": [
            {"label":"BOS","line":[0.45,0.64,0.78,0.64]},
            {"label":"CHOCH","line":[0.32,0.42,0.58,0.42]},
        ],
        "visual_zones": [
            {"kind":"order_block","rect":[0.60,0.50,0.82,0.62]},
            {"kind":"fvg","rect":[0.52,0.70,0.80,0.76]},
            {"kind":"liquidity_area","rect":[0.22,0.20,0.69,0.29]},
        ],
        "visual_expected_path": [[0.78,0.64],[0.84,0.72],[0.88,0.67],[0.93,0.84]],
        "reference_scenario_available": False,
        "action_summary": {"code":"watch","primary_side":"wait","is_confirmed":False},
    }


def test_v368_sanitizes_debug_and_broken_glyphs():
    assert _v368_safe_text("SOURCE result_07") == ""
    assert "□" not in _v368_safe_text("M □□ مرشح")


def test_v368_rich_overlay_keeps_original_canvas(tmp_path: Path):
    source = tmp_path / "chart.png"
    base = Image.new("RGB", (900, 700), (18, 24, 32))
    base.save(source)
    out = Image.open(BytesIO(render_result(_base_analysis(), chart_background_path=source))).convert("RGB")
    assert out.size == base.size
    assert out.tobytes() != base.tobytes()


def test_v368_no_verified_pattern_keeps_blank_chart_clean(tmp_path: Path):
    source = tmp_path / "chart.png"
    base = Image.new("RGB", (700, 900), "white")
    base.save(source)
    analysis = {"candles": [], "current_price": 100.0, "support_levels": [], "resistance_levels": [], "pattern_type":"لا يوجد", "pattern_confidence":0, "reference_scenario_available":False}
    out = Image.open(BytesIO(render_result(analysis, chart_background_path=source))).convert("RGB")
    assert out.size == base.size
    assert out.tobytes() == base.tobytes()
