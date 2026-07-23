# Strict image-axis calibration with Auto-scale retry

- The uploaded chart axis is calibrated from the first complete price tick, the immediately following tick, and the lowest complete tick.
- The real current-price line corrects only a small global vertical offset caused by cropping or resizing.
- The right axis, current price, entry, stop, targets, support and resistance all use the same transform.
- If the axis sequence, current-price line, or their spacing cannot be validated, SaleeM does not render an approximate result.
- The UI asks the user to enable Auto-scale / الضبط التلقائي, keep the full right price axis and current-price line visible, then upload a new screenshot.
- A retry button scrolls to the upload area and opens the image picker.
