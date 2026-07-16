# SaleeM — ChatGPT Analysis + Gemini Drawing

## Railway variables

- `OPENAI_API_KEY`: analyzes the uploaded chart.
- `OPENAI_MODEL`: defaults to `gpt-4.1-mini`.
- `GEMINI_API_KEY`: edits/annotates the chart image.
- `GEMINI_IMAGE_MODEL`: defaults to `gemini-2.5-flash-image`.

ChatGPT returns structured trading-chart observations and drawing instructions. Gemini receives the original image plus those instructions and returns an annotated copy. If Gemini drawing fails, the textual ChatGPT analysis still appears and the original image is shown.

This application provides educational analysis, not guaranteed trading signals.
