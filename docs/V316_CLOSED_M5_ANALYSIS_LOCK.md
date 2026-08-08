# SaleeM v3.16 — Closed M5 Analysis Lock

## Rules

```text
analysis_version = (symbol, "M5", last_closed_m5_timestamp)
```

- Decision input contains closed H4/H1/M15/M5 candles only.
- The forming candle is excluded from direction, state, levels, Entry, Stop and targets.
- The same `analysis_version` reuses one cached decision.
- A new decision is generated only when a new M5 candle closes.
- Screenshot zoom, vertical scale, and trade controls affect geometry only.

## Pipeline

```python
market_data = fetch_market_data()
closed_context = keep_closed_candles_only(market_data)
version_key = hash(symbol, "M5", closed_context.last_m5.time)
decision = cache.get(version_key) or analyze(closed_context)
geometry = extract_axis_geometry(screenshot)
result = project_prices_to_axis(decision, geometry)
```

## Forming candle

The forming candle may be used only for a live fallback price or trigger checks. It cannot mutate the cached analytical decision.
