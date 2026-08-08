# المواصفة البرمجية المعتمدة — ثبات التحليل وربط الأسعار الحقيقية

> **قاعدة v3.66 الناسخة لما يتعارض معها:** الصورة المرفوعة مرجع بصري فقط وليست الخلفية النهائية أو مصدر OHLC. الشموع تُجلب من السوق وتُعاد رسمها داخل SaleeM، وتُقبل الصور الرأسية أو الأفقية. لا تُزاح أسعار السوق لمطابقة الصورة. بعد إعادة بناء الشارت يُرسم السيناريو المرجعي الأقرب فقط بعد تحقق هندسته. المرجع التنفيذي: `SALEEM_RECONSTRUCTED_MARKET_CHART_SPEC_V366.md`.


## Architecture

```text
بيانات Twelve Data H4/H1/M15/M5
        ↓
إنشاء Market Snapshot Key
        ↓
تحليل سوقي ثابت بلا صورة
        ↓
قرار موحد محفوظ لنفس Snapshot

صورة المستخدم
        ↓
قراءة هندسية فقط
current_price + axis labels + y ratios
        ↓
تحويل أسعار القرار إلى مقياس الوسيط
        ↓
الرسم فوق الصورة بدالة price_to_y واحدة
```

## Rules

```text
1. الصورة لا تدخل في الاتجاه أو الحالة أو الاحتمالات أو المستويات.
2. التحليل يعتمد فقط على H4/H1/M15/M5.
3. نفس Market Snapshot يعيد نفس القرار التحليلي.
4. اختلاف Zoom أو Vertical Scale أو شريط أمر التداول لا يغير القرار.
5. الصورة تستخدم فقط لاستخراج السعر الحالي وأرقام المحور ومواضعها.
6. جميع الأسعار تظهر بمنزلة عشرية واحدة داخل بطاقات التحليل.
7. خطوط R1/R2/S1/S2 وEntry/Stop/Cancel/TP تبقى عند السعر الحقيقي.
8. تتحرك البطاقة فقط عند التداخل، ولا يتحرك الخط الحقيقي.
9. بطاقات الدعم والمقاومة تبقى على يسار الشارت، وتظهر النسبة بجوار السعر.
```

## Render pipeline

```python
market_data = fetch_market_data()
market_context = compact_market_context(market_data)
snapshot_key = build_market_snapshot_key(market_context)

canonical_decision = snapshot_cache.get(snapshot_key)
if canonical_decision is None:
    canonical_decision = analyze_market_only(market_context)
    snapshot_cache.save(snapshot_key, canonical_decision)

geometry = extract_axis_geometry_only(uploaded_image)
canonical_analysis = validate_market_decision(canonical_decision, market_data)
render_analysis = bind_market_analysis_to_image(canonical_analysis, geometry)
result_png = render_result(render_analysis, uploaded_image)
```

## Consistency lock

```python
snapshot_key = sha256({
    "symbol": symbol,
    "H4": stable_h4_candles,
    "H1": stable_h1_candles,
    "M15": stable_m15_candles,
    "M5": stable_m5_candles,
})
```

- لا يدخل وقت الجلب `fetched_at` أو معلومات الكاش المؤقتة في المفتاح.
- الشمعة الجاري تكوينها تستخدم وقتها وسعر افتتاحها فقط داخل المفتاح؛ تغير High/Low/Close داخل الشمعة لا ينشئ قرارًا جديدًا.
- يبدأ Snapshot جديد عند بدء شمعة جديدة أو تغير بيانات الشموع المكتملة.
- يمنع قفل داخلي تنفيذ طلبين مختلفين لنفس Snapshot في الوقت نفسه.

## Broker price binding

```python
provider_current = canonical_analysis.current_price
broker_current = geometry.current_price or provider_current
broker_offset = broker_current - provider_current

broker_price = canonical_price + broker_offset
```

يُطبق `broker_offset` مرة واحدة على:

```text
candles.open/high/low/close
support_levels[].price
resistance_levels[].price
entry
stop_loss
target_1
target_2
target_3
nearest_support / nearest_resistance
```

ولا يطبق على:

```text
direction
probabilities
draw_mode
setup_state
strength
touches
scenario selection
```

## Axis rendering

```python
axis_model = calibrate_axis(geometry.image_axis_labels)
y = price_to_y(broker_price, axis_model)
```

يجب أن تستخدم العناصر التالية الدالة نفسها حرفيًا:

```text
current price line
R1 / R2 / S1 / S2
Entry / Stop / Cancel
TP1 / TP2 / TP3
مناطق الربح والخسارة
```

## Overlap handling

```text
true_y = price_to_y(real_price)
card_y = true_y

عند التداخل:
    حرّك card_y فقط داخل مسار البطاقة
    أبقِ true_y ثابتًا
    ارسم connector من true_y إلى card_y
```

- بطاقات التنفيذ تتحرك داخل المحور اليميني فقط.
- بطاقات الدعم والمقاومة تتحرك داخل المسار الأيسر فقط.
- لا تتحول وصلة البطاقة إلى مستوى سعري جديد.

## v3.61 — اتساق مطابقة صور المصادر

- قرار الاتجاه والصفقة يظل ثابتًا بمفتاح آخر شمعة M5 مغلقة كما هو.
- مطابقة صورة الشارت مع أطلس المصادر تختار عائلة نموذج فقط، ولا تنشئ أسعارًا أو قرارًا.
- لا تؤثر المطابقة البصرية على الرسم إلا إذا وجد المحرك الحتمي هندسة M5 من العائلة نفسها.
- اختلاف Zoom/Pan لا يسمح باختلاق نموذج؛ إذا لم تثبت نقاطه على شموع M5 الحقيقية يُستخدم fallback حتمي أو لا يرسم نموذج.
- الحد الأقصى Overlay لنموذج فني واحد في كل نتيجة.


## اعتماد v3.64 — ذاكرة السيناريو المرجعية

لكل شارت جديد تتم مقارنة الشكل مع ذاكرة الصور المرجعية، ثم اختيار سيناريو واحد فقط هو الأقرب. لا يُرسم السيناريو إلا بعد تحقق مكوناته حتميًا على شموع M5 المغلقة. الرسومات تكون Overlay ثابتًا فوق الشارت الأصلي، وتشمل فقط عناصر السيناريو المتحققة (BOS/CHOCH/IDM، OB، FVG، Liquidity، النموذج، وسهم التوقع). المرشح بسهم متقطع والمؤكد بسهم متصل. إذا فشل التحقق الهندسي فلا يظهر سيناريو ولا سهم تخميني. المرجع التنفيذي: `SALEEM_REFERENCE_SCENARIO_ENGINE_SPEC_V364.md`.
