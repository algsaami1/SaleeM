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
MIN_TRADE_PROBABILITY = 55

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
        "stop_reason": {"type": "string"},
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
        "stop_reason",
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


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _valid_targets(analysis: dict[str, Any], direction: str, entry: float) -> list[tuple[float, Any]]:
    targets: list[tuple[float, Any]] = []
    for price_key, y_key in (
        ("target_1", "target_1_y"),
        ("target_2", "target_2_y"),
        ("target_3", "target_3_y"),
    ):
        price = _number(analysis.get(price_key))
        if price is None:
            continue
        if direction == "هابط" and price < entry:
            targets.append((price, analysis.get(y_key)))
        elif direction == "صاعد" and price > entry:
            targets.append((price, analysis.get(y_key)))
    return targets


def _validate_single_trade(analysis: dict[str, Any]) -> dict[str, Any]:
    """يعتمد صفقة واحدة فقط: الاتجاه الأعلى احتمالًا، مع وقف بنيوي من الشارت."""
    analysis = normalize_analysis(analysis)
    buy = int(analysis.get("buy_probability", 50))
    sell = int(analysis.get("sell_probability", 50))

    direction = "صاعد" if buy > sell else "هابط"
    probability = buy if direction == "صاعد" else sell
    side = "شراء" if direction == "صاعد" else "بيع"

    # لا نغيّر الاتجاه العرضي/غير الواضح إلى صفقة بالقوة.
    raw_direction = str(analysis.get("direction") or "غير واضح")
    if raw_direction in {"عرضي", "غير واضح"}:
        trade_valid = False
    else:
        trade_valid = raw_direction == direction

    entry = _number(analysis.get("entry"))
    stop = _number(analysis.get("stop_loss"))
    targets = _valid_targets(analysis, direction, entry) if entry is not None else []

    if probability < MIN_TRADE_PROBABILITY or entry is None or stop is None or not targets:
        trade_valid = False

    if trade_valid and direction == "هابط" and stop <= entry:
        trade_valid = False
    if trade_valid and direction == "صاعد" and stop >= entry:
        trade_valid = False

    # الهدف الأساسي هو الأقرب إلى الدخول؛ لأنه الأعلى قابلية للتحقق على M5.
    selected_target: float | None = None
    selected_target_y: Any = None
    if targets:
        if direction == "هابط":
            selected_target, selected_target_y = max(targets, key=lambda item: item[0])
        else:
            selected_target, selected_target_y = min(targets, key=lambda item: item[0])

    analysis["direction"] = direction if trade_valid else raw_direction
    analysis["trade_valid"] = trade_valid
    analysis["trade_side"] = side if trade_valid else None
    analysis["trade_probability"] = probability if trade_valid else max(buy, sell)
    analysis["selected_target"] = selected_target if trade_valid else None
    analysis["selected_target_y"] = selected_target_y if trade_valid else None

    if not trade_valid:
        analysis["path_points"] = []
        analysis["retest_box"] = None
        analysis["note"] = "لا توجد صفقة واضحة الآن"

    return analysis


def _analyze(path: Path) -> dict[str, Any]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("متغير OPENAI_API_KEY غير موجود في Railway.")

    prompt = f"""أنت محرك SaleeM Gold Analyst المتخصص في الذهب XAUUSD على فريم 5 دقائق فقط.
افحص صورة الشارت بدقة، واستفد من الذاكرة المرجعية للقراءة فقط.
حلل الاحتمالات داخليًا، لكن أخرج صفقة واحدة فقط: الصفقة الأعلى احتمالًا والأوضح فنيًا.

قواعد اختيار الصفقة الوحيدة:
- قارن الشراء والبيع، واختر جهة واحدة فقط. BUY وSELL مجموعهما 100 ولا تستخدم 0 أو 100.
- إذا لم توجد صفقة واضحة أو الاتجاه عرضي، اجعل entry وstop_loss والأهداف null.
- لا ترسم أو تقترح مسارين متعارضين.
- إذا كان نموذج قمتين M واضحًا، رجّح الهبوط فقط بعد كسر/تأكيد مناسب.
- إذا كان نموذج قاعين W واضحًا، رجّح الصعود فقط بعد كسر/تأكيد مناسب.
- السهم المتوقع يتبع بنية الشارت: أحمر للهبوط وأخضر للصعود.

قواعد الدخول والوقف والهدف:
- entry هو دخول الصفقة الأعلى احتمالًا فقط، وليس السعر الحالي تلقائيًا.
- stop_loss يُختار من بنية الشارت والذاكرة: خلف آخر قمة/قاع أو خلف منطقة إبطال النموذج أو إعادة الاختبار.
- لا تستخدم وقفًا ثابتًا ولا تخترع مستوى غير مقروء.
- stop_reason سبب عربي قصير يشرح مستوى إبطال الصفقة.
- الأهداف تكون في اتجاه الصفقة، والهدف الأول هو الأكثر قابلية للتحقق.
- لا تستخدم null إلا عندما لا يكون السعر مقروءًا أو لا توجد صفقة.

قواعد الرسم:
- جميع إحداثيات x وy نسبية من 0 إلى 1 بالنسبة للصورة كاملة.
- ضع الرسم داخل مساحة الشارت وتجنب شريط الهاتف وأزرار التطبيق.
- pattern_lines: خطوط النموذج الأساسية فقط.
- pattern_path: مسار أبيض يربط القمم والقيعان، خصوصًا M أو W عند وضوحهما.
- retest_box: منطقة إعادة الاختبار للصفقة المختارة فقط أو null.
- fvg_boxes: المناطق الواضحة المرتبطة بالصفقة المختارة فقط.
- path_points: سهم واحد فقط يبدأ من الدخول/إعادة الاختبار ويتجه إلى الهدف.
- لا تضف لوحة جانبية أو لوحة سفلية.
- note سطر عربي قصير جدًا.

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
                "name": "saleem_single_best_trade",
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
    return _validate_single_trade(raw_analysis)


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
