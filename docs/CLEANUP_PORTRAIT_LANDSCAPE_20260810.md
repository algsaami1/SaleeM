# SaleeM — Cleanup + Portrait → Landscape

Date: 2026-08-10

## Scope

Work was applied directly to the GitHub archive supplied by the user. No older project archive was used as the source tree.

The existing deterministic analysis stack remains in place:
- `app/services/analyzer.py`
- `app/engine/pattern_engine.py`
- `app/engine/reference_scenario_engine.py`
- the existing 43-rule reference library

No parallel analysis engine was added.

## Visual flow implemented

- Portrait and landscape screenshots are both accepted.
- A portrait screenshot is treated as visual/calibration evidence only.
- The final portrait-input result is rebuilt as a 1600×900 landscape chart from real market OHLC.
- H4/H1/M15/M5 closed market candles remain authoritative for decision and geometry.
- Landscape uploads retain the current native-pixel overlay behavior.
- Optional manual calibration fields were added for:
  - current visible price
  - top visible axis price
  - bottom visible axis price
- Manual calibration changes only visual calibration fields; it cannot change market OHLC, direction, Entry/Stop/Targets, or BUY/SELL/watch gates.

## Pattern rendering changes

- Candidate Flag/Pennant keeps deterministic `trigger/stop/target` while status stays `candidate`.
- Candidate Ascending/Descending Triangle keeps deterministic conditional plan while status stays `candidate`.
- Candidate Rising/Falling Wedge keeps deterministic conditional plan while status stays `candidate`.
- Candidate pattern boundaries/path are dashed.
- Confirmed pattern lines are solid.
- Candidate labels use `مرشح`, `ENTRY IF`, `CANCEL`, and `TARGET` where deterministic geometry exists.
- Unbroken Symmetrical Triangle stays neutral and has no synthetic directional trigger/target.
- The primary deterministic pattern remains visible when a reference scenario also adds SMC/structure overlays.
- The reconstructed chart shows at most one nearest support and one nearest resistance.

## Cleanup performed

Removed obvious non-runtime backup/patch artifacts:
- `_visual_story_backup_20260809_124409/`
- `app/services/analyzer.py.backup_before_reference`
- `app/services/analyzer.py.before_catalog_bridge`
- `app/services/analyzer.py.before_reference`
- `SALEEM59_CHANGED_FILES.txt`
- `SALEEM_UI_V370_INTERACTIVE_ANALYSIS.txt`
- `SALEEM_UI_V371_FULLSCREEN_CHART.txt`
- `SALEEM_UI_V372_CHART_FIT_FIRST.txt`
- `SALEEM_UI_V373_COMPACT_PAN_ZOOM.txt`
- `SALEEM_UI_V374_GALLERY_HORIZONTAL_UPLOAD.txt`
- `SALEEM_UI_V3741_ERROR_DETAIL.txt`

`.gitignore` was extended so local SaleeM backup/patch artifacts do not return to Git.

The reference images and 43-rule reference library were preserved.

## Tests

Before modifications, the downloaded GitHub archive had 3 existing test failures and 176 passes. Two failures came from the horizontal-only upload guard, and one from the zoom-cap mismatch.

After the changes:

- `python3 -m py_compile app/engine/pattern_engine.py app/engine/renderer.py app/services/analyzer.py` — PASS
- Full test suite — `185 passed`
- Reference library count — `43`
- `ScenarioTemplate` count — `9`

New acceptance tests cover:
- candidate Ascending/Descending Triangle conditional plans
- candidate Rising/Falling Wedge conditional plans
- candidate bullish/bearish Flag and Pennant conditional plans
- unbroken Symmetrical Triangle remaining neutral
- portrait input producing a 1600×900 OHLC landscape result
- manual axis calibration not changing market decision values

## Drawing refusal / safety cases preserved

SaleeM does not invent a drawing when geometry is not trustworthy:
- visual similarity alone cannot create a reference scenario without M5 geometry
- a neutral unbroken Symmetrical Triangle receives no artificial direction
- absent deterministic pattern geometry means no fabricated pattern overlay
- unreliable native-axis projection hides price-linked elements instead of guessing X/Y
- invalid manual axis values are rejected rather than translated into market geometry

