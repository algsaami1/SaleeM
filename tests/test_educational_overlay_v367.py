from io import BytesIO
from pathlib import Path

from PIL import Image

from app.engine.renderer import render_result
from app.services.analyzer import _prepare_analysis_image


def test_v367_preserves_original_dimensions_and_accepts_portrait(tmp_path: Path):
    source = tmp_path / "portrait.png"
    Image.new("RGB", (600, 1000), (240, 241, 242)).save(source)
    path, meta = _prepare_analysis_image(source)
    assert path == source
    assert meta["source_chart_preserved"] is True
    assert meta["reconstructed_market_chart"] is True
    assert meta["reference_orientation"] == "portrait"
    assert meta["force_landscape_output"] is True
    assert meta["output_chart_orientation"] == "landscape"
    assert meta["educational_overlay_mode"] is True


def test_v367_visual_geometry_draws_only_after_verified_pattern(tmp_path: Path):
    source = tmp_path / "chart.png"
    Image.new("RGB", (800, 600), "white").save(source)
    analysis = {
        "candles": [],
        "current_price": 100.0,
        "support_levels": [],
        "resistance_levels": [],
        "pattern_type": "M",
        "pattern_confidence": 82,
        "pattern_status": "candidate",
        "pattern_bias": "هابط",
        "pattern_reference_family": "double_top_bottom",
        "visual_geometry_score": 88,
        "visual_chart_plot_bounds": [0.05, 0.08, 0.95, 0.92],
        "visual_pattern_path": [[0.20,0.70],[0.35,0.25],[0.50,0.63],[0.66,0.26],[0.78,0.62]],
        "visual_pattern_lines": [[0.18,0.63,0.80,0.63]],
        "visual_structure_lines": [],
        "visual_zones": [],
        "visual_expected_path": [[0.78,0.62],[0.88,0.78]],
        "reference_scenario_available": False,
    }
    out = Image.open(BytesIO(render_result(analysis, chart_background_path=source))).convert("RGB")
    assert out.size == (800, 600)
    # Overlay changed the white base, but did not reconstruct or resize it.
    assert out.tobytes() != Image.new("RGB", (800, 600), "white").tobytes()


def test_v367_rejects_unverified_visual_geometry(tmp_path: Path):
    source = tmp_path / "chart.png"
    base = Image.new("RGB", (800, 600), "white")
    base.save(source)
    analysis = {
        "candles": [],
        "current_price": 100.0,
        "support_levels": [],
        "resistance_levels": [],
        "pattern_type": "لا يوجد",
        "pattern_confidence": 0,
        "visual_geometry_score": 95,
        "visual_chart_plot_bounds": [0.05, 0.08, 0.95, 0.92],
        "visual_pattern_path": [[0.2,0.7],[0.5,0.2],[0.8,0.7]],
        "visual_pattern_lines": [[0.2,0.7,0.8,0.7]],
        "visual_structure_lines": [],
        "visual_zones": [],
        "visual_expected_path": [[0.8,0.7],[0.9,0.3]],
        "reference_scenario_available": False,
    }
    out = Image.open(BytesIO(render_result(analysis, chart_background_path=source))).convert("RGB")
    assert out.tobytes() == base.tobytes()
