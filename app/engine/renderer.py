from __future__ import annotations

import io
import math
import os
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Iterable

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
GRID = (82, 102, 138, 78)
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
PURPLE = (202, 117, 255, 255)
PURPLE_FILL = (161, 92, 245, 40)
CYAN = (51, 198, 255, 255)
CYAN_DARK = (20, 118, 160, 255)
TEAL = (60, 216, 196, 255)

MAIN_CARD = (24, 150, 1056, 1868)
CHART_CARD = (40, 505, 1040, 1320)
CHART = (72, 555, 912, 1194)
PRICE_AXIS_X = 934
NOTES = (40, 1338, 1040, 1844)

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
        return 8
    if strength >= 70:
        return 6
    return 4


def _strength_name(strength: int) -> str:
    if strength >= 85:
        return "قوية جدًا"
    if strength >= 70:
        return "قوية"
    return "متوسطة"


def _price_range(analysis: dict[str, Any]) -> tuple[float, float]:
    """حساب نطاق سعري متكيف للشارت المعاد رسمه.

    يعتمد على شموع السوق بعد مواءمتها مع سعر الصورة، وعلى السعر الحالي وأعلى
    وأدنى سعر ظاهرين في الصورة. في الصفقة النشطة نمنح جهة الهدف الخضراء
    مساحة أكبر من جهة الوقف، ثم نضيف هامشًا واضحًا أعلى وأسفل المحور.
    """
    candles = analysis.get("candles") or []
    candle_values: list[float] = []
    candle_ranges: list[float] = []
    for candle in candles:
        high = _number(candle.get("high"))
        low = _number(candle.get("low"))
        if high is not None and low is not None:
            candle_values.extend((high, low))
            candle_ranges.append(max(0.01, high - low))

    draw_mode = str(analysis.get("draw_mode") or "watch")
    trade_keys = (
        ("current_price",)
        if draw_mode == "watch"
        else ("entry", "stop_loss", "target_1", "target_2", "target_3", "current_price")
    )
    trade_values = [_number(analysis.get(key)) for key in trade_keys]
    trade_values = [value for value in trade_values if value is not None]

    # حدود الصورة المرفوعة جزء أساسي من المعايرة، وليست مجرد مستويات اختيارية.
    image_high = _number(analysis.get("image_price_high"))
    image_low = _number(analysis.get("image_price_low"))
    image_values = [value for value in (image_high, image_low) if value is not None]

    level_values: list[float] = []
    for key in ("support_levels", "resistance_levels"):
        for level in analysis.get(key) or []:
            price = _number(level.get("price"))
            if price is not None:
                level_values.append(price)

    mandatory_values = candle_values + trade_values + image_values
    if not mandatory_values:
        return 0.0, 1.0

    center = _number(analysis.get("entry")) if draw_mode != "watch" else None
    if center is None:
        center = _number(analysis.get("current_price"))
    if center is None and candles:
        center = _number(candles[-1].get("close"))

    # مستويات بعيدة جدًا لا تضغط الشموع، لكن الشموع والصفقة وحدود الصورة تبقى دائمًا.
    optional_levels = level_values
    if center is not None and candle_ranges:
        atr = median(candle_ranges)
        far_trade = max((abs(value - center) for value in trade_values), default=0.0)
        max_distance = max(atr * 18, far_trade * 1.35, 10.0)
        optional_levels = [value for value in level_values if abs(value - center) <= max_distance]

    values = mandatory_values + optional_levels
    raw_low, raw_high = min(values), max(values)
    raw_span = max(1.0, raw_high - raw_low)

    direction = str(analysis.get("analysis_direction") or analysis.get("direction") or "غير واضح")
    active_trade = draw_mode != "watch" and direction in {"صاعد", "هابط"} and center is not None
    if not active_trade:
        padding = max(0.75, raw_span * 0.09)
        return raw_low - padding, raw_high + padding

    # لا نقص أي عنصر؛ نوسع فقط جهة الربح حتى تكون هي المساحة الأكبر بصريًا.
    above = max(0.0, raw_high - center)
    below = max(0.0, center - raw_low)
    minimum_side = max(0.55, raw_span * 0.12)
    above = max(above, minimum_side)
    below = max(below, minimum_side)
    green_to_red_ratio = 1.28

    if direction == "صاعد":
        above = max(above, below * green_to_red_ratio)
    else:
        below = max(below, above * green_to_red_ratio)

    balanced_span = max(1.0, above + below)
    edge_padding = max(0.70, balanced_span * 0.075)
    green_extra = max(0.35, balanced_span * 0.055)

    price_max = center + above + edge_padding
    price_min = center - below - edge_padding
    if direction == "صاعد":
        price_max += green_extra
    else:
        price_min -= green_extra

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

    latest = analysis.get("market_latest_candle_time") or analysis.get("market_data_fetched_at")
    update_time = _time_label(latest)
    count = len(analysis.get("candles") or [])
    current = _number(analysis.get("current_price"))
    direction = str(analysis.get("direction") or "غير واضح")

    # البطاقة الأولى: الأصل والرمز.
    _draw_rtl(draw, (cards[0][2] - 18, card_y1 + 31), "الأصل والرمز", F_LABEL, (205, 217, 236, 255))
    gx, gy = cards[0][0] + 26, card_y1 + 82
    for dx, dy in ((0, 20), (28, 20), (14, 0)):
        draw.polygon([(gx + dx, gy + dy + 16), (gx + dx + 14, gy + dy), (gx + dx + 35, gy + dy + 4), (gx + dx + 42, gy + dy + 22), (gx + dx + 10, gy + dy + 26)], fill=(247, 174, 25, 255), outline=(201, 126, 0, 255))
    draw.text((cards[0][2] - 18, card_y1 + 88), "XAUUSD", font=F_CARD_LATIN, fill=ORANGE, anchor="ra")
    draw.text((cards[0][2] - 18, card_y1 + 121), "(GOLD / USD)", font=F_STATUS, fill=ORANGE, anchor="ra")

    # وقت التحديث.
    _draw_rtl(draw, (cards[1][2] - 18, card_y1 + 31), "وقت آخر تحديث", F_LABEL, (205, 217, 236, 255))
    draw.ellipse((cards[1][0] + 27, card_y1 + 25, cards[1][0] + 57, card_y1 + 55), outline=(210, 220, 240, 255), width=2)
    draw.line((cards[1][0] + 42, card_y1 + 31, cards[1][0] + 42, card_y1 + 41), fill=(210, 220, 240, 255), width=2)
    draw.line((cards[1][0] + 42, card_y1 + 41, cards[1][0] + 50, card_y1 + 45), fill=(210, 220, 240, 255), width=2)
    draw.text(((cards[1][0] + cards[1][2]) // 2, card_y1 + 106), update_time, font=F_CARD, fill=WHITE, anchor="mm")

    # عدد الشموع.
    _draw_rtl(draw, (cards[2][2] - 18, card_y1 + 31), "عدد الشموع", F_LABEL, (205, 217, 236, 255))
    draw.text(((cards[2][0] + cards[2][2]) // 2, card_y1 + 106), _rtl(f"{count} شمعة"), font=F_CARD, fill=WHITE, anchor="mm")

    # السعر الحالي من الصورة.
    _draw_rtl(draw, (cards[3][2] - 18, card_y1 + 31), "السعر الحالي", F_LABEL, (205, 217, 236, 255))
    trend_color = GREEN if direction == "صاعد" else (RED if direction == "هابط" else GOLD)
    if direction == "صاعد":
        draw.line((cards[3][0] + 32, card_y1 + 116, cards[3][0] + 50, card_y1 + 94, cards[3][0] + 66, card_y1 + 104, cards[3][0] + 85, card_y1 + 76), fill=trend_color, width=4)
        draw.polygon([(cards[3][0] + 85, card_y1 + 76), (cards[3][0] + 73, card_y1 + 79), (cards[3][0] + 83, card_y1 + 89)], fill=trend_color)
    elif direction == "هابط":
        draw.line((cards[3][0] + 32, card_y1 + 76, cards[3][0] + 50, card_y1 + 94, cards[3][0] + 66, card_y1 + 84, cards[3][0] + 85, card_y1 + 112), fill=trend_color, width=4)
        draw.polygon([(cards[3][0] + 85, card_y1 + 112), (cards[3][0] + 73, card_y1 + 109), (cards[3][0] + 83, card_y1 + 99)], fill=trend_color)
    else:
        draw.line((cards[3][0] + 32, card_y1 + 96, cards[3][0] + 85, card_y1 + 96), fill=trend_color, width=4)
        draw.polygon([(cards[3][0] + 85, card_y1 + 96), (cards[3][0] + 73, card_y1 + 89), (cards[3][0] + 73, card_y1 + 103)], fill=trend_color)
    draw.text((cards[3][2] - 18, card_y1 + 106), _fmt_price(current), font=F_CARD, fill=trend_color, anchor="rm")

def _draw_signal(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    direction = str(analysis.get("direction") or "غير واضح")
    state = str(analysis.get("draw_mode") or "watch")
    probability = int(analysis.get("trade_probability") or 50)

    if state == "watch" or direction not in {"صاعد", "هابط"}:
        color = GOLD
        dark = (163, 101, 0, 255)
        side = "WATCH"
    elif direction == "صاعد":
        color = GREEN
        dark = GREEN_DARK
        side = "BUY"
    else:
        color = RED
        dark = RED_DARK
        side = "SELL"

    x, y = 42, 410
    side_width = 166 if side == "WATCH" else 138
    draw.rounded_rectangle((x, y, x + side_width, y + 66), radius=12, fill=color)
    draw.text((x + side_width // 2, y + 33), side, font=F_BUY if side != "WATCH" else F_PERCENT, fill=WHITE, anchor="mm")
    percent_x = x + side_width - 10
    draw.rounded_rectangle((percent_x, y, percent_x + 119, y + 66), radius=12, fill=WHITE, outline=color, width=2)
    draw.text((percent_x + 60, y + 33), f"{probability}%", font=F_PERCENT, fill=color, anchor="mm")

    state_text = {"confirmed": "مؤكد", "conditional": "مشروط", "watch": "مراقبة"}.get(state, "مراقبة")
    state_w = max(126, _text_width(draw, state_text, F_CARD, rtl=True) + 44)
    state_x = percent_x + 145
    draw.rounded_rectangle((state_x, y + 9, state_x + state_w, y + 57), radius=12, fill=WHITE, outline=color, width=2)
    draw.text((state_x + state_w // 2, y + 33), _rtl(state_text), font=F_CARD, fill=dark, anchor="mm")

def _draw_grid(draw: ImageDraw.ImageDraw, price_min: float, price_max: float) -> None:
    draw.rounded_rectangle(CHART_CARD, radius=21, fill=(6, 17, 40, 255), outline=BORDER, width=1)
    left, top, right, bottom = CHART
    ticks = 11
    for index in range(ticks):
        y = int(top + index * (bottom - top) / (ticks - 1))
        draw.line((left, y, right, y), fill=GRID, width=1)
        price = price_max - index * (price_max - price_min) / (ticks - 1)
        draw.text((PRICE_AXIS_X, y), _fmt_price(price), font=F_AXIS, fill=(205, 217, 236, 255), anchor="lm")
    for index in range(7):
        x = int(left + index * (right - left) / 6)
        draw.line((x, top, x, bottom), fill=GRID, width=1)
    draw.line((right, top, right, bottom), fill=(95, 110, 145, 200), width=1)


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

    label_count = min(7, count)
    indexes = sorted(set(round(i * (count - 1) / max(1, label_count - 1)) for i in range(label_count)))
    for index in indexes:
        x = int(left + slot * (index + 0.5))
        draw.text((x, bottom + 64), _time_label(candles[index].get("time")), font=F_AXIS, fill=TEXT, anchor="ma")
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
    level_specs = (("resistance_levels", ORANGE, "مقاومة"), ("support_levels", CYAN, "دعم"))
    for key, color, name in level_specs:
        levels = sorted(analysis.get(key) or [], key=lambda item: int(item.get("strength") or 0), reverse=True)[:2]
        valid: list[tuple[int, dict[str, Any], float, int]] = []
        for rank, level in enumerate(levels, start=1):
            price = _number(level.get("price"))
            if price is None or not (price_min <= price <= price_max):
                continue
            valid.append((rank, level, price, _price_y(price, price_min, price_max)))
        positions = _spaced_positions([(f"{key}-{rank}", y) for rank, _, _, y in valid], min_gap=40)
        for rank, level, price, y in valid:
            strength = int(level.get("strength") or 50)
            y_label = positions.get(f"{key}-{rank}", y)
            draw.line((left, y, right - 18, y), fill=color, width=_strength_width(strength))
            if key == "resistance_levels":
                price_rect = _rounded_label(draw, left - 34, y_label - 17, _fmt_price(price), F_LEVEL, fill=(82, 47, 12, 255), outline=color, text_fill=WHITE, rtl=False)
                name_rect = _rounded_label(draw, left + 53, y_label - 17, f"{name} {rank}", F_LEVEL, fill=(16, 24, 38, 255), outline=color, text_fill=WHITE)
                if abs(y_label - y) > 3:
                    draw.line((left + 8, y, price_rect[0] + 6, y_label), fill=color, width=1)
            else:
                support_rect = _rounded_label(draw, left - 24, y_label - 17, f"{name} {_strength_name(strength)}  {_fmt_price(price)}", F_LEVEL, fill=(16, 24, 38, 255), outline=color, text_fill=WHITE)
                if abs(y_label - y) > 3:
                    draw.line((left + 8, y, support_rect[0] + 8, y_label), fill=color, width=1)

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


def _draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color) -> None:
    sx, sy = start
    ex, ey = end
    mx = int(sx + (ex - sx) * 0.42)
    my = int(sy + (ey - sy) * 0.22)
    shadow = (0, 0, 0, 180)
    draw.line([(sx + 2, sy + 2), (mx + 2, my + 2), (ex + 2, ey + 2)], fill=shadow, width=7, joint="curve")
    draw.line([(sx, sy), (mx, my), (ex, ey)], fill=color, width=5, joint="curve")
    angle = math.atan2(ey - my, ex - mx)
    size = 25
    left = (ex - size * math.cos(angle - math.pi / 6), ey - size * math.sin(angle - math.pi / 6))
    right = (ex - size * math.cos(angle + math.pi / 6), ey - size * math.sin(angle + math.pi / 6))
    draw.polygon([(ex, ey), left, right], fill=shadow)
    draw.polygon([(ex, ey), left, right], fill=color)


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
    zone_left = max(candle_right - 12, int(left + (right - left) * 0.64))
    zone_right = right - 2

    # مناطق الوقف والهدف تلتقي عند خط الدخول بدون تداخل لوني.
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    if target_ys:
        far_target_y = target_ys[-1]
        ld.rectangle((zone_left, min(entry_y, far_target_y), zone_right, max(entry_y, far_target_y)), fill=(17, 183, 94, 50), outline=(17, 183, 94, 150), width=2)
    if stop_y is not None:
        ld.rectangle((zone_left, min(entry_y, stop_y), zone_right, max(entry_y, stop_y)), fill=(245, 63, 70, 46), outline=(245, 63, 70, 145), width=2)
    image.alpha_composite(layer)

    draw.line((left, entry_y, zone_right, entry_y), fill=ORANGE, width=2)
    if stop_y is not None:
        draw.line((zone_left, stop_y, zone_right, stop_y), fill=RED, width=1)
    # أحدث طلب: خطوط TP متصلة، نحيفة، وواضحة.
    for y in target_ys:
        draw.line((zone_left, y, zone_right, y), fill=TEAL, width=1)

    label_items = [("entry", entry_y)]
    if stop_y is not None:
        label_items.append(("stop", stop_y))
    label_items.extend((f"tp{i}", y) for i, y in enumerate(target_ys, start=1))
    positions = _spaced_positions(label_items, min_gap=42)

    entry_label_rect = _rounded_label(draw, right - 74, positions["entry"] - 16, "دخول", F_TRADE_SMALL, fill=(181, 114, 18, 255), outline=ORANGE, text_fill=WHITE, align_right=True)
    _rounded_label(draw, right + 94, positions["entry"] - 16, _fmt_price(entry), F_TRADE_SMALL_LATIN, fill=(20, 28, 45, 245), outline=ORANGE, text_fill=WHITE, rtl=False, align_right=True)
    if abs(positions["entry"] - entry_y) > 3:
        draw.line((zone_right, entry_y, entry_label_rect[0], positions["entry"]), fill=ORANGE, width=1)

    if stop is not None and stop_y is not None:
        stop_label_rect = _rounded_label(draw, right - 74, positions["stop"] - 16, "وقف", F_TRADE_SMALL, fill=(177, 37, 44, 255), outline=RED, text_fill=WHITE, align_right=True)
        _rounded_label(draw, right + 94, positions["stop"] - 16, _fmt_price(stop), F_TRADE_SMALL_LATIN, fill=(20, 28, 45, 245), outline=RED, text_fill=WHITE, rtl=False, align_right=True)
        if abs(positions["stop"] - stop_y) > 3:
            draw.line((zone_right, stop_y, stop_label_rect[0], positions["stop"]), fill=RED, width=1)

    for i, (target, exact_y) in enumerate(zip(targets, target_ys), start=1):
        tag_y = positions[f"tp{i}"] - 13
        tp_rect = _rounded_label(
            draw,
            right + 104,
            tag_y,
            f"TP{i}  {_fmt_price(target)}",
            F_TRADE_SMALL_LATIN,
            fill=(14, 45, 70, 250),
            outline=CYAN,
            text_fill=WHITE,
            rtl=False,
            align_right=True,
            padding_x=7,
            padding_y=4,
        )
        if abs(positions[f"tp{i}"] - exact_y) > 3:
            draw.line((zone_right, exact_y, tp_rect[0], positions[f"tp{i}"]), fill=CYAN, width=1)

    # سهم واضح يبدأ من الدخول، يقوم بإعادة اختبار صغيرة، ثم يتجه إلى TP3.
    retest_offset = -48 if direction == "هابط" else 48
    correction_offset = 38 if direction == "هابط" else -38
    start = (zone_left + 24, entry_y)
    bend1 = (zone_left + 72, entry_y + retest_offset)
    bend2 = (zone_left + 122, entry_y + correction_offset)
    end_y = target_ys[-1] if target_ys else (entry_y - 180 if direction == "صاعد" else entry_y + 180)
    end_y = max(top + 30, min(bottom - 30, end_y))
    end_x = min(zone_right - 22, zone_left + max(118, int((zone_right - zone_left) * 0.78)))
    points = [start, bend1, bend2, (end_x, end_y)]
    arrow_color = GREEN if direction == "صاعد" else RED
    shadow = [(x + 3, y + 3) for x, y in points]
    draw.line(shadow, fill=(0, 0, 0, 175), width=13, joint="curve")
    draw.line(points, fill=arrow_color, width=9, joint="curve")
    angle = math.atan2(end_y - bend2[1], end_x - bend2[0])
    size = 29
    left_head = (end_x - size * math.cos(angle - math.pi / 6), end_y - size * math.sin(angle - math.pi / 6))
    right_head = (end_x - size * math.cos(angle + math.pi / 6), end_y - size * math.sin(angle + math.pi / 6))
    draw.polygon([(end_x + 3, end_y + 3), (left_head[0] + 3, left_head[1] + 3), (right_head[0] + 3, right_head[1] + 3)], fill=(0, 0, 0, 175))
    draw.polygon([(end_x, end_y), left_head, right_head], fill=arrow_color)

def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    if len(text) >= 5 and text[2:3] == ":":
        try:
            return datetime(2000, 1, 1, int(text[:2]), int(text[3:5]))
        except ValueError:
            return None
    return None


def _draw_sessions(draw: ImageDraw.ImageDraw, candles: list[dict[str, Any]], slot: float) -> None:
    left, top, right, bottom = CHART
    y1, y2 = bottom + 18, bottom + 60
    gap = 10
    total_width = right - left
    box_w = int((total_width - gap * 2) / 3)

    # أوقات افتراضية بتوقيت عُمان، قابلة للتعديل من متغيرات Railway.
    def parse_range(name: str, default: str) -> tuple[int, int, str]:
        raw = os.getenv(name, default).strip()
        try:
            start_text, end_text = raw.split("-", 1)
            start = int(start_text.split(":", 1)[0]) % 24
            end = int(end_text.split(":", 1)[0]) % 24
            return start, end, raw
        except (ValueError, IndexError):
            start_text, end_text = default.split("-", 1)
            return int(start_text[:2]), int(end_text[:2]) % 24, default

    latest = _parse_dt(candles[-1].get("time")) if candles else None
    if latest is not None and latest.utcoffset() is not None:
        offset = int(os.getenv("SESSION_TIMEZONE_OFFSET", "4"))
        source_offset = latest.utcoffset().total_seconds() / 3600.0
        latest = (latest + timedelta(hours=offset - source_offset)).replace(tzinfo=None)
    current_hour = latest.hour if latest is not None else None

    def active(hour: int | None, start: int, end: int) -> bool:
        if hour is None:
            return False
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end

    asian = parse_range("ASIAN_SESSION", "04:00-12:00")
    london = parse_range("LONDON_SESSION", "11:00-19:00")
    new_york = parse_range("NEW_YORK_SESSION", "16:00-00:00")
    sessions = [
        ("الجلسة الآسيوية", asian, (188, 130, 45, 255), (255, 248, 234, 255)),
        ("الجلسة الأوروبية", london, BLUE, (242, 247, 255, 255)),
        ("الجلسة الأمريكية", new_york, (126, 92, 235, 255), (246, 241, 255, 255)),
    ]
    for idx, (label, (start, end, timing), color, fill) in enumerate(sessions):
        x1 = left + idx * (box_w + gap)
        x2 = x1 + box_w
        is_active = active(current_hour, start, end)
        border_width = 3 if is_active else 1
        draw.rounded_rectangle((x1, y1, x2, y2), radius=7, fill=fill, outline=color, width=border_width)
        _draw_rtl(draw, (x2 - 12, y1 + 8), label, F_SMALL, color)
        draw.text(((x1 + x2) // 2, y1 + 34), timing.replace("-", " - "), font=F_AXIS, fill=color, anchor="mm")
        if is_active:
            draw.ellipse((x1 + 10, y1 + 14, x1 + 20, y1 + 24), fill=color)

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
    _draw_levels(draw, analysis, price_min, price_max)
    _draw_trade(image, draw, analysis, price_min, price_max, candle_right)
    draw = ImageDraw.Draw(image)
    _draw_sessions(draw, candles, slot)
    _draw_notes(draw, analysis)

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()
