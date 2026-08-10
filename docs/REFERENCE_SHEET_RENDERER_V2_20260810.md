# SaleeM Reference Sheet Renderer v2 — 2026-08-10

## الهدف
تحويل نتيجة SaleeM إلى شارت تعليمي مستطيل قريب من أسلوب الرسومات المرجعية المرفوعة، مع إبقاء OHLC الحقيقي هو مصدر الشموع والهندسة والقرار.

## قواعد لم تتغير
- H4/H1/M15/M5 المغلقة هي مصدر القرار.
- `pattern_engine.py` هو محرك النماذج الحتمي الوحيد؛ لم تتم إضافة محلل موازٍ.
- `reference_scenario_engine.py` ما زال يحتوي 9 `ScenarioTemplate`.
- مكتبة القواعد المرجعية ما زالت 43 قاعدة وتستخدم للترتيب والشرح، لا لإنشاء هندسة غير موجودة.
- لا يزيد عدد النماذج المرسومة عن النموذج الرئيسي المعتمد من المراجعة الحالية.
- Candidate لا يصبح Confirmed إلا حسب شروط الكسر الحتمية الحالية.

## التغيير الرئيسي: Current Price Only
صورة المستخدم لم تعد مصدرًا لمحور X/Y أو نطاق أعلى/أدنى السعر.

يُقرأ منها فقط:
- السعر الحالي عندما يكون واضحًا.
- التوجه البصري العام للصورة كمرجع واجهة فقط.

لا يستخدم SaleeM بعد الآن:
- `axis_high_ref`.
- `axis_low_ref`.
- أرقام محور الصورة.
- Y ratios لمحور الصورة.
- Exact Axis / Auto-scale كشرط للتحليل.

السعر اليدوي الاختياري يبقى `visual_current_price` فقط ولا يغيّر:
- OHLC.
- الاتجاه.
- Entry/Stop/Target.
- BUY/SELL/Watch.
- هندسة النموذج.

## الشارت النهائي
- المقاس: `1600×900`.
- خلفية تعليمية فاتحة ونظيفة قريبة من مراجع الرسومات.
- بدون نسخ بكسلات صورة المستخدم.
- بدون محور أسعار مأخوذ من الصورة.
- يظهر السعر الحالي فقط كـ `CURRENT <price>`.
- يتم عرض تاريخ M5 أوسع على اليسار: نافذة عرض مستهدفة تقارب 104–120 شمعة عند توفرها.
- إذا كان هناك نموذج أو خطة، تُترك مساحة مستقبلية واضحة على اليمين للأهداف والخطة بدل إلصاق آخر شمعة بالحافة.
- إذا كان Stop/Target قريبًا من الحد العلوي/السفلي، يتم توسيع مدى العرض فقط؛ لا تتحرك الأسعار أو نقاط الهندسة.

## لغة الرسم المرجعية
يختار الـRenderer قالب عرض بصري بحسب أقرب سيناريو/نموذج مؤكد هندسيًا، مثل:
- GOOD ENTRY POINTS / Multiple Tops.
- DISTRIBUTION.
- TREND REVERSAL.
- BREAK OF STRUCTURE.
- SMART MONEY REVERSAL.
- ORDER BLOCK REVERSAL.
- HEAD & SHOULDERS / Inverse H&S.
- PATTERN SETUP للنماذج الأخرى.

العناصر المرئية عند وجود هندسة حقيقية فقط:
- 1st/2nd/3rd TOP أو BOTTOM عند القمم/القيعان الحقيقية.
- BOS / CHOCH على Swing مكسور حقيقي.
- Liquidity Sweep على sweep حقيقي.
- ORDER BLOCK / FVG من هندسة السيناريو الحتمية.
- Support واحد وResistance واحد في سياق النموذج.
- Candidate: `ENTRY IF / CANCEL / TARGET` ومسار متقطع.
- Confirmed: `ENTRY / STOP / TARGET` ومسار متصل.
- صندوق Risk/Reward شفاف في مساحة المستقبل على اليمين.

## حالات رفض الرسم
الرسم المرجعي لا يظهر عندما:
1. لا يوجد Pattern/Scenario مثبت هندسيًا على M5.
2. المطابقة المرجعية أقل من عتبة المكتبة الحالية.
3. هندسة النموذج لا تحتوي Anchors/Lines/Path قابلة للربط بالشموع الحقيقية.
4. خطة Candidate لا تحتوي Trigger/Stop/Target حقيقية.
5. اتجاه الخطة لا يحقق ترتيب Entry/Stop/Target المنطقي.
6. النموذج المحايد غير المكسور، مثل Symmetrical Triangle غير المؤكد، لا يحصل على اتجاه أو خطة مصطنعة.

في هذه الحالات يظهر شارت OHLC نظيف مع السعر الحالي فقط أو عناصر SMC المثبتة المتاحة، بدون نموذج مختلق.

## الملفات المعدلة
- `app/main.py`
- `app/services/analyzer.py`
- `app/engine/renderer.py`
- `app/templates/index.html`
- `app/static/style.css`
- `tests/test_analysis_consistency_lock.py`
- `tests/test_health.py`
- `tests/test_reconstructed_chart_v366.py`
- `tests/test_reference_sheet_current_price_only_v369.py` (جديد)

## التحقق
- `python3 -m py_compile app/engine/pattern_engine.py app/engine/renderer.py app/services/analyzer.py app/main.py`
- `pytest -q`
- النتيجة النهائية أثناء التنفيذ: `191 passed`.
- عدد القواعد المرجعية: `43`.
- عدد `ScenarioTemplate`: `9`.
