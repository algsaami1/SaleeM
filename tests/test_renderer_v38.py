from datetime import datetime, timedelta, timezone

from PIL import Image

from app.engine.renderer import _axis_values, _price_range, render_result


def _candles(start=4142.0, count=30):
    base_time = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    result = []
    price = start
    for index in range(count):
        drift = 0.34 if index < 18 else (-0.10 if index < 25 else 0.08)
        open_ = price
        close = price + drift
        result.append(
            {
                "time": (base_time + timedelta(minutes=index * 5)).isoformat(),
                "open": round(open_, 2),
                "high": round(max(open_, close) + 0.38, 2),
                "low": round(min(open_, close) - 0.34, 2),
                "close": round(close, 2),
            }
        )
        price = close
    return result


def _analysis(direction="صاعد"):
    candles = _candles()
    current = candles[-1]["close"]
    if direction == "صاعد":
        entry = current + 0.55
        stop = entry - 2.0
        targets = [entry + 2.1, entry + 4.0, entry + 6.3]
    else:
        entry = current - 0.55
        stop = entry + 2.0
        targets = [entry - 2.1, entry - 4.0, entry - 6.3]
    return {
        "candles": candles,
        "current_price": current,
        "image_price_high": current + 125.0,
        "image_price_low": current - 125.0,
        "draw_mode": "confirmed",
        "direction": direction,
        "analysis_direction": direction,
        "buy_probability": 82 if direction == "صاعد" else 18,
        "sell_probability": 18 if direction == "صاعد" else 82,
        "trade_probability": 82,
        "entry": entry,
        "stop_loss": stop,
        "target_1": targets[0],
        "target_2": targets[1],
        "target_3": targets[2],
        "support_levels": [
            {"price": current - 1.4, "strength": 78, "touches": 3},
            {"price": current - 3.1, "strength": 69, "touches": 2},
        ],
        "resistance_levels": [
            {"price": current + 1.2, "strength": 81, "touches": 4},
            {"price": current + 3.2, "strength": 72, "touches": 3},
        ],
        "pattern_type": "كسر وإعادة اختبار",
        "pattern_confidence": 74,
        "confirmation": "إغلاق واضح ثم إعادة اختبار ناجحة",
        "scenario": "استمرار الحركة بعد ثبات مستوى الدخول",
        "market_timezone": "Asia/Muscat",
        "market_m5_latest_candle_time": candles[-1]["time"],
    }


def test_extreme_image_bounds_do_not_compress_analysis_zone():
    analysis = _analysis("صاعد")
    low, high = _price_range(analysis)
    assert high - low < 45.0
    assert low < analysis["stop_loss"] < high
    assert low < analysis["target_3"] < high


def test_target_side_gets_more_room_for_each_direction():
    bullish = _analysis("صاعد")
    low, high = _price_range(bullish)
    assert high - bullish["entry"] > bullish["entry"] - low

    bearish = _analysis("هابط")
    low, high = _price_range(bearish)
    assert bearish["entry"] - low > high - bearish["entry"]


def test_axis_uses_readable_dynamic_steps():
    values = _axis_values(4137.2, 4169.8)
    assert 5 <= len(values) <= 12
    steps = [round(values[index + 1] - values[index], 6) for index in range(len(values) - 1)]
    assert len(set(steps)) == 1


def test_renderer_produces_phone_png(tmp_path):
    output = tmp_path / "preview.png"
    output.write_bytes(render_result(_analysis("صاعد")))
    with Image.open(output) as image:
        assert image.size == (1080, 1920)
        assert image.format == "PNG"



def test_renderer_accepts_chart_background(tmp_path):
    background = tmp_path / "chart.png"
    Image.new("RGB", (960, 1600), (4, 4, 4)).save(background)
    output = tmp_path / "preview_bg.png"
    output.write_bytes(render_result(_analysis("صاعد"), chart_background_path=background))
    with Image.open(output) as image:
        assert image.size == (1080, 1920)
        assert image.format == "PNG"
