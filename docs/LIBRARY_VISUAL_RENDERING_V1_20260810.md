# SaleeM — Library Visual Rendering v1

التاريخ: 2026-08-10

## الهدف

تحويل نتيجة SaleeM إلى شارت مستطيل واضح مبني على OHLC الحقيقي، ثم تطبيق أسلوب الرسومات التعليمية من المكتبة المرجعية على **أقرب نموذج حقيقي فقط** دون نسخ إحداثيات الصور المرجعية أو اختلاق نموذج.

## ما تم

- صورة المستخدم أصبحت للمعايرة البصرية/السعر/المحور/الأسلوب فقط، سواء كانت رأسية أو أفقية.
- النتيجة النهائية تُعاد دائمًا من شموع M5 الحقيقية على شارت مستطيل 1600×900.
- توسيع التاريخ يسارًا: يجلب SaleeM افتراضيًا 90 شمعة M5، وبحد أدنى 72 وبحد أقصى 120 للعرض.
- استخدام `reference_matcher.py` الموجود أصلًا لترتيب **كل القواعد المرجعية الـ43** من نفس الهندسة الحتمية؛ لم يُنشأ محرك تحليل ثانٍ.
- بقاء `reference_scenario_engine.py` والـ9 `ScenarioTemplate` كما هي.
- الدرجات المرجعية الحالية تبقى: 35% structure/anchors، 20% geometry، 15% breakout/retest، 10% price position، 8% HTF، 7% SMC confluence، 5% recency.
- لا يُرسم مرجع أقل من 68، والتنفيذ لا يصبح صالحًا من المكتبة وحدها.
- أقرب Pattern يستخدم هندسة M5 الحقيقية فقط: anchors/lines/path/trigger/stop/target/breakout_index.
- Candidate: حدود/مسار متقطع + `ENTRY IF` + `CANCEL` + `TARGET` عند توفر خطة حتمية.
- Confirmed: خطوط متصلة + `ENTRY/STOP/TARGET` وفق الحالة الحقيقية.
- Symmetrical Triangle غير المكسور يبقى محايدًا لأن `pattern_engine.py` لم يتغير وبقيت اختباراته ناجحة.
- أضيف أسلوب بصري قريب من فيديوهات المكتبة: خلفية داكنة، إطار cyan خفيف، مسار أبيض واضح، نقاط مضيئة على anchors، مناطق `RESISTANCE ZONE` و`SUPPORT ZONE` من مستويات حقيقية فقط، وعناوين قمم/قيعان عند الأنماط المناسبة.
- مساحة المستقبل/الأهداف على اليمين زادت: الشموع تنتهي تقريبًا عند 72% من مساحة الرسم عند وجود نموذج/سيناريو/هدف، وبذلك لا يلتصق السعر بالمحور اليميني وتظهر الأهداف والمسار بوضوح.
- نطاق السعر أصبح target-aware: Entry/Stop/Targets وخطة Candidate الحتمية تدخل في نطاق العرض لمنع قص الأهداف قرب حافة المحور.
- عند وجود نموذج/سيناريو، لا يظهر R1/S1 النصي المزدحم؛ تُستخدم منطقة دعم واحدة ومقاومة واحدة بصريًا.
- SMC يبقى من شموع حقيقية فقط عبر السيناريو الحالي: BOS/CHOCH، Liquidity، OB، FVG، Engulfing عند وجودها.

## الملفات المعدلة

- `app/services/analyzer.py`
- `app/engine/renderer.py`
- `tests/test_reconstructed_chart_v366.py`

## ملفات لم تتغير عمدًا

- `app/engine/pattern_engine.py`
- `app/engine/reference_scenario_engine.py`

وذلك للحفاظ على المحرك الحالي وعدم إنشاء منطق تحليل موازٍ.

## الاختبارات

- `python3 -m py_compile app/services/analyzer.py app/engine/renderer.py app/engine/pattern_engine.py app/engine/reference_scenario_engine.py app/engine/reference_matcher.py` — PASS
- `pytest -q` — **187 passed**

## حالات رفض الرسم

- المرجع/النموذج الذي لا يملك هندسة M5 موثوقة أو درجته المرجعية أقل من 68 لا يُرسم كنموذج مرجعي.
- عند عدم وجود `pattern_overlays` ولا `reference_scenario_available` لا تُنشأ مناطق Pattern أو مسار توقع مصطنع.
- لا يوجد fallback جديد لتخمين X/Y.
- الاختبارات الحالية تؤكد بقاء Candidate دون ترقية غير حقيقية وبقاء Symmetrical Triangle غير المكسور محايدًا.
