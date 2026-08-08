from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw

import app.engine.renderer as renderer

from app.engine.renderer import (
    AXIS_VISUAL_TEXT,
    AXIS_PRICE_CARD_HEIGHT,
    AXIS_PRICE_CARD_WIDTH,
    CHART,
    CHART_CARD,
    NOTES,
    TOP_SUMMARY_PANEL,
    BOTTOM_SUMMARY_PANEL,
    BOTTOM_CARDS_Y1,
    BOTTOM_CARDS_Y2,
    _analysis_current_reference_y,
    _anchored_price_range,
    _axis_checked_current_reference_y,
    _axis_values,
    _detect_green_reference_line_y,
    _dynamic_image_axis_range,
    _estimate_visible_candle_count,
    _fit_cover,
    _detect_top_trade_controls_band,
    _hide_top_trade_controls,
    _remove_top_trade_controls_by_crop,
    prepare_chart_viewport_image,
    _header_pattern_lines,
    _close_label,
    _horizontal_card_lanes,
    _resolve_axis_card_centers,
    _draw_trade_axis_card,
    _draw_left_level_card,
    _level_strength_text,
    _level_display_items,
    _fmt_card_price,
    _draw_market_zones,
    _draw_scenario_arrows,
    _scenario_arrow_origin,
    _draw_trade_risk_reward_zones,
    _trade_display_items,
    _extreme_display_items,
    _exact_image_axis_model,
    _price_range,
    _price_y,
    _projection_closes,
    _right_axis_labels,
    _select_visual_axis_labels,
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
        "most_probable_peak": {"price": targets[-1] + 1.1},
        "most_probable_trough": {"price": (current - 5.2) if direction == "صاعد" else targets[-1] - 1.1},
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
        assert image.size == (2200, 1050)
        assert image.format == "PNG"



def test_renderer_accepts_chart_background(tmp_path):
    background = tmp_path / "chart.png"
    Image.new("RGB", (960, 1600), (4, 4, 4)).save(background)
    output = tmp_path / "preview_bg.png"
    output.write_bytes(render_result(_analysis("صاعد"), chart_background_path=background))
    with Image.open(output) as image:
        assert image.size == (960, 1600)
        assert image.format == "PNG"


def test_result_preserves_full_iphone_canvas_and_native_viewport():
    assert CHART_CARD == (0, 320, 1320, 2563)
    assert CHART[1] == 320
    assert CHART[3] - CHART[1] == 2243
    assert CHART_CARD[2] == 1320




def test_native_iphone_crop_keeps_canonical_viewport():
    source = Image.new("RGBA", (1320, 2868), (0, 0, 0, 255))
    for x in range(209, 1320):
        for y in range(312, 2555):
            source.putpixel((x, y), (44, 55, 66, 255))
    visible = _fit_cover(source, (1111, 2243))
    assert visible.size == (1111, 2243)
    assert visible.getpixel((0, 0)) == (44, 55, 66, 255)
    assert visible.getpixel((1110, 2242)) == (44, 55, 66, 255)


def test_ratio_crop_normalizes_full_screenshot_from_other_iphone_size():
    source = Image.new("RGBA", (1179, 2556), (0, 0, 0, 255))
    crop_w = round(1179 * (1111 / 1320))
    crop_h = round(2556 * (2243 / 2868))
    crop_left = 1179 - crop_w
    crop_top = (2556 - crop_h) // 2

    for x in range(crop_left, 1179):
        for y in range(crop_top, crop_top + crop_h):
            source.putpixel((x, y), (90, 120, 150, 255))

    visible = _fit_cover(source, (1111, 2243))
    assert visible.size == (1111, 2243)
    assert visible.getpixel((0, 0)) == (90, 120, 150, 255)
    assert visible.getpixel((1110, 2242)) == (90, 120, 150, 255)



def test_already_cropped_viewport_is_preserved_proportionally():
    source = Image.new("RGBA", (992, 2004), (33, 66, 99, 255))
    visible = _fit_cover(source, (1111, 2243))
    assert visible.size == (1111, 2243)
    assert visible.getpixel((0, 0)) == (33, 66, 99, 255)
    assert visible.getpixel((1110, 2242)) == (33, 66, 99, 255)


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




def test_detector_rejects_wide_green_zone_and_uses_thin_price_line():
    width, height = 872, 1208
    background = Image.new("RGBA", (width, height), (7, 14, 28, 255))

    # Broad target area: visually green, but it must never become the current
    # price anchor because it is many pixels thick.
    for y in range(260, 330):
        for x in range(40, width - 160):
            background.putpixel((x, y), (25, 211, 112, 180))

    target_y = 812
    for x in range(18, width - 12):
        background.putpixel((x, target_y), (38, 201, 128, 255))
        background.putpixel((x, target_y + 1), (38, 201, 128, 225))

    detected = _detect_green_reference_line_y(background)
    assert detected is not None
    assert abs(detected - target_y) <= 2


def test_model_current_line_ratio_is_used_as_pixel_detection_fallback():
    analysis = _analysis("صاعد")
    analysis["current_price_y_ratio"] = 0.63
    expected = CHART[1] + round((CHART[3] - CHART[1]) * 0.63)
    detected = _analysis_current_reference_y(analysis)
    assert detected is not None
    assert abs(detected - expected) <= 1


def test_image_axis_uses_exact_label_positions_when_available():
    analysis = _analysis("صاعد")
    current = analysis["current_price"]
    analysis["image_axis_labels"] = [
        {"price": current + 8.0, "y_ratio": 0.06},
        {"price": current + 6.0, "y_ratio": 0.18},
        {"price": current + 4.0, "y_ratio": 0.31},
        {"price": current + 2.0, "y_ratio": 0.44},
        {"price": current + 0.0, "y_ratio": 0.57},
        {"price": current - 2.0, "y_ratio": 0.70},
    ]
    reference_y = CHART[1] + int((CHART[3] - CHART[1]) * 0.52)
    dynamic = _dynamic_image_axis_range(analysis, reference_y)
    assert dynamic is not None
    low, high = dynamic

    # The internal scale still uses the preferred inner anchors.
    top_y = _price_y(current + 6.0, low, high)
    second_y = _price_y(current + 4.0, low, high)
    expected_step_px = round((CHART[3] - CHART[1]) * 0.13)
    assert abs((second_y - top_y) - expected_step_px) <= 3

    labels = _right_axis_labels(analysis, low, high)
    assert [price for _role, price, _y in labels] == [
        current + 8.0,
        current + 6.0,
        current + 4.0,
        current + 2.0,
        current,
        current - 2.0,
    ]
    # The detected current line is the offset anchor, so every axis label must
    # be projected by the exact same transform used by the chart drawings.
    expected_y = [_price_y(price, low, high) for price in (
        current + 8.0,
        current + 6.0,
        current + 4.0,
        current + 2.0,
        current,
        current - 2.0,
    )]
    assert [y for _role, _price, y in labels] == expected_y
    assert abs(_price_y(current, low, high) - reference_y) <= 1



def test_sparse_visual_axis_keeps_exactly_five_evenly_distributed_labels():
    labels = [
        ("axis", 4100.0 - index, CHART[1] + index * 100)
        for index in range(12)
    ]
    selected = _select_visual_axis_labels(labels)
    assert len(selected) == 5
    assert selected[0] == labels[0]
    assert selected[-1] == labels[-1]
    assert [item[2] for item in selected] == sorted(item[2] for item in selected)


def test_sparse_visual_axis_does_not_change_full_calibration_labels():
    analysis = _analysis("صاعد")
    current = analysis["current_price"]
    analysis["image_axis_labels"] = [
        {"price": current + 10.0 - index * 2.0, "y_ratio": 0.05 + index * 0.09}
        for index in range(10)
    ]
    dynamic = _dynamic_image_axis_range(analysis)
    assert dynamic is not None
    low, high = dynamic
    full = _right_axis_labels(analysis, low, high)
    visible = _select_visual_axis_labels(full)
    assert len(full) >= 6
    assert len(visible) == 5
    # Visual filtering must not mutate or replace the labels used by price math.
    assert _right_axis_labels(analysis, low, high) == full


def test_right_axis_visual_text_is_pure_black_and_full_labels_remain_available():
    assert AXIS_VISUAL_TEXT == (0, 0, 0, 255)
    analysis = _analysis("صاعد")
    current = analysis["current_price"]
    analysis["image_axis_labels"] = [
        {"price": current + 10.0 - index * 2.0, "y_ratio": 0.05 + index * 0.09}
        for index in range(10)
    ]
    dynamic = _dynamic_image_axis_range(analysis)
    assert dynamic is not None
    labels = _right_axis_labels(analysis, dynamic[0], dynamic[1])
    assert len(labels) >= 6

def test_image_axis_rejects_inconsistent_inner_anchor_sequence():
    analysis = _analysis("صاعد")
    current = analysis["current_price"]
    analysis["image_axis_labels"] = [
        {"price": current + 10.0, "y_ratio": 0.08},
        {"price": current + 8.0, "y_ratio": 0.20},
        {"price": current + 4.0, "y_ratio": 0.34},
        {"price": current + 1.0, "y_ratio": 0.50},
        {"price": current - 2.0, "y_ratio": 0.66},
    ]
    assert _dynamic_image_axis_range(analysis) is None


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
        assert image.size == (2200, 1050)
        assert image.format == "PNG"


def test_estimate_visible_candle_count_recognizes_more_than_ten_candles():
    width, height = 872, 1208
    background = Image.new("RGBA", (width, height), (240, 240, 240, 255))
    start_x = 30
    step = 34
    for index in range(12):
        x = start_x + index * step
        color = (48, 166, 154, 255) if index % 2 == 0 else (224, 92, 84, 255)
        for y in range(320, 520):
            background.putpixel((x, y), color)
            background.putpixel((x + 1, y), color)
            background.putpixel((x + 2, y), color)
        for y in range(280, 580):
            background.putpixel((x + 1, y), color)

    estimated = _estimate_visible_candle_count(background)
    assert estimated is not None
    assert estimated >= 11


def test_axis_checked_current_reference_y_uses_shared_axis_transform():
    analysis = _analysis("صاعد")
    price_min, price_max = _price_range(analysis)
    calculated_y = _price_y(analysis["current_price"], price_min, price_max)
    detected_y = calculated_y + 140

    chosen = _axis_checked_current_reference_y(analysis, price_min, price_max, detected_y)
    assert chosen == calculated_y


def test_exact_axis_mode_filters_one_bad_ocr_label_and_keeps_source_positions():
    analysis = _analysis("صاعد")
    current = analysis["current_price"]
    analysis["image_axis_labels"] = [
        {"price": current + 8.0, "y_ratio": 0.08},
        {"price": current + 6.0, "y_ratio": 0.20},
        {"price": current + 4.0, "y_ratio": 0.32},
        {"price": current + 9.73, "y_ratio": 0.44},  # bad OCR reading
        {"price": current + 0.0, "y_ratio": 0.56},
        {"price": current - 2.0, "y_ratio": 0.68},
        {"price": current - 4.0, "y_ratio": 0.80},
    ]
    model = _exact_image_axis_model(analysis)
    assert model is not None
    assert model["mode"] == "exact"
    assert model["inlier_count"] >= 6
    assert model["source_count"] == 7
    assert analysis["axis_calibration_mode"] == "exact"
    assert analysis["axis_calibration_confidence"] >= 70
    kept_prices = [round(price, 2) for price, _ratio in model["points"]]
    assert round(current + 9.73, 2) not in kept_prices


def test_exact_axis_range_maps_clean_source_labels_near_their_original_y():
    analysis = _analysis("صاعد")
    current = analysis["current_price"]
    ratios = (0.10, 0.22, 0.34, 0.46, 0.58, 0.70)
    prices = [current + 6, current + 4, current + 2, current, current - 2, current - 4]
    analysis["image_axis_labels"] = [
        {"price": price, "y_ratio": ratio}
        for price, ratio in zip(prices, ratios)
    ]
    dynamic = _dynamic_image_axis_range(analysis)
    assert dynamic is not None
    low, high = dynamic
    chart_height = CHART[3] - CHART[1]
    for price, ratio in zip(prices, ratios):
        fitted_y = _price_y(price, low, high)
        source_y = CHART[1] + round(chart_height * ratio)
        assert abs(fitted_y - source_y) <= 2


def test_top_buy_sell_and_lot_toolbar_is_hidden_as_one_band():
    image = Image.new("RGBA", (1111, 2243), (245, 245, 245, 255))
    # Simulate blue BUY/SELL boxes separated by a white lot field.
    for y in range(18, 118):
        for x in range(0, 250):
            image.putpixel((x, y), (55, 118, 235, 255))
        for x in range(600, 1111):
            image.putpixel((x, y), (55, 118, 235, 255))
    band = _detect_top_trade_controls_band(image)
    assert band is not None
    cleaned = _hide_top_trade_controls(image)
    top, bottom = band
    assert cleaned.getpixel((100, (top + bottom) // 2))[:3] == (3, 17, 35)
    assert cleaned.getpixel((450, (top + bottom) // 2))[:3] == (3, 17, 35)
    assert cleaned.getpixel((900, (top + bottom) // 2))[:3] == (3, 17, 35)
    # Chart body below the toolbar remains untouched.
    assert cleaned.getpixel((450, 180))[:3] == (245, 245, 245)


def test_neutral_white_trade_toolbar_is_cropped_not_painted():
    image = Image.new("RGBA", (1111, 2243), (248, 248, 248, 255))
    draw = ImageDraw.Draw(image)
    # A white/gray one-click trading row with internal separators and text-like blocks.
    draw.rectangle((0, 0, 1110, 142), fill=(220, 220, 220, 255))
    draw.rectangle((0, 0, 160, 142), fill=(185, 185, 185, 255))
    draw.rectangle((600, 0, 1110, 142), fill=(205, 205, 205, 255))
    draw.line((0, 142, 1110, 142), fill=(90, 90, 90, 255), width=3)
    # Chart body starts below the toolbar and includes a unique marker.
    draw.rectangle((0, 143, 1110, 2242), fill=(250, 250, 250, 255))
    draw.rectangle((900, 220, 920, 400), fill=(30, 170, 120, 255))

    band = _detect_top_trade_controls_band(image)
    assert band is not None
    cleaned, removed = _remove_top_trade_controls_by_crop(image)
    assert removed is not None
    assert cleaned.size == image.size
    # The gray toolbar no longer occupies the top after a geometry-preserving crop.
    assert cleaned.getpixel((400, 5))[:3] != (220, 220, 220)


def test_plain_chart_top_is_not_mistaken_for_trade_toolbar():
    image = Image.new("RGBA", (1111, 2243), (4, 8, 15, 255))
    draw = ImageDraw.Draw(image)
    for y in range(90, 2200, 120):
        draw.line((0, y, 930, y), fill=(25, 35, 49, 255), width=1)
    for x in range(90, 930, 120):
        draw.line((x, 0, x, 2242), fill=(25, 35, 49, 255), width=1)
    cleaned, removed = _remove_top_trade_controls_by_crop(image)
    assert removed is None
    assert cleaned.tobytes() == image.tobytes()


def test_header_pattern_uses_two_lines_for_long_break_retest_name():
    assert _header_pattern_lines("كسر وإعادة اختبار") == ["كسر", "إعادة اختبار"]


def test_watch_mode_exposes_entry_only_without_cancel():
    analysis = _analysis("صاعد")
    analysis["draw_mode"] = "watch"
    mode, items = _trade_display_items(analysis, analysis["current_price"] - 20, analysis["current_price"] + 20)
    assert mode == "watch"
    assert [item[0] for item in items] == ["Entry"]


def test_conditional_mode_keeps_entry_cancel_and_three_targets():
    analysis = _analysis("صاعد")
    analysis["draw_mode"] = "conditional"
    mode, items = _trade_display_items(analysis, analysis["current_price"] - 20, analysis["current_price"] + 20)
    assert mode == "conditional"
    assert [item[0] for item in items] == ["Entry", "Cancel", "TP1", "TP2", "TP3"]


def test_inactive_market_has_no_execution_cards():
    analysis = _analysis("صاعد")
    analysis["draw_mode"] = "inactive"
    mode, items = _trade_display_items(analysis, analysis["current_price"] - 20, analysis["current_price"] + 20)
    assert mode == "inactive"
    assert items == []


def test_overlapping_cards_are_separated_vertically_without_changing_true_y():
    items = [
        ("Entry", 4058.0, 1000, (38, 117, 247, 255)),
        ("TP1", 4058.2, 1020, (25, 211, 112, 255)),
        ("Stop", 4057.8, 1040, (245, 63, 70, 255)),
    ]
    true_ys = [item[2] for item in items]
    centers = _resolve_axis_card_centers(
        items, card_height=AXIS_PRICE_CARD_HEIGHT, vertical_gap=6
    )
    ordered = [centers[index] for index in range(len(items))]
    assert ordered[1] - ordered[0] >= AXIS_PRICE_CARD_HEIGHT + 6
    assert ordered[2] - ordered[1] >= AXIS_PRICE_CARD_HEIGHT + 6
    assert [item[2] for item in items] == true_ys


def test_horizontal_card_lanes_compatibility_alias_returns_display_centers():
    items = [
        ("R1 92%", 4058.0, 1000, (102, 22, 31, 245)),
        ("Entry", 4058.1, 1010, (38, 117, 247, 255)),
    ]
    centers = _horizontal_card_lanes(items)
    assert centers[1] - centers[0] >= AXIS_PRICE_CARD_HEIGHT + 6


def test_trade_axis_card_center_matches_exact_price_y_when_not_displaced():
    canvas = Image.new("RGBA", (1320, 2868), (0, 0, 0, 255))
    draw = ImageDraw.Draw(canvas)
    exact_y = 1234
    rect = _draw_trade_axis_card(
        draw,
        label="Entry",
        price=4058.0,
        exact_y=exact_y,
        color=(38, 117, 247, 255),
    )
    assert (rect[1] + rect[3]) // 2 == exact_y
    assert rect[2] - rect[0] == AXIS_PRICE_CARD_WIDTH
    assert rect[3] - rect[1] == AXIS_PRICE_CARD_HEIGHT


def test_trade_axis_card_can_move_vertically_but_stays_in_same_axis_lane():
    canvas = Image.new("RGBA", (1320, 2868), (0, 0, 0, 255))
    draw = ImageDraw.Draw(canvas)
    first = _draw_trade_axis_card(
        draw,
        label="Entry",
        price=4058.0,
        exact_y=1200,
        card_y=1160,
        color=(38, 117, 247, 255),
    )
    second = _draw_trade_axis_card(
        draw,
        label="TP1",
        price=4059.0,
        exact_y=1220,
        card_y=1240,
        color=(25, 211, 112, 255),
    )
    assert first[0] == second[0]
    assert first[2] == second[2]
    assert (first[1] + first[3]) // 2 == 1160
    assert (second[1] + second[3]) // 2 == 1240


def test_support_resistance_items_use_unified_axis_card_shape_and_true_y():
    analysis = _analysis("صاعد")
    current = analysis["current_price"]
    analysis["resistance_levels"] = [
        {"price": current + 0.18, "strength": 92},
        {"price": current + 0.27, "strength": 84},
    ]
    analysis["support_levels"] = [
        {"price": current - 0.16, "strength": 91},
        {"price": current - 0.25, "strength": 80},
    ]
    low, high = current - 2.0, current + 2.0
    items = _level_display_items(analysis, low, high)
    assert [item[0] for item in items] == ["R1 92%", "R2 84%", "S1 91%", "S2 80%"]
    expected_prices = [
        analysis["resistance_levels"][0]["price"],
        analysis["resistance_levels"][1]["price"],
        analysis["support_levels"][0]["price"],
        analysis["support_levels"][1]["price"],
    ]
    for item, price in zip(items, expected_prices):
        assert item[2] == _price_y(price, low, high)


def test_card_price_uses_one_decimal_place():
    assert _fmt_card_price(4052) == "4052.0"
    assert _fmt_card_price(4052.37) == "4052.4"


def test_left_level_card_uses_same_size_as_axis_cards():
    canvas = Image.new("RGBA", (1320, 2868), (0, 0, 0, 255))
    draw = ImageDraw.Draw(canvas)
    rect = _draw_left_level_card(
        draw,
        label="R1 92%",
        price=4053.47,
        exact_y=1200,
        color=(102, 22, 31, 245),
    )
    assert rect[0] == CHART[0] + 14
    assert rect[2] - rect[0] == AXIS_PRICE_CARD_WIDTH
    assert rect[3] - rect[1] == AXIS_PRICE_CARD_HEIGHT
    assert (rect[1] + rect[3]) // 2 == 1200


def test_level_percentage_is_adjacent_to_one_decimal_price():
    name, value = _level_strength_text("S1 91%", 4052.37)
    assert name == "S1"
    assert value == "4052.4 91%"


def test_current_price_binding_uses_shared_transform_even_without_detected_line():
    analysis = _analysis("صاعد")
    low, high = _price_range(analysis)
    expected = _price_y(analysis["current_price"], low, high)
    chosen = _axis_checked_current_reference_y(analysis, low, high, detected_y=None)
    assert chosen == expected


def test_projection_candles_reach_each_target_in_two_steps():
    closes = _projection_closes(4050.0, [4051.0, 4052.0, 4053.0])
    assert len(closes) == 6
    assert closes[1] == 4051.0
    assert closes[3] == 4052.0
    assert closes[5] == 4053.0


def test_trade_card_labels_do_not_use_trigger_or_active():
    for mode in ("watch", "conditional", "confirmed"):
        analysis = _analysis("صاعد")
        analysis["draw_mode"] = mode
        _, items = _trade_display_items(analysis, analysis["current_price"] - 20, analysis["current_price"] + 20)
        labels = {item[0] for item in items}
        assert "Trigger" not in labels
        assert "Active" not in labels


def test_summary_panels_are_fixed_outside_chart_area():
    assert TOP_SUMMARY_PANEL[3] < CHART_CARD[1]
    assert BOTTOM_SUMMARY_PANEL[1] > CHART_CARD[3]
    assert BOTTOM_CARDS_Y1 > CHART_CARD[3]
    assert BOTTOM_CARDS_Y2 < BOTTOM_SUMMARY_PANEL[3]
    assert CHART_CARD == (0, 320, 1320, 2563)


def test_close_card_uses_entry_level_and_direction():
    bullish = _analysis("صاعد")
    bullish["draw_mode"] = "conditional"
    value, _color = _close_label(bullish)
    assert value == f"فوق {_fmt_card_price(bullish['entry'])}"

    bearish = _analysis("هابط")
    bearish["draw_mode"] = "conditional"
    value, _color = _close_label(bearish)
    assert value == f"تحت {_fmt_card_price(bearish['entry'])}"


def test_watch_close_card_waits_instead_of_inventing_level():
    analysis = _analysis("صاعد")
    analysis["draw_mode"] = "watch"
    value, _color = _close_label(analysis)
    assert value == "بانتظار"


def test_watch_mode_draws_market_zones_when_real_fvg_and_ob_exist():
    candles = [
        {"open": 101.0, "high": 101.2, "low": 99.8, "close": 100.0},
        {"open": 100.0, "high": 103.4, "low": 99.9, "close": 103.0},
        {"open": 103.0, "high": 104.2, "low": 102.0, "close": 104.0},
        {"open": 104.0, "high": 104.3, "low": 103.2, "close": 103.5},
        {"open": 103.5, "high": 105.2, "low": 103.4, "close": 105.0},
    ]
    analysis = {
        "draw_mode": "watch",
        "direction": "صاعد",
        "analysis_direction": "صاعد",
        "entry": 103.0,
    }
    canvas = Image.new("RGBA", (1320, 2868), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    _draw_market_zones(
        canvas,
        draw,
        analysis,
        candles,
        slot=40,
        candle_right=650,
        price_min=98.0,
        price_max=106.0,
    )
    assert canvas.getbbox() is not None


def test_pending_conditional_hides_risk_reward_until_entry_activation():
    conditional = _analysis("صاعد")
    conditional["draw_mode"] = "conditional"
    conditional["show_targets_as_active"] = False
    low, high = _price_range(conditional)
    canvas = Image.new("RGBA", (1320, 2868), (0, 0, 0, 0))
    _draw_trade_risk_reward_zones(canvas, conditional, low, high, candle_right=632)
    assert canvas.getbbox() is None

    conditional["show_targets_as_active"] = True
    active = Image.new("RGBA", (1320, 2868), (0, 0, 0, 0))
    _draw_trade_risk_reward_zones(active, conditional, low, high, candle_right=632)
    assert active.getbbox() is not None

    watch = _analysis("صاعد")
    watch["draw_mode"] = "watch"
    neutral = Image.new("RGBA", (1320, 2868), (0, 0, 0, 0))
    _draw_trade_risk_reward_zones(neutral, watch, low, high, candle_right=632)
    assert neutral.getbbox() is not None


def test_pending_conditional_hides_directional_arrow_until_activation():
    analysis = _analysis("صاعد")
    analysis["draw_mode"] = "conditional"
    analysis["directional_path_enabled"] = False
    low, high = _price_range(analysis)
    canvas = Image.new("RGBA", (1320, 2868), (0, 0, 0, 0))
    _draw_scenario_arrows(canvas, analysis, low, high)
    assert canvas.getbbox() is None

    analysis["directional_path_enabled"] = True
    active = Image.new("RGBA", (1320, 2868), (0, 0, 0, 0))
    _draw_scenario_arrows(active, analysis, low, high)
    assert active.getbbox() is not None


def test_watch_mode_keeps_two_alternative_paths():
    analysis = _analysis("صاعد")
    analysis["draw_mode"] = "watch"
    low, high = _price_range(analysis)
    canvas = Image.new("RGBA", (1320, 2868), (0, 0, 0, 0))
    _draw_scenario_arrows(canvas, analysis, low, high)
    assert canvas.getbbox() is not None


def test_most_probable_peak_and_trough_are_drawn_on_right_axis():
    analysis = _analysis("صاعد")
    low, high = _price_range(analysis)
    items = _extreme_display_items(analysis, low, high)
    labels = {item[0] for item in items}
    assert "قمة" in labels
    assert "قاع" in labels


def test_confirmed_arrow_starts_from_activation_candle_close():
    analysis = _analysis("صاعد")
    analysis["buy_scenario_details"] = {
        "is_active": True,
        "activation_candle_close": analysis["current_price"],
        "trigger_price": analysis["entry"],
        "arrow_start_price": analysis["current_price"],
    }
    low, high = _price_range(analysis)
    origin = _scenario_arrow_origin(analysis, side="buy", price_min=low, price_max=high)
    assert origin is not None
    _x, _y, start_price = origin
    assert start_price == analysis["current_price"]


def test_monitoring_arrow_uses_trigger_until_activation_close_exists():
    analysis = _analysis("هابط")
    analysis["sell_scenario_details"] = {
        "is_active": False,
        "activation_candle_close": analysis["current_price"],
        "trigger_price": analysis["entry"],
        "arrow_start_price": analysis["entry"],
    }
    low, high = _price_range(analysis)
    origin = _scenario_arrow_origin(analysis, side="sell", price_min=low, price_max=high)
    assert origin is not None
    _x, _y, start_price = origin
    assert start_price == analysis["entry"]
