# SaleeM Reference Sheet Renderer V5 — 2026-08-10

## النتيجة
- لم يُنشأ أي محرك تحليل موازٍ.
- `pattern_engine.py` بقي مصدر هندسة النماذج الحتمية.
- `reference_scenario_engine.py` والـ9 `ScenarioTemplate` لم تتغير.
- مكتبة الـ43 قاعدة بقيت للترتيب والشرح فقط.
- `analyzer.py` يختار `visual_template_id` فقط ولا يغير BUY/SELL/Watch.
- صورة المستخدم لا تزود محور الأسعار؛ السعر الحالي فقط اختياري بصريًا.
- الشارت النهائي 1600×900 من OHLC الحقيقي.
- النافذة تعرض 72–120 شمعة M5 عند توفرها.
- يوجد Future Space يمين الرسم 16–22% حسب وجود خطة.
- Entry/Stop/Cancel/Target/PRICE مرتبطة بأسعار حقيقية، وبطاقاتها لا تتحرك رأسيًا.
- عند تعارض بطاقات الأسعار تتحول البطاقة إلى Lane أفقي ثانٍ بدل تغيير Y.
- Candidate يستخدم خططًا شرطية ولا يصبح Confirmed إلا بكسر حقيقي.
- Symmetrical Triangle غير المكسور يبقى Neutral ولا يُعطى قالب تنفيذ اتجاهي.
- عند Score أقل من 68 لا يظهر Reference Drawing.

## قوالب V5
1. trend_reversal
2. multiple_tops
3. multiple_bottoms
4. bullish_smc_reversal
5. bearish_smc_reversal
6. distribution
7. head_shoulders
8. inverse_head_shoulders
9. break_retest_continuation

## رفض الرسم
يظهر السبب في `reference_visual_rejection_reason` مثل:
- pattern_score_below_68
- symmetrical_triangle_unbroken_neutral
- insufficient_real_pivots

## الملفات المعدلة
- app/services/analyzer.py
- app/engine/renderer.py
- app/knowledge/visual_reference_templates_v1.json
- tests/test_reference_renderer_v5.py
- docs/REFERENCE_SHEET_RENDERER_V5_20260810.md

`pattern_engine.py` و`reference_scenario_engine.py` لم يتم تعديلهما.
