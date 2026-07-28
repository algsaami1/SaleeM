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
WIDTH = 1320
HEIGHT = 2868

# لوحة ألوان قريبة من التصميم المرجعي.
BG = (3, 17, 35, 255)
WHITE = (255, 255, 255, 255)
NAVY = (235, 241, 255, 255)
TEXT = (226, 235, 247, 255)
MUTED = (155, 169, 196, 255)
BORDER = (66, 85, 123, 255)
GRID = (93, 122, 160, 64)
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

# ألوان المستويات الجديدة: المقاومة أحمر غامق والدعم أزرق غامق.
# لون البطاقة والخط واحد حتى تكون القراءة البصرية مباشرة وواضحة.
RESISTANCE_DARK = (139, 28, 38, 255)
RESISTANCE_FILL = (102, 22, 31, 245)
SUPPORT_DARK = (18, 65, 145, 255)
SUPPORT_FILL = (13, 48, 110, 245)

# بطاقات محور الأسعار اليميني لها نفس أبعاد وشكل بطاقة السعر الحالي.
AXIS_PRICE_CARD_WIDTH = 190
AXIS_PRICE_CARD_HEIGHT = 56
AXIS_PRICE_CARD_RADIUS = 5

# اختلاف بطاقات التنفيذ يكون باللون فقط؛ الحجم والشكل والموضع الأفقي ثابتة.
ENTRY_CARD = (34, 104, 220, 255)
STOP_CARD = (177, 34, 45, 255)
CANCEL_CARD = (205, 99, 19, 255)
TP1_CARD = (37, 166, 106, 255)
TP2_CARD = (20, 142, 84, 255)
TP3_CARD = (8, 112, 64, 255)

# تخطيط مطابق لصورة الآيفون المرفوعة: نحافظ على مقاس الصورة الكاملة
# 1320×2868، ونُظهر داخلها الجزء المحدد 1111×2243 بالبكسل نفسه.
# الجزء الظاهر يأخذ أقصى يمين المصدر (بما فيه محور الأسعار الأصلي)،
# ويُحذف تلقائيًا 209 بكسل من اليسار وقرابة 312 بكسل من الأعلى والأسفل.
# المساحة اليمنى المتبقية 209 بكسل مخصصة للمحور الإضافي، وباقي المساحات سوداء.
CHART_CARD = (0, 320, 1320, 2563)
CHART = (0, 320, 930, 2563)
PRICE_AXIS_X = 1125
NOTES = (0, 2868, 0, 2868)
TOP_SUMMARY_PANEL = (10, 12, WIDTH - 10, CHART[1] - 14)
BOTTOM_SUMMARY_PANEL = (10, CHART_CARD[3] + 12, WIDTH - 10, HEIGHT - 12)
BOTTOM_CARDS_Y1 = CHART_CARD[3] + 26
BOTTOM_CARDS_Y2 = HEIGHT - 174
# شموع السيناريو لها عمود ثابت، لكن مواضعها الرأسية تتبع الأسعار الحقيقية.
PROJECTION_X1 = 675
PROJECTION_X2 = 902
SOURCE_VISIBLE_WIDTH = 1111
SOURCE_VISIBLE_HEIGHT = 2243
SOURCE_AXIS_VISIBLE_WIDTH = SOURCE_VISIBLE_WIDTH - CHART[2]
SALEEM_AXIS_EXTRA_WIDTH = WIDTH - SOURCE_VISIBLE_WIDTH
DUPLICATED_AXIS_LEFT_PADDING = 8
DUPLICATED_AXIS_RIGHT_PADDING = 8
AXIS_VISUAL_LABEL_COUNT = 5
AXIS_VISUAL_BACKGROUND = (4, 21, 43, 255)
# طلب المستخدم: إظهار كل أرقام المحور الإضافي بالأسود الخالص.
AXIS_VISUAL_TEXT = (0, 0, 0, 255)
TOP_PRICE_MIN_GAP_RATIO = 0.14
TOP_PRICE_TRIGGER_ATR = 6.0
TOP_PRICE_TOP_PADDING_RATIO = 0.02

# النتيجة يجب أن تبقى متطابقة على مختلف أجهزة الآيفون. لذلك لا نعتمد
# على قص ثابت بالبكسل من الصورة المرفوعة، بل نستخرج الجزء المطلوب بنِسَب
# مشتقة من صورة مرجعية، ثم نعيد تطبيعه إلى نفس نافذة العرض النهائية.
REFERENCE_SCREENSHOT_WIDTH = 1320
REFERENCE_SCREENSHOT_HEIGHT = 2868
VISIBLE_WIDTH_RATIO = SOURCE_VISIBLE_WIDTH / REFERENCE_SCREENSHOT_WIDTH
VISIBLE_HEIGHT_RATIO = SOURCE_VISIBLE_HEIGHT / REFERENCE_SCREENSHOT_HEIGHT
FULL_SCREEN_ASPECT = REFERENCE_SCREENSHOT_WIDTH / REFERENCE_SCREENSHOT_HEIGHT
VISIBLE_VIEWPORT_ASPECT = SOURCE_VISIBLE_WIDTH / SOURCE_VISIBLE_HEIGHT

# إخفاء لوحة التداول العلوية التي قد تحتوي على BUY/SELL وحقل اللوت.
# يُكتشف الشريط الأزرق داخل أعلى الصورة، ثم تُغطى كامل المنطقة الأفقية
# باللون الأسود حتى لا تبقى أجزاء بيضاء مثل خانة 0.01.
TOP_CONTROL_SCAN_RATIO = 0.18
TOP_CONTROL_MIN_BLUE_RATIO = 0.035
TOP_CONTROL_PADDING_RATIO = 0.008

# قاعدة الإظهار النهائية: نقص قليلًا من أعلى وأسفل ويسار الجزء الملتقط،
# ثم نضعه مزاحًا لليسار داخل الكانفس حتى تتوافر مساحة المحور اليميني الإضافي.


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
F_TOP_LABEL = _font(21, True)
F_TOP_VALUE = _font(29, True)
F_TOP_VALUE_SMALL = _font(24, True)
F_TOP_VALUE_COMPACT = _font(21, True)
F_TOP_VALUE_TINY = _font(18, True)
F_TOP_VALUE_LATIN = _font(29, True, True)
F_TRADE_CARD_LABEL = _font(18, True, True)
F_TRADE_CARD_PRICE = _font(29, True, True)
F_TRADE_AXIS_LABEL = _font(18, True, True)
F_TRADE_AXIS_PRICE = _font(25, True, True)
F_LEVEL_CARD = _font(20, True, True)
F_AXIS_EDGE = _font(17, False, True)
F_SESSION_NAME = _font(23, True, True)
F_SESSION_TIME = _font(17, False, True)


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


def _fmt_card_price(value: Any) -> str:
    """Compact one-decimal price used by all right-axis analysis cards."""
    number = _number(value)
    if number is None:
        return "—"
    return f"{number:.1f}"


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
    """Return a visibly progressive line width for a 0-100 strength score."""
    score = max(0, min(100, int(strength)))
    if score >= 90:
        return 6
    if score >= 80:
        return 5
    if score >= 65:
        return 4
    if score >= 50:
        return 3
    return 2


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
    if draw_mode in {"conditional", "confirmed"}:
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

    anchor = _number(analysis.get("entry")) if draw_mode in {"conditional", "confirmed"} else current
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
    active_trade = draw_mode in {"conditional", "confirmed"} and direction in {"صاعد", "هابط"}
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


def _source_background_box() -> tuple[int, int, int, int]:
    """Exact native-size viewport kept from the uploaded iPhone screenshot."""
    return 0, CHART[1], SOURCE_VISIBLE_WIDTH, CHART[1] + SOURCE_VISIBLE_HEIGHT


def _saleem_axis_box() -> tuple[int, int, int, int]:
    """Black/right strip reserved for the additional synchronized axis."""
    return SOURCE_VISIBLE_WIDTH, CHART[1], WIDTH, CHART[3]


def _background_visible_box() -> tuple[int, int, int, int]:
    return _source_background_box()


def _background_axis_shift() -> int:
    return SALEEM_AXIS_EXTRA_WIDTH


def _fit_cover(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Return one canonical chart viewport without distorting it.

    The rule is intentionally simple and stable:
    - keep the chart and its original right price axis together,
    - crop the needed area from the full screenshot using ratios,
    - do not apply a second crop and do not stretch the result.

    When scaling is needed for another device size, use one uniform scale only,
    then right-align and vertically center the crop so the price axis is never
    removed.
    """
    target_w, target_h = size
    source_w, source_h = source.size
    if source_w <= 1 or source_h <= 1:
        return Image.new("RGBA", size, (0, 0, 0, 255))

    source_aspect = source_w / source_h

    if abs(source_aspect - VISIBLE_VIEWPORT_ASPECT) / VISIBLE_VIEWPORT_ASPECT <= 0.05:
        viewport = source.convert("RGBA")
    elif abs(source_aspect - FULL_SCREEN_ASPECT) / FULL_SCREEN_ASPECT <= 0.08:
        crop_w = min(source_w, max(1, int(round(source_w * VISIBLE_WIDTH_RATIO))))
        crop_h = min(source_h, max(1, int(round(source_h * VISIBLE_HEIGHT_RATIO))))
        crop_left = max(0, source_w - crop_w)
        crop_top = max(0, (source_h - crop_h) // 2)
        viewport = source.crop((crop_left, crop_top, crop_left + crop_w, crop_top + crop_h)).convert("RGBA")
    else:
        crop_w = min(source_w, int(round(source_h * VISIBLE_VIEWPORT_ASPECT)))
        crop_h = int(round(crop_w / VISIBLE_VIEWPORT_ASPECT))
        if crop_h > source_h:
            crop_h = source_h
            crop_w = int(round(crop_h * VISIBLE_VIEWPORT_ASPECT))
        crop_left = max(0, source_w - crop_w)
        crop_top = max(0, (source_h - crop_h) // 2)
        viewport = source.crop((crop_left, crop_top, crop_left + crop_w, crop_top + crop_h)).convert("RGBA")

    if viewport.size == (target_w, target_h):
        return viewport

    # Uniform cover scaling: no stretching and no internal black bars. Any
    # tiny excess is removed from the left and equally from top/bottom, keeping
    # the original right price axis intact.
    scale = max(target_w / viewport.width, target_h / viewport.height)
    scaled_w = max(target_w, int(round(viewport.width * scale)))
    scaled_h = max(target_h, int(round(viewport.height * scale)))
    resized = viewport.resize((scaled_w, scaled_h), resample=Image.Resampling.LANCZOS)
    crop_left = max(0, scaled_w - target_w)
    crop_top = max(0, (scaled_h - target_h) // 2)
    return resized.crop((crop_left, crop_top, crop_left + target_w, crop_top + target_h))


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



def _resize_cover_right_aligned(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Uniformly fill ``size`` while preserving the original right price axis.

    The chart is never stretched independently on one axis. Any horizontal
    excess is removed from the left, because the right-side broker axis is the
    authoritative visual reference.
    """
    target_w, target_h = size
    if source.width <= 1 or source.height <= 1:
        return Image.new("RGBA", size, (0, 0, 0, 255))
    scale = max(target_w / source.width, target_h / source.height)
    scaled_w = max(target_w, int(round(source.width * scale)))
    scaled_h = max(target_h, int(round(source.height * scale)))
    resized = source.convert("RGBA").resize((scaled_w, scaled_h), resample=Image.Resampling.LANCZOS)
    crop_left = max(0, scaled_w - target_w)
    crop_top = max(0, (scaled_h - target_h) // 2)
    return resized.crop((crop_left, crop_top, crop_left + target_w, crop_top + target_h))


def _detect_neutral_top_trade_controls_band(prepared: Image.Image) -> tuple[int, int] | None:
    """Detect light or dark one-click-trading toolbars at the viewport top.

    MetaTrader may render the BUY/SELL/lot row in blue/red, black/gray, or
    white/gray. Colour-only detection therefore misses many real screenshots.
    This detector looks for a strong horizontal change point near the top and
    verifies that the region above it has a different brightness/texture from
    the chart body below it. Ordinary chart grid lines are rejected because
    they do not change the whole top region.
    """
    image = prepared.convert("RGBA")
    width, height = image.size
    if width < 180 or height < 300:
        return None

    scan_bottom = min(height - 20, max(170, int(height * 0.20)))
    x_end = max(80, int(width * 0.84))
    step_x = 2 if width >= 700 else 1
    pixels = image.load()

    row_mean: list[float] = []
    row_texture: list[float] = []
    vertical_change: list[float] = [0.0]
    previous: list[float] | None = None

    for y in range(scan_bottom):
        values: list[float] = []
        texture_hits = 0
        last_value: float | None = None
        for x in range(0, x_end, step_x):
            r, g, b, a = pixels[x, y]
            value = (float(r) + float(g) + float(b)) / 3.0 if a >= 80 else 0.0
            values.append(value)
            if last_value is not None and abs(value - last_value) >= 28.0:
                texture_hits += 1
            last_value = value
        count = max(1, len(values))
        row_mean.append(sum(values) / count)
        row_texture.append(texture_hits / count)
        if previous is not None:
            vertical_change.append(sum(abs(a - b) for a, b in zip(values, previous)) / count)
        previous = values

    # Smooth the row-to-row change so text edges do not beat the toolbar's
    # complete lower boundary.
    radius = 2
    smoothed: list[float] = []
    for index in range(len(vertical_change)):
        start = max(0, index - radius)
        end = min(len(vertical_change), index + radius + 1)
        smoothed.append(sum(vertical_change[start:end]) / max(1, end - start))

    candidate_start = max(36, int(height * 0.018))
    candidate_end = min(scan_bottom - 70, int(height * 0.18))
    if candidate_end <= candidate_start:
        return None
    valid_boundaries: list[tuple[int, float, float]] = []
    for boundary in range(candidate_start, candidate_end):
        strength = smoothed[boundary]
        if strength < 14.0:
            continue
        before_start = max(0, boundary - 76)
        before_end = max(before_start + 1, boundary - 6)
        after_start = min(scan_bottom - 1, boundary + 6)
        after_end = min(scan_bottom, boundary + 96)
        if after_end <= after_start:
            continue

        before_mean = sum(row_mean[before_start:before_end]) / max(1, before_end - before_start)
        after_mean = sum(row_mean[after_start:after_end]) / max(1, after_end - after_start)
        before_texture = sum(row_texture[before_start:before_end]) / max(1, before_end - before_start)
        after_texture = sum(row_texture[after_start:after_end]) / max(1, after_end - after_start)
        brightness_gap = abs(before_mean - after_mean)
        texture_separation = before_texture >= after_texture * 1.45 + 0.003
        if brightness_gap >= 8.0 or texture_separation:
            valid_boundaries.append((boundary, strength, brightness_gap))

    if not valid_boundaries:
        return None

    # The strongest edge may be an internal divider between the lot field and
    # BUY/SELL cells. The actual chart begins after the *last* qualified edge
    # of the toolbar, so choose the lowest valid boundary in the top region.
    boundary = max(item[0] for item in valid_boundaries)
    padding = max(5, int(height * 0.0035))
    return 0, min(height, boundary + padding)


def _remove_top_trade_controls_by_crop(prepared: Image.Image) -> tuple[Image.Image, tuple[int, int] | None]:
    """Remove the broker toolbar by cropping, not by painting over the chart.

    Cropping is essential: painting the row leaves a large dead strip and makes
    the candles appear compressed toward the bottom. The remaining chart and
    its original price axis are uniformly enlarged together, so price geometry
    remains synchronized.
    """
    band = _detect_top_trade_controls_band(prepared)
    if band is None:
        return prepared, None
    top, bottom = band
    if top > int(prepared.height * 0.04) or bottom < 24 or bottom > int(prepared.height * 0.24):
        return prepared, None
    remaining = prepared.crop((0, bottom, prepared.width, prepared.height))
    if remaining.height < int(prepared.height * 0.68):
        return prepared, None
    return _resize_cover_right_aligned(remaining, prepared.size), band


def prepare_chart_viewport_image(
    chart_background_path: str | os.PathLike[str] | None,
) -> tuple[Image.Image | None, dict[str, Any]]:
    """Return a clean canonical chart+axis viewport for geometry and rendering."""
    meta: dict[str, Any] = {
        "chart_viewport_prepared": False,
        "top_trade_controls_removed": False,
    }
    if not chart_background_path:
        return None, meta
    path = Path(chart_background_path)
    if not path.exists():
        return None, meta

    visible_left, visible_top, visible_right, visible_bottom = _source_background_box()
    visible_w = visible_right - visible_left
    visible_h = visible_bottom - visible_top
    try:
        with Image.open(path) as chart_image:
            prepared = _fit_cover(chart_image.convert("RGBA"), (visible_w, visible_h))
        prepared, removed_band = _remove_top_trade_controls_by_crop(prepared)
    except Exception:  # pragma: no cover
        return None, meta

    meta.update({
        "chart_viewport_prepared": True,
        "chart_viewport_size": [visible_w, visible_h],
        "top_trade_controls_removed": removed_band is not None,
        "top_trade_controls_band": list(removed_band) if removed_band is not None else None,
    })
    return prepared, meta


def _prepare_chart_background(
    chart_background_path: str | os.PathLike[str] | None,
) -> tuple[Image.Image | None, int | None, int | None]:
    """Extract a clean 1111×2243 chart viewport with its original price axis."""
    prepared, _meta = prepare_chart_viewport_image(chart_background_path)
    if prepared is None:
        return None, None, None

    visible_top = _source_background_box()[1]
    try:
        detected_local_y = _detect_green_reference_line_y(prepared)
        visible_candles = _estimate_visible_candle_count(prepared)
    except Exception:  # pragma: no cover
        return None, None, None

    detected_absolute_y = None if detected_local_y is None else visible_top + detected_local_y
    return prepared, detected_absolute_y, visible_candles


def _is_broker_trade_panel_pixel(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, a = pixel
    if a < 120:
        return False
    chroma = max(r, g, b) - min(r, g, b)
    if chroma < 58:
        return False
    blue_panel = b >= 135 and b >= r + 42 and b >= g + 16
    red_panel = r >= 145 and r >= g + 38 and r >= b + 28
    return blue_panel or red_panel


def _detect_top_trade_controls_band(prepared: Image.Image) -> tuple[int, int] | None:
    """Detect blue or red BUY/SELL/lot toolbars near the source-chart top."""
    width, height = prepared.size
    if width < 120 or height < 160:
        return None

    scan_bottom = max(32, int(height * TOP_CONTROL_SCAN_RATIO))
    step_x = 2 if width >= 700 else 1
    min_colored = max(6, int((width / step_x) * TOP_CONTROL_MIN_BLUE_RATIO))
    pixels = prepared.load()
    active_rows: list[int] = []
    for y in range(scan_bottom):
        colored_count = 0
        for x in range(0, width, step_x):
            if _is_broker_trade_panel_pixel(pixels[x, y]):
                colored_count += 1
        if colored_count >= min_colored:
            active_rows.append(y)

    if not active_rows:
        return _detect_neutral_top_trade_controls_band(prepared)

    bands: list[list[int]] = []
    for y in active_rows:
        if not bands or y > bands[-1][-1] + 2:
            bands.append([y])
        else:
            bands[-1].append(y)
    band = max(bands, key=len)
    if len(band) < max(3, int(height * 0.004)):
        return _detect_neutral_top_trade_controls_band(prepared)

    padding = max(8, int(height * TOP_CONTROL_PADDING_RATIO))
    top = max(0, band[0] - padding)
    bottom = min(height, band[-1] + padding + 1)
    return top, bottom


def _hide_top_trade_controls(prepared: Image.Image) -> Image.Image:
    """Hide blue BUY/SELL boxes and the lot field as one complete row."""
    band = _detect_top_trade_controls_band(prepared)
    if band is None:
        return prepared
    cleaned = prepared.copy()
    draw = ImageDraw.Draw(cleaned)
    top, bottom = band
    draw.rectangle((0, top, cleaned.width, bottom), fill=BG)
    return cleaned


def _copy_source_axis_to_right_margin(image: Image.Image, prepared: Image.Image) -> None:
    """Duplicate the uploaded price column into the extra right margin.

    This follows the user's preferred rule exactly: instead of rebuilding a new
    synthetic price ladder, copy the screenshot's own right price column and
    shift it a few pixels to the right.  That makes both columns share the same
    glyph positions, current-price badge, and spacing by construction.
    """
    axis_left, axis_top, axis_right, axis_bottom = _saleem_axis_box()
    target_w = max(1, axis_right - axis_left - DUPLICATED_AXIS_LEFT_PADDING - DUPLICATED_AXIS_RIGHT_PADDING)
    target_h = axis_bottom - axis_top
    if prepared.width < 24 or prepared.height < 24 or target_w < 24 or target_h < 24:
        return

    source_strip_w = min(prepared.width, max(24, SOURCE_AXIS_VISIBLE_WIDTH))
    source_left = max(0, prepared.width - source_strip_w)
    source_strip = prepared.crop((source_left, 0, prepared.width, prepared.height)).convert('RGBA')

    if source_strip.size != (target_w, target_h):
        source_strip = source_strip.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)

    dest_x = axis_left + DUPLICATED_AXIS_LEFT_PADDING
    image.alpha_composite(source_strip, (dest_x, axis_top))


def _paste_prepared_chart_background(image: Image.Image, prepared: Image.Image) -> None:
    """Paste chart+source axis after hiding broker trade controls."""
    visible_left, visible_top, visible_right, visible_bottom = _source_background_box()
    cleaned = _hide_top_trade_controls(prepared)
    image.alpha_composite(cleaned, (visible_left, visible_top))

    # The source image's own axis remains visible in the final part.
    # We then duplicate that same axis strip into the extra right margin with
    # only a very small horizontal gap, so both columns remain perfectly synced.
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    axis_left, axis_top, axis_right, axis_bottom = _saleem_axis_box()
    d.rectangle((axis_left, axis_top, axis_right, axis_bottom), fill=(3, 12, 29, 255))
    d.line((visible_right - 1, visible_top, visible_right - 1, visible_bottom), fill=(83, 105, 145, 220), width=2)
    image.alpha_composite(overlay)

    _copy_source_axis_to_right_margin(image, cleaned)

    edge_overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    e = ImageDraw.Draw(edge_overlay)
    e.line((axis_left - 1, axis_top, axis_left - 1, axis_bottom), fill=(83, 105, 145, 165), width=1)
    e.line((axis_right - 1, axis_top, axis_right - 1, axis_bottom), fill=(83, 105, 145, 180), width=1)
    image.alpha_composite(edge_overlay)


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

def _frame_match_count(analysis: dict[str, Any]) -> int:
    direction = str(analysis.get("direction") or "غير واضح")
    frames = analysis.get("frame_directions") or {}
    if direction in {"صاعد", "هابط"} and isinstance(frames, dict):
        count = sum(
            1
            for timeframe in ("H4", "H1", "M15", "M5")
            if str((frames.get(timeframe) or {}).get("direction") or "") == direction
        )
        if count:
            return max(0, min(4, count))
    alignment = int(analysis.get("frame_alignment") or 0)
    return max(0, min(4, int(round(alignment / 25))))


def _active_session_label(analysis: dict[str, Any]) -> str:
    latest = (
        analysis.get("market_m5_latest_candle_time")
        or analysis.get("market_latest_candle_time")
        or analysis.get("market_data_fetched_at")
    )
    localized = _localized_datetime(latest, str(analysis.get("market_timezone") or "Asia/Muscat"))
    if localized is None:
        return "—"
    minute = localized.hour * 60 + localized.minute
    asia = _session_active(minute, *_parse_session_range("ASIAN_SESSION", "04:00-12:00"))
    london = _session_active(minute, *_parse_session_range("LONDON_SESSION", "11:00-19:00"))
    new_york = _session_active(minute, *_parse_session_range("NEW_YORK_SESSION", "16:00-00:00"))
    if london and new_york:
        return "تداخل"
    if new_york:
        return "نيويورك"
    if london:
        return "لندن"
    if asia:
        return "آسيا"
    return "هادئة"


def _header_pattern_lines(pattern: str) -> list[str]:
    """Return at most two compact Arabic lines for the pattern card."""
    normalized = " ".join(str(pattern or "").split())
    aliases = {
        "كسر وإعادة اختبار": ["كسر", "إعادة اختبار"],
        "كسر وإعادة الاختبار": ["كسر", "إعادة اختبار"],
        "الرأس والكتفين": ["رأس", "وكتفين"],
        "الرأس والكتفين المعكوس": ["رأس وكتفين", "معكوس"],
    }
    if normalized in aliases:
        return aliases[normalized]
    if not normalized or normalized in {"لا يوجد", "—", "-"}:
        return ["غير مكتمل"]
    if len(normalized) <= 12:
        return [normalized]
    words = normalized.split()
    if len(words) >= 2:
        midpoint = max(1, len(words) // 2)
        first = " ".join(words[:midpoint])
        second = " ".join(words[midpoint:])
        return [first, second]
    return [normalized]


def _summary_value_font(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    max_width: int,
    *,
    compact: bool = False,
):
    """Choose the largest summary-card font that keeps every line inside."""
    candidates = (
        [F_TOP_VALUE_SMALL, F_TOP_VALUE_COMPACT, F_TOP_VALUE_TINY]
        if compact or len(lines) > 1
        else [F_TOP_VALUE, F_TOP_VALUE_SMALL, F_TOP_VALUE_COMPACT, F_TOP_VALUE_TINY]
    )
    for font in candidates:
        if all(_text_width(draw, line, font, rtl=True) <= max_width for line in lines):
            return font
    return F_TOP_VALUE_TINY


def _draw_rtl_lines_centered(
    draw: ImageDraw.ImageDraw,
    center_x: int,
    center_y: int,
    lines: list[str],
    font,
    fill,
    *,
    spacing: int = 30,
) -> None:
    if not lines:
        return
    total = (len(lines) - 1) * spacing
    start_y = center_y - total // 2
    for index, line in enumerate(lines):
        _draw_rtl(draw, (center_x, start_y + index * spacing), line, font, fill, anchor="mm")


def _analysis_state(analysis: dict[str, Any]) -> tuple[str, tuple[int, int, int, int]]:
    state = str(analysis.get("draw_mode") or "watch")
    value = {
        "confirmed": "مؤكد",
        "conditional": "مشروط",
        "watch": "مراقبة",
        "inactive": "السوق مغلق",
    }.get(state, "مراقبة")
    color = GREEN if state == "confirmed" else (GOLD if state in {"conditional", "inactive"} else BLUE)
    return value, color


def _nearest_zone_label(analysis: dict[str, Any]) -> tuple[str, tuple[int, int, int, int]]:
    current = _number(analysis.get("current_price"))
    if current is None:
        return "مراقبة", BLUE

    nearest_support = None
    nearest_resistance = None
    for item in analysis.get("support_levels") or []:
        value = _number(item.get("price")) if isinstance(item, dict) else None
        if value is not None and value <= current:
            distance = current - value
            if nearest_support is None or distance < nearest_support:
                nearest_support = distance
    for item in analysis.get("resistance_levels") or []:
        value = _number(item.get("price")) if isinstance(item, dict) else None
        if value is not None and value >= current:
            distance = value - current
            if nearest_resistance is None or distance < nearest_resistance:
                nearest_resistance = distance

    if nearest_support is None and nearest_resistance is None:
        return "منتصف", CYAN
    if nearest_resistance is None or (nearest_support is not None and nearest_support <= nearest_resistance):
        return "دعم", CYAN
    return "مقاومة", ORANGE


def _behavior_label(analysis: dict[str, Any]) -> tuple[str, tuple[int, int, int, int]]:
    kind = str(analysis.get("entry_kind") or "مراقبة")
    mapping = {
        "إعادة اختبار": ("ارتداد", CYAN),
        "اختراق": ("اختراق", BLUE),
        "مباشر": ("اندفاع", GREEN),
        "مراقبة": ("تذبذب", BLUE),
    }
    return mapping.get(kind, ("مراقبة", BLUE))


def _momentum_label(analysis: dict[str, Any]) -> tuple[str, tuple[int, int, int, int]]:
    if str(analysis.get("draw_mode") or "watch") == "inactive":
        return "متوقف", GOLD
    candles = analysis.get("candles") or []
    probability = int(analysis.get("trade_probability") or 50)
    if len(candles) >= 5:
        recent = candles[-5:]
        bodies = []
        ranges = []
        signed = 0.0
        for candle in recent:
            open_ = _number(candle.get("open"))
            close = _number(candle.get("close"))
            high = _number(candle.get("high"))
            low = _number(candle.get("low"))
            if None in (open_, close, high, low):
                continue
            body = abs(close - open_)
            span = max(0.01, high - low)
            bodies.append(body)
            ranges.append(span)
            signed += close - open_
        if bodies and ranges:
            body_ratio = sum(bodies) / sum(ranges)
            directional_ratio = abs(signed) / max(0.01, sum(ranges))
            if probability >= 72 and body_ratio >= 0.48 and directional_ratio >= 0.22:
                return "قوي", GREEN
            if probability < 58 or body_ratio < 0.28:
                return "ضعيف", RED
    if probability >= 72:
        return "قوي", GREEN
    if probability < 58:
        return "ضعيف", RED
    return "متوسط", GOLD


def _candle_shape_label(analysis: dict[str, Any]) -> tuple[str, tuple[int, int, int, int]]:
    candles = analysis.get("candles") or []
    if not candles:
        return "غير واضح", BLUE
    last = candles[-1]
    open_ = _number(last.get("open"))
    close = _number(last.get("close"))
    high = _number(last.get("high"))
    low = _number(last.get("low"))
    if None in (open_, close, high, low):
        return "غير واضح", BLUE
    span = max(0.01, high - low)
    body = abs(close - open_)
    upper = high - max(open_, close)
    lower = min(open_, close) - low
    bullish = close >= open_

    if len(candles) >= 2:
        prev = candles[-2]
        prev_open = _number(prev.get("open"))
        prev_close = _number(prev.get("close"))
        if prev_open is not None and prev_close is not None:
            previous_bullish = prev_close >= prev_open
            previous_low_body = min(prev_open, prev_close)
            previous_high_body = max(prev_open, prev_close)
            current_low_body = min(open_, close)
            current_high_body = max(open_, close)
            if bullish != previous_bullish and current_low_body <= previous_low_body and current_high_body >= previous_high_body:
                return "ابتلاعية", GREEN if bullish else RED

    if body / span <= 0.16:
        return "دوجي", GOLD
    if lower >= body * 1.8 and upper <= max(body, span * 0.18):
        return "رفض صاعد", GREEN
    if upper >= body * 1.8 and lower <= max(body, span * 0.18):
        return "رفض هابط", RED
    return ("صاعدة", GREEN) if bullish else ("هابطة", RED)


def _close_label(analysis: dict[str, Any]) -> tuple[str, tuple[int, int, int, int]]:
    state = str(analysis.get("draw_mode") or "watch")
    if state == "inactive":
        return "غير محدث", GOLD
    direction = str(analysis.get("analysis_direction") or analysis.get("direction") or "غير واضح")
    level = _number(analysis.get("entry"))
    if state == "watch" or level is None or direction not in {"صاعد", "هابط"}:
        return "بانتظار", ORANGE
    side = "فوق" if direction == "صاعد" else "تحت"
    color = GREEN if state == "confirmed" else ORANGE
    return f"{side} {_fmt_card_price(level)}", color


def _breakout_label(analysis: dict[str, Any]) -> tuple[str, tuple[int, int, int, int]]:
    state = str(analysis.get("draw_mode") or "watch")
    kind = str(analysis.get("entry_kind") or "مراقبة")
    if state == "confirmed" and kind == "اختراق":
        return "مؤكد", GREEN
    if kind in {"اختراق", "إعادة اختبار"}:
        return "محتمل", CYAN
    return "بانتظار", ORANGE


def _rebound_label(analysis: dict[str, Any]) -> tuple[str, tuple[int, int, int, int]]:
    state = str(analysis.get("draw_mode") or "watch")
    kind = str(analysis.get("entry_kind") or "مراقبة")
    if state == "confirmed" and kind == "إعادة اختبار":
        return "مؤكد", GREEN
    if kind in {"إعادة اختبار", "مراقبة"}:
        return "محتمل", CYAN
    return "ضعيف", GOLD


def _draw_summary_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    label: str,
    values: list[str],
    color,
    *,
    latin_value: bool = False,
) -> None:
    x1, y1, x2, y2 = box
    # Individual cards deliberately use a calm charcoal border. The only gold
    # line is the outer frame around the complete upper/lower sections.
    draw.rounded_rectangle(
        box,
        radius=16,
        fill=(5, 10, 14, 255),
        outline=(62, 65, 62, 255),
        width=2,
    )
    _draw_rtl(draw, ((x1 + x2) // 2, y1 + 27), label, F_TOP_LABEL, (238, 240, 244, 255), anchor="mm")
    center_y = y1 + (76 if len(values) == 1 else 70)
    if latin_value:
        draw.text(((x1 + x2) // 2, center_y), values[0], font=F_TOP_VALUE_LATIN, fill=color, anchor="mm")
    else:
        safe_values = [str(value).strip() for value in values if str(value).strip()]
        if not safe_values:
            safe_values = ["غير مكتمل"] if label == "النموذج" else ["—"]
        font = _summary_value_font(
            draw,
            safe_values,
            max(20, x2 - x1 - 22),
            compact=label == "النموذج",
        )
        font_size = int(getattr(font, "size", 18))
        spacing = max(22, min(29, font_size + 4))
        _draw_rtl_lines_centered(draw, (x1 + x2) // 2, center_y, safe_values[:2], font, color, spacing=spacing)


def _draw_header(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    """Fixed two-row summary; chart coordinates never move between results."""
    draw.rounded_rectangle(
        TOP_SUMMARY_PANEL,
        radius=22,
        fill=(4, 8, 12, 255),
        outline=(220, 160, 45, 255),
        width=3,
    )

    state_value, state_color = _analysis_state(analysis)
    direction = str(analysis.get("direction") or "غير واضح")
    direction_color = GREEN if direction == "صاعد" else (RED if direction == "هابط" else BLUE)
    probability = max(0, min(100, int(analysis.get("trade_probability") or 50)))
    probability_text = "—" if str(analysis.get("draw_mode") or "watch") == "inactive" else f"{probability}%"
    pattern_lines = _header_pattern_lines(str(analysis.get("pattern_type") or "لا يوجد"))
    close_value, close_color = _close_label(analysis)
    zone_value, zone_color = _nearest_zone_label(analysis)
    behavior_value, behavior_color = _behavior_label(analysis)
    momentum_value, momentum_color = _momentum_label(analysis)
    candle_value, candle_color = _candle_shape_label(analysis)
    alignment = _frame_match_count(analysis)

    # Lists are left-to-right on the canvas; RTL reading begins at the right.
    rows = [
        [
            ("الاتجاه", [direction], direction_color, False),
            ("الحالة", [state_value], state_color, False),
            ("الإغلاق", [close_value], close_color, False),
            ("الاحتمال", [probability_text], GOLD, True),
            ("النموذج", pattern_lines, CYAN, False),
        ],
        [
            ("المنطقة", [zone_value], zone_color, False),
            ("السلوك", [behavior_value], behavior_color, False),
            ("الزخم", [momentum_value], momentum_color, False),
            ("التوافق", [f"{alignment}/4"], PURPLE, True),
            ("شكل شمعة", [candle_value], candle_color, False),
        ],
    ]

    margin_x = TOP_SUMMARY_PANEL[0] + 13
    gap_x = 13
    card_w = (TOP_SUMMARY_PANEL[2] - TOP_SUMMARY_PANEL[0] - 26 - gap_x * 4) // 5
    row_gap = 12
    y_top = TOP_SUMMARY_PANEL[1] + 14
    card_h = (TOP_SUMMARY_PANEL[3] - TOP_SUMMARY_PANEL[1] - 28 - row_gap) // 2
    for row_index, cards in enumerate(rows):
        y1 = y_top + row_index * (card_h + row_gap)
        y2 = y1 + card_h
        for index, (label, values, color, latin_value) in enumerate(cards):
            x1 = margin_x + index * (card_w + gap_x)
            x2 = x1 + card_w
            _draw_summary_card(draw, (x1, y1, x2, y2), label, values, color, latin_value=latin_value)


def _draw_signal(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    direction = str(analysis.get("direction") or "غير واضح")
    state = str(analysis.get("draw_mode") or "watch")
    buy = int(analysis.get("buy_probability") or 50)
    sell = int(analysis.get("sell_probability") or 50)

    x, y = 42, 410
    badge_w, badge_h, gap = 178, 64, 12
    buy_active = state in {"conditional", "confirmed"} and direction == "صاعد"
    sell_active = state in {"conditional", "confirmed"} and direction == "هابط"

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

    state_text = {
        "confirmed": "مؤكد",
        "conditional": "مشروط",
        "watch": "مراقبة",
        "inactive": "السوق مغلق",
    }.get(state, "مراقبة")
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

    _left, top, _right, _bottom = CHART
    axis_left, _axis_top, axis_right, _axis_bottom = _saleem_axis_box()
    box = (axis_left + 2, top + 4, axis_right - 2, top + 30)
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



def _select_visual_axis_labels(
    labels: list[tuple[str, float, int]],
    count: int = AXIS_VISUAL_LABEL_COUNT,
) -> list[tuple[str, float, int]]:
    """Choose evenly distributed labels for visual display only.

    All detected axis labels remain available to calibration and price-to-Y
    calculations. This helper only reduces the number painted in the final
    right margin.
    """
    usable = sorted(
        (item for item in labels if CHART[1] <= int(item[2]) <= CHART[3]),
        key=lambda item: int(item[2]),
    )
    if len(usable) <= count:
        return usable

    targets = [CHART[1] + (CHART[3] - CHART[1]) * index / (count - 1) for index in range(count)]
    selected: list[tuple[str, float, int]] = []
    used: set[int] = set()
    for target in targets:
        candidates = sorted(
            enumerate(usable),
            key=lambda pair: (abs(int(pair[1][2]) - target), pair[0]),
        )
        for idx, item in candidates:
            if idx not in used:
                used.add(idx)
                selected.append(item)
                break
    return sorted(selected, key=lambda item: int(item[2]))


def _paint_full_right_axis_black(
    draw: ImageDraw.ImageDraw,
    analysis: dict[str, Any],
    price_min: float,
    price_max: float,
) -> None:
    """Paint every calibrated right-axis price in pure black.

    This is a display-only change.  The complete source-label collection and
    the shared price-to-Y transform remain untouched, so levels, cards and all
    calculations keep exactly the same coordinates.
    """
    axis_left, axis_top, axis_right, axis_bottom = _saleem_axis_box()
    draw.rectangle(
        (axis_left + 2, axis_top + 2, axis_right - 2, axis_bottom - 2),
        fill=AXIS_VISUAL_BACKGROUND,
    )

    labels = _right_axis_labels(analysis, price_min, price_max)
    text_x = axis_right - DUPLICATED_AXIS_RIGHT_PADDING - 4
    half_text = 11
    for _role, price, exact_y in labels:
        if not (axis_top <= int(exact_y) <= axis_bottom):
            continue
        visual_y = max(axis_top + half_text, min(axis_bottom - half_text, int(exact_y)))
        draw.text(
            (text_x, visual_y),
            _fmt_axis_price(price),
            font=F_AXIS_EDGE,
            fill=AXIS_VISUAL_TEXT,
            anchor="rm",
        )

    draw.rectangle(
        (axis_left, axis_top, axis_right, axis_bottom),
        outline=(68, 94, 127, 220),
        width=2,
    )


def _draw_right_price_axis(
    draw: ImageDraw.ImageDraw,
    analysis: dict[str, Any],
    price_min: float,
    price_max: float,
    *,
    current_y: int | None = None,
    top_price_box: tuple[int, int, int, int] | None = None,
) -> None:
    """Paint the complete visual axis without changing calibration inputs."""
    _paint_full_right_axis_black(draw, analysis, price_min, price_max)


def _draw_grid(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float, *, background_mode: bool = False) -> None:
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=BG)
    left, top, right, bottom = CHART
    source_left, source_top, source_right, source_bottom = _source_background_box()
    axis_left, axis_top, axis_right, axis_bottom = _saleem_axis_box()

    if not background_mode:
        draw.rectangle((source_left, source_top, source_right, source_bottom), fill=(4, 19, 37, 255))
    draw.rectangle((axis_left, axis_top, axis_right, axis_bottom), fill=(4, 21, 43, 255))

    for _role, _price, y in _right_axis_labels(analysis, price_min, price_max):
        if not background_mode and CHART[1] + 4 <= y <= CHART[3] - 4:
            draw.line((left, y, right, y), fill=GRID, width=1)

    if not background_mode:
        # A quiet vertical grid is useful only on reconstructed charts.
        for index in range(1, 7):
            x = int(left + (right - left) * index / 7)
            draw.line((x, top, x, bottom), fill=(84, 111, 148, 42), width=1)

    draw.rectangle((source_left, source_top, source_right, source_bottom), outline=(68, 94, 127, 220), width=2)
    draw.rectangle((axis_left, axis_top, axis_right, axis_bottom), outline=(68, 94, 127, 220), width=2)


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
    # Keep all valid gaps.  The renderer chooses the nearest useful one rather
    # than hiding FVG merely because it is not among the last few candles.
    return zones


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
    max_distance = max(0.9, atr * 2.2)
    candidates: list[tuple[float, tuple[int, float, float, int]]] = []
    for zone in _detect_order_blocks(candles):
        index, low, high, strength = zone
        center = (low + high) / 2
        correct_side = center < focal_price if direction == "صاعد" else center > focal_price
        if not correct_side or index < recent_floor or strength < 82 or abs(center - focal_price) > max_distance:
            continue
        score = strength - abs(center - focal_price) * 14 + index * 0.12
        candidates.append((score, zone))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _nearest_detected_order_block(
    analysis: dict[str, Any],
    candles: list[dict[str, Any]],
    focal_price: float,
    atr: float,
) -> tuple[int, float, float, int] | None:
    """Return the best real OB while avoiding the old over-strict hiding.

    The directional strong/recent OB remains the first choice.  When it is not
    available, use the closest actually detected block from the supplied M5
    candles.  No synthetic OB is fabricated.
    """
    preferred = _select_directional_order_block(analysis, candles, focal_price, atr)
    if preferred is not None:
        return preferred

    direction = str(analysis.get("analysis_direction") or analysis.get("direction") or "غير واضح")
    candidates: list[tuple[float, tuple[int, float, float, int]]] = []
    for zone in _detect_order_blocks(candles):
        index, low, high, strength = zone
        center = (low + high) / 2
        side_bonus = 0.0
        if direction == "صاعد" and center <= focal_price:
            side_bonus = 18.0
        elif direction == "هابط" and center >= focal_price:
            side_bonus = 18.0
        recency_bonus = index * 0.35
        distance_penalty = abs(center - focal_price) / max(0.05, atr) * 7.0
        score = float(strength) + side_bonus + recency_bonus - distance_penalty
        candidates.append((score, zone))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _nearest_detected_fvg(
    candles: list[dict[str, Any]],
    focal_price: float,
    atr: float,
) -> tuple[int, float, float] | None:
    """Return the closest real FVG from all available candles."""
    candidates: list[tuple[float, tuple[int, float, float]]] = []
    for zone in _detect_fvg(candles):
        index, low, high = zone
        center = (low + high) / 2
        recency_bonus = index * 0.28
        distance_penalty = abs(center - focal_price) / max(0.05, atr) * 8.0
        size_bonus = min(16.0, abs(high - low) / max(0.05, atr) * 10.0)
        candidates.append((recency_bonus + size_bonus - distance_penalty, zone))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def detect_market_zone_presence(analysis: dict[str, Any]) -> dict[str, bool]:
    """Return the real OB/FVG zones detected by the same renderer logic.

    This small public helper keeps the text summary consistent with the chart:
    the result page mentions Order Block or FVG only when the renderer can
    actually detect that zone from the supplied M5 candles.
    """
    candles = [
        candle
        for candle in (analysis.get("candles") or [])
        if isinstance(candle, dict)
        and all(_number(candle.get(key)) is not None for key in ("open", "high", "low", "close"))
    ]
    if not candles:
        return {"order_block": False, "fvg": False}

    reference = float(_number(candles[-1].get("close")) or 0.0)
    entry = _number(analysis.get("entry"))
    focal_price = float(entry) if entry is not None else reference
    ranges = [
        max(0.01, float(candle["high"]) - float(candle["low"]))
        for candle in candles
    ]
    atr = median(ranges) if ranges else 0.01
    return {
        "order_block": _nearest_detected_order_block(analysis, candles, focal_price, atr) is not None,
        "fvg": _nearest_detected_fvg(candles, focal_price, atr) is not None,
    }


def _draw_market_zones(image: Image.Image, draw: ImageDraw.ImageDraw, analysis: dict[str, Any], candles: list[dict[str, Any]], slot: float, candle_right: int, price_min: float, price_max: float) -> None:
    left, top, right, bottom = CHART
    if not candles:
        return

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    zone_end = right - 18
    reference = float(candles[-1]["close"])
    entry = _number(analysis.get("entry"))
    focal_price = entry if entry is not None else reference
    atr = median([max(0.01, float(c["high"]) - float(c["low"])) for c in candles])
    # OB and FVG remain visible in watch, conditional, buy and sell results.
    # They extend horizontally so the user can read the complete zone easily.
    selected_order_block = _nearest_detected_order_block(analysis, candles, focal_price, atr)
    if selected_order_block is not None:
        index, low, high, strength = selected_order_block
        if not (high < price_min or low > price_max):
            x1 = max(left + 80, int(left + slot * max(0, index - 0.35)))
            x2 = zone_end
            if x2 - x1 < 360:
                x1 = max(left + 80, x2 - 360)
            y1, y2 = sorted((_price_y(high, price_min, price_max), _price_y(low, price_min, price_max)))
            center_y = (y1 + y2) // 2
            height = max(30, min(96, y2 - y1))
            y1, y2 = center_y - height // 2, center_y + height // 2
            ld.rounded_rectangle((x1, y1, x2, y2), radius=5, fill=(75, 99, 190, 34), outline=(100, 139, 255, 150), width=2)
            tag = (x2 - 66, y1 + 4, x2 - 8, min(y2 - 4, y1 + 32))
            ld.rounded_rectangle(tag, radius=4, fill=(45, 74, 154, 225))
            ld.text(((tag[0] + tag[2]) // 2, (tag[1] + tag[3]) // 2), "OB", font=F_ZONE, fill=(235, 242, 255, 255), anchor="mm")

    selected_fvg = _nearest_detected_fvg(candles, focal_price, atr)
    if selected_fvg is not None:
        index, low, high = selected_fvg
        if not (high < price_min or low > price_max):
            x1 = max(left + 80, int(left + slot * max(0, index - 0.25)))
            x2 = zone_end
            if x2 - x1 < 330:
                x1 = max(left + 80, x2 - 330)
            y1, y2 = sorted((_price_y(high, price_min, price_max), _price_y(low, price_min, price_max)))
            center_y = (y1 + y2) // 2
            height = max(28, min(76, y2 - y1))
            y1, y2 = center_y - height // 2, center_y + height // 2
            ld.rounded_rectangle((x1, y1, x2, y2), radius=5, fill=(244, 169, 62, 34), outline=(244, 169, 62, 150), width=2)
            tag = (x2 - 78, y1 + 4, x2 - 8, min(y2 - 4, y1 + 32))
            ld.rounded_rectangle(tag, radius=4, fill=(164, 94, 16, 225))
            ld.text(((tag[0] + tag[2]) // 2, (tag[1] + tag[3]) // 2), "FVG", font=F_ZONE, fill=(255, 239, 204, 255), anchor="mm")

    image.alpha_composite(layer)


def _level_display_items(
    analysis: dict[str, Any],
    price_min: float,
    price_max: float,
) -> list[tuple[str, float, int, tuple[int, int, int, int]]]:
    """Return support/resistance cards for the left side of the chart."""
    items: list[tuple[str, float, int, tuple[int, int, int, int]]] = []
    specs = (
        ("resistance_levels", "R", RESISTANCE_FILL),
        ("support_levels", "S", SUPPORT_FILL),
    )
    for key, prefix, card_color in specs:
        levels = list(analysis.get(key) or [])[:2]
        for rank, level in enumerate(levels, start=1):
            price = _number(level.get("price"))
            if price is None or not (price_min <= price <= price_max):
                continue
            strength = max(0, min(100, int(level.get("strength") or 50)))
            items.append(
                (
                    f"{prefix}{rank} {strength}%",
                    float(price),
                    _price_y(float(price), price_min, price_max),
                    card_color,
                )
            )
    return items


def _draw_levels(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    """Draw immutable true S/R lines; their cards are rendered on the left."""
    left, _top, right, _bottom = CHART
    specs = (
        ("resistance_levels", RESISTANCE_DARK),
        ("support_levels", SUPPORT_DARK),
    )
    for key, color in specs:
        levels = list(analysis.get(key) or [])[:2]
        for level in levels:
            price = _number(level.get("price"))
            if price is None or not (price_min <= price <= price_max):
                continue
            strength = max(0, min(100, int(level.get("strength") or 50)))
            exact_y = _price_y(float(price), price_min, price_max)
            # The true level never moves.  Only its axis card may be displaced.
            draw.line(
                (left + 18, exact_y, right - 3, exact_y),
                fill=color,
                width=_strength_width(strength),
            )

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


def _projection_closes(entry: float, targets: list[float]) -> list[float]:
    """Return two progressive scenario-candle closes per target."""
    closes: list[float] = []
    previous = float(entry)
    for target in targets[:3]:
        target = float(target)
        midpoint = previous + (target - previous) * 0.52
        closes.extend([midpoint, target])
        previous = target
    return closes


def _draw_trade_risk_reward_zones(
    image: Image.Image,
    analysis: dict[str, Any],
    price_min: float,
    price_max: float,
    candle_right: int,
) -> None:
    """Draw transparent target and stop areas for actionable scenarios.

    The zones are shown for conditional, confirmed-buy and confirmed-sell
    results.  Watch mode remains visually neutral because it has two competing
    paths and no committed risk/reward structure yet.
    """
    draw_mode = str(analysis.get("draw_mode") or "watch")
    direction = str(analysis.get("analysis_direction") or analysis.get("direction") or "غير واضح")
    if draw_mode not in {"conditional", "confirmed"} or direction not in {"صاعد", "هابط"}:
        return

    entry = _number(analysis.get("entry"))
    stop = _number(analysis.get("stop_loss"))
    targets = [_number(analysis.get(key)) for key in ("target_1", "target_2", "target_3")]
    targets = [value for value in targets if value is not None]
    if entry is None or stop is None or not targets:
        return

    target = targets[-1]
    if direction == "صاعد":
        valid = stop < entry < target
    else:
        valid = target < entry < stop
    if not valid:
        return

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x1 = min(CHART[2] - 210, max(candle_right + 10, PROJECTION_X1 - 35))
    x2 = CHART[2] - 8
    entry_y = _price_y(entry, price_min, price_max)
    stop_y = _price_y(stop, price_min, price_max)
    target_y = _price_y(target, price_min, price_max)

    # Leave a visible neutral separator around Entry.  Entry is the boundary
    # between reward and loss; it must never look embedded inside the red zone.
    entry_gap = 7
    if direction == "صاعد":
        profit_top = min(target_y, entry_y)
        profit_bottom = max(profit_top, entry_y - entry_gap)
        loss_top = min(stop_y, entry_y + entry_gap)
        loss_bottom = max(stop_y, entry_y + entry_gap)
    else:
        profit_top = min(entry_y + entry_gap, target_y)
        profit_bottom = max(entry_y + entry_gap, target_y)
        loss_top = min(stop_y, entry_y - entry_gap)
        loss_bottom = max(stop_y, entry_y - entry_gap)
    # No border: transparent zones should explain risk/reward without adding
    # another competing frame over the chart.
    draw.rectangle((x1, profit_top, x2, profit_bottom), fill=(25, 211, 112, 46))
    draw.rectangle((x1, loss_top, x2, loss_bottom), fill=(245, 63, 70, 42))
    image.alpha_composite(layer)


def _arrow_head(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    color: tuple[int, int, int, int],
    *,
    size: float = 14.0,
    width: int = 4,
) -> None:
    """Draw a compact arrow head aligned with the final path segment."""
    sx, sy = start
    ex, ey = end
    angle = math.atan2(ey - sy, ex - sx)
    wing = math.radians(31)
    p1 = (ex - size * math.cos(angle - wing), ey - size * math.sin(angle - wing))
    p2 = (ex - size * math.cos(angle + wing), ey - size * math.sin(angle + wing))
    draw.line((ex, ey, p1[0], p1[1]), fill=color, width=width)
    draw.line((ex, ey, p2[0], p2[1]), fill=color, width=width)


def _bezier_points(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    *,
    steps: int = 28,
) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    for index in range(steps + 1):
        t = index / steps
        u = 1.0 - t
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        points.append((round(x), round(y)))
    return points


def _draw_curved_arrow(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    color: tuple[int, int, int, int],
    *,
    width: int = 5,
) -> None:
    if len(points) < 2:
        return
    draw.line(points, fill=color, width=width, joint="curve")
    _arrow_head(draw, points[-2], points[-1], color, size=15.0, width=width)


def _draw_scenario_arrows(
    image: Image.Image,
    analysis: dict[str, Any],
    price_min: float,
    price_max: float,
) -> None:
    """Draw retest arrows for conditional and two alternatives for watch."""
    draw_mode = str(analysis.get("draw_mode") or "watch")
    direction = str(analysis.get("analysis_direction") or analysis.get("direction") or "غير واضح")
    entry = _number(analysis.get("entry"))
    if draw_mode not in {"watch", "conditional"} or entry is None:
        return
    if not _is_visible_price(entry, price_min, price_max):
        return

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    entry_y = _price_y(entry, price_min, price_max)
    x0 = PROJECTION_X1 - 8
    x3 = min(CHART[2] - 44, PROJECTION_X2 - 5)
    price_span = max(0.01, price_max - price_min)
    move = max(price_span * 0.055, abs((_number(analysis.get("target_1")) or entry) - entry) * 0.55)
    move_px = max(74, min(190, abs(_price_y(entry + move, price_min, price_max) - entry_y)))

    def retest_path(sign: int, color: tuple[int, int, int, int]) -> None:
        # sign=-1 means visually upward; sign=+1 means visually downward.
        first_end = (x0 + 74, entry_y + sign * move_px * 0.72)
        first = _bezier_points(
            (x0, entry_y),
            (x0 + 24, entry_y + sign * move_px * 0.15),
            (x0 + 45, entry_y + sign * move_px * 0.78),
            first_end,
            steps=20,
        )
        retest_end = (x0 + 132, entry_y + sign * move_px * 0.25)
        second = _bezier_points(
            first_end,
            (x0 + 92, entry_y + sign * move_px * 0.78),
            (x0 + 108, entry_y + sign * move_px * 0.22),
            retest_end,
            steps=18,
        )
        final_end = (x3, entry_y + sign * move_px * 1.12)
        third = _bezier_points(
            retest_end,
            (x0 + 154, entry_y + sign * move_px * 0.18),
            (x3 - 34, entry_y + sign * move_px * 1.00),
            final_end,
            steps=24,
        )
        path = first + second[1:] + third[1:]
        _draw_curved_arrow(draw, path, color, width=5)

    if draw_mode == "conditional" and direction in {"صاعد", "هابط"}:
        retest_path(-1 if direction == "صاعد" else 1, (249, 115, 22, 225))
    elif draw_mode == "watch":
        # Two equal alternatives begin from the exact Entry level.
        retest_path(-1, (38, 117, 247, 215))
        retest_path(1, (249, 115, 22, 215))

    image.alpha_composite(layer)


def _draw_projection_candles(
    image: Image.Image,
    analysis: dict[str, Any],
    price_min: float,
    price_max: float,
) -> None:
    """Replace the directional arrow with fixed-column scenario candles.

    X positions are identical in every result. Y positions are calculated from
    the shared price transform, so every candle travels from Entry through
    TP1, TP2 and TP3 without changing the uploaded chart or its axis.
    """
    draw_mode = str(analysis.get("draw_mode") or "watch")
    direction = str(analysis.get("analysis_direction") or analysis.get("direction") or "غير واضح")
    entry = _number(analysis.get("entry"))
    if draw_mode not in {"conditional", "confirmed"} or direction not in {"صاعد", "هابط"} or entry is None:
        return

    targets: list[float] = []
    for key in ("target_1", "target_2", "target_3"):
        value = _number(analysis.get(key))
        if value is None or not _is_visible_price(value, price_min, price_max):
            continue
        if direction == "صاعد" and value <= entry:
            continue
        if direction == "هابط" and value >= entry:
            continue
        targets.append(float(value))
    if not targets:
        return

    closes = _projection_closes(float(entry), targets)
    if not closes:
        return

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    count = len(closes)
    span = PROJECTION_X2 - PROJECTION_X1
    slot = span / max(1, count)
    body_w = max(12, min(24, int(slot * 0.48)))
    alpha = 118 if draw_mode == "conditional" else 158
    wick_alpha = min(220, alpha + 35)
    main_rgb = TP_GREEN[:3] if direction == "صاعد" else RED[:3]
    fill = (*main_rgb, alpha)
    outline = (*main_rgb, min(235, alpha + 55))
    wick = (*main_rgb, wick_alpha)

    separator_x = PROJECTION_X1 - 18
    _dash_line(draw, (separator_x, CHART[1] + 46), (separator_x, CHART[3] - 30), (89, 122, 155, 120), width=1, dash=8, gap=8)

    previous = float(entry)
    price_span = max(0.01, price_max - price_min)
    for index, close in enumerate(closes):
        open_price = previous
        movement = close - open_price
        wick_size = max(abs(movement) * 0.18, price_span * 0.0022)
        high = max(open_price, close) + wick_size
        low = min(open_price, close) - wick_size
        x = int(PROJECTION_X1 + slot * (index + 0.5))
        y_open = _price_y(open_price, price_min, price_max)
        y_close = _price_y(close, price_min, price_max)
        y_high = _price_y(high, price_min, price_max)
        y_low = _price_y(low, price_min, price_max)
        draw.line((x, y_high, x, y_low), fill=wick, width=2)
        top = min(y_open, y_close)
        bottom = max(y_open, y_close)
        if bottom - top < 5:
            bottom = top + 5
        draw.rounded_rectangle((x - body_w // 2, top, x + body_w // 2, bottom), radius=2, fill=fill, outline=outline, width=2)
        previous = close

    image.alpha_composite(layer)


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

    draw.line((left, y, right, y), fill=(26, 210, 119, 205), width=2)

    # The uploaded chart already contains its native green current-price card.
    # Draw a fallback card only for fully reconstructed backgrounds.
    if current is None or analysis.get("_using_chart_background"):
        return
    source_axis_right = SOURCE_VISIBLE_WIDTH - 8
    source_axis_left = source_axis_right - AXIS_PRICE_CARD_WIDTH
    half_h = AXIS_PRICE_CARD_HEIGHT // 2
    box = (source_axis_left, y - half_h, source_axis_right, y + half_h)
    draw.rounded_rectangle(
        box,
        radius=AXIS_PRICE_CARD_RADIUS,
        fill=(71, 171, 154, 255),
        outline=(84, 224, 192, 255),
        width=1,
    )
    draw.text(((source_axis_left + source_axis_right) // 2, y), _fmt_price(current), font=F_TRADE_CARD_PRICE, fill=(4, 27, 33, 255), anchor="mm")


def _resolve_axis_card_centers(
    items: list[tuple[str, float, int, tuple[int, int, int, int]]],
    *,
    card_height: int = AXIS_PRICE_CARD_HEIGHT,
    vertical_gap: int = 6,
) -> dict[int, int]:
    """Separate overlapping cards vertically while preserving every true line Y.

    The returned values are display centers for cards only.  ``item[2]`` remains
    the immutable true price Y used by the chart line and connector origin.
    """
    if not items:
        return {}

    axis_left, axis_top, axis_right, axis_bottom = _saleem_axis_box()
    del axis_left, axis_right
    half = card_height // 2
    top_limit = axis_top + half + 4
    bottom_limit = axis_bottom - half - 4
    separation = card_height + vertical_gap

    ordered = sorted(enumerate(items), key=lambda pair: (int(pair[1][2]), pair[0]))
    desired = [max(top_limit, min(bottom_limit, int(item[2]))) for _idx, item in ordered]
    placed = desired[:]

    # Forward pass: make every next card clear the previous one.
    for i in range(1, len(placed)):
        placed[i] = max(placed[i], placed[i - 1] + separation)

    # Pull the cluster back inside the lower boundary.
    if placed[-1] > bottom_limit:
        shift = placed[-1] - bottom_limit
        placed = [value - shift for value in placed]

    # Backward pass: restore spacing after the boundary shift.
    for i in range(len(placed) - 2, -1, -1):
        placed[i] = min(placed[i], placed[i + 1] - separation)

    # Pull the cluster inside the upper boundary, then enforce spacing once more.
    if placed[0] < top_limit:
        shift = top_limit - placed[0]
        placed = [value + shift for value in placed]
    for i in range(1, len(placed)):
        placed[i] = max(placed[i], placed[i - 1] + separation)

    # The axis is much taller than the maximum card count, but keep a final
    # bounded fallback for malformed inputs.
    if placed[-1] > bottom_limit:
        shift = placed[-1] - bottom_limit
        placed = [value - shift for value in placed]

    return {original_index: int(card_y) for (original_index, _item), card_y in zip(ordered, placed)}


def _horizontal_card_lanes(
    items: list[tuple[str, float, int, tuple[int, int, int, int]]],
    *,
    card_height: int = AXIS_PRICE_CARD_HEIGHT,
    vertical_gap: int = 6,
) -> dict[int, int]:
    """Compatibility alias returning card display centers, not X lanes."""
    return _resolve_axis_card_centers(
        items, card_height=card_height, vertical_gap=vertical_gap
    )


def _draw_trade_axis_card(
    draw: ImageDraw.ImageDraw,
    *,
    label: str,
    price: float,
    exact_y: int,
    color: tuple[int, int, int, int],
    card_y: int | None = None,
    x_lane: int = 0,
) -> tuple[int, int, int, int]:
    """Draw a right-axis execution card linked to its immutable true line."""
    del x_lane
    _axis_left, _axis_top, axis_right, _axis_bottom = _saleem_axis_box()
    card_w = AXIS_PRICE_CARD_WIDTH
    card_h = AXIS_PRICE_CARD_HEIGHT
    x2 = axis_right - 14
    x1 = x2 - card_w
    display_y = int(exact_y if card_y is None else card_y)
    y1 = int(display_y - card_h // 2)
    y2 = y1 + card_h

    connector_start = CHART[2] + 4
    elbow_x = x1 - 16
    draw.line((connector_start, exact_y, elbow_x, exact_y), fill=color, width=2)
    draw.line((elbow_x, exact_y, x1, display_y), fill=color, width=2)

    draw.rounded_rectangle(
        (x1, y1, x2, y2),
        radius=AXIS_PRICE_CARD_RADIUS,
        fill=color,
        outline=(255, 255, 255, 175),
        width=1,
    )
    center_y = (y1 + y2) // 2
    draw.text((x1 + 10, center_y), label, font=F_TRADE_AXIS_LABEL, fill=WHITE, anchor="lm")
    draw.text((x2 - 10, center_y), _fmt_card_price(price), font=F_TRADE_AXIS_PRICE, fill=WHITE, anchor="rm")
    return x1, y1, x2, y2


def _level_strength_text(label: str, price: float) -> tuple[str, str]:
    """Return the short level name and adjacent decimal-price/strength text."""
    parts = str(label).split(" ", 1)
    level_name = parts[0]
    strength = parts[1] if len(parts) == 2 else ""
    value = _fmt_card_price(price)
    if strength:
        value = f"{value} {strength}"
    return level_name, value


def _draw_left_level_card(
    draw: ImageDraw.ImageDraw,
    *,
    label: str,
    price: float,
    exact_y: int,
    color: tuple[int, int, int, int],
    card_y: int | None = None,
) -> tuple[int, int, int, int]:
    """Draw a unified S/R card on the chart's left and link it to true Y."""
    card_w = AXIS_PRICE_CARD_WIDTH
    card_h = AXIS_PRICE_CARD_HEIGHT
    x1 = CHART[0] + 14
    x2 = x1 + card_w
    display_y = int(exact_y if card_y is None else card_y)
    y1 = int(display_y - card_h // 2)
    y2 = y1 + card_h

    # The true support/resistance line remains fixed.  Only the card may move
    # to avoid overlap, with an elbow connector returning to the real line.
    elbow_x = x2 + 16
    draw.line((x2, display_y, elbow_x, exact_y), fill=color, width=2)
    draw.line((elbow_x, exact_y, min(CHART[2] - 3, elbow_x + 24), exact_y), fill=color, width=2)

    draw.rounded_rectangle(
        (x1, y1, x2, y2),
        radius=AXIS_PRICE_CARD_RADIUS,
        fill=color,
        outline=(255, 255, 255, 175),
        width=1,
    )
    level_name, price_strength = _level_strength_text(label, price)
    center_y = (y1 + y2) // 2
    draw.text((x1 + 10, center_y), level_name, font=F_TRADE_AXIS_LABEL, fill=WHITE, anchor="lm")
    # The percentage is deliberately adjacent to the decimal price.
    draw.text((x2 - 10, center_y), price_strength, font=F_TRADE_AXIS_LABEL, fill=WHITE, anchor="rm")
    return x1, y1, x2, y2

def _trade_display_items(analysis: dict[str, Any], price_min: float, price_max: float) -> tuple[str, list[tuple[str, float, int, tuple[int, int, int, int]]]]:
    """Return right-axis cards centered on their exact real-price Y."""
    draw_mode = str(analysis.get("draw_mode") or "watch")
    if draw_mode == "inactive":
        return draw_mode, []
    direction = str(analysis.get("analysis_direction") or analysis.get("direction") or "غير واضح")
    if direction not in {"صاعد", "هابط"}:
        return draw_mode, []

    entry = _number(analysis.get("entry"))
    stop = _number(analysis.get("stop_loss"))
    if entry is None or not _is_visible_price(entry, price_min, price_max):
        return draw_mode, []

    entry_y = _price_y(entry, price_min, price_max)
    if draw_mode == "watch":
        return draw_mode, [("Entry", entry, entry_y, ENTRY_CARD)]

    items = [("Entry", entry, entry_y, ENTRY_CARD)]
    if stop is not None and _is_visible_price(stop, price_min, price_max):
        if draw_mode == "conditional":
            items.append(("Cancel", stop, _price_y(stop, price_min, price_max), CANCEL_CARD))
        else:
            items.append(("Stop", stop, _price_y(stop, price_min, price_max), STOP_CARD))
    target_colors = (TP1_CARD, TP2_CARD, TP3_CARD)
    for index, key in enumerate(("target_1", "target_2", "target_3"), start=1):
        target = _number(analysis.get(key))
        if target is not None and _is_visible_price(target, price_min, price_max):
            items.append((f"TP{index}", target, _price_y(target, price_min, price_max), target_colors[index - 1]))
    return draw_mode, items


def _draw_trade(image: Image.Image, draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float, candle_right: int) -> None:
    _left, _top, right, _bottom = CHART
    direction = str(analysis.get("analysis_direction") or analysis.get("direction") or "غير واضح")
    draw_mode, trade_items = _trade_display_items(analysis, price_min, price_max)
    level_items = _level_display_items(analysis, price_min, price_max)

    # Execution lines stay at their true prices.  Support/resistance true lines
    # were already drawn by _draw_levels and are never displaced.
    if trade_items and direction in {"صاعد", "هابط"}:
        trade_line_left = min(right - 165, max(candle_right + 8, int(CHART[0] + (right - CHART[0]) * 0.58)))
        dashed = draw_mode in {"watch", "conditional"}
        for _label, _price, exact_y, color in trade_items:
            if dashed:
                _dash_line(draw, (trade_line_left, exact_y), (right, exact_y), color, width=2, dash=10, gap=7)
            else:
                draw.line((trade_line_left, exact_y, right, exact_y), fill=color, width=2)

    # Left S/R cards and right execution cards use independent collision lanes.
    # Their real chart lines never move; only the display card center changes.
    level_centers = _resolve_axis_card_centers(level_items)
    for index, (label, price, exact_y, color) in enumerate(level_items):
        _draw_left_level_card(
            draw,
            label=label,
            price=price,
            exact_y=exact_y,
            card_y=level_centers.get(index, exact_y),
            color=color,
        )

    trade_centers = _resolve_axis_card_centers(trade_items)
    for index, (label, price, exact_y, color) in enumerate(trade_items):
        _draw_trade_axis_card(
            draw,
            label=label,
            price=price,
            exact_y=exact_y,
            card_y=trade_centers.get(index, exact_y),
            color=color,
        )

    if trade_items and direction in {"صاعد", "هابط"}:
        _draw_projection_candles(image, analysis, price_min, price_max)
        _draw_scenario_arrows(image, analysis, price_min, price_max)

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

def _draw_bottom_summary(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    """Fixed one-row action summary below the chart without changing chart size."""
    draw.rounded_rectangle(
        BOTTOM_SUMMARY_PANEL,
        radius=22,
        fill=(4, 8, 12, 255),
        outline=(220, 160, 45, 255),
        width=3,
    )

    state = str(analysis.get("draw_mode") or "watch")
    direction = str(analysis.get("direction") or "غير واضح")
    if state == "inactive":
        entry_value, entry_color = "متوقف", GOLD
        confirmation_value, confirmation_color = "بيانات قديمة", GOLD
        decision_value, decision_color = "انتظار السوق", GOLD
    else:
        entry_value = "جاهز" if state == "confirmed" else ("مشروط" if state == "conditional" else "مراقبة")
        entry_color = GREEN if state == "confirmed" else (ORANGE if state == "conditional" else BLUE)
        confirmation_value = "مكتمل" if state == "confirmed" else "بانتظار"
        confirmation_color = GREEN if state == "confirmed" else ORANGE
    if state == "confirmed":
        decision_value = "شراء" if direction == "صاعد" else ("بيع" if direction == "هابط" else "انتظار")
        decision_color = GREEN if direction == "صاعد" else (RED if direction == "هابط" else ORANGE)
    elif state != "inactive":
        decision_value, decision_color = "انتظار", ORANGE
    breakout_value, breakout_color = _breakout_label(analysis)
    rebound_value, rebound_color = _rebound_label(analysis)

    cards = [
        ("الدخول", [entry_value], entry_color, False),
        ("التأكيد", [confirmation_value], confirmation_color, False),
        ("القرار", [decision_value], decision_color, False),
        ("الاختراق", [breakout_value], breakout_color, False),
        ("الارتداد", [rebound_value], rebound_color, False),
    ]
    margin_x = BOTTOM_SUMMARY_PANEL[0] + 13
    gap_x = 13
    card_w = (BOTTOM_SUMMARY_PANEL[2] - BOTTOM_SUMMARY_PANEL[0] - 26 - gap_x * 4) // 5
    for index, (label, values, color, latin_value) in enumerate(cards):
        x1 = margin_x + index * (card_w + gap_x)
        x2 = x1 + card_w
        _draw_summary_card(
            draw,
            (x1, BOTTOM_CARDS_Y1, x2, BOTTOM_CARDS_Y2),
            label,
            values,
            color,
            latin_value=latin_value,
        )


def _draw_session_footer(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    """Compact market-session timeline; chart geometry remains unchanged."""
    y2 = HEIGHT - 24
    y1 = HEIGHT - 154
    panel = (12, y1, WIDTH - 12, y2)
    draw.rounded_rectangle(panel, radius=16, fill=(5, 23, 46, 255), outline=(50, 81, 115, 255), width=2)

    active = _active_session_label(analysis)
    items = [
        ("Asia", "04:00 - 12:00", "آسيا", CYAN),
        ("London", "11:00 - 19:00", "لندن", BLUE),
        ("New York", "16:00 - 00:00", "نيويورك", PURPLE),
        ("Overlap", "16:00 - 19:00", "تداخل", (198, 77, 255, 255)),
    ]
    gap = 2
    width = (panel[2] - panel[0] - gap * 3) // 4
    for index, (name, hours, arabic_name, color) in enumerate(items):
        x1 = panel[0] + index * (width + gap)
        x2 = x1 + width
        is_active = active == arabic_name
        fill = (14, 43, 75, 255) if is_active else (5, 25, 48, 255)
        draw.rectangle((x1, y1 + 2, x2, y2 - 2), fill=fill)
        if is_active:
            draw.rectangle((x1 + 6, y1 + 2, x2 - 6, y1 + 7), fill=color)
        draw.text(((x1 + x2) // 2, y1 + 40), name, font=F_SESSION_NAME, fill=color if is_active else (105, 147, 188, 255), anchor="mm")
        draw.text(((x1 + x2) // 2, y1 + 82), hours, font=F_SESSION_TIME, fill=(174, 190, 213, 255) if is_active else (116, 132, 157, 255), anchor="mm")


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

    state_suffix = (
        "السوق مغلق/البيانات غير محدثة"
        if draw_mode == "inactive"
        else ("مراقبة" if draw_mode == "watch" else ("مؤكد" if draw_mode == "confirmed" else "مشروط"))
    )
    direction_value = f"{direction} - احتمال {probability}٪ - {state_suffix}"
    pattern_value = f"{pattern} - ثقة {pattern_confidence}٪" if pattern != "لا يوجد" else "لا يوجد نموذج مكتمل"
    active_setup = draw_mode in {"conditional", "confirmed"}
    stop_value = _fmt_price(stop) if stop is not None and active_setup else "—"
    target_value = (
        " | ".join(f"TP{i}: {_fmt_price(value)}" for i, value in enumerate(targets, start=1) if value is not None)
        if active_setup
        else ("السوق مغلق/البيانات غير محدثة" if draw_mode == "inactive" else "بانتظار وضوح السيناريو")
    )

    rows = [
        ("الاتجاه:", direction_value, GREEN if direction == "صاعد" else (RED if direction == "هابط" else GOLD), False),
        ("النمط:", pattern_value, BLUE, False),
        ("شرط الدخول:", confirmation, GREEN if active_setup else GOLD, False),
        ("وقف:", stop_value, RED, True),
        ("الأهداف:", target_value, GREEN, active_setup),
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

    # صورة الشارت المرفوعة تبقى في حجمها ومكانها دون إعادة رسم أو تحريك؛
    # التعديلات التالية طبقات مستقلة حولها وفوقها فقط.
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

    # Mandatory single-axis binding: even when exact OCR calibration is not
    # available, the current price and every overlay are projected through the
    # same final price->Y transform. The detected pixel line is only an anchor
    # used while building that transform, never a second independent scale.
    current_reference_y = _axis_checked_current_reference_y(
        analysis,
        price_min,
        price_max,
        current_reference_y,
    )
    analysis["price_axis_binding"] = "original_chart_single_transform"
    analysis["price_axis_overlap_policy"] = "true_line_fixed_axis_cards_separated_with_connectors"
    analysis["price_card_alignment"] = "exact_when_clear_displaced_only_on_overlap"

    analysis["_using_chart_background"] = using_chart_background
    _draw_grid(draw, analysis, price_min, price_max, background_mode=using_chart_background)
    top_price_box = None
    if prepared_background is not None:
        _paste_prepared_chart_background(image, prepared_background)
        draw = ImageDraw.Draw(image)
    _draw_header(draw, analysis)
    count = max(1, len(candles))
    candle_right = int(CHART[0] + (CHART[2] - CHART[0]) * 0.68)
    slot = (candle_right - CHART[0]) / count
    _draw_trade_risk_reward_zones(image, analysis, price_min, price_max, candle_right)
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
    _draw_bottom_summary(draw, analysis)
    _draw_session_footer(draw, analysis)

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()
