# سجل تعديلات SaleeM التاريخي
> هذا الملف يجمع ملاحظات التعديل القديمة للرجوع إليها فقط. المرجع التشغيلي الحالي هو `SALEEM_FINAL_SPEC.md` والكود والاختبارات.

---

## MODIFICATIONS_5.5.md

# SaleeM 5.5 — Full-page result chart

- Removed the status/header/information cards from the generated result image.
- Expanded the chart from the top of the image down to the analysis-notes section.
- Kept the analysis-notes box as the only lower section.
- Added a regression test for the new vertical layout.

---

## MODIFICATIONS_5.6.md

# SaleeM 5.6 — ربط جميع الرسومات بالخط الأخضر

- أصبح الخط الأخضر المكتشف من صورة الشارت مرجعًا لمحول السعر كاملًا، وليس لخط السعر الحالي وحده.
- تتحرك معه تلقائيًا جميع الإضافات: الدعم، المقاومة، FVG، Order Block، الدخول، الوقف، TP1/TP2/TP3 والسهم.
- يستخدم محور السعر والرسومات نفس التحويل حتى تبقى الأسعار في مواضع متوافقة.
- تتم زيادة النطاق المرئي فقط عند الحاجة لمنع قص مستوى مهم عند اقتراب الخط الأخضر من حافة الشارت.

---

## MODIFICATIONS_APPROVED_AXIS_CARD_LAYOUT.md

# Approved chart-overlay layout

Implemented the visual layout approved on 2026-07-24.

- The uploaded chart viewport remains the background; its native price axis and current-price badge are not redrawn.
- Support and resistance cards remain compact on the left and include whole-number price plus strength percentage.
- Entry, SL, TP1, TP2, TP3, Active, Cancel, Buy, and Sell cards are compact English-only rectangles inside the added right strip.
- Right-side cards use whole-number prices, stay within the axis, and move vertically to avoid overlap while retaining an elbow connector to the exact price Y.
- The added right strip no longer repeats top, bottom, or current-price numbers.
- Target and risk areas are transparent green/red rectangles without borders.
- FVG and OB zones are long rectangular overlays with their labels inside the zones.
- Projected candles are slightly wider and finish at the selected target.
- Header uses five English cards: Direction, Model, Confluence, Probability, and Trade Type.

Validation: all 57 tests pass.

---

## MODIFICATIONS_AXIS_PULL_AND_CARDS.md

# Axis pull + right-side cards

- Pulled the highest right-axis price label upward and the lowest one downward.
- Moved Entry and Stop cards into the right price-axis strip.
- Shifted analysis zones left to keep space near the right chart edge.
- Removed borders from the green/red analysis zones.

---

## MODIFICATIONS_AXIS_TOP_BOTTOM_TPS.md

# Axis extreme anchors + TP cards in right axis

- Pulled the highest visible right-axis label closer to the top edge.
- Pulled the lowest visible right-axis label closer to the bottom edge.
- Kept Entry, Stop, and TP1/TP2/TP3 cards inside the right price-axis strip.

---

## MODIFICATIONS_AXIS_TOP_NEXT_BOTTOM.md

# تعديل محور السعر: أعلى سعر + السعر التالي + أدنى سعر

- يقرأ البرنامج أعلى رقم كامل ظاهر في محور صورة الشارت.
- يستخدم الرقم الذي تحته مباشرة لحساب فرق السعر والمسافة الرأسية الحقيقية.
- يستخدم أدنى رقم كامل كحد سفلي وللتحقق من أن الرقم الثاني متتالٍ فعلًا.
- يتجاهل قراءات OCR الوسطية عند حساب المقياس حتى لا يفسد رقم خاطئ المحور كله.
- يولّد محور اليمين كسلسلة حسابية واحدة، من دون رقم إضافي أعلى أو أسفل الصورة.
- تستخدم الشموع والدخول والوقف والأهداف والدعم والمقاومة التحويل السعري نفسه.
- يحتفظ بخط السعر الحالي الحقيقي عندما يكون متوافقًا مع المحور، ويرفض اكتشاف خط بعيد وغير منطقي.
- يعود إلى المقياس الاحتياطي السابق إذا لم تتوفر ثلاث نقاط صحيحة.

---

## MODIFICATIONS_AXIS_TP_RIGHT.md

# Axis/top-bottom/TP adjustments

- Moved the highest visible right-axis price closer to the top edge.
- Moved the lowest visible right-axis price closer to the bottom edge.
- Moved TP1 / TP2 / TP3 cards into the right price-axis strip, alongside entry/stop.

---

## MODIFICATIONS_CURRENT_PRICE_ANCHOR.md

# مزامنة السعر الحالي مع خط الصورة

- تثبيت السعر الحالي على موضع الخط الأفقي الحقيقي المكتشف في صورة الشارت.
- تحسين اكتشاف الخط بحيث يفضّل الخط الرفيع الممتد إلى يمين الشارت ويتجاهل مناطق TP الخضراء والشموع الصاعدة.
- إضافة `current_price_y_ratio` كمرجع احتياطي عندما لا يمكن اكتشاف الخط بوضوح من البكسلات.
- ربط محور السعر الأيمن والدعم والمقاومة والدخول والوقف والأهداف بمحول سعر واحد بعد تثبيت السعر الحالي.
- إضافة اختبارات تمنع انحراف أرقام المحور عن خطوط الرسومات.

## تنظيف ملفات المعاينة

- حُذفت صور المعاينة المحلية `preview*.png` و`demo_bg.png` لأنها ليست جزءًا من تشغيل التطبيق.
- أضيفت قواعد إلى `.gitignore` لمنع إضافتها مستقبلًا إلى Git.
- أضيفت `.dockerignore` لمنع نسخ ملفات المعاينة والملفات المؤقتة إلى صورة Docker عند النشر.

---

## MODIFICATIONS_EXACT_AXIS_MODE.md

# Exact Axis Mode

- Reads all clearly visible right-axis price labels and their original vertical positions.
- Cleans duplicate and inconsistent OCR readings.
- Uses a robust linear fit and rejects outlier prices.
- Enables Exact Axis Mode only when at least five consistent labels and sufficient chart coverage are available.
- Redraws accepted axis labels at their original Y positions.
- Uses the same fitted price transform for candles, support/resistance, entry, stop, and TP levels.
- Falls back to Reconstructed Axis Mode using the inner anchor prices when exact calibration is unavailable.
- Keeps the green current-price badge attached to the detected current-price line.
- Does not require a minimum number of candles in the uploaded screenshot.

---

## MODIFICATIONS_EXACT_IMAGE_AXIS.md

# Exact image price-axis synchronization

- The right price axis now copies every readable source label at its original
  vertical `y_ratio` instead of recalculating its Y position from a generated
  scale.
- No label is generated above the first source label or below the last source
  label.
- Partially clipped edge labels remain clipped and are not moved into the
  visible area.
- Right-axis prices always display two decimal places (for example `4049.10`
  and `4055.80`).
- The analyzer instruction explicitly forbids extrapolating missing endpoint
  prices from the numeric sequence.

---

## MODIFICATIONS_NATIVE_IPHONE_BLACK_CANVAS.md

# Native iPhone black-canvas output

- Final PNG size: 1320 × 2868.
- Visible uploaded-chart viewport: 1111 × 2243.
- No non-uniform resizing, stretching, or squeezing.
- For a 1320 × 2868 upload, the renderer keeps native pixels exactly:
  - removes 209 px from the left,
  - removes 312 px from the top,
  - removes 313 px from the bottom.
- The source chart's original right price axis remains visible.
- A separate 209 px right strip is reserved for the additional synchronized SaleeM axis.
- All unused canvas areas remain pure black for later editing.
- Analysis notes remain outside the generated image in the web result page.

---

## MODIFICATIONS_OVERLAY_ONLY_V1_2.md

# SaleeM Overlay-Only Layout v1.2

- Preserved the uploaded chart image at the same size and position.
- Reduced top summary card height without moving the chart.
- Added two-line compact pattern names.
- Watch mode: Trigger / Invalid only, no targets or arrow.
- Conditional mode: dashed Entry / SL / TP lines and dashed scenario arrow.
- Confirmed mode: displayed as active with solid lines and arrow.
- Reduced and unified right-axis execution cards.
- Compacted support/resistance badges.
- Reduced OB and FVG size/opacity and tightened their display conditions.
- Reduced session footer height and emphasized only the active session.
- Added renderer tests for watch/conditional display logic.

---

## MODIFICATIONS_PERMANENT_THREE_STATE_RULE.md

# قاعدة SaleeM الدائمة: صفقة / بشرط / مراقبة

- **صفقة:** شراء أو بيع مع دخول ووقف وTP1 وTP2 وTP3 وشموع توقع بعد آخر شمعة حقيقية.
- **بشرط:** أقرب اتجاه فقط، مع بطاقتي **تفعيل** و**إلغاء**، ولا تُرسم شموع التوقع إلا من نقطة التفعيل.
- **مراقبة:** تبقى الدعوم والمقاومات وOrder Block وFVG ظاهرة، ويُعرض أقرب احتمال شراء وأقرب احتمال بيع دون اعتباره صفقة مؤكدة.
- لا يُمس شارت الصورة الأصلية ولا شموعه ولا أبعاده.
- تُضاف شموع التوقع فقط في مساحة المستقبل قرب آخر شمعة وبداية الانطلاق.
- لا توجد أسهم ولا كلمة «سيناريو» داخل الشارت.
- البطاقة العلوية الأخيرة هي **نوع الصفقة**: بشرط برتقالي، مراقبة أزرق، شراء أخضر، بيع أحمر.

---

## MODIFICATIONS_PRICE_AXIS_BINDING.md

# Price Axis Binding Update

تم اعتماد محور أسعار الشارت الأصلي كمرجع رأسي وحيد لجميع طبقات الأسعار.

## التنفيذ

- جميع الأسعار تستخدم التحويل النهائي المشترك `price -> Y`.
- بطاقات Entry / SL / TP / Trigger / Invalid تتمركز عند Y الحقيقي للسعر.
- ألغي تحريك بطاقات التنفيذ رأسيًا عند التداخل.
- يعالج التداخل بمسارات أفقية تتجه إلى اليسار فقط.
- السعر الحالي يعاد إسقاطه دائمًا عبر التحويل المشترك بعد انتهاء معايرة المحور.
- تمت إضافة معلومات تشخيصية:
  - `price_axis_binding = original_chart_single_transform`
  - `price_axis_overlap_policy = horizontal_only`

---

## MODIFICATIONS_REVERT_TOP_NEXT_BOTTOM.md

# Reverted axis model

- Returned to the previous approach that was visually closer.
- Build the right price axis from three anchors only:
  1. highest full visible price
  2. the price directly below it
  3. lowest full visible price
- The first two anchors define `price_step` and `ratio_step`.
- The bottom anchor validates the arithmetic sequence.
- The green current-price line no longer shifts the axis transform.
- If these three anchors are readable, the image renders using this model.

---

## MODIFICATIONS_SINGLE_AXIS_TRANSFORM.md

# تعديل مطابقة الشارت مع المحور اليميني

- إلغاء قص صورة الشارت أثناء ملاءمتها لمساحة الرسم؛ تُحفظ جميع المواضع الرأسية النسبية كما ظهرت في الصورة.
- استخدام سلسلة أرقام المحور لتحديد مقدار الحركة السعرية لكل نسبة رأسية.
- استخدام خط السعر الحالي الأخضر لتحديد إزاحة المحور الرأسية عند توفره.
- تمرير أرقام المحور اليميني والشموع والدعم والمقاومة والدخول والوقف والأهداف والسعر الحالي عبر تحويل سعري واحد فقط.
- منع بطاقات السعر أو أرقام المحور من تجاوز التحويل الحسابي بوضع رأسي منفصل.
- تحديث اختبارات المحور للتحقق من أن كل سعر يطابق موضعه على المحور نفسه.

التحقق: 42 اختبارًا ناجحًا.

---

## MODIFICATIONS_STRICT_AXIS_AUTOSCALE_RETRY.md

# Strict image-axis calibration with Auto-scale retry

- The uploaded chart axis is calibrated from the first complete price tick, the immediately following tick, and the lowest complete tick.
- The real current-price line corrects only a small global vertical offset caused by cropping or resizing.
- The right axis, current price, entry, stop, targets, support and resistance all use the same transform.
- If the axis sequence, current-price line, or their spacing cannot be validated, SaleeM does not render an approximate result.
- The UI asks the user to enable Auto-scale / الضبط التلقائي, keep the full right price axis and current-price line visible, then upload a new screenshot.
- A retry button scrolls to the upload area and opens the image picker.

---

## MODIFICATIONS_THREE_STATE_PERMANENT_RULE.md

# SaleeM 3.9 — القاعدة الدائمة للحالات الثلاث

تم تثبيت القاعدة التالية داخل منطق التحليل والرسم والمواصفة النهائية:

- **صفقة:** شراء أو بيع مع دخول ووقف وTP1/TP2/TP3 وشموع توقع بعد آخر شمعة حقيقية.
- **بشرط:** أقرب اتجاه واحد فقط، مع بطاقتي **تفعيل** و**إلغاء**، وتبدأ شموع التوقع من التفعيل.
- **مراقبة:** احتمال شراء واحتمال بيع غير مؤكدين، ويُرسم لكل منهما مسار شموع قصير من مستوى التفعيل.

## قواعد الرسم المثبتة

- الحفاظ على صورة الشارت الأصلية وعدم إعادة رسم شموعها.
- اكتشاف موضع آخر شمعة حقيقية من الصورة، ثم بدء شموع التوقع بجانبها مباشرة.
- حذف الأسهم ومساراتها نهائيًا.
- حذف كلمة «سيناريو» من الواجهة المرئية.
- إظهار الدعوم والمقاومات وOrder Block وFVG في كل الحالات، مع fallback بصري خفيف عند عدم اكتشاف منطقة قوية.
- استبدال بطاقة «الجلسة» العلوية ببطاقة «نوع الصفقة»:
  - بشرط: برتقالي.
  - مراقبة: أزرق.
  - شراء: أخضر.
  - بيع: أحمر.
- تبقى الجلسات في الشريط السفلي.

## التحقق

تمت إضافة اختبارات للحالات الثلاث، وشموع المراقبة، وموضع آخر شمعة، وظهور OB/FVG دائمًا.

نتيجة الاختبارات: **57 passed**.

## تثبيت مركز بطاقات الأسعار على الخط — 2026-07-26
- إلغاء توزيع تسميات الدعم والمقاومة رأسيًا عند تقارب المستويات.
- مركز كل تسمية دعم أو مقاومة أصبح مطابقًا حرفيًا لموضع خط السعر.
- الإبقاء على تداخل البطاقات بدل تحريكها بعيدًا عن السعر الحقيقي.
- إضافة اختبار آلي للمستويات المتقاربة للتأكد من تطابق مركز البطاقة مع `price_to_y`.
