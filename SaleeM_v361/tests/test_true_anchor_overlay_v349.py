from __future__ import annotations

from PIL import Image, ImageDraw

from app.engine.renderer import _native_build_candle_x_map, _native_structure_events


def _row(close: float, i: int) -> dict[str, float | str]:
    open_ = close - 0.12 if i % 2 == 0 else close + 0.12
    return {
        "time": f"2026-08-07T20:{i:02d}:00",
        "open": open_,
        "high": max(open_, close) + 0.24,
        "low": min(open_, close) - 0.24,
        "close": close,
    }


def test_candle_x_alignment_uses_wick_prices_and_can_find_feed_lag():
    closes = [100.0, 100.8, 101.6, 100.9, 99.8, 100.5, 102.1, 101.0, 100.2, 101.4, 103.0, 102.0, 101.7, 102.6]
    candles = [_row(value, i) for i, value in enumerate(closes)]
    current_price = 101.0
    current_y = 190.0
    pixels_per_price = 26.0
    image = Image.new("RGBA", (760, 380), (250, 251, 252, 255))
    draw = ImageDraw.Draw(image)
    centers = [80 + i * 55 for i in range(10)]

    # The screenshot deliberately ends two market candles before the live feed:
    # visible market indices are 2..11, while the feed contains 0..13.
    for x, candle in zip(centers, candles[2:12]):
        color = (22, 166, 129, 255) if float(candle["close"]) > float(candle["open"]) else (232, 66, 66, 255)
        y_high = round(current_y - (float(candle["high"]) - current_price) * pixels_per_price)
        y_low = round(current_y - (float(candle["low"]) - current_price) * pixels_per_price)
        y_open = round(current_y - (float(candle["open"]) - current_price) * pixels_per_price)
        y_close = round(current_y - (float(candle["close"]) - current_price) * pixels_per_price)
        draw.line((x, y_high, x, y_low), fill=color, width=2)
        draw.rectangle((x - 5, min(y_open, y_close), x + 5, max(y_open, y_close)), fill=color)

    analysis = {
        "candles": candles,
        "_native_axis_pixel_model": {
            "mode": "pixel_current_grid",
            "current_price": current_price,
            "current_y": current_y,
            "pixels_per_price": pixels_per_price,
            "height": image.height,
        },
    }
    x_map = _native_build_candle_x_map(image, analysis, centers)
    assert x_map[2] == centers[0]
    assert x_map[11] == centers[-1]
    assert 12 not in x_map
    assert analysis["native_candle_alignment_mode"] == "wick_price_match"


def test_structure_events_require_real_swing_break_and_idm_is_internal_swing():
    closes = [100.0, 101.0, 102.0, 101.0, 100.4, 101.5, 103.0, 102.0, 100.8, 102.2, 104.0, 103.4, 103.8]
    candles = [_row(value, i) for i, value in enumerate(closes)]
    analysis = {"direction": "صاعد", "analysis_direction": "صاعد"}
    events = _native_structure_events(analysis, candles)
    bos = next(item for item in events if item["label"] == "BOS")
    assert bos["break_index"] > bos["swing_index"]
    assert float(candles[bos["break_index"]]["close"]) > float(bos["price"])
    idm = next((item for item in events if item["label"] == "IDM"), None)
    if idm is not None:
        assert bos["swing_index"] < idm["swing_index"] < bos["break_index"]
