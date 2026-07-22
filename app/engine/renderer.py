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

MAIN_CARD = (24, 150, 1056, 1868)
CHART_CARD = (36, 500, 1044, 1352)
CHART = (72, 552, 922, 1222)
PRICE_AXIS_X = 946
NOTES = (36, 1370, 1044, 1848)

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
    price_min = anchor - below - edge_padding
    price_max = anchor + above + edge_padding

    if price_max <= price_min:
        return anchor - 1.0, anchor + 1.0
    return price_min, price_max

def _price_y(price: float, price_min: float, price_max: float) -> int:
    left, top, right, bottom = CHART
    ratio = (price_max - price) / max(0.0001, price_max - price_min)
    return int(top + max(0.0, min(1.0, ratio)) * (bottom - top))


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


def _draw_grid(draw: ImageDraw.ImageDraw, price_min: float, price_max: float) -> None:
    draw.rounded_rectangle(CHART_CARD, radius=21, fill=(6, 17, 40, 255), outline=BORDER, width=1)
    left, top, right, bottom = CHART

    # شريط مستقل لمحور السعر حتى تبقى الأرقام بعيدة عن ملصقات الصفقة.
    draw.rounded_rectangle((right + 8, top - 10, CHART_CARD[2] - 12, bottom + 10), radius=12, fill=(5, 15, 34, 255))
    _draw_rtl(draw, (CHART_CARD[2] - 26, top - 34), "محور السعر", F_SMALL, MUTED)
    draw.text((left, top - 34), "XAUUSD · M5", font=F_STATUS, fill=(208, 220, 240, 255), anchor="la")

    for price in _axis_values(price_min, price_max):
        y = _price_y(price, price_min, price_max)
        draw.line((left, y, right, y), fill=GRID, width=1)
        draw.text((PRICE_AXIS_X, y), _fmt_price(price), font=F_AXIS, fill=(194, 207, 229, 255), anchor="lm")

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

def _draw_current_price(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    current = _number(analysis.get("current_price"))
    if current is None or not (price_min <= current <= price_max):
        return
    left, top, right, bottom = CHART
    y = _price_y(current, price_min, price_max)
    draw.line((left, y, right, y), fill=(38, 201, 128, 145), width=1)
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
    if entry is None:
        return

    entry_y = _price_y(entry, price_min, price_max)
    stop_y = _price_y(stop, price_min, price_max) if stop is not None else None
    target_ys = [_price_y(target, price_min, price_max) for target in targets]
    zone_left = min(right - 190, max(candle_right + 12, int(left + (right - left) * 0.67)))
    zone_right = right - 8

    # منطقة التحليل المستقبلية أوسع، مع فصل واضح للربح والخسارة.
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    if target_ys:
        far_target_y = target_ys[-1]
        ld.rounded_rectangle(
            (zone_left, min(entry_y, far_target_y), zone_right, max(entry_y, far_target_y)),
            radius=7,
            fill=TP_GREEN_FILL,
            outline=(25, 211, 112, 150),
            width=2,
        )
    if stop_y is not None:
        ld.rounded_rectangle(
            (zone_left, min(entry_y, stop_y), zone_right, max(entry_y, stop_y)),
            radius=7,
            fill=RED_FILL,
            outline=(245, 63, 70, 150),
            width=2,
        )
    image.alpha_composite(layer)

    # خطوط الصفقة متصلة وتبدأ بعد آخر شمعة فقط.
    draw.line((zone_left, entry_y, zone_right, entry_y), fill=ORANGE, width=2)
    if stop_y is not None:
        draw.line((zone_left, stop_y, zone_right, stop_y), fill=RED, width=2)
    for y in target_ys:
        draw.line((zone_left, y, zone_right, y), fill=TP_GREEN, width=2)

    label_items = [("entry", entry_y)]
    if stop_y is not None:
        label_items.append(("stop", stop_y))
    label_items.extend((f"tp{i}", y) for i, y in enumerate(target_ys, start=1))
    positions = _spaced_positions(label_items, min_gap=37)

    labels: list[tuple[str, int, int, str, Any, bool]] = [
        ("entry", entry_y, positions["entry"], f"دخول | {_fmt_price(entry)}", ORANGE, True),
    ]
    if stop is not None and stop_y is not None:
        labels.append(("stop", stop_y, positions["stop"], f"وقف | {_fmt_price(stop)}", RED, True))
    for index, (target, exact_y) in enumerate(zip(targets, target_ys), start=1):
        labels.append((f"tp{index}", exact_y, positions[f"tp{index}"], f"TP{index} | {_fmt_price(target)}", TP_GREEN, False))

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
        rect = _rounded_label(
            draw,
            zone_right - 5,
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

    # السهم يتبع اتجاه التحليل الحقيقي ولا يكون صاعدًا افتراضيًا.
    if target_ys:
        end_y = target_ys[-1]
    else:
        end_y = entry_y - 120 if direction == "صاعد" else entry_y + 120
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


def render_result(analysis: dict[str, Any]) -> bytes:
    image = Image.new("RGBA", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    _draw_status(draw)
    _shadow_card(image, MAIN_CARD, 24, 6)
    draw = ImageDraw.Draw(image)
    _draw_header(draw, analysis)
    _draw_signal(draw, analysis)

    candles = analysis.get("candles") or []
    price_min, price_max = _price_range(analysis)
    _draw_grid(draw, price_min, price_max)
    count = max(1, len(candles))
    candle_right = int(CHART[0] + (CHART[2] - CHART[0]) * 0.68)
    slot = (candle_right - CHART[0]) / count
    _draw_market_zones(image, draw, analysis, candles, slot, candle_right, price_min, price_max)
    draw = ImageDraw.Draw(image)
    _draw_candles(draw, candles, price_min, price_max)
    _draw_current_price(draw, analysis, price_min, price_max)
    _draw_levels(draw, analysis, price_min, price_max)
    _draw_trade(image, draw, analysis, price_min, price_max, candle_right)
    draw = ImageDraw.Draw(image)
    _draw_sessions(draw, candles, slot, str(analysis.get("market_timezone") or "Asia/Muscat"))
    _draw_notes(draw, analysis)

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()
