# SaleeM v3.15 — Market Snapshot Consistency

## Architecture

```text
Uploaded screenshot
    └── Geometry request only
        ├── current_price
        ├── current_price_y_ratio
        ├── image_price_high / image_price_low
        └── image_axis_labels[]

Twelve Data H4/H1/M15/M5
    └── Stable market-decision request
        ├── direction / probabilities / state
        ├── R1/R2/S1/S2
        ├── Entry / Stop / Targets
        └── scenarios and confirmation

Stable market decision + image geometry
    └── One broker-price offset
        └── One price_to_y transform
            └── Final overlay on the uploaded chart
```

## Rules

1. The screenshot is never used to decide direction, state, probability, support, resistance, entry, stop, or targets.
2. The decision uses H4 for trend, H1 for structure, M15 for activation, and M5 for timing.
3. A snapshot key is calculated from the actual OHLC candles used by the decision request. Volatile metadata such as fetch time is excluded.
4. The same snapshot key reuses the same market decision.
5. The image request returns geometry only and cannot change the market decision.
6. Canonical prices are calculated on the Twelve Data scale, then shifted once to the broker scale using:

```text
broker_offset = image_current_price - provider_current_price
broker_level  = canonical_level + broker_offset
```

7. All overlays use the same final price-to-Y transform.
8. Support/resistance and execution lines remain at their true prices. Only cards may move to avoid overlap.

## Rendering behavior

```python
geometry = extract_chart_geometry(uploaded_image)
snapshot_key = build_market_snapshot_key(market_frames)
canonical_decision = cache.get(snapshot_key) or analyze_market(market_frames)
canonical_analysis = validate(canonical_decision, market_frames)
render_analysis = bind_to_broker_axis(canonical_analysis, geometry)
render(render_analysis, uploaded_image)
```

The binding stage shifts these fields together:

```text
candles.open/high/low/close
support_levels[].price
resistance_levels[].price
entry
stop_loss
target_1
target_2
target_3
nearest support/resistance metadata
```

The following decision fields never change because of zoom or screenshot layout:

```text
direction
buy_probability / sell_probability
draw_mode / setup state
entry kind and confirmation
support/resistance identity and strength
scenario selection
```

## Consistency lock

```text
same H4/H1/M15/M5 candles
        ↓
same snapshot key
        ↓
same analytical decision
        ↓
new screenshot geometry only
        ↓
same prices, newly calibrated Y coordinates
```

The lock is stored by default at:

```env
ANALYSIS_SNAPSHOT_CACHE_PATH=/tmp/saleem_analysis_snapshot_cache.json
```

For Railway Volume:

```env
ANALYSIS_SNAPSHOT_CACHE_PATH=/data/saleem_analysis_snapshot_cache.json
```

Optional controls:

```env
ANALYSIS_SNAPSHOT_CACHE_ENABLED=1
ANALYSIS_SNAPSHOT_CACHE_ENTRIES=24
```

## Axis accuracy

The renderer keeps one mathematical scale:

```text
image axis labels → calibrated price range → price_to_y(price)
```

The current-price line, R/S levels, Entry, Stop/Cancel, and TP levels all pass through that same conversion. The detected green line is used only as an anchor while calibrating the transform; it is not a second independent scale.
