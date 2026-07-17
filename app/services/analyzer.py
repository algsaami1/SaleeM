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

CONFIRMED_PROBABILITY = 65
CONDITIONAL_PROBABILITY = 55
MAX_ENTRY_DISTANCE = 6.0
MAX_STRUCTURAL_STOP = 8.0
MIN_STRUCTURAL_STOP = 0.8

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
        "chart_readable": {"type": "boolean"},
        "chart_box": LINE,
        "axis_top_price": NUM_NULL,
        "axis_top_y": NUM_NULL,
        "axis_bottom_price": NUM_NULL,
        "axis_bottom_y": NUM_NULL,
        "direction": {"type": "string", "enum": ["صاعد", "هابط", "عرضي", "غير واضح"]},
        "buy_probability": {"type": "integer", "minimum": 5, "maximum": 95},
        "sell_probability": {"type": "integer", "minimum": 5, "maximum": 95},
        "setup_state": {"type": "string", "enum": ["مؤكد", "مشروط", "مراقبة", "غير صالح"]},
        "entry_kind": {"type": "string", "enum": ["مباشر", "اختراق", "إعادة اختبار", "مراقبة"]},
        "confirmation": {"type": "string"},
        "current_price": NUM_NULL,
        "support": NUM_NULL,
        "resistance": NUM_NULL,
        "entry": NUM_NULL,
        "stop_loss": NUM_NULL,
        "stop_reason": {"type": "string"},
        "target_1": NUM_NULL,
        "target_2": NUM_NULL,
        "target_3": NUM_NULL,
        "fvg_boxes": {"type": "array", "items": LINE, "maxItems": 1},
        "pattern_type": {
            "type": "string",
            "enum": [
                "مثلث متماثل", "مثلث هابط", "مثلث صاعد", "وتد هابط", "وتد صاعد",
                "قناة هابطة", "قناة صاعدة", "قمتان", "قاعان", "لا يوجد",
            ],
        },
        "pattern_confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "pattern_lines": {"type": "array", "items": LINE, "maxItems": 3},
        "pattern_path": {"type": "array", "items": POINT, "maxItems": 10},
        "retest_box": BOX_NULL,
        "path_points": {"type": "array", "items": POINT, "maxItems": 5},
        "scenario": {"type": "string"},
        "note": {"type": "string"},
        "memory_matches": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
    },
    "required": [
        "chart_readable", "chart_box", "axis_top_price", "axis_top_y", "axis_bottom_price", "axis_bottom_y",
        "direction", "buy_probability", "sell_probability", "setup_state", "entry_kind", "confirmation",
        "current_price", "support", "resistance", "entry", "stop_loss", "stop_reason",
        "target_1", "target_2", "target_3", "fvg_boxes", "pattern_type", "pattern_confidence",
        "pattern_lines", "pattern_path", "retest_box", "path_points", "scenario", "note", "memory_matches",
    ],
}


def _data_url(path: Path) -> str:
    mime = {".png": "image/png", ".webp": "image/webp"}.get(path.suffix.lower(), "image/jpeg")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


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


def _valid_axis(analysis: dict[str, Any]) -> bool:
    top_price = _number(analysis.get("axis_top_price"))
    bottom_price = _number(analysis.get("axis_bottom_price"))
    top_y = _number(analysis.get("axis_top_y"))
    bottom_y = _number(analysis.get("axis_bottom_y"))
    if None in {top_price, bottom_price, top_y, bottom_y}:
        return False
    return bool(top_price > bottom_price and 0 <= top_y < bottom_y <= 1)


def _valid_targets(analysis: dict[str, Any], direction: str, entry: float) -> list[float]:
    values: list[float] = []
    for key in ("target_1", "target_2", "target_3"):
        price = _number(analysis.get(key))
        if price is None:
            continue
        if direction == "هابط" and price < entry:
            values.append(price)
        elif direction == "صاعد" and price > entry:
            values.append(price)
    return values


def _nearest_entry(
    analysis: dict[str, Any], direction: str, current: float
) -> tuple[float, str, str]:
    """يرجع أقرب نقطة تفعيل من المستويات المقروءة، ولا يختار مستوى بعيدًا."""
    proposed = _number(analysis.get("entry"))
    if proposed is not None and abs(proposed - current) <= MAX_ENTRY_DISTANCE:
        kind = str(analysis.get("entry_kind") or "مراقبة")
        return proposed, kind, str(analysis.get("confirmation") or "انتظار تأكيد شمعة خمس دقائق")

    support = _number(analysis.get("support"))
    resistance = _number(analysis.get("resistance"))
    candidates: list[tuple[float, str, str]] = []

    if direction == "صاعد":
        if resistance is not None and current <= resistance <= current + MAX_ENTRY_DISTANCE:
            candidates.append((resistance, "اختراق", "إغلاق شمعة خمس دقائق فوق المقاومة"))
        if support is not None and current - 4.0 <= support <= current:
            candidates.append((support, "إعادة اختبار", "ثبات الدعم وظهور شمعة صاعدة"))
    else:
        if support is not None and current - MAX_ENTRY_DISTANCE <= support <= current:
            candidates.append((support, "اختراق", "إغلاق شمعة خمس دقائق تحت الدعم"))
        if resistance is not None and current <= resistance <= current + 4.0:
            candidates.append((resistance, "إعادة اختبار", "رفض المقاومة وظهور شمعة هابطة"))

    if candidates:
        return min(candidates, key=lambda item: abs(item[0] - current))

    # عندما لا يوجد مستوى قريب، نعرض مراقبة عند السعر الحالي بدل رسم دخول بعيد وغير منطقي.
    return current, "مراقبة", "انتظار شمعة تأكيد خمس دقائق قبل الدخول"


def _validated_stop(
    analysis: dict[str, Any], direction: str, entry: float
) -> tuple[float | None, str]:
    stop = _number(analysis.get("stop_loss"))
    reason = str(analysis.get("stop_reason") or "خلف منطقة إبطال السيناريو")

    if stop is not None:
        distance = abs(stop - entry)
        correct_side = (direction == "صاعد" and stop < entry) or (direction == "هابط" and stop > entry)
        if correct_side and MIN_STRUCTURAL_STOP <= distance <= MAX_STRUCTURAL_STOP:
            return stop, reason

    structural = _number(analysis.get("support" if direction == "صاعد" else "resistance"))
    if structural is not None:
        distance = abs(structural - entry)
        correct_side = (direction == "صاعد" and structural < entry) or (direction == "هابط" and structural > entry)
        if correct_side and MIN_STRUCTURAL_STOP <= distance <= MAX_STRUCTURAL_STOP:
            return structural, "خلف أقرب دعم" if direction == "صاعد" else "فوق أقرب مقاومة"

    return None, "الوقف ينتظر تأكيد البنية"


def _select_target(
    analysis: dict[str, Any], direction: str, entry: float, stop: float | None
) -> float | None:
    targets = _valid_targets(analysis, direction, entry)
    if not targets:
        return None

    ordered = sorted(targets, reverse=(direction == "هابط"))
    if stop is None:
        return ordered[0]

    risk = abs(entry - stop)
    for target in ordered:
        reward = abs(target - entry)
        if risk > 0 and reward / risk >= 1.15:
            return target
    return ordered[0]


def _validate_single_trade(analysis: dict[str, Any]) -> dict[str, Any]:
    """يعرض صفقة واحدة أو أقرب تفعيل محتمل، ويمنع المستويات البعيدة أو المقلوبة."""
    analysis = normalize_analysis(analysis)
    buy = int(analysis.get("buy_probability", 50))
    sell = int(analysis.get("sell_probability", 50))
    direction = "صاعد" if buy >= sell else "هابط"
    probability = buy if direction == "صاعد" else sell
    side = "شراء" if direction == "صاعد" else "بيع"

    current = _number(analysis.get("current_price"))
    chart_readable = bool(analysis.get("chart_readable")) and current is not None and _valid_axis(analysis)

    analysis["direction"] = direction
    analysis["trade_side"] = side
    analysis["trade_probability"] = probability
    analysis["no_setup"] = not chart_readable

    if not chart_readable or current is None:
        analysis.update(
            {
                "trade_valid": False,
                "draw_mode": "none",
                "entry": None,
                "stop_loss": None,
                "selected_target": None,
                "path_points": [],
                "note": "تعذر قراءة محور السعر بوضوح",
            }
        )
        return analysis

    entry, entry_kind, confirmation = _nearest_entry(analysis, direction, current)
    stop, stop_reason = _validated_stop(analysis, direction, entry)
    target = _select_target(analysis, direction, entry, stop)

    model_state = str(analysis.get("setup_state") or "مراقبة")
    distance = abs(entry - current)
    complete_risk_plan = stop is not None and target is not None

    if probability >= CONFIRMED_PROBABILITY and model_state == "مؤكد" and distance <= 3.0 and complete_risk_plan:
        draw_mode = "confirmed"
        trade_valid = True
    elif probability >= CONDITIONAL_PROBABILITY:
        draw_mode = "conditional"
        trade_valid = False
    else:
        draw_mode = "watch"
        trade_valid = False

    # إذا تجاوز السعر الهدف أو ابتعد كثيرًا عن الدخول، تتحول الفكرة إلى مراقبة عند أقرب تفعيل.
    if target is not None:
        target_passed = (direction == "صاعد" and current >= target) or (direction == "هابط" and current <= target)
        if target_passed:
            target = None
            draw_mode = "watch"
            trade_valid = False

    analysis.update(
        {
            "trade_valid": trade_valid,
            "draw_mode": draw_mode,
            "entry": round(entry, 2),
            "entry_kind": entry_kind,
            "confirmation": confirmation,
            "stop_loss": round(stop, 2) if stop is not None else None,
            "stop_reason": stop_reason,
            "selected_target": round(target, 2) if target is not None else None,
            "note": (
                f"{side} مؤكد" if draw_mode == "confirmed" else
                f"{side} محتمل بعد التأكيد" if draw_mode == "conditional" else
                f"مراقبة احتمال {side}"
            ),
        }
    )

    # لا نستخدم نقاط سهم بعيدة من النموذج؛ الرسام يبني السهم من الدخول إلى الهدف/الاتجاه.
    analysis["path_points"] = []
    if int(analysis.get("pattern_confidence") or 0) < 65:
        analysis["pattern_lines"] = []
        analysis["pattern_path"] = []
        analysis["retest_box"] = None
    return analysis


def _analyze(path: Path) -> dict[str, Any]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("متغير OPENAI_API_KEY غير موجود في Railway.")

    prompt = f"""أنت محرك SaleeM Gold Analyst المتخصص في الذهب XAUUSD على فريم M5 فقط.
اقرأ صورة الشارت كما هي، واستفد من الذاكرة المرجعية للقراءة فقط. أخرج سيناريو واحدًا فقط: الأعلى احتمالًا.

أهم قاعدة: لا تعطِ دخولًا بعيدًا عن السعر الحالي. ابحث عن أقرب نقطة تفعيل واقعية خلال نحو 6 دولارات من السعر الحالي.
إذا لم تكتمل الصفقة، لا تقل مباشرة لا توجد صفقة؛ أخرج أقرب دخول محتمل مشروط بالتأكيد مع سهم اتجاه واحد.
استخدم حالة غير صالح فقط إذا كانت صورة الشارت أو محور الأسعار غير مقروءين.

قراءة المحور:
- chart_box هو حدود مساحة الشموع فقط بصيغة [x1,y1,x2,y2] نسبةً للصورة كاملة، مع استبعاد شريط الهاتف ومحور الوقت والأزرار.
- axis_top_price وaxis_top_y: سعر واضح مرتفع على محور اليمين وموقعه y نسبةً للصورة.
- axis_bottom_price وaxis_bottom_y: سعر واضح منخفض على محور اليمين وموقعه y نسبةً للصورة.
- يجب أن يكون axis_top_price أكبر من axis_bottom_price وaxis_top_y أصغر من axis_bottom_y.

اختيار الاتجاه والصفقة:
- BUY وSELL مجموعهما 100، ولا تستخدم 0 أو 100.
- اختر شراء أو بيع واحدًا فقط.
- M/قمتان لا يصبح بيعًا إلا بعد كسر خط العنق أو إعادة اختبار فاشلة مع شمعة هابطة.
- W/قاعان لا يصبح شراءً إلا بعد اختراق خط العنق أو إعادة اختبار ناجحة مع شمعة صاعدة.
- setup_state: مؤكد عند وجود كسر/إغلاق/إعادة اختبار أو تأكيد واضح؛ مشروط عند انتظار التفعيل؛ مراقبة عند ضعف التأكيد.
- entry_kind: مباشر أو اختراق أو إعادة اختبار أو مراقبة.
- confirmation عبارة عربية قصيرة توضح شرط الدخول، واكتب خمس دقائق بدل M5 داخل النص العربي.

الدخول والوقف والهدف:
- entry أقرب نقطة تفعيل من السعر الحالي، وليس مستوى تاريخيًا بعيدًا.
- stop_loss خلف آخر قمة/قاع أو خلف الدعم/المقاومة التي تبطل السيناريو، وليس وقفًا ثابتًا.
- لا تجعل مسافة الوقف مبالغًا فيها لفريم M5؛ استخدم أقرب إبطال بنيوي واضح.
- target_1 هو الهدف الأقرب والمنطقي، ثم target_2 وtarget_3 إن ظهرت.
- لا تضع هدفًا تم تجاوزه بالفعل.

الرسم:
- pattern_lines وpattern_path وretest_box وfvg_boxes تكون إحداثياتها داخل chart_box نفسه: 0,0 أعلى يسار مساحة الشارت و1,1 أسفل يمينها.
- ارسم نموذجًا فقط إذا كان واضحًا، واكتب pattern_confidence بصدق.
- لا تنشئ خطوطًا طويلة عشوائية عبر الشارت.
- سهم واحد فقط؛ الأحمر للهبوط والأخضر للصعود.
- لا توجد لوحة جانبية أو سفلية.

الذاكرة المرجعية:
{memory_context(KNOWLEDGE_DIR)}
"""

    body = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": _data_url(path)},
        ]}],
        "text": {"format": {
            "type": "json_schema",
            "name": "saleem_nearest_single_trade",
            "strict": True,
            "schema": ANALYSIS_SCHEMA,
        }},
    }

    with httpx.Client(timeout=120) as client:
        response = client.post(
            OPENAI_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"خطأ خدمة التحليل ({response.status_code}): {response.text[:500]}")
    return _validate_single_trade(json.loads(_text(response.json())))


def analyze_chart_image(image_path: Path, symbol: str, timeframe: str) -> dict[str, Any]:
    analysis = _analyze(image_path)
    png = render_result(image_path, analysis)
    return {
        **analysis,
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "result_url": "data:image/png;base64," + base64.b64encode(png).decode(),
    }
