from app.services.analyzer import ANALYSIS_SCHEMA, load_permanent_analysis_prompt


def test_permanent_prompt_is_loaded_for_every_analysis():
    prompt = load_permanent_analysis_prompt()
    assert "قاعدة SaleeM الدائمة لكل تحليل" in prompt
    assert "سيناريو صعود" in prompt
    assert "سيناريو هبوط" in prompt
    assert "إذا" in prompt and "فإن" in prompt
    assert "شرط إلغاء" in prompt
    assert "لا تخترع خبرًا" in prompt


def test_structured_output_contains_permanent_prompt_fields():
    properties = ANALYSIS_SCHEMA["properties"]
    required = ANALYSIS_SCHEMA["required"]
    for field in (
        "bullish_scenario",
        "bearish_scenario",
        "invalidation_condition",
        "macro_note",
    ):
        assert field in properties
        assert field in required


def test_permanent_prompt_contains_unified_visual_template():
    prompt = load_permanent_analysis_prompt()
    assert "تستخدم كلمة `Entry` فقط" in prompt
    assert "شموع سيناريو" in prompt
    assert "تتحرك صعودًا وهبوطًا حسب السعر الحقيقي" in prompt
    assert "لا تُكتب السيناريوهات" in prompt
    assert "ثلاثة مربعات تعليق ثابتة" not in prompt
