from unittest.mock import patch

from PIL import Image, ImageDraw

from app.engine.renderer import (
    CHART,
    _draw_market_zones,
    _estimate_rightmost_candle_x,
    _price_range,
    _trade_display_items,
)
from app.services.analyzer import _validate_analysis
from tests.test_two_hour_chart import sample_analysis


def test_watch_mode_builds_two_unconfirmed_setups():
    data = sample_analysis()
    data.update(direction="غير واضح", buy_probability=52, sell_probability=48, setup_state="مراقبة", entry_kind="مراقبة")
    result = _validate_analysis(data)

    assert result["result_case"] == "watch"
    assert result["transaction_type"] == "مراقبة"
    assert [setup["side"] for setup in result["watch_setups"]] == ["شراء", "بيع"]
    assert all(setup["confirmed"] is False for setup in result["watch_setups"])


def test_conditional_uses_activation_and_cancellation_labels():
    analysis = sample_analysis()
    analysis.update(
        draw_mode="conditional",
        analysis_direction="صاعد",
        activation_price=analysis["entry"],
        cancellation_price=analysis["stop_loss"],
    )
    low, high = _price_range(analysis)
    _mode, items = _trade_display_items(analysis, low, high)
    assert [item[0] for item in items] == ["Active", "Cancel"]


def test_watch_cards_show_two_activations_without_fake_targets():
    result = _validate_analysis({**sample_analysis(), "direction": "غير واضح", "entry_kind": "مراقبة", "setup_state": "مراقبة"})
    low, high = _price_range(result)
    _mode, items = _trade_display_items(result, low, high)
    assert {item[0] for item in items} == {"Buy", "Sell"}


def test_rightmost_candle_detector_ignores_horizontal_levels():
    image = Image.new("RGBA", (1111, 2243), (250, 250, 250, 255))
    draw = ImageDraw.Draw(image)
    draw.line((10, 1000, 920, 1000), fill=(76, 190, 255, 255), width=2)
    for x in (300, 390, 510):
        draw.line((x, 900, x, 1140), fill=(75, 165, 150, 255), width=3)
        draw.rectangle((x - 8, 980, x + 8, 1060), fill=(75, 165, 150, 255))
    detected = _estimate_rightmost_candle_x(image)
    assert detected is not None
    assert abs(detected - 510) < 20


def test_ob_and_fvg_are_drawn_even_when_detectors_find_nothing():
    analysis = _validate_analysis({**sample_analysis(), "direction": "غير واضح", "entry_kind": "مراقبة", "setup_state": "مراقبة"})
    low, high = _price_range(analysis)
    image = Image.new("RGBA", (1320, 2868), (0, 0, 0, 0))
    before = image.tobytes()
    with patch("app.engine.renderer._detect_order_blocks", return_value=[]), patch("app.engine.renderer._detect_fvg", return_value=[]):
        _draw_market_zones(
            image,
            ImageDraw.Draw(image),
            analysis,
            analysis["candles"],
            slot=18.0,
            candle_right=650,
            price_min=low,
            price_max=high,
        )
    assert image.tobytes() != before
