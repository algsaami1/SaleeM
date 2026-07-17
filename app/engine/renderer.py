from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:
    arabic_reshaper = None
    get_display = None

WIDTH = 1080
HEIGHT = 1920
BG = (5, 9, 15, 255)
PANEL = (10, 17, 27, 245)
GRID = (55, 68, 84, 90)
BORDER = (78, 92, 110, 150)
RED = (245, 62, 72, 255)
RED_FILL = (245, 62, 72, 48)
GREEN = (27, 207, 111, 255)
GREEN_FILL = (27, 207, 111, 48)
BLUE = (45, 139, 255, 255)
WHITE = (245, 248, 252, 255)
GRAY = (178, 190, 204, 255)
GOLD = (246, 187, 52, 255)
ORANGE = (255, 147, 42, 255)
BLACK_GLASS = (4, 8, 14, 220)

CHART = (72, 178, 920, 1320)
NOTES = (54, 1395, 1026, 1855)


def _rtl(text: str) -> str:
    if not text:
        return ""
    if arabic_reshaper is None or get_display is None:
        return text
    return get_display(arabic_reshaper.reshape(text))


def _font(size: int, bold: bool = False):
    root = Path(__file__).resolve().parents[2]
    names = [
        "NotoSansArabic-Bold.ttf" if bold else "NotoSansArabic-Regular.ttf",
        "NotoNaskhArabic-Bold.ttf" if bold else "NotoNaskhArabic-Regular.ttf",
    ]
    candidates = [root / "fonts" / name for name in names]
    candidates += [
        Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


TITLE_FONT = None
SUBTITLE_FONT = None
PRICE_FONT = None
LABEL_FONT = None
SMALL_FONT = None
NOTE_FONT = None
NOTE_BOLD = None


def _fonts() -> None:
    global TITLE_FONT, SUBTITLE_FONT, PRICE_FONT, LABEL_FONT, SMALL_FONT, NOTE_FONT, NOTE_BOLD
    if TITLE_FONT is None:
        TITLE_FONT = _font(38, bold=True)
        SUBTITLE_FONT = _font(25, bold=False)
        PRICE_FONT = _font(25, bold=True)
        LABEL_FONT = _font(23, bold=False)
        SMALL_FONT = _font(20, bold=False)
        NOTE_FONT = _font(25, bold=False)
        NOTE_BOLD = _font(27, bold=True)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, (int, float)) else None


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int, tuple[int, int, int, int]]:
    display = _rtl(text)
    box = draw.textbbox((0, 0), display, font=font)
    return box[2] - box[0], box[3] - box[1], box


def _draw_text_rtl(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font, fill=WHITE, anchor: str = "ra") -> None:
    draw.text(xy, _rtl(text), font=font, fill=fill, anchor=anchor)


def _rounded_label(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font,
    fill,
    outline,
    text_fill=WHITE,
    padding_x: int = 10,
    padding_y: int = 5,
    align_right: bool = False,
) -> tuple[int, int, int, int]:
    display = _rtl(text)
    box = draw.textbbox((0, 0), display, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    if align_right:
        x -= tw + padding_x * 2
    rect = (x, y, x + tw + padding_x * 2, y + th + padding_y * 2)
    draw.rounded_rectangle(rect, radius=8, fill=fill, outline=outline, width=1)
    draw.text((x + padding_x, y + padding_y - box[1]), display, font=font, fill=text_fill)
    return rect


def _dash_line(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color, width: int = 3, dash: int = 16, gap: int = 10) -> None:
    x1, y1 = start
    x2, y2 = end
    distance = math.hypot(x2 - x1, y2 - y1)
    if distance <= 0:
        return
    dx = (x2 - x1) / distance
    dy = (y2 - y1) / distance
    pos = 0.0
    while pos < distance:
        stop = min(distance, pos + dash)
        draw.line([(x1 + dx * pos, y1 + dy * pos), (x1 + dx * stop, y1 + dy * stop)], fill=color, width=width)
        pos += dash + gap


def _arrow(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], color, width: int = 8) -> None:
    if len(points) < 2:
        return
    draw.line(points, fill=color, width=width, joint="curve")
    p1, p2 = points[-2], points[-1]
    angle = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    size = 26
    left = (p2[0] - size * math.cos(angle - math.pi / 6), p2[1] - size * math.sin(angle - math.pi / 6))
    right = (p2[0] - size * math.cos(angle + math.pi / 6), p2[1] - size * math.sin(angle + math.pi / 6))
    draw.polygon([p2, left, right], fill=color)


def _strength_width(strength: int) -> int:
    if strength >= 85:
        return 8
    if strength >= 70:
        return 6
    return 4


def _price_range(analysis: dict[str, Any]) -> tuple[float, float]:
    values: list[float] = []
    for candle in analysis.get("candles") or []:
        values.extend([float(candle["high"]), float(candle["low"])])
    for key in ("entry", "stop_loss", "target_1", "target_2", "target_3"):
        value = _number(analysis.get(key))
        if value is not None:
            values.append(value)
    for key in ("support_levels", "resistance_levels"):
        for level in analysis.get(key) or []:
            price = _number(level.get("price"))
            if price is not None:
                values.append(price)
    if not values:
        return 0.0, 1.0
    low, high = min(values), max(values)
    spread = max(1.0, high - low)
    padding = spread * 0.08
    return low - padding, high + padding


def _price_y(price: float, price_min: float, price_max: float) -> int:
    left, top, right, bottom = CHART
    ratio = (price_max - price) / max(0.0001, price_max - price_min)
    return int(top + ratio * (bottom - top))


def _chart_point(point: Iterable[float]) -> tuple[int, int]:
    x, y = point
    left, top, right, bottom = CHART
    return (
        int(left + max(0.0, min(1.0, float(x))) * (right - left)),
        int(top + max(0.0, min(1.0, float(y))) * (bottom - top)),
    )


def _draw_header(draw: ImageDraw.ImageDraw) -> None:
    _draw_text_rtl(draw, (WIDTH - 54, 50), "تحليل الذهب", TITLE_FONT, GOLD)
    _draw_text_rtl(draw, (WIDTH - 54, 106), "فريم خمس دقائق، آخر ساعتين، أربع وعشرون شمعة", SUBTITLE_FONT, WHITE)
    draw.line((54, 148, WIDTH - 54, 148), fill=(GOLD[0], GOLD[1], GOLD[2], 130), width=2)


def _draw_grid(draw: ImageDraw.ImageDraw, price_min: float, price_max: float) -> None:
    left, top, right, bottom = CHART
    draw.rounded_rectangle((left - 12, top - 12, right + 104, bottom + 52), radius=18, fill=(7, 13, 22, 255), outline=BORDER, width=2)
    ticks = 9
    for index in range(ticks):
        y = int(top + index * (bottom - top) / (ticks - 1))
        draw.line((left, y, right, y), fill=GRID, width=1)
        price = price_max - index * (price_max - price_min) / (ticks - 1)
        draw.text((right + 16, y), f"{price:.2f}", font=SMALL_FONT, fill=GRAY, anchor="lm")
    for index in range(7):
        x = int(left + index * (right - left) / 6)
        draw.line((x, top, x, bottom), fill=GRID, width=1)


def _draw_candles(draw: ImageDraw.ImageDraw, candles: list[dict[str, Any]], price_min: float, price_max: float) -> None:
    left, top, right, bottom = CHART
    count = max(1, len(candles))
    slot = (right - left) / count
    body_width = max(9, int(slot * 0.48))
    for index, candle in enumerate(candles):
        x = int(left + slot * (index + 0.5))
        open_y = _price_y(float(candle["open"]), price_min, price_max)
        close_y = _price_y(float(candle["close"]), price_min, price_max)
        high_y = _price_y(float(candle["high"]), price_min, price_max)
        low_y = _price_y(float(candle["low"]), price_min, price_max)
        bullish = float(candle["close"]) >= float(candle["open"])
        color = GREEN if bullish else RED
        draw.line((x, high_y, x, low_y), fill=color, width=3)
        y1, y2 = sorted((open_y, close_y))
        if y2 - y1 < 3:
            y2 = y1 + 3
        draw.rectangle((x - body_width // 2, y1, x + body_width // 2, y2), fill=color, outline=color)

    for index in range(0, count, 4):
        x = int(left + slot * (index + 0.5))
        label = str(candles[index].get("time") or "")[:5]
        draw.text((x, bottom + 20), label, font=SMALL_FONT, fill=GRAY, anchor="ma")
    if count > 1 and (count - 1) % 4 != 0:
        x = int(left + slot * (count - 0.5))
        label = str(candles[-1].get("time") or "")[:5]
        draw.text((x, bottom + 20), label, font=SMALL_FONT, fill=GRAY, anchor="ma")


def _draw_levels(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
    left, top, right, bottom = CHART
    for kind, key, color, name in (
        ("support", "support_levels", GREEN, "دعم"),
        ("resistance", "resistance_levels", RED, "مقاومة"),
    ):
        for level in analysis.get(key) or []:
            price = _number(level.get("price"))
            if price is None or not (price_min <= price <= price_max):
                continue
            strength = int(level.get("strength") or 50)
            y = _price_y(price, price_min, price_max)
            width = _strength_width(strength)
            draw.line((left, y, right, y), fill=color, width=width)
            text = f"{name} {price:.2f}، قوة {strength} بالمئة"
            _rounded_label(draw, left + 8, y - 17, text, LABEL_FONT, BLACK_GLASS, color, padding_x=8, padding_y=3)


def _draw_pattern(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    confidence = int(analysis.get("pattern_confidence") or 0)
    if confidence < 60:
        return
    for line in analysis.get("pattern_lines") or []:
        if isinstance(line, list) and len(line) == 4:
            draw.line((_chart_point(line[:2]), _chart_point(line[2:])), fill=BLUE, width=5)
    path = [_chart_point(point) for point in analysis.get("pattern_path") or [] if isinstance(point, list) and len(point) == 2]
    if len(path) >= 2:
        draw.line(path, fill=WHITE, width=3, joint="curve")


def _draw_trade(draw: ImageDraw.ImageDraw, analysis: dict[str, Any], price_min: float, price_max: float) -> None:
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
    target_ys = [_price_y(value, price_min, price_max) for value in targets]
    zone_left = int(left + (right - left) * 0.63)

    if stop_y is not None:
        draw.rectangle((zone_left, min(entry_y, stop_y), right, max(entry_y, stop_y)), fill=RED_FILL)
        _dash_line(draw, (zone_left, stop_y), (right, stop_y), RED, width=3)
        _rounded_label(draw, right - 8, stop_y - 17, f"وقف {stop:.2f}", LABEL_FONT, BLACK_GLASS, RED, padding_x=8, padding_y=3, align_right=True)

    if target_ys:
        far_y = target_ys[-1]
        draw.rectangle((zone_left, min(entry_y, far_y), right, max(entry_y, far_y)), fill=GREEN_FILL)

    _dash_line(draw, (left, entry_y), (right, entry_y), color, width=4)
    entry_prefix = "دخول" if analysis.get("draw_mode") == "confirmed" else "دخول محتمل"
    _rounded_label(draw, right - 8, entry_y - 18, f"{entry_prefix} {entry:.2f}", PRICE_FONT, BLACK_GLASS, color, padding_x=9, padding_y=3, align_right=True)

    for index, (target, y) in enumerate(zip(targets, target_ys), start=1):
        _dash_line(draw, (zone_left, y), (right, y), GREEN, width=3)
        _rounded_label(draw, right - 8, y - 17, f"هدف {index}  {target:.2f}", LABEL_FONT, BLACK_GLASS, GREEN, padding_x=8, padding_y=3, align_right=True)

    end_y = target_ys[-1] if target_ys else (entry_y - 170 if direction == "صاعد" else entry_y + 170)
    arrow_x = int(left + (right - left) * 0.55)
    end_y = max(top + 20, min(bottom - 20, end_y))
    mid_y = int((entry_y + end_y) / 2)
    bend = -22 if direction == "صاعد" else 22
    _arrow(draw, [(arrow_x, entry_y), (arrow_x + bend, mid_y), (arrow_x + 10, end_y)], color, width=9)

    state = {"confirmed": "مؤكد", "conditional": "مشروط", "watch": "مراقبة"}.get(str(analysis.get("draw_mode")), "مشروط")
    side = str(analysis.get("trade_side") or ("شراء" if direction == "صاعد" else "بيع"))
    probability = int(analysis.get("trade_probability") or 50)
    _rounded_label(draw, left + 12, top + 12, f"{state}، {side}، احتمال فني {probability} بالمئة", LABEL_FONT, BLACK_GLASS, color, padding_x=10, padding_y=5)


def _pattern_name(analysis: dict[str, Any]) -> str:
    name = str(analysis.get("pattern_type") or "لا يوجد")
    if name == "قمتان":
        return "نموذج إم"
    if name == "قاعان":
        return "نموذج دبليو"
    return name


def _draw_notes(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    left, top, right, bottom = NOTES
    draw.rounded_rectangle(NOTES, radius=24, fill=PANEL, outline=(GOLD[0], GOLD[1], GOLD[2], 180), width=2)
    _draw_text_rtl(draw, (right - 30, top + 28), "ملاحظات مهمة", NOTE_BOLD, GOLD)
    draw.line((left + 28, top + 80, right - 28, top + 80), fill=(GOLD[0], GOLD[1], GOLD[2], 100), width=2)

    direction = str(analysis.get("direction") or "غير واضح")
    probability = int(analysis.get("trade_probability") or 50)
    pattern = _pattern_name(analysis)
    pattern_confidence = int(analysis.get("pattern_confidence") or 0)
    entry = _number(analysis.get("entry"))
    stop = _number(analysis.get("stop_loss"))
    targets = [_number(analysis.get(key)) for key in ("target_1", "target_2", "target_3")]
    confirmation = str(analysis.get("confirmation") or "انتظار تأكيد شمعة خمس دقائق")
    stop_reason = str(analysis.get("stop_reason") or "خلف منطقة إبطال السيناريو")
    scenario = str(analysis.get("scenario") or analysis.get("note") or "مراقبة حركة السعر عند مستوى التفعيل")

    target_text = "، ".join(f"هدف {index} {value:.2f}" for index, value in enumerate(targets, start=1) if value is not None)
    pattern_text = f"{pattern}، قوة {pattern_confidence} بالمئة" if pattern != "لا يوجد" else "لا يوجد نموذج مكتمل؛ الاعتماد على البنية والمستويات"
    lines = [
        f"الاتجاه: {direction}، الاحتمال الفني {probability} بالمئة",
        f"النموذج: {pattern_text}",
        f"الدخول: {entry:.2f}، {confirmation}" if entry is not None else f"الدخول: {confirmation}",
        f"الوقف: {stop:.2f}، {stop_reason}" if stop is not None else f"الوقف: {stop_reason}",
        f"الأهداف: {target_text}",
    ]

    y = top + 112
    for index, line in enumerate(lines):
        bullet_color = GREEN if index in {0, 2, 4} else RED if index == 3 else BLUE
        draw.ellipse((right - 39, y + 8, right - 27, y + 20), fill=bullet_color)
        _draw_text_rtl(draw, (right - 52, y), line[:100], NOTE_FONT, WHITE)
        y += 54

    draw.line((left + 28, bottom - 90, right - 28, bottom - 90), fill=(GOLD[0], GOLD[1], GOLD[2], 100), width=2)
    _draw_text_rtl(draw, (right - 30, bottom - 72), f"السيناريو الأقرب: {scenario[:95]}", NOTE_FONT, GOLD)
    _draw_text_rtl(draw, (right - 30, bottom - 48), "تحليل فني تقديري وليس ضمانًا للنتيجة", SMALL_FONT, GRAY)


def render_result(analysis: dict[str, Any]) -> bytes:
    _fonts()
    image = Image.new("RGBA", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    # خلفية خفيفة متدرجة يدويًا.
    for y in range(HEIGHT):
        shade = int(5 + 7 * y / HEIGHT)
        draw.line((0, y, WIDTH, y), fill=(shade, shade + 3, shade + 9, 255))

    candles = analysis.get("candles") or []
    price_min, price_max = _price_range(analysis)
    _draw_header(draw)
    _draw_grid(draw, price_min, price_max)
    _draw_candles(draw, candles, price_min, price_max)
    _draw_levels(draw, analysis, price_min, price_max)
    _draw_pattern(draw, analysis)
    _draw_trade(draw, analysis, price_min, price_max)
    _draw_notes(draw, analysis)

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", quality=96, optimize=True)
    return output.getvalue()
