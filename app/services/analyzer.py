from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

OPENAI_URL = "https://api.openai.com/v1/responses"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "direction": {"type": "string", "enum": ["صاعد", "هابط", "عرضي", "غير واضح"]},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "current_price": {"type": ["number", "null"]},
        "support": {"type": ["number", "null"]},
        "support_strength": {"type": "integer", "minimum": 0, "maximum": 100},
        "resistance": {"type": ["number", "null"]},
        "resistance_strength": {"type": "integer", "minimum": 0, "maximum": 100},
        "pattern": {"type": "string"},
        "candle_signal": {"type": "string"},
        "break_status": {"type": "string"},
        "buy_condition": {"type": "string"},
        "buy_entry": {"type": ["number", "null"]},
        "buy_stop": {"type": ["number", "null"]},
        "buy_target_1": {"type": ["number", "null"]},
        "buy_target_2": {"type": ["number", "null"]},
        "sell_condition": {"type": "string"},
        "sell_entry": {"type": ["number", "null"]},
        "sell_stop": {"type": ["number", "null"]},
        "sell_target_1": {"type": ["number", "null"]},
        "sell_target_2": {"type": ["number", "null"]},
        "invalidation": {"type": "string"},
        "summary": {"type": "string"},
        "risk_warning": {"type": "string"},
        "drawing_instructions": {"type": "string"},
    },
    "required": [
        "direction", "confidence", "current_price", "support", "support_strength",
        "resistance", "resistance_strength", "pattern", "candle_signal", "break_status",
        "buy_condition", "buy_entry", "buy_stop", "buy_target_1", "buy_target_2",
        "sell_condition", "sell_entry", "sell_stop", "sell_target_1", "sell_target_2",
        "invalidation", "summary", "risk_warning", "drawing_instructions"
    ],
}


def _mime(path: Path) -> str:
    suffix = path.suffix.lower()
    return {".png": "image/png", ".webp": "image/webp"}.get(suffix, "image/jpeg")


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
    raise RuntimeError("لم ترجع خدمة ChatGPT نتيجة نصية.")


def _analyze_with_chatgpt(image_path: Path, symbol: str, timeframe: str) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("متغير OPENAI_API_KEY غير موجود في Railway.")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    prompt = f"""
أنت محلل شارتات متخصص في الذهب والسكالبينج. حلل صورة {symbol} على فريم {timeframe}.
اقرأ فقط الأرقام الظاهرة بوضوح ولا تخترع سعرًا غير مقروء. حدّد أقرب دعم ومقاومة كرقم واحد لكل منهما،
الاتجاه، قوة المستويات، النمط الفني، شموع الرفض، الكسر أو إعادة الاختبار، وسيناريو شراء وبيع مشروطين.
لا تعطِ أمرًا قطعيًا بالدخول. اكتب drawing_instructions بالإنجليزية كتعليمات دقيقة إلى Gemini لتعديل نفس الصورة:
حافظ على جميع الشموع والأسعار كما هي، أضف خط دعم أخضر، خط مقاومة أحمر، سهم اتجاه، وتسميات قصيرة وواضحة فقط.
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
                "name": "gold_chart_analysis",
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
        raise RuntimeError(f"خطأ ChatGPT API ({response.status_code}): {response.text[:500]}")
    return json.loads(_extract_openai_text(response.json()))


def _draw_with_gemini(image_path: Path, instructions: str, result_path: Path) -> bool:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("متغير GEMINI_API_KEY غير موجود في Railway.")

    model = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image").strip()
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    prompt = (
        "Edit the supplied trading-chart screenshot only. Do not regenerate or alter candles, timestamps, "
        "price digits, indicators, scale, or layout. Add a clean transparent annotation layer according to "
        "these instructions. Keep labels short and preferably numeric/English for maximum legibility. "
        f"Instructions from ChatGPT: {instructions}"
    )
    body = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inlineData": {"mimeType": _mime(image_path), "data": image_b64}},
            ]
        }],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    url = GEMINI_URL.format(model=model)
    with httpx.Client(timeout=180) as client:
        response = client.post(url, params={"key": api_key}, json=body)
    if response.status_code >= 400:
        raise RuntimeError(f"خطأ Gemini API ({response.status_code}): {response.text[:500]}")

    payload = response.json()
    for candidate in payload.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                result_path.write_bytes(base64.b64decode(inline["data"]))
                return True
    logger.warning("Gemini returned no image; using original chart.")
    return False


def analyze_chart_image(image_path: Path, symbol: str, timeframe: str, result_dir: Path) -> dict[str, Any]:
    with Image.open(image_path) as img:
        width, height = img.size

    analysis = _analyze_with_chatgpt(image_path, symbol, timeframe)
    result_name = f"result_{image_path.stem}.png"
    result_path = result_dir / result_name

    drawing_error = None
    try:
        produced = _draw_with_gemini(image_path, analysis["drawing_instructions"], result_path)
    except Exception as exc:
        logger.exception("Gemini drawing failed")
        produced = False
        drawing_error = str(exc)

    if not produced:
        with Image.open(image_path).convert("RGB") as img:
            img.save(result_path, "PNG")

    analysis.update({
        "symbol": symbol,
        "timeframe": timeframe,
        "image_width": width,
        "image_height": height,
        "direction_label": analysis["direction"],
        "result_url": f"/static/results/{result_name}",
        "message": "اكتمل تحليل ChatGPT ورسم Gemini." if produced else "اكتمل تحليل ChatGPT، وتعذر رسم Gemini فتم عرض الصورة الأصلية.",
        "drawing_error": drawing_error,
    })
    return analysis
