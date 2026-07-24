# Native iPhone black-canvas output

- Final PNG size: 1320 × 2868.
- Visible uploaded-chart viewport: 1111 × 2243.
- No non-uniform resizing, stretching, or squeezing.
- For a 1320 × 2868 upload, the renderer keeps native pixels exactly:
  - removes 209 px from the left,
  - removes 312 px from the top,
  - removes 313 px from the bottom.
- The source chart's original right price axis remains visible.
- A separate 209 px right strip is reserved for the additional synchronized SaleeM axis.
- All unused canvas areas remain pure black for later editing.
- Analysis notes remain outside the generated image in the web result page.
