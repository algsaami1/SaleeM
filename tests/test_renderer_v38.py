from datetime import datetime, timedelta, timezone

from PIL import Image

from app.engine.renderer import (
    CHART,
    CHART_CARD,
    NOTES,
    _anchored_price_range,
    _axis_values,
    _detect_green_reference_line_y,
    _price_range,
    _price_y,
    render_result,
)


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


def test_result_chart_fills_page_until_bottom_notes_box():
    assert CHART_CARD[1] <= 24
    assert CHART[1] <= 80
    assert CHART[3] - CHART[1] >= 1200
    assert CHART_CARD[3] < NOTES[1]
    assert NOTES[3] >= 1880


def test_detect_green_reference_line_row():
    background = Image.new("RGBA", (872, 1208), (7, 14, 28, 255))
    # بعض الأشكال الرأسية الخضراء حتى نتأكد أن الكاشف يفضّل الخط الأفقي الطويل.
    for x in range(120, 150):
        for y in range(280, 500):
            background.putpixel((x, y), (17, 183, 94, 255))
    target_y = 644
    for x in range(24, 848):
        background.putpixel((x, target_y), (38, 201, 128, 255))
        background.putpixel((x, target_y + 1), (38, 201, 128, 210))

    detected = _detect_green_reference_line_y(background)
    assert detected is not None
    assert abs(detected - target_y) <= 2


def test_renderer_syncs_current_price_overlay_to_detected_green_line(tmp_path):
    background = tmp_path / "chart_with_green_line.png"
    width, height = 872, 1208
    line_y = 730
    bg = Image.new("RGBA", (width, height), (7, 14, 28, 255))
    for x in range(18, width - 18):
        bg.putpixel((x, line_y), (38, 201, 128, 255))
    bg.save(background)

    analysis = _analysis("صاعد")
    # نجعل السعر الحالي بعيدًا عن موضع الخط حتى يثبت أن المزامنة تعتمد الاكتشاف.
    analysis["current_price"] = analysis["current_price"] + 4.8

    output = tmp_path / "preview_sync.png"
    output.write_bytes(render_result(analysis, chart_background_path=background))
    with Image.open(output) as image:
        sample = image.getpixel((150, 72 + line_y))
        assert sample[1] > sample[0]
        assert sample[1] >= sample[2] - 20


def test_all_price_drawings_share_green_line_anchored_transform():
    analysis = _analysis("صاعد")
    original_min, original_max = _price_range(analysis)
    reference_y = CHART[1] + int((CHART[3] - CHART[1]) * 0.72)

    anchored_min, anchored_max = _anchored_price_range(
        analysis,
        original_min,
        original_max,
        reference_y,
    )

    current_y = _price_y(analysis["current_price"], anchored_min, anchored_max)
    assert abs(current_y - reference_y) <= 1

    # الدعم والمقاومة والدخول والوقف والأهداف كلها تستخدم نفس المحول، لذلك
    # تبقى المسافة الرأسية بينها وبين الخط الأخضر متناسبة مع فرق السعر.
    values = [
        analysis["support_levels"][0]["price"],
        analysis["resistance_levels"][0]["price"],
        analysis["entry"],
        analysis["stop_loss"],
        analysis["target_1"],
        analysis["target_3"],
    ]
    ys = [_price_y(value, anchored_min, anchored_max) for value in values]
    assert all(CHART[1] <= y <= CHART[3] for y in ys)
    assert ys[0] > current_y  # الدعم أسفل السعر الحالي
    assert ys[1] < current_y  # المقاومة أعلى السعر الحالي


def test_close_top_price_from_input_controls_axis_spacing():
    analysis = _analysis("هابط")
    analysis["image_price_high"] = round(analysis["current_price"] + 0.8, 2)
    low, high = _price_range(analysis)
    span = high - low
    top_gap_ratio = (high - analysis["current_price"]) / span
    assert top_gap_ratio >= 0.08


def test_trade_can_be_partially_hidden_if_outside_axis_range(tmp_path):
    analysis = _analysis("هابط")
    analysis["image_price_high"] = round(analysis["current_price"] + 0.65, 2)
    analysis["target_1"] = analysis["entry"] - 2.5
    analysis["target_2"] = analysis["entry"] - 5.5
    analysis["target_3"] = analysis["entry"] - 9.0
    output = tmp_path / "partial_trade_hidden.png"
    output.write_bytes(render_result(analysis))
    with Image.open(output) as image:
        assert image.size == (1080, 1920)
        assert image.format == "PNG"
