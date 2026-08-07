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
PEAK_CARD = (124, 58, 237, 255)
TROUGH_CARD = (8, 145, 178, 255)

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
    direction = str(analysis.get("direction") or "غير واضح")
    if state == "inactive":
        return "السوق مغلق", GOLD
    if state == "watch":
        return "مراقبة", BLUE
    if state == "conditional":
        if direction == "صاعد":
            return "شراء بشرط", ORANGE
        if direction == "هابط":
            return "بيع بشرط", ORANGE
        return "بانتظار التفعيل", ORANGE
    if state == "confirmed":
        if direction == "صاعد":
            return "شراء", GREEN
        if direction == "هابط":
            return "بيع", RED
    return "مراقبة", BLUE


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


def _current_movement_label(analysis: dict[str, Any]) -> tuple[str, tuple[int, int, int, int]]:
    """Show the latest M5 movement separately from the higher-timeframe trend."""
    movement = str(analysis.get("current_movement") or "").strip()
    if not movement:
        frames = analysis.get("frame_directions")
        if isinstance(frames, dict):
            m5 = frames.get("M5")
            if isinstance(m5, dict):
                movement = str(m5.get("direction") or "").strip()
    if movement == "صاعد":
        return movement, GREEN
    if movement == "هابط":
        return movement, RED
    if movement == "عرضي":
        return movement, BLUE
    candle_value, candle_color = _candle_shape_label(analysis)
    if candle_value in {"صاعدة", "رفض صاعد"}:
        return "صاعد", GREEN
    if candle_value in {"هابطة", "رفض هابط"}:
        return "هابط", RED
    return "غير واضح", candle_color


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
            safe_values = ["غير مكتمل"] if label == "النمط" else ["—"]
        font = _summary_value_font(
            draw,
            safe_values,
            max(20, x2 - x1 - 22),
            compact=label == "النمط",
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
    general_direction = str(analysis.get("higher_timeframe_direction") or direction)
    direction_color = GREEN if general_direction == "صاعد" else (RED if general_direction == "هابط" else BLUE)
    probability = max(0, min(100, int(analysis.get("trade_probability") or 50)))
    probability_text = "—" if str(analysis.get("draw_mode") or "watch") == "inactive" else f"{probability}%"
    pattern_lines = _header_pattern_lines(str(analysis.get("pattern_type") or "لا يوجد"))
    close_value, close_color = _close_label(analysis)
    zone_value, zone_color = _nearest_zone_label(analysis)
    movement_value, movement_color = _current_movement_label(analysis)
    momentum_value, momentum_color = _momentum_label(analysis)
    candle_value, candle_color = _candle_shape_label(analysis)
    alignment = _frame_match_count(analysis)

    # Lists are left-to-right on the canvas; RTL reading begins at the right.
    rows = [
        [
            ("الاتجاه العام", [general_direction], direction_color, False),
            ("الحركة الحالية", [movement_value], movement_color, False),
            ("الحالة", [state_value], state_color, False),
            ("المنطقة", [zone_value], zone_color, False),
        ],
        [
            ("الإغلاق", [close_value], close_color, False),
            ("الزخم", [momentum_value], momentum_color, False),
            ("شكل الشمعة", [candle_value], candle_color, False),
            ("النموذج", pattern_lines, CYAN, False),
        ],
    ]

    margin_x = TOP_SUMMARY_PANEL[0] + 13
    gap_x = 13
    card_w = (TOP_SUMMARY_PANEL[2] - TOP_SUMMARY_PANEL[0] - 26 - gap_x * 3) // 4
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
    """Draw the simplified transparent zones requested by the user.

    - في الشراء/البيع المؤكدين أو المفعّلين: منطقة الدخول/الخسارة حمراء،
      ومنطقة الأهداف خضراء.
    - في المراقبة: تظهر منطقة حمراء صغيرة عند التفعيل، ومنطقتان خضراوان
      نحو القمة والقاع المحتملين معًا لعرض الاحتمالين.
    """
    draw_mode = str(analysis.get("draw_mode") or "watch")
    direction = str(analysis.get("analysis_direction") or analysis.get("direction") or "غير واضح")

    x1 = min(CHART[2] - 210, max(candle_right + 10, PROJECTION_X1 - 35))
    x2 = CHART[2] - 8
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    entry = _number(analysis.get("entry"))
    current = _number(analysis.get("current_price"))
    focus = entry if entry is not None else current
    if focus is None or not _is_visible_price(focus, price_min, price_max):
        return

    focus_y = _price_y(focus, price_min, price_max)
    # Entry is the boundary between the neutral center and the surrounding zones.
    entry_gap = 7

    if draw_mode == "watch":
        buy_plan = analysis.get("buy_scenario_details") if isinstance(analysis.get("buy_scenario_details"), dict) else {}
        sell_plan = analysis.get("sell_scenario_details") if isinstance(analysis.get("sell_scenario_details"), dict) else {}
        buy_trigger = _number(buy_plan.get("trigger_price")) or focus
        sell_trigger = _number(sell_plan.get("trigger_price")) or focus
        if buy_trigger < sell_trigger:
            buy_trigger, sell_trigger = sell_trigger, buy_trigger
        buy_trigger = max(price_min, min(price_max, float(buy_trigger)))
        sell_trigger = max(price_min, min(price_max, float(sell_trigger)))

        peak = _number(((analysis.get("most_probable_peak") or {}).get("price")))
        trough = _number(((analysis.get("most_probable_trough") or {}).get("price")))
        if peak is None:
            peak = _number(buy_plan.get("display_target")) or _number(buy_plan.get("extended_target"))
        if trough is None:
            trough = _number(sell_plan.get("display_target")) or _number(sell_plan.get("extended_target"))

        price_span = max(0.01, price_max - price_min)
        upper_target = peak if peak is not None and peak > buy_trigger else buy_trigger + price_span * 0.10
        lower_target = trough if trough is not None and trough < sell_trigger else sell_trigger - price_span * 0.10
        upper_target = max(buy_trigger + price_span * 0.025, min(price_max - price_span * 0.015, float(upper_target)))
        lower_target = min(sell_trigger - price_span * 0.025, max(price_min + price_span * 0.015, float(lower_target)))

        buy_y = _price_y(buy_trigger, price_min, price_max)
        sell_y = _price_y(sell_trigger, price_min, price_max)
        peak_y = _price_y(upper_target, price_min, price_max)
        trough_y = _price_y(lower_target, price_min, price_max)

        # Red is the activation/entry band between the two monitored triggers.
        red_top = min(buy_y, sell_y)
        red_bottom = max(buy_y, sell_y)
        if red_bottom - red_top < 18:
            center = (red_top + red_bottom) // 2
            red_top, red_bottom = center - 9, center + 9
        draw.rectangle((x1, red_top, x2, red_bottom), fill=(245, 63, 70, 44))

        # Monitoring always shows green opportunity zones in both directions.
        draw.rectangle((x1, min(peak_y, buy_y - entry_gap), x2, max(peak_y, buy_y - entry_gap)), fill=(25, 211, 112, 44))
        draw.rectangle((x1, min(sell_y + entry_gap, trough_y), x2, max(sell_y + entry_gap, trough_y)), fill=(25, 211, 112, 44))

        image.alpha_composite(layer)
        return

    if draw_mode not in {"conditional", "confirmed"} or direction not in {"صاعد", "هابط"}:
        return
    if draw_mode == "conditional" and not bool(analysis.get("show_targets_as_active")):
        return

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

    entry_y = _price_y(entry, price_min, price_max)
    stop_y = _price_y(stop, price_min, price_max)
    target_y = _price_y(target, price_min, price_max)

    draw.rectangle((x1, min(stop_y, entry_y + entry_gap), x2, max(stop_y, entry_y + entry_gap)), fill=(245, 63, 70, 44))
    draw.rectangle((x1, min(target_y, entry_y - entry_gap), x2, max(target_y, entry_y - entry_gap)), fill=(25, 211, 112, 48))
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


def _last_rendered_candle_x(analysis: dict[str, Any]) -> int:
    """Return the exact X center of the last rendered M5 candle."""
    candles = [
        candle
        for candle in (analysis.get("candles") or [])
        if isinstance(candle, dict)
        and all(_number(candle.get(key)) is not None for key in ("open", "high", "low", "close"))
    ]
    if not candles:
        return PROJECTION_X1 - 8
    left, _top, right, _bottom = CHART
    candle_right = int(left + (right - left) * 0.68)
    slot = (candle_right - left) / max(1, len(candles))
    return int(left + slot * (len(candles) - 0.5))


def _scenario_arrow_origin(
    analysis: dict[str, Any],
    *,
    side: str,
    price_min: float,
    price_max: float,
) -> tuple[int, int, float] | None:
    """Return the arrow origin at the activation candle close.

    When activation has not happened yet, the relevant trigger level is used as
    the honest monitoring fallback because no activation candle close exists.
    """
    key = "buy_scenario_details" if side == "buy" else "sell_scenario_details"
    plan = analysis.get(key) if isinstance(analysis.get(key), dict) else {}
    active = bool(plan.get("is_active"))
    activation_close = _number(plan.get("activation_candle_close"))
    trigger_price = _number(plan.get("trigger_price"))
    fallback_entry = _number(analysis.get("entry"))

    if active and activation_close is not None:
        start_price = activation_close
    else:
        start_price = _number(plan.get("arrow_start_price")) or trigger_price or fallback_entry
    if start_price is None or not _is_visible_price(start_price, price_min, price_max):
        return None
    return _last_rendered_candle_x(analysis), _price_y(start_price, price_min, price_max), float(start_price)


def _scenario_arrow_target(
    analysis: dict[str, Any],
    *,
    side: str,
    start_price: float,
    price_min: float,
    price_max: float,
) -> float:
    key = "buy_scenario_details" if side == "buy" else "sell_scenario_details"
    plan = analysis.get(key) if isinstance(analysis.get(key), dict) else {}
    probable_key = "most_probable_peak" if side == "buy" else "most_probable_trough"
    probable = plan.get(probable_key) if isinstance(plan.get(probable_key), dict) else {}
    candidates = [
        _number(plan.get("display_target")),
        _number(probable.get("price")),
        _number(plan.get("extended_target")),
        _number(plan.get("quick_target")),
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        if side == "buy" and candidate > start_price:
            return max(price_min, min(price_max, float(candidate)))
        if side == "sell" and candidate < start_price:
            return max(price_min, min(price_max, float(candidate)))
    price_span = max(0.01, price_max - price_min)
    fallback = start_price + (price_span * 0.08 if side == "buy" else -price_span * 0.08)
    return max(price_min, min(price_max, fallback))


def _draw_scenario_arrows(
    image: Image.Image,
    analysis: dict[str, Any],
    price_min: float,
    price_max: float,
) -> None:
    """Draw buy/sell paths from the activation candle close or trigger level."""
    draw_mode = str(analysis.get("draw_mode") or "watch")
    direction = str(analysis.get("analysis_direction") or analysis.get("direction") or "غير واضح")
    if draw_mode not in {"watch", "conditional", "confirmed"}:
        return
    if draw_mode == "conditional" and not bool(analysis.get("directional_path_enabled")):
        return

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x3 = min(CHART[2] - 28, PROJECTION_X2 - 2)

    def draw_side(side: str, color: tuple[int, int, int, int]) -> None:
        origin = _scenario_arrow_origin(
            analysis, side=side, price_min=price_min, price_max=price_max
        )
        if origin is None:
            return
        x0, start_y, start_price = origin
        target_price = _scenario_arrow_target(
            analysis,
            side=side,
            start_price=start_price,
            price_min=price_min,
            price_max=price_max,
        )
        target_y = _price_y(target_price, price_min, price_max)
        sign = -1 if side == "buy" else 1
        minimum_move = 72
        desired_move = abs(target_y - start_y)
        move_px = max(minimum_move, min(240, desired_move))
        final_y = start_y + sign * move_px
        final_y = max(CHART[1] + 24, min(CHART[3] - 24, final_y))

        # The first pixel is anchored to the activation candle close. A compact
        # retest bend follows, then the arrow continues toward the probable target.
        first_end = (x0 + 58, start_y + sign * move_px * 0.58)
        first = _bezier_points(
            (x0, start_y),
            (x0 + 18, start_y + sign * move_px * 0.08),
            (x0 + 34, start_y + sign * move_px * 0.55),
            first_end,
            steps=18,
        )
        retest_end = (x0 + 104, start_y + sign * move_px * 0.22)
        second = _bezier_points(
            first_end,
            (x0 + 72, start_y + sign * move_px * 0.62),
            (x0 + 86, start_y + sign * move_px * 0.18),
            retest_end,
            steps=16,
        )
        third = _bezier_points(
            retest_end,
            (x0 + 132, start_y + sign * move_px * 0.18),
            (x3 - 34, final_y - sign * 14),
            (x3, final_y),
            steps=24,
        )
        draw.ellipse((x0 - 5, start_y - 5, x0 + 5, start_y + 5), fill=color)
        _draw_curved_arrow(draw, first + second[1:] + third[1:], color, width=5)

    green_arrow = (25, 211, 112, 225)
    red_arrow = (245, 63, 70, 225)
    if draw_mode == "watch":
        draw_side("buy", green_arrow)
        draw_side("sell", red_arrow)
    elif direction == "صاعد":
        draw_side("buy", green_arrow)
    elif direction == "هابط":
        draw_side("sell", red_arrow)

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
    if draw_mode == "conditional" and not bool(analysis.get("directional_path_enabled")):
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
    if any("\u0600" <= char <= "\u06ff" for char in str(label)):
        _draw_rtl(draw, (x1 + 10, center_y), str(label), F_TRADE_AXIS_LABEL, WHITE, anchor="lm")
    else:
        draw.text((x1 + 10, center_y), str(label), font=F_TRADE_AXIS_LABEL, fill=WHITE, anchor="lm")
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


def _extreme_display_items(analysis: dict[str, Any], price_min: float, price_max: float) -> list[tuple[str, float, int, tuple[int, int, int, int]]]:
    """Return the most probable peak and trough as right-axis cards."""
    items: list[tuple[str, float, int, tuple[int, int, int, int]]] = []
    peak = analysis.get("most_probable_peak") or {}
    trough = analysis.get("most_probable_trough") or {}
    peak_price = _number(peak.get("price"))
    trough_price = _number(trough.get("price"))

    if peak_price is not None and _is_visible_price(peak_price, price_min, price_max):
        items.append(("قمة", float(peak_price), _price_y(float(peak_price), price_min, price_max), PEAK_CARD))
    if trough_price is not None and _is_visible_price(trough_price, price_min, price_max):
        items.append(("قاع", float(trough_price), _price_y(float(trough_price), price_min, price_max), TROUGH_CARD))
    return items


def _draw_trade(image: Image.Image, draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float, candle_right: int) -> None:
    _left, _top, right, _bottom = CHART
    direction = str(analysis.get("analysis_direction") or analysis.get("direction") or "غير واضح")
    draw_mode, trade_items = _trade_display_items(analysis, price_min, price_max)
    level_items = _level_display_items(analysis, price_min, price_max)
    extreme_items = _extreme_display_items(analysis, price_min, price_max)

    if trade_items and direction in {"صاعد", "هابط"}:
        trade_line_left = min(right - 165, max(candle_right + 8, int(CHART[0] + (right - CHART[0]) * 0.58)))
        dashed = draw_mode in {"watch", "conditional"}
        for _label, _price, exact_y, color in trade_items:
            if dashed:
                _dash_line(draw, (trade_line_left, exact_y), (right, exact_y), color, width=2, dash=10, gap=7)
            else:
                draw.line((trade_line_left, exact_y, right, exact_y), fill=color, width=2)

    level_centers = _resolve_axis_card_centers(level_items)
    for index, (label, price, exact_y, color) in enumerate(level_items):
        _draw_left_level_card(draw, label=label, price=price, exact_y=exact_y, card_y=level_centers.get(index, exact_y), color=color)

    right_items = trade_items + extreme_items
    right_centers = _resolve_axis_card_centers(right_items)
    for index, (label, price, exact_y, color) in enumerate(right_items):
        _draw_trade_axis_card(draw, label=label, price=price, exact_y=exact_y, card_y=right_centers.get(index, exact_y), color=color)

    if direction in {"صاعد", "هابط"} or draw_mode == "watch":
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
    return {"قمتان": "M", "قاعان": "W", "M": "M", "W": "W"}.get(name, name)


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
        entry_value = "جاهز" if state == "confirmed" else ("بانتظار" if state == "conditional" else "مراقبة")
        entry_color = GREEN if state == "confirmed" else (ORANGE if state == "conditional" else BLUE)
    if state == "confirmed":
        decision_value = "شراء" if direction == "صاعد" else ("بيع" if direction == "هابط" else "انتظار")
        decision_color = GREEN if direction == "صاعد" else (RED if direction == "هابط" else ORANGE)
    elif state == "conditional":
        decision_value = "شراء بشرط" if direction == "صاعد" else ("بيع بشرط" if direction == "هابط" else "بانتظار")
        decision_color = ORANGE
    elif state != "inactive":
        decision_value, decision_color = "انتظار", ORANGE
    breakout_value, breakout_color = _breakout_label(analysis)
    rebound_value, rebound_color = _rebound_label(analysis)

    cards = [
        ("التفعيل", [entry_value], entry_color, False),
        ("القرار", [decision_value], decision_color, False),
        ("الاختراق", [breakout_value], breakout_color, False),
        ("الارتداد", [rebound_value], rebound_color, False),
    ]
    margin_x = BOTTOM_SUMMARY_PANEL[0] + 13
    gap_x = 13
    card_w = (BOTTOM_SUMMARY_PANEL[2] - BOTTOM_SUMMARY_PANEL[0] - 26 - gap_x * 3) // 4
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




def _reference_direction(analysis: dict[str, Any], entry: float | None = None, target: float | None = None, stop: float | None = None) -> str:
    direction = str(analysis.get("analysis_direction") or analysis.get("direction") or "").strip()
    if direction in {"صاعد", "هابط"}:
        return direction
    if entry is not None and target is not None:
        return "صاعد" if target > entry else "هابط"
    if entry is not None and stop is not None:
        return "صاعد" if stop < entry else "هابط"
    candles = [c for c in (analysis.get("candles") or []) if isinstance(c, dict)]
    if len(candles) >= 2:
        first = _number(candles[max(0, len(candles) - 8)].get("close"))
        last = _number(candles[-1].get("close"))
        if first is not None and last is not None and last != first:
            return "صاعد" if last > first else "هابط"
    return "هابط"


def _valid_renderer_candles(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for candle in analysis.get("candles") or []:
        if not isinstance(candle, dict):
            continue
        if all(_number(candle.get(key)) is not None for key in ("open", "high", "low", "close")):
            items.append(candle)
    return items


def _simple_swing_points(candles: list[dict[str, Any]], *, window: int = 2) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    if len(candles) < window * 2 + 1:
        return highs, lows
    for i in range(window, len(candles) - window):
        high = float(candles[i]["high"])
        low = float(candles[i]["low"])
        prev_highs = [float(candles[j]["high"]) for j in range(i - window, i)]
        next_highs = [float(candles[j]["high"]) for j in range(i + 1, i + window + 1)]
        prev_lows = [float(candles[j]["low"]) for j in range(i - window, i)]
        next_lows = [float(candles[j]["low"]) for j in range(i + 1, i + window + 1)]
        if high >= max(prev_highs + next_highs):
            highs.append((i, high))
        if low <= min(prev_lows + next_lows):
            lows.append((i, low))
    return highs, lows


def _reference_style_header(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    """Small identity badge; the rest of the top area is reserved for the action card."""
    panel = (24, 24, 282, 118)
    draw.rounded_rectangle(panel, radius=18, fill=(5, 17, 32, 220), outline=(255, 255, 255, 44), width=1)
    draw.text((46, 52), "SaleeM", font=F_TITLE_LATIN, fill=WHITE, anchor="la")
    draw.text((46, 88), f"{analysis.get('symbol') or 'XAUUSD'} / {analysis.get('timeframe') or 'M5'}", font=F_TRADE_LATIN, fill=(186, 198, 216, 255), anchor="la")


def _reference_action_banner(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    """Answer enter/wait/no-trade without showing stale execution geometry."""
    action = analysis.get("action_summary") if isinstance(analysis.get("action_summary"), dict) else {}
    code = str(action.get("code") or analysis.get("draw_mode") or "watch")
    side = str(action.get("primary_side") or ("buy" if str(analysis.get("direction")) == "صاعد" else "sell" if str(analysis.get("direction")) == "هابط" else "wait"))
    confirmed = bool(action.get("is_confirmed")) or code in {"buy", "sell", "confirmed"}

    if code in {"inactive", "no_trade"} or side == "wait":
        title = "لا تدخل الآن"
        subtitle = str(action.get("instruction") or "انتظر إغلاق شمعة الخمس دقائق بوضوح")
        accent = (62, 128, 245, 255)
    elif confirmed:
        title = "ادخل شراء" if side == "buy" else "ادخل بيع"
        subtitle = "الصفقة مفعّلة — لا تطارد السعر بعيدًا عن الدخول"
        accent = (28, 178, 103, 255) if side == "buy" else (222, 72, 72, 255)
    else:
        title = "انتظر تفعيل الشراء" if side == "buy" else "انتظر تفعيل البيع"
        trigger = _number(action.get("trigger"))
        if trigger is not None:
            subtitle = f"بعد إغلاق شمعة الخمس دقائق {'فوق' if side == 'buy' else 'تحت'} {_fmt_axis_price(trigger)}"
        else:
            subtitle = str(action.get("instruction") or "لا تدخل قبل إغلاق شمعة التفعيل")
        accent = (235, 147, 45, 255)

    rect = (304, 24, WIDTH - 24, 286)
    draw.rounded_rectangle(rect, radius=22, fill=(5, 18, 34, 238), outline=(accent[0], accent[1], accent[2], 180), width=2)
    draw.rectangle((rect[0], rect[1], rect[0] + 8, rect[3]), fill=accent)

    _draw_rtl(draw, (rect[2] - 26, 56), title, F_TITLE, accent, anchor="ra")
    shown_subtitle = _fit_text(draw, subtitle, F_NOTE_BOLD, rect[2] - rect[0] - 62, rtl=True)
    _draw_rtl(draw, (rect[2] - 26, 110), shown_subtitle, F_NOTE_BOLD, WHITE, anchor="ra")

    strength = int(action.get("strength") or analysis.get("trade_probability") or 0)
    current = _number(analysis.get("current_price"))
    analysis_entry = _number(analysis.get("entry"))
    analysis_stop = _number(analysis.get("stop_loss"))
    analysis_t1 = _number(analysis.get("target_1"))
    trigger = _number(action.get("trigger"))
    cancel = _number(action.get("cancel"))
    action_target = _number(action.get("target"))

    if confirmed:
        values = [
            ("الدخول", _fmt_axis_price(analysis_entry) if analysis_entry is not None else "—", (226, 235, 247, 255)),
            ("الوقف", _fmt_axis_price(analysis_stop) if analysis_stop is not None else "—", (244, 103, 103, 255)),
            ("الهدف 1", _fmt_axis_price(analysis_t1) if analysis_t1 is not None else "—", (68, 214, 138, 255)),
            ("القوة", f"{max(0, min(100, strength))}%", accent),
        ]
    elif side in {"buy", "sell"} and code not in {"no_trade", "inactive"}:
        values = [
            ("التفعيل", _fmt_axis_price(trigger) if trigger is not None else "—", (235, 181, 79, 255)),
            ("الإلغاء", _fmt_axis_price(cancel) if cancel is not None else "—", (244, 103, 103, 255)),
            ("الهدف بعد التفعيل", _fmt_axis_price(action_target) if action_target is not None else "—", (68, 214, 138, 255)),
            ("القوة", f"{max(0, min(100, strength))}%", accent),
        ]
    else:
        values = [
            ("السعر الآن", _fmt_axis_price(current) if current is not None else "—", (226, 235, 247, 255)),
            ("التفعيل", "—", (155, 169, 196, 255)),
            ("الهدف", "—", (155, 169, 196, 255)),
            ("القوة", f"{max(0, min(100, strength))}%", accent),
        ]

    cell_left = rect[0] + 28
    cell_right = rect[2] - 28
    cell_w = (cell_right - cell_left) // 4
    y1, y2 = 158, 264
    for i, (label, value, color) in enumerate(values):
        x1 = cell_left + i * cell_w
        x2 = cell_left + (i + 1) * cell_w - 8
        draw.rounded_rectangle((x1, y1, x2, y2), radius=12, fill=(12, 31, 53, 235), outline=(74, 96, 125, 110), width=1)
        _draw_rtl(draw, (x2 - 12, y1 + 18), label, F_SMALL_BOLD, MUTED, anchor="ra")
        draw.text((x2 - 12, y2 - 20), value, font=F_TOP_VALUE_LATIN, fill=color, anchor="rs")


def _candle_slot_geometry(candles: list[dict[str, Any]]) -> tuple[float, int]:
    count = max(1, len(candles))
    candle_right = int(CHART[0] + (CHART[2] - CHART[0]) * 0.70)
    slot = (candle_right - CHART[0]) / count
    return slot, candle_right


def _reference_style_sr_levels(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    """Show only active S/R on the correct side of the current price."""
    current = _number(analysis.get("current_price"))
    if current is None:
        return
    specs = (
        ("resistance_levels", "R", (176, 67, 75, 150), lambda price: price > current),
        ("support_levels", "S", (54, 112, 190, 150), lambda price: price < current),
    )
    for key, prefix, color, valid_side in specs:
        shown_rank = 0
        for level in list(analysis.get(key) or []):
            price = _number(level.get("price")) if isinstance(level, dict) else None
            if price is None or not valid_side(float(price)) or not (price_min <= float(price) <= price_max):
                continue
            shown_rank += 1
            y = _price_y(float(price), price_min, price_max)
            draw.line((CHART[0] + 10, y, CHART[2] - 4, y), fill=color, width=2)
            draw.text((WIDTH - 16, y), f"{prefix}{shown_rank} {_fmt_axis_price(float(price))}", font=F_AXIS_EDGE, fill=color, anchor="rm")
            if shown_rank >= 2:
                break


def _reference_style_zones(image: Image.Image, draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    candles = _valid_renderer_candles(analysis)
    if not candles:
        return
    slot, _candle_right = _candle_slot_geometry(candles)
    entry = _number(analysis.get("entry"))
    current = _number(analysis.get("current_price"))
    focal_price = entry if entry is not None else (current if current is not None else float(candles[-1]["close"]))
    atr = median([max(0.01, float(c["high"]) - float(c["low"])) for c in candles]) if candles else 0.5

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    zone_right = CHART[2] - 16
    scenario_left = max(CHART[0] + 600, zone_right - 190)

    ob = _nearest_detected_order_block(analysis, candles, float(focal_price), float(atr))
    if ob is not None:
        index, low, high, _strength = ob
        y1, y2 = sorted((_price_y(high, price_min, price_max), _price_y(low, price_min, price_max)))
        center_y = (y1 + y2) // 2
        height = max(48, min(96, y2 - y1 + 16))
        y1, y2 = center_y - height // 2, center_y + height // 2
        x1 = max(CHART[0] + 110, int(CHART[0] + slot * max(0, index - 0.25)))
        x2 = min(zone_right, x1 + 330)
        if x1 < scenario_left - 80:
            x2 = min(x2, scenario_left - 12)
        if x2 - x1 >= 100:
            ld.rounded_rectangle((x1, y1, x2, y2), radius=7, fill=(54, 67, 88, 72), outline=(164, 174, 194, 70), width=1)
            # Keep the text quiet and left of the scenario whenever possible.
            ld.text((x1 + 12, center_y), "ORDER BLOCK", font=F_ZONE, fill=(196, 208, 223, 190), anchor="lm")

    fvg = _nearest_detected_fvg(candles, float(focal_price), float(atr))
    if fvg is not None:
        index, low, high = fvg
        center_price = (low + high) / 2
        recent_enough = index >= max(0, len(candles) - 14)
        close_enough = abs(center_price - float(focal_price)) <= max(float(atr) * 3.5, 0.8)
        if recent_enough and close_enough:
            y1, y2 = sorted((_price_y(high, price_min, price_max), _price_y(low, price_min, price_max)))
            center_y = (y1 + y2) // 2
            x1 = max(CHART[0] + 90, int(CHART[0] + slot * max(0, index - 0.15)))
            x2 = min(scenario_left - 18, x1 + 160)
            if x2 - x1 >= 64:
                _dash_line(ld, (x1, center_y), (x2, center_y), (225, 231, 239, 210), width=2, dash=9, gap=6)
                ld.text((x2 + 10, center_y), "FVG", font=F_TRADE_SMALL_LATIN, fill=(235, 240, 247, 225), anchor="lm")

    image.alpha_composite(layer)

def _rect_overlap_area(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    if right <= left or bottom <= top:
        return 0
    return (right - left) * (bottom - top)


def _structure_candidate_box(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    label: str,
    side: str,
    span: int,
) -> tuple[int, int, int, int]:
    font = F_TRADE_SMALL_LATIN
    text_box = draw.textbbox((0, 0), label, font=font)
    text_w = max(38, text_box[2] - text_box[0])
    text_h = max(16, text_box[3] - text_box[1])
    if side == "left":
        line_end = max(CHART[0] + 52, x - span)
        text_right = line_end - 8
        text_left = text_right - text_w
        left = text_left - 6
        right = x + 12
    else:
        line_end = min(CHART[2] - 104, x + span)
        text_left = line_end + 8
        text_right = text_left + text_w
        left = x - 12
        right = text_right + 6
    top = y - max(10, text_h // 2 + 6)
    bottom = y + max(10, text_h // 2 + 6)
    return (left, top, right, bottom)

def _structure_line(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    label: str,
    *,
    occupied: list[tuple[int, int, int, int]] | None = None,
    blocked: list[tuple[int, int, int, int]] | None = None,
    point_fill=(188, 196, 210, 240),
) -> tuple[int, int, int, int]:
    """Draw a secondary structure marker, flipping its side when crowded.

    The true structure level is preserved, but the visible marker is clamped
    inside the chart so BOS/CHOCH/IDM can never be clipped by the header or
    bottom edge.
    """
    occupied = occupied or []
    blocked = blocked or []
    chart_mid = (CHART[0] + CHART[2]) // 2
    preferred = "left" if x > chart_mid + 40 else "right"
    alternate = "right" if preferred == "left" else "left"
    span = 104 if label in {"BOS", "IDM"} else 124

    true_y = int(y)
    margin_y = 22
    display_y = max(CHART[1] + margin_y, min(CHART[3] - margin_y, true_y))
    if display_y != true_y:
        draw.line((x, true_y, x, display_y), fill=(173, 184, 199, 150), width=1)

    candidates: list[tuple[int, str, tuple[int, int, int, int]]] = []
    for side in (preferred, alternate):
        box = _structure_candidate_box(draw, x, display_y, label, side, span)
        overlap = sum(_rect_overlap_area(box, other) for other in occupied)
        overlap += sum(_rect_overlap_area(box, other) for other in blocked)
        # Strongly penalize any label/leader that would leave the chart.
        if box[0] < CHART[0] + 6 or box[2] > CHART[2] - 6:
            overlap += 100000
        candidates.append((overlap, side, box))

    _score, side, box = min(candidates, key=lambda item: item[0])

    radius = 9
    draw.ellipse(
        (x - radius, display_y - radius, x + radius, display_y + radius),
        fill=point_fill,
        outline=(245, 248, 252, 235),
        width=2,
    )
    line_color = (205, 214, 226, 195)
    text_color = (235, 240, 247, 235)
    font = F_TRADE_SMALL_LATIN
    if side == "left":
        x2 = max(CHART[0] + 52, x - span)
        _dash_line(draw, (x - radius - 3, display_y), (x2, display_y), line_color, width=2, dash=8, gap=5)
        draw.text((x2 - 8, display_y), label, font=font, fill=text_color, anchor="rm")
    else:
        x2 = min(CHART[2] - 104, x + span)
        _dash_line(draw, (x + radius + 3, display_y), (x2, display_y), line_color, width=2, dash=8, gap=5)
        draw.text((x2 + 8, display_y), label, font=font, fill=text_color, anchor="lm")
    return box

def _latest_internal_swing(
    candles: list[dict[str, Any]],
    swings: list[tuple[int, float]],
    choch_idx: int,
    bos_idx: int,
    *,
    lookback: int = 12,
) -> tuple[int, float] | None:
    """Return a recent *real* internal swing immediately before BOS.

    IDM is intentionally omitted when there is no genuine local swing in the
    recent structure window; drawing an old distant low/high is worse than not
    drawing IDM at all.
    """
    if bos_idx <= 1:
        return None
    lo = max(1, bos_idx - max(8, min(12, lookback)))
    if choch_idx < bos_idx:
        lo = max(lo, choch_idx + 1)
    hi = min(len(candles) - 2, bos_idx - 1)
    if lo > hi:
        return None
    candidates = [(idx, price) for idx, price in swings if lo <= idx <= hi]
    return candidates[-1] if candidates else None

def _reference_style_structure(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    candles = _valid_renderer_candles(analysis)
    if len(candles) < 6:
        return

    highs, lows = _simple_swing_points(candles, window=2)
    internal_highs, internal_lows = _simple_swing_points(candles, window=1)
    slot, _candle_right = _candle_slot_geometry(candles)
    direction = _reference_direction(analysis)

    # Structure labels must describe the current leg, never an old distant move.
    recent_floor = max(0, len(candles) - 18)
    recent_highs = [item for item in highs if item[0] >= recent_floor]
    recent_lows = [item for item in lows if item[0] >= recent_floor]
    recent_end = len(candles) - 2

    data: list[tuple[int, float, str]] = []
    if direction == "هابط":
        low_idx, low_price = recent_lows[-1] if recent_lows else (
            max(3, recent_end - 3), min(float(c["low"]) for c in candles[-6:])
        )
        # CHOCH is the immediately preceding meaningful low in the same recent leg.
        prior_lows = [item for item in recent_lows if max(recent_floor, low_idx - 12) <= item[0] <= low_idx - 3]
        choch = prior_lows[-1] if prior_lows else None
        if choch is not None:
            data.append((choch[0], choch[1], "CHOCH"))
        data.append((low_idx, low_price, "BOS"))
        idm_start = choch[0] if choch is not None else max(recent_floor, low_idx - 12)
        idm = _latest_internal_swing(candles, internal_highs, idm_start, low_idx)
        if idm is not None:
            data.append((idm[0], idm[1], "IDM"))
    else:
        high_idx, high_price = recent_highs[-1] if recent_highs else (
            max(3, recent_end - 3), max(float(c["high"]) for c in candles[-6:])
        )
        # CHOCH is the immediately preceding meaningful high in the same recent leg.
        prior_highs = [item for item in recent_highs if max(recent_floor, high_idx - 12) <= item[0] <= high_idx - 3]
        choch = prior_highs[-1] if prior_highs else None
        if choch is not None:
            data.append((choch[0], choch[1], "CHOCH"))
        data.append((high_idx, high_price, "BOS"))
        idm_start = choch[0] if choch is not None else max(recent_floor, high_idx - 12)
        idm = _latest_internal_swing(candles, internal_lows, idm_start, high_idx)
        if idm is not None:
            data.append((idm[0], idm[1], "IDM"))

    chart_width = CHART[2] - CHART[0]
    trade_block = (int(CHART[0] + chart_width * 0.72), CHART[1] + 90, CHART[2], CHART[3] - 70)
    occupied: list[tuple[int, int, int, int]] = []
    for idx2, price2, label in data:
        if idx2 < recent_floor:
            continue
        y2 = _price_y(float(price2), price_min, price_max)
        x2 = int(CHART[0] + slot * (idx2 + 0.5))
        x2 = max(CHART[0] + 16, min(CHART[2] - 16, x2))
        box = _structure_line(draw, x2, y2, label, occupied=occupied, blocked=[trade_block])
        occupied.append(box)


def _reference_style_trade_overlay(image: Image.Image, draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    action = analysis.get("action_summary") if isinstance(analysis.get("action_summary"), dict) else {}
    code = str(action.get("code") or analysis.get("draw_mode") or "watch")
    side = str(action.get("primary_side") or "wait")
    confirmed = bool(action.get("is_confirmed")) or code in {"buy", "sell", "confirmed"}

    # Never draw an execution box when the headline says no trade.
    if code in {"inactive", "no_trade", "watch"} or side == "wait":
        return

    # A conditional idea shows only the activation/cancel guide. TP/SL candles are
    # reserved for a confirmed trade so the picture cannot imply an entry early.
    if not confirmed:
        trigger = _number(action.get("trigger"))
        cancel = _number(action.get("cancel"))
        if trigger is None:
            return
        trigger_y = _price_y(float(trigger), price_min, price_max)
        guide_color = (235, 147, 45, 230)
        _dash_line(draw, (CHART[0] + 460, trigger_y), (CHART[2] - 12, trigger_y), guide_color, width=2, dash=9, gap=6)
        label = "تفعيل شراء" if side == "buy" else "تفعيل بيع"
        _draw_rtl(draw, (CHART[2] - 24, trigger_y - 12), f"{label} {_fmt_axis_price(float(trigger))}", F_SMALL_BOLD, guide_color, anchor="ra")
        if cancel is not None and price_min <= float(cancel) <= price_max:
            cancel_y = _price_y(float(cancel), price_min, price_max)
            _dash_line(draw, (CHART[0] + 520, cancel_y), (CHART[2] - 12, cancel_y), (224, 94, 94, 175), width=1, dash=8, gap=7)
        return

    current = _number(analysis.get("current_price"))
    entry = _number(analysis.get("entry"))
    stop = _number(analysis.get("stop_loss"))
    t1 = _number(analysis.get("target_1"))
    t2 = _number(analysis.get("target_2"))
    t3 = _number(analysis.get("target_3"))
    primary_target = t3 or t2 or t1
    if entry is None:
        entry = current
    if entry is None:
        return

    direction = _reference_direction(analysis, entry=entry, target=primary_target, stop=stop)
    span = max(0.5, price_max - price_min)
    if stop is None:
        stop = entry - span * 0.07 if direction == "صاعد" else entry + span * 0.07
    if primary_target is None:
        primary_target = entry + span * 0.14 if direction == "صاعد" else entry - span * 0.14

    targets: list[float] = [float(v) for v in (t1, t2, t3) if v is not None and price_min <= float(v) <= price_max]
    if len(targets) < 3:
        distance = float(primary_target) - float(entry)
        targets = [float(entry) + distance * r for r in (0.36, 0.68, 1.0)]

    # A compact scenario area near the latest candles; it should explain, not cover, the chart.
    zone_right = CHART[2] - 16
    zone_width = 190
    zone_left = max(CHART[0] + 600, zone_right - zone_width)
    entry_y = _price_y(float(entry), price_min, price_max)
    stop_y = _price_y(float(stop), price_min, price_max)
    target_y = _price_y(float(primary_target), price_min, price_max)

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    risk_fill = (189, 66, 56, 108)
    reward_fill = (15, 117, 79, 102)
    if direction == "هابط":
        ld.rounded_rectangle((zone_left, min(stop_y, entry_y), zone_right, max(stop_y, entry_y)), radius=8, fill=risk_fill)
        ld.rounded_rectangle((zone_left, min(target_y, entry_y), zone_right, max(target_y, entry_y)), radius=8, fill=reward_fill)
    else:
        ld.rounded_rectangle((zone_left, min(target_y, entry_y), zone_right, max(target_y, entry_y)), radius=8, fill=reward_fill)
        ld.rounded_rectangle((zone_left, min(stop_y, entry_y), zone_right, max(stop_y, entry_y)), radius=8, fill=risk_fill)
    image.alpha_composite(layer)

    # Exact execution levels across the scenario area.
    _dash_line(draw, (zone_left - 22, entry_y), (zone_right, entry_y), (242, 245, 248, 235), width=2, dash=8, gap=5)
    _dash_line(draw, (zone_left - 12, stop_y), (zone_right, stop_y), (238, 95, 95, 210), width=1, dash=8, gap=6)
    target_colors = ((61, 207, 131, 230), (43, 181, 108, 230), (27, 154, 91, 230))
    target_y_values: list[int] = []
    for idx, value in enumerate(targets[:3], start=1):
        y = _price_y(value, price_min, price_max)
        target_y_values.append(y)
        _dash_line(draw, (zone_left - 12, y), (zone_right, y), target_colors[idx - 1], width=1, dash=8, gap=6)

    # Short expected candle path: easy to understand for a trader at a glance.
    end_target_y = target_y_values[-1] if target_y_values else target_y
    candle_count = 5
    for i in range(candle_count):
        ratio = (i + 1) / candle_count
        x = int(zone_left + 34 + ratio * max(50, zone_width - 64))
        base_y = int(entry_y + (end_target_y - entry_y) * ratio)
        wave = (-1 if i % 2 == 0 else 1) * min(14, max(5, abs(end_target_y - entry_y) // 20))
        close_y = base_y + wave
        open_y = entry_y if i == 0 else int(entry_y + (end_target_y - entry_y) * (i / candle_count)) - wave
        body_top, body_bottom = sorted((open_y, close_y))
        if body_bottom - body_top < 8:
            body_bottom = body_top + 8
        candle_color = (79, 201, 184, 215) if close_y < open_y else (239, 104, 98, 215)
        draw.line((x, body_top - 12, x, body_bottom + 12), fill=(222, 229, 237, 130), width=2)
        draw.rounded_rectangle((x - 6, body_top, x + 6, body_bottom), radius=2, fill=candle_color)

    # Small in-chart labels make the setup understandable without recreating
    # the old large right-axis cards.
    def draw_trade_tag(y: int, text_value: str, fill: tuple[int, int, int, int], *, width: int = 154) -> None:
        tag_h = 34
        x2 = zone_right - 4
        x1 = max(zone_left + 18, x2 - width)
        yy = max(CHART[1] + tag_h // 2 + 4, min(CHART[3] - tag_h // 2 - 4, y))
        draw.rounded_rectangle((x1, yy - tag_h // 2, x2, yy + tag_h // 2), radius=6, fill=fill, outline=(245, 248, 252, 150), width=1)
        draw.text(((x1 + x2) // 2, yy), text_value, font=F_TRADE_SMALL_LATIN, fill=WHITE, anchor="mm")

    draw_trade_tag(entry_y, f"ENTRY {_fmt_axis_price(entry)}", (21, 126, 91, 230), width=166)
    draw_trade_tag(stop_y, f"SL {_fmt_axis_price(stop)}", (190, 52, 56, 232), width=148)
    if targets and target_y_values:
        draw_trade_tag(target_y_values[0], f"TP1 {_fmt_axis_price(targets[0])}", (18, 139, 84, 232), width=158)

    # Colored text on the spare right margin, aligned with the true price level.
    axis_x = WIDTH - 14
    draw.text((axis_x, stop_y), f"وقف {_fmt_axis_price(stop)}", font=F_AXIS_EDGE, fill=(239, 94, 94, 255), anchor="rm")
    draw.text((axis_x, entry_y), f"دخول {_fmt_axis_price(entry)}", font=F_AXIS_EDGE, fill=(104, 170, 255, 255), anchor="rm")
    for idx, (value, y) in enumerate(zip(targets[:3], target_y_values), start=1):
        draw.text((axis_x, y), f"TP{idx} {_fmt_axis_price(value)}", font=F_AXIS_EDGE, fill=target_colors[idx - 1], anchor="rm")

    rr = abs(float(primary_target) - float(entry)) / max(0.01, abs(float(stop) - float(entry)))
    rr_y = max(CHART[1] + 20, min(CHART[3] - 22, end_target_y + (34 if direction == "هابط" else -34)))
    draw.text((zone_left + 6, rr_y), f"RR {rr:.1f}", font=F_TRADE_LATIN, fill=(225, 231, 239, 240), anchor="la")



# === SaleeM Professional Dashboard v3.42 ===
DASH_CHART = (24, 960, 1120, 2220)
DASH_AXIS_X = 1144

def _dash_price_y(price: float, price_min: float, price_max: float) -> int:
    left, top, right, bottom = DASH_CHART
    ratio = (price_max - float(price)) / max(0.0001, price_max - price_min)
    return int(top + max(0.0, min(1.0, ratio)) * (bottom - top))

def _dash_card(draw: ImageDraw.ImageDraw, box: tuple[int,int,int,int], title: str, value: str, *, value_color=WHITE, subtitle: str | None = None) -> None:
    x1,y1,x2,y2 = box
    draw.rounded_rectangle(box, radius=18, fill=(10,25,43,245), outline=(64,86,112,160), width=1)
    if all(ord(ch) < 128 for ch in title):
        draw.text((x2-18,y1+18), title, font=F_SMALL_BOLD, fill=MUTED, anchor='ra')
    else:
        _draw_rtl(draw, (x2-18,y1+18), title, F_SMALL_BOLD, MUTED, anchor='ra')
    draw.text((x2-18, y1+56), str(value), font=F_CARD_LATIN, fill=value_color, anchor='ra')
    if subtitle:
        _draw_rtl(draw, (x2-18,y2-20), subtitle, F_SMALL, MUTED, anchor='ra')

def _dash_action_state(analysis: dict[str, Any]) -> tuple[str,str,tuple[int,int,int,int],str]:
    action = analysis.get('action_summary') if isinstance(analysis.get('action_summary'), dict) else {}
    code = str(action.get('code') or analysis.get('draw_mode') or 'watch')
    side = str(action.get('primary_side') or ('buy' if str(analysis.get('direction'))=='صاعد' else 'sell' if str(analysis.get('direction'))=='هابط' else 'wait'))
    confirmed = bool(action.get('is_confirmed')) or code in {'buy','sell','confirmed'}
    if confirmed and side == 'buy':
        return 'شراء', 'صفقة شراء مفعّلة', GREEN, 'شراء'
    if confirmed and side == 'sell':
        return 'بيع', 'صفقة بيع مفعّلة', RED, 'بيع'
    if side == 'buy' and code not in {'inactive','no_trade'}:
        return 'مراقبة شراء', 'انتظر تأكيد مستوى الدخول', (30,171,103,255), 'مراقبة'
    if side == 'sell' and code not in {'inactive','no_trade'}:
        return 'مراقبة بيع', 'انتظر تأكيد مستوى الدخول', (219,82,82,255), 'مراقبة'
    return 'مراقبة', 'لا تدخل قبل اكتمال شروط التفعيل', BLUE, 'مراقبة'

def _dash_draw_header(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    state, state_sub, accent, _ = _dash_action_state(analysis)
    # App bar
    draw.rectangle((0,0,WIDTH,190), fill=(3,15,27,255))
    draw.text((38,72), 'SaleeM', font=_font(46,True,True), fill=WHITE, anchor='la')
    draw.text((330,80), f"{analysis.get('symbol') or 'XAUUSD'} / {analysis.get('timeframe') or 'M5'}", font=_font(27,True,True), fill=(210,220,232,255), anchor='la')
    # state panel
    panel=(24,210,1296,530)
    draw.rounded_rectangle(panel, radius=24, fill=(6,23,40,248), outline=(51,80,110,180), width=2)
    # status circle
    cx,cy=120,330
    draw.ellipse((cx-56,cy-56,cx+56,cy+56), outline=accent, width=10)
    draw.ellipse((cx-18,cy-10,cx+18,cy+10), outline=accent, width=4)
    _draw_rtl(draw,(545,270),'الوضع الحالي',F_NOTE,MUTED,anchor='ra')
    _draw_rtl(draw,(545,324),state,_font(34,True),accent,anchor='ra')
    _draw_rtl(draw,(545,376),state_sub,F_NOTE,WHITE,anchor='ra')
    action = analysis.get('action_summary') if isinstance(analysis.get('action_summary'),dict) else {}
    strength=int(action.get('strength') or analysis.get('trade_probability') or 0)
    latest=str(analysis.get('analysis_last_closed_m5_time') or analysis.get('market_m5_latest_candle_time') or '—')
    latest = latest[-8:] if len(latest)>=8 else latest
    _draw_rtl(draw,(1248,270),'آخر تحديث',F_NOTE,MUTED,anchor='ra')
    draw.text((1248,315),latest,font=F_CARD_LATIN,fill=WHITE,anchor='ra')
    _draw_rtl(draw,(1248,382),'قوة السوق',F_NOTE,MUTED,anchor='ra')
    draw.text((1248,432),f'{max(0,min(100,strength))}%',font=F_PERCENT,fill=accent,anchor='ra')
    draw.rounded_rectangle((1000,446,1248,462),radius=8,fill=(39,50,65,255))
    draw.rounded_rectangle((1000,446,1000+int(248*max(0,min(100,strength))/100),462),radius=8,fill=accent)

def _dash_trade_values(analysis: dict[str, Any]) -> list[tuple[str,str,tuple[int,int,int,int],str | None]]:
    action=analysis.get('action_summary') if isinstance(analysis.get('action_summary'),dict) else {}
    code=str(action.get('code') or analysis.get('draw_mode') or 'watch')
    side=str(action.get('primary_side') or 'wait')
    confirmed=bool(action.get('is_confirmed')) or code in {'buy','sell','confirmed'}
    entry=_number(analysis.get('entry')) if confirmed else _number(action.get('trigger'))
    stop=_number(analysis.get('stop_loss')) if confirmed else _number(action.get('cancel'))
    t1=_number(analysis.get('target_1')) if confirmed else _number(action.get('target'))
    t2=_number(analysis.get('target_2')) if confirmed else None
    rr='—'
    if entry is not None and stop is not None and t1 is not None and abs(entry-stop)>0.001:
        rr=f"1 : {abs(t1-entry)/abs(entry-stop):.2f}"
    strength=int(action.get('strength') or analysis.get('trade_probability') or 0)
    return [
        ('ENTRY' if confirmed else 'التفعيل', _fmt_axis_price(entry) if entry is not None else '—', GREEN if side!='sell' else RED, None),
        ('STOP LOSS' if confirmed else 'الإلغاء', _fmt_axis_price(stop) if stop is not None else '—', RED, None),
        ('TP1' if confirmed else 'الهدف', _fmt_axis_price(t1) if t1 is not None else '—', GREEN, None),
        ('TP2', _fmt_axis_price(t2) if t2 is not None else '—', GREEN, None),
        ('RISK / REWARD', rr, PURPLE, None),
        ('الثقة', f'{max(0,min(100,strength))}%', GOLD, 'قوة القراءة'),
    ]

def _dash_draw_trade_cards(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    values=_dash_trade_values(analysis)
    gap=12
    total_w=WIDTH-48
    card_w=(total_w-gap*5)//6
    y1,y2=558,830
    for i,(title,value,color,sub) in enumerate(values):
        x1=24+i*(card_w+gap); x2=x1+card_w
        _dash_card(draw,(x1,y1,x2,y2),title,value,value_color=color,subtitle=sub)

def _dash_draw_chart_base(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    x1,y1,x2,y2=DASH_CHART
    draw.rounded_rectangle((x1-2,y1-2,x2+2,y2+2), radius=18, fill=(4,15,26,255), outline=(42,65,86,180), width=2)
    # grid
    for i in range(1,8):
        x=int(x1+(x2-x1)*i/8); draw.line((x,y1,x,y2),fill=(55,75,95,55),width=1)
    for i in range(1,9):
        y=int(y1+(y2-y1)*i/10); draw.line((x1,y,x2,y),fill=(55,75,95,70),width=1)
    candles=_valid_renderer_candles(analysis)[-42:]
    if not candles:
        return
    slot=(x2-x1-64)/max(1,len(candles))
    body=max(6,min(16,int(slot*0.58)))
    for i,c in enumerate(candles):
        o=_number(c.get('open')); h=_number(c.get('high')); l=_number(c.get('low')); cl=_number(c.get('close'))
        if None in (o,h,l,cl): continue
        x=int(x1+30+(i+0.5)*slot)
        yo=_dash_price_y(o,price_min,price_max); yh=_dash_price_y(h,price_min,price_max); yl=_dash_price_y(l,price_min,price_max); yc=_dash_price_y(cl,price_min,price_max)
        color=(61,188,158,255) if cl>=o else (232,82,74,255)
        draw.line((x,yh,x,yl),fill=color,width=2)
        top,bottom=sorted((yo,yc)); bottom=max(bottom,top+4)
        draw.rectangle((x-body//2,top,x+body//2,bottom),fill=color)
    current=_number(analysis.get('current_price'))
    if current is not None and price_min<=current<=price_max:
        y=_dash_price_y(current,price_min,price_max)
        _dash_line(draw,(x1,y),(x2,y),(61,190,171,210),width=2,dash=7,gap=5)
        draw.rounded_rectangle((1128,y-32,1296,y+32),radius=8,fill=(38,139,119,240))
        draw.text((1212,y-7),_fmt_axis_price(current),font=F_CARD_LATIN,fill=WHITE,anchor='mm')

def _dash_draw_sr(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    current=_number(analysis.get('current_price'))
    for key,prefix,color in [('resistance_levels','R',RED),('support_levels','S',BLUE)]:
        rank=0
        for lvl in list(analysis.get(key) or []):
            price=_number(lvl.get('price'))
            if price is None or not(price_min<=price<=price_max): continue
            if current is not None:
                if prefix=='R' and price<=current: continue
                if prefix=='S' and price>=current: continue
            rank+=1
            if rank>2: break
            y=_dash_price_y(price,price_min,price_max)
            draw.line((DASH_CHART[0],y,DASH_CHART[2],y),fill=(color[0],color[1],color[2],180),width=2)
            draw.rounded_rectangle((1148,y-23,1294,y+23),radius=7,fill=(color[0],color[1],color[2],220))
            draw.text((1280,y),f'{prefix}{rank} {_fmt_axis_price(price)}',font=F_TRADE_SMALL_LATIN,fill=WHITE,anchor='rm')

def _dash_recent_swings(candles: list[dict[str,Any]]) -> tuple[list[tuple[int,float]],list[tuple[int,float]]]:
    highs=[]; lows=[]
    if len(candles)<5: return highs,lows
    for i in range(2,len(candles)-2):
        h=float(candles[i]['high']); l=float(candles[i]['low'])
        if h>=max(float(candles[j]['high']) for j in range(i-2,i+3)): highs.append((i,h))
        if l<=min(float(candles[j]['low']) for j in range(i-2,i+3)): lows.append((i,l))
    return highs,lows

def _dash_structure_marker(draw: ImageDraw.ImageDraw, x:int,y:int,label:str, *, prefer_left=False) -> None:
    radius=8
    draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=(223,230,238,255),outline=(40,55,70,255),width=1)
    if prefer_left:
        x2=max(DASH_CHART[0]+70,x-125); _dash_line(draw,(x-10,y),(x2,y),WHITE,width=2,dash=7,gap=5); draw.text((x2-8,y),label,font=F_TRADE_SMALL_LATIN,fill=WHITE,anchor='rm')
    else:
        x2=min(DASH_CHART[2]-80,x+125); _dash_line(draw,(x+10,y),(x2,y),WHITE,width=2,dash=7,gap=5); draw.text((x2+8,y),label,font=F_TRADE_SMALL_LATIN,fill=WHITE,anchor='lm')

def _dash_draw_structure(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    candles=_valid_renderer_candles(analysis)[-34:]
    if len(candles)<8: return
    highs,lows=_dash_recent_swings(candles)
    slot=(DASH_CHART[2]-DASH_CHART[0]-64)/len(candles)
    def pos(idx,price): return int(DASH_CHART[0]+30+(idx+0.5)*slot), _dash_price_y(price,price_min,price_max)
    direction=str(analysis.get('direction') or analysis.get('analysis_direction') or '')
    # choose only recent structure points; no stale labels
    recent_start=max(0,len(candles)-14)
    rh=[p for p in highs if p[0]>=recent_start]; rl=[p for p in lows if p[0]>=recent_start]
    if direction=='صاعد':
        bos=(rh[-1] if rh else None); choch=(rl[-1] if rl else None); idm=(rl[-2] if len(rl)>=2 else None)
    else:
        bos=(rl[-1] if rl else None); choch=(rh[-1] if rh else None); idm=(rh[-2] if len(rh)>=2 else None)
    used=[]
    for label,item in [('BOS',bos),('CHOCH',choch),('IDM',idm)]:
        if not item: continue
        x,y=pos(*item)
        prefer_left = x>DASH_CHART[0]+(DASH_CHART[2]-DASH_CHART[0])*0.62 or any(abs(y-uy)<58 for _,uy in used)
        _dash_structure_marker(draw,x,y,label,prefer_left=prefer_left)
        used.append((x,y))

def _dash_draw_zones(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    current=_number(analysis.get('current_price'))
    # Lightweight OB/FVG derived from latest candles so they look like chart tools.
    candles=_valid_renderer_candles(analysis)[-18:]
    if len(candles)<6: return
    direction=str(analysis.get('direction') or '')
    anchor=max(0,len(candles)-8)
    c=candles[anchor]
    high=_number(c.get('high')); low=_number(c.get('low'))
    if high is not None and low is not None:
        y1=_dash_price_y(high,price_min,price_max); y2=_dash_price_y(low,price_min,price_max)
        left=int(DASH_CHART[0]+(DASH_CHART[2]-DASH_CHART[0])*0.44); right=int(DASH_CHART[0]+(DASH_CHART[2]-DASH_CHART[0])*0.66)
        draw.rounded_rectangle((left,min(y1,y2),right,max(y1,y2)),radius=5,fill=(57,79,106,100),outline=(91,119,153,120),width=1)
        draw.text(((left+right)//2,(y1+y2)//2),'ORDER BLOCK',font=F_TRADE_SMALL_LATIN,fill=(210,219,230,230),anchor='mm')
    # FVG under/over current based on direction, only near current.
    if current is not None:
        delta=max(0.45,(price_max-price_min)*0.035)
        center=current-delta*2.3 if direction=='صاعد' else current+delta*2.3
        if price_min<center<price_max:
            ya=_dash_price_y(center+delta/2,price_min,price_max); yb=_dash_price_y(center-delta/2,price_min,price_max)
            left=int(DASH_CHART[0]+(DASH_CHART[2]-DASH_CHART[0])*0.31); right=int(DASH_CHART[0]+(DASH_CHART[2]-DASH_CHART[0])*0.58)
            draw.rectangle((left,min(ya,yb),right,max(ya,yb)),fill=(197,124,53,42),outline=(222,145,63,145),width=1)
            draw.text(((left+right)//2,(ya+yb)//2),'FVG',font=F_TRADE_SMALL_LATIN,fill=(232,213,192,240),anchor='mm')

def _dash_draw_scenario(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    action=analysis.get('action_summary') if isinstance(analysis.get('action_summary'),dict) else {}
    code=str(action.get('code') or analysis.get('draw_mode') or 'watch')
    side=str(action.get('primary_side') or ('buy' if str(analysis.get('direction'))=='صاعد' else 'sell' if str(analysis.get('direction'))=='هابط' else 'wait'))
    confirmed=bool(action.get('is_confirmed')) or code in {'buy','sell','confirmed'}
    entry=_number(analysis.get('entry')) if confirmed else _number(action.get('trigger'))
    stop=_number(analysis.get('stop_loss')) if confirmed else _number(action.get('cancel'))
    targets=[]
    if confirmed:
        targets=[_number(analysis.get(k)) for k in ('target_1','target_2','target_3')]
    else:
        targets=[_number(action.get('target'))]
    targets=[v for v in targets if v is not None]
    if entry is None or stop is None or not targets or side=='wait': return
    # Validate trade geometry before drawing.
    bullish=side=='buy' or (side not in {'buy','sell'} and targets[0]>entry)
    if bullish and not(stop<entry<max(targets)): return
    if not bullish and not(stop>entry>min(targets)): return
    x1,x2=840,1100
    ey=_dash_price_y(entry,price_min,price_max); sy=_dash_price_y(stop,price_min,price_max); ty=_dash_price_y(targets[-1],price_min,price_max)
    reward=(20,152,94,75); risk=(209,65,61,80)
    draw.rectangle((x1,min(ey,ty),x2,max(ey,ty)),fill=reward)
    draw.rectangle((x1,min(ey,sy),x2,max(ey,sy)),fill=risk)
    _dash_line(draw,(x1,ey),(x2,ey),WHITE,width=2,dash=8,gap=5)
    def tag(y,label,color):
        draw.rounded_rectangle((1010,y-22,1112,y+22),radius=7,fill=color)
        draw.text((1061,y),label,font=F_TRADE_SMALL_LATIN,fill=WHITE,anchor='mm')
    tag(ey,f"ENTRY {_fmt_axis_price(entry)}",(20,135,91,245))
    tag(sy,f"SL {_fmt_axis_price(stop)}",(196,55,55,245))
    for i,t in enumerate(targets[:3],1):
        y=_dash_price_y(t,price_min,price_max); _dash_line(draw,(x1,y),(x2,y),(35,190,109,200),width=1,dash=8,gap=5); tag(y,f"TP{i} {_fmt_axis_price(t)}",(22,151,88,245))
    # expected path only on valid active/conditional geometry
    endy=_dash_price_y(targets[-1],price_min,price_max)
    pts=[]
    for i in range(6):
        r=i/5; x=int(860+r*205); base=int(ey+(endy-ey)*r); wobble=(-1 if i%2 else 1)*10; pts.append((x,base+wobble))
    for a,b in zip(pts[:-1],pts[1:]): _dash_line(draw,a,b,(226,234,240,210),width=2,dash=8,gap=5)

def _dash_draw_timeframes(draw: ImageDraw.ImageDraw) -> None:
    y1,y2=2240,2340
    draw.rounded_rectangle((24,y1,1296,y2),radius=18,fill=(6,21,37,250),outline=(39,60,80,150),width=1)
    labels=['M1','M5','M15','H1','H4','D1']
    x=90
    for label in labels:
        if label=='M5': draw.rounded_rectangle((x-26,y1+14,x+70,y2-14),radius=12,fill=(19,65,121,255))
        draw.text((x+20,(y1+y2)//2),label,font=F_CARD_LATIN,fill=(80,158,255,255) if label=='M5' else (188,199,211,255),anchor='mm')
        x+=170

def _dash_analysis_value(analysis: dict[str,Any], key: str, fallback: str) -> str:
    v=analysis.get(key)
    if isinstance(v,(str,int,float)) and str(v).strip(): return str(v)
    return fallback

def _dash_draw_bottom_cards(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    direction=str(analysis.get('direction') or analysis.get('analysis_direction') or 'غير واضح')
    items=[
        ('الاتجاه',direction,GREEN if direction=='صاعد' else RED if direction=='هابط' else GOLD),
        ('البنية',_dash_analysis_value(analysis,'structure','متابعة'),BLUE),
        ('الزخم',_dash_analysis_value(analysis,'momentum','متوسط'),GOLD),
        ('شكل الشمعة',_dash_analysis_value(analysis,'candle_shape','مراقبة'),GREEN),
        ('الإغلاق',_dash_analysis_value(analysis,'close_behavior','محايد'),GOLD),
        ('المنطقة',_dash_analysis_value(analysis,'zone_behavior','بين مستويات'),BLUE),
    ]
    gap=12; total=WIDTH-48; w=(total-gap*5)//6; y1,y2=2360,2610
    for i,(title,val,color) in enumerate(items):
        x1=24+i*(w+gap); x2=x1+w
        draw.rounded_rectangle((x1,y1,x2,y2),radius=18,fill=(8,24,41,248),outline=(43,65,85,170),width=1)
        _draw_rtl(draw,(x2-14,y1+35),title,F_SMALL_BOLD,MUTED,anchor='ra')
        _draw_rtl(draw,(x2-14,y1+100),_fit_text(draw,val,F_NOTE_BOLD,w-28,rtl=True),F_NOTE_BOLD,color,anchor='ra')

def _dash_draw_nav(draw: ImageDraw.ImageDraw) -> None:
    y1=2640
    draw.rectangle((0,y1,WIDTH,HEIGHT),fill=(3,14,25,255))
    labels=['الرئيسية','السجل','التحليل','تنبيهات','المفضلة']
    for i,label in enumerate(labels):
        cx=int((i+0.5)*WIDTH/5)
        if label=='التحليل': draw.rounded_rectangle((cx-62,y1+32,cx+62,y1+150),radius=18,fill=(12,51,95,255))
        draw.ellipse((cx-13,y1+52,cx+13,y1+78),outline=(72,142,240,255) if label=='التحليل' else (147,160,174,255),width=3)
        _draw_rtl(draw,(cx,y1+116),label,F_SMALL_BOLD,(72,142,240,255) if label=='التحليل' else (170,180,192,255),anchor='ma')

def _render_professional_dashboard(analysis: dict[str, Any]) -> bytes:
    image=Image.new('RGBA',(WIDTH,HEIGHT),(3,14,25,255))
    draw=ImageDraw.Draw(image)
    price_min,price_max=_price_range(analysis)
    # Ensure the visible chart includes useful trade and nearby levels rather than full image extremes.
    vals=[]
    for k in ('current_price','entry','stop_loss','target_1','target_2','target_3'):
        v=_number(analysis.get(k));
        if v is not None: vals.append(v)
    for key in ('support_levels','resistance_levels'):
        for lvl in list(analysis.get(key) or [])[:2]:
            v=_number(lvl.get('price'));
            if v is not None: vals.append(v)
    candles=_valid_renderer_candles(analysis)[-42:]
    for c in candles:
        for k in ('high','low'):
            v=_number(c.get(k));
            if v is not None: vals.append(v)
    if vals:
        lo,hi=min(vals),max(vals); span=max(3.0,hi-lo); pad=span*0.08; price_min,price_max=lo-pad,hi+pad
    _dash_draw_header(draw,analysis)
    _dash_draw_trade_cards(draw,analysis)
    _dash_draw_chart_base(draw,analysis,price_min,price_max)
    _dash_draw_sr(draw,analysis,price_min,price_max)
    _dash_draw_zones(draw,analysis,price_min,price_max)
    _dash_draw_structure(draw,analysis,price_min,price_max)
    _dash_draw_scenario(draw,analysis,price_min,price_max)
    _dash_draw_timeframes(draw)
    _dash_draw_bottom_cards(draw,analysis)
    _dash_draw_nav(draw)
    out=io.BytesIO(); image.convert('RGB').save(out,format='PNG',optimize=True); return out.getvalue()

SCROLL_CHART_WIDTH = 2200
SCROLL_CHART_HEIGHT = 1050
SCROLL_PLOT = (54, 68, 1990, 940)
SCROLL_AXIS_X = 2015


def _scroll_price_y(price: float, price_min: float, price_max: float) -> int:
    top, bottom = SCROLL_PLOT[1], SCROLL_PLOT[3]
    ratio = (price_max - float(price)) / max(0.0001, price_max - price_min)
    return int(round(top + ratio * (bottom - top)))


def _scroll_chart_range(analysis: dict[str, Any], candles: list[dict[str, Any]]) -> tuple[float, float]:
    values: list[float] = []
    for candle in candles:
        for key in ('high', 'low'):
            value = _number(candle.get(key))
            if value is not None:
                values.append(float(value))
    for key in ('current_price', 'entry', 'stop_loss', 'target_1', 'target_2', 'target_3'):
        value = _number(analysis.get(key))
        if value is not None:
            values.append(float(value))
    for key in ('support_levels', 'resistance_levels'):
        for level in list(analysis.get(key) or [])[:2]:
            value = _number(level.get('price'))
            if value is not None:
                values.append(float(value))
    if not values:
        return 0.0, 1.0
    lo, hi = min(values), max(values)
    span = max(2.0, hi - lo)
    return lo - span * 0.08, hi + span * 0.08


def _scroll_x_for_index(index: int, count: int) -> int:
    left, _, right, _ = SCROLL_PLOT
    usable = right - left - 70
    slot = usable / max(1, count)
    return int(left + 32 + (index + 0.5) * slot)


def _scroll_draw_axis(draw: ImageDraw.ImageDraw, price_min: float, price_max: float) -> None:
    left, top, right, bottom = SCROLL_PLOT
    draw.rectangle((left, top, right, bottom), fill=(250, 252, 255, 255), outline=(196, 205, 217, 255), width=2)
    for i in range(1, 10):
        x = int(left + (right - left) * i / 10)
        draw.line((x, top, x, bottom), fill=(220, 226, 234, 210), width=1)
    for i in range(1, 9):
        y = int(top + (bottom - top) * i / 9)
        draw.line((left, y, right, y), fill=(220, 226, 234, 220), width=1)
    for i in range(10):
        ratio = i / 9
        price = price_max - (price_max - price_min) * ratio
        y = int(top + (bottom - top) * ratio)
        draw.line((right, y, right + 10, y), fill=(135, 145, 158, 255), width=1)
        draw.text((SCROLL_AXIS_X, y), _fmt_axis_price(price), font=_font(24, False, True), fill=(50, 57, 66, 255), anchor='lm')


def _scroll_draw_candles(draw: ImageDraw.ImageDraw, candles: list[dict[str, Any]], price_min: float, price_max: float) -> None:
    count = len(candles)
    if not count:
        return
    slot = (SCROLL_PLOT[2] - SCROLL_PLOT[0] - 70) / max(1, count)
    body_w = max(7, min(20, int(slot * 0.56)))
    for index, candle in enumerate(candles):
        o = _number(candle.get('open')); h = _number(candle.get('high')); l = _number(candle.get('low')); c = _number(candle.get('close'))
        if None in (o, h, l, c):
            continue
        x = _scroll_x_for_index(index, count)
        yo = _scroll_price_y(float(o), price_min, price_max)
        yh = _scroll_price_y(float(h), price_min, price_max)
        yl = _scroll_price_y(float(l), price_min, price_max)
        yc = _scroll_price_y(float(c), price_min, price_max)
        color = (25, 167, 122, 255) if c >= o else (231, 53, 55, 255)
        draw.line((x, yh, x, yl), fill=(46, 56, 64, 230), width=2)
        top, bottom = sorted((yo, yc)); bottom = max(bottom, top + 5)
        draw.rectangle((x - body_w // 2, top, x + body_w // 2, bottom), fill=color, outline=(35, 42, 49, 255), width=1)


def _scroll_draw_price_levels(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    current = _number(analysis.get('current_price'))
    plot_left, _, plot_right, _ = SCROLL_PLOT
    specs = [('resistance_levels', 'R', (229, 51, 61, 255), True), ('support_levels', 'S', (35, 113, 235, 255), False)]
    for key, prefix, color, is_resistance in specs:
        rank = 0
        for level in list(analysis.get(key) or []):
            price = _number(level.get('price'))
            if price is None or not (price_min <= price <= price_max):
                continue
            if current is not None:
                if is_resistance and price <= current:
                    continue
                if not is_resistance and price >= current:
                    continue
            rank += 1
            if rank > 2:
                break
            y = _scroll_price_y(price, price_min, price_max)
            draw.line((plot_left, y, plot_right, y), fill=color, width=2)
            label = f'{prefix}{rank} {_fmt_axis_price(price)}'
            bbox = draw.textbbox((0, 0), label, font=_font(22, True, True))
            w = bbox[2] - bbox[0] + 24
            x1 = plot_right - w - 5
            draw.rounded_rectangle((x1, y - 20, plot_right - 4, y + 20), radius=7, fill=color)
            draw.text((plot_right - 14, y), label, font=_font(22, True, True), fill=WHITE, anchor='rm')
    if current is not None and price_min <= current <= price_max:
        y = _scroll_price_y(current, price_min, price_max)
        _dash_line(draw, (plot_left, y), (plot_right, y), (31, 177, 150, 255), width=2, dash=9, gap=6)
        draw.rounded_rectangle((plot_right - 146, y - 27, plot_right - 4, y + 27), radius=7, fill=(28, 164, 135, 255))
        draw.text((plot_right - 16, y), _fmt_axis_price(current), font=_font(23, True, True), fill=WHITE, anchor='rm')


def _scroll_draw_zones(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], candles: list[dict[str, Any]], price_min: float, price_max: float) -> None:
    if len(candles) < 8:
        return
    current = _number(analysis.get('current_price'))
    direction = str(analysis.get('direction') or '')
    anchor = max(0, len(candles) - 11)
    c = candles[anchor]
    high = _number(c.get('high')); low = _number(c.get('low'))
    if high is not None and low is not None:
        y1 = _scroll_price_y(high, price_min, price_max); y2 = _scroll_price_y(low, price_min, price_max)
        left = _scroll_x_for_index(max(0, len(candles) - 25), len(candles))
        right = _scroll_x_for_index(max(1, len(candles) - 10), len(candles))
        draw.rectangle((left, min(y1, y2), right, max(y1, y2)), fill=(83, 145, 235, 45), outline=(61, 123, 220, 180), width=2)
        draw.text(((left + right) // 2, (y1 + y2) // 2), 'ORDER BLOCK', font=_font(20, True, True), fill=(37, 74, 129, 255), anchor='mm')
    if current is not None:
        delta = max(0.35, (price_max - price_min) * 0.022)
        center = current - delta * 3 if direction == 'صاعد' else current + delta * 3
        if price_min < center < price_max:
            ya = _scroll_price_y(center + delta / 2, price_min, price_max); yb = _scroll_price_y(center - delta / 2, price_min, price_max)
            left = _scroll_x_for_index(max(0, len(candles) - 33), len(candles))
            right = _scroll_x_for_index(max(1, len(candles) - 14), len(candles))
            draw.rectangle((left, min(ya, yb), right, max(ya, yb)), fill=(246, 162, 73, 42), outline=(234, 145, 49, 190), width=2)
            draw.text(((left + right) // 2, (ya + yb) // 2), 'FVG', font=_font(20, True, True), fill=(101, 68, 30, 255), anchor='mm')


def _scroll_draw_structure(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], candles: list[dict[str, Any]], price_min: float, price_max: float) -> None:
    highs, lows = _dash_recent_swings(candles)
    if not highs and not lows:
        return
    direction = str(analysis.get('direction') or '')
    recent = max(0, len(candles) - 22)
    rh = [x for x in highs if x[0] >= recent]; rl = [x for x in lows if x[0] >= recent]
    if direction == 'صاعد':
        data = [('BOS', rh[-1] if rh else None), ('CHOCH', rl[-1] if rl else None), ('IDM', rl[-2] if len(rl) > 1 else None)]
    else:
        data = [('BOS', rl[-1] if rl else None), ('CHOCH', rh[-1] if rh else None), ('IDM', rh[-2] if len(rh) > 1 else None)]
    occupied: list[tuple[int, int]] = []
    for label, item in data:
        if item is None:
            continue
        idx, price = item
        x = _scroll_x_for_index(idx, len(candles)); y = _scroll_price_y(price, price_min, price_max)
        radius = 9
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=(248,248,248,255), outline=(35,42,49,255), width=2)
        crowded = any(abs(y-uy) < 55 for _, uy in occupied)
        prefer_left = x > (SCROLL_PLOT[0] + SCROLL_PLOT[2]) // 2 or crowded
        if prefer_left:
            x2 = max(SCROLL_PLOT[0] + 70, x - 150)
            _dash_line(draw, (x-12, y), (x2, y), (45,48,52,255), width=2, dash=8, gap=5)
            draw.text((x2-8, y), label, font=_font(20, True, True), fill=(32,36,40,255), anchor='rm')
        else:
            x2 = min(SCROLL_PLOT[2] - 70, x + 150)
            _dash_line(draw, (x+12, y), (x2, y), (45,48,52,255), width=2, dash=8, gap=5)
            draw.text((x2+8, y), label, font=_font(20, True, True), fill=(32,36,40,255), anchor='lm')
        occupied.append((x, y))


def _scroll_draw_scenario(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    action = analysis.get('action_summary') if isinstance(analysis.get('action_summary'), dict) else {}
    code = str(action.get('code') or analysis.get('draw_mode') or 'watch')
    side = str(action.get('primary_side') or ('buy' if str(analysis.get('direction')) == 'صاعد' else 'sell' if str(analysis.get('direction')) == 'هابط' else 'wait'))
    confirmed = bool(action.get('is_confirmed')) or code in {'buy', 'sell', 'confirmed'}
    entry = _number(analysis.get('entry')) if confirmed else _number(action.get('trigger'))
    stop = _number(analysis.get('stop_loss')) if confirmed else _number(action.get('cancel'))
    targets = [_number(analysis.get(k)) for k in ('target_1', 'target_2', 'target_3')] if confirmed else [_number(action.get('target'))]
    targets = [float(v) for v in targets if v is not None]
    if side == 'wait' or entry is None or stop is None or not targets:
        return
    entry = float(entry); stop = float(stop)
    bullish = side == 'buy'
    if bullish and not (stop < entry < max(targets)):
        return
    if not bullish and not (stop > entry > min(targets)):
        return
    x1, x2 = 1580, 1925
    ey = _scroll_price_y(entry, price_min, price_max); sy = _scroll_price_y(stop, price_min, price_max)
    end_target = targets[-1]
    ty = _scroll_price_y(end_target, price_min, price_max)
    draw.rectangle((x1, min(ey, ty), x2, max(ey, ty)), fill=(44, 193, 126, 60), outline=(32, 173, 108, 140), width=1)
    draw.rectangle((x1, min(ey, sy), x2, max(ey, sy)), fill=(235, 77, 77, 55), outline=(214, 57, 57, 140), width=1)
    def tag(y: int, label: str, fill: tuple[int,int,int,int]):
        width = 190
        draw.rounded_rectangle((x2-width, y-22, x2, y+22), radius=7, fill=fill)
        draw.text((x2-10, y), label, font=_font(18, True, True), fill=WHITE, anchor='rm')
    tag(ey, f'ENTRY {_fmt_axis_price(entry)}', (22, 160, 108, 245))
    tag(sy, f'SL {_fmt_axis_price(stop)}', (225, 47, 49, 245))
    for i, target in enumerate(targets[:3], 1):
        y = _scroll_price_y(target, price_min, price_max)
        _dash_line(draw, (x1, y), (x2, y), (31, 188, 111, 210), width=2, dash=9, gap=6)
        tag(y, f'TP{i} {_fmt_axis_price(target)}', (23, 183, 102, 245))
    # Expected candles stay inside the chart and move with it.
    steps = 6
    prev_y = ey
    for i in range(steps):
        r = (i + 1) / steps
        x = int(x1 + 30 + r * (x2 - x1 - 80))
        base = int(ey + (ty - ey) * r)
        close_y = base + (-8 if i % 2 else 7)
        color = (36, 180, 127, 210) if bullish else (224, 75, 74, 210)
        draw.line((x, min(prev_y, close_y)-18, x, max(prev_y, close_y)+18), fill=(83,89,95,150), width=2)
        draw.rectangle((x-7, min(prev_y, close_y), x+7, max(prev_y, close_y)+3), fill=color)
        prev_y = close_y


def _render_scrollable_chart(analysis: dict[str, Any]) -> bytes:
    candles = _valid_renderer_candles(analysis)[-64:]
    price_min, price_max = _scroll_chart_range(analysis, candles)
    image = Image.new('RGBA', (SCROLL_CHART_WIDTH, SCROLL_CHART_HEIGHT), (245, 248, 252, 255))
    draw = ImageDraw.Draw(image)
    # Small chart-only heading; app information is rendered outside and remains fixed.
    draw.text((56, 30), f"{analysis.get('symbol') or 'XAUUSD'} · {analysis.get('timeframe') or 'M5'}", font=_font(25, True, True), fill=(31, 38, 46, 255), anchor='la')
    _scroll_draw_axis(draw, price_min, price_max)
    _scroll_draw_candles(draw, candles, price_min, price_max)
    _scroll_draw_price_levels(draw, analysis, price_min, price_max)
    _scroll_draw_zones(draw, analysis, candles, price_min, price_max)
    _scroll_draw_structure(draw, analysis, candles, price_min, price_max)
    _scroll_draw_scenario(draw, analysis, price_min, price_max)
    out = io.BytesIO()
    image.convert('RGB').save(out, format='PNG', optimize=True)
    return out.getvalue()


def _native_source_price_ratio(analysis: dict[str, Any], price: float) -> float | None:
    """Map a price directly onto the uploaded screenshot's own Y ratio."""
    model = _exact_image_axis_model(analysis)
    if model is not None:
        slope = float(model.get("slope") or 0.0)
        intercept = float(model.get("intercept") or 0.0)
        if slope > 0:
            ratio = (intercept - float(price)) / slope
            if -0.12 <= ratio <= 1.12:
                return max(0.0, min(1.0, ratio))

    step = _image_axis_step_model(analysis)
    if step is not None:
        price_step = float(step.get("price_step") or 0.0)
        ratio_step = float(step.get("ratio_step") or 0.0)
        if price_step > 0 and ratio_step > 0:
            intervals = (float(step["top_price"]) - float(price)) / price_step
            ratio = float(step["top_ratio"]) + intervals * ratio_step
            if -0.12 <= ratio <= 1.12:
                return max(0.0, min(1.0, ratio))

    points = _image_axis_points(analysis)
    if len(points) >= 2:
        top_price, top_ratio = points[0]
        bottom_price, bottom_ratio = points[-1]
        delta = top_price - bottom_price
        if delta > 0.01 and bottom_ratio > top_ratio:
            fraction = (top_price - float(price)) / delta
            ratio = top_ratio + fraction * (bottom_ratio - top_ratio)
            if -0.12 <= ratio <= 1.12:
                return max(0.0, min(1.0, ratio))
    return None


def _native_y(analysis: dict[str, Any], price: float, height: int) -> int | None:
    ratio = _native_source_price_ratio(analysis, float(price))
    if ratio is None:
        return None
    return max(1, min(height - 2, int(round(ratio * max(1, height - 1)))))


def _native_tag(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    *,
    fill: tuple[int, int, int, int],
    font,
    pad_x: int,
    pad_y: int,
) -> tuple[int, int, int, int]:
    """Small flat label; deliberately avoids the old protruding card style."""
    box = draw.textbbox((0, 0), text, font=font)
    tw = max(1, box[2] - box[0])
    th = max(1, box[3] - box[1])
    left = x
    top = y - th // 2 - pad_y
    right = x + tw + pad_x * 2
    bottom = y + th // 2 + pad_y
    draw.rounded_rectangle((left, top, right, bottom), radius=max(3, pad_y + 1), fill=fill)
    draw.text((left + pad_x, y), text, font=font, fill=(248, 250, 252, 245), anchor="lm")
    return (left, top, right, bottom)



def _native_is_candle_pixel(pixel: tuple[int, int, int, int]) -> bool:
    """Detect likely red/green candle pixels in the untouched broker screenshot."""
    r, g, b, a = pixel
    if a < 120:
        return False
    # Red candle families.
    if r >= 120 and r >= g * 1.28 and r >= b * 1.20:
        return True
    # Green / teal candle families used by common broker themes.
    if g >= 90 and g >= r * 1.28 and (g >= b * 1.05 or b >= r * 1.30):
        return True
    return False


def _native_detect_candle_centers(image: Image.Image) -> list[int]:
    """Return candle X centers from the original screenshot, never from a rebuilt chart.

    The detector intentionally rejects wide colored runs so support/resistance
    lines and broker widgets are not mistaken for candles.  If the positions
    cannot be found reliably, pattern geometry is not drawn at all.
    """
    rgba = image.convert("RGBA")
    width, height = rgba.size
    if width < 240 or height < 160:
        return []
    left = max(2, int(width * 0.01))
    right = max(left + 40, int(width * 0.82))
    top = max(4, int(height * 0.03))
    bottom = min(height - 4, int(height * 0.96))
    pixels = rgba.load()
    min_hits = max(4, int((bottom - top) * 0.0045))
    active: list[bool] = []
    for x in range(left, right):
        hits = 0
        for y in range(top, bottom):
            if _native_is_candle_pixel(pixels[x, y]):
                hits += 1
                if hits >= min_hits:
                    break
        active.append(hits >= min_hits)

    segments: list[tuple[int, int]] = []
    start: int | None = None
    for offset, is_active in enumerate(active):
        if is_active and start is None:
            start = offset
        elif not is_active and start is not None:
            segments.append((start, offset - 1))
            start = None
    if start is not None:
        segments.append((start, len(active) - 1))

    max_width = max(5, int((right - left) * 0.035))
    centers = [left + (a + b) // 2 for a, b in segments if 1 <= b - a + 1 <= max_width]
    # Real M5 screenshots normally show several candles.  Fewer than six is
    # not enough to anchor a chart pattern safely.
    if len(centers) < 6:
        return []
    return centers


def _native_pattern_abs_index(analysis: dict[str, Any], geometry: dict[str, Any], relative_index: int) -> int | None:
    candles = _valid_renderer_candles(analysis)
    if not candles:
        return None
    try:
        window_size = int(geometry.get("window_size") or len(candles))
    except (TypeError, ValueError):
        window_size = len(candles)
    window_size = max(1, min(len(candles), window_size))
    return len(candles) - window_size + int(relative_index)


def _native_index_x(
    analysis: dict[str, Any],
    geometry: dict[str, Any],
    relative_index: int,
    candle_centers: list[int],
) -> int | None:
    candles = _valid_renderer_candles(analysis)
    if not candles or not candle_centers:
        return None
    visible_count = min(len(candle_centers), len(candles))
    centers = candle_centers[-visible_count:]
    visible_start = len(candles) - visible_count
    absolute = _native_pattern_abs_index(analysis, geometry, relative_index)
    if absolute is None or absolute < visible_start or absolute >= len(candles):
        return None
    return int(centers[absolute - visible_start])


def _native_draw_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int, int],
    *,
    width: int,
) -> None:
    draw.line((start[0], start[1], end[0], end[1]), fill=color, width=width)
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 8:
        return
    ux, uy = dx / length, dy / length
    size = max(7, width * 5)
    angle = math.radians(28)
    ca, sa = math.cos(angle), math.sin(angle)
    for sign in (-1, 1):
        vx = ux * ca - sign * uy * sa
        vy = sign * ux * sa + uy * ca
        point = (int(end[0] - vx * size), int(end[1] - vy * size))
        draw.line((end[0], end[1], point[0], point[1]), fill=color, width=width)


def _native_draw_pattern_overlays(
    image: Image.Image,
    analysis: dict[str, Any],
    width: int,
    height: int,
    font,
    candle_centers: list[int],
) -> None:
    """Draw at most two M5 patterns anchored to detected screenshot candles.

    Candidate patterns are dashed and never receive a forecast arrow.  A solid
    forecast arrow is allowed only after deterministic breakout confirmation.
    No X fallback is used: if candle positions are not detectable, the pattern
    is hidden rather than shifted to a cosmetically convenient location.
    """
    overlays = analysis.get("pattern_overlays")
    if not isinstance(overlays, list) or not overlays or len(candle_centers) < 6:
        return
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    line_w = max(1, int(height * 0.0020))
    dot = max(3, int(height * 0.0048))
    spacing = 18
    if len(candle_centers) >= 2:
        gaps = [b - a for a, b in zip(candle_centers[:-1], candle_centers[1:]) if 2 <= b - a <= width * 0.12]
        if gaps:
            spacing = max(8, int(median(gaps)))
    future_x = min(int(width * 0.80), candle_centers[-1] + spacing * 5)

    for rank, overlay in enumerate(overlays[:2]):
        if not isinstance(overlay, dict) or str(overlay.get("timeframe") or "") != "M5":
            continue
        geometry = overlay.get("geometry") if isinstance(overlay.get("geometry"), dict) else {}
        status = str(overlay.get("status") or "candidate")
        bias = str(overlay.get("bias") or "محايد")
        confirmed = status == "confirmed"
        opacity = 205 if rank == 0 else 135
        boundary = (79, 91, 213, opacity) if confirmed else (71, 80, 94, opacity)
        path_color = (70, 78, 89, max(90, opacity - 50))

        # Boundaries / neckline. Clip a boundary only when both true endpoints
        # are visible; guessed line placement is deliberately forbidden.
        visible_lines = 0
        for item in geometry.get("lines") or []:
            if not isinstance(item, dict):
                continue
            p1, p2 = item.get("p1"), item.get("p2")
            if not (isinstance(p1, list) and len(p1) >= 2 and isinstance(p2, list) and len(p2) >= 2):
                continue
            x1 = _native_index_x(analysis, geometry, int(p1[0]), candle_centers)
            x2 = _native_index_x(analysis, geometry, int(p2[0]), candle_centers)
            y1 = _native_y(analysis, float(p1[1]), height)
            y2 = _native_y(analysis, float(p2[1]), height)
            if None in (x1, x2, y1, y2):
                continue
            role = str(item.get("role") or "")
            color = (187, 139, 33, opacity) if role in {"neckline", "trigger"} else boundary
            if confirmed:
                draw.line((x1, y1, x2, y2), fill=color, width=line_w)
            else:
                _dash_line(draw, (x1, y1), (x2, y2), color, width=line_w, dash=max(5, spacing // 2), gap=max(4, spacing // 3))
            visible_lines += 1

        # Pattern skeleton such as W/M/H&S. Only actual visible pivots are used.
        path_points: list[tuple[int, int]] = []
        for point in geometry.get("path") or []:
            if not (isinstance(point, list) and len(point) >= 2):
                continue
            x = _native_index_x(analysis, geometry, int(point[0]), candle_centers)
            y = _native_y(analysis, float(point[1]), height)
            if x is not None and y is not None:
                path_points.append((x, y))
        if len(path_points) >= 2:
            if confirmed:
                draw.line(path_points, fill=path_color, width=line_w)
            else:
                for a, b in zip(path_points[:-1], path_points[1:]):
                    _dash_line(draw, a, b, path_color, width=line_w, dash=max(5, spacing // 2), gap=max(4, spacing // 3))

        anchor_points: list[tuple[int, int]] = []
        for anchor in geometry.get("anchors") or []:
            if not isinstance(anchor, dict):
                continue
            try:
                x = _native_index_x(analysis, geometry, int(anchor.get("index")), candle_centers)
                y = _native_y(analysis, float(anchor.get("price")), height)
            except (TypeError, ValueError):
                continue
            if x is None or y is None:
                continue
            anchor_points.append((x, y))
            draw.ellipse((x - dot, y - dot, x + dot, y + dot), fill=(248, 250, 252, 205), outline=boundary, width=1)

        # No visible real anchors means no pattern overlay at all.
        if not anchor_points and visible_lines == 0:
            continue

        # Tiny label only; detailed pattern explanation stays in the fixed UI.
        name = str(overlay.get("name") or "")
        if name and anchor_points:
            lx, ly = anchor_points[-1]
            text = f"{name}{' ✓' if confirmed else ''}"
            draw.text((min(width - 8, lx + dot + 4), max(8, ly - dot - 2)), text, font=font, fill=(45, 52, 62, min(235, opacity + 20)), anchor="ls")

        # Forecast arrow is permitted only after the real breakout is confirmed.
        if confirmed:
            trigger = _number(geometry.get("trigger"))
            target = _number(geometry.get("target"))
            breakout_idx = geometry.get("breakout_index")
            if trigger is not None and target is not None and breakout_idx is not None:
                try:
                    sx = _native_index_x(analysis, geometry, int(breakout_idx), candle_centers)
                except (TypeError, ValueError):
                    sx = None
                sy = _native_y(analysis, float(trigger), height)
                ty = _native_y(analysis, float(target), height)
                if sx is not None and sy is not None and ty is not None and future_x > sx + 4:
                    arrow_color = (18, 155, 92, 205) if bias == "صاعد" else (211, 55, 62, 205)
                    _native_draw_arrow(draw, (sx, sy), (future_x, ty), arrow_color, width=max(2, line_w))

    image.alpha_composite(layer)

def _native_draw_sr(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], width: int, height: int, font) -> None:
    current = _number(analysis.get("current_price"))
    if current is None:
        return
    left = int(width * 0.035)
    right = int(width * 0.855)
    pad_x = max(4, int(width * 0.004))
    pad_y = max(2, int(height * 0.003))
    specs = (
        ("resistance_levels", "R", (226, 50, 60, 190), lambda p: p > current),
        ("support_levels", "S", (38, 112, 230, 190), lambda p: p < current),
    )
    for key, prefix, color, side_ok in specs:
        rank = 0
        for item in analysis.get(key) or []:
            price = _number(item.get("price")) if isinstance(item, dict) else None
            if price is None or not side_ok(float(price)):
                continue
            y = _native_y(analysis, float(price), height)
            if y is None or y < int(height * 0.03) or y > int(height * 0.97):
                continue
            rank += 1
            draw.line((left, y, right, y), fill=color, width=max(1, int(height * 0.0022)))
            _native_tag(
                draw,
                left + max(3, int(width * 0.006)),
                y,
                f"{prefix}{rank} {_fmt_axis_price(float(price))}",
                fill=(color[0], color[1], color[2], 160),
                font=font,
                pad_x=pad_x,
                pad_y=pad_y,
            )
            if rank >= 2:
                break


def _native_draw_zones(image: Image.Image, analysis: dict[str, Any], width: int, height: int, font) -> None:
    candles = _valid_renderer_candles(analysis)
    if not candles:
        return
    current = _number(analysis.get("current_price"))
    entry = _number(analysis.get("entry"))
    focal = float(entry if entry is not None else (current if current is not None else candles[-1]["close"]))
    atr = median([max(0.01, float(c["high"]) - float(c["low"])) for c in candles])
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    ob = _nearest_detected_order_block(analysis, candles, focal, float(atr))
    if ob is not None:
        _index, low, high, _strength = ob
        y1 = _native_y(analysis, float(high), height)
        y2 = _native_y(analysis, float(low), height)
        if y1 is not None and y2 is not None:
            y1, y2 = sorted((y1, y2))
            x1, x2 = int(width * 0.42), int(width * 0.66)
            min_h = max(8, int(height * 0.018))
            if y2 - y1 < min_h:
                c = (y1 + y2) // 2
                y1, y2 = c - min_h // 2, c + min_h // 2
            draw.rectangle((x1, y1, x2, y2), fill=(39, 112, 220, 38), outline=(39, 112, 220, 120), width=1)
            draw.text(((x1 + x2) // 2, (y1 + y2) // 2), "ORDER BLOCK", font=font, fill=(28, 77, 146, 210), anchor="mm")

    fvg = _nearest_detected_fvg(candles, focal, float(atr))
    if fvg is not None:
        _index, low, high = fvg
        y1 = _native_y(analysis, float(high), height)
        y2 = _native_y(analysis, float(low), height)
        if y1 is not None and y2 is not None:
            y1, y2 = sorted((y1, y2))
            x1, x2 = int(width * 0.25), int(width * 0.50)
            min_h = max(7, int(height * 0.014))
            if y2 - y1 < min_h:
                c = (y1 + y2) // 2
                y1, y2 = c - min_h // 2, c + min_h // 2
            draw.rectangle((x1, y1, x2, y2), fill=(232, 147, 45, 30), outline=(218, 133, 35, 105), width=1)
            draw.text(((x1 + x2) // 2, (y1 + y2) // 2), "FVG", font=font, fill=(145, 82, 22, 210), anchor="mm")
    image.alpha_composite(layer)


def _native_draw_structure(
    draw: ImageDraw.ImageDraw,
    analysis: dict[str, Any],
    width: int,
    height: int,
    font,
    candle_centers: list[int] | None = None,
) -> None:
    candles = _valid_renderer_candles(analysis)
    if len(candles) < 8 or not candle_centers:
        return
    highs, lows = _simple_swing_points(candles, window=2)
    direction = _reference_direction(analysis)
    recent_floor = max(0, len(candles) - 18)
    highs = [p for p in highs if p[0] >= recent_floor]
    lows = [p for p in lows if p[0] >= recent_floor]
    items: list[tuple[int, float, str]] = []
    if direction == "هابط":
        if lows:
            items.append((*lows[-1], "BOS"))
        if len(lows) >= 2:
            items.append((*lows[-2], "CHOCH"))
        if highs:
            items.append((*highs[-1], "IDM"))
    else:
        if highs:
            items.append((*highs[-1], "BOS"))
        if len(highs) >= 2:
            items.append((*highs[-2], "CHOCH"))
        if lows:
            items.append((*lows[-1], "IDM"))

    plot_left, plot_right = int(width * 0.03), int(width * 0.82)
    structure_geometry = {"window_size": len(candles)}
    for idx, price, label in items[:3]:
        y = _native_y(analysis, float(price), height)
        x = _native_index_x(analysis, structure_geometry, int(idx), candle_centers)
        if y is None or x is None:
            continue
        lead = max(34, int(width * 0.065))
        # Move only the label/leader direction; the anchor dot never moves.
        if x - lead - plot_left >= 20:
            x2 = max(plot_left, x - lead)
            label_anchor = "rm"
            label_x = x2 - max(4, int(width * 0.005))
        else:
            x2 = min(plot_right, x + lead)
            label_anchor = "lm"
            label_x = x2 + max(4, int(width * 0.005))
        dot = max(3, int(height * 0.006))
        draw.ellipse((x-dot, y-dot, x+dot, y+dot), fill=(246, 248, 251, 215), outline=(46, 55, 67, 220), width=1)
        edge_x = x - dot - 2 if x2 < x else x + dot + 2
        _dash_line(draw, (edge_x, y), (x2, y), (50, 58, 69, 165), width=max(1, int(height * 0.0017)), dash=max(4, int(width * 0.006)), gap=max(3, int(width * 0.004)))
        draw.text((label_x, y), label, font=font, fill=(31, 38, 47, 205), anchor=label_anchor)


def _native_draw_trade(image: Image.Image, analysis: dict[str, Any], width: int, height: int, font) -> None:
    action = analysis.get("action_summary") if isinstance(analysis.get("action_summary"), dict) else {}
    code = str(action.get("code") or analysis.get("draw_mode") or "watch")
    side = str(action.get("primary_side") or "wait")
    confirmed = bool(action.get("is_confirmed")) or code in {"buy", "sell", "confirmed"}
    if code in {"inactive", "no_trade", "watch"} or side == "wait":
        return

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    left, right = int(width * 0.64), int(width * 0.82)
    line_left = int(width * 0.55)
    pad_x = max(4, int(width * 0.004))
    pad_y = max(2, int(height * 0.003))

    if not confirmed:
        trigger = _number(action.get("trigger"))
        cancel = _number(action.get("cancel"))
        if trigger is None:
            return
        y = _native_y(analysis, float(trigger), height)
        if y is not None:
            _dash_line(draw, (line_left, y), (right, y), (226, 142, 38, 195), width=max(1, int(height * 0.002)), dash=8, gap=5)
            _native_tag(draw, left, y, "ACTIVATE", fill=(185, 111, 25, 165), font=font, pad_x=pad_x, pad_y=pad_y)
        if cancel is not None:
            cy = _native_y(analysis, float(cancel), height)
            if cy is not None:
                _dash_line(draw, (line_left, cy), (right, cy), (204, 66, 66, 150), width=1, dash=7, gap=5)
        image.alpha_composite(layer)
        return

    entry = _number(analysis.get("entry")) or _number(analysis.get("current_price"))
    stop = _number(analysis.get("stop_loss"))
    targets = [_number(analysis.get(k)) for k in ("target_1", "target_2", "target_3")]
    targets = [float(v) for v in targets if v is not None]
    if entry is None or stop is None or not targets:
        return
    ey = _native_y(analysis, float(entry), height)
    sy = _native_y(analysis, float(stop), height)
    tys = [(value, _native_y(analysis, value, height)) for value in targets]
    tys = [(value, y) for value, y in tys if y is not None]
    if ey is None or sy is None or not tys:
        return
    far_y = tys[-1][1]
    draw.rectangle((left, min(ey, far_y), right, max(ey, far_y)), fill=(17, 162, 98, 38))
    draw.rectangle((left, min(ey, sy), right, max(ey, sy)), fill=(213, 61, 67, 38))
    levels = [("ENTRY", ey, (18, 150, 103, 180)), ("SL", sy, (198, 50, 56, 180))]
    levels += [(f"TP{i}", y, (18, 166, 92, 175)) for i, (_value, y) in enumerate(tys[:3], start=1)]
    for label, y, color in levels:
        _dash_line(draw, (line_left, y), (right, y), color, width=max(1, int(height * 0.002)), dash=8, gap=5)
        _native_tag(draw, right - max(54, int(width * 0.075)), y, label, fill=color, font=font, pad_x=pad_x, pad_y=pad_y)
    image.alpha_composite(layer)


def _render_uploaded_chart_with_overlays(
    analysis: dict[str, Any],
    chart_background_path: str | os.PathLike[str] | None,
) -> bytes:
    """Preserve the exact uploaded landscape screenshot and add only light overlays."""
    if chart_background_path:
        try:
            with Image.open(chart_background_path) as source:
                image = source.convert("RGBA").copy()
        except Exception:
            image = None
    else:
        image = None
    if image is None:
        return _render_scrollable_chart(analysis)

    width, height = image.size
    font_size = max(9, min(14, int(round(height * 0.015))))
    font = _font(font_size, True, True)
    # Detect X anchors from the untouched screenshot before adding any SaleeM overlay.
    candle_centers = _native_detect_candle_centers(image)
    draw = ImageDraw.Draw(image)
    _native_draw_sr(draw, analysis, width, height, font)
    _native_draw_zones(image, analysis, width, height, font)
    _native_draw_pattern_overlays(image, analysis, width, height, font, candle_centers)
    draw = ImageDraw.Draw(image)
    _native_draw_structure(draw, analysis, width, height, font, candle_centers)
    _native_draw_trade(image, analysis, width, height, font)

    out = io.BytesIO()
    image.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


def render_result(analysis: dict[str, Any], chart_background_path: str | os.PathLike[str] | None = None) -> bytes:
    """Use the user's uploaded chart itself as the pannable chart canvas.

    The fixed application UI stays outside this image. Only price-linked chart
    drawings are added here, so panning moves the screenshot and every overlay
    together without recreating the candles or price axis.
    """
    return _render_uploaded_chart_with_overlays(analysis, chart_background_path)

