from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:  # يبقى التطبيق عاملاً، لكن يفضّل تثبيت المكتبتين.
    arabic_reshaper = None
    get_display = None


RED = (244, 63, 63, 255)
RED_FILL = (244, 63, 63, 58)
GREEN = (34, 197, 94, 255)
GREEN_FILL = (34, 197, 94, 58)
BLUE = (45, 125, 255, 255)
WHITE = (255, 255, 255, 255)
BLACK_GLASS = (7, 14, 25, 205)
GOLD = (245, 180, 35, 255)


def _rtl(text: str) -> str:
    if not text:
        return ""
    if arabic_reshaper is None or get_display is None:
        return text
    return get_display(arabic_reshaper.reshape(text))


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    root = Path(__file__).resolve().parents[2]
    candidates = [
        root / "fonts" / ("NotoSansArabic-Bold.ttf" if bold else "NotoSansArabic-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _point(point: Iterable[float], width: int, height: int) -> tuple[int, int]:
    x, y = point
    return (
        int(_clamp(float(x), 0.0, 1.0) * width),
        int(_clamp(float(y), 0.0, 1.0) * height),
    )


def _dash_line(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    fill: tuple[int, int, int, int],
    width: int,
    dash: int,
    gap: int,
) -> None:
    x1, y1 = start
    x2, y2 = end
    distance = math.hypot(x2 - x1, y2 - y1)
    if distance <= 0:
        return

    dx = (x2 - x1) / distance
    dy = (y2 - y1) / distance
    position = 0.0
    while position < distance:
        segment_end = min(position + dash, distance)
        draw.line(
            [
                (x1 + dx * position, y1 + dy * position),
                (x1 + dx * segment_end, y1 + dy * segment_end),
            ],
            fill=fill,
            width=width,
        )
        position += dash + gap


def _arrow_head(
    draw: ImageDraw.ImageDraw,
    previous: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int, int],
    size: int,
) -> None:
    angle = math.atan2(end[1] - previous[1], end[0] - previous[0])
    left = (
        end[0] - size * math.cos(angle - math.pi / 6),
        end[1] - size * math.sin(angle - math.pi / 6),
    )
    right = (
        end[0] - size * math.cos(angle + math.pi / 6),
        end[1] - size * math.sin(angle + math.pi / 6),
    )
    draw.polygon([end, left, right], fill=color)


def _polyline_arrow(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    color: tuple[int, int, int, int],
    width: int,
) -> None:
    if len(points) < 2:
        return
    draw.line(points, fill=color, width=width, joint="curve")
    _arrow_head(draw, points[-2], points[-1], color, max(14, width * 3))


def _label(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    canvas_width: int,
    padding_x: int,
    padding_y: int,
) -> tuple[int, int, int, int]:
    display = _rtl(text)
    box = draw.textbbox((0, 0), display, font=font)
    tw = box[2] - box[0]
    th = box[3] - box[1]

    x = int(_clamp(xy[0], 8, max(8, canvas_width - tw - padding_x * 2 - 8)))
    y = xy[1]
    rect = (x, y, x + tw + padding_x * 2, y + th + padding_y * 2)

    draw.rounded_rectangle(
        rect,
        radius=max(8, padding_y),
        fill=fill,
        outline=outline,
        width=max(2, padding_y // 3),
    )
    draw.text(
        (x + padding_x, y + padding_y - box[1]),
        display,
        font=font,
        fill=WHITE,
    )
    return rect


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _estimate_price_to_y(analysis: dict[str, Any]) -> tuple[float, float] | None:
    """يرجع y = slope * price + intercept باستعمال المستويات التي قرأها النموذج."""
    pairs: list[tuple[float, float]] = []
    for price_key, y_key in (
        ("support", "support_y"),
        ("resistance", "resistance_y"),
        ("entry", "entry_y"),
        ("target_1", "target_1_y"),
        ("target_2", "target_2_y"),
        ("target_3", "target_3_y"),
    ):
        price = _number(analysis.get(price_key))
        y_value = _number(analysis.get(y_key))
        if price is not None and y_value is not None and 0 <= y_value <= 1:
            pairs.append((price, y_value))

    # إزالة التكرار المتطابق.
    pairs = list(dict.fromkeys(pairs))
    if len(pairs) < 2:
        return None

    mean_price = sum(p for p, _ in pairs) / len(pairs)
    mean_y = sum(y for _, y in pairs) / len(pairs)
    denominator = sum((p - mean_price) ** 2 for p, _ in pairs)
    if denominator <= 1e-9:
        return None

    slope = sum((p - mean_price) * (y - mean_y) for p, y in pairs) / denominator
    intercept = mean_y - slope * mean_price
    if abs(slope) < 1e-8:
        return None
    return slope, intercept


def _price_y(
    analysis: dict[str, Any],
    price: float | None,
    explicit_y: Any,
    fallback: float,
) -> float:
    y_value = _number(explicit_y)
    if y_value is not None and 0 <= y_value <= 1:
        return _clamp(y_value, 0.08, 0.90)

    mapping = _estimate_price_to_y(analysis)
    if mapping is not None and price is not None:
        slope, intercept = mapping
        return _clamp(slope * price + intercept, 0.08, 0.90)

    return fallback


def _select_target(analysis: dict[str, Any], direction: str, entry: float) -> tuple[float | None, Any]:
    candidates: list[tuple[float, Any]] = []
    for price_key, y_key in (
        ("target_1", "target_1_y"),
        ("target_2", "target_2_y"),
        ("target_3", "target_3_y"),
    ):
        price = _number(analysis.get(price_key))
        if price is not None:
            candidates.append((price, analysis.get(y_key)))

    if direction == "هابط":
        valid = [item for item in candidates if item[0] < entry]
        return min(valid, key=lambda item: item[0]) if valid else (None, None)

    if direction == "صاعد":
        valid = [item for item in candidates if item[0] > entry]
        return max(valid, key=lambda item: item[0]) if valid else (None, None)

    return candidates[0] if candidates else (None, None)


def render_result(image_path: Path, analysis: dict[str, Any]) -> bytes:
    """يرسم التحليل داخل الشارت فقط ويعيد PNG bytes."""
    with Image.open(image_path) as source:
        source = ImageOps.exif_transpose(source).convert("RGBA")

    original_size = source.size
    scale = 2
    image = source.resize(
        (source.width * scale, source.height * scale),
        Image.Resampling.LANCZOS,
    )
    width, height = image.size

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    line_width = max(5, int(width * 0.005))
    thin_width = max(3, int(width * 0.003))
    main_font = _font(max(28, int(width * 0.030)), bold=True)
    small_font = _font(max(23, int(width * 0.023)), bold=True)

    direction = str(analysis.get("direction") or "غير واضح")
    trade_valid = bool(analysis.get("trade_valid"))
    entry = _number(analysis.get("entry")) if trade_valid else None
    stop = _number(analysis.get("stop_loss")) if trade_valid else None
    probability = int(analysis.get("trade_probability") or 50)
    side = str(analysis.get("trade_side") or "")

    # 1) رسم خطوط النموذج الفني باللون الأزرق.
    for line in analysis.get("pattern_lines") or []:
        if isinstance(line, list) and len(line) == 4:
            p1 = _point(line[:2], width, height)
            p2 = _point(line[2:], width, height)
            draw.line([p1, p2], fill=BLUE, width=line_width)

    # 2) مسار القمم والقيعان داخل النموذج باللون الأبيض.
    pattern_path = [
        _point(point, width, height)
        for point in (analysis.get("pattern_path") or [])
        if isinstance(point, list) and len(point) == 2
    ]
    if len(pattern_path) >= 2:
        draw.line(pattern_path, fill=WHITE, width=thin_width, joint="curve")

    # 3) مناطق FVG الشفافة.
    for box in analysis.get("fvg_boxes") or []:
        if not isinstance(box, list) or len(box) != 4:
            continue
        x1, y1 = _point(box[:2], width, height)
        x2, y2 = _point(box[2:], width, height)
        rect = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        color = RED if direction == "هابط" else GREEN
        fill = RED_FILL if direction == "هابط" else GREEN_FILL
        draw.rounded_rectangle(rect, radius=12, fill=fill, outline=color, width=thin_width)

    # 4) مربع إعادة الاختبار.
    retest_box = analysis.get("retest_box")
    if isinstance(retest_box, list) and len(retest_box) == 4:
        x1, y1 = _point(retest_box[:2], width, height)
        x2, y2 = _point(retest_box[2:], width, height)
        rect = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        retest_color = RED if direction == "هابط" else GREEN
        retest_fill = RED_FILL if direction == "هابط" else GREEN_FILL
        draw.rounded_rectangle(rect, radius=12, fill=retest_fill, outline=retest_color, width=thin_width)
        label_y = max(int(height * 0.08), rect[1] - int(height * 0.042))
        _label(
            draw,
            (rect[0], label_y),
            "إعادة اختبار",
            small_font,
            BLACK_GLASS,
            retest_color,
            width,
            int(width * 0.014),
            int(width * 0.008),
        )

    if entry is not None and stop is not None:
        target = _number(analysis.get("selected_target"))
        target_explicit_y = analysis.get("selected_target_y")
        if target is None:
            target, target_explicit_y = _select_target(analysis, direction, entry)

        entry_y_n = _price_y(analysis, entry, analysis.get("entry_y"), 0.62)
        stop_y_n = _price_y(
            analysis,
            stop,
            analysis.get("stop_loss_y"),
            entry_y_n - 0.035 if direction == "هابط" else entry_y_n + 0.035,
        )
        target_y_n = _price_y(
            analysis,
            target,
            target_explicit_y,
            entry_y_n + 0.20 if direction == "هابط" else entry_y_n - 0.20,
        )

        entry_y = int(entry_y_n * height)
        stop_y = int(stop_y_n * height)
        target_y = int(target_y_n * height)

        zone_left = int(width * 0.54)
        zone_right = int(width * 0.91)
        label_x = int(width * 0.64)

        # منطقة الوقف: مبنية على مستوى إبطال الصفقة من قراءة الشارت والذاكرة.
        draw.rectangle(
            (
                zone_left,
                min(stop_y, entry_y),
                zone_right,
                max(stop_y, entry_y),
            ),
            fill=RED_FILL,
            outline=RED,
            width=thin_width,
        )

        # منطقة الهدف: خضراء شفافة على الشارت نفسه.
        if target is not None:
            draw.rectangle(
                (
                    zone_left,
                    min(entry_y, target_y),
                    zone_right,
                    max(entry_y, target_y),
                ),
                fill=GREEN_FILL,
                outline=(GREEN[0], GREEN[1], GREEN[2], 165),
                width=thin_width,
            )

        entry_color = RED if direction == "هابط" else GREEN
        entry_fill = (130, 24, 32, 225) if direction == "هابط" else (12, 108, 56, 230)

        _dash_line(
            draw,
            (int(width * 0.04), entry_y),
            (zone_right, entry_y),
            entry_color,
            thin_width,
            dash=max(14, int(width * 0.017)),
            gap=max(10, int(width * 0.011)),
        )
        _dash_line(
            draw,
            (zone_left, stop_y),
            (zone_right, stop_y),
            RED,
            thin_width,
            dash=max(14, int(width * 0.017)),
            gap=max(10, int(width * 0.011)),
        )

        if target is not None:
            _dash_line(
                draw,
                (zone_left, target_y),
                (zone_right, target_y),
                GREEN,
                thin_width,
                dash=max(14, int(width * 0.017)),
                gap=max(10, int(width * 0.011)),
            )

        # البطاقات مرتبطة مباشرة بمستوياتها داخل الشارت.
        _label(
            draw,
            (label_x, stop_y - int(height * 0.038)),
            f"وقف {stop:.2f}",
            main_font,
            (130, 24, 32, 225),
            RED,
            width,
            int(width * 0.016),
            int(width * 0.009),
        )
        _label(
            draw,
            (label_x, entry_y + int(height * 0.006)),
            f"دخول {entry:.2f}",
            main_font,
            entry_fill,
            entry_color,
            width,
            int(width * 0.016),
            int(width * 0.009),
        )

        if target is not None:
            target_label_y = target_y - int(height * 0.050)
            _label(
                draw,
                (int(width * 0.57), target_label_y),
                f"منطقة الهدف {target:.2f}",
                main_font,
                (8, 90, 45, 220),
                GREEN,
                width,
                int(width * 0.016),
                int(width * 0.009),
            )

        # مسار السيناريو المتوقع فقط.
        future_path = [
            _point(point, width, height)
            for point in (analysis.get("path_points") or [])
            if isinstance(point, list) and len(point) == 2
        ]
        if len(future_path) < 2 and target is not None:
            future_path = [
                (int(width * 0.68), entry_y),
                (int(width * 0.62), int((entry_y + target_y) / 2)),
                (int(width * 0.80), target_y),
            ]

        if len(future_path) >= 2:
            _polyline_arrow(
                draw,
                future_path,
                RED if direction == "هابط" else GREEN,
                line_width * 2,
            )

    # بطاقة واحدة فقط لنسبة الصفقة المختارة.
    if trade_valid:
        probability_color = RED if direction == "هابط" else GREEN
        probability_fill = (130, 24, 32, 225) if direction == "هابط" else (12, 108, 56, 230)
        _label(
            draw,
            (int(width * 0.68), int(height * 0.11)),
            f"{side} {probability}%",
            main_font,
            probability_fill,
            probability_color,
            width,
            int(width * 0.016),
            int(width * 0.009),
        )

    # عند غياب صفقة واضحة لا نرسم دخولًا أو وقفًا أو هدفًا مزيفًا.
    if not trade_valid:
        _label(
            draw,
            (int(width * 0.22), int(height * 0.48)),
            "لا توجد صفقة واضحة الآن",
            main_font,
            BLACK_GLASS,
            GOLD,
            width,
            int(width * 0.018),
            int(width * 0.010),
        )

    # 5) عناوين صغيرة داخل الشارت فقط، دون بطاقات جانبية أو لوحة سفلية.
    pattern_type = str(analysis.get("pattern_type") or "")
    if pattern_type == "قمتان":
        pattern_type = "نموذج M"
    elif pattern_type == "قاعان":
        pattern_type = "نموذج W"

    if pattern_type and pattern_type != "لا يوجد":
        _label(
            draw,
            (int(width * 0.05), int(height * 0.10)),
            pattern_type,
            small_font,
            BLACK_GLASS,
            BLUE,
            width,
            int(width * 0.014),
            int(width * 0.008),
        )

    scenario = str(analysis.get("scenario") or "").strip()
    if scenario:
        _label(
            draw,
            (int(width * 0.05), int(height * 0.16)),
            scenario[:48],
            small_font,
            BLACK_GLASS,
            GOLD,
            width,
            int(width * 0.014),
            int(width * 0.008),
        )

    result = Image.alpha_composite(image, overlay)
    result = result.resize(original_size, Image.Resampling.LANCZOS).convert("RGB")

    output = io.BytesIO()
    result.save(output, format="PNG", optimize=True)
    return output.getvalue()
