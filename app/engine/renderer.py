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
    trend_color = GREEN if direction == "صاعد" else RED
    if direction == "صاعد":
        draw.line((cards[3][0] + 32, card_y1 + 116, cards[3][0] + 50, card_y1 + 94, cards[3][0] + 66, card_y1 + 104, cards[3][0] + 85, card_y1 + 76), fill=trend_color, width=4)
        draw.polygon([(cards[3][0] + 85, card_y1 + 76), (cards[3][0] + 73, card_y1 + 79), (cards[3][0] + 83, card_y1 + 89)], fill=trend_color)
    else:
        draw.line((cards[3][0] + 32, card_y1 + 76, cards[3][0] + 50, card_y1 + 94, cards[3][0] + 66, card_y1 + 84, cards[3][0] + 85, card_y1 + 112), fill=trend_color, width=4)
        draw.polygon([(cards[3][0] + 85, card_y1 + 112), (cards[3][0] + 73, card_y1 + 109), (cards[3][0] + 83, card_y1 + 99)], fill=trend_color)
    draw.text((cards[3][2] - 18, card_y1 + 106), _fmt_price(current), font=F_CARD, fill=trend_color, anchor="rm")

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


def _draw_market_zones(image: Image.Image, draw: ImageDraw.ImageDraw, analysis: dict[str, Any], candles: list[dict[str, Any]], slot: float, candle_right: int, price_min: float, price_max: float) -> None:
    left, top, right, bottom = CHART
    if not candles:
        return
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    trade_zone_left = max(candle_right - 8, int(left + (right - left) * 0.64))
    reference = float(candles[-1]["close"])
    entry = _number(analysis.get("entry"))
    focal_price = entry if entry is not None else reference

    raw_obs = _detect_order_blocks(candles)
    strong_threshold = 72
    order_blocks = []
    for zone in raw_obs:
        index, low, high, strength = zone
        if strength < strong_threshold:
            continue
        center = (low + high) / 2
        width_penalty = abs(high - low) * 2.4
        score = strength * 1.1 - abs(center - focal_price) * 2.2 - width_penalty
        order_blocks.append((score, zone))
    order_blocks.sort(key=lambda item: item[0], reverse=True)

    selected_obs: list[tuple[int, float, float, int]] = []
    for _, zone in order_blocks:
        _, low, high, _ = zone
        center = (low + high) / 2
        if all(abs(center - (z[1] + z[2]) / 2) > max(0.45, abs(z[2] - z[1]) * 0.65) for z in selected_obs):
            selected_obs.append(zone)
        if len(selected_obs) == 2:
            break
    selected_obs.sort(key=lambda item: (item[1] + item[2]) / 2, reverse=True)

    for index, low, high, strength in selected_obs:
        if high < price_min or low > price_max:
            continue
        x1 = max(left + 140, int(left + slot * max(0, index - 0.35)))
        x2 = min(trade_zone_left + 24, max(x1 + 168, int(left + slot * (index + 5.3))))
        y1, y2 = sorted((_price_y(high, price_min, price_max), _price_y(low, price_min, price_max)))
        if y2 - y1 < 24:
            mid = (y1 + y2) // 2
            y1, y2 = mid - 12, mid + 12
        alpha = 28 + max(0, min(44, (strength - strong_threshold) * 2))
        ld.rounded_rectangle((x1, y1, x2, y2), radius=6, fill=(49, 128, 255, alpha), outline=(86, 154, 255, 118), width=1)
        draw.text((x1 + 15, y1 + 14), "ORDER BLOCK", font=F_ZONE, fill=(72, 145, 255, 255), anchor="la")

    fvgs = []
    for zone in _detect_fvg(candles):
        index, low, high = zone
        center = (low + high) / 2
        distance = abs(center - focal_price)
        # نفضّل الفجوة الأقرب لمنطقة الدخول مع ترجيح ظهورها في النصف الأيمن من الشموع.
        right_bias = max(0, len(candles) - index) * 0.08
        score = -distance - right_bias
        fvgs.append((score, zone))
    fvgs.sort(key=lambda item: item[0], reverse=True)

    selected_fvgs: list[tuple[int, float, float]] = []
    for _, zone in fvgs:
        index, low, high = zone
        center = (low + high) / 2
        if all(abs(center - (z[1] + z[2]) / 2) > max(0.18, abs(z[2] - z[1]) * 0.8) for z in selected_fvgs):
            selected_fvgs.append(zone)
        if len(selected_fvgs) == 1:
            break

    for index, low, high in selected_fvgs:
        if high < price_min or low > price_max:
            continue
        y1, y2 = sorted((_price_y(high, price_min, price_max), _price_y(low, price_min, price_max)))
        if y2 - y1 < 18:
            center = (y1 + y2) // 2
            y1, y2 = center - 9, center + 9
        x2 = min(trade_zone_left - 10, max(left + 260, int(left + slot * (index + 2.2))))
        x1 = max(left + 170, x2 - 74)
        ld.rounded_rectangle((x1, y1, x2, y2), radius=4, fill=(244, 194, 91, 36), outline=(214, 155, 45, 148), width=1)
        draw.text((x1 - 12, (y1 + y2) // 2), "FVG", font=F_ZONE, fill=(235, 200, 124, 255), anchor="ra")

    image.alpha_composite(layer)


def _draw_levels(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    left, top, right, bottom = CHART
    level_specs = (("resistance_levels", PURPLE, "مقاومة"), ("support_levels", CYAN, "دعم"))
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
                price_rect = _rounded_label(draw, left - 34, y_label - 17, _fmt_price(price), F_LEVEL, fill=(58, 36, 86, 255), outline=color, text_fill=WHITE, rtl=False)
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
    zone_left = max(candle_right - 12, int(left + (right - left) * 0.64))
    zone_right = right - 2

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    if target_ys:
        far_target_y = target_ys[-1]
        ld.rectangle((zone_left, min(entry_y, far_target_y), zone_right, max(entry_y, far_target_y)), fill=(17, 183, 94, 52), outline=(17, 183, 94, 150), width=2)
    if stop_y is not None:
        ld.rectangle((zone_left, min(entry_y, stop_y), zone_right, max(entry_y, stop_y)), fill=(245, 63, 70, 48), outline=(245, 63, 70, 145), width=2)

    candle_ranges = [max(0.01, float(c["high"]) - float(c["low"])) for c in analysis.get("candles") or []]
    atr = median(candle_ranges) if candle_ranges else 1.0
    band = max(0.18, min(0.65, atr * 0.22))
    band_top = _price_y(entry + band, price_min, price_max)
    band_bottom = _price_y(entry - band, price_min, price_max)
    blend_top = min(band_top, band_bottom)
    blend_bottom = max(band_top, band_bottom)
    blend_mid = (blend_top + blend_bottom) // 2
    ld.rectangle((zone_left, blend_top, zone_right, blend_mid), fill=(245, 63, 70, 58))
    ld.rectangle((zone_left, blend_mid, zone_right, blend_bottom), fill=(17, 183, 94, 58))
    ld.rectangle((zone_left, blend_top, zone_right, blend_bottom), outline=(185, 193, 208, 165), width=1)
    image.alpha_composite(layer)

    draw.line((left, entry_y, zone_right, entry_y), fill=ORANGE, width=2)
    if stop_y is not None:
        _dash_line(draw, (zone_left, stop_y), (zone_right, stop_y), RED, width=1, dash=9, gap=7)
    for y in target_ys:
        _dash_line(draw, (zone_left, y), (zone_right, y), TEAL, width=1, dash=8, gap=7)

    label_items = [("entry", entry_y)]
    if stop_y is not None:
        label_items.append(("stop", stop_y))
    label_items.extend((f"tp{i}", y) for i, y in enumerate(target_ys, start=1))
    positions = _spaced_positions(label_items, min_gap=44)

    # دخول
    entry_label_rect = _rounded_label(draw, right - 74, positions["entry"] - 16, "دخول", F_TRADE_SMALL, fill=(181, 114, 18, 255), outline=ORANGE, text_fill=WHITE, align_right=True)
    entry_price_rect = _rounded_label(draw, right + 94, positions["entry"] - 16, _fmt_price(entry), F_TRADE_SMALL_LATIN, fill=(20, 28, 45, 245), outline=ORANGE, text_fill=WHITE, rtl=False, align_right=True)
    if abs(positions["entry"] - entry_y) > 3:
        draw.line((zone_right, entry_y, entry_label_rect[0], positions["entry"]), fill=ORANGE, width=1)

    # وقف
    if stop is not None and stop_y is not None:
        stop_label_rect = _rounded_label(draw, right - 74, positions["stop"] - 16, "وقف", F_TRADE_SMALL, fill=(177, 37, 44, 255), outline=RED, text_fill=WHITE, align_right=True)
        stop_price_rect = _rounded_label(draw, right + 94, positions["stop"] - 16, _fmt_price(stop), F_TRADE_SMALL_LATIN, fill=(20, 28, 45, 245), outline=RED, text_fill=WHITE, rtl=False, align_right=True)
        if abs(positions["stop"] - stop_y) > 3:
            draw.line((zone_right, stop_y, stop_label_rect[0], positions["stop"]), fill=RED, width=1)

    # الأهداف بأحجام أصغر وعلى اليمين.
    for i, (target, exact_y) in enumerate(zip(targets, target_ys), start=1):
        tag_x = right + 8
        tag_y = positions[f"tp{i}"] - 14
        tp_tag = _rounded_label(draw, tag_x, tag_y, f"TP{i}", F_TRADE_SMALL_LATIN, fill=(37, 112, 150, 255), outline=CYAN, text_fill=WHITE, rtl=False)
        price_rect = _rounded_label(draw, right + 94, tag_y, _fmt_price(target), F_TRADE_SMALL_LATIN, fill=(14, 32, 54, 250), outline=CYAN, text_fill=WHITE, rtl=False, align_right=True)
        if abs(positions[f"tp{i}"] - exact_y) > 3:
            draw.line((zone_right, exact_y, tp_tag[0], positions[f"tp{i}"]), fill=CYAN, width=1)

    # سهم أوضح على مسار الحركة.
    swing = 42 if direction == "هابط" else -42
    start = (zone_left + 28, entry_y)
    bend1 = (zone_left + 70, entry_y + swing)
    bend2 = (zone_left + 116, entry_y - swing // 2)
    end_y = target_ys[-1] if target_ys else (entry_y - 180 if direction == "صاعد" else entry_y + 180)
    end_y = max(top + 30, min(bottom - 30, end_y))
    end_x = zone_left + max(110, int((zone_right - zone_left) * 0.78))
    points = [start, bend1, bend2, (end_x, end_y)]
    shadow = [(x + 3, y + 3) for x, y in points]
    draw.line(shadow, fill=(0, 0, 0, 160), width=12, joint="curve")
    draw.line(points, fill=RED if direction == "هابط" else GREEN, width=9, joint="curve")
    angle = math.atan2(end_y - bend2[1], end_x - bend2[0])
    size = 28
    left_head = (end_x - size * math.cos(angle - math.pi / 6), end_y - size * math.sin(angle - math.pi / 6))
    right_head = (end_x - size * math.cos(angle + math.pi / 6), end_y - size * math.sin(angle + math.pi / 6))
    draw.polygon([(end_x + 2, end_y + 2), (left_head[0] + 2, left_head[1] + 2), (right_head[0] + 2, right_head[1] + 2)], fill=(0, 0, 0, 160))
    draw.polygon([(end_x, end_y), left_head, right_head], fill=RED if direction == "هابط" else GREEN)

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
        ("الجلسة الآسيوية", "17:00 - 01:00", (188, 130, 45, 255), (255, 248, 234, 255), "☀"),
        ("الجلسة الأوروبية", "13:00 - 17:00", BLUE, (242, 247, 255, 255), "☀"),
        ("الجلسة الأمريكية", "17:00 - 22:00", (126, 92, 235, 255), (246, 241, 255, 255), "☾"),
    ]
    for idx, (label, timing, color, fill, icon) in enumerate(sessions):
        x1 = left + idx * (box_w + gap)
        x2 = x1 + box_w
        draw.rounded_rectangle((x1, y1, x2, y2), radius=7, fill=fill, outline=color, width=1)
        draw.text((x1 + 20, y1 + 19), icon, font=F_SMALL_BOLD, fill=color, anchor="lm")
        _draw_rtl(draw, (x2 - 18, y1 + 10), label, F_SMALL_BOLD, color)
        draw.text(((x1 + x2) // 2, y1 + 33), timing, font=F_AXIS, fill=color, anchor="mm")

def _pattern_name(analysis: dict[str, Any]) -> str:
    name = str(analysis.get("pattern_type") or "لا يوجد")
    return {"قمتان": "نموذج M", "قاعان": "نموذج W"}.get(name, name)


def _note_row(draw: ImageDraw.ImageDraw, y: int, label: str, value: str, dot_color) -> None:
    left, top, right, bottom = NOTES
    mid_x = right - 235
    draw.line((left + 20, y + 46, right - 20, y + 46), fill=(45, 67, 102, 255), width=1)
    draw.line((mid_x, y - 2, mid_x, y + 46), fill=(40, 60, 92, 255), width=1)
    draw.ellipse((right - 45, y + 12, right - 31, y + 26), fill=dot_color)
    _draw_rtl(draw, (right - 66, y + 2), label, F_NOTE_BOLD, WHITE)
    max_width = mid_x - left - 45
    fitted = _fit_text(draw, value, F_NOTE_MIXED, max_width)
    draw.text((mid_x - 18, y + 2), fitted, font=F_NOTE_MIXED, fill=(232, 238, 249, 255), anchor="ra")

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
    pattern = _pattern_name(analysis)
    pattern_confidence = int(analysis.get("pattern_confidence") or 0)
    confirmation = str(analysis.get("confirmation") or "انتظار تأكيد شمعة خمس دقائق")
    stop = _number(analysis.get("stop_loss"))
    scenario = str(analysis.get("scenario") or analysis.get("note") or "مراقبة مستوى التفعيل")
    targets = [_number(analysis.get(key)) for key in ("target_1", "target_2", "target_3")]

    direction_value = f"{direction} - احتمال {probability}٪"
    pattern_value = f"{pattern} - ثقة {pattern_confidence}٪" if pattern != "لا يوجد" else "لا يوجد نموذج مكتمل"
    entry_value = confirmation
    stop_value = _fmt_price(stop) if stop is not None else "—"
    target_value = " | ".join(f"TP{i}: {_fmt_price(value)}" for i, value in enumerate(targets, start=1) if value is not None)

    rows = [
        ("الاتجاه:", direction_value, GREEN if direction == "صاعد" else RED),
        ("النمط:", pattern_value, BLUE),
        ("شرط الدخول:", entry_value, GREEN),
        ("وقف:", stop_value, RED),
        ("الأهداف:", target_value, GREEN),
        ("أقرب سيناريو:", scenario, ORANGE),
    ]
    draw.rounded_rectangle((left + 12, top + 82, right - 12, bottom - 28), radius=14, outline=(52, 77, 112, 255), width=1)
    y = top + 92
    for label, value, color in rows:
        _note_row(draw, y, label, value, color)
        y += 54

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
