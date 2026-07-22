from unittest.mock import patch

from app.engine.renderer import (
    _price_range,
    _select_directional_order_block,
    _strength_width,
    render_result,
)
from app.services.analyzer import _validate_analysis


def sample_analysis():
    candles = []
    price = 4000.0
    for index in range(30):
        open_ = price
        close = price + (0.7 if index % 3 != 0 else -0.45)
        high = max(open_, close) + 0.35
        low = min(open_, close) - 0.30
        candles.append({
            "time": f"{14 + (index * 5) // 60:02d}:{(index * 5) % 60:02d}",
            "open": open_, "high": high, "low": low, "close": close,
        })
        price = close
    return {
        "chart_readable": True,
        "candles": candles,
        "direction": "صاعد",
        "buy_probability": 68,
        "sell_probability": 32,
        "setup_state": "مؤكد",
        "entry_kind": "إعادة اختبار",
        "confirmation": "ثبات الدعم وظهور شمعة صاعدة",
        "current_price": candles[-1]["close"],
        "image_price_high": candles[-1]["close"] + 6.0,
        "image_price_low": candles[-1]["close"] - 4.0,
        "support_levels": [{"price": 4004.0, "strength": 82, "touches": 4}],
        "resistance_levels": [{"price": 4010.0, "strength": 74, "touches": 3}],
        "entry": candles[-1]["close"],
        "stop_loss": candles[-1]["close"] - 2.0,
        "stop_reason": "أسفل آخر قاع",
        "target_1": candles[-1]["close"] + 2.0,
        "target_2": candles[-1]["close"] + 3.5,
        "target_3": candles[-1]["close"] + 5.0,
        "pattern_type": "قاعان",
        "pattern_confidence": 72,
        "pattern_lines": [],
        "pattern_path": [],
        "scenario": "صعود بعد إعادة اختبار الدعم",
        "note": "الزخم الصاعد يحتاج ثباتًا فوق الدخول",
        "memory_matches": [],
    }


def test_strength_width_matches_spec():
    assert _strength_width(90) == 8
    assert _strength_width(75) == 6
    assert _strength_width(60) == 4


def test_validation_accepts_flexible_candles_and_three_targets():
    result = _validate_analysis(sample_analysis())
    assert len(result["candles"]) == len(sample_analysis()["candles"])
    assert result["target_1"] < result["target_2"] < result["target_3"]
    assert len(result["support_levels"]) <= 2
    assert len(result["resistance_levels"]) <= 2


def test_renderer_creates_png():
    result = _validate_analysis(sample_analysis())
    png = render_result(result)
    assert png.startswith(b"\x89PNG")
    assert len(png) > 10_000


def test_auto_scale_keeps_extra_margins_and_more_space_on_green_side():
    result = _validate_analysis(sample_analysis())
    price_min, price_max = _price_range(result)
    entry = float(result["entry"])

    assert price_max > float(result["image_price_high"])
    assert price_min < float(result["image_price_low"])
    assert price_max - entry > entry - price_min


def test_bearish_auto_scale_puts_more_space_below_for_green_target_zone():
    analysis = sample_analysis()
    analysis.update(
        direction="هابط",
        analysis_direction="هابط",
        draw_mode="conditional",
        current_price=4010.0,
        entry=4010.0,
        stop_loss=4012.0,
        target_1=4008.0,
        target_2=4006.5,
        target_3=4004.0,
        image_price_high=4013.0,
        image_price_low=4004.5,
    )
    price_min, price_max = _price_range(analysis)
    assert analysis["entry"] - price_min > price_max - analysis["entry"]
    assert price_max > analysis["image_price_high"]
    assert price_min < analysis["image_price_low"]


def test_order_block_is_only_selected_on_invalidation_side():
    candles = sample_analysis()["candles"]
    zones = [
        (20, 4007.8, 4008.4, 90),
        (21, 4010.8, 4011.4, 92),
    ]
    with patch("app.engine.renderer._detect_order_blocks", return_value=zones):
        bullish = _select_directional_order_block(
            {"analysis_direction": "صاعد"}, candles, focal_price=4010.0, atr=1.0
        )
        bearish = _select_directional_order_block(
            {"analysis_direction": "هابط"}, candles, focal_price=4010.0, atr=1.0
        )

    assert bullish == zones[0]
    assert bearish == zones[1]


def test_renderer_does_not_require_libraqm(monkeypatch):
    """يجب ألا يمرر الرسم معاملات RAQM إلى Pillow في Railway."""
    from PIL import ImageDraw

    original_text = ImageDraw.ImageDraw.text
    original_textbbox = ImageDraw.ImageDraw.textbbox

    def guarded_text(self, *args, **kwargs):
        forbidden = {"direction", "language", "features"}.intersection(kwargs)
        assert not forbidden, f"RAQM-only kwargs used: {forbidden}"
        return original_text(self, *args, **kwargs)

    def guarded_textbbox(self, *args, **kwargs):
        forbidden = {"direction", "language", "features"}.intersection(kwargs)
        assert not forbidden, f"RAQM-only kwargs used: {forbidden}"
        return original_textbbox(self, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", guarded_text)
    monkeypatch.setattr(ImageDraw.ImageDraw, "textbbox", guarded_textbbox)

    result = _validate_analysis(sample_analysis())
    png = render_result(result)
    assert png.startswith(b"\x89PNG")
