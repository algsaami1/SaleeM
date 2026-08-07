# SaleeM v3.47 — Strict pixel price-axis alignment

- The uploaded broker chart remains untouched and is the only visual canvas.
- OCR/vision y-ratios no longer decide overlay height in native uploaded-chart mode.
- The current broker price line is detected directly from source pixels.
- Horizontal broker grid spacing is detected directly from recurring source grid rows.
- Axis-label numerical values determine the broker tick price step.
- One transform maps every R/S, OB/FVG, BOS/CHOCH/IDM, pattern point, Entry/SL/TP to Y.
- The transform is validated by projecting broker tick values back onto detected source grid rows.
- If strict pixel calibration cannot be validated, price-linked overlays are hidden instead of guessed.
