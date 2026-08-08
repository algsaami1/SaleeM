# SaleeM v3.17 — Chart Viewport Extraction

## القاعدة الأساسية

تستخدم مرحلة قراءة هندسة المحور ومرحلة الرسم النهائي نافذة الشارت نفسها حرفيًا. لا يجوز أن تقرأ مرحلة المحور صورة مختلفة عن الصورة التي تُلصق في النتيجة.

## Pipeline

1. Normalize the uploaded screenshot to the canonical chart viewport.
2. Detect a top one-click trading toolbar using both color and structural change detection.
3. Remove the toolbar by cropping the pixels, never by painting a blank band.
4. Uniformly scale the remaining chart and original right price axis together.
5. Right-align the result so the broker price axis is never lost.
6. Use this exact viewport for geometry extraction, axis validation, current-line detection, and final rendering.

## Invariants

- The toolbar does not consume chart height.
- The chart and its price axis always receive the same transform.
- No independent vertical stretching is allowed.
- Zoom or order-panel presence changes only image geometry, not the locked market decision.
- The latest closed M5 candle remains the analysis snapshot key.
