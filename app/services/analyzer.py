from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import httpx

from app.engine.memory_engine import memory_context
from app.engine.models import normalize_analysis
from app.engine.renderer import render_result

OPENAI_URL = "https://api.openai.com/v1/responses"
BASE_DIR = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = BASE_DIR / "knowledge"

NUM_NULL = {"type": ["number", "null"]}
POINT = {
    "type": "array",
    "items": {"type": "number", "minimum": 0, "maximum": 1},
    "minItems": 2,
    "maxItems": 2,
}
LINE = {
    "type": "array",
    "items": {"type": "number", "minimum": 0, "maximum": 1},
    "minItems": 4,
    "maxItems": 4,
}
BOX_NULL = {
    "type": ["array", "null"],
    "items": {"type": "number", "minimum": 0, "maximum": 1},
    "minItems": 4,
    "maxItems": 4,
}

ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "direction": {
            "type": "string",
            "enum": ["صاعد", "هابط", "عرضي", "غير واضح"],
        },
        "buy_probability": {"type": "integer", "minimum": 5, "maximum": 95},
        "sell_probability": {"type": "integer", "minimum": 5, "maximum": 95},
        "current_price": NUM_NULL,
        "support": NUM_NULL,
        "resistance": NUM_NULL,
        "entry": NUM_NULL,
        "stop_loss": NUM_NULL,
        "target_1": NUM_NULL,
        "target_2": NUM_NULL,
        "target_3": NUM_NULL,
        "support_y": NUM_NULL,
        "resistance_y": NUM_NULL,
        "entry_y": NUM_NULL,
        "stop_loss_y": NUM_NULL,
        "target_1_y": NUM_NULL,
        "target_2_y": NUM_NULL,
        "target_3_y": NUM_NULL,
        "fvg_boxes": {
            "type": "array",
            "items": LINE,
            "maxItems": 3,
        },
        "pattern_type": {
            "type": "string",
            "enum": [
                "مثلث متماثل",
                "مثلث هابط",
                "مثلث صاعد",
                "وتد هابط",
                "وتد صاعد",
                "قناة هابطة",
                "قناة صاعدة",
                "قمتان",
                "قاعان",
                "لا يوجد",
            ],
        },
        "pattern_lines": {
            "type": "array",
            "items": LINE,
            "maxItems": 4,
        },
        "pattern_path": {
            "type": "array",
            "items": POINT,
            "maxItems": 12,
        },
        "retest_box": BOX_NULL,
        "path_points": {
            "type": "array",
            "items": POINT,
            "maxItems": 8,
        },
        "scenario": {"type": "string"},
        "note": {"type": "string"},
        "memory_matches": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 4,
        },
    },
    "required": [
        "direction",
        "buy_probability",
        "sell_probability",
        "current_price",
        "support",
        "resistance",
        "entry",
        "stop_loss",
        "target_1",
        "target_2",
        "target_3",
        "support_y",
        "resistance_y",
        "entry_y",
        "stop_loss_y",
        "target_1_y",
        "target_2_y",
        "target_3_y",
        "fvg_boxes",
        "pattern_type",
        "pattern_lines",
        "pattern_path",
        "retest_box",
        "path_points",
        "scenario",
        "note",
        "memory_matches",
    ],
}


def _data_url(path: Path) -> str:
    mime = {
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "image/jpeg")
    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{encoded}"


def _text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]

    for item in payload.get("output", []):
        for content in item.get("content", []):
            if isinstance(content.get("text"), str):
                return content["text"]

    raise RuntimeError("لم ترجع خدمة التحليل نتيجة صالحة.")


def _force_two_dollar_stop(analysis: dict[str, Any]) -> dict[str, Any]:
    """يجعل وقف الخسارة دائمًا على بُعد دولارين من الدخول."""
    entry = analysis.get("entry")
    if not isinstance(entry, (int, float)):
        analysis["stop_loss"] = None
        analysis["stop_loss_y"] = None
        return analysis

    direction = analysis.get("direction")
    if direction == "هابط":
        analysis["stop_loss"] = round(float(entry) + 2.0, 2)
    elif direction == "صاعد":
        analysis["stop_loss"] = round(float(entry) - 2.0, 2)
    elif analysis.get("sell_probability", 50) > analysis.get("buy_probability", 50):
        analysis["stop_loss"] = round(float(entry) + 2.0, 2)
    else:
        analysis["stop_loss"] = round(float(entry) - 2.0, 2)

    # موضع الوقف يُعاد حسابه داخل renderer بحسب علاقة السعر بمحور الشارت.
    analysis["stop_loss_y"] = None
    return analysis


def _analyze(path: Path) -> dict[str, Any]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("متغير OPENAI_API_KEY غير موجود في Railway.")

    prompt = f"""أنت محرك SaleeM Gold Analyst المتخصص في الذهب XAUUSD على فريم 5 دقائق فقط.
افحص صورة الشارت بدقة، واستفد من القواعد والسيناريوهات المرجعية للقراءة فقط، ثم أرجع JSON منظمًا للرسم فوق صورة الشارت نفسها.

قواعد التحليل:
- حدد الاتجاه والدعم والمقاومة والدخول وثلاثة أهداف فقط عندما تكون الأسعار مقروءة.
- BUY وSELL يجب أن يكون مجموعهما 100، ولا تستخدم 0 أو 100.
- لا تخترع أي سعر غير واضح؛ استخدم null عند عدم الوضوح.
- stop_loss يمكن أن يكون null لأن البرنامج سيحسبه آليًا على بُعد دولارين من الدخول.
- note ملاحظة عربية قصيرة جدًا لا تتجاوز 82 حرفًا.
- اختر سيناريو واحدًا فقط، ولا تعرض سيناريوهات متعارضة.

قواعد إحداثيات الرسم:
- جميع إحداثيات x وy نسبية من 0 إلى 1 بالنسبة للصورة كاملة.
- y=0 أعلى الصورة وy=1 أسفلها، وx=0 اليسار وx=1 اليمين.
- ضع الرسم داخل مساحة الشارت فقط، وتجنب شريط الهاتف العلوي وأزرار التطبيق السفلية.
- pattern_lines: خطوط النموذج الفني الأساسية فقط، كل خط [x1,y1,x2,y2].
- pattern_path: مسار أبيض يربط القمم والقيعان داخل النموذج.
- retest_box: مربع إعادة الاختبار [x1,y1,x2,y2] أو null.
- fvg_boxes: مناطق FVG الواضحة فقط.
- path_points: المسار المستقبلي المتوقع بعد الدخول فقط، وليس تاريخ حركة السعر.
- لا تضف بطاقات جانبية أو لوحة سفلية؛ جميع الرسومات والملاحظات تكون داخل الشارت.

الذاكرة المرجعية:
{memory_context(KNOWLEDGE_DIR)}
"""

    body = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": _data_url(path)},
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "saleem_overlay_v2",
                "strict": True,
                "schema": ANALYSIS_SCHEMA,
            }
        },
    }

    with httpx.Client(timeout=120) as client:
        response = client.post(
            OPENAI_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=body,
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"خطأ خدمة التحليل ({response.status_code}): {response.text[:500]}"
        )

    raw_analysis = json.loads(_text(response.json()))
    normalized = normalize_analysis(raw_analysis)

    # نحافظ على حقول الرسم الجديدة حتى لو لم تكن موجودة في normalize_analysis.
    analysis = {**raw_analysis, **normalized}
    return _force_two_dollar_stop(analysis)


def analyze_chart_image(
    image_path: Path,
    symbol: str,
    timeframe: str,
) -> dict[str, Any]:
    analysis = _analyze(image_path)
    png = render_result(image_path, analysis)

    return {
        **analysis,
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "result_url": "data:image/png;base64," + base64.b64encode(png).decode(),
    }
