from fastapi.testclient import TestClient

from app.main import app

from pathlib import Path

from app.engine.renderer import _header_pattern_lines
from app.main import _logic_text
from app.services import analyzer


ROOT = Path(__file__).resolve().parents[1]


def test_processing_steps_have_the_approved_order():
    html = (ROOT / "app" / "templates" / "index.html").read_text(encoding="utf-8")
    steps = [
        "جلب بيانات السوق",
        "تحليل H4 و H1",
        "فحص M15 و M5",
        "مراجعة النماذج والذاكرة المرجعية",
        "تجهيز الشارت والسيناريو",
    ]
    positions = [html.index(step) for step in steps]
    assert positions == sorted(positions)
    assert "تمت المتابعة تلقائيًا" not in html
    assert "مراجعة النماذج والذاكرة المرجعية" in html
    assert "result.market_reading_comment" in html


def test_market_reading_comment_is_neutral_complete_and_short(monkeypatch):
    monkeypatch.setattr(
        analyzer,
        "detect_market_zone_presence",
        lambda _analysis: {"order_block": True, "fvg": True},
    )
    text = analyzer._build_market_reading_comment(
        {
            "direction": "صاعد",
            "current_price": 3378.40,
            "support_levels": [{"price": 3372.20}],
            "resistance_levels": [{"price": 3385.70}],
            "candles": [],
        }
    )

    assert len(text) <= 220
    for required in ("القراءة", "السيولة", "الدعم", "المقاومة", "Order Block", "FVG"):
        assert required in text
    for banned in ("شراء", "بيع", "Entry", "Stop", "TP1", "TP2", "TP3"):
        assert banned not in text


def test_logic_words_are_arabic_red_spans_and_input_is_escaped():
    rendered = str(_logic_text("IF كسر <script> THEN صعود"))
    assert '<span class="logic-keyword">إذا</span>' in rendered
    assert '<span class="logic-keyword">فإن</span>' in rendered
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_pattern_card_never_returns_empty_or_dash_only():
    assert _header_pattern_lines("") == ["غير مكتمل"]
    assert _header_pattern_lines("لا يوجد") == ["غير مكتمل"]
    assert _header_pattern_lines("-") == ["غير مكتمل"]
    assert _header_pattern_lines("كسر وإعادة اختبار") == ["كسر", "إعادة اختبار"]
    assert len(_header_pattern_lines("نموذج طويل يحتاج إلى سطرين")) <= 2


client = TestClient(app)


def test_result_page_renders_scenario_cards_below_image_without_conditional(monkeypatch):
    sample_result = {
        "result_url": "data:image/png;base64,ZmFrZQ==",
        "draw_mode": "watch",
        "direction": "صاعد",
        "trade_probability": 61,
        "higher_timeframe_direction": "صاعد",
        "current_movement": "هابط",
        "current_movement_strength": "ضعيف",
        "entry_activation_reason": "بانتظار إغلاق واضح",
        "confirmation": "بانتظار إغلاق واضح",
        "market_reading_comment": "ملخص قراءة السوق.",
        "breakout_summary": "لا يوجد كسر مؤكد.",
        "analysis_last_closed_m5_time": "2026-07-30 12:00",
        "pattern_type": "W",
        "pattern_confidence": 70,
        "scenario": "انتظار حتى يتضح الاتجاه",
        "invalidation_condition": "عند كسر المستوى",
        "limit_recommendations": {"available": False, "reason": "لا توجد قمة أو قاع صالح للتوصية حاليًا."},
        "buy_scenario_details": {
            "state": "مراقبة",
            "trigger_condition": "إغلاق فوق 100.10",
            "quick_target": 100.5,
            "extended_target": 101.0,
            "cancel_price": 99.5,
            "cancel_reason": "إغلاق أسفل الدعم",
            "most_probable_peak": {"price": 101.2},
            "supporting_reasons": ["السعر عند دعم"],
            "display_activation": "إغلاق M5 فوق 100.10",
            "display_target": 101.2,
            "display_reason": "السعر عند دعم",
        },
        "sell_scenario_details": {
            "state": "مراقبة",
            "trigger_condition": "إغلاق تحت 99.90",
            "quick_target": 99.5,
            "extended_target": 99.0,
            "cancel_price": 100.6,
            "cancel_reason": "إغلاق فوق المقاومة",
            "most_probable_trough": {"price": 99.1},
            "supporting_reasons": ["الزخم هابط"],
            "display_activation": "إغلاق M5 تحت 99.90",
            "display_target": 99.1,
            "display_reason": "الزخم هابط",
        },
        "dual_scenario_decision": {
            "label": "القرار الآن: مراقبة",
            "reason": "يظهر التطبيق سيناريو الشراء وسيناريو البيع معًا.",
            "waiting_for": "انتظار أول شرط واضح على شمعة M5 مغلقة",
        },
    }

    monkeypatch.setattr("app.main.analyze_chart_image", lambda *_args, **_kwargs: sample_result)
    from io import BytesIO
    from PIL import Image

    payload = BytesIO()
    Image.new("RGB", (640, 360), "white").save(payload, format="PNG")
    response = client.post("/analyze", files={"image": ("chart.png", payload.getvalue(), "image/png")})
    html = response.text

    assert response.status_code == 200
    assert "سيناريو الشراء والبيع" in html
    assert 'id="dual-scenarios-card"' in html
    assert "سيناريو الشراء" in html and "سيناريو البيع" in html
    assert "القرار الآن: مراقبة" in html
    assert "التفعيل" in html
    assert "الهدف الأرجح" in html
    assert "السبب" in html
    assert "+5 نقاط" not in html
    assert "+10 نقاط" not in html
    assert "يبقى مستقلًا عن الصورة" not in html
    assert "شراء بشرط" not in html
    assert "بيع بشرط" not in html
