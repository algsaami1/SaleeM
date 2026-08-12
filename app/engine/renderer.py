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


def _wrap_text_by_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    max_width: int,
    *,
    rtl: bool = True,
    max_lines: int = 4,
) -> list[str]:
    """Wrap short UI prose deterministically without external layout engines."""
    words = " ".join(str(text or "").split()).split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        if _text_width(draw, candidate, font, rtl) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and words:
        consumed = sum(len(line.split()) for line in lines)
        if consumed < len(words):
            lines[-1] = _fit_text(draw, lines[-1] + " " + " ".join(words[consumed:]), font, max_width, rtl=rtl)
    return lines[:max_lines]


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


def _valid_renderer_candles(
    analysis: dict[str, Any],
    *,
    prefer_render_window: bool = False,
) -> list[dict[str, Any]]:
    items = []
    raw = analysis.get("render_candles") if prefer_render_window and isinstance(analysis.get("render_candles"), list) else analysis.get("candles")
    for candle in raw or []:
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



def _native_axis_price_step(analysis: dict[str, Any]) -> float | None:
    """Return the broker tick price step using label *values only*.

    Y ratios coming from vision are deliberately ignored here.  The screenshot
    itself supplies the pixel spacing; OCR/vision supplies only the numerical
    tick sequence.  Missing ticks are tolerated because the smallest regular
    gaps dominate the lower portion of the sorted gap list.
    """
    raw_prices: list[float] = []
    for item in analysis.get("image_axis_labels") or []:
        if not isinstance(item, dict):
            continue
        value = _number(item.get("price"))
        if value is not None and math.isfinite(float(value)):
            raw_prices.append(float(value))
    prices = sorted({round(value, 4) for value in raw_prices}, reverse=True)
    if len(prices) < 3:
        return None
    gaps = sorted(
        price_a - price_b
        for price_a, price_b in zip(prices[:-1], prices[1:])
        if price_a - price_b > 0.03
    )
    if len(gaps) < 2:
        return None
    pool_count = max(2, int(math.ceil(len(gaps) * 0.70)))
    base = float(median(gaps[:pool_count]))
    if base <= 0.03:
        return None
    regular: list[float] = []
    for gap in gaps:
        multiple = max(1, min(6, int(round(gap / base))))
        expected = base * multiple
        if abs(gap - expected) <= max(0.08, base * 0.08 * multiple):
            if multiple == 1:
                regular.append(gap)
    if len(regular) >= 2:
        base = float(median(regular))
    return base if base > 0.03 else None


def _native_is_grid_pixel(pixel: tuple[int, int, int, int]) -> bool:
    """Identify quiet horizontal broker-grid pixels on light chart themes."""
    r, g, b, a = pixel
    if a < 100:
        return False
    # Pale blue MT5/TradingView-like dashed grid.
    if 205 <= r <= 246 and 214 <= g <= 250 and 222 <= b <= 255:
        if b >= g - 3 and g >= r - 2 and (b - r) <= 45:
            return True
    # Neutral light-gray grid fallback. Pure white background is excluded.
    if 176 <= r <= 244 and 176 <= g <= 244 and 176 <= b <= 244:
        if max(r, g, b) - min(r, g, b) <= 12:
            return True
    return False


def _native_horizontal_grid_rows(image: Image.Image) -> list[int]:
    """Detect recurring horizontal grid rows directly from source pixels.

    This is intentionally independent of OCR Y coordinates.  It scans only the
    chart body and chooses thin, high-coverage pale/neutral rows.  Consecutive
    rows are collapsed to one center so antialiasing cannot create fake ticks.
    """
    rgba = image.convert("RGBA")
    width, height = rgba.size
    if width < 240 or height < 180:
        return []
    pixels = rgba.load()
    left = max(4, int(width * 0.025))
    right = max(left + 80, int(width * 0.82))
    sample_step = 2 if width >= 900 else 1
    sample_count = max(1, (right - left + sample_step - 1) // sample_step)
    scores = [0] * height
    for y in range(max(2, int(height * 0.02)), min(height - 2, int(height * 0.98))):
        hits = 0
        for x in range(left, right, sample_step):
            if _native_is_grid_pixel(pixels[x, y]):
                hits += 1
        scores[y] = hits
    best = max(scores, default=0)
    threshold = max(18, int(sample_count * 0.075), int(best * 0.38))
    if best < threshold:
        return []

    candidates: list[int] = []
    for y in range(2, height - 2):
        score = scores[y]
        if score < threshold:
            continue
        if score >= scores[y - 1] and score >= scores[y + 1]:
            candidates.append(y)
    if not candidates:
        return []

    bands: list[list[int]] = []
    for y in candidates:
        if not bands or y - bands[-1][-1] > 4:
            bands.append([y])
        else:
            bands[-1].append(y)
    rows: list[int] = []
    for band in bands:
        best_y = max(band, key=lambda row: scores[row])
        rows.append(int(best_y))
    return rows


def _native_horizontal_grid_step(image: Image.Image) -> tuple[float | None, list[int]]:
    rows = _native_horizontal_grid_rows(image)
    if len(rows) < 4:
        return None, rows
    height = image.height
    gaps = [
        b - a
        for a, b in zip(rows[:-1], rows[1:])
        if max(10, int(height * 0.025)) <= b - a <= int(height * 0.24)
    ]
    if len(gaps) < 3:
        return None, rows
    best_gap: float | None = None
    best_score = -1.0
    for candidate in gaps:
        supporters = [gap for gap in gaps if abs(gap - candidate) <= max(4.0, candidate * 0.12)]
        score = len(supporters) - abs(candidate - median(gaps)) / max(1.0, candidate) * 0.10
        if score > best_score:
            best_score = score
            best_gap = float(median(supporters)) if supporters else float(candidate)
    if best_gap is None:
        return None, rows
    supporters = [gap for gap in gaps if abs(gap - best_gap) <= max(4.0, best_gap * 0.12)]
    if len(supporters) < 3:
        return None, rows
    return float(median(supporters)), rows


def _native_build_pixel_axis_model(image: Image.Image, analysis: dict[str, Any]) -> dict[str, float | int | str] | None:
    """Build the strict source-price transform from pixels, not OCR Y ratios.

    The current broker price line fixes the vertical origin. Repeating source
    grid rows fix pixels-per-tick, while axis label *values* fix price-per-tick.
    Therefore a bad y_ratio cannot place R/S/OB/FVG/pattern geometry at the
    wrong height.  The model is accepted only when predicted broker tick prices
    land back on detected source grid rows.
    """
    current = _number(analysis.get("visual_current_price")) or _number(analysis.get("current_price"))
    if current is None:
        return None
    current_y = _detect_green_reference_line_y(image)
    price_step = _native_axis_price_step(analysis)
    grid_step, grid_rows = _native_horizontal_grid_step(image)
    if current_y is None or price_step is None or grid_step is None:
        return None
    pixels_per_price = float(grid_step) / float(price_step)
    if not math.isfinite(pixels_per_price) or pixels_per_price <= 0.2:
        return None

    # Numerical tick values should project onto actual source grid rows.
    labels = []
    for item in analysis.get("image_axis_labels") or []:
        if isinstance(item, dict):
            value = _number(item.get("price"))
            if value is not None:
                labels.append(float(value))
    tolerance = max(5.0, float(grid_step) * 0.16)
    hits = 0
    checked = 0
    for price in labels:
        y = float(current_y) - (price - float(current)) * pixels_per_price
        if not (0 <= y <= image.height - 1):
            continue
        checked += 1
        if grid_rows and min(abs(y - row) for row in grid_rows) <= tolerance:
            hits += 1
    if checked >= 4 and hits < max(3, int(math.ceil(checked * 0.55))):
        return None

    return {
        "mode": "pixel_current_grid",
        "current_price": float(current),
        "current_y": int(current_y),
        "height": int(image.height),
        "price_step": float(price_step),
        "grid_step": float(grid_step),
        "pixels_per_price": float(pixels_per_price),
        "validation_hits": int(hits),
        "validation_checked": int(checked),
    }


def _native_literal_axis_points(analysis: dict[str, Any]) -> list[tuple[float, float]]:
    """Return literal broker-axis anchors in whole-image coordinates.

    Source tick labels are more authoritative than a best-fit scale.  The current
    price badge is admitted as an extra anchor only when it agrees closely with
    the surrounding tick sequence, so one bad vision read cannot bend the axis.
    """
    points = list(_image_axis_points(analysis))
    if len(points) < 2:
        return points

    current = _number(analysis.get("visual_current_price")) or _number(analysis.get("current_price"))
    current_ratio = _number(analysis.get("current_price_y_ratio"))
    if current is not None and current_ratio is not None:
        current_ratio = max(0.0, min(1.0, float(current_ratio)))
        expected: float | None = None
        for (upper_price, upper_ratio), (lower_price, lower_ratio) in zip(points[:-1], points[1:]):
            if upper_price >= float(current) >= lower_price and upper_price > lower_price:
                fraction = (upper_price - float(current)) / (upper_price - lower_price)
                expected = upper_ratio + fraction * (lower_ratio - upper_ratio)
                break
        if expected is None or abs(expected - current_ratio) <= 0.035:
            points.append((float(current), current_ratio))

    points.sort(key=lambda item: item[1])
    cleaned: list[tuple[float, float]] = []
    for price_value, ratio_value in points:
        if cleaned and ratio_value - cleaned[-1][1] < 0.004:
            continue
        if cleaned and price_value >= cleaned[-1][0] - 0.01:
            continue
        cleaned.append((float(price_value), float(ratio_value)))
    return cleaned


def _native_piecewise_price_ratio(analysis: dict[str, Any], price: float) -> float | None:
    """Interpolate between the two nearest literal axis ticks.

    This makes every visible broker tick an exact anchor instead of allowing a
    global fitted line to drift a few pixels away from the original screenshot.
    """
    points = _native_literal_axis_points(analysis)
    if len(points) < 2:
        return None

    target = float(price)
    for (upper_price, upper_ratio), (lower_price, lower_ratio) in zip(points[:-1], points[1:]):
        if upper_price >= target >= lower_price and upper_price > lower_price:
            fraction = (upper_price - target) / (upper_price - lower_price)
            return max(0.0, min(1.0, upper_ratio + fraction * (lower_ratio - upper_ratio)))

    # Permit only a small extrapolation beyond the first/last visible tick.
    if target > points[0][0]:
        p1, r1 = points[0]
        p2, r2 = points[1]
    elif target < points[-1][0]:
        p1, r1 = points[-2]
        p2, r2 = points[-1]
    else:
        return None
    price_span = p1 - p2
    ratio_span = r2 - r1
    if price_span <= 0.01 or ratio_span <= 0.001:
        return None
    extrapolated_steps = abs(target - (p1 if target > points[0][0] else p2)) / price_span
    if extrapolated_steps > 1.25:
        return None
    ratio = r1 + ((p1 - target) / price_span) * ratio_span
    if -0.08 <= ratio <= 1.08:
        return max(0.0, min(1.0, ratio))
    return None


def _native_source_price_ratio(analysis: dict[str, Any], price: float) -> float | None:
    """Map a price onto the uploaded screenshot with one authoritative scale."""
    pixel_model = analysis.get("_native_axis_pixel_model")
    if isinstance(pixel_model, dict) and pixel_model.get("mode") == "pixel_current_grid":
        current_price = _number(pixel_model.get("current_price"))
        current_y = _number(pixel_model.get("current_y"))
        pixels_per_price = _number(pixel_model.get("pixels_per_price"))
        source_height = int(pixel_model.get("height") or 0)
        if current_price is not None and current_y is not None and pixels_per_price is not None and source_height > 1:
            y = float(current_y) - (float(price) - float(current_price)) * float(pixels_per_price)
            margin = max(4.0, source_height * 0.02)
            if -margin <= y <= (source_height - 1) + margin:
                analysis["native_axis_projection_mode"] = "pixel_current_grid"
                return max(0.0, min(1.0, y / float(source_height - 1)))

    # For uploaded-chart rendering v3.47 is fail-closed: a missing pixel model
    # hides price-linked overlays instead of drawing them at a guessed height.
    if analysis.get("_native_axis_strict_pixel"):
        analysis["native_axis_projection_mode"] = "hidden_untrusted_axis"
        return None

    literal = _native_piecewise_price_ratio(analysis, float(price))
    if literal is not None:
        analysis["native_axis_projection_mode"] = "literal_piecewise"
        return literal

    model = _exact_image_axis_model(analysis)
    if model is not None:
        slope = float(model.get("slope") or 0.0)
        intercept = float(model.get("intercept") or 0.0)
        if slope > 0:
            ratio = (intercept - float(price)) / slope
            if -0.12 <= ratio <= 1.12:
                analysis["native_axis_projection_mode"] = "robust_fit"
                return max(0.0, min(1.0, ratio))

    step = _image_axis_step_model(analysis)
    if step is not None:
        price_step = float(step.get("price_step") or 0.0)
        ratio_step = float(step.get("ratio_step") or 0.0)
        if price_step > 0 and ratio_step > 0:
            intervals = (float(step["top_price"]) - float(price)) / price_step
            ratio = float(step["top_ratio"]) + intervals * ratio_step
            if -0.12 <= ratio <= 1.12:
                analysis["native_axis_projection_mode"] = "step_fallback"
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




def _native_candle_color_side(pixel: tuple[int, int, int, int]) -> str | None:
    r, g, b, a = pixel
    if a < 120:
        return None
    if r >= 120 and r >= g * 1.28 and r >= b * 1.20:
        return "bear"
    if g >= 90 and g >= r * 1.28 and (g >= b * 1.05 or b >= r * 1.30):
        return "bull"
    return None


def _native_detect_candle_geometry(image: Image.Image, centers: list[int]) -> list[dict[str, Any]]:
    """Read the visible candle wick range directly from the untouched screenshot.

    This geometry is used only to align the market-candle indices with the actual
    pixels in the uploaded chart.  It never recreates or replaces the chart.
    """
    if not centers:
        return []
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    top = max(2, int(height * 0.02))
    bottom = min(height - 3, int(height * 0.97))
    gaps = [b - a for a, b in zip(centers[:-1], centers[1:]) if b > a]
    spacing = int(median(gaps)) if gaps else max(8, width // max(12, len(centers)))
    half = max(2, min(6, spacing // 5))
    result: list[dict[str, Any]] = []
    for x in centers:
        ys: list[int] = []
        bull = 0
        bear = 0
        for xx in range(max(0, x - half), min(width, x + half + 1)):
            for y in range(top, bottom + 1):
                side = _native_candle_color_side(pixels[xx, y])
                if side is None:
                    continue
                ys.append(y)
                if side == "bull":
                    bull += 1
                else:
                    bear += 1
        if len(ys) < 3:
            continue
        result.append({
            "x": int(x),
            "y_high": int(min(ys)),
            "y_low": int(max(ys)),
            "side": "bull" if bull > bear * 1.12 else "bear" if bear > bull * 1.12 else "neutral",
        })
    return result


def _native_y_to_price(analysis: dict[str, Any], y: float) -> float | None:
    model = analysis.get("_native_axis_pixel_model")
    if not isinstance(model, dict) or model.get("mode") != "pixel_current_grid":
        return None
    current_price = _number(model.get("current_price"))
    current_y = _number(model.get("current_y"))
    pixels_per_price = _number(model.get("pixels_per_price"))
    if current_price is None or current_y is None or pixels_per_price is None or pixels_per_price <= 0:
        return None
    return float(current_price) + (float(current_y) - float(y)) / float(pixels_per_price)


def _native_build_candle_x_map(
    image: Image.Image,
    analysis: dict[str, Any],
    candle_centers: list[int],
) -> dict[int, int]:
    """Align visible screenshot candles to the real market-candle indices.

    v3.48 mapped the last N market candles to the N detected screenshot candles.
    That can shift every W/M/BOS/CHOCH/IDM horizontally when the screenshot is a
    few candles behind the market feed.  Here we compare the screenshot wick
    high/low and color with the market data and search for the best recent
    contiguous alignment.  If the match is not trustworthy we fail closed.
    """
    candles = _valid_renderer_candles(analysis)
    geoms = _native_detect_candle_geometry(image, candle_centers)
    if len(candles) < 8 or len(geoms) < 6:
        return {}
    # Keep centers and geometry in the same order; geometry may omit a rare
    # unreadable center, so use only its own x values.
    usable = []
    for geom in geoms:
        high_price = _native_y_to_price(analysis, float(geom["y_high"]))
        low_price = _native_y_to_price(analysis, float(geom["y_low"]))
        if high_price is None or low_price is None:
            continue
        high_price, low_price = max(high_price, low_price), min(high_price, low_price)
        usable.append((int(geom["x"]), high_price, low_price, str(geom.get("side") or "neutral")))
    if len(usable) < 6:
        return {}

    n = len(usable)
    if n > len(candles):
        usable = usable[-len(candles):]
        n = len(usable)
    recent_atr_values = [max(0.01, float(c["high"]) - float(c["low"])) for c in candles[-32:]]
    atr = max(0.01, float(median(recent_atr_values))) if recent_atr_values else 0.25
    # Screenshot can trail the live feed; search a generous recent window.
    max_lag = min(24, max(0, len(candles) - n))
    candidate_starts = [len(candles) - n - lag for lag in range(max_lag + 1)]
    best: tuple[float, int] | None = None
    for start in candidate_starts:
        if start < 0 or start + n > len(candles):
            continue
        errors: list[float] = []
        side_penalty = 0.0
        for offset, (_x, img_high, img_low, side) in enumerate(usable):
            candle = candles[start + offset]
            err = (abs(img_high - float(candle["high"])) + abs(img_low - float(candle["low"]))) / (2.0 * atr)
            errors.append(min(4.0, err))
            market_side = "bull" if float(candle["close"]) > float(candle["open"]) else "bear" if float(candle["close"]) < float(candle["open"]) else "neutral"
            if side != "neutral" and market_side != "neutral" and side != market_side:
                side_penalty += 0.18
        if not errors:
            continue
        errors.sort()
        # Robust median-ish error so one long wick does not ruin the alignment.
        core = errors[:max(4, int(len(errors) * 0.80))]
        score = sum(core) / len(core) + side_penalty / max(1, len(errors))
        if best is None or score < best[0]:
            best = (score, start)
    if best is None or best[0] > 1.15:
        analysis["native_candle_alignment_score"] = None if best is None else round(best[0], 3)
        analysis["native_candle_alignment_mode"] = "hidden_untrusted_x"
        return {}
    score, start = best
    analysis["native_candle_alignment_score"] = round(score, 3)
    analysis["native_candle_alignment_mode"] = "wick_price_match"
    return {start + offset: int(item[0]) for offset, item in enumerate(usable)}

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
    """Project a market candle index onto the uploaded chart only from a calibrated X map.

    Uploaded-chart rendering is fail-closed: if the wick/price matching could
    not prove which screenshot candle corresponds to the market index, no X is
    returned. The old trailing-window fallback caused W/M/BOS/CHOCH/IDM to
    drift onto unrelated candles and is intentionally removed.
    """
    candles = _valid_renderer_candles(analysis)
    if not candles or not candle_centers:
        return None
    absolute = _native_pattern_abs_index(analysis, geometry, relative_index)
    if absolute is None:
        return None
    x_map = analysis.get("_native_candle_x_map")
    if not isinstance(x_map, dict) or not x_map:
        return None
    value = x_map.get(int(absolute))
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

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


def _native_pattern_execution_allowed(analysis: dict[str, Any], overlay: dict[str, Any], rank: int) -> bool:
    """Only the primary, direction-compatible pattern may explain an executable path."""
    if rank != 0:
        return False
    if str(analysis.get("market_status") or "active") != "active":
        return False
    draw_mode = str(analysis.get("draw_mode") or "watch")
    if draw_mode not in {"conditional", "confirmed"}:
        return False
    direction = str(analysis.get("direction") or "")
    bias = str(overlay.get("bias") or "")
    if bias == "صاعد" and direction != "صاعد":
        return False
    if bias == "هابط" and direction != "هابط":
        return False
    action = analysis.get("action_summary") if isinstance(analysis.get("action_summary"), dict) else {}
    side = str(action.get("primary_side") or "wait")
    expected_side = "buy" if bias == "صاعد" else "sell" if bias == "هابط" else "wait"
    return side == expected_side


def _native_pattern_core_visible(
    analysis: dict[str, Any],
    overlay: dict[str, Any],
    geometry: dict[str, Any],
    candle_centers: list[int],
) -> bool:
    """Require the full W/M core to be visible before drawing any part of it."""
    name = str(overlay.get("name") or "")
    if name not in {"W", "M"}:
        return True
    roles: list[tuple[int, str]] = []
    for anchor in geometry.get("anchors") or []:
        if not isinstance(anchor, dict):
            continue
        try:
            idx = int(anchor.get("index"))
        except (TypeError, ValueError):
            continue
        role = str(anchor.get("role") or "")
        if role in {"pivot", "neck"}:
            roles.append((idx, role))
    if len(roles) < 3:
        return False
    visible = [_native_index_x(analysis, geometry, idx, candle_centers) for idx, _role in roles[:3]]
    return all(value is not None for value in visible)


def _native_draw_pattern_overlays(
    image: Image.Image,
    analysis: dict[str, Any],
    width: int,
    height: int,
    font,
    candle_centers: list[int],
) -> None:
    """Draw the single closest source-matched M5 pattern on the real chart.

    v3.61 makes the explanatory arrow mandatory for the chosen pattern:
    candidate = dashed expectation, confirmed = solid expectation.  The arrow
    explains the model and never turns a watch state into an executable trade.
    All anchors/lines still come from real closed M5 candles; no X fallback is
    allowed when screenshot candle positions cannot be detected reliably.
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

    for rank, overlay in enumerate(overlays[:1]):
        if not isinstance(overlay, dict) or str(overlay.get("timeframe") or "") != "M5":
            continue
        geometry = overlay.get("geometry") if isinstance(overlay.get("geometry"), dict) else {}
        status = str(overlay.get("status") or "candidate")
        bias = str(overlay.get("bias") or "محايد")
        confirmed = status == "confirmed"
        if not _native_pattern_core_visible(analysis, overlay, geometry, candle_centers):
            continue
        execution_allowed = confirmed and _native_pattern_execution_allowed(analysis, overlay, rank)
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

        # Make the selected source-model family obvious on the chart without
        # hiding candles.  The rule itself remains below the saved image.
        name = str(overlay.get("name") or "")
        if name and anchor_points:
            center_x = int(sum(point[0] for point in anchor_points) / len(anchor_points))
            if bias == "هابط":
                label_y = max(18, min(point[1] for point in anchor_points) - dot * 5)
            else:
                label_y = min(height - 18, max(point[1] for point in anchor_points) + dot * 5)
            text = f"{name}{' ✓' if confirmed else ' — مرشح'}"
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = max(1, bbox[2] - bbox[0]); th = max(1, bbox[3] - bbox[1])
            lx = max(6, min(width - tw - 16, center_x - tw // 2))
            ly = max(6, min(height - th - 12, label_y - th // 2))
            label_fill = (252, 253, 255, 222)
            label_outline = (208, 62, 70, 180) if bias == "هابط" else (25, 151, 92, 180)
            draw.rounded_rectangle((lx - 6, ly - 4, lx + tw + 6, ly + th + 4), radius=5, fill=label_fill, outline=label_outline, width=1)
            draw.text((lx, ly), text, font=font, fill=(40, 48, 58, 235))

        trigger = _number(geometry.get("trigger"))
        stop = _number(geometry.get("stop"))
        target = _number(geometry.get("target"))
        breakout_idx = geometry.get("breakout_index")
        pivot_prices = []
        for anchor in geometry.get("anchors") or []:
            if isinstance(anchor, dict) and str(anchor.get("role") or "") == "pivot":
                price = _number(anchor.get("price"))
                if price is not None:
                    pivot_prices.append(float(price))

        # Only the primary, direction-compatible active scenario may show
        # activation/entry/invalidation. Secondary patterns stay analytical only.
        if execution_allowed and trigger is not None:
            trigger_y = _native_y(analysis, float(trigger), height)
            if trigger_y is not None:
                zone_left = max(candle_centers[-1] - spacing * 2, int(width * 0.68))
                zone_right = min(width - 8, future_x + spacing)
                if pivot_prices:
                    if bias == "صاعد":
                        zone_depth = max(0.08, min(0.42, (float(trigger) - min(pivot_prices)) * 0.22))
                        zone_top_price = float(trigger) + zone_depth
                        zone_bottom_price = float(trigger)
                    else:
                        zone_depth = max(0.08, min(0.42, (max(pivot_prices) - float(trigger)) * 0.22))
                        zone_top_price = float(trigger)
                        zone_bottom_price = float(trigger) - zone_depth
                    zy1 = _native_y(analysis, zone_top_price, height)
                    zy2 = _native_y(analysis, zone_bottom_price, height)
                else:
                    zy1 = trigger_y - max(8, spacing // 2)
                    zy2 = trigger_y + max(8, spacing // 2)
                if zy1 is not None and zy2 is not None:
                    top_y, bottom_y = sorted((zy1, zy2))
                    fill = (33, 166, 102, 42) if bias == "صاعد" else (210, 63, 70, 42)
                    outline = (33, 166, 102, 120) if bias == "صاعد" else (210, 63, 70, 120)
                    draw.rectangle((zone_left, top_y, zone_right, bottom_y), fill=fill, outline=outline, width=1)
                    _draw_rtl(draw, (zone_right - 4, (top_y + bottom_y) // 2), "منطقة التفعيل", font, outline, anchor="rm")
                _dash_line(draw, (zone_left, trigger_y), (zone_right, trigger_y), (33, 147, 83, 190) if bias == "صاعد" else (212, 62, 70, 190), width=max(1, line_w), dash=max(6, spacing // 2), gap=max(4, spacing // 3))
                _draw_rtl(draw, (zone_right - 4, max(12, trigger_y - 6)), "عنق / تفعيل", font, (33, 147, 83, 200) if bias == "صاعد" else (212, 62, 70, 200), anchor="rs")
        # The model's invalidation belongs to the explanation, so the primary
        # selected pattern may show it even while the trade state is watch.
        if rank == 0 and stop is not None:
            stop_y = _native_y(analysis, float(stop), height)
            if stop_y is not None:
                line_left = max(int(width * 0.66), candle_centers[-1] - spacing * 2)
                line_right = min(width - 8, future_x)
                _dash_line(draw, (line_left, stop_y), (line_right, stop_y), (212, 62, 70, 160), width=max(1, line_w), dash=max(6, spacing // 2), gap=max(4, spacing // 3))
                _draw_rtl(draw, ((line_left + line_right) // 2, stop_y - 6), "إلغاء النموذج", font, (212, 62, 70, 190), anchor="ms")

        # Mandatory model expectation arrow.  Confirmed patterns use a solid
        # path from the real breakout.  Candidate patterns use a dashed path
        # from the latest visible candle toward the activation/nearest real
        # structural level.  This is explanatory, not an Entry signal.
        if rank == 0 and bias in {"صاعد", "هابط"} and not bool(analysis.get("reference_scenario_available")):
            current = _number(analysis.get("current_price"))
            arrow_target = target
            if arrow_target is None or _native_y(analysis, float(arrow_target), height) is None:
                level_key = "resistance_levels" if bias == "صاعد" else "support_levels"
                real_levels: list[float] = []
                for level in analysis.get(level_key) or []:
                    if not isinstance(level, dict):
                        continue
                    price = _number(level.get("price"))
                    if price is None or current is None:
                        continue
                    if bias == "صاعد" and float(price) > float(current):
                        real_levels.append(float(price))
                    elif bias == "هابط" and float(price) < float(current):
                        real_levels.append(float(price))
                if real_levels:
                    arrow_target = min(real_levels, key=lambda price: abs(price - float(current)))

            ty = _native_y(analysis, float(arrow_target), height) if arrow_target is not None else None
            arrow_end_x = min(width - 10, max(future_x, candle_centers[-1] + spacing * 6))
            arrow_color = (18, 155, 92, 220) if bias == "صاعد" else (211, 55, 62, 220)

            if confirmed and trigger is not None and breakout_idx is not None and ty is not None:
                try:
                    sx = _native_index_x(analysis, geometry, int(breakout_idx), candle_centers)
                except (TypeError, ValueError):
                    sx = None
                sy = _native_y(analysis, float(trigger), height)
                if sx is not None and sy is not None and arrow_end_x > sx + 6:
                    _native_draw_arrow(draw, (sx, sy), (arrow_end_x, ty), arrow_color, width=max(3, line_w + 2))
            elif current is not None and ty is not None:
                sx = candle_centers[-1]
                sy = _native_y(analysis, float(current), height)
                if sy is not None and arrow_end_x > sx + 8:
                    trigger_y = _native_y(analysis, float(trigger), height) if trigger is not None else None
                    bend_x = min(arrow_end_x - spacing, sx + spacing * 2)
                    bend_y = trigger_y if trigger_y is not None else int(round((sy + ty) / 2))
                    _dash_line(draw, (sx, sy), (bend_x, bend_y), arrow_color, width=max(2, line_w + 1), dash=max(7, spacing // 2), gap=max(5, spacing // 3))
                    _dash_line(draw, (bend_x, bend_y), (arrow_end_x, ty), arrow_color, width=max(2, line_w + 1), dash=max(7, spacing // 2), gap=max(5, spacing // 3))
                    _native_draw_arrow(draw, (bend_x, bend_y), (arrow_end_x, ty), arrow_color, width=max(2, line_w + 1))

    image.alpha_composite(layer)

def _native_draw_sr(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], width: int, height: int, font) -> None:
    """v3.68: draw readable support/resistance *zones* on the original chart.

    The price level remains the anchor.  A translucent band is only a visual
    comfort layer around that exact level; it never changes the price or the
    detected geometry.  Up to two nearby levels per side may be shown because
    v3.68 prefers organized richness over hiding useful context.
    """
    current = _number(analysis.get("current_price"))
    if current is None:
        return
    bounds = analysis.get("educational_overlay_bounds")
    if isinstance(bounds, list) and len(bounds) >= 4:
        left, _top, right, _bottom = [int(v) for v in bounds[:4]]
    else:
        left, right = int(width * 0.035), int(width * 0.855)
    left = max(2, min(width - 4, left))
    right = max(left + 8, min(width - 2, right))
    line_w = max(1, int(round(min(width, height) * 0.0022)))
    band_half = max(5, int(round(height * 0.0075)))
    label_pad_x = max(5, int(width * 0.0045))
    label_pad_y = max(3, int(height * 0.0028))

    decision_zone = analysis.get("decision_zone") if isinstance(analysis.get("decision_zone"), dict) else {}
    zone_low = _number(decision_zone.get("low")) if decision_zone.get("active") else None
    zone_high = _number(decision_zone.get("high")) if decision_zone.get("active") else None
    if zone_low is not None and zone_high is not None and float(zone_low) < float(zone_high):
        yh = _native_y(analysis, float(zone_high), height)
        yl = _native_y(analysis, float(zone_low), height)
        if yh is not None and yl is not None:
            zt, zb = sorted((yh, yl))
            draw.rounded_rectangle((left, zt, right, zb), radius=max(4, band_half // 2), fill=(245, 158, 11, 26), outline=(195, 127, 26, 110), width=1)
            _dash_line(draw, (left, zt), (right, zt), (195, 127, 26, 155), width=line_w, dash=10, gap=7)
            _dash_line(draw, (left, zb), (right, zb), (195, 127, 26, 155), width=line_w, dash=10, gap=7)

    def _inside_decision(price: float) -> bool:
        return zone_low is not None and zone_high is not None and float(zone_low) - 1e-9 <= price <= float(zone_high) + 1e-9

    specs = (
        ("resistance_levels", "R", (221, 63, 72, 255), (221, 63, 72, 28), lambda p: p > float(current)),
        ("support_levels", "S", (42, 111, 214, 255), (42, 111, 214, 28), lambda p: p < float(current)),
    )
    for key, prefix, color, fill, side_ok in specs:
        candidates: list[tuple[float, int, int]] = []
        for item in analysis.get(key) or []:
            if not isinstance(item, dict):
                continue
            price = _number(item.get("price"))
            if price is None or not side_ok(float(price)) or _inside_decision(float(price)):
                continue
            strength = max(0, min(100, int(item.get("strength") or 0)))
            touches = max(1, int(item.get("touches") or 1))
            candidates.append((float(price), strength, touches))
        candidates.sort(key=lambda item: abs(item[0] - float(current)))
        for rank, (price, strength, touches) in enumerate(candidates[:2], 1):
            y = _native_y(analysis, price, height)
            if y is None or not (2 <= y <= height - 3):
                continue
            # Stronger levels get a slightly wider visible band, never a moved level.
            half = band_half + (2 if strength >= 80 else 0)
            draw.rounded_rectangle((left, max(1, y-half), right, min(height-2, y+half)), radius=max(3, half//2), fill=fill)
            draw.line((left, y, right, y), fill=(color[0], color[1], color[2], 205 if strength >= 75 else 170), width=line_w)
            strength_text = f" · {strength}%" if strength else ""
            touch_text = f" · {touches}x" if touches >= 3 else ""
            _native_tag(
                draw,
                left + max(4, int(width * 0.006)),
                y,
                f"{prefix}{rank} {_fmt_axis_price(price)}{strength_text}{touch_text}",
                fill=(color[0], color[1], color[2], 205),
                font=font,
                pad_x=label_pad_x,
                pad_y=label_pad_y,
            )

def _native_draw_zones(
    image: Image.Image,
    analysis: dict[str, Any],
    width: int,
    height: int,
    font,
    candle_centers: list[int] | None = None,
) -> None:
    candles = _valid_renderer_candles(analysis)
    if not candles or not candle_centers:
        return
    current = _number(analysis.get("current_price"))
    entry = _number(analysis.get("entry"))
    focal = float(entry if entry is not None else (current if current is not None else candles[-1]["close"]))
    atr = median([max(0.01, float(c["high"]) - float(c["low"])) for c in candles])
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    geometry = {"window_size": len(candles)}
    gaps = [b - a for a, b in zip(candle_centers[:-1], candle_centers[1:]) if b > a]
    spacing = max(8, int(median(gaps))) if gaps else max(10, width // max(12, len(candle_centers)))
    latest_x = max(candle_centers)

    ob = _nearest_detected_order_block(analysis, candles, focal, float(atr))
    if ob is not None:
        index, low, high, _strength = ob
        y1 = _native_y(analysis, float(high), height)
        y2 = _native_y(analysis, float(low), height)
        x1 = _native_index_x(analysis, geometry, int(index), candle_centers)
        if y1 is not None and y2 is not None and x1 is not None:
            y1, y2 = sorted((y1, y2))
            x2 = min(int(width * 0.86), max(x1 + spacing * 5, latest_x + spacing))
            if y2 <= y1:
                y2 = min(height - 2, y1 + 1)
            if x2 > x1 + 4:
                draw.rectangle((x1, y1, x2, y2), fill=(39, 112, 220, 30), outline=(39, 112, 220, 105), width=1)
                draw.text(((x1 + x2) // 2, (y1 + y2) // 2), "ORDER BLOCK", font=font, fill=(28, 77, 146, 205), anchor="mm")

    fvg = _nearest_detected_fvg(candles, focal, float(atr))
    if fvg is not None:
        index, low, high = fvg
        y1 = _native_y(analysis, float(high), height)
        y2 = _native_y(analysis, float(low), height)
        x1 = _native_index_x(analysis, geometry, int(index), candle_centers)
        if y1 is not None and y2 is not None and x1 is not None:
            y1, y2 = sorted((y1, y2))
            x2 = min(int(width * 0.86), max(x1 + spacing * 4, latest_x))
            if y2 <= y1:
                y2 = min(height - 2, y1 + 1)
            if x2 > x1 + 4:
                draw.rectangle((x1, y1, x2, y2), fill=(232, 147, 45, 24), outline=(218, 133, 35, 90), width=1)
                draw.text(((x1 + x2) // 2, (y1 + y2) // 2), "FVG", font=font, fill=(145, 82, 22, 200), anchor="mm")
    image.alpha_composite(layer)


def _native_structure_events(
    analysis: dict[str, Any],
    candles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build recent market-structure events from real swing breaks only.

    A break exists only when a later closed candle closes beyond the latest
    known swing high/low. The first break establishes structure. A break in the
    same direction is BOS; the first opposite break is CHOCH and flips the
    structure state. IDM is an actual internal opposite swing inside the most
    recent BOS leg. No floating label is created without a source swing.
    """
    highs, lows = _simple_swing_points(candles, window=2)
    if not highs and not lows:
        return []
    atr_values = [max(0.01, float(c["high"]) - float(c["low"])) for c in candles[-24:]]
    atr = max(0.01, float(median(atr_values))) if atr_values else 0.25
    tolerance = atr * 0.05

    high_by_idx = {int(i): float(p) for i, p in highs}
    low_by_idx = {int(i): float(p) for i, p in lows}
    broken_highs: set[int] = set()
    broken_lows: set[int] = set()
    active_high: tuple[int, float] | None = None
    active_low: tuple[int, float] | None = None
    structural_side: str | None = None
    events: list[dict[str, Any]] = []

    for j in range(len(candles)):
        # A 2-bar pivot becomes knowable only after two candles to its right.
        pivot_idx = j - 2
        if pivot_idx in high_by_idx:
            active_high = (pivot_idx, high_by_idx[pivot_idx])
        if pivot_idx in low_by_idx:
            active_low = (pivot_idx, low_by_idx[pivot_idx])
        close = float(candles[j]["close"])

        candidate: dict[str, Any] | None = None
        if active_high is not None and active_high[0] not in broken_highs and j >= active_high[0] + 2:
            if close > active_high[1] + tolerance:
                candidate = {
                    "side": "bull",
                    "swing_index": active_high[0],
                    "break_index": j,
                    "price": active_high[1],
                }
                broken_highs.add(active_high[0])
        if active_low is not None and active_low[0] not in broken_lows and j >= active_low[0] + 2:
            if close < active_low[1] - tolerance:
                bear = {
                    "side": "bear",
                    "swing_index": active_low[0],
                    "break_index": j,
                    "price": active_low[1],
                }
                broken_lows.add(active_low[0])
                if candidate is None:
                    candidate = bear
                else:
                    # A single candle should not normally break both sides. If it
                    # does, keep the break that travelled farther beyond its level.
                    bull_excess = close - float(candidate["price"])
                    bear_excess = float(bear["price"]) - close
                    if bear_excess > bull_excess:
                        candidate = bear
        if candidate is None:
            continue

        side = str(candidate["side"])
        if structural_side is None:
            label = "BOS"
            structural_side = side
        elif side == structural_side:
            label = "BOS"
        else:
            label = "CHOCH"
            structural_side = side
        candidate["label"] = label
        events.append(candidate)

    if not events:
        return []
    recent_floor = max(0, len(candles) - 34)
    recent_events = [e for e in events if int(e["break_index"]) >= recent_floor]
    if not recent_events:
        return []

    last_choch = next((e for e in reversed(recent_events) if e["label"] == "CHOCH"), None)
    bos_candidates = [e for e in recent_events if e["label"] == "BOS"]
    if last_choch is not None:
        after = [e for e in bos_candidates if int(e["break_index"]) > int(last_choch["break_index"])]
        last_bos = after[-1] if after else None
    else:
        last_bos = bos_candidates[-1] if bos_candidates else None

    result: list[dict[str, Any]] = []
    if last_bos is not None:
        result.append(dict(last_bos))
    if last_choch is not None:
        result.append(dict(last_choch))

    # IDM = last real opposite swing inside the latest BOS leg only.
    if last_bos is not None:
        a = int(last_bos["swing_index"])
        b = int(last_bos["break_index"])
        if str(last_bos["side"]) == "bull":
            internal = [(i, p) for i, p in lows if a < i < b]
        else:
            internal = [(i, p) for i, p in highs if a < i < b]
        if internal:
            i, price = internal[-1]
            result.append({
                "side": str(last_bos["side"]),
                "swing_index": int(i),
                "break_index": int(i),
                "price": float(price),
                "label": "IDM",
            })
    return result[:3]

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
    events = _native_structure_events(analysis, candles)
    geometry = {"window_size": len(candles)}
    dot = max(3, int(height * 0.0055))
    for event in events:
        try:
            start_idx = int(event["swing_index"])
            break_idx = int(event["break_index"])
            price = float(event["price"])
            label = str(event["label"])
        except (KeyError, TypeError, ValueError):
            continue
        y = _native_y(analysis, price, height)
        x1 = _native_index_x(analysis, geometry, start_idx, candle_centers)
        x2 = _native_index_x(analysis, geometry, break_idx, candle_centers)
        if y is None or x1 is None:
            continue
        draw.ellipse((x1-dot, y-dot, x1+dot, y+dot), fill=(246, 248, 251, 220), outline=(46, 55, 67, 220), width=1)
        if label in {"BOS", "CHOCH"} and x2 is not None and x2 > x1 + 3:
            _dash_line(draw, (x1 + dot + 1, y), (x2, y), (50, 58, 69, 170), width=max(1, int(height * 0.0017)), dash=max(5, int(width * 0.006)), gap=max(3, int(width * 0.004)))
            text_x = min(width - 8, x1 + max(10, (x2 - x1) // 2))
            draw.text((text_x, y - 5), label, font=font, fill=(31, 38, 47, 210), anchor="ms")
        else:
            lead = max(30, int(width * 0.055))
            x_end = max(int(width * 0.03), x1 - lead) if x1 > width * 0.20 else min(int(width * 0.84), x1 + lead)
            _dash_line(draw, (x1 - dot - 1 if x_end < x1 else x1 + dot + 1, y), (x_end, y), (50, 58, 69, 155), width=max(1, int(height * 0.0015)), dash=max(5, int(width * 0.006)), gap=max(3, int(width * 0.004)))
            draw.text((x_end - 4 if x_end < x1 else x_end + 4, y), label, font=font, fill=(31, 38, 47, 205), anchor="rm" if x_end < x1 else "lm")




def _ratio_point_to_px(point: Any, width: int, height: int, bounds: tuple[int, int, int, int]) -> tuple[int, int] | None:
    if not (isinstance(point, list) and len(point) >= 2):
        return None
    try:
        xr = float(point[0]); yr = float(point[1])
    except (TypeError, ValueError):
        return None
    if not (0.0 <= xr <= 1.0 and 0.0 <= yr <= 1.0):
        return None
    x = max(bounds[0], min(bounds[2], int(round(xr * max(1, width - 1)))))
    y = max(bounds[1], min(bounds[3], int(round(yr * max(1, height - 1)))))
    return x, y


def _visual_overlay_bounds(analysis: dict[str, Any], width: int, height: int) -> tuple[int, int, int, int]:
    raw = analysis.get("visual_chart_plot_bounds")
    if isinstance(raw, list) and len(raw) >= 4:
        try:
            x1, y1, x2, y2 = [float(v) for v in raw[:4]]
            x1, x2 = sorted((max(0.0, min(1.0, x1)), max(0.0, min(1.0, x2))))
            y1, y2 = sorted((max(0.0, min(1.0, y1)), max(0.0, min(1.0, y2))))
            if x2 - x1 >= 0.20 and y2 - y1 >= 0.20:
                return (
                    int(round(x1 * (width - 1))), int(round(y1 * (height - 1))),
                    int(round(x2 * (width - 1))), int(round(y2 * (height - 1))),
                )
        except (TypeError, ValueError):
            pass
    return (0, 0, width - 1, height - 1)



def _v368_safe_text(value: str) -> str:
    """Strip internal/debug artifacts and broken glyph placeholders from UI text."""
    text = str(value or "")
    for bad in ("\ufffd", "□□", "□", "\x00"):
        text = text.replace(bad, "")
    # Source IDs belong in debug logs, never in the customer-facing overlay.
    if text.upper().startswith("SOURCE "):
        return ""
    return " ".join(text.split()).strip()


def _image_is_dark(image: Image.Image, bounds: tuple[int, int, int, int]) -> bool:
    x1, y1, x2, y2 = bounds
    samples = []
    for rx, ry in ((0.08,0.08),(0.5,0.12),(0.12,0.50),(0.88,0.50),(0.5,0.88)):
        x = max(0, min(image.width-1, int(x1 + (x2-x1)*rx)))
        y = max(0, min(image.height-1, int(y1 + (y2-y1)*ry)))
        r,g,b,*_ = image.convert('RGBA').getpixel((x,y))
        samples.append((r+g+b)/3)
    return (sum(samples)/max(1,len(samples))) < 118


def _v368_label(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font,
    accent: tuple[int,int,int,int],
    image_size: tuple[int,int],
    bounds: tuple[int,int,int,int],
    *,
    anchor: str = "mm",
    compact: bool = False,
) -> tuple[int,int,int,int] | None:
    text = _v368_safe_text(text)
    if not text:
        return None
    box = draw.textbbox((0,0), text, font=font)
    tw = max(1, box[2]-box[0]); th=max(1,box[3]-box[1])
    px = 4 if compact else 7; py = 2 if compact else 4
    if anchor in {"ma","mm","ms"}:
        left = x - tw//2 - px
    elif anchor.endswith("r"):
        left = x - tw - px*2
    else:
        left = x
    top = y - th//2 - py if anchor.endswith("m") or anchor == "mm" else y - py
    bx1,by1,bx2,by2=bounds
    left=max(bx1+2,min(bx2-tw-px*2-2,left)); top=max(by1+2,min(by2-th-py*2-2,top))
    right=left+tw+px*2; bottom=top+th+py*2
    fill=(7,15,24,190) if accent[0]+accent[1]+accent[2] > 540 else (250,252,255,218)
    text_fill=(248,250,253,245) if fill[0] < 100 else (28,36,47,245)
    draw.rounded_rectangle((left,top,right,bottom),radius=max(4,py+2),fill=fill,outline=(accent[0],accent[1],accent[2],150),width=1)
    draw.text((left+px,(top+bottom)//2),text,font=font,fill=text_fill,anchor="lm")
    return (left,top,right,bottom)

def _native_draw_visual_reference_geometry(
    image: Image.Image,
    analysis: dict[str, Any],
    width: int,
    height: int,
    font,
) -> bool:
    """v3.68: rich but orderly pixel-anchored educational geometry.

    The uploaded chart pixels remain immutable.  Pattern pivots, structure
    labels, OB/FVG/liquidity zones and the expected path are composited above
    the chart only after the deterministic family/scenario gate succeeds.
    """
    score = int(analysis.get("visual_geometry_score") or 0)
    scenario_ok = bool(analysis.get("reference_scenario_available"))
    pattern_ok = str(analysis.get("pattern_type") or "لا يوجد") != "لا يوجد" and int(analysis.get("pattern_confidence") or 0) >= 60
    if score < 68 or not (scenario_ok or pattern_ok):
        return False

    path_raw = analysis.get("visual_pattern_path") or []
    lines_raw = analysis.get("visual_pattern_lines") or []
    structures = analysis.get("visual_structure_lines") or []
    zones = analysis.get("visual_zones") or []
    expected = analysis.get("visual_expected_path") or []
    if not (path_raw or lines_raw or structures or zones or expected):
        return False

    bounds = _visual_overlay_bounds(analysis, width, height)
    analysis["educational_overlay_bounds"] = list(bounds)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    status = str(analysis.get("reference_scenario_status") or analysis.get("pattern_status") or "candidate")
    confirmed = status == "confirmed"
    bias = str(analysis.get("reference_scenario_bias") or analysis.get("pattern_bias") or "محايد")
    components = set(str(x) for x in (analysis.get("reference_scenario_draw_components") or []))
    line_w = max(2, int(round(min(width, height) * 0.0031)))
    thin_w = max(1, line_w - 1)
    dash = max(8, int(round(min(width, height) * 0.013)))
    gap = max(5, int(round(min(width, height) * 0.007)))
    pattern_color = (76, 116, 235, 242)
    pattern_under = (7, 12, 19, 118)
    text_dark = (24, 31, 41, 244)
    structure_color = (233, 238, 245, 235) if _image_is_dark(image, bounds) else (35, 44, 57, 230)

    # Zones: calm translucency + explicit label; no visual element moves its source.
    allowed = set()
    if "order_block" in components: allowed.add("order_block")
    if "fvg" in components: allowed.add("fvg")
    if "liquidity" in components: allowed.add("liquidity_area")
    for item in zones[:6]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        if scenario_ok and allowed and kind not in allowed:
            continue
        rect = item.get("rect")
        if not (isinstance(rect, list) and len(rect) >= 4):
            continue
        p1 = _ratio_point_to_px(rect[:2], width, height, bounds)
        p2 = _ratio_point_to_px(rect[2:4], width, height, bounds)
        if p1 is None or p2 is None:
            continue
        x1, x2 = sorted((p1[0], p2[0])); y1, y2 = sorted((p1[1], p2[1]))
        if x2 - x1 < 8 or y2 - y1 < 6:
            continue
        if kind == "order_block":
            bullish = bias == "صاعد"
            fill = (31, 166, 111, 42) if bullish else (218, 70, 76, 42)
            outline = (31, 144, 97, 160) if bullish else (194, 55, 64, 160)
            label = "OB"
        elif kind == "fvg":
            fill = (245, 158, 11, 34); outline = (205, 127, 21, 150); label = "FVG"
        else:
            fill = (65, 137, 218, 30); outline = (50, 111, 190, 145); label = "LIQUIDITY"
        radius = max(5, line_w * 2)
        draw.rounded_rectangle((x1, y1, x2, y2), radius=radius, fill=fill, outline=outline, width=thin_w)
        _v368_label(draw, x1 + 6, y1 + 6, label, font, outline, image.size, bounds, anchor="la")

    # Pattern boundaries and a clean teaching skeleton.  Candidate geometry is dashed.
    if pattern_ok or "pattern" in components:
        for item in lines_raw[:8]:
            if not (isinstance(item, list) and len(item) >= 4):
                continue
            p1 = _ratio_point_to_px(item[:2], width, height, bounds)
            p2 = _ratio_point_to_px(item[2:4], width, height, bounds)
            if p1 is None or p2 is None:
                continue
            draw.line((p1, p2), fill=pattern_under, width=line_w + 3)
            if confirmed:
                draw.line((p1, p2), fill=pattern_color, width=line_w)
            else:
                _dash_line(draw, p1, p2, pattern_color, width=line_w, dash=dash, gap=gap)

        path = []
        for point in path_raw[:14]:
            px = _ratio_point_to_px(point, width, height, bounds)
            if px is not None:
                path.append(px)
        if len(path) >= 2:
            for a, b in zip(path[:-1], path[1:]):
                draw.line((a, b), fill=pattern_under, width=line_w + 4)
                if confirmed:
                    draw.line((a, b), fill=(245, 248, 252, 245), width=line_w)
                else:
                    _dash_line(draw, a, b, (245, 248, 252, 238), width=line_w, dash=dash, gap=gap)
            r = max(4, line_w + 1)
            for i, (x, y) in enumerate(path):
                draw.ellipse((x-r, y-r, x+r, y+r), fill=(248, 251, 255, 235), outline=pattern_color, width=thin_w)
                if len(path) <= 6:
                    label = chr(ord('A') + i)
                    draw.text((x, y-r-4), label, font=font, fill=pattern_color, anchor="ms")

    # Structure labels get their own soft chip so BOS/CHOCH/MSS/IDM remain readable.
    for item in structures[:8]:
        if not isinstance(item, dict):
            continue
        line = item.get("line"); label = _v368_safe_text(str(item.get("label") or ""))
        if not (isinstance(line, list) and len(line) >= 4 and label):
            continue
        p1 = _ratio_point_to_px(line[:2], width, height, bounds)
        p2 = _ratio_point_to_px(line[2:4], width, height, bounds)
        if p1 is None or p2 is None:
            continue
        _dash_line(draw, p1, p2, structure_color, width=thin_w, dash=max(7, dash-2), gap=gap)
        mx = (p1[0] + p2[0]) // 2; my = (p1[1] + p2[1]) // 2
        _v368_label(draw, mx, my - 7, label, font, structure_color, image.size, bounds, anchor="ms")

    anchor_points = [_ratio_point_to_px(pt, width, height, bounds) for pt in path_raw]
    anchor_points = [pt for pt in anchor_points if pt is not None]
    label = _v368_safe_text(str(analysis.get("reference_scenario_label") or analysis.get("pattern_type") or "").strip())
    if label and anchor_points:
        xs = [p[0] for p in anchor_points]; ys = [p[1] for p in anchor_points]
        accent = (20, 159, 99, 230) if bias == "صاعد" else (218, 61, 70, 230) if bias == "هابط" else pattern_color
        short = label if len(label) <= 42 else label[:39] + "…"
        suffix = " ✓" if confirmed else " · مرشح"
        _v368_label(draw, int(sum(xs)/len(xs)), max(bounds[1] + 18, min(ys) - 20), short + suffix, font, accent, image.size, bounds, anchor="ma")

    # Expected path: 3–5 instructional stages, with a subtle under-stroke and stage labels.
    forecast = []
    for point in expected[:6]:
        px = _ratio_point_to_px(point, width, height, bounds)
        if px is not None:
            forecast.append(px)
    if len(forecast) < 3 and anchor_points and bias in {"صاعد", "هابط"}:
        sx, sy = anchor_points[-1]
        span_x = max(55, int((bounds[2] - bounds[0]) * 0.18))
        step_x = max(24, span_x // 3)
        primary_dy = max(28, int((bounds[3] - bounds[1]) * 0.10))
        sign = -1 if bias == "صاعد" else 1
        p1 = (min(bounds[2]-8, sx + step_x), max(bounds[1]+8, min(bounds[3]-8, sy + sign * primary_dy * 0.45)))
        p2 = (min(bounds[2]-8, sx + step_x*2), max(bounds[1]+8, min(bounds[3]-8, sy - sign * primary_dy * 0.12)))
        p3 = (min(bounds[2]-8, sx + step_x*3), max(bounds[1]+8, min(bounds[3]-8, sy + sign * primary_dy)))
        forecast = [(sx, sy), p1, p2, p3]
    if len(forecast) >= 2 and bias in {"صاعد", "هابط"}:
        col = (19, 170, 101, 238) if bias == "صاعد" else (224, 61, 70, 238)
        shadow = (5, 10, 15, 120)
        for a, b in zip(forecast[:-1], forecast[1:]):
            draw.line((a, b), fill=shadow, width=line_w + 5)
            if confirmed:
                draw.line((a, b), fill=col, width=line_w + 1)
            else:
                _dash_line(draw, a, b, col, width=line_w + 1, dash=dash, gap=gap)
        _native_draw_arrow(draw, forecast[-2], forecast[-1], col, width=line_w + 1)
        stage_labels = ["BREAK", "RETEST", "TARGET"]
        for idx, pt in enumerate(forecast[1:4]):
            if idx < len(stage_labels):
                _v368_label(draw, pt[0], pt[1] - 8, stage_labels[idx], font, col, image.size, bounds, anchor="ms", compact=True)

    image.alpha_composite(layer)
    analysis["educational_overlay_visual_geometry_used"] = True
    return True

def _native_draw_reference_scenario(
    image: Image.Image,
    analysis: dict[str, Any],
    width: int,
    height: int,
    font,
    candle_centers: list[int],
) -> None:
    """Draw only the components of the closest verified reference scenario.

    The scenario memory is explanatory, never generative: every visible line,
    zone and marker is backed by closed-M5 geometry saved by the deterministic
    reference_scenario_engine.  Candidate scenarios use dashed expectation;
    confirmed scenarios use a solid expectation arrow.
    """
    if not bool(analysis.get("reference_scenario_available")) or len(candle_centers) < 6:
        # Classical source pattern remains the safe fallback.
        _native_draw_pattern_overlays(image, analysis, width, height, font, candle_centers)
        return

    components = set(str(x) for x in (analysis.get("reference_scenario_draw_components") or []))
    geometry = analysis.get("reference_scenario_geometry") if isinstance(analysis.get("reference_scenario_geometry"), dict) else {}
    bias = str(analysis.get("reference_scenario_bias") or "محايد")
    status = str(analysis.get("reference_scenario_status") or "candidate")
    confirmed = status == "confirmed"

    # Draw market-index classical geometry only when no trustworthy pixel-anchored
    # visual geometry exists.  v3.68 prefers exact screenshot anchors so a stale
    # or differently cropped upload cannot shift the pattern horizontally.
    visual_ready = int(analysis.get("visual_geometry_score") or 0) >= 68 and bool(analysis.get("visual_pattern_path") or analysis.get("visual_pattern_lines"))
    if "pattern" in components and analysis.get("pattern_overlays") and not visual_ready:
        _native_draw_pattern_overlays(image, analysis, width, height, font, candle_centers)

    if "structure" in components:
        _native_draw_structure(ImageDraw.Draw(image), analysis, width, height, font, candle_centers)

    if "order_block" in components or "fvg" in components:
        # The helper redraws only actually detected M5 zones.  It never fabricates one.
        _native_draw_zones(image, analysis, width, height, font, candle_centers)

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    native_geom = {"window_size": int(geometry.get("window_size") or len(candle_centers))}
    line_w = max(1, int(height * 0.0018))
    gaps = [b-a for a,b in zip(candle_centers[:-1], candle_centers[1:]) if 2 <= b-a <= width*0.12]
    spacing = max(8, int(median(gaps))) if gaps else max(9, width // max(14, len(candle_centers)))

    # Liquidity sweep is anchored to the real swept pivot price and sweep candle.
    if "liquidity" in components:
        sweep = geometry.get("liquidity_sweep") if isinstance(geometry.get("liquidity_sweep"), dict) else None
        if sweep:
            try:
                idx = int(sweep.get("index")); price = float(sweep.get("price")); side = str(sweep.get("side"))
            except (TypeError, ValueError):
                idx = -1; price = 0.0; side = ""
            x = _native_index_x(analysis, native_geom, idx, candle_centers) if idx >= 0 else None
            y = _native_y(analysis, price, height) if idx >= 0 else None
            if x is not None and y is not None:
                x1 = max(8, x - spacing * 4)
                x2 = min(width - 8, x + spacing)
                color = (201, 67, 75, 190) if side == "high" else (26, 145, 91, 190)
                _dash_line(draw, (x1, y), (x2, y), color, width=line_w, dash=max(6, spacing//2), gap=max(4, spacing//3))
                draw.text(((x1+x2)//2, y-5), "Liquidity Sweep", font=font, fill=color, anchor="ms")

    # Engulfing is shown only as a small factual candle marker, not a new model.
    if "engulfing" in components:
        engulf = geometry.get("engulfing") if isinstance(geometry.get("engulfing"), dict) else None
        if engulf:
            try:
                idx = int(engulf.get("index")); side = str(engulf.get("side"))
            except (TypeError, ValueError):
                idx = -1; side = ""
            x = _native_index_x(analysis, native_geom, idx, candle_centers) if idx >= 0 else None
            candles = _valid_renderer_candles(analysis)
            if x is not None and 0 <= idx < len(candles):
                high_y = _native_y(analysis, float(candles[idx]["high"]), height)
                low_y = _native_y(analysis, float(candles[idx]["low"]), height)
                if high_y is not None and low_y is not None:
                    top,bottom=sorted((high_y,low_y)); pad=max(4,spacing//3)
                    color=(23,150,91,190) if side=="bull" else (207,59,68,190)
                    draw.rounded_rectangle((x-pad, top-3, x+pad, bottom+3), radius=4, outline=color, width=max(1,line_w))
                    draw.text((x, max(10, top-7)), "Engulfing", font=font, fill=color, anchor="ms")

    # Compact scenario name: one label, never a large educational title.
    label = str(analysis.get("reference_scenario_label") or "").strip()
    if label:
        color = (19, 139, 83, 220) if bias == "صاعد" else (204, 57, 66, 220) if bias == "هابط" else (43, 104, 196, 220)
        suffix = " ✓" if confirmed else " — مرشح"
        text = f"{label}{suffix}"
        bbox = draw.textbbox((0,0), text, font=font)
        tw=max(1,bbox[2]-bbox[0]); th=max(1,bbox[3]-bbox[1])
        lx=max(8,min(width-tw-22,int(width*0.50)-tw//2)); ly=max(8,int(height*0.035))
        draw.rounded_rectangle((lx-7,ly-5,lx+tw+7,ly+th+5),radius=6,fill=(252,253,255,224),outline=color,width=1)
        draw.text((lx,ly),text,font=font,fill=(35,44,55,235))

    # Mandatory expectation arrow for an accepted reference scenario.
    if "expectation_arrow" in components and bias in {"صاعد", "هابط"}:
        current = _number(analysis.get("current_price"))
        target = _number(analysis.get("target_1"))
        if current is not None:
            # If TP1 is off the visible axis, use the nearest real level in the same direction.
            if target is None or _native_y(analysis, float(target), height) is None:
                key = "resistance_levels" if bias == "صاعد" else "support_levels"
                valid: list[float] = []
                for item in analysis.get(key) or []:
                    if not isinstance(item, dict):
                        continue
                    price = _number(item.get("price"))
                    if price is None:
                        continue
                    if bias == "صاعد" and float(price) > float(current): valid.append(float(price))
                    if bias == "هابط" and float(price) < float(current): valid.append(float(price))
                if valid:
                    target = min(valid, key=lambda p: abs(p-float(current)))
            sy = _native_y(analysis, float(current), height)
            ty = _native_y(analysis, float(target), height) if target is not None else None
            if sy is not None and ty is not None:
                sx = candle_centers[-1]
                ex = min(width-12, max(sx+spacing*5, int(width*0.80)))
                color = (20, 151, 91, 225) if bias == "صاعد" else (207, 58, 67, 225)
                if confirmed:
                    _native_draw_arrow(draw, (sx,sy), (ex,ty), color, width=max(3,line_w+2))
                else:
                    bend_x=min(ex-spacing, sx+spacing*2)
                    bend_y=int(round((sy+ty)/2))
                    _dash_line(draw,(sx,sy),(bend_x,bend_y),color,width=max(2,line_w+1),dash=max(7,spacing//2),gap=max(5,spacing//3))
                    _dash_line(draw,(bend_x,bend_y),(ex,ty),color,width=max(2,line_w+1),dash=max(7,spacing//2),gap=max(5,spacing//3))
                    _native_draw_arrow(draw,(bend_x,bend_y),(ex,ty),color,width=max(2,line_w+1))

    image.alpha_composite(layer)


# v3.65: browser/GIF animation remains intentionally removed.
# The closest verified reference scenario is rendered as a static overlay.
# The selected source-matched pattern is drawn as one static overlay directly
# on the untouched uploaded chart; its expectation arrow is produced by
# _native_draw_pattern_overlays and remains tied to real M5 geometry.


def _native_draw_trade(image: Image.Image, analysis: dict[str, Any], width: int, height: int, font) -> None:
    """v3.68: clear Entry/Stop/Cancel/TP cards and risk-reward zones.

    Cards remain price-anchored.  Their centers are always at the true y of the
    corresponding source-axis price; only horizontal placement/label width may
    change to avoid hiding candles.
    """
    action = analysis.get("action_summary") if isinstance(analysis.get("action_summary"), dict) else {}
    code = str(action.get("code") or analysis.get("draw_mode") or "watch")
    side = str(action.get("primary_side") or "wait")
    confirmed = bool(action.get("is_confirmed")) or code in {"buy", "sell", "confirmed"}
    if code in {"inactive", "no_trade", "watch"} or side == "wait":
        return

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    bounds = analysis.get("educational_overlay_bounds")
    if isinstance(bounds, list) and len(bounds) >= 4:
        plot_left, _pt, plot_right, _pb = [int(v) for v in bounds[:4]]
    else:
        plot_left, plot_right = int(width * 0.04), int(width * 0.86)
    zone_left = max(plot_left, int(plot_left + (plot_right-plot_left) * 0.62))
    zone_right = min(width - 4, plot_right)
    line_left = max(plot_left, int(plot_left + (plot_right-plot_left) * 0.50))
    tag_x = max(line_left + 8, zone_right - max(150, int(width * 0.20)))
    line_w = max(2, int(round(min(width, height) * 0.0024)))
    pad_x = max(5, int(width * 0.005)); pad_y = max(3, int(height * 0.003))

    if not confirmed:
        trigger = _number(action.get("trigger"))
        cancel = _number(action.get("cancel"))
        if trigger is None:
            return
        ty = _native_y(analysis, float(trigger), height)
        if ty is not None:
            _dash_line(draw, (line_left, ty), (zone_right, ty), (234, 147, 35, 220), width=line_w, dash=9, gap=6)
            _native_tag(draw, tag_x, ty, f"ENTRY IF {_fmt_axis_price(trigger)}", fill=(190, 112, 24, 220), font=font, pad_x=pad_x, pad_y=pad_y)
        if cancel is not None:
            cy = _native_y(analysis, float(cancel), height)
            if cy is not None:
                _dash_line(draw, (line_left, cy), (zone_right, cy), (211, 64, 72, 190), width=line_w, dash=8, gap=6)
                _native_tag(draw, tag_x, cy, f"CANCEL {_fmt_axis_price(cancel)}", fill=(185, 51, 59, 205), font=font, pad_x=pad_x, pad_y=pad_y)
        image.alpha_composite(layer)
        return

    entry = _number(analysis.get("entry")) or _number(analysis.get("current_price"))
    stop = _number(analysis.get("stop_loss"))
    targets = [_number(analysis.get(k)) for k in ("target_1", "target_2", "target_3")]
    targets = [float(v) for v in targets if v is not None]
    if entry is None or stop is None or not targets:
        return
    ey = _native_y(analysis, float(entry), height); sy = _native_y(analysis, float(stop), height)
    ty_pairs = [(value, _native_y(analysis, value, height)) for value in targets]
    ty_pairs = [(value, y) for value, y in ty_pairs if y is not None]
    if ey is None or sy is None or not ty_pairs:
        return

    far_y = ty_pairs[-1][1]
    # Target and stop risk/reward blocks are intentionally translucent so the original candles remain visible.
    draw.rounded_rectangle((zone_left, min(ey, far_y), zone_right, max(ey, far_y)), radius=8, fill=(23, 184, 111, 44), outline=(20, 145, 91, 120), width=1)
    draw.rounded_rectangle((zone_left, min(ey, sy), zone_right, max(ey, sy)), radius=8, fill=(225, 65, 72, 42), outline=(188, 49, 58, 120), width=1)

    levels: list[tuple[str, float, int, tuple[int,int,int,int]]] = [
        ("ENTRY", float(entry), ey, (17, 151, 102, 225)),
        ("SL", float(stop), sy, (202, 53, 61, 225)),
    ]
    target_colors = [(32, 180, 105, 220), (22, 151, 91, 220), (13, 122, 77, 220)]
    levels += [(f"TP{i}", value, y, target_colors[min(i-1, 2)]) for i, (value, y) in enumerate(ty_pairs[:3], start=1)]
    cancel = _number(action.get("cancel"))
    if cancel is not None:
        cy = _native_y(analysis, float(cancel), height)
        if cy is not None and abs(cy - sy) > max(12, int(height * 0.012)):
            levels.append(("CANCEL", float(cancel), cy, (204, 105, 29, 215)))
    for label, value, y, color in levels:
        _dash_line(draw, (line_left, y), (zone_right, y), color, width=line_w, dash=9, gap=6)
        _native_tag(draw, tag_x, y, f"{label} {_fmt_axis_price(value)}", fill=color, font=font, pad_x=pad_x, pad_y=pad_y)

    risk = abs(float(entry) - float(stop))
    reward = abs(float(ty_pairs[0][0]) - float(entry)) if ty_pairs else 0.0
    if risk > 1e-9 and reward > 0:
        rr = reward / risk
        rr_y = int(round((ey + ty_pairs[0][1]) / 2))
        _v368_label(draw, int((zone_left + zone_right)/2), rr_y, f"RR 1:{rr:.1f}", font, (22, 126, 84, 220), image.size, (plot_left, 0, plot_right, height-1), anchor="mm", compact=True)
    image.alpha_composite(layer)

def _render_uploaded_chart_with_overlays(
    analysis: dict[str, Any],
    chart_background_path: str | os.PathLike[str] | None,
) -> bytes:
    """Composite one clean educational overlay over the exact uploaded chart."""
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
    font_size = max(9, min(16, int(round(min(width, height) * 0.018))))
    font = _font(font_size, True, True)

    # Price mapping: prefer strict pixel calibration.  If it fails but the
    # screenshot reader supplied at least two literal broker ticks, permit only
    # piecewise interpolation between those real labels.  No synthetic scale.
    analysis.pop("_native_axis_pixel_model", None)
    pixel_axis_model = _native_build_pixel_axis_model(image, analysis)
    if pixel_axis_model is not None:
        analysis["_native_axis_pixel_model"] = pixel_axis_model
        analysis["_native_axis_strict_pixel"] = True
        analysis["native_axis_pixel_calibration_passed"] = True
    else:
        literal = _native_literal_axis_points(analysis)
        analysis["native_axis_pixel_calibration_passed"] = False
        if len(literal) >= 2:
            analysis["_native_axis_strict_pixel"] = False
            analysis["native_axis_projection_mode"] = "literal_piecewise_fallback"
        else:
            analysis["_native_axis_strict_pixel"] = True
            analysis["native_axis_projection_mode"] = "hidden_untrusted_axis"

    # Market candle index mapping is optional in v3.68.  If exact screenshot to
    # market alignment fails, the visual-reference geometry still places the
    # verified model directly on real visible pivots without recreating candles.
    candle_centers = _native_detect_candle_centers(image)
    analysis.pop("_native_candle_x_map", None)
    candle_x_map = _native_build_candle_x_map(image, analysis, candle_centers) if pixel_axis_model is not None else {}
    if candle_x_map:
        analysis["_native_candle_x_map"] = candle_x_map
    analysis.pop("animation_plan", None)

    scenario_available = bool(analysis.get("reference_scenario_available"))
    pattern_available = str(analysis.get("pattern_type") or "لا يوجد") != "لا يوجد"

    # v3.68: organized richness.  S/R context is always allowed when it is
    # price-calibrated; the primary scenario then adds its own geometry/zones.
    # Exact uploaded pixels remain the base layer throughout.
    _native_draw_sr(ImageDraw.Draw(image), analysis, width, height, font)
    used_visual = False
    if scenario_available or pattern_available:
        used_visual = _native_draw_visual_reference_geometry(image, analysis, width, height, font)
    if scenario_available:
        # If pixel-anchored geometry was unavailable, fall back to deterministic
        # market-index geometry.  Do not double-draw the same pattern/structure.
        if not used_visual:
            _native_draw_reference_scenario(image, analysis, width, height, font, candle_centers)
        else:
            # Deterministic OB/FVG can supplement a visual pattern when the image
            # matcher did not return those rectangles.
            if not analysis.get("visual_zones") and ({"order_block","fvg"} & set(str(x) for x in (analysis.get("reference_scenario_draw_components") or []))):
                _native_draw_zones(image, analysis, width, height, font, candle_centers)
    elif pattern_available and not used_visual:
        _native_draw_pattern_overlays(image, analysis, width, height, font, candle_centers)

    # Price-linked execution cards/zones are rendered last so they stay legible.
    if analysis.get("native_axis_projection_mode") != "hidden_untrusted_axis":
        _native_draw_trade(image, analysis, width, height, font)

    out = io.BytesIO()
    image.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()



def _reconstructed_dimensions(analysis: dict[str, Any]) -> tuple[int, int]:
    """V7.9 single full-view 16:9 canvas used everywhere in the UI.

    There is no compact renderer.  The same 1920x1080 chart is used in the
    result card, gallery/full-screen view, and downstream save/share flow.
    """
    return 1920, 1080


def _reference_template_kind(analysis: dict[str, Any]) -> str:
    """Return the approved V5 visual template id only; no decision logic here."""
    explicit = str(analysis.get("visual_template_id") or "").strip()
    allowed = {
        "trend_reversal", "multiple_tops", "multiple_bottoms",
        "bullish_smc_reversal", "bearish_smc_reversal", "distribution",
        "head_shoulders", "inverse_head_shoulders", "break_retest_continuation",
    }
    if explicit in allowed:
        return explicit

    scenario = str(analysis.get("reference_scenario_id") or "")
    mapping = {
        "trend_reversal_choch_ifvg": "trend_reversal",
        "bullish_engulfing_orderblock": "bullish_smc_reversal",
        "bearish_fvg_liquidity_double_top": "multiple_tops",
        "inverse_head_shoulders_ob": "inverse_head_shoulders",
        "bearish_bos_ob_retest": "bearish_smc_reversal",
        "distribution_structure_sequence": "distribution",
        "multiple_tops_breakdown": "multiple_tops",
        "bullish_smc_reversal": "bullish_smc_reversal",
        "smart_money_sellside_reversal": "bullish_smc_reversal",
    }
    if scenario in mapping:
        return mapping[scenario]

    name = str(analysis.get("pattern_type") or "")
    if name in {"M", "قمة ثلاثية"}:
        return "multiple_tops"
    if name in {"W", "قاع ثلاثي"}:
        return "multiple_bottoms"
    if name == "رأس وكتفين":
        return "head_shoulders"
    if name == "رأس وكتفين مقلوب":
        return "inverse_head_shoulders"
    if name == "كسر وإعادة اختبار" or any(t in name for t in ("علم", "راية", "مثلث", "وتد", "قناة", "مستطيل")):
        return "break_retest_continuation"
    return ""

def _reference_template_title(analysis: dict[str, Any]) -> str:
    titles = {
        "trend_reversal": "TREND REVERSAL",
        "multiple_tops": "GOOD ENTRY POINTS",
        "multiple_bottoms": "REVERSAL STRUCTURE",
        "bullish_smc_reversal": "SMART MONEY REVERSAL",
        "bearish_smc_reversal": "SMART MONEY REVERSAL",
        "distribution": "DISTRIBUTION",
        "head_shoulders": "HEAD & SHOULDERS",
        "inverse_head_shoulders": "INVERSE HEAD & SHOULDERS",
        "break_retest_continuation": "BREAK • RETEST • CONTINUATION",
    }
    return titles.get(_reference_template_kind(analysis), "MARKET STRUCTURE")

def _reference_primary_title(analysis: dict[str, Any]) -> str:
    """Exactly one visual headline: the deterministic primary pattern wins."""
    name = str(analysis.get("pattern_type") or "")
    if name and name != "لا يوجد":
        return _reference_model_english(name)
    return _reference_template_title(analysis)


def _reference_confirmation_label(analysis: dict[str, Any]) -> str:
    """A compact helper confluence, never a competing second model title."""
    if not bool(analysis.get("reference_scenario_available")):
        return ""
    components = set(str(x) for x in (analysis.get("reference_scenario_draw_components") or []))
    tokens: list[str] = []
    geom = analysis.get("reference_scenario_geometry") if isinstance(analysis.get("reference_scenario_geometry"), dict) else {}
    labels = {str(e.get("label") or "").upper() for e in (geom.get("structure_events") or []) if isinstance(e, dict)}
    if "CHOCH" in labels:
        tokens.append("CHOCH")
    elif "BOS" in labels or "structure" in components:
        tokens.append("BOS")
    if "order_block" in components:
        tokens.append("OB")
    if "fvg" in components:
        tokens.append("FVG")
    if "liquidity" in components:
        tokens.append("LIQUIDITY")
    if "engulfing" in components:
        tokens.append("ENGULFING")
    tokens = tokens[:3]
    return " + ".join(tokens) + (" CONFIRMATION" if tokens else "")


def _reference_setup_status(analysis: dict[str, Any]) -> str:
    """Visual lifecycle label without changing SaleeM execution gates.

    A deterministic pattern can be confirmed while execution is still blocked by
    the existing SaleeM gates.  In that case the renderer must not present an
    actionable CONFIRMED trade.
    """
    plan = _resolve_reference_trade_plan(analysis)
    lifecycle = _reference_trade_lifecycle(analysis, plan) if plan else {"state": "none"}
    state = str(lifecycle.get("state") or "none")
    if state == "target_hit":
        return "TARGET HIT"
    if state == "invalidated":
        return "SETUP INVALIDATED"
    if state == "expired":
        return "SETUP EXPIRED"
    if state == "active":
        return "CONFIRMED"
    if state == "conditional":
        if plan and bool(plan.get("pattern_confirmed")):
            return "PATTERN CONFIRMED · WATCH"
        return "CANDIDATE"

    overlays = [item for item in (analysis.get("pattern_overlays") or []) if isinstance(item, dict)]
    if overlays and str(overlays[0].get("status") or "candidate") == "confirmed":
        return "PATTERN CONFIRMED · WATCH"
    return "WATCH"


def _reconstructed_palette(analysis: dict[str, Any]) -> dict[str, tuple[int, int, int, int]]:
    """Reference-sheet palette: quiet paper, dark ink, template-aware candles."""
    template = _reference_template_kind(analysis)
    bull = (43, 111, 184, 255) if template in {"trend_reversal", "head_shoulders", "inverse_head_shoulders"} else (28, 151, 91, 255)
    return {
        "bg": (241, 242, 240, 255),
        "plot": (250, 250, 247, 255),
        "grid": (105, 112, 118, 20),
        "text": (17, 19, 22, 255),
        "muted": (92, 97, 102, 255),
        "border": (190, 194, 196, 120),
        "bull": bull,
        "bear": (211, 55, 63, 255),
        "pivot": (214, 63, 73, 255),
    }

def _reconstructed_window(analysis: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """Render broad real-M5 context while keeping legacy non-image scenes intact.

    When the analyzer supplies ``render_candles`` (normal V7.6 image flow), the
    screenshot-matched segment is anchored at the right and ~42 real candles are
    shown. Older direct renderer/tests that provide only ``candles`` retain the
    historical 100–120-candle viewport.
    """
    has_render_context = isinstance(analysis.get("render_candles"), list) and len(analysis.get("render_candles") or []) >= 6
    all_candles = _valid_renderer_candles(analysis, prefer_render_window=True)
    if not all_candles:
        return [], 0
    if has_render_context:
        # V7.9: one full visual profile everywhere.  32–40 candles gives the
        # 1920px canvas enough market context while keeping bodies comfortably
        # wide and readable on phones.
        try:
            desired = int(analysis.get("render_visible_candle_count") or 36)
        except (TypeError, ValueError):
            desired = 36
        desired = max(32, min(40, desired))
    else:
        try:
            desired = int(analysis.get("render_visible_candle_count") or min(110, len(all_candles)))
        except (TypeError, ValueError):
            desired = min(110, len(all_candles))
        desired = max(30, min(120, desired))
    desired = min(len(all_candles), desired)
    window = all_candles[-desired:]
    return window, len(all_candles) - len(window)


def _reconstructed_price_range(analysis: dict[str, Any], candles: list[dict[str, Any]]) -> tuple[float, float]:
    """Scale from the *visible* OHLC and only a still-live trade plan.

    Old targets/supports far outside the uploaded chart used to stretch the
    vertical axis and make the result look unrelated to the user's screenshot.
    V7.2 ignores stale plan geometry for scaling and includes only nearby real
    levels. No price is moved; this changes visual room only.
    """
    values: list[float] = []
    for candle in candles:
        values.extend((float(candle["low"]), float(candle["high"])))
    current = _number(analysis.get("current_price"))
    if current is not None:
        values.append(float(current))
    if not values:
        return 0.0, 1.0

    base_lo, base_hi = min(values), max(values)
    base_span = max(0.2, base_hi - base_lo)
    near_lo = base_lo - base_span * 0.35
    near_hi = base_hi + base_span * 0.35

    plan = _resolve_reference_trade_plan(analysis)
    lifecycle = _reference_trade_lifecycle(analysis, plan) if plan else {"state": "none"}
    if plan:
        # The approved reference sheet keeps Entry/Stop/TP context visible even
        # after the old plan completes, but only when those real levels are
        # reasonably near the displayed market. This is visual history, not a
        # reactivation of the trade.
        plan_values = [float(plan[key]) for key in ("entry", "stop", "target")]
        plan_values.extend(
            float(v) for v in (plan.get("targets") or [])
            if _number(v) is not None
        )
        if lifecycle.get("state") in {"active", "conditional"}:
            values.extend(plan_values)
        else:
            history_lo = base_lo - base_span * 1.25
            history_hi = base_hi + base_span * 1.25
            values.extend(v for v in plan_values if history_lo <= v <= history_hi)

    # Nearby real support/resistance may be useful context, but a historical
    # far-away level must not destroy the local viewport scale.
    for key in ("support_levels", "resistance_levels"):
        for item in analysis.get(key) or []:
            if not isinstance(item, dict):
                continue
            value = _number(item.get("price"))
            if value is not None and near_lo <= float(value) <= near_hi:
                values.append(float(value))

    lo, hi = min(values), max(values)
    span = max(0.2, hi - lo)
    lo -= span * 0.08
    hi += span * 0.08
    return lo, hi


def _recon_index_to_actual(index: int, window_size: int, total: int) -> int:
    """Map a detector index to the trailing displayed candle window.

    ``window_size`` is the detector source length while ``total`` is the number
    of candles actually rendered.  The old mapping clipped late pivots to the
    final candle whenever the detector used more history than the renderer.
    This trailing-window mapping keeps every BOS/CHOCH/OB/FVG/top anchor on its
    true candle.
    """
    if total <= 0:
        return 0
    source_n = max(1, int(window_size))
    idx = int(index)
    if source_n >= total:
        mapped = idx - (source_n - total)
    else:
        mapped = idx + (total - source_n)
    return max(0, min(total - 1, mapped))


def _recon_index_to_visible(index: int, window_size: int, total: int) -> int | None:
    """Map an index only when the source candle exists in the visible tail."""
    if total <= 0:
        return None
    source_n = max(1, int(window_size))
    idx = int(index)
    if idx < 0 or idx >= source_n:
        return None
    if source_n >= total:
        start = source_n - total
        if idx < start:
            return None
        return idx - start
    mapped = idx + (total - source_n)
    return mapped if 0 <= mapped < total else None


def _dashed_ellipse(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], color, *, width: int = 2) -> None:
    """Reference-style dotted/dashed ring used around real liquidity pivots."""
    for start in range(0, 360, 30):
        draw.arc(box, start=start, end=min(360, start + 18), fill=color, width=width)


def _recon_arrow(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], color, *, width: int = 3, dashed: bool = False) -> None:
    if len(points) < 2:
        return
    for a, b in zip(points[:-1], points[1:]):
        if dashed:
            _dash_line(draw, a, b, color, width=width, dash=max(8, width * 3), gap=max(6, width * 2))
        else:
            draw.line((*a, *b), fill=color, width=width)
    a, b = points[-2], points[-1]
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    size = max(12, width * 4)
    left = (int(b[0] - size * math.cos(ang - math.pi / 6)), int(b[1] - size * math.sin(ang - math.pi / 6)))
    right = (int(b[0] - size * math.cos(ang + math.pi / 6)), int(b[1] - size * math.sin(ang + math.pi / 6)))
    draw.polygon([b, left, right], fill=color)



def _reference_boxes_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int], pad: int = 4) -> bool:
    return not (a[2] + pad < b[0] or b[2] + pad < a[0] or a[3] + pad < b[1] or b[3] + pad < a[1])


def _draw_reference_event_label_below_candle(
    draw: ImageDraw.ImageDraw,
    *,
    candles: list[dict[str, Any]],
    candle_x: list[int],
    index: int,
    price_y,
    plot: tuple[int, int, int, int],
    text: str,
    font,
    color: tuple[int, int, int, int],
    occupied: list[tuple[int, int, int, int]],
    anchor_y: int | None = None,
) -> tuple[int, int, int, int] | None:
    """V7.6 label rule: event text lives below its real anchor candle.

    Only the text chip may move into a lower collision lane.  The candle, price
    line, sweep/BOS anchor, OB/FVG geometry and all other market-owned pixels
    remain fixed.  A thin leader keeps the moved label visually tied to the
    source candle.
    """
    if index < 0 or index >= len(candles) or index >= len(candle_x):
        return None
    left, top, right, bottom = plot
    x = int(candle_x[index])
    try:
        low_y = int(price_y(float(candles[index]["low"])))
    except (KeyError, TypeError, ValueError):
        return None
    if anchor_y is None:
        anchor_y = low_y

    bbox = draw.textbbox((0, 0), str(text), font=font)
    tw = max(1, bbox[2] - bbox[0])
    th = max(1, bbox[3] - bbox[1])
    half_w = tw // 2 + 7
    half_h = th // 2 + 4

    # Four downward lanes plus modest horizontal nudges.  This resolves dense
    # clusters while respecting the user's rule that labels stay below candles.
    y_offsets = (22, 44, 66, 88)
    x_offsets = (0, -30, 30, -58, 58)
    chosen: tuple[int, int, int, int] | None = None
    for yoff in y_offsets:
        cy = min(bottom - half_h - 5, max(top + half_h + 5, low_y + yoff))
        for xoff in x_offsets:
            cx = min(right - half_w - 6, max(left + half_w + 6, x + xoff))
            box = (cx - half_w, cy - half_h, cx + half_w, cy + half_h)
            if all(not _reference_boxes_overlap(box, other, 5) for other in occupied):
                chosen = box
                break
        if chosen is not None:
            break

    if chosen is None:
        cy = min(bottom - half_h - 5, max(top + half_h + 5, low_y + y_offsets[-1]))
        cx = min(right - half_w - 6, max(left + half_w + 6, x))
        chosen = (cx - half_w, cy - half_h, cx + half_w, cy + half_h)

    cx = (chosen[0] + chosen[2]) // 2
    cy = (chosen[1] + chosen[3]) // 2
    leader_end_y = chosen[1] - 3 if cy >= int(anchor_y) else chosen[3] + 3
    leader = (color[0], color[1], color[2], min(150, color[3] if len(color) > 3 else 150))
    draw.line((x, int(anchor_y), cx, leader_end_y), fill=leader, width=1)
    draw.rounded_rectangle(
        chosen,
        radius=4,
        fill=(250, 250, 247, 225),
        outline=(color[0], color[1], color[2], 115),
        width=1,
    )
    draw.text((cx, cy), str(text), font=font, fill=color, anchor="mm")
    occupied.append(chosen)
    return chosen


def _draw_reference_texture(draw: ImageDraw.ImageDraw, plot: tuple[int, int, int, int]) -> None:
    """Very faint deterministic circuit/topographic hints like an educational sheet."""
    left, top, right, bottom = plot
    c = (125, 132, 137, 16)
    step = max(90, (right - left) // 12)
    for x in range(left + 22, right - 22, step):
        y0 = top + 28 + ((x // step) % 4) * 22
        draw.line((x, y0, x, min(bottom - 26, y0 + 52)), fill=c, width=1)
        draw.line((x, y0, min(right - 20, x + 34), y0), fill=c, width=1)
        draw.ellipse((min(right - 23, x + 31), y0 - 2, min(right - 19, x + 35), y0 + 2), outline=c, width=1)
    # Corner registration marks only; no heavy frame.
    cc = (88, 126, 145, 35)
    length = 24
    for x, y, sx, sy in ((left, top, 1, 1), (right, top, -1, 1), (left, bottom, 1, -1), (right, bottom, -1, -1)):
        draw.line((x, y, x + sx * length, y), fill=cc, width=1)
        draw.line((x, y, x, y + sy * length), fill=cc, width=1)

def _reference_model_english(name: str) -> str:
    mapping = {
        "M": "DOUBLE TOP / M",
        "W": "DOUBLE BOTTOM / W",
        "قمة ثلاثية": "TRIPLE TOP",
        "قاع ثلاثي": "TRIPLE BOTTOM",
        "رأس وكتفين": "HEAD & SHOULDERS",
        "رأس وكتفين مقلوب": "INVERSE HEAD & SHOULDERS",
        "مثلث صاعد": "ASCENDING TRIANGLE",
        "مثلث هابط": "DESCENDING TRIANGLE",
        "مثلث متماثل": "SYMMETRICAL TRIANGLE",
        "وتد صاعد": "RISING WEDGE",
        "وتد هابط": "FALLING WEDGE",
        "علم صاعد": "BULL FLAG",
        "علم هابط": "BEAR FLAG",
        "راية صاعدة": "BULL PENNANT",
        "راية هابطة": "BEAR PENNANT",
    }
    return mapping.get(name, name if name and not any("\u0600" <= ch <= "\u06ff" for ch in name) else "VERIFIED PATTERN")


def _draw_reconstructed_pattern(
    draw: ImageDraw.ImageDraw,
    analysis: dict[str, Any],
    candles: list[dict[str, Any]],
    candle_x: list[int],
    price_y,
    palette: dict[str, tuple[int, int, int, int]],
    font,
    plot: tuple[int, int, int, int],
    label_occupied: list[tuple[int, int, int, int]],
) -> None:
    """Primary pattern as a bold educational sketch over real M5 pivots."""
    overlays = [item for item in (analysis.get("pattern_overlays") or []) if isinstance(item, dict)]
    if not overlays:
        return
    overlay = overlays[0]
    geom = overlay.get("geometry") if isinstance(overlay.get("geometry"), dict) else {}
    try:
        window_size = int(geom.get("window_size") or len(candles))
    except (TypeError, ValueError):
        window_size = len(candles)
    confirmed = str(overlay.get("status") or "candidate") == "confirmed"
    overlay_name = str(overlay.get("name") or analysis.get("pattern_type") or "")
    reference_clean_pivots = bool(analysis.get("reference_scenario_available")) and overlay_name in {"M", "W", "قمة ثلاثية", "قاع ثلاثي"}
    bias = str(overlay.get("bias") or analysis.get("pattern_bias") or "محايد")
    pivot = (213, 56, 70, 255) if bias == "هابط" else (36, 158, 96, 255) if bias == "صاعد" else (90, 98, 106, 255)
    line_color = (31, 35, 40, 235)
    trigger_color = (25, 118, 200, 235)
    label_color = (28, 32, 37, 250)

    def mapped(point: Any) -> tuple[int, int] | None:
        if not (isinstance(point, list) and len(point) >= 2):
            return None
        try:
            idx = _recon_index_to_visible(int(point[0]), window_size, len(candles))
            if idx is None:
                return None
            return candle_x[idx], price_y(float(point[1]))
        except (TypeError, ValueError, IndexError):
            return None

    if not reference_clean_pivots:
        for item in geom.get("lines") or []:
            if not isinstance(item, dict):
                continue
            a, b = mapped(item.get("p1")), mapped(item.get("p2"))
            if a is None or b is None:
                continue
            role = str(item.get("role") or "")
            c = trigger_color if role in {"neckline", "trigger"} else line_color
            if confirmed:
                draw.line((*a, *b), fill=c, width=2)
            else:
                _dash_line(draw, a, b, c, width=2, dash=10, gap=7)

        path = [p for item in (geom.get("path") or []) if (p := mapped(item)) is not None]
        if len(path) >= 2:
            if confirmed:
                draw.line(path, fill=line_color, width=2, joint="curve")
            else:
                for a, b in zip(path[:-1], path[1:]):
                    _dash_line(draw, a, b, line_color, width=2, dash=10, gap=7)

    anchors: list[tuple[int, int, str, int]] = []
    for item in geom.get("anchors") or []:
        if not isinstance(item, dict):
            continue
        try:
            idx = _recon_index_to_visible(int(item.get("index")), window_size, len(candles))
            if idx is None:
                continue
            x, y = candle_x[idx], price_y(float(item.get("price")))
        except (TypeError, ValueError, IndexError):
            continue
        role = str(item.get("role") or "pivot")
        anchors.append((x, y, role, idx))
        if reference_clean_pivots:
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=pivot)
        else:
            draw.ellipse((x - 16, y - 16, x + 16, y + 16), fill=(pivot[0], pivot[1], pivot[2], 30))
            draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=(250, 250, 250, 235), outline=(pivot[0], pivot[1], pivot[2], 230), width=3)
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=pivot)

    name = overlay_name
    pivots = [item for item in anchors if item[2] not in {"neck", "lower", "upper", "pole", "retest"}]
    if name in {"M", "قمة ثلاثية"}:
        for i, (_x, y, _role, idx) in enumerate(pivots[:3], 1):
            ordinal = "1st" if i == 1 else "2nd" if i == 2 else "3rd"
            _draw_reference_event_label_below_candle(
                draw, candles=candles, candle_x=candle_x, index=idx, price_y=price_y,
                plot=plot, text=f"{ordinal} TOP", font=font, color=label_color,
                occupied=label_occupied, anchor_y=y,
            )
    elif name in {"W", "قاع ثلاثي"}:
        for i, (_x, y, _role, idx) in enumerate(pivots[:3], 1):
            ordinal = "1st" if i == 1 else "2nd" if i == 2 else "3rd"
            _draw_reference_event_label_below_candle(
                draw, candles=candles, candle_x=candle_x, index=idx, price_y=price_y,
                plot=plot, text=f"{ordinal} BOTTOM", font=font, color=label_color,
                occupied=label_occupied, anchor_y=y,
            )
    elif "رأس وكتفين" in name:
        role_names = {"shoulder": "SHOULDER", "head": "HEAD", "neck": "NECKLINE"}
        for _x, y, role, idx in anchors:
            if role in role_names:
                _draw_reference_event_label_below_candle(
                    draw, candles=candles, candle_x=candle_x, index=idx, price_y=price_y,
                    plot=plot, text=role_names[role], font=font, color=label_color,
                    occupied=label_occupied, anchor_y=y,
                )

def _draw_reconstructed_reference_zones(
    draw: ImageDraw.ImageDraw,
    analysis: dict[str, Any],
    candles: list[dict[str, Any]],
    candle_x: list[int],
    price_y,
    plot: tuple[int, int, int, int],
    font,
    candle_right: int,
) -> None:
    """V7.9 transparent M5 support/resistance zones with real strength.

    Only the nearest support and resistance are shown.  A verified liquidity
    pool may widen the matching side, but the opposite side remains visible so
    the user can immediately see where a projected move may react.
    """
    if not analysis.get("pattern_overlays") and not analysis.get("reference_scenario_available"):
        return
    left, top, right, bottom = plot
    current = _number(analysis.get("current_price"))
    atr = median([max(0.01, float(c["high"]) - float(c["low"])) for c in candles[-20:]]) if candles else 0.5
    half = max(atr * 0.18, 0.06)
    bias = str(analysis.get("reference_scenario_bias") or analysis.get("pattern_bias") or "محايد")
    scenario_geom = analysis.get("reference_scenario_geometry") if isinstance(analysis.get("reference_scenario_geometry"), dict) else {}

    def nearest_level(key: str) -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []
        for raw in analysis.get(key) or []:
            if not isinstance(raw, dict):
                continue
            value = _number(raw.get("price"))
            if value is None:
                continue
            if current is not None:
                if key == "support_levels" and float(value) >= float(current):
                    continue
                if key == "resistance_levels" and float(value) <= float(current):
                    continue
            candidates.append({
                "price": float(value),
                "strength": max(0, min(100, int(raw.get("strength") or 0))),
            })
        if not candidates:
            return None
        if current is None:
            return candidates[0]
        return min(candidates, key=lambda item: abs(float(item["price"]) - float(current)))

    support_item = nearest_level("support_levels")
    resistance_item = nearest_level("resistance_levels")
    drawn_side: set[str] = set()

    # Prefer a verified equal-high/equal-low pool as the width for that side,
    # while still showing the other side as a normal M5 zone.
    cluster_key = "equal_highs" if bias == "هابط" else "equal_lows" if bias == "صاعد" else ""
    cluster = scenario_geom.get(cluster_key) if cluster_key and isinstance(scenario_geom.get(cluster_key), dict) else None
    if cluster and candle_x:
        level = _number(cluster.get("price"))
        tolerance = _number(cluster.get("tolerance"))
        points = [p for p in (cluster.get("points") or []) if isinstance(p, dict)]
        if level is not None and len(points) >= 2:
            try:
                window_size = int(scenario_geom.get("window_size") or len(candles))
            except (TypeError, ValueError):
                window_size = len(candles)
            mapped: list[int] = []
            for point in points:
                try:
                    mapped.append(_recon_index_to_actual(int(point.get("index")), window_size, len(candles)))
                except (TypeError, ValueError):
                    pass
            zone_half = min(max(half, float(tolerance or 0.0) * 0.70), max(half, atr * 0.42))
            y1, y2 = price_y(float(level) + zone_half), price_y(float(level) - zone_half)
            yy1, yy2 = max(top, min(y1, y2)), min(bottom, max(y1, y2))
            if mapped and yy2 > yy1:
                x1 = max(left + 10, candle_x[min(mapped)] - 200)
                x2 = min(right - 250, max(candle_right + 60, candle_x[max(mapped)] + 120))
                if bias == "هابط":
                    strength = int((resistance_item or {}).get("strength") or 0)
                    fill, outline, base = (224, 66, 78, 26), (196, 67, 76, 165), "RESISTANCE"
                    drawn_side.add("resistance")
                else:
                    strength = int((support_item or {}).get("strength") or 0)
                    fill, outline, base = (50, 170, 91, 24), (49, 145, 82, 165), "SUPPORT"
                    drawn_side.add("support")
                label = f"{base} {strength}%" if strength else base
                draw.rectangle((x1, yy1, x2, yy2), fill=fill, outline=outline, width=1)
                draw.text((x1 + 12, (yy1 + yy2) // 2), label, font=font, fill=outline, anchor="lm")

    x1 = candle_x[max(0, len(candle_x) - min(40, len(candle_x)))] if candle_x else left + 10
    x2 = min(right - 250, candle_right + 95)
    if x2 <= x1 + 80:
        x1 = max(left + 10, candle_right - 260)

    specs = (
        ("resistance", resistance_item, "RESISTANCE", (224, 66, 78, 22), (196, 67, 76, 155)),
        ("support", support_item, "SUPPORT", (50, 170, 91, 20), (49, 145, 82, 155)),
    )
    for side_name, item, label, fill, outline in specs:
        if not item or side_name in drawn_side:
            continue
        value = float(item["price"])
        strength = int(item.get("strength") or 0)
        y1, y2 = price_y(value + half), price_y(value - half)
        yy1, yy2 = max(top, min(y1, y2)), min(bottom, max(y1, y2))
        if yy2 <= yy1:
            continue
        label_text = f"{label} {strength}%" if strength else label
        draw.rectangle((x1, yy1, x2, yy2), fill=fill, outline=outline, width=1)
        draw.text((x1 + 10, (yy1 + yy2) // 2), label_text, font=font, fill=outline, anchor="lm")


def _draw_reconstructed_reference_scenario(
    image: Image.Image,
    analysis: dict[str, Any],
    candles: list[dict[str, Any]],
    candle_x: list[int],
    price_y,
    plot: tuple[int, int, int, int],
    palette: dict[str, tuple[int, int, int, int]],
    font,
    candle_right: int,
) -> None:
    """Draw the approved TradingView-like SMC teaching layer on real M5 OHLC.

    Every line/box/circle is anchored to deterministic candle geometry supplied
    by ``reference_scenario_engine``.  The renderer never invents a price.
    """
    draw = ImageDraw.Draw(image)
    label_occupied: list[tuple[int, int, int, int]] = []
    if analysis.get("pattern_overlays"):
        _draw_reconstructed_pattern(
            draw, analysis, candles, candle_x, price_y, palette, font, plot, label_occupied
        )
    if not bool(analysis.get("reference_scenario_available")) or not candle_x:
        return

    components = set(str(x) for x in (analysis.get("reference_scenario_draw_components") or []))
    geom = analysis.get("reference_scenario_geometry") if isinstance(analysis.get("reference_scenario_geometry"), dict) else {}
    try:
        window_size = int(geom.get("window_size") or len(candles))
    except (TypeError, ValueError):
        window_size = len(candles)
    bias = str(analysis.get("reference_scenario_bias") or "محايد")
    left, top, right, bottom = plot
    dark = (31, 36, 42, 238)
    green = (35, 145, 83, 225)
    purple = (105, 63, 142, 230)
    red = (198, 66, 76, 225)
    blue = (55, 117, 171, 230)
    orange = (178, 96, 44, 230)

    def map_index(raw: Any) -> int | None:
        try:
            return _recon_index_to_visible(int(raw), window_size, len(candles))
        except (TypeError, ValueError):
            return None

    # Previous trend line: rising swing lows before a bearish reversal, or
    # falling swing highs before a bullish reversal.
    trend_key = "trend_line_bull" if bias == "هابط" else "trend_line_bear" if bias == "صاعد" else ""
    trend = geom.get(trend_key) if trend_key and isinstance(geom.get(trend_key), dict) else None
    if trend:
        p1, p2 = trend.get("p1"), trend.get("p2")
        if isinstance(p1, list) and isinstance(p2, list) and len(p1) >= 2 and len(p2) >= 2:
            i1, i2 = map_index(p1[0]), map_index(p2[0])
            if i1 is not None and i2 is not None:
                a = (candle_x[i1], price_y(float(p1[1])))
                b = (candle_x[i2], price_y(float(p2[1])))
                # Extend only to the next real part of the chart; do not project price.
                dx = max(1, b[0] - a[0])
                slope = (b[1] - a[1]) / dx
                end_x = min(candle_right, b[0] + min(180, max(60, dx)))
                end_y = int(round(b[1] + slope * (end_x - b[0])))
                c = green if bias == "هابط" else red
                _dash_line(draw, a, (end_x, end_y), c, width=2, dash=9, gap=5)
                tx = (a[0] + end_x) // 2
                ty = int(round(a[1] + (end_y - a[1]) * 0.5))
                draw.text((tx, ty - 7), "TREND LINE", font=font, fill=c, anchor="ms")

    # Equal highs/lows: dotted circles and ordinal labels.  If the primary
    # classical pattern already owns its pivots, do not print duplicate text.
    cluster_key = "equal_highs" if bias == "هابط" else "equal_lows" if bias == "صاعد" else ""
    cluster = geom.get(cluster_key) if cluster_key and isinstance(geom.get(cluster_key), dict) else None
    pattern_name = str(analysis.get("pattern_type") or "")
    primary_owns_labels = pattern_name in {"M", "W", "قمة ثلاثية", "قاع ثلاثي"}
    if cluster:
        points = [p for p in (cluster.get("points") or []) if isinstance(p, dict)]
        for n, point in enumerate(points[:3], 1):
            idx = map_index(point.get("index"))
            price = _number(point.get("price"))
            if idx is None or price is None:
                continue
            x, y = candle_x[idx], price_y(float(price))
            ring = red if bias == "هابط" else green
            _dashed_ellipse(draw, (x - 20, y - 22, x + 20, y + 22), ring, width=2)
            if not primary_owns_labels:
                ordinal = "1st" if n == 1 else "2nd" if n == 2 else "3rd"
                suffix = "TOP" if bias == "هابط" else "BOTTOM"
                _draw_reference_event_label_below_candle(
                    draw, candles=candles, candle_x=candle_x, index=idx, price_y=price_y,
                    plot=plot, text=f"{ordinal} {suffix}", font=font, color=dark,
                    occupied=label_occupied, anchor_y=y,
                )

    # Market structure. BOS is green like the reference; the first opposing
    # structural change is highlighted as MSS / CHOCH in purple.
    if "structure" in components:
        for event in (geom.get("structure_events") or [])[-5:]:
            if not isinstance(event, dict):
                continue
            swing = map_index(event.get("swing_index")); brk = map_index(event.get("break_index"))
            price = _number(event.get("price"))
            if swing is None or brk is None or price is None:
                continue
            y = price_y(float(price))
            x1, x2 = sorted((candle_x[swing], candle_x[brk]))
            raw_label = str(event.get("label") or "BOS").upper()
            if raw_label == "CHOCH":
                color, label = purple, "MSS / CHOCH"
            else:
                color, label = green, "BOS"
            _dash_line(draw, (x1, y), (x2, y), color, width=2, dash=9, gap=5)
            _draw_reference_event_label_below_candle(
                draw, candles=candles, candle_x=candle_x, index=brk, price_y=price_y,
                plot=plot, text=label, font=font, color=color,
                occupied=label_occupied, anchor_y=y,
            )

    # Order block and FVG use the direction-specific zone chosen by the engine.
    if "order_block" in components:
        block = geom.get("order_block") if isinstance(geom.get("order_block"), dict) else None
        if block:
            idx = map_index(block.get("index"))
            hi = _number(block.get("zone_high")) or _number(block.get("high"))
            lo = _number(block.get("zone_low")) or _number(block.get("low"))
            if idx is not None and hi is not None and lo is not None:
                y1, y2 = price_y(float(hi)), price_y(float(lo))
                x1 = max(left, candle_x[idx] - 8)
                zone_width = max(105, min(220, int((right - left) * 0.16)))
                x2 = min(right - 26, x1 + zone_width)
                yy1, yy2 = min(y1, y2), max(y1, y2)
                fill = (231, 174, 116, 42) if bias == "هابط" else (99, 176, 116, 36)
                outline = orange if bias == "هابط" else green
                draw.rectangle((x1, yy1, x2, yy2), fill=fill, outline=outline, width=1)
                draw.text((x1 + 12, (yy1 + yy2) // 2), "ORDER BLOCK", font=font, fill=orange if bias == "هابط" else green, anchor="lm")

    if "fvg" in components:
        gap = geom.get("fvg") if isinstance(geom.get("fvg"), dict) else None
        if gap:
            idx = map_index(gap.get("index"))
            hi, lo = _number(gap.get("high")), _number(gap.get("low"))
            if idx is not None and hi is not None and lo is not None:
                y1, y2 = price_y(float(hi)), price_y(float(lo))
                x1 = max(left, candle_x[max(0, idx - 1)] - 4)
                zone_width = max(100, min(205, int((right - left) * 0.15)))
                x2 = min(right - 26, x1 + zone_width)
                yy1, yy2 = min(y1, y2), max(y1, y2)
                draw.rectangle((x1, yy1, x2, yy2), fill=(114, 173, 219, 34), outline=blue, width=1)
                draw.text((x1 + 12, (yy1 + yy2) // 2), "FVG", font=font, fill=blue, anchor="lm")

    if "liquidity" in components:
        sweep = geom.get("liquidity_sweep") if isinstance(geom.get("liquidity_sweep"), dict) else None
        if sweep:
            idx = map_index(sweep.get("index"))
            anchor_idx = map_index(sweep.get("anchor_index"))
            level = _number(sweep.get("price"))
            if idx is not None and level is not None:
                x2 = candle_x[idx]
                # Start at the exact real pivot/cluster candle that was swept.
                # Only the text may move for readability; the price line and
                # its anchors never move.
                x1 = candle_x[anchor_idx] if anchor_idx is not None else max(left, x2 - 210)
                if anchor_idx is None and cluster:
                    pts = [p for p in (cluster.get("points") or []) if isinstance(p, dict)]
                    mapped = [map_index(p.get("index")) for p in pts]
                    mapped = [m for m in mapped if m is not None]
                    if mapped:
                        x1 = candle_x[max(mapped)]
                y = price_y(float(level))
                sweep_color = red if str(sweep.get("side")) == "high" else green
                if x2 > x1 + 5:
                    _dash_line(draw, (x1, y), (x2, y), sweep_color, width=2, dash=9, gap=5)
                    _draw_reference_event_label_below_candle(
                        draw, candles=candles, candle_x=candle_x, index=idx, price_y=price_y,
                        plot=plot, text="LIQUIDITY SWEEP", font=font, color=dark,
                        occupied=label_occupied, anchor_y=y,
                    )
                # Small directional marker on the actual sweep candle.
                wick_price = float(candles[idx]["high"] if str(sweep.get("side")) == "high" else candles[idx]["low"])
                wy = price_y(wick_price)
                tip_y = min(bottom - 8, wy + 30) if str(sweep.get("side")) == "high" else max(top + 8, wy - 30)
                _recon_arrow(draw, [(x2, wy - 8 if tip_y > wy else wy + 8), (x2, tip_y)], sweep_color, width=2, dashed=False)

    if "engulfing" in components:
        engulf = geom.get("engulfing") if isinstance(geom.get("engulfing"), dict) else None
        if engulf:
            idx = map_index(engulf.get("index"))
            if idx is not None and 0 <= idx < len(candles):
                c = candles[idx]
                x = candle_x[idx]
                y1, y2 = price_y(float(c["high"])), price_y(float(c["low"]))
                color = green if str(engulf.get("side")) == "bull" else red
                draw.rounded_rectangle((x - 9, min(y1, y2) - 3, x + 9, max(y1, y2) + 3), radius=3, outline=color, width=2)


def _resolve_reference_trade_plan(analysis: dict[str, Any]) -> dict[str, Any] | None:
    """Return real deterministic plan geometry, never a new trade decision.

    ``confirmed`` means the existing SaleeM execution gate is confirmed.
    ``pattern_confirmed`` records deterministic pattern confirmation separately
    so the visual layer can explain a confirmed pattern that is still WATCH.
    """
    action = analysis.get("action_summary") if isinstance(analysis.get("action_summary"), dict) else {}
    side = str(action.get("primary_side") or "wait")
    confirmed = bool(action.get("is_confirmed")) and side in {"buy", "sell"}

    def execution_plan(*, is_confirmed: bool) -> dict[str, Any] | None:
        entry = _number(analysis.get("entry"))
        stop = _number(analysis.get("stop_loss"))
        targets = [
            float(v) for key in ("target_1", "target_2", "target_3")
            if (v := _number(analysis.get(key))) is not None
        ]
        if side not in {"buy", "sell"} or entry is None or stop is None or not targets:
            return None
        directional = [
            value for value in targets
            if (side == "buy" and float(stop) < float(entry) < value)
            or (side == "sell" and float(stop) > float(entry) > value)
        ]
        if not directional:
            return None
        # Keep the analyzer's TP order.  It is already deterministic and is
        # the only source of execution targets; the renderer never fabricates
        # a missing TP merely to fill the chart.
        directional = directional[:3]
        return {
            "side": side,
            "entry": float(entry),
            "stop": float(stop),
            "target": float(directional[0]),
            "targets": directional,
            "confirmed": bool(is_confirmed),
            "pattern_confirmed": bool(is_confirmed),
            "source": "execution" if is_confirmed else "conditional_execution",
        }

    if confirmed:
        plan = execution_plan(is_confirmed=True)
        if plan is not None:
            return plan

    # A non-confirmed plan may be illustrated only when SaleeM itself is in
    # the conditional state and a fresh M5 trigger is still pending.  WATCH or
    # expired states must not resurrect an old Entry/TP plan.
    if (
        str(analysis.get("draw_mode") or "watch") == "conditional"
        and not bool(analysis.get("scenario_expired"))
        and side in {"buy", "sell"}
    ):
        plan = execution_plan(is_confirmed=False)
        if plan is not None:
            return plan

    overlays = [item for item in (analysis.get("pattern_overlays") or []) if isinstance(item, dict)]
    if overlays:
        overlay = overlays[0]
        geom = overlay.get("geometry") if isinstance(overlay.get("geometry"), dict) else {}
        entry = _number(geom.get("trigger"))
        stop = _number(geom.get("stop"))
        target = _number(geom.get("target"))
        bias = str(overlay.get("bias") or "محايد")
        side = "buy" if bias == "صاعد" else "sell" if bias == "هابط" else "wait"
        if side != "wait" and entry is not None and stop is not None and target is not None:
            pattern_targets: list[float] = [float(target)]
            # Reuse only analyzer-owned TP prices that are directionally valid
            # for this same pattern geometry.  This exposes TP2/TP3 when real
            # deterministic targets already exist; the renderer never creates
            # synthetic filler levels.
            for key in ("target_1", "target_2", "target_3"):
                value = _number(analysis.get(key))
                if value is None:
                    continue
                value_f = float(value)
                valid = (side == "buy" and float(stop) < float(entry) < value_f) or (side == "sell" and float(stop) > float(entry) > value_f)
                if not valid:
                    continue
                if all(abs(value_f - existing) >= 0.05 for existing in pattern_targets):
                    pattern_targets.append(value_f)
            pattern_targets.sort(reverse=(side == "sell"))
            pattern_targets = pattern_targets[:3]
            return {
                "side": side, "entry": float(entry), "stop": float(stop), "target": float(pattern_targets[0]),
                "targets": pattern_targets,
                "confirmed": False,
                "pattern_confirmed": str(overlay.get("status") or "candidate") == "confirmed",
                "source": "pattern",
            }
    return None


def _reference_trade_lifecycle(
    analysis: dict[str, Any],
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve display lifecycle from the effective current price and plan.

    The effective current price is the trusted chart label when locked, else
    market live/closed price. This prevents stale plans from being drawn as new entries.  It never changes
    BUY/SELL/Watch, pattern status, trigger, stop, or target.
    """
    plan = plan or _resolve_reference_trade_plan(analysis)
    if not plan:
        return {"state": "none", "current": None}

    side = str(plan.get("side") or "wait")
    entry = float(plan["entry"]); stop = float(plan["stop"])
    targets = [
        float(v) for v in (plan.get("targets") or [plan.get("target")])
        if _number(v) is not None
    ]
    if not targets:
        return {"state": "invalid_geometry", "current": None, "targets_reached": 0}
    target = float(targets[0])
    final_target = float(targets[-1])
    valid = (side == "buy" and stop < entry < target) or (side == "sell" and stop > entry > target)
    if not valid:
        return {"state": "invalid_geometry", "current": None, "targets_reached": 0}

    current = _number(analysis.get("current_price"))
    if current is None:
        current = _number(analysis.get("market_last_close"))
    current_f = float(current) if current is not None else None
    if current_f is None:
        return {"state": "active" if bool(plan.get("confirmed")) else "conditional", "current": None, "targets_reached": 0}

    tol = max(0.02, abs(entry) * 1e-6)
    confirmed = bool(plan.get("confirmed"))
    if side == "buy":
        reached = [value for value in targets if current_f >= value - tol]
        final_reached = current_f >= final_target - tol
        invalidated = current_f <= stop + tol
    else:
        reached = [value for value in targets if current_f <= value + tol]
        final_reached = current_f <= final_target + tol
        invalidated = current_f >= stop - tol

    if invalidated:
        state = "invalidated"
    elif final_reached:
        # An execution plan remains alive through TP1/TP2 and completes only at
        # its final available target (normally TP3).  A conditional pattern
        # that has already travelled through its objective is stale.
        state = "target_hit" if confirmed else "expired"
    else:
        state = "active" if confirmed else "conditional"
    return {
        "state": state,
        "current": current_f,
        "targets_reached": len(reached),
        "target_count": len(targets),
        "last_reached_target": reached[-1] if reached else None,
        "final_target": final_target,
    }



def _reference_dual_preview_needed(analysis: dict[str, Any]) -> bool:
    """V7.6: WATCH / RE-EVALUATE always keeps both conditional sides visible.

    These are not two active trades.  They are two mutually exclusive M5
    conditions (buy breakout vs sell rejection/break).  Once SaleeM confirms a
    real execution side, the renderer returns to one active Entry-origin path.
    """
    if str(analysis.get("draw_mode") or "watch") != "watch":
        return False
    action = analysis.get("action_summary") if isinstance(analysis.get("action_summary"), dict) else {}
    if bool(action.get("is_confirmed")):
        return False
    buy = analysis.get("buy_scenario_details") if isinstance(analysis.get("buy_scenario_details"), dict) else {}
    sell = analysis.get("sell_scenario_details") if isinstance(analysis.get("sell_scenario_details"), dict) else {}
    if _number(buy.get("trigger_price")) is None or _number(sell.get("trigger_price")) is None:
        return False
    if _number(buy.get("display_target")) is None or _number(sell.get("display_target")) is None:
        return False
    return True


def _draw_reference_projected_candles(
    draw: ImageDraw.ImageDraw,
    *,
    entry: float,
    targets: list[float],
    side: str,
    price_y,
    x1: int,
    x2: int,
    confirmed: bool,
) -> None:
    """Draw translucent scenario candles for Break -> Retest -> Continuation.

    These are explicitly projected candles, not market OHLC.  Their prices are
    deterministic interpolation between the real Entry and real TP levels, so
    they explain the route without inventing an extra labelled market level.
    """
    if not targets or x2 <= x1 + 34:
        return
    first_target = float(targets[0])
    move = first_target - float(entry)
    if abs(move) < 1e-9:
        return

    # Deliberate bend: first push through Entry, retest toward Entry, then
    # continuation through every real TP supplied by the analyzer.
    break_price = float(entry) + move * 0.46
    retest_price = float(entry) + move * 0.16
    projected_prices: list[float] = [break_price, retest_price]
    for target in targets[:3]:
        target = float(target)
        previous = projected_prices[-1]
        projected_prices.extend([previous + (target - previous) * 0.55, target])

    count = len(projected_prices)
    slot = (x2 - x1) / max(1, count)
    body_w = max(5, min(9, int(slot * 0.46)))
    main = (40, 157, 91) if side == "buy" else (202, 63, 72)
    opposite = (202, 63, 72) if side == "buy" else (40, 157, 91)
    alpha = 150 if confirmed else 92
    previous = float(entry)
    span = max(abs(float(targets[-1]) - float(entry)), abs(move), 0.01)

    for i, close in enumerate(projected_prices):
        x = int(round(x1 + slot * (i + 0.5)))
        open_price = previous
        # The explicit retest candle (index 1) uses the opposite body color.
        rgb = opposite if i == 1 else main
        wick = max(abs(close - open_price) * 0.18, span * 0.012)
        high = max(open_price, close) + wick
        low = min(open_price, close) - wick
        yo, yc = price_y(open_price), price_y(close)
        yh, yl = price_y(high), price_y(low)
        draw.line((x, yh, x, yl), fill=(*rgb, min(210, alpha + 35)), width=1)
        top, bottom = sorted((yo, yc))
        if bottom - top < 3:
            bottom = top + 3
        draw.rectangle(
            (x - body_w // 2, top, x + body_w // 2, bottom),
            fill=(*rgb, alpha),
            outline=(*rgb, min(225, alpha + 55)),
            width=1,
        )
        previous = float(close)


def _reference_reaction_level(
    analysis: dict[str, Any],
    *,
    side: str,
    entry: float,
    target: float,
) -> dict[str, Any] | None:
    """Nearest REAL S/R station between Entry and the projected target."""
    key = "resistance_levels" if side == "buy" else "support_levels"
    candidates: list[dict[str, Any]] = []
    for raw in analysis.get(key) or []:
        if not isinstance(raw, dict):
            continue
        price = _number(raw.get("price"))
        if price is None:
            continue
        value = float(price)
        inside = entry < value <= target if side == "buy" else target <= value < entry
        if not inside:
            continue
        candidates.append({
            "price": value,
            "strength": max(0, min(100, int(raw.get("strength") or 0))),
        })
    if not candidates:
        return None
    return min(candidates, key=lambda item: abs(float(item["price"]) - entry))


def _draw_reaction_tag(draw: ImageDraw.ImageDraw, x: int, y: int, *, side: str, strength: int, font) -> None:
    if side == "buy":
        text = f"R {strength}% · PULLBACK" if strength else "R · PULLBACK"
        color = (196, 67, 76, 230)
    else:
        text = f"S {strength}% · BOUNCE" if strength else "S · BOUNCE"
        color = (49, 145, 82, 230)
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    bx1, by1 = x - w // 2 - 8, y - h - 24
    bx2, by2 = x + w // 2 + 8, y - 8
    draw.rounded_rectangle((bx1, by1, bx2, by2), radius=5, fill=(255, 255, 255, 228), outline=color, width=1)
    draw.text((x, (by1 + by2)//2), text, font=font, fill=color, anchor="mm")


def _draw_reference_dual_watch_paths(
    draw: ImageDraw.ImageDraw,
    analysis: dict[str, Any],
    price_y,
    plot: tuple[int, int, int, int],
    candle_right: int,
    font,
    *,
    origin_entry: float | None = None,
) -> bool:
    """V7.9 WATCH preview: green bullish path, red bearish path.

    Both start from their real M5 trigger.  The stronger path is vivid while
    the alternative is lighter.  If a real resistance/support lies between the
    trigger and target, the path explicitly touches it and shows the expected
    pullback/bounce before continuation.
    """
    if not _reference_dual_preview_needed(analysis):
        return False
    left, top, right, bottom = plot
    lane_left = max(candle_right + 22, left + int((right - left) * 0.80))
    lane_right = right - 250
    if lane_right <= lane_left + 76:
        lane_left = max(candle_right + 12, lane_right - 112)
    if lane_right <= lane_left + 56:
        return False

    buy = analysis.get("buy_scenario_details") if isinstance(analysis.get("buy_scenario_details"), dict) else {}
    sell = analysis.get("sell_scenario_details") if isinstance(analysis.get("sell_scenario_details"), dict) else {}
    buy_score = max(0, min(100, int(buy.get("score") or analysis.get("buy_probability") or 0)))
    sell_score = max(0, min(100, int(sell.get("score") or analysis.get("sell_probability") or 0)))
    strongest = "buy" if buy_score >= sell_score else "sell"

    specs = [
        ("buy", buy, buy_score, (30, 167, 88)),
        ("sell", sell, sell_score, (216, 67, 76)),
    ]
    drew = False
    for side, scenario, score, rgb in specs:
        entry = _number(scenario.get("trigger_price"))
        target = _number(scenario.get("display_target"))
        if entry is None or target is None:
            continue
        entry, target = float(entry), float(target)
        if side == "buy" and target <= entry:
            continue
        if side == "sell" and target >= entry:
            continue

        ey = max(top + 16, min(bottom - 16, price_y(entry)))
        ty_raw = price_y(target)
        ty = max(top + 24, min(bottom - 24, ty_raw))
        max_vertical = 118
        if abs(ty - ey) > max_vertical:
            ty = ey + (max_vertical if ty > ey else -max_vertical)
            ty = max(top + 24, min(bottom - 24, ty))

        stronger = side == strongest
        alpha = 235 if stronger else 105
        width = 4 if stronger else 2
        color = (rgb[0], rgb[1], rgb[2], alpha)
        span_x = lane_right - lane_left
        reaction = _reference_reaction_level(analysis, side=side, entry=entry, target=target)
        if reaction:
            rx = lane_left + max(30, int(span_x * 0.43))
            px = lane_left + max(56, int(span_x * 0.68))
            ry = max(top + 20, min(bottom - 20, price_y(float(reaction["price"]))))
            # Visual pullback/bounce bends back toward Entry without inventing a labelled price.
            py = int(round(ey + (ry - ey) * 0.40))
            points = [(lane_left, ey), (rx, ry), (px, py), (lane_right, ty)]
            if stronger:
                _draw_reaction_tag(draw, rx, ry, side=side, strength=int(reaction.get("strength") or 0), font=font)
        else:
            break_x = lane_left + max(26, span_x // 3)
            retest_x = lane_left + max(50, span_x * 2 // 3)
            break_y = int(round(ey + (ty - ey) * 0.44))
            retest_y = int(round(ey + (ty - ey) * 0.10))
            points = [(lane_left, ey), (break_x, break_y), (retest_x, retest_y), (lane_right, ty)]

        draw.ellipse((lane_left - 4, ey - 4, lane_left + 4, ey + 4), fill=color)
        _recon_arrow(draw, points, color, width=width, dashed=True)
        drew = True
    return drew


def _draw_reference_trade_plan(
    draw: ImageDraw.ImageDraw,
    analysis: dict[str, Any],
    price_y,
    plot: tuple[int, int, int, int],
    candle_right: int,
    font,
) -> None:
    """Reference trade path with Entry-origin arrows and TP1/TP2/TP3.

    Primary rule: every scenario path starts exactly at Entry.  The bend is
    intentional and always means Break -> Retest -> Continuation.  If there is
    no fresh executable/conditional plan, an ambiguous WATCH may show two
    dashed alternatives; neither is treated as active.
    """
    plan = _resolve_reference_trade_plan(analysis)
    draw_mode = str(analysis.get("draw_mode") or "watch")
    if not plan:
        _draw_reference_dual_watch_paths(draw, analysis, price_y, plot, candle_right, font)
        return
    lifecycle = _reference_trade_lifecycle(analysis, plan)
    state = str(lifecycle.get("state") or "none")

    # V7.9 keeps WATCH/RE-EVALUATE clean: no historical Entry/Stop/TP overlay
    # and no conditional execution box.  The two BUY/SELL trigger previews are
    # the only trade paths until an execution is actually confirmed.
    if draw_mode != "confirmed" or state != "active":
        _draw_reference_dual_watch_paths(draw, analysis, price_y, plot, candle_right, font)
        return

    left, top, right, bottom = plot
    side = str(plan["side"])
    entry, stop = float(plan["entry"]), float(plan["stop"])
    targets = [float(v) for v in (plan.get("targets") or [plan.get("target")]) if _number(v) is not None]
    if not targets:
        return
    bullish = side == "buy"
    directional_targets = [
        value for value in targets[:3]
        if (bullish and stop < entry < value) or ((not bullish) and stop > entry > value)
    ]
    if not directional_targets:
        return
    targets = directional_targets

    ey, sy = price_y(entry), price_y(stop)
    target_pairs = [(value, price_y(value)) for value in targets]
    far_y = target_pairs[-1][1]

    # Leave a clean lane for the exact right-axis cards while reserving enough
    # room for projected candles and the bent scenario arrow.
    x1 = max(candle_right + 24, left + int((right - left) * 0.72))
    x2 = right - 270
    if x2 - x1 < 118:
        x1 = max(candle_right + 14, x2 - 142)
    if x2 <= x1 + 82:
        return

    green = (72, 176, 104, 46)
    red = (216, 72, 80, 46)
    green_border = (55, 150, 87, 150)
    red_border = (193, 63, 70, 150)
    draw.rectangle((x1, min(ey, far_y), x2, max(ey, far_y)), fill=green)
    draw.rectangle((x1, min(ey, sy), x2, max(ey, sy)), fill=red)
    confirmed = lifecycle.get("state") == "active"
    if confirmed:
        draw.rectangle((x1, min(ey, far_y), x2, max(ey, far_y)), outline=green_border, width=2)
        draw.rectangle((x1, min(ey, sy), x2, max(ey, sy)), outline=red_border, width=2)
    else:
        for y, color in ((ey, (52, 58, 64, 160)), (sy, red_border)):
            _dash_line(draw, (x1, y), (x2, y), color, width=2, dash=9, gap=6)
        _dash_line(draw, (x1, far_y), (x2, far_y), green_border, width=2, dash=9, gap=6)

    # Exact target lines: no vertical displacement.  Labels may move only in X.
    target_colors = [(45, 164, 95, 205), (31, 144, 83, 205), (20, 119, 72, 210)]
    for i, (_value, y) in enumerate(target_pairs[:3], start=1):
        _dash_line(draw, (x1, y), (x2, y), target_colors[i-1], width=1, dash=7, gap=5)
        draw.text((x2 - 5, y - 4), f"TP{i}", font=font, fill=target_colors[i-1], anchor="rs")

    ring = (44, 151, 88, 235) if bullish else (202, 62, 72, 235)
    draw.ellipse((x1 - 9, ey - 9, x1 + 9, ey + 9), outline=ring, width=3)
    draw.text((x1 + 14, ey - 8), "ENTRY", font=font, fill=ring, anchor="ls")

    # Scenario candles begin after Entry and use only interpolation between the
    # real Entry/TP prices.  They are intentionally translucent.
    candle_lane_start = x1 + 18
    candle_lane_end = x2 - 12
    _draw_reference_projected_candles(
        draw,
        entry=entry,
        targets=targets,
        side=side,
        price_y=price_y,
        x1=candle_lane_start,
        x2=candle_lane_end,
        confirmed=confirmed,
    )

    # V7.9: the active path is directional by color and reacts at a REAL S/R
    # station when one exists between Entry and TP3.
    target_y = far_y
    end_x = x2 - 8
    reaction = _reference_reaction_level(analysis, side=side, entry=entry, target=targets[-1])
    if reaction:
        rx = x1 + max(38, int((x2 - x1) * 0.43))
        px = x1 + max(76, int((x2 - x1) * 0.68))
        ry = max(top + 20, min(bottom - 20, price_y(float(reaction["price"]))))
        py = int(round(ey + (ry - ey) * 0.40))
        path_points = [(x1, ey), (rx, ry), (px, py), (end_x, target_y)]
        _draw_reaction_tag(draw, rx, ry, side=side, strength=int(reaction.get("strength") or 0), font=font)
    else:
        break_y = int(round(ey + (target_y - ey) * 0.34))
        retest_y = int(round(ey + (target_y - ey) * 0.10))
        break_x = x1 + max(34, (x2 - x1) // 3)
        retest_x = x1 + max(68, (x2 - x1) * 2 // 3)
        path_points = [(x1, ey), (break_x, break_y), (retest_x, retest_y), (end_x, target_y)]
    path_color = (30, 167, 88, 235) if bullish else (216, 67, 76, 235)
    _recon_arrow(
        draw,
        path_points,
        path_color,
        width=4,
        dashed=not confirmed,
    )
    # Stage names are kept in the Expected Candle Sequence inset underneath
    # their projected candles.  Leaving the main price path unlabeled prevents
    # BREAK/RETEST text from covering real OHLC.

def _draw_reference_price_axis_and_cards(
    draw: ImageDraw.ImageDraw,
    analysis: dict[str, Any],
    price_y,
    price_min: float,
    price_max: float,
    plot: tuple[int, int, int, int],
    font,
    candle_right: int | None = None,
) -> None:
    """V7.9 right-lane cards with vertical auto-repel and exact connectors.

    WATCH/RE-EVALUATE shows only CURRENT + BUY IF + SELL IF.  Confirmed trades
    show ENTRY + STOP + TP1/2/3 (+ CURRENT).  Card text may move vertically to
    avoid collisions, but every connector starts at the exact real price Y.
    """
    left, top, right, bottom = plot
    tick_color = (92, 98, 104, 230)
    line_color = (150, 155, 160, 100)
    tick_label_x = right + 145

    tick_count = 9
    for i in range(tick_count):
        ratio = i / (tick_count - 1)
        price = price_max - (price_max - price_min) * ratio
        y = int(round(top + (bottom - top) * ratio))
        draw.line((right + 3, y, right + 10, y), fill=line_color, width=1)
        draw.text((tick_label_x, y), _fmt_axis_price(price), font=font, fill=tick_color, anchor="rm")

    plan = _resolve_reference_trade_plan(analysis)
    lifecycle = _reference_trade_lifecycle(analysis, plan) if plan else {"state": "none"}
    state = str(lifecycle.get("state") or "none")
    draw_mode = str(analysis.get("draw_mode") or "watch")
    confirmed = bool(plan) and state == "active" and draw_mode == "confirmed"
    cards: list[tuple[str, float, tuple[int,int,int,int], int]] = []

    if confirmed and plan:
        cards.extend([
            ("ENTRY", float(plan["entry"]), (36, 147, 85, 242), 1),
            ("STOP", float(plan["stop"]), (201, 62, 70, 242), 0),
        ])
        target_colors = [(45, 164, 95, 242), (31, 144, 83, 242), (20, 119, 72, 242)]
        target_names = (
            ["TP1 · NEAR HIGH", "TP2 · PREV HIGH", "TP3 · MAIN HIGH"]
            if str(plan.get("side")) == "buy"
            else ["TP1 · NEAR LOW", "TP2 · PREV LOW", "TP3 · MAIN LOW"]
        )
        for i, value in enumerate((plan.get("targets") or [plan.get("target")])[:3], start=1):
            number = _number(value)
            if number is not None:
                cards.append((target_names[i-1], float(number), target_colors[i-1], 2 + i))
    else:
        # Any non-confirmed state is visually a WATCH state.  Never duplicate a
        # conditional Entry/CANCEL/TP plan next to BUY/SELL triggers.
        buy = analysis.get("buy_scenario_details") if isinstance(analysis.get("buy_scenario_details"), dict) else {}
        sell = analysis.get("sell_scenario_details") if isinstance(analysis.get("sell_scenario_details"), dict) else {}
        buy_trigger = _number(buy.get("trigger_price"))
        sell_trigger = _number(sell.get("trigger_price"))
        buy_score = max(0, min(100, int(buy.get("score") or analysis.get("buy_probability") or 0)))
        sell_score = max(0, min(100, int(sell.get("score") or analysis.get("sell_probability") or 0)))
        if buy_trigger is not None:
            cards.append((f"BUY {buy_score}% IF", float(buy_trigger), (94, 49, 181, 235), 1))
        if sell_trigger is not None:
            cards.append((f"SELL {sell_score}% IF", float(sell_trigger), (42, 47, 52, 238), 2))

    current = _number(analysis.get("current_price"))
    if current is None:
        current = _number(analysis.get("visual_current_price"))
    if current is not None and price_min <= float(current) <= price_max:
        exact_current_y = price_y(float(current))
        _dash_line(draw, (left, exact_current_y), (right, exact_current_y), (62, 112, 112, 145), width=1, dash=5, gap=4)
        cards.append(("CURRENT", float(current), (55, 61, 67, 238), 0))

    visible = []
    for label, price, color, priority in cards:
        if price_min <= price <= price_max:
            visible.append({
                "label": label,
                "price": price,
                "color": color,
                "priority": priority,
                "exact_y": int(price_y(price)),
            })
    if not visible:
        return

    # One dedicated card corridor to the right of real candles.  This makes the
    # market geometry readable even when several levels share nearly the same Y.
    candle_right = int(candle_right if candle_right is not None else left + (right-left) * 0.80)
    corridor_left = max(candle_right + 26, right - 360)
    card_right = right - 14
    card_max_w = max(188, min(248, card_right - corridor_left))
    min_gap = 40
    half_h = 16

    # Stable auto-repel: sort by exact price Y, push downward, then shift the
    # entire stack upward if it exceeds the bottom and repair once upward.
    visible.sort(key=lambda item: (item["exact_y"], item["priority"]))
    for i, item in enumerate(visible):
        desired = max(top + half_h + 4, min(bottom - half_h - 4, item["exact_y"]))
        if i:
            desired = max(desired, visible[i-1]["display_y"] + min_gap)
        item["display_y"] = desired
    overflow = visible[-1]["display_y"] - (bottom - half_h - 4)
    if overflow > 0:
        for item in visible:
            item["display_y"] -= overflow
    for i in range(len(visible)-2, -1, -1):
        max_y = visible[i+1]["display_y"] - min_gap
        visible[i]["display_y"] = min(visible[i]["display_y"], max_y)
    underflow = (top + half_h + 4) - visible[0]["display_y"]
    if underflow > 0:
        for item in visible:
            item["display_y"] += underflow

    for item in visible:
        label, price, color = item["label"], item["price"], item["color"]
        exact_y, display_y = int(item["exact_y"]), int(round(item["display_y"]))
        card_text = f"{label} {_fmt_axis_price(price)}"
        tb = draw.textbbox((0, 0), card_text, font=font)
        text_w = max(1, tb[2] - tb[0])
        card_w = max(176, min(card_max_w, text_w + 22))
        card_left = card_right - card_w

        # Exact price anchor -> small elbow -> displaced card.  Price geometry
        # never moves; only the label box does.
        anchor_x = min(card_left - 12, max(candle_right + 8, corridor_left - 16))
        connector = (color[0], color[1], color[2], 125)
        draw.line((anchor_x, exact_y, card_left - 8, exact_y), fill=connector, width=1)
        if display_y != exact_y:
            draw.line((card_left - 8, exact_y, card_left - 8, display_y), fill=connector, width=1)
        draw.line((card_left - 8, display_y, card_left, display_y), fill=connector, width=1)
        draw.rounded_rectangle((card_left, display_y - half_h, card_right, display_y + half_h), radius=6, fill=color)
        draw.text((card_right - 9, display_y), card_text, font=font, fill=(255,255,255,255), anchor="rm")

def _draw_reference_legend(
    draw: ImageDraw.ImageDraw,
    analysis: dict[str, Any],
    plot: tuple[int, int, int, int],
    width: int,
    height: int,
) -> None:
    """Dynamic SMC legend plus the approved Arrow Rules strip.

    A concept is listed only when its real geometry exists in this result.  In
    particular MSS/CHOCH never appears merely because the template supports it.
    """
    left, _top, right, bottom = plot
    y0 = bottom + 54
    if y0 > height - 96:
        return
    draw.line((left, y0 - 20, width - 52, y0 - 20), fill=(168, 172, 176, 110), width=1)
    f_title = _font(11, True, True)
    f_desc = _font(9, False, True)
    f_rules = _font(10, True, True)

    components = set(str(x) for x in (analysis.get("reference_scenario_draw_components") or []))
    geom = analysis.get("reference_scenario_geometry") if isinstance(analysis.get("reference_scenario_geometry"), dict) else {}
    structure_labels = {
        str(event.get("label") or "").upper()
        for event in (geom.get("structure_events") or [])
        if isinstance(event, dict)
    }
    items: list[tuple[str, str, str, tuple[int,int,int,int]]] = []
    if "liquidity" in components and isinstance(geom.get("liquidity_sweep"), dict):
        items.append(("LIQUIDITY SWEEP", "Real wick beyond high/low", "circle", (198, 66, 76, 230)))
    if "structure" in components and "BOS" in structure_labels:
        items.append(("BOS", "Swing → break candle", "dash", (35, 145, 83, 230)))
    if "order_block" in components and isinstance(geom.get("order_block"), dict):
        items.append(("ORDER BLOCK", "Last opposite candle", "box", (205, 126, 56, 220)))
    if "fvg" in components and isinstance(geom.get("fvg"), dict):
        items.append(("FVG", "Real 3-candle gap", "box_blue", (55, 117, 171, 230)))
    if "structure" in components and "CHOCH" in structure_labels:
        items.append(("MSS / CHOCH", "Real structure change", "dash", (105, 63, 142, 230)))
    plan = _resolve_reference_trade_plan(analysis)
    if plan or _reference_dual_preview_needed(analysis):
        items.append(("PLAN", "Entry · SL/Cancel · TP1/2/3", "arrow", (45, 50, 55, 230)))

    if items:
        usable = width - left - 52
        col = usable / len(items)
        for i, (title, desc, kind, color) in enumerate(items):
            x = int(left + i * col + 2)
            icon_x = x + 11
            icon_y = y0 + 8
            if kind == "circle":
                _dashed_ellipse(draw, (icon_x - 8, icon_y - 8, icon_x + 8, icon_y + 8), color, width=2)
            elif kind == "dash":
                _dash_line(draw, (icon_x - 10, icon_y), (icon_x + 12, icon_y), color, width=2, dash=6, gap=4)
            elif kind == "box":
                draw.rectangle((icon_x - 9, icon_y - 7, icon_x + 13, icon_y + 7), fill=(231, 174, 116, 60), outline=color, width=1)
            elif kind == "box_blue":
                draw.rectangle((icon_x - 9, icon_y - 7, icon_x + 13, icon_y + 7), fill=(114, 173, 219, 34), outline=color, width=1)
            else:
                _recon_arrow(draw, [(icon_x - 10, icon_y), (icon_x + 12, icon_y)], color, width=2, dashed=True)
            tx = x + 30
            draw.text((tx, y0), title, font=f_title, fill=color, anchor="la")
            draw.text((tx, y0 + 19), desc, font=f_desc, fill=(92, 97, 102, 235), anchor="la")

    # Dedicated Arrow Rules strip.  This explains the line grammar rather than
    # a specific trade and remains visible on every accepted scenario.
    rules_y = y0 + 53
    if rules_y > height - 20:
        return
    draw.line((left, rules_y - 12, width - 52, rules_y - 12), fill=(184, 188, 192, 90), width=1)
    draw.text((left, rules_y), "ARROW RULES", font=f_rules, fill=(38, 43, 49, 235), anchor="la")

    rules = [
        ("UP", "breakout", (35, 145, 83, 220), "up"),
        ("DOWN", "rejection / break", (198, 66, 76, 220), "down"),
        ("PATH", "BREAK → RETEST → CONTINUATION", (55, 61, 67, 220), "bend"),
        ("ORIGIN", "all scenario arrows start at ENTRY", (92, 98, 104, 230), "dot"),
    ]
    start_x = left + 125
    usable = width - 52 - start_x
    col = usable / len(rules)
    for i, (title, desc, color, kind) in enumerate(rules):
        x = int(start_x + i * col)
        ix, iy = x + 12, rules_y + 7
        if kind == "up":
            _recon_arrow(draw, [(ix - 10, iy + 7), (ix + 12, iy - 7)], color, width=2, dashed=False)
        elif kind == "down":
            _recon_arrow(draw, [(ix - 10, iy - 7), (ix + 12, iy + 7)], color, width=2, dashed=False)
        elif kind == "bend":
            _recon_arrow(draw, [(ix - 12, iy + 4), (ix - 2, iy - 6), (ix + 6, iy + 1), (ix + 16, iy - 8)], color, width=2, dashed=True)
        else:
            draw.ellipse((ix - 4, iy - 4, ix + 4, iy + 4), fill=color)
        tx = x + 34
        draw.text((tx, rules_y), title, font=f_rules, fill=color, anchor="la")
        draw.text((tx, rules_y + 18), desc, font=f_desc, fill=(92, 97, 102, 235), anchor="la")



def _draw_reference_expected_sequence_inset(
    draw: ImageDraw.ImageDraw,
    analysis: dict[str, Any],
    plot: tuple[int, int, int, int],
) -> None:
    """Approved miniature BREAK → RETEST → CONTINUATION teaching card.

    This card is explanatory only.  It never creates market prices and is
    intentionally separated from the price-scaled chart geometry.
    """
    components = set(str(x) for x in (analysis.get("reference_scenario_draw_components") or []))
    plan = _resolve_reference_trade_plan(analysis)
    if "expectation_arrow" not in components and not plan:
        return

    left, top, right, bottom = plot
    panel_w, panel_h = 326, 116
    x2 = min(right - 310, left + int((right - left) * 0.74))
    x1 = x2 - panel_w
    y2 = bottom - 8
    y1 = y2 - panel_h
    if x1 < left + 360:
        x1 = left + int((right - left) * 0.50)
        x2 = x1 + panel_w
    if x2 > right - 260:
        x2 = right - 260
        x1 = x2 - panel_w

    draw.rounded_rectangle(
        (x1, y1, x2, y2),
        radius=8,
        fill=(247, 248, 247, 244),
        outline=(112, 118, 123, 170),
        width=1,
    )
    f_title = _font(12, True, True)
    f_sub = _font(10, False, True)
    f_cell = _font(9, True, True)
    draw.text(((x1 + x2) // 2, y1 + 11), "EXPECTED CANDLE SEQUENCE", font=f_title, fill=(28, 32, 37, 245), anchor="ma")
    draw.text(((x1 + x2) // 2, y1 + 29), "Break → Retest → Continuation", font=f_sub, fill=(70, 75, 80, 235), anchor="ma")

    side = str(plan.get("side") if plan else "buy")
    bullish = side != "sell"
    cell_gap = 8
    inner_l, inner_r = x1 + 10, x2 - 10
    cell_w = (inner_r - inner_l - cell_gap * 2) // 3
    cell_y1, cell_y2 = y1 + 43, y2 - 7
    labels = ("BREAK", "RETEST", "CONTINUATION")
    for i, label in enumerate(labels):
        cx1 = inner_l + i * (cell_w + cell_gap)
        cx2 = cx1 + cell_w
        draw.rounded_rectangle((cx1, cell_y1, cx2, cell_y2), radius=5, fill=(250, 250, 248, 255), outline=(155, 160, 164, 150), width=1)

        # Tiny pedagogical candles. Direction mirrors the plan, but their
        # vertical positions are local to the inset and never map to prices.
        # V7.6 keeps the stage label underneath its miniature candles.
        base = cell_y2 - 28 if bullish else cell_y1 + 17
        step = -10 if bullish else 10
        colors_up = (39, 151, 89, 230)
        colors_dn = (207, 58, 67, 230)

        if label == "BREAK":
            sequence = [
                (colors_dn if bullish else colors_up, 0, 6),
                (colors_up if bullish else colors_dn, 1, 17),
                (colors_up if bullish else colors_dn, 2, 12),
            ]
        elif label == "RETEST":
            sequence = [
                (colors_dn if bullish else colors_up, 1, 14),
                (colors_up if bullish else colors_dn, 0, 7),
                (colors_dn if bullish else colors_up, -1, 7),
                (colors_up if bullish else colors_dn, 1, 14),
            ]
        else:
            sequence = [
                (colors_up if bullish else colors_dn, 0, 8),
                (colors_up if bullish else colors_dn, 1, 12),
                (colors_up if bullish else colors_dn, 2, 15),
                (colors_up if bullish else colors_dn, 3, 18),
            ]
        slot = max(10, (cell_w - 18) // max(1, len(sequence)))
        for j, (color, level, body_h) in enumerate(sequence):
            x = cx1 + 10 + slot * j + slot // 2
            center = base + step * level
            if bullish:
                yy2 = center
                yy1 = center - body_h
            else:
                yy1 = center
                yy2 = center + body_h
            draw.line((x, yy1 - 4, x, yy2 + 4), fill=(color[0], color[1], color[2], 170), width=1)
            draw.rectangle((x - 3, yy1, x + 3, yy2), fill=color)

        draw.text(((cx1 + cx2) // 2, cell_y2 - 5), label, font=f_cell, fill=(42, 46, 50, 245), anchor="ms")

        if i < 2:
            ax = cx2 + cell_gap // 2
            ay = (cell_y1 + cell_y2) // 2 + 5
            _recon_arrow(draw, [(ax - 5, ay), (ax + 5, ay)], (48, 53, 58, 210), width=1, dashed=False)


def _draw_reference_footer_panels(
    draw: ImageDraw.ImageDraw,
    analysis: dict[str, Any],
    plot: tuple[int, int, int, int],
    width: int,
    height: int,
) -> None:
    """V7.6 bottom composition matching the user's approved second image.

    Left: Arabic arrow rules. Middle: dynamic SMC legend. Right: trade-plan
    summary with Entry/Stop/TP1/TP2/TP3 and R:R.  Geometry remains market-owned;
    these panels are explanatory metadata only.
    """
    left, _top, right, bottom = plot
    top_y = bottom + 24
    bottom_y = height - 38
    gap = 14
    x0 = 20
    total_w = width - 40
    left_w = 560
    mid_w = 520
    right_w = total_w - left_w - mid_w - gap * 2
    panels = [
        (x0, top_y, x0 + left_w, bottom_y),
        (x0 + left_w + gap, top_y, x0 + left_w + gap + mid_w, bottom_y),
        (x0 + left_w + gap + mid_w + gap, top_y, width - 20, bottom_y),
    ]
    for rect in panels:
        draw.rounded_rectangle(rect, radius=9, fill=(248, 249, 248, 248), outline=(171, 176, 180, 150), width=1)

    # --- Arrow rules panel ---
    ax1, ay1, ax2, ay2 = panels[0]
    f_ar_title = _font(16, True, True)
    f_ar = _font(11, False, True)
    f_num = _font(10, True, True)
    _draw_rtl(draw, ((ax1 + ax2) // 2, ay1 + 20), "قواعد خطوط الأسهم", f_ar_title, (26, 31, 36, 245), anchor="ma")
    draw.line((ax1 + 24, ay1 + 38, ax2 - 24, ay1 + 38), fill=(112, 80, 159, 100), width=1)

    rules = [
        ("1", "خط السيناريو الصاعد (الأرجواني) يبدأ من مستوى ENTRY وينتظر الاختراق وإعادة الاختبار."),
        ("2", "خط السيناريو الهابط (الأسود) يبدأ من مستوى ENTRY ويعبّر عن الرفض أو الكسر الهابط."),
        ("3", "المسار المتوقع يتبع بنية السوق: اختراق → إعادة اختبار → استمرار الحركة."),
        ("4", "جميع خطوط الأسهم تبدأ دائماً من مستوى ENTRY لربط الخطة بمستوى سعر حقيقي."),
        ("5", "لا يتم تفعيل أي صفقة جديدة إلا بعد وجود Trigger جديد على إطار M5."),
    ]
    y = ay1 + 58
    for num, rule in rules:
        cy = y + 6
        draw.ellipse((ax1 + 18, cy - 9, ax1 + 36, cy + 9), fill=(68, 35, 135, 245))
        draw.text((ax1 + 27, cy), num, font=f_num, fill=(255, 255, 255, 255), anchor="mm")
        _draw_rtl(draw, (ax2 - 18, y), rule, f_ar, (45, 50, 55, 245), anchor="ra")
        y += 34

    # --- Dynamic legend panel ---
    lx1, ly1, lx2, ly2 = panels[1]
    f_leg_title = _font(14, True, True)
    f_leg = _font(10, True, True)
    f_desc = _font(8, False, True)
    draw.text(((lx1 + lx2) // 2, ly1 + 20), "LEGEND", font=f_leg_title, fill=(30, 35, 40, 245), anchor="ma")
    draw.line((lx1 + 24, ly1 + 38, lx2 - 24, ly1 + 38), fill=(75, 116, 169, 100), width=1)

    components = set(str(x) for x in (analysis.get("reference_scenario_draw_components") or []))
    geom = analysis.get("reference_scenario_geometry") if isinstance(analysis.get("reference_scenario_geometry"), dict) else {}
    structure_labels = {
        str(event.get("label") or "").upper()
        for event in (geom.get("structure_events") or [])
        if isinstance(event, dict)
    }
    legend_items = [
        ("RESISTANCE / LIQUIDITY", "Supply / liquidity zone", "box_red", (199, 68, 77, 230), True),
        ("FVG", "Fair Value Gap", "box_blue", (52, 119, 184, 230), "fvg" in components),
        ("BOS", "Break of Structure", "dash_green", (35, 145, 83, 230), "BOS" in structure_labels),
        ("LIQUIDITY SWEEP", "Wick beyond equal high/low", "dash_blue", (42, 110, 176, 230), "liquidity" in components),
        ("ORDER BLOCK (OB)", "Last opposite candle", "box_green", (43, 143, 83, 230), "order_block" in components),
        ("MSS / CHOCH", "Market Structure Shift", "dash_purple", (103, 61, 145, 230), "CHOCH" in structure_labels),
        ("PLAN", "Entry · Stop · Target", "arrow", (45, 50, 55, 230), bool(_resolve_reference_trade_plan(analysis)) or _reference_dual_preview_needed(analysis)),
    ]
    legend_items = [item for item in legend_items if bool(item[4])]
    col_w = (lx2 - lx1 - 38) // 2
    row_h = 44
    for i, (title, desc, kind, color, _show) in enumerate(legend_items[:8]):
        col = i % 2
        row = i // 2
        x = lx1 + 18 + col * col_w
        y0 = ly1 + 54 + row * row_h
        ix, iy = x + 12, y0 + 8
        if kind == "box_red":
            draw.rectangle((ix - 10, iy - 7, ix + 14, iy + 7), fill=(223, 77, 85, 35), outline=color, width=1)
        elif kind == "box_blue":
            draw.rectangle((ix - 10, iy - 7, ix + 14, iy + 7), fill=(92, 157, 211, 38), outline=color, width=1)
        elif kind == "box_green":
            draw.rectangle((ix - 10, iy - 7, ix + 14, iy + 7), fill=(92, 168, 110, 35), outline=color, width=1)
        elif kind.startswith("dash"):
            _dash_line(draw, (ix - 11, iy), (ix + 15, iy), color, width=2, dash=6, gap=4)
        else:
            _recon_arrow(draw, [(ix - 11, iy), (ix + 15, iy)], color, width=2, dashed=True)
        tx = x + 34
        draw.text((tx, y0), title, font=f_leg, fill=color, anchor="la")
        draw.text((tx, y0 + 17), desc, font=f_desc, fill=(90, 95, 100, 235), anchor="la")

    # --- Trade plan summary panel ---
    tx1, ty1, tx2, ty2 = panels[2]
    navy = (20, 54, 101, 245)
    f_table_title = _font(12, True, True)
    f_table = _font(10, True, True)
    f_table_small = _font(9, False, True)
    header_h = 28
    draw.rectangle((tx1, ty1, tx2, ty1 + header_h), fill=navy)
    draw.text(((tx1 + tx2) // 2, ty1 + header_h // 2), "TRADE PLAN SUMMARY", font=f_table_title, fill=(255, 255, 255, 255), anchor="mm")

    plan = _resolve_reference_trade_plan(analysis)
    lifecycle = _reference_trade_lifecycle(analysis, plan) if plan else {"state": "none"}
    state = str(lifecycle.get("state") or "none")
    if _reference_dual_preview_needed(analysis):
        type_text = "WATCH / BUY OR SELL"
    elif state == "active":
        type_text = "BUY" if str(plan.get("side")) == "buy" else "SELL"
    elif state == "conditional":
        type_text = "WATCH / CONDITIONAL"
    elif state in {"expired", "target_hit", "invalidated"}:
        type_text = "WATCH / RE-EVALUATE"
    else:
        type_text = "WATCH"

    table_top = ty1 + header_h
    col1 = tx1 + 92
    col2 = tx1 + 265
    draw.line((col1, table_top, col1, ty2 - 10), fill=(185, 189, 193, 140), width=1)
    draw.line((col2, table_top, col2, ty2 - 10), fill=(185, 189, 193, 140), width=1)
    draw.text((tx1 + 45, table_top + 15), "TYPE", font=f_table, fill=(65, 70, 75, 245), anchor="mm")
    draw.text(((col1 + col2) // 2, table_top + 15), type_text, font=f_table, fill=(33, 38, 43, 245), anchor="mm")
    summary_header = "R:R / STRENGTH" if _reference_dual_preview_needed(analysis) else "R:R SUMMARY"
    draw.text(((col2 + tx2) // 2, table_top + 15), summary_header, font=f_table, fill=(33, 38, 43, 245), anchor="mm")
    draw.line((tx1, table_top + 30, tx2, table_top + 30), fill=(185, 189, 193, 140), width=1)

    rows: list[tuple[str, str, tuple[int,int,int,int], str]] = []
    best_rr = 0.0
    best_label = "—"
    if plan:
        entry = float(plan["entry"])
        stop = float(plan["stop"])
        targets = [float(v) for v in (plan.get("targets") or [plan.get("target")]) if _number(v) is not None][:3]
        risk = abs(entry - stop)
        rows.append(("ENTRY", _fmt_axis_price(entry), (42, 112, 183, 245), f"RISK {risk:.2f}"))
        rows.append(("STOP", _fmt_axis_price(stop), (201, 62, 70, 245), ""))
        target_cols = [(45, 164, 95, 245), (31, 144, 83, 245), (20, 119, 72, 245)]
        for i, target in enumerate(targets, 1):
            rr = abs(target - entry) / risk if risk > 1e-9 else 0.0
            if rr > best_rr:
                best_rr = rr
                best_label = f"TP{i}"
            rows.append((f"TP{i}", _fmt_axis_price(target), target_cols[i-1], f"1:{rr:.2f}" if risk > 1e-9 else "—"))
    else:
        current = _number(analysis.get("current_price"))
        rows.append(("CURRENT", _fmt_axis_price(current) if current is not None else "—", (55, 61, 67, 245), ""))

    if _reference_dual_preview_needed(analysis):
        buy = analysis.get("buy_scenario_details") if isinstance(analysis.get("buy_scenario_details"), dict) else {}
        sell = analysis.get("sell_scenario_details") if isinstance(analysis.get("sell_scenario_details"), dict) else {}
        buy_trigger = _number(buy.get("trigger_price"))
        sell_trigger = _number(sell.get("trigger_price"))
        if buy_trigger is not None:
            rows.append((
                "BUY IF", _fmt_axis_price(float(buy_trigger)), (94, 49, 181, 245),
                f"{max(0, min(100, int(buy.get('score') or 0)))}%",
            ))
        if sell_trigger is not None:
            rows.append((
                "SELL IF", _fmt_axis_price(float(sell_trigger)), (42, 47, 52, 245),
                f"{max(0, min(100, int(sell.get('score') or 0)))}%",
            ))

    row_top = table_top + 31
    available = max(1, ty2 - 28 - row_top)
    row_h = max(22, min(31, available // max(1, len(rows))))
    for i, (label, value, color, rr_text) in enumerate(rows):
        y1 = row_top + i * row_h
        ymid = y1 + row_h // 2
        draw.line((tx1, y1 + row_h, tx2, y1 + row_h), fill=(205, 208, 211, 120), width=1)
        draw.text((tx1 + 45, ymid), label, font=f_table, fill=color, anchor="mm")
        draw.text(((col1 + col2) // 2, ymid), value, font=f_table, fill=color, anchor="mm")
        draw.text(((col2 + tx2) // 2, ymid), rr_text, font=f_table_small, fill=(45, 50, 55, 245), anchor="mm")

    if plan and best_rr > 0:
        badge_y1 = ty2 - 29
        draw.rounded_rectangle((col2 + 12, badge_y1, tx2 - 12, ty2 - 8), radius=5, fill=navy)
        draw.text(((col2 + tx2) // 2, (badge_y1 + ty2 - 8) // 2), f"BEST R:R → {best_label} (1:{best_rr:.2f})", font=f_table_small, fill=(255, 255, 255, 255), anchor="mm")

    # Small educational footer matching the approved reference style.
    f_note = _font(8, False, True)
    draw.text((20, height - 14), "ⓘ  Educational analysis only. Wait for a new M5 trigger before executing.", font=f_note, fill=(83, 88, 93, 235), anchor="la")

def _build_reference_visual_scene(analysis: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic render geometry only; never create a market decision."""
    width, height = _reconstructed_dimensions(analysis)
    candles, offset = _reconstructed_window(analysis)
    price_min, price_max = _reconstructed_price_range(analysis, candles) if candles else (0.0, 1.0)
    template_id = _reference_template_kind(analysis)
    visual_score = max(
        int(analysis.get("reference_visual_score") or 0),
        int(analysis.get("reference_match_score") or 0),
        int(analysis.get("reference_scenario_confidence") or 0),
        int(analysis.get("pattern_confidence") or 0),
    )
    rejection = str(analysis.get("reference_visual_rejection_reason") or "")
    if template_id and visual_score and visual_score < 68:
        rejection = rejection or "pattern_score_below_68"
        template_id = ""
    plan = _resolve_reference_trade_plan(analysis)
    lifecycle = _reference_trade_lifecycle(analysis, plan) if plan else {"state": "none", "current": None}
    live_plan = lifecycle.get("state") in {"active", "conditional"}
    dual_watch = _reference_dual_preview_needed(analysis)
    return {
        "canvas": {"width": width, "height": height},
        "candles": candles,
        "window_offset": offset,
        "price_min": price_min,
        "price_max": price_max,
        "template_id": template_id,
        "visual_score": visual_score,
        "rejection_reason": rejection,
        "trade_lifecycle": lifecycle,
        # Keep the approved reference-sheet composition stable whenever a real
        # deterministic plan exists. Completed/invalidated plans no longer draw
        # the risk box, but the empty future lane avoids layout jumps between
        # consecutive renders of the same setup.
        # Preserve the future lane even after a plan completes so consecutive
        # renders do not jump horizontally.  Execution graphics themselves are
        # still removed by the lifecycle guard.
        "future_space_ratio": 0.20 if plan and template_id else 0.20 if dual_watch and template_id else 0.10 if template_id else 0.05,
    }


def _render_reconstructed_market_chart(
    analysis: dict[str, Any],
    chart_background_path: str | os.PathLike[str] | None = None,
) -> bytes:
    """V7.9 M5 simple decision chart: one clear model and reaction-aware path."""
    scene = _build_reference_visual_scene(analysis)
    width, height = int(scene["canvas"]["width"]), int(scene["canvas"]["height"])
    palette = _reconstructed_palette(analysis)
    image = Image.new("RGBA", (width, height), palette["bg"])
    draw = ImageDraw.Draw(image)
    candles = list(scene["candles"])
    if not candles:
        out = io.BytesIO(); image.convert("RGB").save(out, format="PNG"); return out.getvalue()

    # V7.9: the PNG is one full M5 decision chart, not a report sheet. Rules, legend and plan
    # summaries are rendered as real HTML UI outside the image.  This gives
    # the candles substantially more vertical room and removes report boxes.
    margin_l, margin_r, margin_t, margin_b = 24, 215, 100, 72
    plot = (margin_l, margin_t, width - margin_r, height - margin_b)
    left, top, right, bottom = plot
    draw.rectangle((left, top, right, bottom), fill=palette["plot"])
    _draw_reference_texture(draw, plot)

    price_min, price_max = float(scene["price_min"]), float(scene["price_max"])
    def price_y(price: float) -> int:
        ratio = (price_max - float(price)) / max(1e-9, price_max - price_min)
        return int(round(top + ratio * (bottom - top)))

    # Fine, quiet chart grid like the approved reference image.
    for i in range(1, 8):
        y = int(round(top + (bottom - top) * i / 8))
        draw.line((left, y, right, y), fill=(105, 112, 118, 24), width=1)
    for i in range(1, 11):
        x = int(round(left + (right - left) * i / 11))
        draw.line((x, top, x, bottom), fill=(105, 112, 118, 20), width=1)

    template_id = str(scene.get("template_id") or "")
    has_plan = _resolve_reference_trade_plan(analysis) is not None and bool(template_id)
    future_ratio = float(scene.get("future_space_ratio") or 0.16)
    history_ratio = 1.0 - future_ratio if template_id else 0.92
    candle_right = int(left + (right - left) * history_ratio)
    slot = (candle_right - left) / max(1, len(candles))
    body_w = max(8, min(18, int(slot * 0.72)))
    candle_x: list[int] = []
    for i, candle in enumerate(candles):
        x = int(round(left + slot * (i + 0.5)))
        candle_x.append(x)
        oy, cy = price_y(float(candle["open"])), price_y(float(candle["close"]))
        hy, ly = price_y(float(candle["high"])), price_y(float(candle["low"]))
        bullish = float(candle["close"]) >= float(candle["open"])
        color = palette["bull"] if bullish else palette["bear"]
        draw.line((x, hy, x, ly), fill=(color[0], color[1], color[2], 230), width=max(1, body_w // 4))
        y1, y2 = sorted((oy, cy))
        if y2 - y1 < 2: y2 = y1 + 2
        draw.rectangle((x - body_w // 2, y1, x + body_w // 2, y2), fill=color, outline=(34, 36, 39, 90), width=1)

    f_axis = _font(16, False, True)
    for j in range(6):
        idx = round(j * (len(candles) - 1) / 5)
        draw.text((candle_x[idx], bottom + 22), _time_label(candles[idx].get("time")), font=f_axis, fill=palette["muted"], anchor="ma")

    f_title = _font(30, True, True)
    f_sub = _font(15, True, True)
    f_label = _font(14, True, True)
    draw.text((left, 20), "XAUUSD · M5", font=f_title, fill=palette["text"], anchor="la")
    # Fine divider used by the approved reference header.
    draw.line((325, 16, 325, 60), fill=(88, 93, 98, 145), width=1)

    lifecycle_state = str((scene.get("trade_lifecycle") or {}).get("state") or "none")
    expired = lifecycle_state in {"expired", "target_hit", "invalidated"} or bool(analysis.get("scenario_expired"))
    scenario_bias = str(analysis.get("reference_scenario_bias") or analysis.get("pattern_bias") or "محايد")
    confirmed_execution = lifecycle_state == "active" and str(analysis.get("draw_mode") or "watch") == "confirmed"

    # V7.9 header answers only the decision question; SMC evidence stays on the chart.
    if expired:
        headline = "M5 DECISION VIEW · RE-EVALUATE"
    elif confirmed_execution and scenario_bias == "صاعد":
        headline = "M5 BUY ACTIVE · FOLLOW REACTION LEVELS"
    elif confirmed_execution and scenario_bias == "هابط":
        headline = "M5 SELL ACTIVE · FOLLOW REACTION LEVELS"
    elif scenario_bias == "صاعد":
        headline = "M5 DECISION VIEW · WAIT BUY TRIGGER"
    elif scenario_bias == "هابط":
        headline = "M5 DECISION VIEW · WAIT SELL TRIGGER"
    else:
        headline = "M5 DECISION VIEW · WAIT CLEAR TRIGGER"
    draw.text(((left + right) // 2 + 55, 22), headline, font=f_title, fill=palette["text"], anchor="ma")

    model = str(analysis.get("pattern_type") or "")
    subtitle_parts = ["BREAK → RETEST → CONTINUATION"]
    if model and model != "لا يوجد":
        subtitle_parts.append(_reference_model_english(model))
    draw.text(((left + right) // 2 + 40, 61), " · ".join(subtitle_parts[:2]), font=f_sub, fill=palette["muted"], anchor="ma")

    if template_id:
        _draw_reconstructed_reference_zones(draw, analysis, candles, candle_x, price_y, plot, f_label, candle_right)
        _draw_reconstructed_reference_scenario(image, analysis, candles, candle_x, price_y, plot, palette, f_label, candle_right)
        _draw_reference_trade_plan(draw, analysis, price_y, plot, candle_right, f_label)
    else:
        # Keep rejection visible to logs/data, not as chart clutter.
        pass
    _draw_reference_price_axis_and_cards(draw, analysis, price_y, price_min, price_max, plot, f_label, candle_right)
    # V7.9 deliberately does not paint Expected-Sequence, Arrow-Rules, Legend
    # or Trade-Plan report boxes into the PNG.  Those belong to the app UI.

    out = io.BytesIO()
    # ImageDraw writes RGBA fills by replacement; composite once onto the paper
    # background so translucent zones/grid actually remain translucent.
    flattened = Image.new("RGBA", image.size, palette["bg"])
    flattened.alpha_composite(image)
    flattened.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()

def render_share_snapshot(analysis: dict[str, Any], chart_png: bytes) -> bytes:
    """Create a pattern-first image for Save/Share without polluting the chart.

    The interactive chart keeps the exact uploaded pixels and composites only
    the verified educational overlay.  The source/scenario rule explanation
    remains directly below the chart, followed by compact cards.
    """
    try:
        with Image.open(io.BytesIO(chart_png)) as source:
            chart = source.convert("RGBA").copy()
    except Exception:
        chart = Image.new("RGBA", (1320, 620), (245, 247, 250, 255))

    pad = 28
    canvas_w = min(1900, max(1320, chart.width + pad * 2))
    chart_target_w = canvas_w - pad * 2
    scale = min(1.0, chart_target_w / max(1, chart.width))
    chart_w = max(1, int(round(chart.width * scale)))
    chart_h = max(1, int(round(chart.height * scale)))
    if (chart_w, chart_h) != chart.size:
        chart = chart.resize((chart_w, chart_h), Image.Resampling.LANCZOS)

    header_h = 360
    rule_h = 250
    bottom_h = 230
    footer_h = 58
    canvas_h = header_h + chart_h + rule_h + bottom_h + footer_h + pad * 4
    image = Image.new("RGBA", (canvas_w, canvas_h), (4, 12, 24, 255))
    draw = ImageDraw.Draw(image)

    f_brand = _font(46, True, True)
    f_sub = _font(21, False, True)
    f_state = _font(34, True)
    f_instruction = _font(24, True)
    f_card_label = _font(18, True)
    f_card_value = _font(27, True)
    f_card_value_latin = _font(27, True, True)
    f_small = _font(17, False)
    f_small_latin = _font(17, False, True)
    f_rule_title = _font(28, True)
    f_rule = _font(20, False)
    f_rule_bold = _font(20, True)
    f_rule_latin = _font(17, True, True)

    action = analysis.get("action_summary") if isinstance(analysis.get("action_summary"), dict) else {}
    code = str(action.get("code") or analysis.get("draw_mode") or "watch")
    side = str(action.get("primary_side") or "wait")
    confirmed = bool(action.get("is_confirmed"))
    if confirmed and side == "buy":
        accent = (28, 184, 106, 255)
    elif confirmed and side == "sell":
        accent = (225, 71, 78, 255)
    elif code == "inactive":
        accent = (202, 151, 45, 255)
    elif code.startswith("watch") or code in {"no_trade", "no_signal"}:
        accent = (65, 132, 242, 255)
    else:
        accent = (230, 147, 43, 255)

    # Identity row.
    draw.text((pad, 34), "SaleeM", font=f_brand, fill=(248, 250, 252, 255), anchor="la")
    draw.text((pad, 83), "XAUUSD  /  M5", font=f_sub, fill=(156, 174, 199, 255), anchor="la")
    last_update = str(analysis.get("analysis_last_closed_m5_time") or analysis.get("market_m5_latest_candle_time") or "—")
    draw.text((canvas_w - pad, 84), last_update, font=f_small_latin, fill=(145, 163, 187, 255), anchor="ra")

    # Primary answer banner.
    banner = (pad, 118, canvas_w - pad, 236)
    draw.rounded_rectangle(banner, radius=20, fill=(8, 24, 43, 255), outline=(accent[0], accent[1], accent[2], 220), width=2)
    draw.rectangle((banner[0], banner[1], banner[0] + 8, banner[3]), fill=accent)
    title = str(action.get("title") or "مراقبة")
    instruction = str(action.get("instruction") or "انتظر إغلاق M5 واضح قبل أي قرار")
    _draw_rtl(draw, (banner[2] - 24, banner[1] + 28), title, f_state, accent, anchor="ra")
    fitted_instruction = _fit_text(draw, instruction, f_instruction, banner[2] - banner[0] - 60, rtl=True)
    _draw_rtl(draw, (banner[2] - 24, banner[1] + 78), fitted_instruction, f_instruction, (236, 242, 250, 255), anchor="ra")

    direction = str(analysis.get("higher_timeframe_direction") or analysis.get("direction") or "غير واضح")
    movement = str(analysis.get("current_movement") or "غير واضح")
    pattern = str(analysis.get("pattern_type") or "لا يوجد")
    strength = int(action.get("strength") or analysis.get("trade_probability") or 0)
    rule_check = analysis.get("rule_check") if isinstance(analysis.get("rule_check"), dict) else {}
    rule_match = int(rule_check.get("match_percent") if rule_check.get("match_percent") is not None else strength)
    zone = analysis.get("decision_zone") if isinstance(analysis.get("decision_zone"), dict) else {}
    zone_value = "بين مستويات"
    if zone.get("active"):
        lo = _number(zone.get("low")); hi = _number(zone.get("high"))
        if lo is not None and hi is not None:
            zone_value = f"{_fmt_axis_price(lo)} - {_fmt_axis_price(hi)}"

    metrics = [
        ("الاتجاه العام", direction, GREEN if direction == "صاعد" else RED if direction == "هابط" else BLUE, False),
        ("الحركة الحالية", movement, GREEN if movement == "صاعد" else RED if movement == "هابط" else BLUE, False),
        ("منطقة القرار", zone_value, GOLD if zone.get("active") else CYAN, True),
        ("تطابق القاعدة", f"{rule_match}%", GREEN if rule_match == 100 else GOLD if rule_match >= 75 else BLUE, True),
    ]
    cards_y1, cards_y2 = 252, 342
    gap = 12
    card_w = (canvas_w - pad * 2 - gap * 3) // 4
    for i, (label, value, color, latin_value) in enumerate(metrics):
        x1 = pad + i * (card_w + gap)
        x2 = x1 + card_w
        draw.rounded_rectangle((x1, cards_y1, x2, cards_y2), radius=14, fill=(7, 21, 37, 255), outline=(46, 66, 88, 220), width=1)
        _draw_rtl(draw, (x2 - 14, cards_y1 + 20), label, f_card_label, (151, 169, 194, 255), anchor="ra")
        if latin_value:
            draw.text((x2 - 14, cards_y2 - 20), value, font=f_card_value_latin, fill=color, anchor="rs")
        else:
            fitted = _fit_text(draw, value, f_card_value, card_w - 28, rtl=True)
            _draw_rtl(draw, (x2 - 14, cards_y2 - 20), fitted, f_card_value, color, anchor="ra")

    # Exact chart area (preserve aspect ratio and do not crop candles or axis).
    chart_y = header_h + pad
    chart_x = (canvas_w - chart_w) // 2
    draw.rounded_rectangle((chart_x - 4, chart_y - 4, chart_x + chart_w + 4, chart_y + chart_h + 4), radius=8, fill=(255, 255, 255, 255), outline=(61, 82, 108, 255), width=2)
    image.alpha_composite(chart, dest=(chart_x, chart_y))

    # The user's approved rule explanation is always directly below the chart.
    rule_y1 = chart_y + chart_h + pad
    rule_y2 = rule_y1 + rule_h
    draw.rounded_rectangle(
        (pad, rule_y1, canvas_w - pad, rule_y2),
        radius=18,
        fill=(247, 250, 254, 255),
        outline=(72, 113, 170, 255),
        width=2,
    )
    _draw_rtl(draw, (canvas_w // 2, rule_y1 + 34), "القاعدة الأساسية", f_rule_title, (28, 74, 126, 255), anchor="ma")

    pattern_name = str(analysis.get("pattern_type") or "لا يوجد")
    pattern_status = str(analysis.get("pattern_status") or "none")
    scenario_available = bool(analysis.get("reference_scenario_available"))
    scenario_name = str(analysis.get("reference_scenario_label") or "").strip()
    scenario_status = str(analysis.get("reference_scenario_status") or "none")
    reference_id = str(analysis.get("reference_scenario_source_id") or analysis.get("pattern_reference_source_id") or "").strip()
    reference_rule = str(analysis.get("reference_scenario_rule") or analysis.get("pattern_reference_rule") or "").strip()
    evidence = str(analysis.get("reference_scenario_evidence") or analysis.get("pattern_reference_visual_evidence") or analysis.get("pattern_review_summary") or "").strip()
    if scenario_available and scenario_name:
        intro = f"تمت مراجعة الشارت مع ذاكرة السيناريوهات المرجعية، والسيناريو الأقرب هو: {scenario_name}."
        rule_text = reference_rule or evidence or "لا يُقبل السيناريو إلا بعد تحقق مكوناته على شموع M5 الحقيقية."
        arrow_text = (
            "السهم المتصل يوضح المسار المرجعي بعد اكتمال التحقق الهندسي."
            if scenario_status == "confirmed"
            else "السهم المتقطع يوضح أقرب سيناريو مرجعي مرشح؛ لا يعني دخولًا قبل اكتمال شرط التفعيل."
        )
    elif pattern_name != "لا يوجد":
        intro = f"تمت مراجعة الشارت مع صور النماذج المرجعية، والنموذج الأقرب هو: {pattern_name}."
        rule_text = reference_rule or evidence or "يُقبل النموذج فقط عندما ترتبط نقاطه بقمم وقيعان حقيقية على M5."
        arrow_text = (
            "السهم المتصل يوضح مسار النموذج بعد التأكيد، وخط الإلغاء يبين موضع بطلان النموذج."
            if pattern_status == "confirmed"
            else "السهم المتقطع يوضح السيناريو المتوقع للنموذج المرشح؛ لا يصبح مؤكدًا إلا عند تحقق شرط الكسر أو التفعيل."
        )
    else:
        intro = "تمت مراجعة الشارت مع ذاكرة النماذج والسيناريوهات المرجعية، ولم توجد مطابقة هندسية كافية للرسم."
        rule_text = "لا يُرسم سيناريو تقريبي ولا تُختلق نقاط أو خطوط إذا لم تثبت المطابقة على شموع M5 الحقيقية."
        arrow_text = "عند غياب سيناريو صالح لا يظهر سهم توقع؛ يبقى الشارت الأصلي نظيفًا."

    mechanism = "آلية التطبيق: لكل شارت جديد تُراجع الذاكرة المرجعية، ثم يُرسم السيناريو الأقرب فقط بعد تثبيت مكوناته هندسيًا على الشارت."
    if reference_id and str(os.environ.get("SALEEM_DEBUG_OVERLAY", "")).lower() in {"1", "true", "yes"}:
        draw.text((pad + 28, rule_y1 + 38), f"SOURCE  {reference_id}", font=f_rule_latin, fill=(80, 100, 125, 255), anchor="la")
    text_right = canvas_w - pad - 28
    text_width = canvas_w - pad * 2 - 56
    y_cursor = rule_y1 + 76
    for text, font_obj, fill, max_lines in (
        (intro, f_rule_bold, (29, 44, 62, 255), 2),
        ("القاعدة: " + rule_text, f_rule, (46, 60, 78, 255), 2),
        (arrow_text, f_rule, (72, 83, 98, 255), 1),
        (mechanism, f_rule_bold, (29, 79, 134, 255), 1),
    ):
        lines = _wrap_text_by_width(draw, text, font_obj, text_width, rtl=True, max_lines=max_lines)
        for line in lines:
            _draw_rtl(draw, (text_right, y_cursor), line, font_obj, fill, anchor="ra")
            y_cursor += 29
        y_cursor += 3

    # Bottom action row changes with the current state.
    bottom_y1 = rule_y2 + pad
    bottom_y2 = bottom_y1 + bottom_h
    draw.rounded_rectangle((pad, bottom_y1, canvas_w - pad, bottom_y2), radius=20, fill=(5, 18, 33, 255), outline=(39, 60, 82, 255), width=1)

    bottom_items: list[tuple[str, str, tuple[int, int, int, int]]] = []
    if zone.get("active"):
        up = _number(zone.get("up_trigger")); down = _number(zone.get("down_trigger"))
        bottom_items = [
            ("القرار الآن", "لا دخول داخل المنطقة", BLUE),
            ("تفعيل صعود", f"> {_fmt_axis_price(up)}" if up is not None else "—", GREEN),
            ("تفعيل هبوط", f"< {_fmt_axis_price(down)}" if down is not None else "—", RED),
            ("القاعدة", "إغلاق M5 خارج المنطقة", GOLD),
        ]
    elif confirmed:
        entry = _number(analysis.get("entry")); stop = _number(analysis.get("stop_loss")); tp1 = _number(analysis.get("target_1")); tp2 = _number(analysis.get("target_2"))
        bottom_items = [
            ("Entry", _fmt_axis_price(entry) if entry is not None else "—", ENTRY_CARD),
            ("Stop", _fmt_axis_price(stop) if stop is not None else "—", STOP_CARD),
            ("TP1", _fmt_axis_price(tp1) if tp1 is not None else "—", TP1_CARD),
            ("TP2", _fmt_axis_price(tp2) if tp2 is not None else "—", TP2_CARD),
        ]
    else:
        buy = analysis.get("buy_scenario_details") if isinstance(analysis.get("buy_scenario_details"), dict) else {}
        sell = analysis.get("sell_scenario_details") if isinstance(analysis.get("sell_scenario_details"), dict) else {}
        buy_trigger = _number(buy.get("trigger_price")); sell_trigger = _number(sell.get("trigger_price")); current = _number(analysis.get("current_price"))
        bottom_items = [
            ("السعر الآن", _fmt_axis_price(current) if current is not None else "—", WHITE),
            ("شراء بعد", f"> {_fmt_axis_price(buy_trigger)}" if buy_trigger is not None else "—", GREEN),
            ("بيع بعد", f"< {_fmt_axis_price(sell_trigger)}" if sell_trigger is not None else "—", RED),
            ("الحالة", str(action.get("badge") or "مراقبة"), accent),
        ]

    inner_pad = 16
    bx1, bx2 = pad + inner_pad, canvas_w - pad - inner_pad
    gap = 12
    card_w = (bx2 - bx1 - gap * 3) // 4
    card_top = bottom_y1 + 24
    card_bottom = bottom_y2 - 24
    for i, (label, value, color) in enumerate(bottom_items[:4]):
        x1 = bx1 + i * (card_w + gap)
        x2 = x1 + card_w
        draw.rounded_rectangle((x1, card_top, x2, card_bottom), radius=14, fill=(10, 28, 47, 255), outline=(48, 70, 93, 220), width=1)
        if any("\u0600" <= ch <= "\u06ff" for ch in label):
            _draw_rtl(draw, (x2 - 14, card_top + 24), label, f_card_label, (151, 169, 194, 255), anchor="ra")
        else:
            draw.text((x2 - 14, card_top + 24), label, font=f_card_label, fill=(151, 169, 194, 255), anchor="ra")
        if any("\u0600" <= ch <= "\u06ff" for ch in value):
            fitted = _fit_text(draw, value, f_card_value, card_w - 28, rtl=True)
            _draw_rtl(draw, (x2 - 14, card_bottom - 26), fitted, f_card_value, color, anchor="ra")
        else:
            draw.text((x2 - 14, card_bottom - 26), value, font=f_card_value_latin, fill=color, anchor="rs")

    footer_y = bottom_y2 + 28
    _draw_rtl(draw, (canvas_w - pad, footer_y), "تحليل فني تعليمي، وليس توصية استثمارية.", f_small, (145, 163, 187, 255), anchor="ra")
    draw.text((pad, footer_y), "SaleeM v7.9", font=f_small_latin, fill=(117, 137, 162, 255), anchor="la")

    out = io.BytesIO()
    image.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


def render_result(analysis: dict[str, Any], chart_background_path: str | os.PathLike[str] | None = None) -> bytes:
    """Render native landscape uploads or rebuild portrait uploads from OHLC."""
    if bool(analysis.get("reconstructed_market_chart")):
        return _render_reconstructed_market_chart(analysis, chart_background_path)
    return _render_uploaded_chart_with_overlays(analysis, chart_background_path)
