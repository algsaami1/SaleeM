from __future__ import annotations

import io
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image, ImageDraw, ImageFont

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:  # pragma: no cover
    arabic_reshaper = None
    get_display = None

# صورة عمودية مناسبة للهاتف، لكن جميع الإحداثيات داخلية وقابلة للتغيير.
WIDTH = 1080
HEIGHT = 1920

# لوحة ألوان قريبة من التصميم المرجعي.
BG = (4, 13, 30, 255)
WHITE = (255, 255, 255, 255)
NAVY = (235, 241, 255, 255)
TEXT = (226, 235, 247, 255)
MUTED = (155, 169, 196, 255)
BORDER = (66, 85, 123, 255)
GRID = (82, 102, 138, 42)
GREEN = (17, 183, 94, 255)
GREEN_DARK = (8, 130, 67, 255)
GREEN_FILL = (17, 183, 94, 52)
RED = (245, 63, 70, 255)
RED_DARK = (187, 30, 39, 255)
RED_FILL = (245, 63, 70, 52)
BLUE = (38, 117, 247, 255)
BLUE_FILL = (69, 139, 255, 34)
GOLD = (245, 158, 11, 255)
CREAM = (244, 194, 91, 30)
ORANGE = (249, 115, 22, 255)
PURPLE = (190, 92, 255, 255)
PURPLE_FILL = (161, 92, 245, 40)
CYAN = (76, 190, 255, 255)
CYAN_DARK = (20, 118, 160, 255)
TEAL = (60, 216, 196, 255)
TP_GREEN = (25, 211, 112, 255)
TP_GREEN_FILL = (25, 211, 112, 52)

# تخطيط صورة النتيجة: الشارت هو العنصر الرئيسي ويبدأ من أعلى الصورة،
# ثم يأتي صندوق ملاحظات التحليل أسفل الشارت وبفاصل واضح حتى يكون خارج
# صورة التحليل نفسها وليس فوقها.
CHART_CARD = (20, 20, 1060, 1352)
CHART = (56, 72, 928, 1280)
PRICE_AXIS_X = 952
NOTES = (36, 1392, 1044, 1886)
TOP_PRICE_MIN_GAP_RATIO = 0.14
TOP_PRICE_TRIGGER_ATR = 6.0
TOP_PRICE_TOP_PADDING_RATIO = 0.02

# ضبط خاصية صورة الشارت المرفوعة: نقص جزءًا من اليسار، نحافظ على
# النسبة الأصلية بدون ضغط، ثم نغطي الأجزاء العلوية والسفلية غير المهمة
# حتى يبقى الشارت واضحًا ويظهر إلى جواره محور السعر اليميني بوضوح.
UPLOADED_BG_LEFT_CROP_RATIO = 0.0
UPLOADED_BG_RIGHT_TRIM_RATIO = 0.01
UPLOADED_BG_TOP_MASK_RATIO = 0.055
UPLOADED_BG_BOTTOM_MASK_RATIO = 0.10
UPLOADED_BG_MIN_LEFT_CROP_PX = 0


class AxisCalibrationError(RuntimeError):
    """Raised when the uploaded chart cannot produce a trustworthy price axis."""

_FONT_CACHE: dict[tuple[int, bool, bool], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


def _rtl(text: str) -> str:
    if not text:
        return ""
    if arabic_reshaper is None or get_display is None:
        return text
    return get_display(arabic_reshaper.reshape(str(text)))


def _font(size: int, bold: bool = False, latin: bool = False):
    key = (size, bold, latin)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    root = Path(__file__).resolve().parents[2]
    if latin:
        candidates = [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
    else:
        candidates = [
            root / "fonts" / ("NotoSansArabicUI-Bold.ttf" if bold else "NotoSansArabicUI-Regular.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSansArabicUI-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansArabicUI-Regular.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
    for path in candidates:
        if path.exists():
            font = ImageFont.truetype(str(path), size=size)
            _FONT_CACHE[key] = font
            return font
    font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


F_STATUS = _font(20, True, True)
F_SMALL = _font(17)
F_SMALL_BOLD = _font(17, True)
F_LABEL = _font(19)
F_CARD = _font(27, True)
F_CARD_LATIN = _font(24, True, True)
F_TITLE = _font(36, True)
F_TITLE_LATIN = _font(36, True, True)
F_HEADER = _font(35, True, True)
F_BUY = _font(34, True, True)
F_PERCENT = _font(29, True, True)
F_AXIS = _font(15, False, True)
F_SESSION = _font(12, True)
F_LEVEL = _font(16, True)
F_ZONE = _font(15, True, True)
F_TRADE = _font(18, True)
F_TRADE_LATIN = _font(18, True, True)
F_TRADE_SMALL = _font(15, True)
F_TRADE_SMALL_LATIN = _font(15, True, True)
F_NOTE_TITLE = _font(29, True)
F_NOTE = _font(19)
F_NOTE_MIXED = _font(19, False, True)
F_NOTE_BOLD = _font(20, True)
F_BUTTON = _font(27, False)
F_DISCLAIMER = _font(15)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _fmt_price(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "—"
    rounded = round(number, 2)
    if abs(rounded - round(rounded)) < 0.005:
        return str(int(round(rounded)))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def _fmt_axis_price(value: Any) -> str:
    """Format source-axis labels exactly like a broker price scale.

    Trade labels may omit trailing zeroes to save space, but the right price
    axis must preserve two decimals so values such as 4049.10 and 4055.80 do
    not visually differ from the uploaded chart.
    """
    number = _number(value)
    if number is None:
        return "—"
    return f"{round(number, 2):.2f}"


def _time_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "--:--"
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.strftime("%H:%M")
    except ValueError:
        pass
    if "T" in text:
        time_part = text.split("T", 1)[1]
        if len(time_part) >= 5:
            return time_part[:5]
    if " " in text:
        time_part = text.rsplit(" ", 1)[-1]
        if len(time_part) >= 5 and ":" in time_part:
            return time_part[:5]
    if len(text) >= 5 and text[2:3] == ":":
        return text[:5]
    return text[-5:]



def _localized_datetime(value: Any, source_timezone: str | None = None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        if len(text) >= 5 and text[2:3] == ":":
            try:
                parsed = datetime(2000, 1, 1, int(text[:2]), int(text[3:5]))
            except ValueError:
                return None
    if parsed is None:
        return None

    source_name = str(source_timezone or "Asia/Muscat").strip() or "Asia/Muscat"
    display_name = os.getenv("DISPLAY_TIMEZONE", "Asia/Muscat").strip() or "Asia/Muscat"
    try:
        source_zone = ZoneInfo(source_name)
    except ZoneInfoNotFoundError:
        source_zone = timezone.utc
    try:
        display_zone = ZoneInfo(display_name)
    except ZoneInfoNotFoundError:
        display_zone = ZoneInfo("Asia/Muscat")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=source_zone)
    return parsed.astimezone(display_zone)


def _market_time_label(value: Any, source_timezone: str | None = None) -> str:
    parsed = _localized_datetime(value, source_timezone)
    return parsed.strftime("%H:%M") if parsed is not None else _time_label(value)

def _draw_rtl(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font, fill=TEXT, anchor: str = "ra") -> None:
    draw.text(xy, _rtl(text), font=font, fill=fill, anchor=anchor)


def _draw_mixed_rtl(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font,
    fill=TEXT,
    anchor: str = "ra",
) -> None:
    """رسم النص العربي المختلط من دون الاعتماد على libraqm.

    يعالج ``arabic-reshaper`` و``python-bidi`` اتجاه الحروف والأجزاء
    اللاتينية قبل تمرير النص إلى Pillow؛ لذلك لا نستخدم معاملات
    ``direction`` أو ``language`` التي قد لا تتوفر في بيئة Railway.
    """
    draw.text(xy, _rtl(str(text)), font=font, fill=fill, anchor=anchor)


def _mixed_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    box = draw.textbbox((0, 0), _rtl(str(text)), font=font)
    return box[2] - box[0]


def _fit_mixed_rtl(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    cleaned = " ".join(str(text).split())
    if _mixed_width(draw, cleaned, font) <= max_width:
        return cleaned
    while len(cleaned) > 8 and _mixed_width(draw, cleaned + "…", font) > max_width:
        cleaned = cleaned[:-1]
    return cleaned.rstrip() + "…"


def _text_width(draw: ImageDraw.ImageDraw, text: str, font, rtl: bool = True) -> int:
    shown = _rtl(text) if rtl else str(text)
    box = draw.textbbox((0, 0), shown, font=font)
    return box[2] - box[0]


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, rtl: bool = True) -> str:
    cleaned = " ".join(str(text).split())
    if _text_width(draw, cleaned, font, rtl) <= max_width:
        return cleaned
    while len(cleaned) > 7 and _text_width(draw, cleaned + "…", font, rtl) > max_width:
        cleaned = cleaned[:-1]
    return cleaned.rstrip() + "…"


def _shadow_card(image: Image.Image, rect: tuple[int, int, int, int], radius: int = 22, shadow: int = 7) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x1, y1, x2, y2 = rect
    d.rounded_rectangle((x1, y1 + shadow, x2, y2 + shadow), radius=radius, fill=(0, 0, 0, 70))
    image.alpha_composite(layer)


def _rounded_label(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font,
    *,
    fill=WHITE,
    outline=BORDER,
    text_fill=TEXT,
    padding_x: int = 10,
    padding_y: int = 5,
    rtl: bool = True,
    align_right: bool = False,
    radius: int = 8,
) -> tuple[int, int, int, int]:
    shown = _rtl(text) if rtl else str(text)
    box = draw.textbbox((0, 0), shown, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    if align_right:
        x -= tw + padding_x * 2
    rect = (x, y, x + tw + padding_x * 2, y + th + padding_y * 2)
    draw.rounded_rectangle(rect, radius=radius, fill=fill, outline=outline, width=1)
    draw.text((x + padding_x, y + padding_y - box[1]), shown, font=font, fill=text_fill)
    return rect


def _dash_line(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color, width: int = 2, dash: int = 11, gap: int = 8) -> None:
    x1, y1 = start
    x2, y2 = end
    length = math.hypot(x2 - x1, y2 - y1)
    if length <= 0:
        return
    dx, dy = (x2 - x1) / length, (y2 - y1) / length
    pos = 0.0
    while pos < length:
        stop = min(length, pos + dash)
        draw.line((x1 + dx * pos, y1 + dy * pos, x1 + dx * stop, y1 + dy * stop), fill=color, width=width)
        pos += dash + gap


def _strength_width(strength: int) -> int:
    if strength >= 85:
        return 3
    if strength >= 70:
        return 2
    return 1


def _strength_name(strength: int) -> str:
    if strength >= 85:
        return "قوية جدًا"
    if strength >= 70:
        return "قوية"
    return "متوسطة"


def _image_key_prices(analysis: dict[str, Any]) -> tuple[float, float, float] | None:
    # نفعّل هذا النمط فقط عندما تكون قراءة محور الصورة نفسها متاحة، حتى لا
    # نفسد سلوك الاختيار التحليلي في الحالات القديمة أو الاختبارات الاصطناعية.
    if not (analysis.get("image_axis_labels") or []):
        return None
    image_high = _number(analysis.get("image_price_high"))
    current = _number(analysis.get("current_price"))
    image_low = _number(analysis.get("image_price_low"))
    if image_high is None or current is None or image_low is None:
        return None
    if not (image_low < current < image_high):
        return None
    return float(image_high), float(current), float(image_low)


def _strict_axis_sync(analysis: dict[str, Any]) -> bool:
    if _exact_image_axis_model(analysis) is not None:
        return True
    if _image_axis_step_model(analysis) is not None:
        return True
    return _image_key_prices(analysis) is not None


def _image_axis_points(analysis: dict[str, Any]) -> list[tuple[float, float]]:
    labels = analysis.get("image_axis_labels") or []
    points: list[tuple[float, float]] = []
    for item in labels:
        if not isinstance(item, dict):
            continue
        price = _number(item.get("price"))
        y_ratio = _number(item.get("y_ratio"))
        if price is None or y_ratio is None:
            continue
        y_ratio = max(0.0, min(1.0, float(y_ratio)))
        points.append((float(price), y_ratio))
    points.sort(key=lambda item: item[1])

    # Remove near-duplicate OCR readings without changing the original order.
    deduped: list[tuple[float, float]] = []
    for price, ratio in points:
        duplicate = False
        for old_price, old_ratio in deduped:
            if abs(ratio - old_ratio) <= 0.004 and abs(price - old_price) <= 0.08:
                duplicate = True
                break
        if not duplicate:
            deduped.append((price, ratio))
    return deduped


def _median_number(values: list[float]) -> float | None:
    clean = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not clean:
        return None
    middle = len(clean) // 2
    if len(clean) % 2:
        return clean[middle]
    return (clean[middle - 1] + clean[middle]) / 2.0


def _exact_image_axis_model(analysis: dict[str, Any]) -> dict[str, Any] | None:
    """Fit a robust literal axis model from all readable source labels.

    The model uses a Theil-Sen style median slope so one bad OCR label cannot
    bend the whole scale.  It then removes outliers and refits a single linear
    price-to-Y transform.  Exact mode is enabled only when at least five
    consistent labels cover a useful portion of the chart.
    """
    cached = analysis.get("_exact_axis_model")
    if isinstance(cached, dict):
        return cached

    points = _image_axis_points(analysis)
    if len(points) < 5:
        return None

    pair_slopes: list[float] = []
    for index, (price_a, ratio_a) in enumerate(points):
        for price_b, ratio_b in points[index + 1:]:
            ratio_delta = ratio_b - ratio_a
            price_delta = price_a - price_b
            if ratio_delta < 0.025 or price_delta <= 0.01:
                continue
            pair_slopes.append(price_delta / ratio_delta)

    slope = _median_number(pair_slopes)
    if slope is None or slope <= 0.1:
        return None

    intercept = _median_number([price + slope * ratio for price, ratio in points])
    if intercept is None:
        return None

    adjacent_steps = [
        points[index][0] - points[index + 1][0]
        for index in range(len(points) - 1)
        if points[index][0] - points[index + 1][0] > 0.01
    ]
    typical_step = _median_number(adjacent_steps) or 0.5
    tolerance = max(0.10, typical_step * 0.24, slope * 0.010)

    inliers = [
        (price, ratio)
        for price, ratio in points
        if abs(price - (intercept - slope * ratio)) <= tolerance
    ]
    if len(inliers) < 5:
        return None

    # Refit after outlier removal.  price = intercept - slope * y_ratio.
    mean_ratio = sum(ratio for _, ratio in inliers) / len(inliers)
    mean_price = sum(price for price, _ in inliers) / len(inliers)
    variance = sum((ratio - mean_ratio) ** 2 for _, ratio in inliers)
    if variance <= 1e-9:
        return None
    covariance = sum((ratio - mean_ratio) * (price - mean_price) for price, ratio in inliers)
    fitted_slope = -covariance / variance
    if fitted_slope <= 0.1:
        return None
    fitted_intercept = mean_price + fitted_slope * mean_ratio

    final_tolerance = max(0.08, typical_step * 0.20, fitted_slope * 0.008)
    final_points = [
        (price, ratio)
        for price, ratio in inliers
        if abs(price - (fitted_intercept - fitted_slope * ratio)) <= final_tolerance
    ]
    if len(final_points) < 5:
        return None

    # Preserve only strictly descending prices as Y increases.
    monotonic: list[tuple[float, float]] = []
    for price, ratio in final_points:
        if monotonic and price >= monotonic[-1][0] - 0.01:
            continue
        monotonic.append((price, ratio))
    if len(monotonic) < 5:
        return None

    # Axis labels should follow a regular tick sequence. Missing labels are
    # allowed only when the price gap and the pixel gap both represent the same
    # integer multiple of the typical step.
    interval_pairs = [
        (monotonic[index][0] - monotonic[index + 1][0], monotonic[index + 1][1] - monotonic[index][1])
        for index in range(len(monotonic) - 1)
    ]
    price_gaps = [gap for gap, _ in interval_pairs if gap > 0.01]
    ratio_gaps = [gap for _, gap in interval_pairs if gap > 0.005]
    base_price_gap = _median_number(price_gaps)
    base_ratio_gap = _median_number(ratio_gaps)
    if base_price_gap is None or base_ratio_gap is None:
        return None

    regular_intervals = 0
    for price_gap, ratio_gap in interval_pairs:
        multiple = max(1, int(round(price_gap / base_price_gap)))
        expected_price_gap = base_price_gap * multiple
        expected_ratio_gap = base_ratio_gap * multiple
        price_error = abs(price_gap - expected_price_gap) / max(expected_price_gap, 1e-6)
        ratio_error = abs(ratio_gap - expected_ratio_gap) / max(expected_ratio_gap, 1e-6)
        if price_error <= 0.20 and ratio_error <= 0.24:
            regular_intervals += 1
    regularity = regular_intervals / max(1, len(interval_pairs))
    if regularity < 0.72:
        return None

    coverage = monotonic[-1][1] - monotonic[0][1]
    residuals = [abs(price - (fitted_intercept - fitted_slope * ratio)) for price, ratio in monotonic]
    median_residual = _median_number(residuals) or 0.0
    inlier_ratio = len(monotonic) / max(1, len(points))
    count_score = min(1.0, len(monotonic) / 8.0)
    coverage_score = min(1.0, coverage / 0.55)
    residual_score = max(0.0, 1.0 - median_residual / max(final_tolerance, 1e-6))
    confidence = (
        0.42 * inlier_ratio
        + 0.28 * count_score
        + 0.18 * coverage_score
        + 0.08 * residual_score
        + 0.04 * regularity
    )
    if confidence < 0.70 or coverage < 0.30:
        return None

    model: dict[str, Any] = {
        "mode": "exact",
        "points": [(float(price), float(ratio)) for price, ratio in monotonic],
        "slope": float(fitted_slope),
        "intercept": float(fitted_intercept),
        "price_max": float(fitted_intercept),
        "price_min": float(fitted_intercept - fitted_slope),
        "confidence": round(float(confidence), 4),
        "source_count": len(points),
        "inlier_count": len(monotonic),
        "median_residual": float(median_residual),
        "regularity": round(float(regularity), 4),
    }
    analysis["_exact_axis_model"] = model
    analysis["axis_calibration_mode"] = "exact"
    analysis["axis_calibration_confidence"] = round(float(confidence) * 100.0, 1)
    return model


def _exact_source_axis_labels(
    analysis: dict[str, Any],
    price_min: float | None = None,
    price_max: float | None = None,
) -> list[tuple[str, float, int]]:
    """Return cleaned source prices using the same transform as every drawing.

    The previous implementation drew OCR labels at their raw pixel ratios while
    candles, levels and trade lines used the fitted price transform.  Even a
    small OCR residual therefore produced two competing vertical scales.  When
    a calibrated range is supplied, all labels are now projected through
    ``_price_y`` so the chart and the right axis are mathematically identical.
    """
    model = _exact_image_axis_model(analysis)
    if model is None:
        return []
    points = model.get("points") or []
    top, bottom = CHART[1], CHART[3]
    chart_height = bottom - top
    labels: list[tuple[str, float, int]] = []
    use_shared_transform = (
        price_min is not None
        and price_max is not None
        and float(price_max) > float(price_min)
    )
    for price, y_ratio in points:
        if use_shared_transform:
            y = _price_y(float(price), float(price_min), float(price_max))
        else:
            y = int(round(top + float(y_ratio) * chart_height))
        labels.append(("axis", round(float(price), 2), y))
    return labels


def _image_axis_step_model(analysis: dict[str, Any]) -> dict[str, float | int] | None:
    """Build the chart scale from inner visual anchors.

    User preference: ignore the outermost OCR prices when possible.  The label
    directly below the highest visible price becomes the effective top anchor
    of the right axis, the label below it defines the price/pixel step, and
    the penultimate visible price becomes the lower anchor.  This is usually
    more stable because the very first and very last visible labels are the
    most likely to be clipped by the screenshot edges.

    If the image does not contain enough labels for the inner-anchor model, we
    gracefully fall back to the original top/next/bottom model.
    """
    points = _image_axis_points(analysis)
    if len(points) < 3:
        return None

    use_inner_anchors = len(points) >= 5
    if use_inner_anchors:
        top_price, top_ratio = points[1]
        second_price, second_ratio = points[2]
        bottom_price, bottom_ratio = points[-2]
    else:
        top_price, top_ratio = points[0]
        second_price, second_ratio = points[1]
        bottom_price, bottom_ratio = points[-1]

    price_step = top_price - second_price
    ratio_step = second_ratio - top_ratio
    if price_step <= 0.01 or ratio_step < 0.025:
        return None
    if bottom_price >= second_price or bottom_ratio <= second_ratio:
        return None

    raw_intervals = (top_price - bottom_price) / price_step
    intervals = int(round(raw_intervals))
    if intervals < 1:
        return None

    residual = abs((top_price - intervals * price_step) - bottom_price)
    if residual > max(0.08, price_step * 0.18):
        return None

    expected_bottom_ratio = top_ratio + intervals * ratio_step
    if abs(expected_bottom_ratio - bottom_ratio) > max(0.055, ratio_step * 0.55):
        return None

    return {
        "top_price": float(top_price),
        "top_ratio": float(top_ratio),
        "second_price": float(second_price),
        "second_ratio": float(second_ratio),
        "bottom_price": float(bottom_price),
        "bottom_ratio": float(bottom_ratio),
        "price_step": float(price_step),
        "ratio_step": float(ratio_step),
        "intervals": intervals,
        "uses_inner_anchors": 1 if use_inner_anchors else 0,
    }


def _dynamic_image_axis_range(
    analysis: dict[str, Any],
    reference_y: int | None = None,
) -> tuple[float, float] | None:
    """Build one authoritative price-to-pixel transform for the whole chart.

    The label sequence determines the scale (price per normalized Y).  The
    uploaded green current-price line, when available, determines the vertical
    offset.  As a result candles, support/resistance, entry, stop, targets,
    current price and right-axis numbers all use exactly the same transform.
    """
    top, bottom = CHART[1], CHART[3]
    chart_height = max(1, bottom - top)

    reference_ratio: float | None = None
    if reference_y is not None:
        reference_ratio = (float(reference_y) - top) / chart_height
        reference_ratio = max(0.0, min(1.0, reference_ratio))
    else:
        model_ratio = _number(analysis.get("current_price_y_ratio"))
        if model_ratio is not None:
            reference_ratio = max(0.0, min(1.0, float(model_ratio)))

    current = _number(analysis.get("current_price"))

    exact_model = _exact_image_axis_model(analysis)
    if exact_model is not None:
        price_per_ratio = float(exact_model["slope"])
        if current is not None and reference_ratio is not None:
            price_max = float(current) + price_per_ratio * reference_ratio
            anchor_source = "current_line"
        else:
            price_max = float(exact_model["price_max"])
            anchor_source = "axis_fit"
        price_min = price_max - price_per_ratio
        if price_max > price_min and price_max - price_min >= 0.1:
            analysis["_calibrated_axis_model"] = {
                **exact_model,
                "mode": "exact",
                "price_per_ratio": float(price_per_ratio),
                "price_max": float(price_max),
                "price_min": float(price_min),
                "anchor_source": anchor_source,
                "reference_ratio": reference_ratio,
            }
            analysis["axis_alignment_mode"] = "single_transform"
            return price_min, price_max

    model = _image_axis_step_model(analysis)
    if model is None:
        return None

    top_price = float(model["top_price"])
    top_ratio = float(model["top_ratio"])
    price_step = float(model["price_step"])
    ratio_step = float(model["ratio_step"])
    price_per_ratio = price_step / ratio_step

    if current is not None and reference_ratio is not None:
        price_max = float(current) + price_per_ratio * reference_ratio
        anchor_source = "current_line"
    else:
        price_max = top_price + top_ratio * price_per_ratio
        anchor_source = "axis_fit"
    price_min = price_max - price_per_ratio
    if price_max <= price_min or price_max - price_min < 0.1:
        return None

    analysis["_calibrated_axis_model"] = {
        **model,
        "mode": "reconstructed",
        "price_per_ratio": float(price_per_ratio),
        "price_max": float(price_max),
        "price_min": float(price_min),
        "anchor_source": anchor_source,
        "reference_ratio": reference_ratio,
    }
    analysis["axis_calibration_mode"] = "reconstructed"
    analysis["axis_alignment_mode"] = "single_transform"
    return price_min, price_max


def validate_uploaded_axis(
    analysis: dict[str, Any],
    chart_background_path: str | os.PathLike[str] | None,
) -> tuple[bool, str]:
    """Validate a user screenshot before generating a final result image.

    The chart axis remains the primary reference.  We prefer the inner labels
    (the price below the highest, the price below it, and the penultimate low)
    because they are usually more stable than the clipped outer edges.  The
    current-price line remains useful for rendering the green badge, but it
    does not block generation when the axis sequence itself is readable.
    """
    prepared_background, detected_green_line_y, _visible_candles = _prepare_chart_background(chart_background_path)
    if prepared_background is None:
        return False, "تعذر تجهيز صورة الشارت للمعايرة."

    exact_model = _exact_image_axis_model(analysis)
    reconstructed_model = _image_axis_step_model(analysis)
    if exact_model is None and reconstructed_model is None:
        return False, "لم تُقرأ نقاط سعرية كافية ومتناسقة من محور الصورة لبناء مقياس موثوق."

    calibrated = _dynamic_image_axis_range(analysis, detected_green_line_y)
    if calibrated is None:
        return False, "تعذر بناء محور السعر من مواضع الأرقام الأصلية أو من نقاط الارتكاز الاحتياطية."

    labels = _right_axis_labels(analysis, calibrated[0], calibrated[1])
    if len(labels) < 3:
        return False, "لم يتكوّن سلم سعري كامل وموثوق من الصورة."
    return True, ""


def _image_axis_range(analysis: dict[str, Any]) -> tuple[float, float] | None:
    # Full source-axis labels are the primary reference.  High/current/low are
    # used only as a fallback when the image did not provide enough labels.
    dynamic_range = _dynamic_image_axis_range(analysis)
    if dynamic_range is not None:
        return dynamic_range

    key_prices = _image_key_prices(analysis)
    if key_prices is not None:
        image_high, current, image_low = key_prices
        span = max(0.0001, image_high - image_low)
        pad = max(span * 0.04, 0.12)
        return image_low - pad, image_high + pad
    return None


def _price_range(analysis: dict[str, Any]) -> tuple[float, float]:
    """إنشاء محور سعر يركز على منطقة القرار بدل ضغط الشموع.

    السعر الحالي والشموع والدعم والمقاومة والدخول والوقف والأهداف هي العناصر
    الحاكمة. أعلى وأدنى سعر المقروءان من الصورة يُستخدمان كمرجع مساعد فقط؛
    فإذا كانا بعيدين جدًا ولا يخدمان السيناريو لا نسمح لهما بتصغير الشموع.
    """
    candles = analysis.get("candles") or []
    candle_values: list[float] = []
    candle_ranges: list[float] = []
    for candle in candles:
        high = _number(candle.get("high"))
        low = _number(candle.get("low"))
        if high is None or low is None:
            continue
        candle_values.extend((high, low))
        candle_ranges.append(max(0.01, high - low))

    current = _number(analysis.get("current_price"))
    draw_mode = str(analysis.get("draw_mode") or "watch")
    direction = str(analysis.get("analysis_direction") or analysis.get("direction") or "غير واضح")

    trade_values: list[float] = []
    if draw_mode != "watch":
        for key in ("entry", "stop_loss", "target_1", "target_2", "target_3"):
            value = _number(analysis.get(key))
            if value is not None:
                trade_values.append(value)

    level_values: list[float] = []
    for key in ("support_levels", "resistance_levels"):
        for level in analysis.get(key) or []:
            price = _number(level.get("price"))
            if price is not None:
                level_values.append(price)

    anchor = _number(analysis.get("entry")) if draw_mode != "watch" else current
    if anchor is None:
        anchor = current
    if anchor is None and candles:
        anchor = _number(candles[-1].get("close"))
    if anchor is None:
        anchor = 0.0

    atr = median(candle_ranges) if candle_ranges else 1.0
    atr = max(0.05, float(atr))

    axis_range = _image_axis_range(analysis)
    if axis_range is not None:
        return axis_range

    # نبقي المستويات القريبة المفيدة فقط حتى لا تُضغط منطقة القرار.
    max_level_distance = max(atr * 16.0, 10.0)
    relevant_levels = [value for value in level_values if abs(value - anchor) <= max_level_distance]
    core_values = candle_values + trade_values + relevant_levels
    if current is not None:
        core_values.append(current)
    if not core_values:
        core_values = [anchor - 1.0, anchor + 1.0]

    core_low, core_high = min(core_values), max(core_values)
    core_span = max(core_high - core_low, atr * 8.0, 4.0)

    # حدود الصورة لا تُضم إلا إن كانت قريبة من المنطقة المفيدة.
    image_high = _number(analysis.get("image_price_high"))
    image_low = _number(analysis.get("image_price_low"))
    image_limit = max(core_span * 0.65, atr * 10.0, 6.0)
    if image_high is not None and image_high > anchor and image_high - core_high <= image_limit:
        core_high = max(core_high, image_high)
    if image_low is not None and image_low < anchor and core_low - image_low <= image_limit:
        core_low = min(core_low, image_low)

    above = max(core_high - anchor, core_span * 0.36)
    below = max(anchor - core_low, core_span * 0.36)

    # نضيف هامشًا معتدلًا في جهة الهدف من دون موازنة كامل التاريخ المقابل؛
    # لأن الموازنة القسرية كانت تنشئ فراغًا كبيرًا وتضغط الشموع.
    active_trade = draw_mode != "watch" and direction in {"صاعد", "هابط"}
    if active_trade and direction == "صاعد":
        above = max(above * 1.10, below * 1.04, atr * 3.0)
    elif active_trade and direction == "هابط":
        below = max(below * 1.10, above * 1.04, atr * 3.0)
    else:
        balanced = max(above, below)
        above = max(above, balanced * 0.82)
        below = max(below, balanced * 0.82)

    visible_span = max(above + below, atr * 8.0, 4.0)
    edge_padding = max(atr * 0.85, visible_span * 0.075, 0.45)
    standard_price_min = anchor - below - edge_padding
    standard_price_max = anchor + above + edge_padding

    # إذا كانت المسافة المرئية بين أعلى سعر الصورة والسعر الحالي صغيرة جدًا
    # مقارنة بمدى المحور المحسوب، نعيد بناء المدى بحيث تصبح هذه المسافة مرجعًا
    # مباشرًا لمحور السعر. عندها من الطبيعي أن تختفي أي رسومات تقع خارج المدى.
    top_gap_priority = False
    if current is not None and image_high is not None and image_high > current:
        image_gap = image_high - current
        current_gap_ratio = image_gap / max(0.0001, standard_price_max - standard_price_min)
        if current_gap_ratio < TOP_PRICE_MIN_GAP_RATIO:
            top_gap_priority = True
            desired_total_span = max(image_gap / TOP_PRICE_MIN_GAP_RATIO, atr * 4.5, image_gap * 2.2)
            top_padding = max(desired_total_span * TOP_PRICE_TOP_PADDING_RATIO, atr * 0.10, 0.06)
            price_max = image_high + top_padding
            price_min = price_max - desired_total_span
        else:
            price_min = standard_price_min
            price_max = standard_price_max
    else:
        price_min = standard_price_min
        price_max = standard_price_max

    if price_max <= price_min:
        return anchor - 1.0, anchor + 1.0
    return price_min, price_max

def _price_y(price: float, price_min: float, price_max: float) -> int:
    left, top, right, bottom = CHART
    ratio = (price_max - price) / max(0.0001, price_max - price_min)
    return int(top + max(0.0, min(1.0, ratio)) * (bottom - top))


def _is_visible_price(price: float | None, price_min: float, price_max: float) -> bool:
    if price is None:
        return False
    return price_min <= float(price) <= price_max


def _anchored_price_range(
    analysis: dict[str, Any],
    price_min: float,
    price_max: float,
    reference_y: int | None,
) -> tuple[float, float]:
    """Shift the complete price transform so the current price sits on the
    green reference line detected in the uploaded chart.

    In the special case where the uploaded chart provides a nearby visible top
    price, that top price becomes the primary anchor for the right price axis.
    This keeps the vertical distance between the top-price badge and the green
    current-price badge visually meaningful instead of being washed out by a
    much larger auto-scaled span.
    """
    current = _number(analysis.get("current_price"))
    if current is None or reference_y is None:
        return price_min, price_max

    _, top, _, bottom = CHART
    chart_height = max(1, bottom - top)
    y = int(max(top + 1, min(bottom - 1, reference_y)))

    # Fractions of the chart available above and below the detected line.
    above_fraction = max(1.0 / chart_height, (y - top) / chart_height)
    below_fraction = max(1.0 / chart_height, (bottom - y) / chart_height)
    original_span = max(0.0001, price_max - price_min)

    key_prices = _image_key_prices(analysis)
    if key_prices is not None:
        image_high, _, image_low = key_prices
        above_gap = max(0.0001, image_high - current)
        below_gap = max(0.0001, current - image_low)
        top_padding = max(above_gap * 0.04, original_span * 0.01, 0.06)
        bottom_padding = max(below_gap * 0.04, original_span * 0.01, 0.06)
        span = max(
            (above_gap + top_padding) / above_fraction,
            (below_gap + bottom_padding) / below_fraction,
            original_span,
            4.0,
        )
        anchored_max = current + above_fraction * span
        anchored_min = current - below_fraction * span
        if anchored_max > anchored_min:
            return anchored_min, anchored_max

    image_high = _number(analysis.get("image_price_high"))
    if image_high is not None and image_high > current and above_fraction >= 0.10:
        image_gap = image_high - current
        gap_ratio = image_gap / original_span
        if gap_ratio <= max(TOP_PRICE_MIN_GAP_RATIO + 0.03, 0.19):
            top_padding = max(original_span * TOP_PRICE_TOP_PADDING_RATIO, image_gap * 0.04, 0.06)
            desired_above = image_gap + top_padding
            span = max(desired_above / above_fraction, desired_above + 0.8, 4.0)
            anchored_max = current + above_fraction * span
            anchored_min = anchored_max - span
            if anchored_max > anchored_min:
                return anchored_min, anchored_max

    visible_values: list[float] = [current]
    for candle in analysis.get("candles") or []:
        for key in ("high", "low"):
            value = _number(candle.get(key))
            if value is not None:
                visible_values.append(value)
    for key in ("entry", "stop_loss", "target_1", "target_2", "target_3"):
        value = _number(analysis.get(key))
        if value is not None:
            visible_values.append(value)
    for key in ("support_levels", "resistance_levels"):
        for level in analysis.get(key) or []:
            value = _number(level.get("price"))
            if value is not None:
                visible_values.append(value)

    required_above = max((value - current for value in visible_values), default=0.0)
    required_below = max((current - value for value in visible_values), default=0.0)

    # Preserve the previous visual scale whenever possible.  If the green line
    # is near an edge, expand just enough so no important drawing is clipped.
    span = max(
        original_span,
        required_above / above_fraction if required_above > 0 else 0.0,
        required_below / below_fraction if required_below > 0 else 0.0,
    )
    span *= 1.015

    anchored_max = current + above_fraction * span
    anchored_min = current - below_fraction * span
    return anchored_min, anchored_max


def _fit_cover(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Prepare the uploaded chart without vertical distortion.

    The user asked to keep exactly the *visible* chart portion from the
    uploaded screenshot without squeezing or stretching it. We therefore keep
    the user-provided visible crop as-is, preserve the original aspect ratio
    with uniform scaling, and align the result to the left inside the chart
    frame so the custom SaleeM price axis remains clear.
    """
    target_w, target_h = size
    source_w, source_h = source.size
    if source_w <= 1 or source_h <= 1:
        return source.resize(size, resample=Image.Resampling.LANCZOS)

    left_crop = max(UPLOADED_BG_MIN_LEFT_CROP_PX, int(round(source_w * UPLOADED_BG_LEFT_CROP_RATIO)))
    right_trim = int(round(source_w * UPLOADED_BG_RIGHT_TRIM_RATIO))
    crop_left = min(max(0, left_crop), max(0, source_w - 2))
    crop_right = max(crop_left + 1, source_w - right_trim)
    focused = source.crop((crop_left, 0, crop_right, source_h))

    # Uniform scaling preserves candle/body proportions and avoids the squeezed
    # look that a direct width+height resize introduces.
    scale = target_h / max(1, focused.size[1])
    scaled_w = max(1, int(round(focused.size[0] * scale)))
    scaled_h = max(1, int(round(focused.size[1] * scale)))
    resized = focused.resize((scaled_w, scaled_h), resample=Image.Resampling.LANCZOS)

    canvas = Image.new('RGBA', (target_w, target_h), (6, 17, 40, 255))

    if scaled_w >= target_w:
        # Keep the right side from the source visible, but because we already
        # cropped the source's far left area, this still feels visually shifted
        # left and leaves the SaleeM custom right axis readable.
        window = resized.crop((0, 0, target_w, target_h))
        canvas.alpha_composite(window, (0, 0))
    else:
        # Leave the extra width on the right so the chart feels left-shifted.
        y = max(0, (target_h - scaled_h) // 2)
        canvas.alpha_composite(resized, (0, y))

    return canvas


def _is_green_reference_pixel(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, a = pixel
    if a < 110:
        return False
    if g < 78:
        return False
    if g < r + 15:
        return False
    if b > g + 55:
        return False
    if (g + b) < 150:
        return False
    return True


def _row_green_metrics(chart_image: Image.Image, y: int) -> tuple[int, int, int, int, int]:
    """Return green occupancy and the longest horizontal run for one row.

    The current-price marker is normally a thin horizontal line that reaches
    most of the chart and often touches the right-hand price badge.  Capturing
    the run bounds and right-edge occupancy lets the detector distinguish that
    line from green candle bodies or broad target zones.
    """
    width, _ = chart_image.size
    count = 0
    run = 0
    max_run = 0
    run_start = -1
    best_start = -1
    best_end = -1
    right_count = 0
    right_start = int(width * 0.78)
    pixels = chart_image.load()

    for x in range(width):
        if _is_green_reference_pixel(pixels[x, y]):
            count += 1
            if x >= right_start:
                right_count += 1
            if run == 0:
                run_start = x
            run += 1
            if run > max_run:
                max_run = run
                best_start = run_start
                best_end = x
        else:
            run = 0
            run_start = -1
    return count, max_run, best_start, best_end, right_count


def _row_green_score(chart_image: Image.Image, y: int) -> tuple[int, int]:
    count, max_run, _, _, _ = _row_green_metrics(chart_image, y)
    return count, max_run


def _detect_green_reference_line_y(chart_image: Image.Image) -> int | None:
    """Detect the uploaded chart's real current-price line.

    A valid candidate must look like a *thin* horizontal feature spread across
    the chart.  Extra weight is given when it reaches the right side, where the
    broker's current-price badge normally sits.  Wide green areas are rejected
    so a TP zone or a large bullish candle cannot move the current-price card.
    """
    width, height = chart_image.size
    if width < 80 or height < 80:
        return None

    top_skip = max(8, height // 30)
    bottom_skip = max(8, height // 30)
    min_run = max(36, int(width * 0.28))
    min_count = max(48, int(width * 0.30))
    min_right = max(3, int(width * 0.012))

    candidates: list[tuple[int, int, int]] = []
    for y in range(top_skip, height - bottom_skip):
        count, max_run, run_start, run_end, right_count = _row_green_metrics(chart_image, y)
        if max_run < min_run and count < min_count:
            continue

        reaches_right = run_end >= int(width * 0.82) or right_count >= min_right
        spans_chart = run_start >= 0 and run_start <= int(width * 0.18) and run_end >= int(width * 0.72)
        if not reaches_right and not spans_chart:
            continue

        score = max_run * 4 + count + right_count * 3
        if reaches_right:
            score += int(width * 0.35)
        if spans_chart:
            score += int(width * 0.25)
        candidates.append((y, score, max_run))

    if not candidates:
        return None

    # Group consecutive rows.  A real line is usually 1-4 px thick; a filled
    # green rectangle remains strong for many rows and is therefore rejected.
    bands: list[list[tuple[int, int, int]]] = []
    for candidate in candidates:
        if not bands or candidate[0] > bands[-1][-1][0] + 1:
            bands.append([candidate])
        else:
            bands[-1].append(candidate)

    max_thickness = max(7, int(height * 0.009))
    valid_bands = [band for band in bands if len(band) <= max_thickness]
    if not valid_bands:
        return None

    best_band = max(valid_bands, key=lambda band: max(item[1] for item in band))
    best_score = max(item[1] for item in best_band)
    strong_rows = [(y, score) for y, score, _ in best_band if score >= int(best_score * 0.72)]
    if not strong_rows:
        strong_rows = [(y, score) for y, score, _ in best_band]

    weighted_sum = sum(y * score for y, score in strong_rows)
    total_score = sum(score for _, score in strong_rows)
    return int(round(weighted_sum / max(1, total_score)))


def _analysis_current_reference_y(analysis: dict[str, Any]) -> int | None:
    """Fallback to the model-read current line position when pixels are unclear."""
    ratio = _number(analysis.get("current_price_y_ratio"))
    if ratio is None:
        return None
    ratio = max(0.0, min(1.0, float(ratio)))
    top, bottom = CHART[1], CHART[3]
    return int(round(top + ratio * (bottom - top)))


def _axis_checked_current_reference_y(
    analysis: dict[str, Any],
    price_min: float,
    price_max: float,
    detected_y: int | None,
) -> int | None:
    """Return the current-price Y from the shared calibrated transform.

    ``_dynamic_image_axis_range`` already uses the detected green line as an
    anchor when possible.  Returning the calculated value here prevents the
    badge from bypassing the axis transform and creating a second scale.
    """
    current = _number(analysis.get("current_price"))
    if current is None:
        return detected_y
    return _price_y(float(current), price_min, price_max)


def _is_candle_colored_pixel(pixel: tuple[int, int, int, int]) -> bool:
    """Detect likely candle pixels while ignoring neutral grid/background tones."""
    r, g, b, a = pixel
    if a < 110:
        return False
    chroma = max(r, g, b) - min(r, g, b)
    if chroma < 18:
        return False
    brightness = (r + g + b) / 3.0
    if brightness < 20 or brightness > 246:
        return False
    return True



def _estimate_visible_candle_count(chart_image: Image.Image) -> int | None:
    """Estimate how many candles are visible in the uploaded screenshot.

    The estimate is intentionally simple: scan the chart area (excluding the
    right price axis) and count narrow clusters of colored columns.  This is
    used only to reject screenshots that are too zoomed-in, not for precise
    analysis.
    """
    width, height = chart_image.size
    if width < 120 or height < 120:
        return None

    left = max(4, int(width * 0.01))
    right = max(left + 20, int(width * 0.82))
    top = max(8, int(height * 0.04))
    bottom = min(height - 8, int(height * 0.96))
    pixels = chart_image.load()

    active_columns: list[bool] = []
    for x in range(left, right):
        colored = 0
        for y in range(top, bottom):
            if _is_candle_colored_pixel(pixels[x, y]):
                colored += 1
        active_columns.append(colored >= max(6, int((bottom - top) * 0.018)))

    if not any(active_columns):
        return None

    segments: list[int] = []
    run = 0
    for active in active_columns:
        if active:
            run += 1
        elif run:
            segments.append(run)
            run = 0
    if run:
        segments.append(run)

    if not segments:
        return None

    max_width = max(2, int((right - left) * 0.075))
    count = sum(1 for width_px in segments if 1 <= width_px <= max_width)
    return count or None



def _prepare_chart_background(
    chart_background_path: str | os.PathLike[str] | None,
) -> tuple[Image.Image | None, int | None, int | None]:
    """Fit the uploaded chart once, detect the green line, and estimate candle count."""
    if not chart_background_path:
        return None, None, None
    path = Path(chart_background_path)
    if not path.exists():
        return None, None, None

    left, top, right, bottom = CHART
    try:
        with Image.open(path) as chart_image:
            chart_rgba = chart_image.convert("RGBA")
            fitted = _fit_cover(chart_rgba, (right - left, bottom - top))
            detected_local_y = _detect_green_reference_line_y(fitted)
            visible_candles = _estimate_visible_candle_count(fitted)
    except Exception:  # pragma: no cover
        return None, None, None

    detected_absolute_y = None if detected_local_y is None else top + detected_local_y
    return fitted, detected_absolute_y, visible_candles


def _paste_prepared_chart_background(image: Image.Image, fitted: Image.Image) -> None:
    """Paste a previously fitted chart and add the readability overlay."""
    left, top, right, bottom = CHART

    image.alpha_composite(fitted, (left, top))

    # تعتيم خفيف حتى تبقى طبقات التحليل والملصقات أوضح فوق الشارت الأصلي،
    # مع تغطية أعلى وأسفل الصورة المرفوعة كما طلب المستخدم.
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rounded_rectangle((left, top, right, bottom), radius=6, fill=(0, 10, 26, 70))

    chart_h = bottom - top
    top_mask_h = max(26, int(chart_h * UPLOADED_BG_TOP_MASK_RATIO))
    bottom_mask_h = max(52, int(chart_h * UPLOADED_BG_BOTTOM_MASK_RATIO))
    d.rounded_rectangle((left + 1, top + 1, right - 1, top + top_mask_h), radius=6, fill=(2, 11, 25, 170))
    d.rounded_rectangle((left + 1, bottom - bottom_mask_h, right - 1, bottom - 1), radius=6, fill=(2, 11, 25, 188))
    d.rectangle((left, top, right, bottom), outline=(112, 133, 168, 165), width=1)
    image.alpha_composite(overlay)


def _paste_chart_background(
    image: Image.Image,
    chart_background_path: str | os.PathLike[str] | None,
) -> tuple[bool, int | None]:
    """Compatibility wrapper used by older callers/tests."""
    fitted, detected_absolute_y, _visible_candles = _prepare_chart_background(chart_background_path)
    if fitted is None:
        return False, None
    _paste_prepared_chart_background(image, fitted)
    return True, detected_absolute_y


def _draw_status(draw: ImageDraw.ImageDraw) -> None:
    # لا نرسم ساعة الجهاز أو البطارية حتى تبقى الصورة نظيفة مثل طلب المستخدم.
    draw.ellipse((31, 43, 79, 91), fill=(5, 35, 25, 255), outline=GREEN, width=2)
    draw.line((46, 67, 56, 77), fill=GREEN, width=4)
    draw.line((56, 77, 68, 55), fill=GREEN, width=4)
    _draw_rtl(draw, (128, 49), "اكتمل التحليل", F_SMALL_BOLD, GREEN, anchor="la")
    title_y = 40
    _draw_rtl(draw, (1019, title_y), "تحليل", F_TITLE, NAVY)
    arabic_width = _text_width(draw, "تحليل", F_TITLE)
    draw.text((1019 - arabic_width - 14, title_y), "SaleeM", font=F_TITLE_LATIN, fill=GOLD, anchor="ra")

def _draw_header(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    draw.rounded_rectangle(MAIN_CARD, radius=24, fill=(6, 17, 40, 255), outline=BORDER, width=1)
    draw.text((540, 188), "SaleeM - XAUUSD - M5", font=F_HEADER, fill=WHITE, anchor="ma")

    card_y1, card_y2 = 230, 385
    gap = 12
    card_w = (984 - gap * 3) // 4
    x_positions = [40 + i * (card_w + gap) for i in range(4)]
    cards = [(x, card_y1, x + card_w, card_y2) for x in x_positions]
    for rect in cards:
        draw.rounded_rectangle(rect, radius=17, fill=(4, 18, 45, 255), outline=BORDER, width=1)

    latest = (
        analysis.get("market_m5_latest_candle_time")
        or analysis.get("market_latest_candle_time")
        or analysis.get("market_data_fetched_at")
    )
    source_timezone = str(analysis.get("market_timezone") or "Asia/Muscat")
    update_time = _market_time_label(latest, source_timezone)
    count = len(analysis.get("candles") or [])
    current = _number(analysis.get("current_price"))
    direction = str(analysis.get("direction") or "غير واضح")

    # الأصل: عملة ذهبية بسيطة وواضحة بدل شكل سبائك غير مقنع.
    _draw_rtl(draw, (cards[0][2] - 18, card_y1 + 31), "الأصل والرمز", F_LABEL, (205, 217, 236, 255))
    coin_x, coin_y = cards[0][0] + 58, card_y1 + 101
    draw.ellipse((coin_x - 35, coin_y - 35, coin_x + 35, coin_y + 35), fill=(235, 164, 20, 255), outline=(255, 206, 82, 255), width=3)
    draw.ellipse((coin_x - 27, coin_y - 27, coin_x + 27, coin_y + 27), outline=(183, 111, 0, 255), width=2)
    draw.text((coin_x, coin_y - 6), "Au", font=F_CARD_LATIN, fill=(74, 41, 0, 255), anchor="mm")
    draw.text((coin_x, coin_y + 19), "79", font=F_AXIS, fill=(89, 50, 0, 255), anchor="mm")
    draw.text((cards[0][2] - 18, card_y1 + 91), "XAUUSD", font=F_CARD_LATIN, fill=ORANGE, anchor="ra")
    draw.text((cards[0][2] - 18, card_y1 + 121), "GOLD / USD", font=F_STATUS, fill=ORANGE, anchor="ra")

    # الوقت: آخر شمعة M5 الفعلية، مع تحويل العرض إلى توقيت مسقط.
    _draw_rtl(draw, (cards[1][2] - 18, card_y1 + 31), "آخر شمعة", F_LABEL, (205, 217, 236, 255))
    draw.ellipse((cards[1][0] + 27, card_y1 + 25, cards[1][0] + 57, card_y1 + 55), outline=(210, 220, 240, 255), width=2)
    draw.line((cards[1][0] + 42, card_y1 + 31, cards[1][0] + 42, card_y1 + 41), fill=(210, 220, 240, 255), width=2)
    draw.line((cards[1][0] + 42, card_y1 + 41, cards[1][0] + 50, card_y1 + 45), fill=(210, 220, 240, 255), width=2)
    draw.text(((cards[1][0] + cards[1][2]) // 2, card_y1 + 99), update_time, font=F_CARD, fill=WHITE, anchor="mm")
    _draw_rtl(draw, ((cards[1][0] + cards[1][2]) // 2, card_y1 + 128), "بتوقيت مسقط", F_SMALL, MUTED, anchor="mm")

    _draw_rtl(draw, (cards[2][2] - 18, card_y1 + 31), "الشموع المعروضة", F_LABEL, (205, 217, 236, 255))
    draw.text(((cards[2][0] + cards[2][2]) // 2, card_y1 + 106), _rtl(f"{count} شمعة"), font=F_CARD, fill=WHITE, anchor="mm")

    _draw_rtl(draw, (cards[3][2] - 18, card_y1 + 31), "السعر الحالي", F_LABEL, (205, 217, 236, 255))
    trend_color = GREEN if direction == "صاعد" else (RED if direction == "هابط" else GOLD)
    icon_x = cards[3][0] + 58
    icon_y = card_y1 + 98
    if direction == "صاعد":
        draw.line((icon_x - 25, icon_y + 15, icon_x - 8, icon_y - 5, icon_x + 6, icon_y + 2, icon_x + 25, icon_y - 22), fill=trend_color, width=3)
        draw.polygon([(icon_x + 25, icon_y - 22), (icon_x + 13, icon_y - 19), (icon_x + 23, icon_y - 9)], fill=trend_color)
    elif direction == "هابط":
        draw.line((icon_x - 25, icon_y - 18, icon_x - 8, icon_y + 2, icon_x + 6, icon_y - 5, icon_x + 25, icon_y + 20), fill=trend_color, width=3)
        draw.polygon([(icon_x + 25, icon_y + 20), (icon_x + 13, icon_y + 17), (icon_x + 23, icon_y + 7)], fill=trend_color)
    else:
        draw.line((icon_x - 25, icon_y, icon_x + 25, icon_y), fill=trend_color, width=3)
    draw.text((cards[3][2] - 18, card_y1 + 106), _fmt_price(current), font=F_CARD, fill=trend_color, anchor="rm")


def _draw_signal(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    direction = str(analysis.get("direction") or "غير واضح")
    state = str(analysis.get("draw_mode") or "watch")
    buy = int(analysis.get("buy_probability") or 50)
    sell = int(analysis.get("sell_probability") or 50)

    x, y = 42, 410
    badge_w, badge_h, gap = 178, 64, 12
    buy_active = state != "watch" and direction == "صاعد"
    sell_active = state != "watch" and direction == "هابط"

    buy_fill = GREEN if buy_active else (8, 42, 42, 255)
    sell_fill = RED if sell_active else (47, 24, 36, 255)
    draw.rounded_rectangle((x, y, x + badge_w, y + badge_h), radius=12, fill=buy_fill, outline=GREEN, width=2)
    sell_x = x + badge_w + gap
    draw.rounded_rectangle((sell_x, y, sell_x + badge_w, y + badge_h), radius=12, fill=sell_fill, outline=RED, width=2)
    buy_text_color = WHITE if buy_active else GREEN
    sell_text_color = WHITE if sell_active else RED
    _draw_rtl(draw, (x + badge_w - 20, y + badge_h // 2), "شراء", F_CARD, buy_text_color, anchor="rm")
    draw.text((x + 22, y + badge_h // 2), f"{buy}%", font=F_PERCENT, fill=buy_text_color, anchor="lm")
    _draw_rtl(draw, (sell_x + badge_w - 20, y + badge_h // 2), "بيع", F_CARD, sell_text_color, anchor="rm")
    draw.text((sell_x + 22, y + badge_h // 2), f"{sell}%", font=F_PERCENT, fill=sell_text_color, anchor="lm")

    state_text = {"confirmed": "مؤكد", "conditional": "مشروط", "watch": "مراقبة"}.get(state, "مراقبة")
    state_color = GREEN if state == "confirmed" else (ORANGE if state == "conditional" else GOLD)
    state_x = x + badge_w * 2 + gap + 22
    state_w = max(142, _text_width(draw, state_text, F_CARD, rtl=True) + 54)
    draw.rounded_rectangle((state_x, y + 5, state_x + state_w, y + badge_h - 5), radius=12, fill=(16, 25, 43, 255), outline=state_color, width=2)
    _draw_rtl(draw, (state_x + state_w // 2, y + badge_h // 2), state_text, F_CARD, state_color, anchor="mm")


def _nice_step(span: float, target_ticks: int = 8) -> float:
    raw = max(0.0001, span / max(2, target_ticks - 1))
    exponent = math.floor(math.log10(raw))
    fraction = raw / (10 ** exponent)
    if fraction <= 1:
        nice = 1
    elif fraction <= 2:
        nice = 2
    elif fraction <= 2.5:
        nice = 2.5
    elif fraction <= 5:
        nice = 5
    else:
        nice = 10
    return nice * (10 ** exponent)


def _axis_values(price_min: float, price_max: float) -> list[float]:
    step = _nice_step(price_max - price_min, 8)
    first = math.ceil(price_min / step) * step
    values: list[float] = []
    value = first
    while value <= price_max + step * 0.05 and len(values) < 12:
        values.append(round(value, 6))
        value += step
    if len(values) < 5:
        values = [price_min + i * (price_max - price_min) / 6 for i in range(7)]
    return values


def _draw_input_top_price(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> tuple[int, int, int, int] | None:
    """Fallback top-price badge when full source-axis labels are unavailable."""
    if _exact_image_axis_model(analysis) is not None or _image_axis_step_model(analysis) is not None:
        return None
    image_high = _number(analysis.get("image_price_high"))
    if image_high is None:
        return None

    left, top, right, bottom = CHART
    axis_left = right + 10
    axis_right = CHART_CARD[2] - 14
    box = (axis_left, top + 4, axis_right, top + 30)
    draw.rounded_rectangle(box, radius=6, fill=(12, 27, 54, 255), outline=(92, 112, 156, 215), width=1)
    draw.text(((axis_left + axis_right) // 2, (box[1] + box[3]) // 2), _fmt_price(image_high), font=F_TRADE_SMALL_LATIN, fill=(224, 234, 248, 255), anchor="mm")
    return box



def _right_axis_labels(analysis: dict[str, Any], price_min: float, price_max: float) -> list[tuple[str, float, int]]:
    exact_labels = _exact_source_axis_labels(analysis, price_min, price_max)
    if len(exact_labels) >= 3:
        return exact_labels

    model = analysis.get("_calibrated_axis_model")
    if not isinstance(model, dict):
        model = _image_axis_step_model(analysis)
    if model is not None:
        # Fall back to a reconstructed arithmetic sequence when the chart did
        # not provide enough readable labels to mirror directly.
        top_price = float(model["top_price"])
        top_ratio = float(model["top_ratio"])
        price_step = float(model["price_step"])
        ratio_step = float(model["ratio_step"])
        intervals = int(model["intervals"])
        bottom_ratio = float(model["bottom_ratio"])

        labels: list[tuple[str, float, int]] = []
        for index in range(intervals + 1):
            y_ratio = top_ratio + index * ratio_step
            if y_ratio > bottom_ratio + max(0.018, ratio_step * 0.22):
                break
            price = top_price - index * price_step
            y = _price_y(price, price_min, price_max)
            labels.append(("axis", round(price, 2), y))
        if len(labels) >= 3:
            return labels

    key_prices = _image_key_prices(analysis)
    if key_prices is not None:
        image_high, current, image_low = key_prices
        return [
            ("high", image_high, _price_y(image_high, price_min, price_max)),
            ("current", current, _price_y(current, price_min, price_max)),
            ("low", image_low, _price_y(image_low, price_min, price_max)),
        ]
    return [("axis", price, _price_y(price, price_min, price_max)) for price in _axis_values(price_min, price_max)]



def _draw_right_price_axis(
    draw: ImageDraw.ImageDraw,
    analysis: dict[str, Any],
    price_min: float,
    price_max: float,
    *,
    current_y: int | None = None,
    top_price_box: tuple[int, int, int, int] | None = None,
) -> None:
    labels = [item for item in _right_axis_labels(analysis, price_min, price_max) if item[0] not in {"high", "current"}]
    exact_mode = len(_exact_source_axis_labels(analysis)) >= 3
    for index, (role, price, y) in enumerate(labels):
        if not (CHART[1] + 8 <= y <= CHART[3] - 6):
            continue
        draw_y = y
        if not exact_mode:
            # In reconstructed mode we can cosmetically hug the axis edges.
            if index == 0:
                top_anchor = CHART[1] + 6
                if top_price_box is not None:
                    top_anchor = max(top_anchor, top_price_box[3] + 6)
                draw_y = top_anchor
            elif index == len(labels) - 1:
                bottom_anchor = CHART[3] - 4
                draw_y = bottom_anchor
        if current_y is not None and abs(draw_y - current_y) < 22:
            continue
        if top_price_box is not None and top_price_box[1] - 4 <= draw_y <= top_price_box[3] + 4:
            continue
        axis_text = _fmt_axis_price(price) if role == "axis" else _fmt_price(price)
        draw.text((PRICE_AXIS_X + 12, draw_y), axis_text, font=F_AXIS, fill=(194, 207, 229, 255), anchor="lm")



def _draw_grid(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float, *, background_mode: bool = False) -> None:
    draw.rounded_rectangle(CHART_CARD, radius=21, fill=(6, 17, 40, 255), outline=BORDER, width=1)
    left, top, right, bottom = CHART

    # شريط مستقل لمحور السعر حتى تبقى الأرقام بعيدة عن ملصقات الصفقة.
    draw.rounded_rectangle((right + 8, top - 10, CHART_CARD[2] - 12, bottom + 10), radius=12, fill=(5, 15, 34, 255))
    _draw_rtl(draw, (CHART_CARD[2] - 26, top - 34), "محور السعر", F_SMALL, MUTED)
    draw.text((left, top - 34), "XAUUSD · M5", font=F_STATUS, fill=(208, 220, 240, 255), anchor="la")

    for role, price, y in _right_axis_labels(analysis, price_min, price_max):
        if not background_mode and CHART[1] + 4 <= y <= CHART[3] - 4:
            draw.line((left, y, right, y), fill=GRID, width=1)

    # لا توجد خطوط عمودية حتى لا يزدحم الرسم.
    draw.rectangle((left, top, right, bottom), outline=(77, 96, 131, 175), width=1)

def _draw_candles(draw: ImageDraw.ImageDraw, candles: list[dict[str, Any]], price_min: float, price_max: float) -> tuple[float, int]:
    left, top, right, bottom = CHART
    count = max(1, len(candles))
    # نترك مساحة يمين الشموع للسيناريو والأهداف مثل الصورة المرجعية.
    candle_right = int(left + (right - left) * 0.68)
    slot = (candle_right - left) / count
    body_width = max(6, min(14, int(slot * 0.58)))

    for index, candle in enumerate(candles):
        x = int(left + slot * (index + 0.5))
        open_y = _price_y(float(candle["open"]), price_min, price_max)
        close_y = _price_y(float(candle["close"]), price_min, price_max)
        high_y = _price_y(float(candle["high"]), price_min, price_max)
        low_y = _price_y(float(candle["low"]), price_min, price_max)
        bullish = float(candle["close"]) >= float(candle["open"])
        color = GREEN if bullish else RED
        draw.line((x, high_y, x, low_y), fill=color, width=2)
        y1, y2 = sorted((open_y, close_y))
        if y2 - y1 < 3:
            y2 = y1 + 3
        draw.rectangle((x - body_width // 2, y1, x + body_width // 2, y2), fill=color, outline=color)

    label_count = min(6, count)
    indexes = sorted(set(round(i * (count - 1) / max(1, label_count - 1)) for i in range(label_count)))
    for index in indexes:
        x = int(left + slot * (index + 0.5))
        draw.text((x, bottom + 66), _time_label(candles[index].get("time")), font=F_AXIS, fill=TEXT, anchor="ma")
    return slot, candle_right


def _detect_fvg(candles: list[dict[str, Any]]) -> list[tuple[int, float, float]]:
    zones: list[tuple[int, float, float]] = []
    for i in range(2, len(candles)):
        a, c = candles[i - 2], candles[i]
        if float(a["high"]) < float(c["low"]):
            zones.append((i, float(a["high"]), float(c["low"])))
        elif float(a["low"]) > float(c["high"]):
            zones.append((i, float(c["high"]), float(a["low"])))
    return zones[-1:]


def _detect_order_blocks(candles: list[dict[str, Any]]) -> list[tuple[int, float, float, int]]:
    if len(candles) < 5:
        return []
    bodies = [abs(float(c["close"]) - float(c["open"])) for c in candles]
    baseline = max(0.01, median(bodies))
    zones: list[tuple[int, float, float, int]] = []
    for i in range(1, len(candles)):
        prev, impulse = candles[i - 1], candles[i]
        body = abs(float(impulse["close"]) - float(impulse["open"]))
        prev_bull = float(prev["close"]) >= float(prev["open"])
        impulse_bull = float(impulse["close"]) >= float(impulse["open"])
        if body < baseline * 1.35 or prev_bull == impulse_bull:
            continue
        strength = min(100, int(58 + body / baseline * 12))
        zones.append((i - 1, float(prev["low"]), float(prev["high"]), strength))
    # إزالة المناطق المتقاربة جدًا.
    selected: list[tuple[int, float, float, int]] = []
    for zone in reversed(zones):
        center = (zone[1] + zone[2]) / 2
        if all(abs(center - (z[1] + z[2]) / 2) > max(0.25, abs(zone[2] - zone[1]) * 0.7) for z in selected):
            selected.append(zone)
        if len(selected) == 4:
            break
    return list(reversed(selected))


def _select_directional_order_block(
    analysis: dict[str, Any],
    candles: list[dict[str, Any]],
    focal_price: float,
    atr: float,
) -> tuple[int, float, float, int] | None:
    """اختيار Order Block ثانوي وعلى جهة الإبطال فقط.

    في الصعود يجب أن يكون أسفل السعر، وفي الهبوط أعلى السعر. لا نعرض منطقة
    مخالفة للاتجاه ولا نسمح لها أن تصبح العنصر البصري المسيطر.
    """
    direction = str(analysis.get("analysis_direction") or analysis.get("direction") or "غير واضح")
    if direction not in {"صاعد", "هابط"}:
        return None

    recent_floor = max(0, len(candles) - 16)
    max_distance = max(1.0, atr * 2.8)
    candidates: list[tuple[float, tuple[int, float, float, int]]] = []
    for zone in _detect_order_blocks(candles):
        index, low, high, strength = zone
        center = (low + high) / 2
        correct_side = center < focal_price if direction == "صاعد" else center > focal_price
        if not correct_side or index < recent_floor or strength < 78 or abs(center - focal_price) > max_distance:
            continue
        score = strength - abs(center - focal_price) * 14 + index * 0.12
        candidates.append((score, zone))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _draw_market_zones(image: Image.Image, draw: ImageDraw.ImageDraw, analysis: dict[str, Any], candles: list[dict[str, Any]], slot: float, candle_right: int, price_min: float, price_max: float) -> None:
    left, top, right, bottom = CHART
    if not candles or str(analysis.get("draw_mode") or "watch") == "watch":
        return

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    analysis_left = max(candle_right - 8, int(left + (right - left) * 0.64))
    zone_end = right - 8
    reference = float(candles[-1]["close"])
    entry = _number(analysis.get("entry"))
    focal_price = entry if entry is not None else reference
    atr = median([max(0.01, float(c["high"]) - float(c["low"])) for c in candles])
    max_distance = max(1.2, atr * 3.2)
    recent_floor = max(0, len(candles) - 16)

    # Order Block عنصر ثانوي فقط، وعلى جهة الإبطال المناسبة للاتجاه.
    selected_order_block = _select_directional_order_block(analysis, candles, focal_price, atr)
    if selected_order_block is not None:
        index, low, high, strength = selected_order_block
        if not (high < price_min or low > price_max):
            x1 = max(left + 170, int(left + slot * max(0, index - 0.4)))
            x2 = min(zone_end, max(x1 + 155, analysis_left + 95))
            y1, y2 = sorted((_price_y(high, price_min, price_max), _price_y(low, price_min, price_max)))
            if y2 - y1 < 28:
                mid = (y1 + y2) // 2
                y1, y2 = mid - 14, mid + 14
            ld.rounded_rectangle((x1, y1, x2, y2), radius=5, fill=(75, 99, 190, 36), outline=(100, 139, 255, 120), width=1)
            ld.text(((x1 + x2) // 2, (y1 + y2) // 2), "ORDER BLOCK", font=F_ZONE, fill=(185, 207, 255, 225), anchor="mm")

    # FVG: فجوة حديثة وقريبة من الدخول، ممتدة حتى منطقة التحليل.
    fvg_candidates: list[tuple[float, tuple[int, float, float]]] = []
    for zone in _detect_fvg(candles):
        index, low, high = zone
        center = (low + high) / 2
        if index < recent_floor or abs(center - focal_price) > max_distance:
            continue
        score = -abs(center - focal_price) + index * 0.02
        fvg_candidates.append((score, zone))
    fvg_candidates.sort(key=lambda item: item[0], reverse=True)

    if fvg_candidates:
        _, (index, low, high) = fvg_candidates[0]
        if not (high < price_min or low > price_max):
            x1 = max(left + 170, int(left + slot * max(0, index - 0.3)))
            x2 = min(zone_end, max(x1 + 150, analysis_left + 70))
            y1, y2 = sorted((_price_y(high, price_min, price_max), _price_y(low, price_min, price_max)))
            if y2 - y1 < 28:
                mid = (y1 + y2) // 2
                y1, y2 = mid - 14, mid + 14
            ld.rounded_rectangle((x1, y1, x2, y2), radius=5, fill=(244, 169, 62, 45), outline=(244, 169, 62, 165), width=2)
            ld.text(((x1 + x2) // 2, (y1 + y2) // 2), "FVG", font=F_ZONE, fill=(255, 214, 145, 255), anchor="mm")

    image.alpha_composite(layer)

def _draw_levels(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    left, top, right, bottom = CHART
    all_levels: list[tuple[str, int, dict[str, Any], float, int, tuple[int, int, int, int], str]] = []
    specs = (
        ("resistance_levels", PURPLE, "مقاومة"),
        ("support_levels", CYAN, "دعم"),
    )
    for key, color, name in specs:
        levels = list(analysis.get(key) or [])[:2]
        for rank, level in enumerate(levels, start=1):
            price = _number(level.get("price"))
            if price is None or not (price_min <= price <= price_max):
                continue
            all_levels.append((key, rank, level, price, _price_y(price, price_min, price_max), color, name))

    if _strict_axis_sync(analysis):
        positions = {f"{key}-{rank}": y for key, rank, _, _, y, _, _ in all_levels}
    else:
        positions = _spaced_positions(
            [(f"{key}-{rank}", y) for key, rank, _, _, y, _, _ in all_levels],
            min_gap=40,
        )
    for key, rank, level, price, exact_y, color, name in all_levels:
        strength = int(level.get("strength") or 50)
        source = str(level.get("source") or "market")
        y_label = positions.get(f"{key}-{rank}", exact_y)
        strength_text = "تقديري" if source == "projected" else _strength_name(strength)
        label = f"{name} {rank} | {_fmt_price(price)} | {strength_text}"
        rect = _rounded_label(
            draw,
            left + 8,
            y_label - 15,
            label,
            F_TRADE_SMALL,
            fill=(10, 23, 45, 248),
            outline=color,
            text_fill=color,
            padding_x=8,
            padding_y=4,
            radius=7,
        )
        line_start = min(right - 20, rect[2] + 8)
        # الدعم والمقاومة خطوط متصلة وواضحة كما طلب المستخدم.
        draw.line((line_start, exact_y, right - 5, exact_y), fill=color, width=max(2, _strength_width(strength)))
        if abs(y_label - exact_y) > 3:
            draw.line((rect[2], y_label, line_start, exact_y), fill=color, width=1)

def _spaced_positions(items: list[tuple[str, int]], min_gap: int = 43) -> dict[str, int]:
    ordered = sorted(items, key=lambda item: item[1])
    positions: dict[str, int] = {}
    previous: int | None = None
    for key, exact in ordered:
        y = exact if previous is None else max(exact, previous + min_gap)
        positions[key] = y
        previous = y
    max_y = CHART[3] - 24
    overflow = max(positions.values(), default=max_y) - max_y
    if overflow > 0:
        positions = {key: y - overflow for key, y in positions.items()}
    min_y = CHART[1] + 10
    underflow = min_y - min(positions.values(), default=min_y)
    if underflow > 0:
        positions = {key: y + underflow for key, y in positions.items()}
    return positions


def _draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color, *, dashed: bool = False) -> None:
    sx, sy = start
    ex, ey = end
    mx = int(sx + (ex - sx) * 0.48)
    # انحناءة خفيفة في اتجاه الهدف بدل خط ضخم يغطي الشموع.
    my = int(sy + (ey - sy) * 0.30)
    if dashed:
        _dash_line(draw, (sx, sy), (mx, my), color, width=4, dash=10, gap=7)
        _dash_line(draw, (mx, my), (ex, ey), color, width=4, dash=10, gap=7)
    else:
        draw.line([(sx, sy), (mx, my), (ex, ey)], fill=color, width=4, joint="curve")
    angle = math.atan2(ey - my, ex - mx)
    size = 17
    left_head = (ex - size * math.cos(angle - math.pi / 6), ey - size * math.sin(angle - math.pi / 6))
    right_head = (ex - size * math.cos(angle + math.pi / 6), ey - size * math.sin(angle + math.pi / 6))
    draw.polygon([(ex, ey), left_head, right_head], fill=color)

def _draw_current_price(
    draw: ImageDraw.ImageDraw,
    analysis: dict[str, Any],
    price_min: float,
    price_max: float,
    *,
    y_override: int | None = None,
    top_price_box: tuple[int, int, int, int] | None = None,
) -> None:
    current = _number(analysis.get("current_price"))
    left, top, right, bottom = CHART
    if y_override is None:
        if current is None or not (price_min <= current <= price_max):
            return
        y = _price_y(current, price_min, price_max)
    else:
        y = int(max(top + 1, min(bottom - 1, y_override)))
        if current is None:
            # نحتفظ بالخط حتى لو تعذر الرقم، لكن بدون صندوق سعر فارغ.
            draw.line((left, y, right, y), fill=(38, 201, 128, 170), width=2)
            return

    draw.line((left, y, right, y), fill=(38, 201, 128, 170), width=2)
    axis_left = right + 10
    axis_right = CHART_CARD[2] - 14
    draw.rounded_rectangle((axis_left, y - 15, axis_right, y + 15), radius=6, fill=(9, 133, 75, 255), outline=TP_GREEN, width=1)
    draw.text(((axis_left + axis_right) // 2, y), _fmt_price(current), font=F_TRADE_SMALL_LATIN, fill=WHITE, anchor="mm")


def _draw_trade(image: Image.Image, draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float, candle_right: int) -> None:
    left, top, right, bottom = CHART
    draw_mode = str(analysis.get("draw_mode") or "watch")
    direction = str(analysis.get("analysis_direction") or analysis.get("direction") or "غير واضح")
    if draw_mode == "watch" or direction not in {"صاعد", "هابط"}:
        return

    entry = _number(analysis.get("entry"))
    stop = _number(analysis.get("stop_loss"))
    targets = [_number(analysis.get(key)) for key in ("target_1", "target_2", "target_3")]
    targets = [value for value in targets if value is not None]
    if entry is None or not _is_visible_price(entry, price_min, price_max):
        return

    entry_y = _price_y(entry, price_min, price_max)
    stop_visible = _is_visible_price(stop, price_min, price_max)
    stop_y = _price_y(stop, price_min, price_max) if stop_visible and stop is not None else None
    visible_targets = [(target, _price_y(target, price_min, price_max)) for target in targets if _is_visible_price(target, price_min, price_max)]
    target_ys = [item[1] for item in visible_targets]
    # Shift the analysis zones a bit left so the chart-side axis remains clear,
    # and reserve the right strip for the price cards.
    zone_left = min(right - 210, max(candle_right + 8, int(left + (right - left) * 0.60)))
    zone_right = right - 28

    # لا نشترط بقاء جميع الرسومات داخل الشاشة؛ كل عنصر خارج محور الأسعار يختفي.
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    if target_ys:
        far_target_y = target_ys[-1]
        ld.rounded_rectangle(
            (zone_left, min(entry_y, far_target_y), zone_right, max(entry_y, far_target_y)),
            radius=7,
            fill=TP_GREEN_FILL,
        )
    if stop_y is not None:
        ld.rounded_rectangle(
            (zone_left, min(entry_y, stop_y), zone_right, max(entry_y, stop_y)),
            radius=7,
            fill=RED_FILL,
        )
    image.alpha_composite(layer)

    # خطوط الصفقة المتاحة فقط.
    draw.line((zone_left, entry_y, zone_right, entry_y), fill=ORANGE, width=2)
    if stop_y is not None:
        draw.line((zone_left, stop_y, zone_right, stop_y), fill=RED, width=2)
    for _, y in visible_targets:
        draw.line((zone_left, y, zone_right, y), fill=TP_GREEN, width=2)

    label_items = [("entry", entry_y)]
    if stop_y is not None:
        label_items.append(("stop", stop_y))
    label_items.extend((f"tp{i}", y) for i, (_, y) in enumerate(visible_targets, start=1))
    if _strict_axis_sync(analysis):
        positions = {key: y for key, y in label_items}
    else:
        positions = _spaced_positions(label_items, min_gap=37)

    labels: list[tuple[str, int, int, str, Any, bool]] = [
        ("entry", entry_y, positions["entry"], f"دخول | {_fmt_price(entry)}", ORANGE, True),
    ]
    if stop is not None and stop_y is not None:
        labels.append(("stop", stop_y, positions["stop"], f"وقف | {_fmt_price(stop)}", RED, True))
    for index, (target, exact_y) in enumerate(visible_targets, start=1):
        labels.append((f"tp{index}", exact_y, positions[f"tp{index}"], f"TP{index} | {_fmt_price(target)}", TP_GREEN, False))

    axis_card_right = CHART_CARD[2] - 16
    chart_card_right = zone_right - 5
    for key, exact_y, shown_y, text, color, rtl in labels:
        if key.startswith("tp"):
            fill = (5, 62, 38, 248)
            text_fill = TP_GREEN
        elif key == "entry":
            fill = (112, 63, 10, 248)
            text_fill = WHITE
        else:
            fill = (112, 24, 35, 248)
            text_fill = WHITE
        # Keep all trade cards, including TP targets, inside the right price-axis strip.
        label_x = axis_card_right
        rect = _rounded_label(
            draw,
            label_x,
            shown_y - 14,
            text,
            F_TRADE_SMALL if rtl else F_TRADE_SMALL_LATIN,
            fill=fill,
            outline=color,
            text_fill=text_fill,
            rtl=rtl,
            align_right=True,
            padding_x=7,
            padding_y=4,
            radius=7,
        )
        if abs(shown_y - exact_y) > 3:
            elbow_x = rect[0] - 7
            draw.line((elbow_x, exact_y, elbow_x, shown_y), fill=color, width=1)
            draw.line((elbow_x, shown_y, rect[0], shown_y), fill=color, width=1)

    # السهم يظهر فقط إذا بقي ضمن المحور هدف مرئي أو مساحة حركة واضحة.
    if visible_targets:
        end_y = visible_targets[-1][1]
    elif stop_y is not None:
        end_y = max(top + 28, min(bottom - 28, entry_y - 90 if direction == "صاعد" else entry_y + 90))
    else:
        return
    end_y = max(top + 28, min(bottom - 28, end_y))
    start_point = (zone_left + 18, entry_y - 5 if direction == "صاعد" else entry_y + 5)
    end_x = max(start_point[0] + 62, zone_right - 122)
    end_point = (end_x, end_y)
    path_color = TP_GREEN if direction == "صاعد" else RED
    _draw_arrow(draw, start_point, end_point, path_color, dashed=draw_mode == "conditional")

def _parse_session_range(name: str, default: str) -> tuple[int, int]:
    raw = os.getenv(name, default).strip()
    try:
        start_text, end_text = raw.split("-", 1)
        sh, sm = [int(part) for part in start_text.split(":", 1)]
        eh, em = [int(part) for part in end_text.split(":", 1)]
        return (sh % 24) * 60 + sm % 60, (eh % 24) * 60 + em % 60
    except (ValueError, IndexError):
        start_text, end_text = default.split("-", 1)
        sh, sm = [int(part) for part in start_text.split(":", 1)]
        eh, em = [int(part) for part in end_text.split(":", 1)]
        return sh * 60 + sm, (eh % 24) * 60 + em


def _session_active(minute: int, start: int, end: int) -> bool:
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


def _draw_sessions(
    draw: ImageDraw.ImageDraw,
    candles: list[dict[str, Any]],
    slot: float,
    source_timezone: str | None = None,
) -> None:
    """رسم شرائط جلسات مرتبطة فعليًا بكل شمعة على محور الزمن."""
    if not candles or os.getenv("SHOW_MARKET_SESSIONS", "true").strip().lower() in {"0", "false", "no"}:
        return

    left, top, right, bottom = CHART
    parsed_times = [_localized_datetime(candle.get("time"), source_timezone) for candle in candles]
    if not any(value is not None for value in parsed_times):
        return

    sessions = [
        ("آسيا", _parse_session_range("ASIAN_SESSION", "04:00-12:00"), (197, 139, 45, 255)),
        ("لندن", _parse_session_range("LONDON_SESSION", "11:00-19:00"), (62, 128, 245, 255)),
        ("نيويورك", _parse_session_range("NEW_YORK_SESSION", "16:00-00:00"), (139, 92, 246, 255)),
    ]
    row_height = 12
    row_gap = 3
    base_y = bottom + 12

    for row, (label, (start, end), color) in enumerate(sessions):
        y1 = base_y + row * (row_height + row_gap)
        y2 = y1 + row_height
        segment_start: int | None = None
        for index in range(len(candles) + 1):
            active = False
            if index < len(candles) and parsed_times[index] is not None:
                local = parsed_times[index]
                minute = local.hour * 60 + local.minute
                active = _session_active(minute, start, end)
            if active and segment_start is None:
                segment_start = index
            if (not active or index == len(candles)) and segment_start is not None:
                x1 = int(left + slot * segment_start)
                x2 = int(left + slot * index)
                x2 = min(right, max(x1 + 3, x2))
                fill = (color[0], color[1], color[2], 86)
                draw.rounded_rectangle((x1, y1, x2, y2), radius=3, fill=fill, outline=color, width=1)
                if x2 - x1 >= 62:
                    _draw_rtl(draw, ((x1 + x2) // 2, (y1 + y2) // 2 - 1), label, F_SESSION, WHITE, anchor="mm")
                segment_start = None


def _pattern_name(analysis: dict[str, Any]) -> str:
    name = str(analysis.get("pattern_type") or "لا يوجد")
    return {"قمتان": "نموذج M", "قاعان": "نموذج W"}.get(name, name)


def _note_row(draw: ImageDraw.ImageDraw, y: int, label: str, value: str, dot_color, *, ltr_value: bool = False) -> None:
    left, top, right, bottom = NOTES
    mid_x = right - 235
    draw.line((left + 20, y + 46, right - 20, y + 46), fill=(45, 67, 102, 255), width=1)
    draw.line((mid_x, y - 2, mid_x, y + 46), fill=(40, 60, 92, 255), width=1)
    draw.ellipse((right - 45, y + 12, right - 31, y + 26), fill=dot_color)
    _draw_rtl(draw, (right - 66, y + 2), label, F_NOTE_BOLD, WHITE)
    max_width = mid_x - left - 42
    if ltr_value:
        fitted = _fit_text(draw, value, F_NOTE_MIXED, max_width, rtl=False)
        draw.text((mid_x - 18, y + 2), fitted, font=F_NOTE_MIXED, fill=(232, 238, 249, 255), anchor="ra")
    else:
        fitted = _fit_mixed_rtl(draw, value, F_NOTE_MIXED, max_width)
        _draw_mixed_rtl(draw, (mid_x - 18, y + 2), fitted, F_NOTE_MIXED, (232, 238, 249, 255), anchor="ra")

def _draw_notes(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    left, top, right, bottom = NOTES
    note_fill = (8, 25, 58, 255)
    note_border = (224, 170, 52, 255)
    draw.rounded_rectangle(NOTES, radius=20, fill=note_fill, outline=note_border, width=2)
    _draw_rtl(draw, (right - 72, top + 38), "ملاحظات التحليل", F_NOTE_TITLE, (245, 184, 48, 255))
    draw.rounded_rectangle((right - 47, top + 20, right - 19, top + 53), radius=4, outline=note_border, width=2)
    draw.rounded_rectangle((right - 41, top + 15, right - 25, top + 24), radius=3, outline=note_border, width=2)
    draw.line((left + 24, top + 70, right - 24, top + 70), fill=note_border, width=1)

    direction = str(analysis.get("direction") or "غير واضح")
    probability = int(analysis.get("trade_probability") or 50)
    draw_mode = str(analysis.get("draw_mode") or "watch")
    pattern = _pattern_name(analysis)
    pattern_confidence = int(analysis.get("pattern_confidence") or 0)
    confirmation = str(analysis.get("confirmation") or "انتظار تأكيد واضح")
    stop = _number(analysis.get("stop_loss"))
    scenario = str(analysis.get("scenario") or "مراقبة مستوى التفعيل")
    targets = [_number(analysis.get(key)) for key in ("target_1", "target_2", "target_3")]

    state_suffix = "مراقبة" if draw_mode == "watch" else ("مؤكد" if draw_mode == "confirmed" else "مشروط")
    direction_value = f"{direction} - احتمال {probability}٪ - {state_suffix}"
    pattern_value = f"{pattern} - ثقة {pattern_confidence}٪" if pattern != "لا يوجد" else "لا يوجد نموذج مكتمل"
    stop_value = _fmt_price(stop) if stop is not None and draw_mode != "watch" else "—"
    target_value = " | ".join(f"TP{i}: {_fmt_price(value)}" for i, value in enumerate(targets, start=1) if value is not None) if draw_mode != "watch" else "بانتظار وضوح السيناريو"

    rows = [
        ("الاتجاه:", direction_value, GREEN if direction == "صاعد" else (RED if direction == "هابط" else GOLD), False),
        ("النمط:", pattern_value, BLUE, False),
        ("شرط الدخول:", confirmation, GREEN if draw_mode != "watch" else GOLD, False),
        ("وقف:", stop_value, RED, True),
        ("الأهداف:", target_value, GREEN, draw_mode != "watch"),
        ("أقرب سيناريو:", scenario, ORANGE, False),
    ]
    draw.rounded_rectangle((left + 12, top + 82, right - 12, bottom - 28), radius=14, outline=(52, 77, 112, 255), width=1)
    y = top + 92
    for label, value, color, ltr_value in rows:
        _note_row(draw, y, label, value, color, ltr_value=ltr_value)
        y += 54
    _draw_rtl(draw, (right - 24, bottom - 36), "تحليل فني تعليمي، وليس توصية استثمارية.", F_DISCLAIMER, (184, 197, 219, 255))

def _draw_buttons(draw: ImageDraw.ImageDraw) -> None:
    y1, y2 = 1762, 1870
    draw.rounded_rectangle((42, y1, 468, y2), radius=17, fill=(66, 78, 99, 255))
    draw.rounded_rectangle((484, y1, 1038, y2), radius=17, fill=GREEN)
    _draw_rtl(draw, (300, (y1 + y2) // 2), "مشاركة", F_BUTTON, WHITE, anchor="mm")
    _draw_rtl(draw, (770, (y1 + y2) // 2), "حفظ في الاستديو", F_BUTTON, WHITE, anchor="mm")
    # رموز مشاركة وحفظ بسيطة.
    draw.line((213, 1819, 213, 1788), fill=WHITE, width=3)
    draw.line((200, 1800, 213, 1787, 226, 1800), fill=WHITE, width=3)
    draw.rectangle((194, 1807, 232, 1840), outline=WHITE, width=3)
    draw.line((914, 1788, 914, 1825), fill=WHITE, width=3)
    draw.line((901, 1813, 914, 1826, 927, 1813), fill=WHITE, width=3)
    draw.line((896, 1837, 932, 1837), fill=WHITE, width=3)


def render_result(analysis: dict[str, Any], chart_background_path: str | os.PathLike[str] | None = None) -> bytes:
    image = Image.new("RGBA", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    # لا نضع ترويسة أو بطاقات معلومات فوق الشارت في صورة النتيجة؛
    # الشارت يملأ الصفحة من الأعلى حتى صندوق الملاحظات السفلي.
    candles = analysis.get("candles") or []
    price_min, price_max = _price_range(analysis)
    prepared_background, detected_green_line_y, _visible_candles = _prepare_chart_background(chart_background_path)
    using_chart_background = prepared_background is not None
    current_reference_y = detected_green_line_y
    if current_reference_y is None:
        current_reference_y = _analysis_current_reference_y(analysis)

    # محور الصورة هو المرجع الأول. أعلى رقم كامل والرقم الذي يليه مباشرة
    # يحددان الخطوة السعرية والمسافة الرأسية، بينما أدنى رقم كامل يحدد نهاية
    # السلسلة. جميع الشموع والخطوط تستخدم التحويل الحسابي نفسه.
    dynamic_axis_range = _dynamic_image_axis_range(analysis, current_reference_y)
    if dynamic_axis_range is not None:
        price_min, price_max = dynamic_axis_range
        current_reference_y = _axis_checked_current_reference_y(
            analysis,
            price_min,
            price_max,
            current_reference_y,
        )

    _draw_grid(draw, analysis, price_min, price_max, background_mode=using_chart_background)
    top_price_box = _draw_input_top_price(draw, analysis)
    if prepared_background is not None:
        _paste_prepared_chart_background(image, prepared_background)
        draw = ImageDraw.Draw(image)
    count = max(1, len(candles))
    candle_right = int(CHART[0] + (CHART[2] - CHART[0]) * 0.68)
    slot = (candle_right - CHART[0]) / count
    _draw_market_zones(image, draw, analysis, candles, slot, candle_right, price_min, price_max)
    draw = ImageDraw.Draw(image)
    if not using_chart_background:
        _draw_candles(draw, candles, price_min, price_max)
    current_value = _number(analysis.get("current_price"))
    current_axis_y = None
    if current_value is not None:
        current_axis_y = int(max(CHART[1] + 1, min(CHART[3] - 1, current_reference_y if current_reference_y is not None else _price_y(current_value, price_min, price_max))))
    _draw_right_price_axis(draw, analysis, price_min, price_max, current_y=current_axis_y, top_price_box=top_price_box)
    _draw_current_price(draw, analysis, price_min, price_max, y_override=current_reference_y, top_price_box=top_price_box)
    _draw_levels(draw, analysis, price_min, price_max)
    _draw_trade(image, draw, analysis, price_min, price_max, candle_right)
    draw = ImageDraw.Draw(image)
    _draw_sessions(draw, candles, slot, str(analysis.get("market_timezone") or "Asia/Muscat"))
    _draw_notes(draw, analysis)

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()
