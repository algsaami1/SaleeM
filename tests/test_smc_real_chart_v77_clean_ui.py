from pathlib import Path

import app.engine.renderer as renderer


def test_v77_keeps_wide_canvas_but_uses_chart_space_not_footer_sheet():
    assert renderer._reconstructed_dimensions({}) == (1920, 1080)
    source = Path(renderer.__file__).read_text()
    render_body = source[source.index("def _render_reconstructed_market_chart"):source.index("def render_share_snapshot")]
    assert "margin_l, margin_r, margin_t, margin_b = 24, 215, 100, 72" in render_body
    assert "_draw_reference_footer_panels(draw" not in render_body
    assert "_draw_reference_expected_sequence_inset(draw" not in render_body


def test_v77_result_page_moves_rules_and_plan_outside_chart_and_removes_timeframe_strip():
    html = (Path(__file__).parents[1] / "app/templates/index.html").read_text()
    assert 'class="v77-scenarios"' in html
    assert 'class="v77-trade-plan"' in html
    assert 'class="v77-drawing-rules"' in html
    assert '<nav class="terminal-timeframes"' not in html
    assert 'id="saleem-ui-rule-card-v371"' not in html
    assert "القاعدة المرجعية" in html


def test_v77_chart_shell_has_no_green_report_box_border():
    css = (Path(__file__).parents[1] / "app/static/style.css").read_text()
    marker = css.index("V7.7 — CLEAN CHART / UI-OWNED RULES")
    tail = css[marker:]
    assert "border:0!important" in tail
    assert ".terminal-timeframes{display:none!important}" in tail
