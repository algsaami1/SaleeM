# Reverted axis model

- Returned to the previous approach that was visually closer.
- Build the right price axis from three anchors only:
  1. highest full visible price
  2. the price directly below it
  3. lowest full visible price
- The first two anchors define `price_step` and `ratio_step`.
- The bottom anchor validates the arithmetic sequence.
- The green current-price line no longer shifts the axis transform.
- If these three anchors are readable, the image renders using this model.
