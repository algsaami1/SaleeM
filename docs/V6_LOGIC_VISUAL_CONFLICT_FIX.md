# SaleeM v3.68 — Reference Visual Logic Conflict Fix

This patch keeps the existing analysis engines and execution gates unchanged and fixes renderer-only contradictions found in the reference-sheet output.

## Fixed lifecycle contradictions

- Candidate: `ENTRY IF / CANCEL / TARGET` with dashed conditional path.
- Pattern confirmed but SaleeM execution gate blocked: `PATTERN CONFIRMED · WATCH`; never shown as an actionable confirmed trade.
- Execution confirmed: `ENTRY / STOP / TARGET` with solid path.
- Target already reached by the closed M5 market price: `TARGET HIT`; no new-entry risk/reward box is drawn.
- Stop/cancel already violated: `SETUP INVALIDATED`; no future trade box is drawn.
- Conditional setup already beyond its target before execution confirmation: `SETUP EXPIRED`, not `TARGET HIT`.

The closed M5 market price drives lifecycle. Image/manual current price is display-only fallback and cannot change the decision.

## Visual cleanup

- One coherent educational headline.
- Larger, clearer exact price cards and 9 generated OHLC-axis ticks.
- Green/earth-tone Order Block and light-blue FVG zones inspired by the supplied visual references.
- The future lane stays geometrically stable across setup lifecycle states; completed/invalidated setups hide the risk box instead of shifting chart geometry.
- Existing one-primary-pattern limit, support/resistance limit, deterministic pivots, and no-guessed-X/Y rules remain unchanged.
