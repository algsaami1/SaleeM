from __future__ import annotations

from PIL import Image, ImageDraw

from app.engine.renderer import (
    _native_build_pixel_axis_model,
    _native_source_price_ratio,
    _native_y,
)


def _synthetic_chart() -> Image.Image:
    width, height = 1200, 720
    image = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    # Broker grid: 60 px per 4.56 price points.
    for y in range(60, 661, 60):
        for x in range(25, 985, 18):
            draw.line((x, y, min(x + 9, 985), y), fill=(225, 236, 242, 255), width=1)
    # Current-price line at y=480. Use a SaleeM-recognized teal/green family.
    draw.line((20, 480, 1080, 480), fill=(38, 166, 154, 255), width=2)
    return image


def test_pixel_axis_ignores_bad_vision_y_ratios_and_uses_source_grid():
    analysis = {
        "current_price": 4334.73,
        # Ratios are intentionally very wrong; v3.47 must ignore them for native placement.
        "image_axis_labels": [
            {"price": 4352.76, "y_ratio": 0.10},
            {"price": 4348.20, "y_ratio": 0.20},
            {"price": 4343.64, "y_ratio": 0.30},
            {"price": 4339.08, "y_ratio": 0.40},
            {"price": 4334.52, "y_ratio": 0.50},
            {"price": 4329.96, "y_ratio": 0.60},
        ],
    }
    image = _synthetic_chart()
    model = _native_build_pixel_axis_model(image, analysis)
    assert model is not None
    assert abs(float(model["grid_step"]) - 60.0) <= 1.0
    assert abs(float(model["price_step"]) - 4.56) <= 0.01

    analysis["_native_axis_pixel_model"] = model
    analysis["_native_axis_strict_pixel"] = True

    # 4334.52 is 0.21 below current, therefore just below y=480, not y=360 from bad ratio.
    y_tick = _native_y(analysis, 4334.52, image.height)
    assert y_tick is not None
    assert abs(y_tick - 483) <= 2

    # R1-like price 4337.05 must be ~30.5 px above the current line.
    y_r1 = _native_y(analysis, 4337.05, image.height)
    assert y_r1 is not None
    assert abs(y_r1 - 449) <= 2

    ratio = _native_source_price_ratio(analysis, 4337.05)
    assert ratio is not None
    assert abs(ratio * (image.height - 1) - y_r1) <= 1.0


def test_strict_native_axis_fails_closed_without_pixel_model():
    analysis = {
        "current_price": 4334.73,
        "_native_axis_strict_pixel": True,
        "image_axis_labels": [
            {"price": 4350.0, "y_ratio": 0.10},
            {"price": 4340.0, "y_ratio": 0.40},
            {"price": 4330.0, "y_ratio": 0.80},
        ],
    }
    assert _native_source_price_ratio(analysis, 4337.05) is None
