from io import BytesIO

from PIL import Image

from app.engine.reference_scenario_engine import build_reference_features, review_reference_scenarios
from app.engine.renderer import _recon_index_to_actual, render_result


def _bearish_reference_candles():
    closes = []
    for i in range(30):
        closes.append(4360 + i * (31 / 29))
    closes += [
        4391.5, 4392.4, 4392.8, 4391.4, 4389.8, 4388.9, 4389.7,
        4391.0, 4392.2, 4392.7, 4391.5, 4390.2, 4389.0, 4388.5,
        4389.4, 4391.2, 4392.5, 4392.9, 4391.6, 4390.0,
    ]
    start = closes[-1]
    for i in range(20):
        closes.append(start - (i + 1) * 0.9)
    start = closes[-1]
    for i in range(10):
        closes.append(start + (i + 1) * 2.0)
    closes += [4392.0, 4389.5]
    start = closes[-1]
    for i in range(15):
        closes.append(start - (i + 1) * 1.0)

    rows = []
    prev = closes[0] - 0.3
    for i, raw_close in enumerate(closes):
        close = raw_close
        open_ = prev
        high = max(open_, close) + 0.35
        low = min(open_, close) - 0.35
        if i in {32, 39, 47}:
            high = 4393.35 + (i % 3) * 0.04
        if i == 80:
            high = 4394.6
            close = 4392.0
        rows.append({
            "time": f"2026-08-11T{(17 + (i * 5) // 60) % 24:02d}:{(i * 5) % 60:02d}:00",
            "open": open_, "high": high, "low": low, "close": close,
        })
        prev = close
    return rows


def test_v7_detects_equal_high_liquidity_and_real_sweep():
    candles = _bearish_reference_candles()
    pattern_review = {"candidates": [{"timeframe": "M5", "confidence": 88, "name": "قمة ثلاثية"}]}
    built = build_reference_features({"M5": candles}, pattern_review)
    cluster = built["geometry"]["equal_highs"]
    assert cluster is not None
    assert cluster["count"] == 3
    assert [p["index"] for p in cluster["points"]] == [32, 39, 47]
    sweep = built["geometry"]["liquidity_sweep_high"]
    assert sweep is not None
    assert sweep["index"] == 80
    assert sweep["source"] == "equal_liquidity"


def test_v7_bearish_scenario_pairs_ob_fvg_with_sweep_not_tail_gap():
    candles = _bearish_reference_candles()
    pattern_review = {"candidates": [{"timeframe": "M5", "confidence": 88, "name": "قمة ثلاثية"}]}
    scenario = review_reference_scenarios({"M5": candles}, pattern_review)
    assert scenario["available"] is True
    assert scenario["bias"] == "هابط"
    assert scenario["geometry"]["liquidity_sweep"]["side"] == "high"
    assert scenario["geometry"]["order_block"]["side"] == "bear"
    assert scenario["geometry"]["fvg"]["side"] == "bear"
    assert scenario["geometry"]["fvg"]["index"] >= scenario["geometry"]["liquidity_sweep"]["index"]
    assert scenario["geometry"]["fvg"]["index"] <= scenario["geometry"]["liquidity_sweep"]["index"] + 18


def test_v7_detector_indices_map_to_trailing_render_window():
    assert _recon_index_to_actual(200, 240, 120) == 80
    assert _recon_index_to_actual(239, 240, 120) == 119
    assert _recon_index_to_actual(120, 240, 120) == 0


def test_v7_reference_renderer_stays_16_by_9_and_renders_real_plan():
    candles = _bearish_reference_candles()
    pattern_review = {"candidates": [{"timeframe": "M5", "confidence": 88, "name": "قمة ثلاثية"}]}
    scenario = review_reference_scenarios({"M5": candles}, pattern_review)
    analysis = {
        "candles": candles,
        "reconstructed_market_chart": True,
        "current_price": candles[-1]["close"],
        "pattern_type": "قمة ثلاثية",
        "pattern_status": "confirmed",
        "pattern_confidence": 90,
        "reference_match_score": 90,
        "reference_visual_score": 90,
        "visual_template_id": "multiple_tops",
        "pattern_bias": "هابط",
        "pattern_overlays": [{
            "name": "قمة ثلاثية", "status": "confirmed", "bias": "هابط", "confidence": 90,
            "geometry": {
                "window_size": len(candles),
                "anchors": [
                    {"index": 32, "price": candles[32]["high"], "role": "pivot"},
                    {"index": 39, "price": candles[39]["high"], "role": "pivot"},
                    {"index": 47, "price": candles[47]["high"], "role": "pivot"},
                ],
                "lines": [], "path": [],
                "trigger": 4383.5, "stop": 4395.0, "target": 4365.0,
                "breakout_index": 60,
            },
        }],
        "support_levels": [{"price": 4370.0, "strength": 80}],
        "resistance_levels": [{"price": 4393.4, "strength": 92}],
        "reference_scenario_available": scenario["available"],
        "reference_scenario_id": scenario["scenario_id"],
        "reference_scenario_confidence": scenario["confidence"],
        "reference_scenario_status": scenario["status"],
        "reference_scenario_bias": scenario["bias"],
        "reference_scenario_geometry": scenario["geometry"],
        "reference_scenario_draw_components": scenario["draw_components"],
        "action_summary": {"primary_side": "sell", "is_confirmed": True},
        "entry": 4383.5, "stop_loss": 4395.0, "target_1": 4365.0,
    }
    png = render_result(analysis)
    with Image.open(BytesIO(png)) as image:
        assert image.size == (1920, 1080)
        rgb = image.convert("RGB")
        # The output must contain both red stop-side and green target-side pixels.
        pixels = list(rgb.crop((1100, 160, 1420, 720)).get_flattened_data())
        assert any(r > 150 and r > g * 1.25 for r, g, b in pixels)
        assert any(g > 120 and g > r * 1.15 for r, g, b in pixels)
