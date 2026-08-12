from pathlib import Path

from app import __version__
from app.engine import renderer
from app.services import analyzer


def test_v79_version_and_style_markers():
    assert __version__ == "3.79.0"
    source = Path("app/services/analyzer.py").read_text()
    css = Path("app/static/style.css").read_text()
    assert 'analysis["smc_real_chart_style_version"] = "v7.9"' in source
    assert 'analysis["visual_overlay_clarity_mode"] = "v7.9_m5_simple_decision"' in source
    assert "V7.9 — M5 SIMPLE DECISION VIEW" in css


def test_v79_bull_and_bear_paths_use_directional_colors_and_reaction_levels():
    source = Path("app/engine/renderer.py").read_text()
    watch = source[source.index("def _draw_reference_dual_watch_paths"):source.index("def _draw_reference_trade_plan")]
    trade = source[source.index("def _draw_reference_trade_plan"):source.index("def _draw_reference_price_axis_and_cards")]
    assert '("buy", buy, buy_score, (30, 167, 88))' in watch
    assert '("sell", sell, sell_score, (216, 67, 76))' in watch
    assert "_reference_reaction_level" in watch
    assert "PULLBACK" in source
    assert "BOUNCE" in source
    assert "path_color = (30, 167, 88, 235) if bullish else (216, 67, 76, 235)" in trade


def test_v79_support_resistance_zones_show_strength():
    source = Path("app/engine/renderer.py").read_text()
    body = source[source.index("def _draw_reconstructed_reference_zones"):source.index("def _draw_reconstructed_reference_scenario")]
    assert 'label_text = f"{label} {strength}%" if strength else label' in body
    assert '"RESISTANCE"' in body
    assert '"SUPPORT"' in body


def test_v79_target_landmarks_use_real_structural_candidates_only():
    analysis = {
        "current_price": 4400.0,
        "action_summary": {"primary_side": "buy", "trigger": 4400.0, "strength": 74, "title": "مراقبة شراء"},
        "support_levels": [{"price": 4398.0, "strength": 80, "touches": 2}],
        "resistance_levels": [
            {"price": 4402.0, "strength": 72, "touches": 2},
            {"price": 4405.0, "strength": 82, "touches": 3},
            {"price": 4409.0, "strength": 91, "touches": 4},
        ],
        "confirmed_limit_swings": {"peaks": [], "troughs": []},
    }
    landmarks = analyzer._build_m5_target_landmarks(analysis)
    assert [item["price"] for item in landmarks] == [4402.0, 4405.0, 4409.0]
    assert [item["label"] for item in landmarks] == ["القمة القريبة", "القمة التالية", "القمة الرئيسية"]
    assert all(item["approximate"] is True for item in landmarks)


def test_v79_ui_is_decision_first_and_m5_only_on_primary_surface():
    html = Path("app/templates/index.html").read_text()
    assert 'class="m5-decision-hero' in html
    assert 'class="m5-next-station"' in html
    assert 'class="m5-quick-grid"' in html
    assert 'class="m5-trigger-strip"' in html
    assert 'class="m5-target-stations"' in html
    assert "قرار M5 الآن" in html
    assert "الأهداف التقريبية" in html
    primary = html[html.index('<section class="saleem-terminal"'):html.index('<section class="card scenarios-card')]
    assert "من H4 / H1" not in primary
    assert "المسار الصاعد</b><small>أخضر" in primary
    assert "المسار الهابط</b><small>أحمر" in primary


def test_v79_target_cards_describe_highs_and_lows():
    source = Path("app/engine/renderer.py").read_text()
    body = source[source.index("def _draw_reference_price_axis_and_cards"):source.index("def _draw_reference_legend")]
    assert "TP1 · NEAR HIGH" in body
    assert "TP3 · MAIN HIGH" in body
    assert "TP1 · NEAR LOW" in body
    assert "TP3 · MAIN LOW" in body
