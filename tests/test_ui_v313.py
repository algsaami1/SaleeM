from pathlib import Path

from app.engine.renderer import _header_pattern_lines
from app.main import _logic_text


ROOT = Path(__file__).resolve().parents[1]


def test_processing_steps_have_the_approved_order():
    html = (ROOT / "app" / "templates" / "index.html").read_text(encoding="utf-8")
    steps = [
        "جلب آخر تحديث لبيانات سوق الذهب",
        "تحديد اتجاه الفريمات الأخرى",
        "تحليل الهيكل السعري",
        "تحديد مناطق المقاومة والدعم",
        "مسح مناطق العرض والطلب",
        "حساب مؤشرات الزخم",
        "بناء أقرب سيناريو",
        "إعادة رسم وتوليد الشارت النهائي",
    ]
    positions = [html.index(step) for step in steps]
    assert positions == sorted(positions)
    assert "تمت المتابعة تلقائيًا" not in html
    assert "اكتملت قراءة الصورة والتحليل" in html


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
