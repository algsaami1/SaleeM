from __future__ import annotations

import io
import math
from datetime import datetime
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
BG = (248, 250, 253, 255)
WHITE = (255, 255, 255, 255)
NAVY = (15, 31, 67, 255)
TEXT = (24, 38, 66, 255)
MUTED = (104, 118, 143, 255)
BORDER = (224, 230, 239, 255)
GRID = (205, 214, 227, 115)
GREEN = (17, 183, 94, 255)
GREEN_DARK = (8, 130, 67, 255)
GREEN_FILL = (17, 183, 94, 38)
RED = (245, 63, 70, 255)
RED_DARK = (187, 30, 39, 255)
RED_FILL = (245, 63, 70, 36)
BLUE = (38, 117, 247, 255)
BLUE_FILL = (69, 139, 255, 22)
GOLD = (245, 158, 11, 255)
CREAM = (244, 194, 91, 30)
ORANGE = (249, 115, 22, 255)

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
    d.rounded_rectangle((x1, y1 + shadow, x2, y2 + shadow), radius=radius, fill=(31, 49, 84, 20))
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
    candles = analysis.get("candles") or []
    candle_values: list[float] = []
    for candle in candles:
        high = _number(candle.get("high"))
        low = _number(candle.get("low"))
        if high is not None and low is not None:
            candle_values.extend((high, low))

    trade_values = [
        _number(analysis.get(key))
        for key in ("entry", "stop_loss", "target_1", "target_2", "target_3", "current_price")
    ]
    level_values: list[float] = []
    for key in ("support_levels", "resistance_levels"):
        for level in analysis.get(key) or []:
            price = _number(level.get("price"))
            if price is not None:
                level_values.append(price)

    values = candle_values + [v for v in trade_values if v is not None] + level_values
    if not values:
        return 0.0, 1.0

    # تجاهل مستوى بعيد جدًا يمنع ضغط الشموع، مع الاحتفاظ بالصفقة الحالية.
    center = _number(analysis.get("current_price"))
    if center is None and candles:
        center = _number(candles[-1].get("close"))
    if center is not None and candle_values:
        ranges = [max(0.01, float(c["high"]) - float(c["low"])) for c in candles]
        atr = median(ranges) if ranges else 1.0
        max_distance = max(atr * 14, 8.0)
        nearby = [value for value in values if abs(value - center) <= max_distance]
        if len(nearby) >= max(6, len(candle_values) // 2):
            values = nearby

    low, high = min(values), max(values)
    spread = max(1.0, high - low)
    padding = max(0.65, spread * 0.07)
    return low - padding, high + padding


def _price_y(price: float, price_min: float, price_max: float) -> int:
    left, top, right, bottom = CHART
    ratio = (price_max - price) / max(0.0001, price_max - price_min)
    return int(top + max(0.0, min(1.0, ratio)) * (bottom - top))


def _draw_status(draw: ImageDraw.ImageDraw) -> None:
    draw.text((38, 29), "12:04", font=F_STATUS, fill=(10, 14, 24, 255), anchor="la")
    draw.text((975, 29), "5G", font=F_STATUS, fill=(10, 14, 24, 255), anchor="ra")
    # إشارة وبطارية مبسطة دون الاعتماد على رموز خطوط خاصة.
    for i, h in enumerate((7, 11, 15, 20)):
        draw.rounded_rectangle((894 + i * 10, 47 - h, 900 + i * 10, 47), radius=2, fill=(10, 14, 24, 255))
    draw.rounded_rectangle((992, 23, 1041, 47), radius=6, outline=(30, 35, 45, 255), width=2)
    draw.rectangle((1041, 30, 1046, 40), fill=(30, 35, 45, 255))
    draw.rectangle((996, 27, 1022, 43), fill=(30, 35, 45, 255))
    draw.ellipse((31, 79, 79, 127), fill=(225, 247, 235, 255))
    draw.line((46, 103, 56, 113), fill=GREEN, width=4)
    draw.line((56, 113, 68, 91), fill=GREEN, width=4)
    _draw_rtl(draw, (1019, 58), "اكتمال التحليل", F_SMALL_BOLD, GREEN)
    title_y = 84
    _draw_rtl(draw, (1019, title_y), "تحليل", F_TITLE, NAVY)
    arabic_width = _text_width(draw, "تحليل", F_TITLE)
    draw.text((1019 - arabic_width - 14, title_y), "SaleeM", font=F_TITLE_LATIN, fill=NAVY, anchor="ra")


def _draw_header(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    draw.rounded_rectangle(MAIN_CARD, radius=24, fill=WHITE, outline=BORDER, width=1)
    draw.text((540, 188), "SaleeM - XAUUSD - M5", font=F_HEADER, fill=NAVY, anchor="ma")

    card_y1, card_y2 = 230, 385
    gap = 12
    card_w = (984 - gap * 3) // 4
    x_positions = [40 + i * (card_w + gap) for i in range(4)]
    cards = [(x, card_y1, x + card_w, card_y2) for x in x_positions]

    for rect in cards:
        draw.rounded_rectangle(rect, radius=17, fill=(255, 255, 255, 255), outline=BORDER, width=1)

    latest = analysis.get("market_latest_candle_time") or analysis.get("market_data_fetched_at")
    update_time = _time_label(latest)
    count = len(analysis.get("candles") or [])
    current = _number(analysis.get("current_price"))

    # البطاقة الأولى: الأصل والرمز.
    _draw_rtl(draw, (cards[0][2] - 18, card_y1 + 31), "الأصل / الرمز", F_LABEL, TEXT)
    # أيقونة ذهب بسيطة.
    gx, gy = cards[0][0] + 26, card_y1 + 82
    for dx, dy in ((0, 20), (28, 20), (14, 0)):
        draw.polygon([(gx + dx, gy + dy + 16), (gx + dx + 14, gy + dy), (gx + dx + 35, gy + dy + 4), (gx + dx + 42, gy + dy + 22), (gx + dx + 10, gy + dy + 26)], fill=(247, 174, 25, 255), outline=(201, 126, 0, 255))
    draw.text((cards[0][2] - 18, card_y1 + 88), "XAUUSD", font=F_CARD_LATIN, fill=ORANGE, anchor="ra")
    draw.text((cards[0][2] - 18, card_y1 + 121), "(GOLD / USD)", font=F_STATUS, fill=ORANGE, anchor="ra")

    # وقت التحديث.
    _draw_rtl(draw, (cards[1][2] - 18, card_y1 + 31), "وقت آخر تحديث", F_LABEL, TEXT)
    draw.ellipse((cards[1][0] + 27, card_y1 + 25, cards[1][0] + 57, card_y1 + 55), outline=(118, 136, 165, 255), width=2)
    draw.line((cards[1][0] + 42, card_y1 + 31, cards[1][0] + 42, card_y1 + 41), fill=(118, 136, 165, 255), width=2)
    draw.line((cards[1][0] + 42, card_y1 + 41, cards[1][0] + 50, card_y1 + 45), fill=(118, 136, 165, 255), width=2)
    draw.text(((cards[1][0] + cards[1][2]) // 2, card_y1 + 106), update_time, font=F_CARD, fill=NAVY, anchor="mm")

    # عدد الشموع.
    _draw_rtl(draw, (cards[2][2] - 18, card_y1 + 31), "عدد الشموع", F_LABEL, TEXT)
    draw.text(((cards[2][0] + cards[2][2]) // 2, card_y1 + 106), _rtl(f"{count} شمعة"), font=F_CARD, fill=NAVY, anchor="mm")

    # السعر الحالي من الصورة.
    _draw_rtl(draw, (cards[3][2] - 18, card_y1 + 31), "السعر الحالي", F_LABEL, TEXT)
    draw.line((cards[3][0] + 32, card_y1 + 116, cards[3][0] + 50, card_y1 + 94, cards[3][0] + 66, card_y1 + 104, cards[3][0] + 85, card_y1 + 76), fill=GREEN, width=4)
    draw.polygon([(cards[3][0] + 85, card_y1 + 76), (cards[3][0] + 73, card_y1 + 79), (cards[3][0] + 83, card_y1 + 89)], fill=GREEN)
    draw.text((cards[3][2] - 18, card_y1 + 106), _fmt_price(current), font=F_CARD, fill=GREEN, anchor="rm")


def _draw_signal(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    direction = str(analysis.get("direction") or "صاعد")
    probability = int(analysis.get("trade_probability") or 50)
    color = GREEN if direction == "صاعد" else RED
    dark = GREEN_DARK if direction == "صاعد" else RED_DARK
    side = "BUY" if direction == "صاعد" else "SELL"

    x, y = 42, 410
    draw.rounded_rectangle((x, y, x + 138, y + 66), radius=12, fill=color)
    draw.text((x + 69, y + 33), side, font=F_BUY, fill=WHITE, anchor="mm")
    draw.rounded_rectangle((x + 128, y, x + 247, y + 66), radius=12, fill=WHITE, outline=color, width=2)
    draw.text((x + 188, y + 33), f"{probability}%", font=F_PERCENT, fill=color, anchor="mm")

    state = str(analysis.get("draw_mode") or "conditional")
    state_text = {"confirmed": "مؤكد", "conditional": "مشروط", "watch": "مراقبة"}.get(state, "مشروط")
    state_w = max(126, _text_width(draw, state_text, F_CARD, rtl=True) + 44)
    draw.rounded_rectangle((x + 273, y + 9, x + 273 + state_w, y + 57), radius=12, fill=WHITE, outline=color, width=2)
    draw.text((x + 273 + state_w // 2, y + 33), _rtl(state_text), font=F_CARD, fill=dark, anchor="mm")


def _draw_grid(draw: ImageDraw.ImageDraw, price_min: float, price_max: float) -> None:
    draw.rounded_rectangle(CHART_CARD, radius=21, fill=WHITE, outline=BORDER, width=1)
    left, top, right, bottom = CHART
    ticks = 11
    for index in range(ticks):
        y = int(top + index * (bottom - top) / (ticks - 1))
        draw.line((left, y, right, y), fill=GRID, width=1)
        price = price_max - index * (price_max - price_min) / (ticks - 1)
        draw.text((PRICE_AXIS_X, y), _fmt_price(price), font=F_AXIS, fill=TEXT, anchor="lm")
    for index in range(7):
        x = int(left + index * (right - left) / 6)
        draw.line((x, top, x, bottom), fill=GRID, width=1)
    draw.line((right, top, right, bottom), fill=(167, 179, 197, 200), width=1)


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


def _draw_market_zones(image: Image.Image, draw: ImageDraw.ImageDraw, candles: list[dict[str, Any]], slot: float, candle_right: int, price_min: float, price_max: float) -> None:
    left, top, right, bottom = CHART
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)

    for index, low, high, strength in _detect_order_blocks(candles):
        if high < price_min or low > price_max:
            continue
        x1 = int(left + slot * max(0, index - 0.5))
        x2 = min(right - 10, max(candle_right + 100, x1 + 250))
        y1, y2 = sorted((_price_y(high, price_min, price_max), _price_y(low, price_min, price_max)))
        alpha = 18 + max(0, min(34, (strength - 50) // 2))
        ld.rounded_rectangle((x1, y1, x2, y2), radius=5, fill=(49, 128, 255, alpha), outline=(49, 128, 255, 80), width=1)
        draw.text((x1 + 13, (y1 + y2) // 2), "ORDER BLOCK", font=F_ZONE, fill=BLUE, anchor="lm")

    for index, low, high in _detect_fvg(candles):
        if high < price_min or low > price_max:
            continue
        x1 = int(left + slot * max(0, index - 1.2))
        x2 = min(right - 15, max(candle_right + 20, x1 + 220))
        y1, y2 = sorted((_price_y(high, price_min, price_max), _price_y(low, price_min, price_max)))
        if y2 - y1 < 18:
            center = (y1 + y2) // 2
            y1, y2 = center - 9, center + 9
        ld.rounded_rectangle((x1, y1, x2, y2), radius=4, fill=CREAM, outline=(214, 155, 45, 105), width=1)
        draw.text(((x1 + x2) // 2, (y1 + y2) // 2), "FVG", font=F_ZONE, fill=(102, 73, 20, 255), anchor="mm")

    image.alpha_composite(layer)


def _draw_levels(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    left, top, right, bottom = CHART
    for key, color, name in (("resistance_levels", RED, "مقاومة"), ("support_levels", GREEN, "دعم")):
        levels = sorted(analysis.get(key) or [], key=lambda item: int(item.get("strength") or 0), reverse=True)[:2]
        for rank, level in enumerate(levels, start=1):
            price = _number(level.get("price"))
            if price is None or not (price_min <= price <= price_max):
                continue
            strength = int(level.get("strength") or 50)
            y = _price_y(price, price_min, price_max)
            draw.line((left, y, right - 18, y), fill=color, width=_strength_width(strength))
            if key == "resistance_levels":
                _rounded_label(draw, left - 34, y - 17, _fmt_price(price), F_LEVEL, fill=color, outline=color, text_fill=WHITE, rtl=False)
                _rounded_label(draw, left + 53, y - 17, f"{name} {rank}", F_LEVEL, fill=WHITE, outline=color, text_fill=TEXT)
                _rounded_label(draw, right + 94, y - 17, _fmt_price(price), F_TRADE_LATIN, fill=WHITE, outline=color, text_fill=color, rtl=False, align_right=True)
            else:
                _rounded_label(draw, left - 24, y - 17, f"{name} {_strength_name(strength)}  {_fmt_price(price)}", F_LEVEL, fill=WHITE, outline=color, text_fill=TEXT)


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
    mx = int(sx + (ex - sx) * 0.48)
    my = int(sy + (ey - sy) * 0.58)
    points = [(sx, sy), (mx, my), (ex, ey)]
    draw.line(points, fill=color, width=4, joint="curve")
    angle = math.atan2(ey - my, ex - mx)
    size = 23
    left = (ex - size * math.cos(angle - math.pi / 6), ey - size * math.sin(angle - math.pi / 6))
    right = (ex - size * math.cos(angle + math.pi / 6), ey - size * math.sin(angle + math.pi / 6))
    draw.polygon([(ex, ey), left, right], fill=color)


def _draw_trade(image: Image.Image, draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float, candle_right: int) -> None:
    left, top, right, bottom = CHART
    direction = str(analysis.get("direction") or "صاعد")
    color = GREEN if direction == "صاعد" else RED
    entry = _number(analysis.get("entry"))
    stop = _number(analysis.get("stop_loss"))
    targets = [_number(analysis.get(key)) for key in ("target_1", "target_2", "target_3")]
    targets = [value for value in targets if value is not None]
    if entry is None:
        return

    entry_y = _price_y(entry, price_min, price_max)
    stop_y = _price_y(stop, price_min, price_max) if stop is not None else None
    target_ys = [_price_y(target, price_min, price_max) for target in targets]
    zone_left = max(candle_right - 30, int(left + (right - left) * 0.58))

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    if target_ys:
        far_target_y = target_ys[-1]
        ld.rounded_rectangle((zone_left, min(entry_y, far_target_y), right, max(entry_y, far_target_y)), radius=5, fill=(17, 183, 94, 44), outline=(17, 183, 94, 145), width=2)
    if stop_y is not None:
        ld.rounded_rectangle((zone_left, min(entry_y, stop_y), right, max(entry_y, stop_y)), radius=5, fill=(245, 63, 70, 42), outline=(245, 63, 70, 135), width=2)

    # شريط دمج واضح حول الدخول يربط المنطقة الخضراء والحمراء.
    candle_ranges = [max(0.01, float(c["high"]) - float(c["low"])) for c in analysis.get("candles") or []]
    atr = median(candle_ranges) if candle_ranges else 1.0
    band = max(0.18, min(0.65, atr * 0.22))
    band_top = _price_y(entry + band, price_min, price_max)
    band_bottom = _price_y(entry - band, price_min, price_max)
    blend_top = min(band_top, band_bottom)
    blend_bottom = max(band_top, band_bottom)
    blend_mid = (blend_top + blend_bottom) // 2
    ld.rounded_rectangle((zone_left, blend_top, right, blend_mid), radius=5, fill=(245, 63, 70, 48))
    ld.rounded_rectangle((zone_left, blend_mid, right, blend_bottom), radius=5, fill=(17, 183, 94, 48))
    ld.rounded_rectangle((zone_left, blend_top, right, blend_bottom), radius=5, outline=(128, 140, 160, 150), width=1)
    image.alpha_composite(layer)

    _dash_line(draw, (left, entry_y), (right, entry_y), (113, 132, 161, 210), width=2)
    if stop_y is not None:
        _dash_line(draw, (zone_left, stop_y), (right, stop_y), RED, width=2)
    for y in target_ys:
        _dash_line(draw, (zone_left, y), (right, y), GREEN, width=2)

    label_items = [("entry", entry_y)]
    if stop_y is not None:
        label_items.append(("stop", stop_y))
    label_items.extend((f"tp{i}", y) for i, y in enumerate(target_ys, start=1))
    positions = _spaced_positions(label_items)

    entry_rect = _rounded_label(draw, right - 5, positions["entry"] - 18, "منطقة الدخول", F_TRADE, fill=(250, 251, 253, 255), outline=(140, 151, 169, 255), text_fill=TEXT, align_right=True)
    _rounded_label(draw, right + 95, positions["entry"] - 18, _fmt_price(entry), F_TRADE_LATIN, fill=(250, 251, 253, 255), outline=(140, 151, 169, 255), text_fill=TEXT, rtl=False, align_right=True)
    if abs(positions["entry"] - entry_y) > 3:
        draw.line((right, entry_y, entry_rect[0], positions["entry"]), fill=(130, 142, 159, 255), width=1)

    if stop is not None and stop_y is not None:
        _draw_rtl(draw, (right - 76, stop_y - 4), "وقف الخسارة", F_SMALL_BOLD, RED)
        _rounded_label(draw, right + 92, positions["stop"] - 18, _fmt_price(stop), F_TRADE_LATIN, fill=WHITE, outline=RED, text_fill=RED, rtl=False, align_right=True)

    for i, (target, exact_y) in enumerate(zip(targets, target_ys), start=1):
        _rounded_label(draw, right - 7, positions[f"tp{i}"] - 18, f"TP{i}:  {_fmt_price(target)}", F_TRADE_LATIN, fill=(250, 255, 252, 255), outline=GREEN, text_fill=GREEN_DARK, rtl=False, align_right=True)
        if abs(positions[f"tp{i}"] - exact_y) > 3:
            draw.line((right, exact_y, right - 12, positions[f"tp{i}"]), fill=GREEN, width=1)

    end_y = target_ys[-1] if target_ys else (entry_y - 180 if direction == "صاعد" else entry_y + 180)
    end_y = max(top + 35, min(bottom - 35, end_y))
    _draw_arrow(draw, (zone_left + 28, entry_y), (zone_left + 145, end_y), color)

    # خط البنية/إعادة الاختبار الرفيع.
    draw.line((zone_left - 42, min(bottom - 8, entry_y + 180), zone_left + 65, entry_y - 45), fill=BLUE, width=2)


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
    sessions = [
        ("Asian Session", "17:00 - 01:00", (237, 228, 197, 255), (255, 249, 234, 255)),
        ("London Session", "13:00 - 17:00", BLUE, (242, 247, 255, 255)),
        ("New York Session", "17:00 - 22:00", (126, 92, 235, 255), (246, 241, 255, 255)),
    ]
    for idx, (label, timing, color, fill) in enumerate(sessions):
        x1 = left + idx * (box_w + gap)
        x2 = x1 + box_w
        draw.rounded_rectangle((x1, y1, x2, y2), radius=7, fill=fill, outline=color, width=1)
        draw.text(((x1 + x2) // 2, y1 + 13), label, font=F_AXIS, fill=color, anchor="mm")
        draw.text(((x1 + x2) // 2, y1 + 31), timing, font=F_AXIS, fill=color, anchor="mm")


def _pattern_name(analysis: dict[str, Any]) -> str:
    name = str(analysis.get("pattern_type") or "لا يوجد")
    return {"قمتان": "نموذج M", "قاعان": "نموذج W"}.get(name, name)


def _note_row(draw: ImageDraw.ImageDraw, y: int, label: str, value: str, dot_color) -> None:
    left, top, right, bottom = NOTES
    draw.ellipse((right - 48, y + 8, right - 32, y + 24), fill=dot_color)
    _draw_rtl(draw, (right - 64, y + 1), label, F_NOTE_BOLD, WHITE)
    label_width = _text_width(draw, label, F_NOTE_BOLD)
    max_width = right - left - 280
    fitted = _fit_text(draw, value, F_NOTE_MIXED, max_width)
    _draw_rtl(draw, (right - 82 - label_width, y + 1), fitted, F_NOTE_MIXED, (232, 238, 249, 255))
    draw.line((left + 28, y + 48, right - 28, y + 48), fill=(56, 78, 114, 255), width=1)


def _draw_notes(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    left, top, right, bottom = NOTES
    note_fill = (8, 25, 58, 255)
    note_border = (224, 170, 52, 255)
    draw.rounded_rectangle(NOTES, radius=20, fill=note_fill, outline=note_border, width=2)
    _draw_rtl(draw, (right - 72, top + 38), "ملاحظات التحليل", F_NOTE_TITLE, (245, 184, 48, 255))
    # أيقونة clipboard مبسطة.
    draw.rounded_rectangle((right - 47, top + 20, right - 19, top + 53), radius=4, outline=note_border, width=2)
    draw.rounded_rectangle((right - 41, top + 15, right - 25, top + 24), radius=3, outline=note_border, width=2)
    draw.line((left + 24, top + 70, right - 24, top + 70), fill=note_border, width=1)

    direction = str(analysis.get("direction") or "غير واضح")
    probability = int(analysis.get("trade_probability") or 50)
    frame_directions = analysis.get("frame_directions") or {}
    arrows = {"صاعد": "↑", "هابط": "↓", "عرضي": "↔", "غير واضح": "?"}
    frame_text = " ".join(
        f"{frame} {arrows.get(str((frame_directions.get(frame) or {}).get('direction')), '?')}"
        for frame in ("M15", "H1", "H4")
        if isinstance(frame_directions, dict)
    )
    pattern = _pattern_name(analysis)
    pattern_confidence = int(analysis.get("pattern_confidence") or 0)
    entry = _number(analysis.get("entry"))
    stop = _number(analysis.get("stop_loss"))
    targets = [_number(analysis.get(key)) for key in ("target_1", "target_2", "target_3")]
    confirmation = str(analysis.get("confirmation") or "انتظار تأكيد شمعة خمس دقائق")
    stop_reason = str(analysis.get("stop_reason") or "خلف منطقة إبطال السيناريو")
    scenario = str(analysis.get("scenario") or analysis.get("note") or "مراقبة مستوى التفعيل")

    direction_value = f"{direction} - احتمال فني {probability}٪"
    if frame_text:
        direction_value += f"  |  {frame_text}"
    pattern_value = f"{pattern} - ثقة {pattern_confidence}٪" if pattern != "لا يوجد" else "لا يوجد نموذج مكتمل؛ الاعتماد على البنية والمستويات"
    entry_value = f"{_fmt_price(entry)} - {confirmation}" if entry is not None else confirmation
    stop_value = f"{_fmt_price(stop)} - {stop_reason}" if stop is not None else stop_reason
    target_value = " | ".join(f"TP{i}: {_fmt_price(value)}" for i, value in enumerate(targets, start=1) if value is not None)

    rows = [
        ("الاتجاه:", direction_value, GREEN if direction == "صاعد" else RED),
        ("النمط:", pattern_value, BLUE),
        ("شرط الدخول:", entry_value, GREEN),
        ("وقف الخسارة:", stop_value, RED),
        ("الأهداف:", target_value, GREEN),
        ("أقرب سيناريو:", scenario, ORANGE),
    ]
    y = top + 83
    for label, value, color in rows:
        _note_row(draw, y, label, value, color)
        y += 52

    _draw_rtl(draw, (right - 28, bottom - 28), "هذا التحليل لأغراض تعليمية فقط. يرجى إدارة المخاطر قبل الدخول في أي صفقة.", F_DISCLAIMER, (214, 221, 234, 255))


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
    _draw_market_zones(image, draw, candles, slot, candle_right, price_min, price_max)
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
