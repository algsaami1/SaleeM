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
