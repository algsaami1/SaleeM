from pathlib import Path

from app.services.analyzer import _build_result_explanation

ROOT = Path(__file__).resolve().parents[1]


def test_result_page_uses_the_approved_information_order():
    html = (ROOT / "app" / "templates" / "index.html").read_text(encoding="utf-8")
    tokens = [
        'id="result-image"',
        'id="result-action-status"',
        'id="dual-scenarios-card"',
        'id="analysis-notes-card"',
        'id="reading-card"',
        'id="limit-recommendations-card"',
        'id="feedback-card"',
        'id="summary-card"',
    ]
    positions = [html.index(token) for token in tokens]
    assert positions == sorted(positions)


def test_detailed_reason_panel_keeps_advanced_information_collapsed():
    html = (ROOT / "app" / "templates" / "index.html").read_text(encoding="utf-8")
    for label in (
        "اتجاه الفريمات",
        "البنية والحركة",
        "الزخم",
        "السيولة",
        "المناطق الفنية",
        "النماذج الفنية",
        "الأخبار والعوامل الخارجية",
        "ما الذي يمنع التأكيد أو يلغي السيناريو؟",
    ):
        assert label in html
    assert '<details class="card intelligent-details why-result-card"' in html
    assert '<details class="card limit-recommendations"' in html
    assert '<details class="card summary-card"' in html


def test_result_explanation_never_invents_news_and_orders_frames():
    explanation = _build_result_explanation(
        {
            "direction": "صاعد",
            "higher_timeframe_direction": "صاعد",
            "current_movement": "تراجع صحي",
            "current_movement_strength": "متوسط",
            "frame_directions": {
                "M5": {"direction": "هابط"},
                "H4": {"direction": "صاعد"},
                "H1": {"direction": "صاعد"},
                "M15": {"direction": "مختلط"},
            },
            "pattern_type": "لا يوجد",
            "macro_note": "لا تتوفر بيانات أخبار أو DXY ضمن المدخلات الحالية",
            "support_levels": [{"price": 2400.0}],
            "resistance_levels": [{"price": 2420.0}],
            "confirmation_explanation": "بانتظار إغلاق M5",
            "invalidation_condition": "إلغاء عند كسر الدعم",
        }
    )
    assert [item["timeframe"] for item in explanation["frames"]] == ["H4", "H1", "M15", "M5"]
    assert explanation["news_available"] is False
    assert "لا تتوفر" in explanation["news"]
    assert "السيولة" in explanation["liquidity"]


def test_mobile_css_prevents_page_overflow_and_respects_safe_area():
    css = (ROOT / "app" / "static" / "style.css").read_text(encoding="utf-8")
    assert "env(safe-area-inset-top)" in css
    assert "overflow-x:hidden" in css
    assert ".recommendation-type-grid" in css
    assert ".combined-feedback-card" in css
ck-card" in css
