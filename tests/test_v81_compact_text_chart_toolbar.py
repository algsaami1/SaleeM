from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_patch_is_additive_on_current_v81_ui():
    css = text("app/static/style.css")
    js = text("app/static/app.js")
    assert "SALEEM_V81_RESULT_CHART_CARDS_ADDON" in css
    assert "SALEEM_V81_WIDE_RESULT_RULE_LINK_POLISH" in css
    assert "SALEEM_V81_COMPACT_TEXT_CHART_TOOLBAR" in css
    assert "SALEEM_V81_COMPACT_TEXT_CHART_TOOLBAR" in js


def test_result_card_typography_is_smaller_and_responsive():
    css = text("app/static/style.css")
    assert ".v81r-side-head h3" in css
    assert "clamp(17px, 4.2vw, 22px)" in css
    assert ".v81r-trigger strong" in css
    assert "clamp(22px, 5.7vw, 29px)" in css


def test_fullscreen_button_gets_an_icon():
    css = text("app/static/style.css")
    js = text("app/static/app.js")
    assert 'content: "⛶"' in css
    assert "v81c-fullscreen-action" in js
    assert "عرض الشارت كامل" in js


def test_chart_refresh_note_is_added():
    css = text("app/static/style.css")
    js = text("app/static/app.js")
    assert ".v81c-chart-refresh-note" in css
    assert "↻ تحديث الشارت" in js
    assert "آخر شارت مع نتيجة التحليل الحالية" in js


def test_rejected_reason_summary_is_removed_only():
    css = text("app/static/style.css")
    js = text("app/static/app.js")
    assert ".v81p-logic-strip { display: none !important; }" in css
    assert "removeRejectedSummary" in js
    assert "qa('.v81p-logic-strip').forEach((el) => el.remove())" in js


def test_existing_chart_and_result_cards_still_exist():
    css = text("app/static/style.css")
    assert ".v81r-chart-tools" in css
    assert ".v81r-results-grid" in css
    assert ".v81r-side-card" in css
    assert ".v81r-rules-card" in css


def test_no_analysis_engine_changes_from_ui_patch():
    marker = "SALEEM_V81_COMPACT_TEXT_CHART_TOOLBAR"
    for rel in (
        "app/engine/pattern_engine.py",
        "app/engine/renderer.py",
        "app/engine/reference_scenario_engine.py",
        "app/services/analyzer.py",
        "app/templates/index.html",
    ):
        p = ROOT / rel
        if p.exists():
            assert marker not in p.read_text(encoding="utf-8")
