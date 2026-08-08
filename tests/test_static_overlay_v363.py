from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_result_template_is_static_and_has_no_animation_controls():
    html = (ROOT / "app" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="result-image"' in html
    assert 'id="chart-pan-canvas"' in html
    assert 'id="saleem-animation-overlay"' not in html
    assert 'id="saleem-animation-plan"' not in html
    assert 'id="chart-animation-replay"' not in html
    assert "buildScenarioAnimation" not in js


def test_upload_surface_previews_chart_inside_same_chart_box():
    html = (ROOT / "app" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "app" / "static" / "style.css").read_text(encoding="utf-8")
    assert 'class="drop-zone upload-chart-box"' in html
    assert 'id="upload-chart-preview"' in html
    assert 'id="upload-chart-placeholder"' in html
    assert "URL.createObjectURL(file)" in js
    assert ".upload-chart-preview" in css
    assert "object-fit:contain" in css.replace(" ", "")


def test_bottom_navigation_removed_and_metrics_are_fixed_grids():
    html = (ROOT / "app" / "templates" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "app" / "static" / "style.css").read_text(encoding="utf-8")
    assert 'class="saleem-bottom-nav"' not in html
    compact = css.replace(" ", "").replace("\n", "")
    assert "grid-template-columns:repeat(5,minmax(0,1fr))!important" in compact
    assert "grid-template-columns:repeat(4,minmax(0,1fr))!important" in compact


def test_renderer_no_longer_builds_animation_plan_and_keeps_pattern_arrow_rule():
    renderer = (ROOT / "app" / "engine" / "renderer.py").read_text(encoding="utf-8")
    assert "def _native_build_expected_scenario_animation_plan" not in renderer
    assert "def _native_draw_expected_scenario_path" not in renderer
    assert "Mandatory model expectation arrow" in renderer
    assert "_native_draw_pattern_overlays(image, analysis" in renderer
    assert "_native_draw_trade(image, analysis" in renderer[renderer.index("def _render_uploaded_chart_with_overlays"):renderer.index("def render_share_snapshot")]
    assert "native_axis_projection_mode" in renderer
