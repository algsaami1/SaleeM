> **ملاحظة:** هذا المستند تاريخي فقط. أُلغي التنفيذ المتحرك في v3.63 واستُبدل بـ `V363_STATIC_REFERENCE_OVERLAY.md`.

# SaleeM v3.51 — Animation Spec v1

The result keeps the uploaded broker chart as the original canvas. A live SVG layer sits above it and shares the same pan/zoom transform.

## Scenario path
The primary path is available for BUY, SELL, WATCH BUY and WATCH SELL when strict geometry is trusted. It explains:

1. current price / latest calibrated candle
2. break of the nearest activation level
3. retest / correction near the broken level
4. short continuation in the expected direction

The continuation is intentionally clipped; it does not stretch visually to a distant TP. Actual targets remain in the analysis.

## Strict geometry
- X is accepted only from the calibrated screenshot candle map.
- Y is accepted only from the strict pixel-derived price model.
- Missing X/Y disables the animation rather than guessing.
- W/M skeleton animation is supported in v1 only when every model point is anchored.

## Timing
The sequence is approximately 3.6 seconds: pattern -> activation -> zone -> scenario path -> retest -> invalidation. A replay button is available and reduced-motion preferences are respected.

## Save/share
The renderer also draws the final still version of the same break/retest/continuation path so saved PNG output retains the scenario explanation.
