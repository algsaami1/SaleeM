# SaleeM v3.68 — Logic + Reference Visual V6 Report

## الهدف

توحيد رسومات SaleeM لتقترب من الرسومات التعليمية المرجعية (SMC / BOS / CHOCH / Liquidity / OB / FVG / Entry / Stop / Target) مع إصلاح التعارضات المنطقية قبل تحسين الشكل.

## ما تم إصلاحه

1. **فصل تأكيد النموذج عن تأكيد التنفيذ**
   - قد يكون النموذج deterministic confirmed بينما بوابات SaleeM ما زالت تمنع التنفيذ.
   - عندها لا يظهر `CONFIRMED` كصفقة قابلة للتنفيذ؛ يظهر: `PATTERN CONFIRMED · WATCH`.

2. **منع إعادة عرض صفقة انتهت كأنها دخول جديد**
   - تنفيذ مؤكد + وصول السعر إلى الهدف: `TARGET HIT` فقط، ولا يظهر Risk/Reward جديد.
   - كسر الوقف/الإلغاء: `SETUP INVALIDATED` فقط.
   - Candidate وصل السعر بعد هدفه قبل تأكيد التنفيذ: `SETUP EXPIRED`، وليس `TARGET HIT`.

3. **Candidate / Confirmed واضحان بصريًا**
   - Candidate: `ENTRY IF / CANCEL / TARGET` ومسار متقطع.
   - Execution Confirmed: `ENTRY / STOP / TARGET` ومسار متصل.

4. **السعر الحالي لا يغيّر القرار**
   - دورة حياة الرسم تعتمد على `current_price` من M5 المغلقة.
   - سعر الصورة/المعايرة يبقى fallback بصري فقط ولا يغيّر BUY/SELL/Watch.

5. **تنظيف الرسم المرجعي**
   - عنوان واحد واضح حسب السيناريو.
   - `BEARISH/BULLISH REVERSAL · SMART MONEY` عندما يناسب القالب.
   - Order Block بألوان هادئة متوافقة مع الاتجاه.
   - FVG أزرق فاتح بدل ازدحام الألوان.
   - 9 تدريجات سعرية مولدة من OHLC.
   - بطاقات سعر أكبر وأوضح: Entry / Stop-Cancel / Target / Current.
   - لا تتحرك نقطة السعر أو المنطقة لتجنب التراكب؛ تتحرك البطاقة أفقيًا فقط.

## ما لم يتغير

- `app/engine/pattern_engine.py` لم يتغير في هذه المرحلة.
- `app/services/analyzer.py` لم يتغير في هذه المرحلة.
- لا يوجد محرك تحليل ثانٍ.
- `reference_scenario_engine.py` والـ9 `ScenarioTemplate` كما هي.
- مكتبة الـ43 قاعدة كما هي.
- لا تغيير لبوابات BUY/SELL/Watch.
- لا guessed X/Y fallback.
- Pattern رئيسي واحد فقط في overlay كما في النظام الحالي.

## حالات رفض الرسم الموجودة والمختبرة

- `pattern_score_below_68`
- `symmetrical_triangle_unbroken_neutral`
- `insufficient_real_pivots`

في هذه الحالات لا يتم اختلاق نموذج مرجعي.

## الاختبارات

```text
python3 -m py_compile app/engine/pattern_engine.py app/engine/renderer.py app/services/analyzer.py
PASS

pytest -q
205 passed
```

## سلامة المكتبة

```text
ScenarioTemplate = 9
Reference rules = 43
```

## الملفات المعدلة في V6

- `app/engine/renderer.py`
- `tests/test_reference_renderer_v6_logic_visual.py` (جديد)
- `docs/V6_LOGIC_VISUAL_CONFLICT_FIX.md` (جديد)
- `docs/V6_IMPLEMENTATION_REPORT.md` (جديد)
