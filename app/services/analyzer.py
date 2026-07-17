from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

OPENAI_URL = "https://api.openai.com/v1/responses"

ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "direction": {"type": "string", "enum": ["صاعد", "هابط", "عرضي", "غير واضح"]},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 90},
        "current_price": {"type": ["number", "null"]},
        "support": {"type": ["number", "null"]},
        "resistance": {"type": ["number", "null"]},
        "entry": {"type": ["number", "null"]},
        "stop_loss": {"type": ["number", "null"]},
        "target_1": {"type": ["number", "null"]},
        "target_2": {"type": ["number", "null"]},
        "target_3": {"type": ["number", "null"]},
        "scenario": {"type": "string"},
        "invalidation": {"type": "string"},
    },
    "required": [
        "direction", "confidence", "current_price", "support", "resistance",
        "entry", "stop_loss", "target_1", "target_2", "target_3",
        "scenario", "invalidation"
    ],
}


def _mime(path: Path) -> str:
    return {".png": "image/png", ".webp": "image/webp"}.get(path.suffix.lower(), "image/jpeg")


def _data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{_mime(path)};base64,{encoded}"


def _extract_openai_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    for item in payload.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                return text
    raise RuntimeError("لم ترجع خدمة التحليل نتيجة صالحة.")


def _analyze_chart(image_path: Path) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("متغير OPENAI_API_KEY غير موجود في Railway.")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    prompt = """
حلل صورة شارت الذهب XAUUSD على فريم 5 دقائق فقط.
أخرج سيناريو واحدًا مرجحًا (صعود أو هبوط أو عرضي) ولا تدّعِ اليقين.
اقرأ الأسعار الظاهرة فقط، ولا تخترع رقمًا غير مقروء.
حدد رقمًا واحدًا لأقرب دعم ورقمًا واحدًا لأقرب مقاومة، ثم نقطة دخول ووقف خسارة وثلاثة أهداف؛
اجعل TP3 هدفًا بعيدًا منطقيًا مبنيًا على البنية الظاهرة، وليس على شمعة واحدة.
النسبة هي قوة السيناريو من 0 إلى 90 فقط، ولا تستخدم 100 مطلقًا.
لا تكتب تنبيه شراء أو بيع ولا عبارة انتظر أو لا تدخل. اكتب وصفًا قصيرًا للسيناريو وشرط إلغائه فقط.
""".strip()

    body = {
        "model": model,
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": _data_url(image_path)},
            ],
        }],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "saleem_gold_analysis",
                "strict": True,
                "schema": ANALYSIS_SCHEMA,
            }
        },
    }

    with httpx.Client(timeout=120) as client:
        response = client.post(
            OPENAI_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"خطأ خدمة التحليل ({response.status_code}): {response.text[:500]}")
    return json.loads(_extract_openai_text(response.json()))


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        return f"{value:.2f}"
    return str(value)


def _render_result(image_path: Path, analysis: dict[str, Any], result_path: Path) -> None:
    with Image.open(image_path).convert("RGB") as original:
        original.thumbnail((1400, 1050))
        chart = original.copy()

    panel_w = max(380, int(chart.width * 0.32))
    canvas_h = max(chart.height, 760)
    canvas = Image.new("RGB", (chart.width + panel_w, canvas_h), (14, 18, 25))
    canvas.paste(chart, (0, 0))
    draw = ImageDraw.Draw(canvas)

    x0 = chart.width
    draw.rectangle((x0, 0, canvas.width, canvas.height), fill=(14, 18, 25))
    draw.text((x0 + 28, 24), "SaleeM Gold Analyst", font=_font(28, True), fill=(242, 201, 76))
    draw.text((x0 + 28, 62), "XAUUSD • 5M", font=_font(18, True), fill=(218, 223, 230))

    confidence = max(0, min(90, int(analysis.get("confidence", 0))))
    cx, cy, radius = x0 + panel_w // 2, 155, 62
    bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
    draw.arc(bbox, start=135, end=405, fill=(54, 64, 78), width=13)
    end_angle = 135 + (270 * confidence / 100)
    gauge_color = (52, 199, 89) if confidence >= 65 else (242, 201, 76) if confidence >= 45 else (235, 87, 87)
    draw.arc(bbox, start=135, end=end_angle, fill=gauge_color, width=13)
    pct = f"{confidence}%"
    tb = draw.textbbox((0, 0), pct, font=_font(30, True))
    draw.text((cx - (tb[2]-tb[0])/2, cy - 20), pct, font=_font(30, True), fill=(245, 247, 250))
    draw.text((x0 + 28, 231), f"الاتجاه: {analysis.get('direction', 'غير واضح')}", font=_font(22, True), fill=(245, 247, 250))

    rows = [
        ("الدخول", analysis.get("entry")),
        ("وقف الخسارة", analysis.get("stop_loss")),
        ("TP1", analysis.get("target_1")),
        ("TP2", analysis.get("target_2")),
        ("TP3", analysis.get("target_3")),
        ("الدعم", analysis.get("support")),
        ("المقاومة", analysis.get("resistance")),
    ]
    y = 278
    for label, value in rows:
        draw.rounded_rectangle((x0 + 24, y, canvas.width - 24, y + 46), radius=10, fill=(25, 31, 42))
        draw.text((x0 + 40, y + 11), label, font=_font(17, True), fill=(183, 191, 204))
        val = _fmt(value)
        vb = draw.textbbox((0, 0), val, font=_font(18, True))
        draw.text((canvas.width - 40 - (vb[2]-vb[0]), y + 10), val, font=_font(18, True), fill=(245, 247, 250))
        y += 54

    invalidation = str(analysis.get("invalidation", ""))[:85]
    draw.text((x0 + 28, y + 10), "إلغاء السيناريو", font=_font(15, True), fill=(235, 87, 87))
    draw.multiline_text((x0 + 28, y + 38), invalidation, font=_font(13), fill=(218, 223, 230), spacing=3)

    canvas.save(result_path, "PNG", optimize=True)


def analyze_chart_image(image_path: Path, symbol: str, timeframe: str, result_dir: Path) -> dict[str, Any]:
    analysis = _analyze_chart(image_path)
    analysis["confidence"] = max(0, min(90, int(analysis.get("confidence", 0))))

    result_name = f"result_{image_path.stem}.png"
    result_path = result_dir / result_name
    _render_result(image_path, analysis, result_path)

    return {
        **analysis,
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "result_url": f"/static/results/{result_name}",
    }
