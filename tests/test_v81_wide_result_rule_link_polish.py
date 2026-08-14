from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_polish_is_additive_on_existing_result_addon():
    css = text("app/static/style.css")
    js = text("app/static/app.js")
    assert "SALEEM_V81_RESULT_CHART_CARDS_ADDON" in css
    assert "SALEEM_V81_RESULT_CHART_CARDS_ADDON" in js
    assert "SALEEM_V81_WIDE_RESULT_RULE_LINK_POLISH" in css
    assert "SALEEM_V81_WIDE_RESULT_RULE_LINK_POLISH" in js


def test_analysis_result_and_chart_are_slightly_wider():
    css = text("app/static/style.css")
    assert ".v81p-wide-decision" in css
    assert "width: calc(100% + 12px)" in css
    assert ".v81r-chart-stage" in css


def test_decision_is_light_transparent_not_deleted():
    css = text("app/static/style.css")
    js = text("app/static/app.js")
    assert "linear-gradient(135deg" in css
    assert "decorateDecision" in js
    assert "remove()" not in js.split("SALEEM_V81_WIDE_RESULT_RULE_LINK_POLISH", 1)[1]


def test_existing_summary_cards_are_only_decorated():
    js = text("app/static/app.js")
    assert "decorateSummaryCards" in js
    assert "المحطة التالية" in js
    assert "الهيكل السابق" in js
    assert "التأكيد" in js
    assert "الموقع" in js


def test_result_is_visually_linked_to_existing_rules():
    js = text("app/static/app.js")
    assert "ملخص سبب النتيجة" in js
    assert "من القواعد والبيانات الظاهرة نفسها" in js
    assert "existingRuleCounts" in js
    assert "قاعدة متحققة" in js


def test_missing_plan_fields_are_explained_not_fabricated():
    js = text("app/static/app.js")
    assert "الخطة غير مكتملة" in js
    assert "الهدف الهندسي غير متوفر" in js
    assert "لا يُنشأ هدف افتراضي" in js
    assert "الترجيح يشرح السيناريو ولا يساوي تنفيذًا مؤكدًا" in js


def test_chart_and_existing_buy_sell_cards_are_preserved():
    css = text("app/static/style.css")
    assert ".v81r-chart-media #result-image" in css
    assert ".v81r-results-grid" in css
    assert ".v81r-side-card" in css


def test_no_analysis_engine_changes_from_polish():
    for rel in (
        "app/engine/pattern_engine.py",
        "app/engine/renderer.py",
        "app/engine/reference_scenario_engine.py",
        "app/services/analyzer.py",
    ):
        p = ROOT / rel
        if p.exists():
            assert "SALEEM_V81_WIDE_RESULT_RULE_LINK_POLISH" not in p.read_text(encoding="utf-8")
