import random

import app.engine.renderer as renderer
from app.engine.reference_scenario_engine import _order_blocks
from app.services.analyzer import _market_segment_signature, _match_visual_market_segment


def _market_rows(count=48):
    random.seed(74)
    rows = []
    price = 4380.0
    for i in range(count):
        # Deterministic but irregular sequence so a 10-candle fingerprint is unique.
        delta = random.choice([-1.25, -0.8, -0.35, 0.28, 0.65, 1.1]) + (0.07 if i % 7 == 0 else 0.0)
        open_ = price
        close = open_ + delta
        up_wick = 0.18 + (i % 5) * 0.09
        down_wick = 0.16 + (i % 4) * 0.07
        high = max(open_, close) + up_wick
        low = min(open_, close) - down_wick
        rows.append({
            "time": f"2026-08-11T{17 + (i * 5) // 60:02d}:{(i * 5) % 60:02d}:00",
            "open": round(open_, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
        })
        price = close
    return rows


def test_v74_visual_fingerprint_selects_exact_real_m5_segment():
    candles = _market_rows()
    start, end = 23, 34
    target = candles[start:end]
    signature = _market_segment_signature(target)
    # Simulate small vision-ratio noise without altering the side sequence.
    visual = []
    for i, item in enumerate(signature):
        drift = 0.006 if i % 2 == 0 else -0.004
        visual.append({
            "side": item["side"],
            "high_ratio": max(0.0, min(1.0, item["high_ratio"] + drift)),
            "low_ratio": max(0.0, min(1.0, item["low_ratio"] + drift)),
        })
    geometry = {
        "current_price": target[-1]["close"],
        "visible_candle_count": len(target),
        "last_visible_time_label": "19:50",
        "visible_candles": visual,
    }
    match = _match_visual_market_segment(geometry, candles)
    assert match["matched"] is True
    assert match["start_index"] == start
    assert match["end_index"] == end - 1
    assert match["segment"][-1]["time"] == target[-1]["time"]
    assert match["confidence"] >= 60


def test_v74_visual_fingerprint_fails_closed_when_shape_is_unrelated():
    candles = _market_rows()
    geometry = {
        "current_price": candles[-1]["close"] + 20.0,
        "visible_candle_count": 10,
        "last_visible_time_label": "",
        "visible_candles": [
            {"side": "bull" if i % 2 == 0 else "bear", "high_ratio": 0.02, "low_ratio": 0.98}
            for i in range(10)
        ],
    }
    match = _match_visual_market_segment(geometry, candles)
    assert match["matched"] is False
    assert match["reason"] in {"visual_shape_match_below_gate", "no_candidate"}


def test_v74_reconstructed_window_uses_matched_visible_count_not_forced_28():
    candles = _market_rows(36)
    analysis = {
        "candles": candles,
        "render_candles": candles[-12:],
        "render_visible_candle_count": 12,
    }
    window, offset = renderer._reconstructed_window(analysis)
    assert len(window) == 12
    assert window[0]["time"] == candles[-12]["time"]
    assert offset == 0  # render_candles is already the selected display window


def test_v74_pattern_plan_reuses_existing_tp2_tp3_without_fabricating_prices():
    analysis = {
        "draw_mode": "watch",
        "action_summary": {"primary_side": "wait", "is_confirmed": False},
        "target_1": 4395.0,
        "target_2": 4398.0,
        "target_3": 4401.0,
        "pattern_overlays": [{
            "bias": "صاعد",
            "status": "candidate",
            "geometry": {"trigger": 4390.0, "stop": 4386.0, "target": 4393.0},
        }],
    }
    plan = renderer._resolve_reference_trade_plan(analysis)
    assert plan is not None
    assert plan["source"] == "pattern"
    assert plan["entry"] == 4390.0
    assert plan["targets"] == [4393.0, 4395.0, 4398.0]


def test_v74_order_block_visual_band_is_real_opposite_candle_body():
    candles = [
        {"open": 10.0, "high": 10.3, "low": 9.7, "close": 10.2},
        # Opposite bearish candle with long wicks.
        {"open": 10.25, "high": 11.2, "low": 9.1, "close": 9.95},
        # Strong bullish impulse.
        {"open": 9.96, "high": 12.3, "low": 9.9, "close": 12.0},
        {"open": 12.0, "high": 12.4, "low": 11.8, "close": 12.2},
        {"open": 12.2, "high": 12.5, "low": 12.0, "close": 12.3},
    ]
    blocks = _order_blocks(candles)
    block = next(item for item in blocks if item["index"] == 1)
    assert block["low"] == 9.1 and block["high"] == 11.2  # audit keeps full candle
    assert block["zone_low"] == 9.95
    assert block["zone_high"] == 10.25
    assert block["validation_reason"] == "last_opposite_candle_body_before_real_impulse"
