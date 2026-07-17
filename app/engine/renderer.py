from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:  # pragma: no cover
    arabic_reshaper = None
    get_display = None

WIDTH = 1080
HEIGHT = 1920

BG_TOP = (3, 7, 13, 255)
BG_BOTTOM = (8, 13, 22, 255)
PANEL = (9, 16, 27, 248)
PANEL_2 = (12, 21, 34, 248)
GRID = (73, 87, 105, 62)
BORDER = (89, 108, 132, 145)
RED = (246, 67, 77, 255)
RED_FILL = (246, 67, 77, 45)
GREEN = (29, 211, 116, 255)
GREEN_FILL = (29, 211, 116, 45)
BLUE = (47, 137, 255, 255)
WHITE = (245, 248, 252, 255)
GRAY = (170, 184, 200, 255)
GOLD = (245, 184, 48, 255)
CYAN = (86, 210, 255, 255)
BLACK_GLASS = (3, 8, 14, 224)

MARGIN = 48
INFO_TOP = 115
INFO_BOTTOM = 248
CHART_PANEL = (48, 275, 1032, 1292)
CHART = (84, 322, 858, 1235)
PRICE_AXIS_X = 875
NOTES = (48, 1330, 1032, 1875)

_FONT_CACHE: dict[tuple[int, bool], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


def _rtl(text: str) -> str:
    if not text:
        return ""
    if arabic_reshaper is None or get_display is None:
        return text
    return get_display(arabic_reshaper.reshape(text))


def _font(size: int, bold: bool = False):
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    root = Path(__file__).resolve().parents[2]
    names = [
        "NotoSansArabic-Bold.ttf" if bold else "NotoSansArabic-Regular.ttf",
        "NotoNaskhArabic-Bold.ttf" if bold else "NotoNaskhArabic-Regular.ttf",
    ]
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    candidates += [root / "fonts" / name for name in names]
    candidates += [
        Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansArabic-Bold.ttf" if bold else "/usr/share/fonts/opentype/noto/NotoSansArabic-Regular.ttf"),
    ]
    for path in candidates:
        if path.exists():
            font = ImageFont.truetype(str(path), size=size)
            _FONT_CACHE[key] = font
            return font

    font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


TITLE_FONT = _font(42, True)
TITLE_LATIN = _font(42, True)
CARD_LABEL = _font(18, False)
CARD_VALUE = _font(25, True)
PRICE_FONT = _font(26, True)
AXIS_FONT = _font(18, False)
LEVEL_FONT = _font(18, False)
TRADE_FONT = _font(21, True)
NOTE_TITLE = _font(29, True)
NOTE_FONT = _font(22, False)
NOTE_BOLD = _font(23, True)
FOOTER_FONT = _font(17, False)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, (int, float)) else None


def _display(text: str, rtl: bool = True) -> str:
    return _rtl(text) if rtl else text


def _text_width(draw: ImageDraw.ImageDraw, text: str, font, rtl: bool = True) -> int:
    box = draw.textbbox((0, 0), _display(text, rtl), font=font)
    return box[2] - box[0]


def _draw_rtl(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font,
    fill=WHITE,
    anchor: str = "ra",
) -> None:
    draw.text(xy, _rtl(text), font=font, fill=fill, anchor=anchor)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    cleaned = " ".join(str(text).split())
    if _text_width(draw, cleaned, font) <= max_width:
        return cleaned
    while len(cleaned) > 6 and _text_width(draw, cleaned + "…", font) > max_width:
        cleaned = cleaned[:-1]
    return cleaned.rstrip() + "…"


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
    rtl: bool = True,
) -> tuple[int, int, int, int]:
    shown = _display(text, rtl)
    box = draw.textbbox((0, 0), shown, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    if align_right:
        x -= tw + padding_x * 2
    rect = (x, y, x + tw + padding_x * 2, y + th + padding_y * 2)
    draw.rounded_rectangle(rect, radius=9, fill=fill, outline=outline, width=1)
    draw.text((x + padding_x, y + padding_y - box[1]), shown, font=font, fill=text_fill)
    return rect


def _dash_line(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color,
    width: int = 3,
    dash: int = 15,
    gap: int = 10,
) -> None:
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
        draw.line(
            [(x1 + dx * pos, y1 + dy * pos), (x1 + dx * stop, y1 + dy * stop)],
            fill=color,
            width=width,
        )
        pos += dash + gap


def _arrow(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], color, width: int = 9) -> None:
    if len(points) < 2:
        return
    draw.line(points, fill=color, width=width, joint="curve")
    p1, p2 = points[-2], points[-1]
    angle = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    size = 28
    left = (
        p2[0] - size * math.cos(angle - math.pi / 6),
        p2[1] - size * math.sin(angle - math.pi / 6),
    )
    right = (
        p2[0] - size * math.cos(angle + math.pi / 6),
        p2[1] - size * math.sin(angle + math.pi / 6),
    )
    draw.polygon([p2, left, right], fill=color)


def _strength_width(strength: int) -> int:
    if strength >= 85:
        return 8
    if strength >= 70:
        return 6
    return 4


def _strength_name(strength: int) -> str:
    if strength >= 85:
        return "قوي جدًا"
    if strength >= 70:
        return "قوي"
    return "متوسط"


def _price_range(analysis: dict[str, Any]) -> tuple[float, float]:
    values: list[float] = []
    for candle in analysis.get("candles") or []:
        values.extend([float(candle["high"]), float(candle["low"])])
    for key in ("entry", "stop_loss", "target_1", "target_2", "target_3", "current_price"):
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
    padding = max(0.8, spread * 0.09)
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


def _draw_mixed_title(draw: ImageDraw.ImageDraw) -> None:
    segments = [
        ("تحليل", TITLE_FONT, WHITE, True),
        ("SaleeM", TITLE_LATIN, GOLD, False),
        ("- XAUUSD - M5 -", TITLE_LATIN, WHITE, False),
        ("آخر ساعتين", TITLE_FONT, WHITE, True),
    ]
    gap = 13
    widths = [_text_width(draw, text, font, rtl) for text, font, _, rtl in segments]
    total = sum(widths) + gap * (len(segments) - 1)
    x = int((WIDTH + total) / 2)
    y = 49
    for (text, font, color, rtl), width in zip(segments, widths):
        draw.text((x, y), _display(text, rtl), font=font, fill=color, anchor="ra")
        x -= width + gap
    draw.line((MARGIN, 102, WIDTH - MARGIN, 102), fill=(GOLD[0], GOLD[1], GOLD[2], 120), width=2)


def _draw_info_card(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    label: str,
    value: str,
    value_color=WHITE,
    value_rtl: bool = True,
) -> None:
    x1, y1, x2, y2 = rect
    draw.rounded_rectangle(rect, radius=16, fill=PANEL_2, outline=BORDER, width=1)
    _draw_rtl(draw, (x2 - 16, y1 + 22), label, CARD_LABEL, GRAY)
    if value_rtl:
        draw.text(
            (x2 - 16, y1 + 67),
            _display(value, True),
            font=CARD_VALUE,
            fill=value_color,
            anchor="ra",
        )
    else:
        shown = _fit_text(draw, value, CARD_VALUE, x2 - x1 - 24)
        draw.text(
            ((x1 + x2) // 2, y1 + 67),
            shown,
            font=CARD_VALUE,
            fill=value_color,
            anchor="ma",
        )


def _draw_header(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    _draw_mixed_title(draw)
    current = _number(analysis.get("current_price"))
    cards = [
        (48, INFO_TOP, 318, INFO_BOTTOM),
        (330, INFO_TOP, 532, INFO_BOTTOM),
        (544, INFO_TOP, 746, INFO_BOTTOM),
        (758, INFO_TOP, 1032, INFO_BOTTOM),
    ]
    _draw_info_card(draw, cards[0], "الأصل والفريم", "XAUUSD (GOLD) | M5", GOLD, False)
    _draw_info_card(draw, cards[1], "الفترة", "آخر ساعتين", WHITE, True)
    _draw_info_card(draw, cards[2], "عدد الشموع", "24 شمعة", WHITE, True)
    _draw_info_card(
        draw,
        cards[3],
        "السعر الحالي",
        f"{current:.2f}" if current is not None else "غير واضح",
        GREEN if current is not None else GRAY,
        False,
    )


def _draw_grid(draw: ImageDraw.ImageDraw, price_min: float, price_max: float) -> None:
    px1, py1, px2, py2 = CHART_PANEL
    left, top, right, bottom = CHART
    draw.rounded_rectangle(CHART_PANEL, radius=20, fill=(6, 12, 21, 255), outline=BORDER, width=2)
    ticks = 9
    for index in range(ticks):
        y = int(top + index * (bottom - top) / (ticks - 1))
        draw.line((left, y, right, y), fill=GRID, width=1)
        price = price_max - index * (price_max - price_min) / (ticks - 1)
        draw.text((PRICE_AXIS_X, y), f"{price:.2f}", font=AXIS_FONT, fill=GRAY, anchor="lm")
    for index in range(7):
        x = int(left + index * (right - left) / 6)
        draw.line((x, top, x, bottom), fill=GRID, width=1)
    draw.line((PRICE_AXIS_X - 12, top, PRICE_AXIS_X - 12, bottom), fill=(96, 112, 132, 100), width=1)


def _draw_candles(
    draw: ImageDraw.ImageDraw,
    candles: list[dict[str, Any]],
    price_min: float,
    price_max: float,
) -> None:
    left, top, right, bottom = CHART
    count = max(1, len(candles))
    slot = (right - left) / count
    body_width = max(10, int(slot * 0.50))

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
        if y2 - y1 < 4:
            y2 = y1 + 4
        draw.rectangle((x - body_width // 2, y1, x + body_width // 2, y2), fill=color, outline=color)

    indexes = list(range(0, count, 4))
    if count - 1 not in indexes:
        indexes.append(count - 1)
    for index in indexes:
        x = int(left + slot * (index + 0.5))
        label = str(candles[index].get("time") or "")[:5]
        draw.text((x, bottom + 23), label, font=AXIS_FONT, fill=GRAY, anchor="ma")


def _level_label_y(y: int, used: list[int]) -> int:
    candidate = y - 16
    for other in used:
        if abs(candidate - other) < 34:
            candidate = other + 36
    used.append(candidate)
    return candidate


def _draw_levels(
    draw: ImageDraw.ImageDraw,
    analysis: dict[str, Any],
    price_min: float,
    price_max: float,
) -> None:
    left, top, right, bottom = CHART
    used_labels: list[int] = []
    for key, color, name in (
        ("resistance_levels", RED, "مقاومة"),
        ("support_levels", GREEN, "دعم"),
    ):
        levels = sorted(
            analysis.get(key) or [],
            key=lambda item: int(item.get("strength") or 0),
            reverse=True,
        )[:2]
        for level in levels:
            price = _number(level.get("price"))
            if price is None or not (price_min <= price <= price_max):
                continue
            strength = int(level.get("strength") or 50)
            y = _price_y(price, price_min, price_max)
            width = _strength_width(strength)
            draw.line((left, y, right, y), fill=color, width=width)
            label_y = _level_label_y(y, used_labels)
            label_y = max(top + 6, min(bottom - 34, label_y))
            text = f"{name} {_strength_name(strength)} {price:.2f} - {strength}٪"
            _rounded_label(
                draw,
                left + 8,
                label_y,
                text,
                LEVEL_FONT,
                BLACK_GLASS,
                color,
                padding_x=8,
                padding_y=3,
            )


def _draw_pattern(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    confidence = int(analysis.get("pattern_confidence") or 0)
    if confidence < 60:
        return
    for line in analysis.get("pattern_lines") or []:
        if isinstance(line, list) and len(line) == 4:
            draw.line((_chart_point(line[:2]), _chart_point(line[2:])), fill=BLUE, width=5)
    path = [
        _chart_point(point)
        for point in analysis.get("pattern_path") or []
        if isinstance(point, list) and len(point) == 2
    ]
    if len(path) >= 2:
        draw.line(path, fill=WHITE, width=3, joint="curve")


def _spaced_label_positions(items: list[tuple[str, float, int]], min_gap: int = 42) -> dict[str, int]:
    ordered = sorted(items, key=lambda item: item[2])
    result: dict[str, int] = {}
    previous: int | None = None
    for key, _, exact_y in ordered:
        y = exact_y
        if previous is not None and y - previous < min_gap:
            y = previous + min_gap
        result[key] = y
        previous = y
    bottom_limit = CHART[3] - 35
    overflow = max(result.values(), default=0) - bottom_limit
    if overflow > 0:
        for key in result:
            result[key] -= overflow
    top_limit = CHART[1] + 4
    underflow = top_limit - min(result.values(), default=top_limit)
    if underflow > 0:
        for key in result:
            result[key] += underflow
    return result


def _draw_trade(
    draw: ImageDraw.ImageDraw,
    analysis: dict[str, Any],
    price_min: float,
    price_max: float,
) -> None:
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
    zone_left = int(left + (right - left) * 0.68)

    if stop_y is not None:
        draw.rectangle(
            (zone_left, min(entry_y, stop_y), right, max(entry_y, stop_y)),
            fill=RED_FILL,
        )
        _dash_line(draw, (zone_left, stop_y), (right, stop_y), RED, width=3)

    if target_ys:
        far_y = target_ys[-1]
        draw.rectangle(
            (zone_left, min(entry_y, far_y), right, max(entry_y, far_y)),
            fill=GREEN_FILL,
        )

    _dash_line(draw, (left, entry_y), (right, entry_y), WHITE, width=3)
    for y in target_ys:
        _dash_line(draw, (zone_left, y), (right, y), GREEN, width=3)

    label_items: list[tuple[str, float, int]] = [("entry", entry, entry_y)]
    if stop is not None and stop_y is not None:
        label_items.append(("stop", stop, stop_y))
    for index, (target, y) in enumerate(zip(targets, target_ys), start=1):
        label_items.append((f"tp{index}", target, y))
    positions = _spaced_label_positions(label_items)

    entry_prefix = "دخول" if analysis.get("draw_mode") == "confirmed" else "دخول محتمل"
    entry_rect = _rounded_label(
        draw,
        1018,
        positions["entry"] - 17,
        f"{entry_prefix} {entry:.2f}",
        TRADE_FONT,
        (235, 240, 246, 245),
        WHITE,
        text_fill=(10, 17, 27, 255),
        padding_x=9,
        padding_y=4,
        align_right=True,
    )
    if positions["entry"] != entry_y:
        draw.line((right, entry_y, entry_rect[0], positions["entry"]), fill=WHITE, width=1)

    if stop is not None and stop_y is not None:
        stop_rect = _rounded_label(
            draw,
            1018,
            positions["stop"] - 17,
            f"وقف {stop:.2f}",
            TRADE_FONT,
            (126, 25, 34, 245),
            RED,
            padding_x=9,
            padding_y=4,
            align_right=True,
        )
        if positions["stop"] != stop_y:
            draw.line((right, stop_y, stop_rect[0], positions["stop"]), fill=RED, width=1)

    for index, (target, y) in enumerate(zip(targets, target_ys), start=1):
        key = f"tp{index}"
        rect = _rounded_label(
            draw,
            1018,
            positions[key] - 17,
            f"TP{index}  {target:.2f}",
            TRADE_FONT,
            (7, 82, 45, 244),
            GREEN,
            padding_x=9,
            padding_y=4,
            align_right=True,
            rtl=False,
        )
        if positions[key] != y:
            draw.line((right, y, rect[0], positions[key]), fill=GREEN, width=1)

    end_y = target_ys[-1] if target_ys else (entry_y - 180 if direction == "صاعد" else entry_y + 180)
    end_y = max(top + 25, min(bottom - 25, end_y))
    arrow_x = int(left + (right - left) * 0.58)
    mid_y = int((entry_y + end_y) / 2)
    bend = 28 if direction == "صاعد" else -28
    _arrow(
        draw,
        [(arrow_x, entry_y), (arrow_x + bend, mid_y), (arrow_x + 4, end_y)],
        color,
        width=9,
    )

    state = {"confirmed": "مؤكد", "conditional": "مشروط", "watch": "مراقبة"}.get(
        str(analysis.get("draw_mode")), "مشروط"
    )
    side = str(analysis.get("trade_side") or ("شراء" if direction == "صاعد" else "بيع"))
    probability = int(analysis.get("trade_probability") or 50)
    _rounded_label(
        draw,
        left + 12,
        top + 12,
        f"{side} {probability}% - {state}",
        TRADE_FONT,
        BLACK_GLASS,
        color,
        padding_x=11,
        padding_y=5,
    )


def _pattern_name(analysis: dict[str, Any]) -> str:
    name = str(analysis.get("pattern_type") or "لا يوجد")
    if name == "قمتان":
        return "نموذج M"
    if name == "قاعان":
        return "نموذج W"
    return name


def _note_row(
    draw: ImageDraw.ImageDraw,
    y: int,
    label: str,
    value: str,
    dot_color,
) -> None:
    left, top, right, bottom = NOTES
    draw.ellipse((right - 37, y + 8, right - 23, y + 22), fill=dot_color)
    label_text = _rtl(label)
    label_box = draw.textbbox((0, 0), label_text, font=NOTE_BOLD)
    label_width = label_box[2] - label_box[0]
    draw.text((right - 50, y), label_text, font=NOTE_BOLD, fill=GRAY, anchor="ra")
    max_value_width = right - left - 240
    fitted = _fit_text(draw, value, NOTE_FONT, max_value_width)
    draw.text(
        (right - 64 - label_width, y),
        _rtl(fitted),
        font=NOTE_FONT,
        fill=WHITE,
        anchor="ra",
    )
    draw.line((left + 30, y + 44, right - 30, y + 44), fill=(76, 91, 111, 70), width=1)


def _draw_notes(draw: ImageDraw.ImageDraw, analysis: dict[str, Any]) -> None:
    left, top, right, bottom = NOTES
    draw.rounded_rectangle(NOTES, radius=24, fill=PANEL, outline=(GOLD[0], GOLD[1], GOLD[2], 190), width=2)
    _draw_rtl(draw, (right - 30, top + 31), "ملاحظات التحليل", NOTE_TITLE, GOLD)
    draw.line((left + 28, top + 82, right - 28, top + 82), fill=(GOLD[0], GOLD[1], GOLD[2], 110), width=2)

    direction = str(analysis.get("direction") or "غير واضح")
    probability = int(analysis.get("trade_probability") or 50)
    pattern = _pattern_name(analysis)
    pattern_confidence = int(analysis.get("pattern_confidence") or 0)
    entry = _number(analysis.get("entry"))
    stop = _number(analysis.get("stop_loss"))
    targets = [_number(analysis.get(key)) for key in ("target_1", "target_2", "target_3")]
    confirmation = str(analysis.get("confirmation") or "انتظار تأكيد شمعة خمس دقائق")
    stop_reason = str(analysis.get("stop_reason") or "خلف منطقة إبطال السيناريو")
    scenario = str(analysis.get("scenario") or analysis.get("note") or "مراقبة مستوى التفعيل")

    pattern_value = (
        f"{pattern} - ثقة {pattern_confidence}٪"
        if pattern != "لا يوجد"
        else "لا يوجد نموذج مكتمل؛ الاعتماد على البنية والمستويات"
    )
    entry_value = f"{entry:.2f} - {confirmation}" if entry is not None else confirmation
    stop_value = f"{stop:.2f} - {stop_reason}" if stop is not None else stop_reason
    target_value = " | ".join(
        f"TP{index}: {value:.2f}"
        for index, value in enumerate(targets, start=1)
        if value is not None
    )
    rows = [
        ("الاتجاه:", f"{direction} - احتمال فني {probability}٪", GREEN if direction == "صاعد" else RED),
        ("النمط:", pattern_value, BLUE),
        ("شرط الدخول:", entry_value, GREEN),
        ("وقف الخسارة:", stop_value, RED),
        ("الأهداف:", target_value, GREEN),
        ("أقرب سيناريو:", scenario, GOLD),
    ]

    y = top + 104
    for label, value, color in rows:
        _note_row(draw, y, label, value, color)
        y += 62

    _draw_rtl(
        draw,
        (right - 28, bottom - 35),
        "هذا تحليل فني تعليمي وليس توصية استثمارية. إدارة المخاطر مسؤوليتك.",
        FOOTER_FONT,
        GRAY,
    )


def render_result(analysis: dict[str, Any]) -> bytes:
    image = Image.new("RGBA", (WIDTH, HEIGHT), BG_TOP)
    draw = ImageDraw.Draw(image)

    for y in range(HEIGHT):
        ratio = y / max(1, HEIGHT - 1)
        color = tuple(
            int(BG_TOP[index] + (BG_BOTTOM[index] - BG_TOP[index]) * ratio)
            for index in range(3)
        ) + (255,)
        draw.line((0, y, WIDTH, y), fill=color)

    candles = analysis.get("candles") or []
    price_min, price_max = _price_range(analysis)
    _draw_header(draw, analysis)
    _draw_grid(draw, price_min, price_max)
    _draw_candles(draw, candles, price_min, price_max)
    _draw_levels(draw, analysis, price_min, price_max)
    _draw_pattern(draw, analysis)
    _draw_trade(draw, analysis, price_min, price_max)
    _draw_notes(draw, analysis)

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", quality=96, optimize=True)
    return output.getvalue()
