# SaleeM Reference Visual Clean V3 — 2026-08-10

## الهدف
تنظيف نتيجة الرسم لتصبح أقرب إلى أسلوب الرسومات التعليمية المرجعية مع إبقاء OHLC الحقيقي والهندسة الحتمية مصدر القرار والرسم.

## التعديلات
- جعل النموذج الرئيسي هو العنوان الوحيد الواضح؛ السيناريو المرجعي يظهر كتأكيد مختصر (BOS/CHOCH/OB/FVG...) وليس كنموذج ثانٍ منافس.
- خلفية تعليمية داكنة ونظيفة مع Grid خفيف جدًا.
- تكبير وإبراز هندسة النموذج الأساسية ومسارها، مع نقاط Pivot مضيئة وتسميات 1st/2nd/3rd Top أو Bottom عند توفرها.
- تقصير Support/Resistance إلى منطقة النموذج النشطة بدل تمريرها فوق كامل الشارت.
- منع Support/Resistance من التكدس فوق OB/FVG إذا كانت في نفس النطاق السعري.
- OB/FVG أصبحا مناطق مساعدة قصيرة بتسميات مختصرة.
- إبقاء BOS/CHOCH/Liquidity/Engulfing كطبقة SMC مساعدة قليلة النصوص.
- تقليص عرض صندوق Entry/Cancel(or Stop)/Target ووضعه داخل المساحة المستقبلية فقط.
- حذف بطاقة CURRENT الكبيرة؛ يظهر السعر الحالي فقط كوسم صغير على اليمين.
- حذف REFERENCE MATCH من الرسم النهائي.
- زيادة التاريخ المرئي يسارًا مع المحافظة على مساحة يمين للمسار والأهداف.
- Candidate يظل متقطعًا وConfirmed متصلًا؛ لم تتغير بوابات التنفيذ أو قرار BUY/SELL/مراقبة.

## الملفات المعدلة
- app/engine/renderer.py
- tests/test_reconstructed_chart_v366.py
- tests/test_reference_sheet_visual_cleanup_v3.py

## ملفات لم تتغير
- app/engine/pattern_engine.py
- app/engine/reference_scenario_engine.py
- app/services/analyzer.py

## الاختبارات
- python3 -m py_compile app/engine/pattern_engine.py app/engine/renderer.py app/services/analyzer.py : PASS
- pytest -q : 193 passed

## حالات رفض الرسم
تظل بوابات SaleeM الحالية كما هي: إذا لم تتوفر هندسة حتمية موثوقة أو لم ينجح اختيار النموذج/السيناريو، لا يتم اختلاق نموذج أو X/Y جديد، وتبقى النتيجة في وضع المراقبة/بدون رسم مرجعي حسب المنطق الحالي.
