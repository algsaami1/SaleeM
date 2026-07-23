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
