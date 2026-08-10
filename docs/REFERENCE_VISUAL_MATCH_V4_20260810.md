# SaleeM Reference Visual Match V4 — 2026-08-10

## Visual changes
- Restored a generated market-price axis on the right from real OHLC/plan prices; it is not read from the uploaded screenshot.
- Added exact-price compact cards for ENTRY/ENTRY IF, STOP/CANCEL, TARGET and PRICE.
- Switched the reconstructed result to a light educational reference-sheet palette closer to the supplied Marbs FX examples.
- Primary teaching headline now uses the selected reference template (e.g. GOOD ENTRY POINTS / TREND REVERSAL), with the deterministic detected model directly underneath.
- Pattern pivots use clearer red/green focus rings and thicker educational zig-zag lines.
- SMC helper labels use dark high-contrast text on the light chart and remain secondary to the pattern.
- Entry/stop/target future box remains tied to deterministic prices and is drawn in the future area only.
- Wider left candle history and right future room remain unchanged.

## Safety / deterministic behavior
- No price geometry is taken from the uploaded screenshot axis.
- H4/H1/M15/M5 market data and existing deterministic engines remain authoritative.
- No second analysis engine was added.
- Pattern candidate/confirmed rules were not changed.

## Validation
- python3 -m py_compile app/engine/renderer.py app/engine/pattern_engine.py app/services/analyzer.py app/main.py: PASS
- pytest -q: 194 passed
