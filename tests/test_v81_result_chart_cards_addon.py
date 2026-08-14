from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_addon_only_touches_ui_assets():
    css = text("app/static/style.css")
    js = text("app/static/app.js")
    assert "SALEEM_V81_RESULT_CHART_CARDS_ADDON" in css
    assert "SALEEM_V81_RESULT_CHART_CARDS_ADDON" in js


def test_real_chart_image_is_reused_not_recreated():
    js = text("app/static/app.js")
    addon = js.split("SALEEM_V81_RESULT_CHART_CARDS_ADDON", 1)[1]
    assert "q('#result-image')" in addon
    assert "media.appendChild(image)" in addon
    assert "cloneNode" not in addon


def test_fullscreen_only_and_zoom_controls_hidden_in_new_card():
    css = text("app/static/style.css")
    assert ".v81r-chart-tools" in css
    assert ".v81r-chart-media .chart-zoom-controls" in css
    assert "display: none !important" in css


def test_chart_card_has_reference_layout():
    css = text("app/static/style.css")
    js = text("app/static/app.js")
    assert ".v81r-chart-air" in css
    assert "الشارت M5" in js
    assert "XAUUSD • M5" in js


def test_buy_sell_cards_are_added_below_chart():
    js = text("app/static/app.js")
    assert "stage.insertAdjacentElement('afterend', grid)" in js
    assert "نتيجة الشراء" in js
    assert "نتيجة البيع" in js
    assert "BUY IF" in js
    assert "SELL IF" in js


def test_missing_stop_or_target_is_not_fabricated():
    js = text("app/static/app.js")
    assert "غير متوفر" in js
    assert "لا يوجد Target هندسي موثوق" in js
    assert "لن يصنع SaleeM هدفًا هندسيًا غير متوفر" in js


def test_rules_summary_uses_existing_counts_when_available():
    js = text("app/static/app.js")
    assert "متحقق" in js
    assert "انتظار" in js
    assert "openExistingRules" in js


def test_analysis_engines_not_modified_by_addon():
    for rel in (
        "app/engine/pattern_engine.py",
        "app/engine/renderer.py",
        "app/engine/reference_scenario_engine.py",
        "app/services/analyzer.py",
    ):
        p = ROOT / rel
        if p.exists():
            assert "SALEEM_V81_RESULT_CHART_CARDS_ADDON" not in p.read_text(encoding="utf-8")
