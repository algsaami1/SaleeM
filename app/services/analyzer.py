from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def _load_rules() -> dict[str, Any]:
    rules_path = Path(__file__).resolve().parents[2] / "data" / "rules.json"
    if not rules_path.exists():
        return {}
    import json
    return json.loads(rules_path.read_text(encoding="utf-8"))


def _default_font(size: int = 24):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size=size)
    except Exception:
        return ImageFont.load_default()


def analyze_chart_image(
    image_path: Path,
    symbol: str,
    timeframe: str,
    result_dir: Path,
) -> dict[str, Any]:
    """
    MVP analyzer.

    Current behavior:
    - Validates and opens the image.
    - Adds an analysis panel over the screenshot.
    - Returns structured demo data.

    Next stages:
    - detect chart crop
    - read price axis
    - detect candles
    - map pixels to prices
    - calculate support/resistance
    - connect a vision model
    """
    rules = _load_rules()

    with Image.open(image_path).convert("RGB") as img:
        width, height = img.size
        draw = ImageDraw.Draw(img, "RGBA")

        panel_height = max(250, int(height * 0.23))
        draw.rectangle(
            [(0, height - panel_height), (width, height)],
            fill=(10, 20, 32, 225),
        )

        title_font = _default_font(max(28, width // 28))
        body_font = _default_font(max(20, width // 38))

        lines = [
            f"SaleeM | {symbol} {timeframe}",
            "الحالة: نسخة تجريبية",
            "الاتجاه: بانتظار محرك التحليل الحقيقي",
            "الدعم: غير محسوب بعد",
            "المقاومة: غير محسوبة بعد",
            "المرحلة التالية: اكتشاف محور السعر والشموع",
        ]

        y = height - panel_height + 24
        for i, line in enumerate(lines):
            font = title_font if i == 0 else body_font
            draw.text(
                (24, y),
                line,
                font=font,
                fill=(255, 255, 255, 255),
                direction="rtl" if any("\u0600" <= ch <= "\u06FF" for ch in line) else None,
            )
            y += int(font.size * 1.55) if hasattr(font, "size") else 38

        result_name = f"result_{image_path.stem}.jpg"
        result_path = result_dir / result_name
        img.save(result_path, quality=92)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "image_width": width,
        "image_height": height,
        "direction": "pending",
        "direction_label": "بانتظار محرك التحليل",
        "confidence": 0,
        "support": None,
        "resistance": None,
        "rules_loaded": len(rules.get("rules", [])),
        "result_url": f"/static/results/{result_name}",
        "message": "تم رفع الصورة وإنشاء نتيجة تجريبية بنجاح.",
    }
