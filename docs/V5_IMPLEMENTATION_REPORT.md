# SaleeM Reference Renderer V5 — تقرير التنفيذ

التاريخ: 2026-08-10

## الملفات المعدلة
- `app/services/analyzer.py`
- `app/engine/renderer.py`
- `app/knowledge/visual_reference_templates_v1.json` (جديد)
- `tests/test_reference_renderer_v5.py` (جديد)
- `docs/REFERENCE_SHEET_RENDERER_V5_20260810.md` (جديد)
- `docs/V5_IMPLEMENTATION_REPORT.md` (جديد)

## ملفات لم تتغير
- `app/engine/pattern_engine.py`
- `app/engine/reference_scenario_engine.py`

وبذلك بقيت هندسة النماذج الحالية، والـ9 `ScenarioTemplate`، ومكتبة الـ43 قاعدة بدون إنشاء محرك تحليل موازٍ.

## ما تم
- إضافة `visual_template_id` في طبقة التحليل كاختيار **أسلوب رسم فقط**.
- إضافة `reference_visual_rejection_reason` دون تغيير BUY/SELL/Watch.
- اعتماد 9 قوالب V5 بصرية.
- الشارت النهائي 1600×900 من OHLC الحقيقي.
- محور السعر يولد من OHLC والخطة الحقيقية، وليس من صورة المستخدم.
- السعر الحالي من الصورة يبقى معايرة بصرية اختيارية فقط.
- 72–120 شمعة M5 حسب النافذة المتاحة والهندسة.
- مساحة يمين 16–22% للهدف والمسار عند وجود خطة.
- Entry/Stop/Cancel/Target/PRICE على Y الحقيقي؛ عند تزاحم البطاقات تتحرك أفقيًا فقط إلى Lane ثانية.
- Candidate يبقى متقطعًا ويعرض ENTRY IF / CANCEL / TARGET.
- Confirmed يعرض الخطة المؤكدة فقط بعد الكسر الحتمي.
- تخفيف الشبكة والخلفية وإضافة Texture تعليمية خفيفة.
- الحفاظ على نموذج رئيسي واحد فقط في الرسم، وSMC كتأكيد مساعد.
- دعم رفض الرسم المرجعي عندما تكون الجودة/الهندسة غير كافية.

## حالات رفض الرسم المرجعي
- `pattern_score_below_68`
- `symmetrical_triangle_unbroken_neutral`
- `insufficient_real_pivots`

في هذه الحالات يبقى الشارت الحقيقي ظاهرًا دون اختلاق نموذج مرجعي.

## القبول
- `python3 -m py_compile app/engine/pattern_engine.py app/engine/renderer.py app/services/analyzer.py` ✅
- `pytest -q` ✅
- النتيجة: `200 passed`
- عدد `ScenarioTemplate`: 9 ✅
- عدد القواعد المرجعية: 43 ✅
