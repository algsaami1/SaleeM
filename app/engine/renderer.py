from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:
    arabic_reshaper = None
    get_display = None

RED = (245, 55, 65, 255)
RED_FILL = (245, 55, 65, 54)
GREEN = (20, 205, 100, 255)
GREEN_FILL = (20, 205, 100, 48)
BLUE = (35, 135, 255, 255)
WHITE = (255, 255, 255, 255)
BLACK_GLASS = (4, 10, 18, 225)
GOLD = (245, 185, 45, 255)
GRAY = (205, 215, 225, 255)


def _rtl(text: str) -> str:
    if not text:
        return ""
    if arabic_reshaper is None or get_display is None:
        return text
    return get_display(arabic_reshaper.reshape(text))


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    root = Path(__file__).resolve().parents[2]
    names = [
        "NotoSansArabic-Bold.ttf" if bold else "NotoSansArabic-Regular.ttf",
        "NotoNaskhArabic-Bold.ttf" if bold else "NotoNaskhArabic-Regular.ttf",
    ]
    candidates = [root / "fonts" / name for name in names]
    candidates.extend([
        Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ])
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, (int, float)) else None


def _chart_box(analysis: dict[str, Any], width: int, height: int) -> tuple[int, int, int, int]:
    box = analysis.get("chart_box")
    if isinstance(box, list) and len(box) == 4:
        x1, y1, x2, y2 = [float(v) for v in box]
        x1, x2 = sorted((_clamp(x1, 0.0, 1.0), _clamp(x2, 0.0, 1.0)))
        y1, y2 = sorted((_clamp(y1, 0.0, 1.0), _clamp(y2, 0.0, 1.0)))
        if x2 - x1 >= 0.45 and y2 - y1 >= 0.45:
            return int(x1 * width), int(y1 * height), int(x2 * width), int(y2 * height)
    return int(width * 0.02), int(height * 0.12), int(width * 0.87), int(height * 0.90)


def _chart_point(
    point: Iterable[float], chart: tuple[int, int, int, int]
) -> tuple[int, int]:
    x, y = point
    left, top, right, bottom = chart
    return (
        int(left + _clamp(float(x), 0.0, 1.0) * (right - left)),
        int(top + _clamp(float(y), 0.0, 1.0) * (bottom - top)),
    )


def _price_to_y(analysis: dict[str, Any], price: float, height: int) -> int | None:
    top_price = _number(analysis.get("axis_top_price"))
    bottom_price = _number(analysis.get("axis_bottom_price"))
    top_y = _number(analysis.get("axis_top_y"))
    bottom_y = _number(analysis.get("axis_bottom_y"))
    if None in {top_price, bottom_price, top_y, bottom_y}:
        return None
    if top_price <= bottom_price or top_y >= bottom_y:
        return None
    ratio = (top_price - price) / (top_price - bottom_price)
    y_norm = top_y + ratio * (bottom_y - top_y)
    return int(_clamp(y_norm, top_y, bottom_y) * height)


def _dash_line(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], fill, width: int, dash: int, gap: int) -> None:
    x1, y1 = start
    x2, y2 = end
    distance = math.hypot(x2 - x1, y2 - y1)
    if distance <= 0:
        return
    dx = (x2 - x1) / distance
    dy = (y2 - y1) / distance
    pos = 0.0
    while pos < distance:
        segment_end = min(pos + dash, distance)
        draw.line([(x1 + dx * pos, y1 + dy * pos), (x1 + dx * segment_end, y1 + dy * segment_end)], fill=fill, width=width)
        pos += dash + gap


def _arrow(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], color, width: int) -> None:
    if len(points) < 2:
        return
    draw.line(points, fill=color, width=width, joint="curve")
    previous, end = points[-2], points[-1]
    angle = math.atan2(end[1] - previous[1], end[0] - previous[0])
    size = max(18, width * 3)
    left = (end[0] - size * math.cos(angle - math.pi / 6), end[1] - size * math.sin(angle - math.pi / 6))
    right = (end[0] - size * math.cos(angle + math.pi / 6), end[1] - size * math.sin(angle + math.pi / 6))
    draw.polygon([end, left, right], fill=color)


def _label(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font,
    fill,
    outline,
    bounds: tuple[int, int, int, int],
    padding_x: int,
    padding_y: int,
) -> tuple[int, int, int, int]:
    display = _rtl(text)
    bbox = draw.textbbox((0, 0), display, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    left, top, right, bottom = bounds
    x = int(_clamp(xy[0], left + 6, max(left + 6, right - tw - 2 * padding_x - 6)))
    y = int(_clamp(xy[1], top + 6, max(top + 6, bottom - th - 2 * padding_y - 6)))
    rect = (x, y, x + tw + 2 * padding_x, y + th + 2 * padding_y)
    draw.rounded_rectangle(rect, radius=max(10, padding_y), fill=fill, outline=outline, width=max(2, padding_y // 3))
    draw.text((x + padding_x, y + padding_y - bbox[1]), display, font=font, fill=WHITE)
    return rect


def render_result(image_path: Path, analysis: dict[str, Any]) -> bytes:
    with Image.open(image_path) as source:
        source = ImageOps.exif_transpose(source).convert("RGBA")

    original_size = source.size
    scale = 2
    image = source.resize((source.width * scale, source.height * scale), Image.Resampling.LANCZOS)
    width, height = image.size
    chart = _chart_box(analysis, width, height)
    left, top, right, bottom = chart

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # الأحجام تحسب على الصورة النهائية ثم تضرب بمعامل التكبير حتى تبقى واضحة بعد التصغير.
    final_main = max(34, int(original_size[0] * 0.044))
    final_small = max(27, int(original_size[0] * 0.034))
    final_tiny = max(23, int(original_size[0] * 0.029))
    main_font = _font(final_main * scale, bold=True)
    small_font = _font(final_small * scale, bold=True)
    tiny_font = _font(final_tiny * scale, bold=True)
    line_width = max(7, int(original_size[0] * 0.006) * scale)
    thin_width = max(4, int(original_size[0] * 0.0035) * scale)

    direction = str(analysis.get("direction") or "غير واضح")
    color = GREEN if direction == "صاعد" else RED
    side = str(analysis.get("trade_side") or ("شراء" if direction == "صاعد" else "بيع"))
    probability = int(analysis.get("trade_probability") or 50)
    draw_mode = str(analysis.get("draw_mode") or "none")
    entry = _number(analysis.get("entry"))
    stop = _number(analysis.get("stop_loss"))
    target = _number(analysis.get("selected_target"))

    # النموذج يرسم فقط عند ثقة جيدة، وبإحداثيات داخل مساحة الشارت لا الصورة كاملة.
    pattern_confidence = int(analysis.get("pattern_confidence") or 0)
    if pattern_confidence >= 65:
        for line in analysis.get("pattern_lines") or []:
            if isinstance(line, list) and len(line) == 4:
                draw.line([_chart_point(line[:2], chart), _chart_point(line[2:], chart)], fill=BLUE, width=thin_width)
        path = [_chart_point(p, chart) for p in (analysis.get("pattern_path") or []) if isinstance(p, list) and len(p) == 2]
        if len(path) >= 2:
            draw.line(path, fill=WHITE, width=thin_width, joint="curve")

    # منطقة FVG واحدة فقط مرتبطة بالسيناريو حتى لا يزدحم الشارت.
    if draw_mode in {"confirmed", "conditional"}:
        for box in (analysis.get("fvg_boxes") or [])[:1]:
            if isinstance(box, list) and len(box) == 4:
                p1, p2 = _chart_point(box[:2], chart), _chart_point(box[2:], chart)
                rect = (min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1]))
                draw.rounded_rectangle(rect, radius=12, fill=GREEN_FILL if direction == "صاعد" else RED_FILL, outline=color, width=thin_width)

    entry_y = _price_to_y(analysis, entry, height) if entry is not None else None
    stop_y = _price_to_y(analysis, stop, height) if stop is not None else None
    target_y = _price_to_y(analysis, target, height) if target is not None else None

    zone_left = int(left + (right - left) * 0.62)
    zone_right = right - max(10, int((right - left) * 0.015))
    label_x = int(left + (right - left) * 0.66)

    if draw_mode != "none" and entry_y is not None:
        entry_text = "دخول" if draw_mode == "confirmed" else "دخول محتمل"
        _dash_line(draw, (left + 8, entry_y), (zone_right, entry_y), color, thin_width, 22, 14)

        # مناطق المخاطرة/الهدف لا ترسم إلا عندما تكون المستويات داخل المحور وبترتيب صحيح.
        correct_stop = stop_y is not None and ((direction == "صاعد" and stop_y > entry_y) or (direction == "هابط" and stop_y < entry_y))
        correct_target = target_y is not None and ((direction == "صاعد" and target_y < entry_y) or (direction == "هابط" and target_y > entry_y))

        if correct_stop:
            draw.rectangle((zone_left, min(stop_y, entry_y), zone_right, max(stop_y, entry_y)), fill=RED_FILL, outline=RED, width=thin_width)
            _dash_line(draw, (zone_left, stop_y), (zone_right, stop_y), RED, thin_width, 22, 14)
        if correct_target:
            draw.rectangle((zone_left, min(entry_y, target_y), zone_right, max(entry_y, target_y)), fill=GREEN_FILL, outline=GREEN, width=thin_width)
            _dash_line(draw, (zone_left, target_y), (zone_right, target_y), GREEN, thin_width, 22, 14)

        # بطاقات كبيرة وموحدة على يمين مساحة الشارت.
        if direction == "صاعد":
            entry_label_y = entry_y - (final_main + 20) * scale
            stop_label_y = (stop_y + 6 * scale) if correct_stop else entry_y
            target_label_y = (target_y - (final_main + 20) * scale) if correct_target else entry_y
        else:
            entry_label_y = entry_y + 6 * scale
            stop_label_y = (stop_y - (final_main + 20) * scale) if correct_stop else entry_y
            target_label_y = (target_y + 6 * scale) if correct_target else entry_y

        if correct_stop:
            _label(draw, (label_x, stop_label_y), f"وقف {stop:.2f}", main_font, (125, 20, 32, 235), RED, chart, 18 * scale, 8 * scale)
        _label(draw, (label_x, entry_label_y), f"{entry_text} {entry:.2f}", main_font, (10, 105, 55, 235) if direction == "صاعد" else (125, 20, 32, 235), color, chart, 18 * scale, 8 * scale)
        if correct_target:
            _label(draw, (label_x, target_label_y), f"الهدف {target:.2f}", main_font, (8, 90, 45, 235), GREEN, chart, 18 * scale, 8 * scale)

        # سهم متوسط الطول يبدأ من نقطة الدخول، ولا يقطع الشارت كاملًا.
        if correct_target:
            end_y = target_y
        else:
            delta = int((bottom - top) * 0.16)
            end_y = max(top + 20, entry_y - delta) if direction == "صاعد" else min(bottom - 20, entry_y + delta)
        arrow_x = int(left + (right - left) * 0.52)
        mid_y = int((entry_y + end_y) / 2)
        _arrow(draw, [(arrow_x, entry_y), (arrow_x + 18 * scale, mid_y), (arrow_x + 5 * scale, end_y)], color, line_width)

        # بطاقة النسبة وحالة الصفقة.
        state_text = "مؤكد" if draw_mode == "confirmed" else "مشروط" if draw_mode == "conditional" else "مراقبة"
        _label(draw, (left + 14 * scale, top + 14 * scale), f"{state_text}  {side}  {probability} بالمئة", main_font, (10, 105, 55, 235) if direction == "صاعد" else (125, 20, 32, 235), color, chart, 18 * scale, 8 * scale)

        confirmation = str(analysis.get("confirmation") or "").strip()
        if confirmation:
            _label(draw, (left + 14 * scale, top + (final_main + 28) * scale), confirmation[:44], small_font, BLACK_GLASS, GOLD, chart, 14 * scale, 7 * scale)

    if draw_mode == "none":
        _label(draw, (left + int((right - left) * 0.15), top + int((bottom - top) * 0.45)), "تعذر قراءة محور السعر", main_font, BLACK_GLASS, GOLD, chart, 18 * scale, 9 * scale)

    pattern_type = str(analysis.get("pattern_type") or "")
    if pattern_type == "قمتان":
        pattern_type = "نموذج M"
    elif pattern_type == "قاعان":
        pattern_type = "نموذج W"
    if pattern_confidence >= 65 and pattern_type and pattern_type != "لا يوجد":
        _label(draw, (left + 14 * scale, bottom - (final_small + 38) * scale), f"{pattern_type} {pattern_confidence}%", tiny_font, BLACK_GLASS, BLUE, chart, 12 * scale, 6 * scale)

    result = Image.alpha_composite(image, overlay)
    result = result.resize(original_size, Image.Resampling.LANCZOS).convert("RGB")
    output = io.BytesIO()
    result.save(output, format="PNG", optimize=True)
    return output.getvalue()
