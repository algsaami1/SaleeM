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
