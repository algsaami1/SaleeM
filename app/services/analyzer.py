from __future__ import annotations

import base64
import json
import logging
import os
import random
import statistics
import time
from pathlib import Path
from datetime import datetime
from typing import Any

import httpx

from app.engine.memory_engine import memory_context
from app.engine.renderer import AxisCalibrationError, render_result, validate_uploaded_axis
from app.services.market_data import (
    MarketDataError,
    compact_market_context,
    fetch_market_data,
)

OPENAI_URL = "https://api.openai.com/v1/responses"
BASE_DIR = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
SPEC_PATH = BASE_DIR / "SALEEM_FINAL_SPEC.md"


def load_final_spec() -> str:
    """قراءة دستور SaleeM النهائي دون تعديله."""
    if not SPEC_PATH.exists():
        raise RuntimeError("ملف SALEEM_FINAL_SPEC.md غير موجود في المجلد الرئيسي للمشروع.")
    return SPEC_PATH.read_text(encoding="utf-8").strip()

CONFIRMED_PROBABILITY = 65
CONDITIONAL_PROBABILITY = 55
MAX_ENTRY_DISTANCE = 8.0
MIN_STOP_DISTANCE = 0.6
MAX_STOP_DISTANCE = 4.0
STOP_ATR_MULTIPLIER = 1.10

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
CANDLE = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "time": {"type": "string"},
        "open": {"type": "number"},
        "high": {"type": "number"},
        "low": {"type": "number"},
        "close": {"type": "number"},
    },
    "required": ["time", "open", "high", "low", "close"],
}
LEVEL = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "price": {"type": "number"},
        "strength": {"type": "integer", "minimum": 0, "maximum": 100},
        "touches": {"type": "integer", "minimum": 1, "maximum": 12},
    },
    "required": ["price", "strength", "touches"],
}
AXIS_LABEL = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "price": {"type": "number"},
        "y_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["price", "y_ratio"],
}

ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "chart_readable": {"type": "boolean"},
        "candles": {"type": "array", "items": CANDLE, "minItems": 0, "maxItems": 60},
        "direction": {"type": "string", "enum": ["صاعد", "هابط", "عرضي", "غير واضح"]},
        "buy_probability": {"type": "integer", "minimum": 5, "maximum": 95},
        "sell_probability": {"type": "integer", "minimum": 5, "maximum": 95},
        "setup_state": {"type": "string", "enum": ["مؤكد", "مشروط", "مراقبة", "غير صالح"]},
        "entry_kind": {"type": "string", "enum": ["مباشر", "اختراق", "إعادة اختبار", "مراقبة"]},
        "confirmation": {"type": "string"},
        "current_price": NUM_NULL,
        "current_price_y_ratio": NUM_NULL,
        "image_price_high": NUM_NULL,
        "image_price_low": NUM_NULL,
        "image_axis_labels": {"type": "array", "items": AXIS_LABEL, "maxItems": 20},
        "support_levels": {"type": "array", "items": LEVEL, "maxItems": 2},
        "resistance_levels": {"type": "array", "items": LEVEL, "maxItems": 2},
        "entry": NUM_NULL,
        "stop_loss": NUM_NULL,
        "stop_reason": {"type": "string"},
        "target_1": NUM_NULL,
        "target_2": NUM_NULL,
        "target_3": NUM_NULL,
        "pattern_type": {
            "type": "string",
            "enum": [
                "مثلث متماثل", "مثلث هابط", "مثلث صاعد", "وتد هابط", "وتد صاعد",
                "قناة هابطة", "قناة صاعدة", "قمتان", "قاعان", "كسر وإعادة اختبار", "لا يوجد",
            ],
        },
        "pattern_confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "pattern_lines": {"type": "array", "items": LINE, "maxItems": 4},
        "pattern_path": {"type": "array", "items": POINT, "maxItems": 12},
        "scenario": {"type": "string"},
        "note": {"type": "string"},
        "memory_matches": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
    },
    "required": [
        "chart_readable", "candles", "direction", "buy_probability", "sell_probability",
        "setup_state", "entry_kind", "confirmation", "current_price", "current_price_y_ratio", "image_price_high",
        "image_price_low", "image_axis_labels", "support_levels", "resistance_levels", "entry", "stop_loss",
        "stop_reason", "target_1", "target_2",
        "target_3", "pattern_type", "pattern_confidence", "pattern_lines", "pattern_path",
        "scenario", "note", "memory_matches",
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



def _normalize_candle_time(value: Any, index: int) -> str:
    text = str(value or "").strip()
    if not text:
        return f"شمعة {index + 1}"
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.isoformat()
    except ValueError:
        return text[:32]


def _normalize_candles(raw: Any) -> list[dict[str, Any]]:
    """تنظيف شموع السوق دون فرض عدد ثابت.

    الشموع المعروضة تأتي من مزود السوق، لذلك يقبل المحرك أي نافذة مفيدة
    متاحة ويكتفي بحد أعلى لحماية الرسم من الازدحام.
    """
    candles: list[dict[str, Any]] = []
    for index, item in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(item, dict):
            continue
        values = [_number(item.get(key)) for key in ("open", "high", "low", "close")]
        if any(value is None for value in values):
            continue
        open_, high, low, close = [float(value) for value in values]
        true_high = max(high, open_, close)
        true_low = min(low, open_, close)
        if true_high <= true_low:
            continue
        candles.append(
            {
                "time": _normalize_candle_time(item.get("time"), index),
                "open": round(open_, 2),
                "high": round(true_high, 2),
                "low": round(true_low, 2),
                "close": round(close, 2),
            }
        )

    candles = candles[-60:]
    if len(candles) < 6:
        raise RuntimeError("بيانات السوق المتاحة لا تكفي لرسم شارت واضح حاليًا.")

    ranges = [max(0.01, c["high"] - c["low"]) for c in candles]
    median_range = statistics.median(ranges)
    if median_range <= 0:
        raise RuntimeError("تعذر معايرة حركة شموع السوق.")

    # تجاهل شمعة شاذة بدل إسقاط التحليل بالكامل إذا كانت بقية بيانات المزود سليمة.
    filtered: list[dict[str, Any]] = []
    for candle in candles:
        if candle["high"] - candle["low"] <= median_range * 12:
            filtered.append(candle)
    if len(filtered) >= 6:
        candles = filtered

    return candles


def _atr(candles: list[dict[str, Any]], periods: int = 8) -> float:
    sample = candles[-periods:] if candles else []
    if not sample:
        return 2.0
    ranges = [max(0.01, float(c["high"]) - float(c["low"])) for c in sample]
    return sum(ranges) / len(ranges)


def _cluster_levels(
    candles: list[dict[str, Any]],
    kind: str,
    current: float,
) -> list[dict[str, Any]]:
    """اشتقاق مستويات فعلية من القمم والقيعان مع أولوية للـ pivots والحداثة."""
    if not candles:
        return []

    atr = max(0.01, _atr(candles))
    tolerance = max(0.25, atr * 0.32)
    side_tolerance = max(0.18, atr * 0.18)
    key = "low" if kind == "support" else "high"
    candidates: list[dict[str, Any]] = []

    for index, candle in enumerate(candles):
        price = float(candle[key])
        left = candles[max(0, index - 2):index]
        right = candles[index + 1:index + 3]
        neighbors = left + right
        if kind == "support":
            pivot = bool(neighbors) and price <= min(float(item["low"]) for item in neighbors)
            valid_side = price <= current + side_tolerance
        else:
            pivot = bool(neighbors) and price >= max(float(item["high"]) for item in neighbors)
            valid_side = price >= current - side_tolerance
        if valid_side:
            candidates.append({"price": price, "index": index, "pivot": pivot})

    clusters: list[list[dict[str, Any]]] = []
    for item in sorted(candidates, key=lambda value: float(value["price"])):
        for cluster in clusters:
            center = statistics.median(float(value["price"]) for value in cluster)
            if abs(float(item["price"]) - center) <= tolerance:
                cluster.append(item)
                break
        else:
            clusters.append([item])

    levels: list[dict[str, Any]] = []
    last_index = max(1, len(candles) - 1)
    for cluster in clusters:
        prices = [float(item["price"]) for item in cluster]
        center = float(statistics.median(prices))
        touches = len({int(item["index"]) for item in cluster})
        pivot_count = sum(1 for item in cluster if bool(item["pivot"]))
        latest_index = max(int(item["index"]) for item in cluster)
        recency = latest_index / last_index
        strength = int(round(_clip(38 + touches * 7 + pivot_count * 7 + recency * 10, 42, 92)))
        levels.append(
            {
                "price": round(center, 2),
                "strength": strength,
                "touches": min(12, max(1, touches)),
                "source": "market",
            }
        )

    return levels


def _normalize_levels(raw: Any, candles: list[dict[str, Any]], kind: str, current: float) -> list[dict[str, Any]]:
    """دمج مستويات النموذج والسوق وضمان ظهور أقرب مستويين بوضوح.

    إذا لم يوجد مستوى تاريخي على الجهة المطلوبة، نضيف مستوى تقديري منخفض القوة
    مبنيًا على ATR ونميّزه في الرسم بدل تسميته مقاومة/دعم قويًا.
    """
    atr = max(0.01, _atr(candles))
    side_tolerance = max(0.25, atr * 0.20)
    levels: list[dict[str, Any]] = []

    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        price = _number(item.get("price"))
        if price is None:
            continue
        if kind == "support" and price > current + side_tolerance:
            continue
        if kind == "resistance" and price < current - side_tolerance:
            continue
        levels.append(
            {
                "price": round(price, 2),
                "strength": max(35, min(95, int(item.get("strength") or 50))),
                "touches": max(1, min(12, int(item.get("touches") or 1))),
                "source": "model",
            }
        )

    levels.extend(_cluster_levels(candles, kind, current))

    # دمج المستويات المتقاربة مع الاحتفاظ بالأقوى والأحدث.
    merge_distance = max(0.30, atr * 0.32)
    levels.sort(
        key=lambda level: (
            -int(level.get("strength") or 0),
            abs(float(level["price"]) - current),
        )
    )
    merged: list[dict[str, Any]] = []
    for level in levels:
        if any(abs(float(level["price"]) - float(other["price"])) <= merge_distance for other in merged):
            continue
        merged.append(level)

    # أقرب القمم/القيعان الفعلية كخطة احتياطية، حتى لو كانت لمسة واحدة فقط.
    key = "low" if kind == "support" else "high"
    raw_prices = sorted(
        (float(candle[key]) for candle in candles),
        reverse=(kind == "support"),
    )
    for price in raw_prices:
        valid_side = price <= current + side_tolerance if kind == "support" else price >= current - side_tolerance
        if not valid_side:
            continue
        if any(abs(price - float(other["price"])) <= merge_distance for other in merged):
            continue
        merged.append(
            {
                "price": round(price, 2),
                "strength": 44,
                "touches": 1,
                "source": "market",
            }
        )
        if len(merged) >= 2:
            break

    # لا نخفي خطوط الجهة المقابلة إذا كان السعر عند قمة/قاع جديد تمامًا.
    # نستخدم مستوى تقديري صريح منخفض القوة بدل اختلاق مستوى تاريخي.
    step = max(0.55, atr * 0.90)
    projection_index = 0
    while len(merged) < 2:
        projection_index += 1
        distance = step * (1.0 + 0.85 * (projection_index - 1))
        price = current - distance if kind == "support" else current + distance
        merged.append(
            {
                "price": round(price, 2),
                "strength": 40,
                "touches": 0,
                "source": "projected",
            }
        )

    # الأقرب أولًا مع المحافظة على الجهة الصحيحة.
    merged.sort(key=lambda level: abs(float(level["price"]) - current))
    return merged[:2]


def _normalize_probabilities(data: dict[str, Any]) -> tuple[int, int]:
    """تطبيع احتمالي الشراء والبيع بدون افتراض جهة افتراضية.

    إذا أعاد النموذج القيمتين نستخدمهما معًا ثم نعيد موازنتهما إلى 100٪.
    وعند غياب القيم أو فسادها نبدأ من 50/50 بدل ترجيح الشراء.
    """
    def parse(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if not 0 <= parsed <= 100:
            return None
        return parsed

    buy_raw = parse(data.get("buy_probability"))
    sell_raw = parse(data.get("sell_probability"))
    if buy_raw is None and sell_raw is None:
        return 50, 50
    if buy_raw is None:
        buy_raw = 100.0 - float(sell_raw)
    if sell_raw is None:
        sell_raw = 100.0 - float(buy_raw)

    total = max(1.0, float(buy_raw) + float(sell_raw))
    buy = int(round(float(buy_raw) * 100.0 / total))
    buy = max(5, min(95, buy))
    sell = 100 - buy
    return buy, sell



def _apply_level_pressure(
    candles: list[dict[str, Any]],
    current: float,
    supports: list[dict[str, Any]],
    resistances: list[dict[str, Any]],
    direction: str,
    buy: int,
    sell: int,
) -> tuple[str, int, int, dict[str, Any]]:
    """تعديل الاحتمالات عند الاصطدام بدعم/مقاومة قريبة بدل فرض اتجاه.

    المستويات التقديرية لا تُستخدم كدليل ضغط؛ هي للرسم فقط عند غياب مستوى
    تاريخي واضح. أما المستويات الفعلية فتؤثر حسب القرب والقوة وذيول الرفض.
    """
    atr = max(0.01, _atr(candles))
    recent = candles[-2:] if candles else []
    last = candles[-1] if candles else None
    buy_adj = float(buy)
    sell_adj = float(sell)
    context: dict[str, Any] = {
        "resistance_pressure": 0,
        "support_pressure": 0,
        "nearest_resistance": None,
        "nearest_support": None,
    }

    actual_resistances = [
        level for level in resistances
        if str(level.get("source") or "") != "projected" and float(level["price"]) >= current - atr * 0.20
    ]
    actual_supports = [
        level for level in supports
        if str(level.get("source") or "") != "projected" and float(level["price"]) <= current + atr * 0.20
    ]

    if actual_resistances:
        resistance = min(actual_resistances, key=lambda item: abs(float(item["price"]) - current))
        price = float(resistance["price"])
        distance_atr = max(0.0, price - current) / atr
        strength = int(resistance.get("strength") or 50)
        rejection = 0.0
        for candle in recent:
            body = max(0.02, abs(float(candle["close"]) - float(candle["open"])))
            upper_wick = max(0.0, float(candle["high"]) - max(float(candle["open"]), float(candle["close"])))
            if float(candle["close"]) <= price + atr * 0.10:
                rejection = max(rejection, upper_wick / body)
        if distance_atr <= 1.15 and (last is None or float(last["close"]) < price + atr * 0.15):
            pressure = 4 + max(0, strength - 55) // 6
            if distance_atr <= 0.55:
                pressure += 4
            if rejection >= 0.8:
                pressure += min(6, int(rejection * 2))
            pressure = max(0, min(16, pressure))
            buy_adj -= pressure
            sell_adj += pressure
            context["resistance_pressure"] = pressure
            context["nearest_resistance"] = round(price, 2)

    if actual_supports:
        support = min(actual_supports, key=lambda item: abs(float(item["price"]) - current))
        price = float(support["price"])
        distance_atr = max(0.0, current - price) / atr
        strength = int(support.get("strength") or 50)
        rejection = 0.0
        for candle in recent:
            body = max(0.02, abs(float(candle["close"]) - float(candle["open"])))
            lower_wick = max(0.0, min(float(candle["open"]), float(candle["close"])) - float(candle["low"]))
            if float(candle["close"]) >= price - atr * 0.10:
                rejection = max(rejection, lower_wick / body)
        if distance_atr <= 1.15 and (last is None or float(last["close"]) > price - atr * 0.15):
            pressure = 4 + max(0, strength - 55) // 6
            if distance_atr <= 0.55:
                pressure += 4
            if rejection >= 0.8:
                pressure += min(6, int(rejection * 2))
            pressure = max(0, min(16, pressure))
            sell_adj -= pressure
            buy_adj += pressure
            context["support_pressure"] = pressure
            context["nearest_support"] = round(price, 2)

    total = max(1.0, buy_adj + sell_adj)
    buy_final = int(round(_clip(buy_adj * 100.0 / total, 5, 95)))
    sell_final = 100 - buy_final
    margin = abs(buy_final - sell_final)

    if margin < 12:
        adjusted_direction = "غير واضح"
    else:
        adjusted_direction = "صاعد" if buy_final > sell_final else "هابط"

    # لا نقلب اتجاهًا قويًا بمجرد ضغط صغير؛ نجعله مراقبة عند التعارض المحدود.
    if direction in {"صاعد", "هابط"} and adjusted_direction != direction and margin < 18:
        adjusted_direction = "غير واضح"

    return adjusted_direction, buy_final, sell_final, context

def _clip(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _market_frame_signal(candles: Any) -> dict[str, Any]:
    """تلخيص اتجاه فريم واحد من بيانات OHLC الفعلية."""
    valid: list[dict[str, float]] = []
    for item in candles if isinstance(candles, list) else []:
        if not isinstance(item, dict):
            continue
        values = [_number(item.get(key)) for key in ("open", "high", "low", "close")]
        if any(value is None for value in values):
            continue
        open_, high, low, close = [float(value) for value in values]
        valid.append(
            {
                "open": open_,
                "high": max(high, open_, close),
                "low": min(low, open_, close),
                "close": close,
            }
        )

    if len(valid) < 24:
        return {"direction": "غير واضح", "score": 0.0, "confidence": 0}

    ranges = [max(0.01, candle["high"] - candle["low"]) for candle in valid[-40:]]
    atr = max(0.01, sum(ranges) / len(ranges))
    closes = [candle["close"] for candle in valid]
    fast = sum(closes[-8:]) / 8
    slow = sum(closes[-21:]) / 21
    recent_move = (closes[-1] - closes[-10]) / atr
    broad_index = max(0, len(closes) - 40)
    broad_move = (closes[-1] - closes[broad_index]) / atr
    score = _clip(
        ((fast - slow) / atr) * 0.50
        + recent_move * 0.30
        + broad_move * 0.20,
        -3.0,
        3.0,
    )

    if score > 0.20:
        direction = "صاعد"
    elif score < -0.20:
        direction = "هابط"
    else:
        direction = "عرضي"

    confidence = int(round(_clip(48 + abs(score) * 18, 48, 90)))
    if direction == "عرضي":
        confidence = int(round(_clip(62 - abs(score) * 20, 50, 62)))
    return {
        "direction": direction,
        "score": round(score, 3),
        "confidence": confidence,
        "last_close": round(closes[-1], 3),
    }


def _build_market_summary(market_data: dict[str, Any]) -> dict[str, Any]:
    frames = market_data.get("frames") if isinstance(market_data, dict) else None
    frame_signals: dict[str, dict[str, Any]] = {}
    for timeframe in ("H4", "H1", "M15", "M5"):
        candles = frames.get(timeframe) if isinstance(frames, dict) else None
        frame_signals[timeframe] = _market_frame_signal(candles)

    weights = {"H4": 0.32, "H1": 0.30, "M15": 0.23, "M5": 0.15}
    weighted_score = sum(
        float(frame_signals[frame].get("score") or 0.0) * weight
        for frame, weight in weights.items()
    )
    if weighted_score > 0.20:
        direction = "صاعد"
    elif weighted_score < -0.20:
        direction = "هابط"
    else:
        direction = "عرضي"

    if direction in {"صاعد", "هابط"}:
        aligned_count = sum(
            1
            for item in frame_signals.values()
            if item.get("direction") == direction
        )
        alignment = round(100 * aligned_count / max(1, len(frame_signals)))
    else:
        alignment = 50

    m5_candles = frames.get("M5") if isinstance(frames, dict) else None
    m5_latest_candle_time = (
        m5_candles[-1].get("time")
        if isinstance(m5_candles, list) and m5_candles and isinstance(m5_candles[-1], dict)
        else market_data.get("latest_candle_time")
    )

    return {
        "source": market_data.get("source"),
        "symbol": market_data.get("symbol"),
        "timezone": market_data.get("timezone") or "Asia/Muscat",
        "fetched_at": market_data.get("fetched_at"),
        "latest_candle_time": market_data.get("latest_candle_time"),
        "m5_latest_candle_time": m5_latest_candle_time,
        "direction": direction,
        "score": round(weighted_score, 3),
        "alignment": int(alignment),
        "frames": frame_signals,
        "cache": market_data.get("cache"),
        "warnings": market_data.get("warnings") or [],
    }


def _choose_direction(
    data: dict[str, Any],
    candles: list[dict[str, Any]],
    buy: int,
    sell: int,
    market_summary: dict[str, Any] | None = None,
) -> tuple[str, int, int]:
    """اختيار غير منحاز للاتجاه مع إعطاء الفريمات العليا وزنها الحقيقي.

    H4 يحدد الاتجاه العام، H1 البنية، M15 التفعيل، وM5 التوقيت.
    عند ضعف الفارق أو تعارض H4/H1 نعيد اتجاهًا غير واضح بدل فرض BUY/SELL.
    """
    atr = max(0.01, _atr(candles))
    full_move = _clip((float(candles[-1]["close"]) - float(candles[0]["close"])) / atr, -3.0, 3.0)
    recent_move = _clip((float(candles[-1]["close"]) - float(candles[-6]["close"])) / atr, -3.0, 3.0)
    model_score = _clip((buy - sell) / 45.0, -2.0, 2.0)
    m5_score = full_move * 0.42 + recent_move * 0.58

    frames = (market_summary or {}).get("frames") if isinstance(market_summary, dict) else {}
    frame_weights = {"H4": 0.36, "H1": 0.30, "M15": 0.22, "M5": 0.12}
    frame_score = 0.0
    frame_weight_used = 0.0
    for frame, weight in frame_weights.items():
        item = frames.get(frame) if isinstance(frames, dict) else None
        if not isinstance(item, dict):
            continue
        try:
            score = float(item.get("score") or 0.0)
        except (TypeError, ValueError):
            continue
        confidence = max(0.35, min(1.0, float(item.get("confidence") or 50) / 100.0))
        frame_score += _clip(score, -3.0, 3.0) * weight * confidence
        frame_weight_used += weight * confidence
    if frame_weight_used:
        frame_score /= frame_weight_used
    elif isinstance(market_summary, dict):
        try:
            frame_score = float(market_summary.get("score") or 0.0)
        except (TypeError, ValueError):
            frame_score = 0.0

    # النموذج يساهم، لكن لا يستطيع منفردًا فرض الاتجاه.
    combined = model_score * 0.15 + m5_score * 0.28 + frame_score * 0.57

    h4 = str((frames.get("H4") or {}).get("direction") or "غير واضح") if isinstance(frames, dict) else "غير واضح"
    h1 = str((frames.get("H1") or {}).get("direction") or "غير واضح") if isinstance(frames, dict) else "غير واضح"
    higher_conflict = h4 in {"صاعد", "هابط"} and h1 in {"صاعد", "هابط"} and h4 != h1

    # منطقة حياد حقيقية؛ لا تحويل تلقائي إلى شراء أو بيع.
    neutral_threshold = 0.36 if higher_conflict else 0.30
    if abs(combined) < neutral_threshold:
        edge = int(round(min(6.0, abs(combined) * 18.0)))
        if combined >= 0:
            return "غير واضح", 50 + edge, 50 - edge
        return "غير واضح", 50 - edge, 50 + edge

    direction = "صاعد" if combined > 0 else "هابط"
    raw_probability = int(round(_clip(52 + abs(combined) * 16, 52, 84)))

    alignment = int((market_summary or {}).get("alignment") or 50) if isinstance(market_summary, dict) else 50
    higher_direction = str((market_summary or {}).get("direction") or "عرضي") if isinstance(market_summary, dict) else "عرضي"
    if higher_conflict:
        raw_probability = min(raw_probability, 58)
    elif higher_direction in {"صاعد", "هابط"} and higher_direction != direction:
        raw_probability = min(raw_probability, 59)
    elif h4 == direction and h1 == direction:
        raw_probability = min(90, raw_probability + max(0, alignment - 50) // 10)
    elif h4 in {"صاعد", "هابط"} and h4 != direction:
        raw_probability = min(raw_probability, 60)

    if isinstance(market_summary, dict) and market_summary.get("warnings"):
        raw_probability = min(raw_probability, 60)

    buy_final = raw_probability if direction == "صاعد" else 100 - raw_probability
    sell_final = 100 - buy_final
    return direction, buy_final, sell_final


def _nearest_entry(
    data: dict[str, Any], direction: str, current: float,
    supports: list[dict[str, Any]], resistances: list[dict[str, Any]],
) -> tuple[float, str, str]:
    proposed = _number(data.get("entry"))
    if proposed is not None and abs(proposed - current) <= MAX_ENTRY_DISTANCE:
        return round(proposed, 2), str(data.get("entry_kind") or "مراقبة"), str(data.get("confirmation") or "انتظار تأكيد شمعة خمس دقائق")

    candidates: list[tuple[float, str, str]] = []
    if direction == "صاعد":
        for level in resistances:
            price = float(level["price"])
            if current <= price <= current + MAX_ENTRY_DISTANCE:
                candidates.append((price, "اختراق", "إغلاق شمعة خمس دقائق فوق المقاومة"))
        for level in supports:
            price = float(level["price"])
            if current - MAX_ENTRY_DISTANCE <= price <= current:
                candidates.append((price, "إعادة اختبار", "ثبات الدعم وظهور شمعة صاعدة"))
    else:
        for level in supports:
            price = float(level["price"])
            if current - MAX_ENTRY_DISTANCE <= price <= current:
                candidates.append((price, "اختراق", "إغلاق شمعة خمس دقائق تحت الدعم"))
        for level in resistances:
            price = float(level["price"])
            if current <= price <= current + MAX_ENTRY_DISTANCE:
                candidates.append((price, "إعادة اختبار", "رفض المقاومة وظهور شمعة هابطة"))

    if candidates:
        return min(candidates, key=lambda item: abs(item[0] - current))
    return round(current, 2), "مراقبة", "انتظار شمعة تأكيد خمس دقائق عند السعر الحالي"


def _short_confirmation(direction: str, entry_kind: str, original: str) -> str:
    """إرجاع شرط دخول قصير وثابت يصلح للرسم العربي."""
    normalized = " ".join(str(original or "").split())
    templates = {
        ("صاعد", "اختراق"): "إغلاق فوق المقاومة ثم إعادة اختبار",
        ("صاعد", "إعادة اختبار"): "ثبات فوق الدعم مع شمعة صاعدة",
        ("هابط", "اختراق"): "كسر الدعم ثم إعادة اختبار فاشلة",
        ("هابط", "إعادة اختبار"): "رفض واضح من المقاومة",
    }
    if entry_kind == "مراقبة":
        return "انتظار شمعة تأكيد عند مستوى التفعيل"
    preferred = templates.get((direction, entry_kind))
    if preferred:
        return preferred
    if len(normalized) <= 52:
        return normalized or "انتظار تأكيد واضح"
    return "انتظار تأكيد واضح عند مستوى الدخول"


def _validated_stop(
    data: dict[str, Any], direction: str, entry: float, candles: list[dict[str, Any]],
    supports: list[dict[str, Any]], resistances: list[dict[str, Any]],
) -> tuple[float, str]:
    atr = max(0.01, _atr(candles))
    dynamic_max = max(1.20, min(MAX_STOP_DISTANCE, atr * STOP_ATR_MULTIPLIER))
    buffer = max(0.12, min(0.45, atr * 0.10))
    proposed = _number(data.get("stop_loss"))
    proposed_reason = str(data.get("stop_reason") or "خلف منطقة الإبطال القريبة")

    choices: list[tuple[float, str]] = []

    def add_choice(stop: float, reason: str) -> None:
        distance = abs(stop - entry)
        correct_side = (direction == "صاعد" and stop < entry) or (direction == "هابط" and stop > entry)
        if correct_side and MIN_STOP_DISTANCE <= distance <= dynamic_max:
            choices.append((round(stop, 2), reason))

    if proposed is not None:
        add_choice(proposed, proposed_reason)

    recent = candles[-5:]
    if direction == "صاعد":
        recent_low = min(float(candle["low"]) for candle in recent) - buffer
        add_choice(recent_low, "أسفل أقرب قاع محلي من آخر خمس شمعات")
        for level in supports:
            price = float(level["price"])
            if price < entry:
                add_choice(price - buffer, "أسفل أقرب دعم بنيوي")
    else:
        recent_high = max(float(candle["high"]) for candle in recent) + buffer
        add_choice(recent_high, "فوق أقرب قمة محلية من آخر خمس شمعات")
        for level in resistances:
            price = float(level["price"])
            if price > entry:
                add_choice(price + buffer, "فوق أقرب مقاومة بنيوية")

    if choices:
        stop, reason = min(choices, key=lambda item: abs(item[0] - entry))
        return stop, reason

    fallback_distance = max(MIN_STOP_DISTANCE, min(dynamic_max, atr * 0.85))
    if direction == "صاعد":
        return round(entry - fallback_distance, 2), "أسفل منطقة الإبطال القريبة حسب تذبذب M5"
    return round(entry + fallback_distance, 2), "فوق منطقة الإبطال القريبة حسب تذبذب M5"



def _validated_targets(
    data: dict[str, Any],
    direction: str,
    entry: float,
    stop: float,
    supports: list[dict[str, Any]],
    resistances: list[dict[str, Any]],
) -> list[float]:
    candidates: list[float] = []

    # المستويات المقابلة أولًا لأنها أكثر منطقية من أهداف عشوائية.
    level_source = resistances if direction == "صاعد" else supports
    for level in level_source:
        value = _number(level.get("price"))
        if value is None:
            continue
        valid = (direction == "صاعد" and value > entry) or (direction == "هابط" and value < entry)
        if valid:
            candidates.append(round(value, 2))

    for key in ("target_1", "target_2", "target_3"):
        value = _number(data.get(key))
        if value is None:
            continue
        valid = (direction == "صاعد" and value > entry) or (direction == "هابط" and value < entry)
        if valid:
            candidates.append(round(value, 2))

    risk = max(MIN_STOP_DISTANCE, abs(entry - stop))
    for multiplier in (1.0, 1.7, 2.5, 3.2):
        value = entry + risk * multiplier if direction == "صاعد" else entry - risk * multiplier
        candidates.append(round(value, 2))

    unique: list[float] = []
    for value in sorted(candidates, reverse=(direction == "هابط")):
        if all(abs(value - existing) >= max(0.25, risk * 0.15) for existing in unique):
            unique.append(value)
        if len(unique) == 3:
            break

    # حماية إضافية من التقريب أو تكرار المستويات: لا نوقف التحليل بسبب هدف ناقص.
    multiplier = 4.0
    while len(unique) < 3:
        value = entry + risk * multiplier if direction == "صاعد" else entry - risk * multiplier
        value = round(value, 2)
        if all(abs(value - existing) >= max(0.25, risk * 0.15) for existing in unique):
            unique.append(value)
        multiplier += 0.8
    return unique[:3]


def _normalize_axis_labels(labels: Any, *, image_high: float | None = None, image_low: float | None = None) -> list[dict[str, float]]:
    result: list[dict[str, float]] = []
    if not isinstance(labels, list):
        labels = []
    for item in labels:
        if not isinstance(item, dict):
            continue
        price = _number(item.get("price"))
        y_ratio = _number(item.get("y_ratio"))
        if price is None or y_ratio is None:
            continue
        y_ratio = max(0.0, min(1.0, float(y_ratio)))
        # لا نحذف رقمًا واضحًا بسبب خطأ محتمل في قراءة أعلى/أدنى المحور؛
        # السلسلة الكاملة للأرقام أهم لأنها تحدد مقياس الصورة الحقيقي.
        result.append({"price": round(float(price), 2), "y_ratio": round(y_ratio, 4)})
    result.sort(key=lambda item: item["y_ratio"])
    dedup: list[dict[str, float]] = []
    for item in result:
        if dedup and abs(dedup[-1]["y_ratio"] - item["y_ratio"]) < 0.015:
            if abs(item["price"] - dedup[-1]["price"]) > 0.02:
                dedup[-1] = item
            continue
        dedup.append(item)
    # نتأكد أن الأسعار تنخفض عمومًا كلما نزلنا لأسفل.
    cleaned: list[dict[str, float]] = []
    last_price: float | None = None
    for item in dedup:
        price = item["price"]
        if last_price is not None and price >= last_price:
            continue
        cleaned.append(item)
        last_price = price
    return cleaned[:20]


def _validate_analysis(
    data: dict[str, Any],
    market_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # القراءة من الصورة هي الأولوية، لكن فشلها لا يوقف التحليل بالكامل.
    # نحفظ القيمة الخام في مفتاح داخلي حتى لا نخلطها بسعر السوق الاحتياطي.
    image_current = _number(data.get("_image_current_price"))
    if image_current is None and "_image_current_price" not in data:
        image_current = _number(data.get("current_price"))
    image_was_readable = bool(data.get("_image_chart_readable", data.get("chart_readable")))

    candles = _normalize_candles(data.get("candles"))
    market_close = float(candles[-1]["close"])
    current = float(image_current) if image_current is not None else market_close

    current_price_y_ratio = _number(data.get("current_price_y_ratio"))
    if current_price_y_ratio is not None:
        current_price_y_ratio = max(0.0, min(1.0, float(current_price_y_ratio)))
    if image_current is None:
        # A line position without a price read from the image is not a reliable
        # anchor; the renderer will fall back to its normal market transform.
        current_price_y_ratio = None

    image_price_high = _number(data.get("image_price_high"))
    image_price_low = _number(data.get("image_price_low"))
    image_axis_labels = _normalize_axis_labels(data.get("image_axis_labels"))
    if image_price_high is not None and image_price_high <= current:
        image_price_high = None
    if image_price_low is not None and image_price_low >= current:
        image_price_low = None

    # عند توفر سلسلة المحور نستخدم أول وآخر رقم واضحين لتصحيح أي قراءة
    # منفصلة خاطئة للحدين، من دون إجبارهما على حواف الصورة.
    if len(image_axis_labels) >= 2:
        top_axis_price = float(image_axis_labels[0]["price"])
        bottom_axis_price = float(image_axis_labels[-1]["price"])
        if image_price_high is None or image_price_high < top_axis_price:
            image_price_high = top_axis_price
        if image_price_low is None or image_price_low > bottom_axis_price:
            image_price_low = bottom_axis_price

    # إذا لم يقرأ النموذج حدي المحور، نستخدم نطاق الشموع المجلوبة بعد مواءمتها.
    # هذا يمنع توقف الرسم ويظل محور النتيجة متوازنًا مع هامش علوي وسفلي.
    if image_price_high is None:
        image_price_high = max(float(candle["high"]) for candle in candles)
    if image_price_low is None:
        image_price_low = min(float(candle["low"]) for candle in candles)
    buy, sell = _normalize_probabilities(data)
    supports = _normalize_levels(data.get("support_levels"), candles, "support", current)
    resistances = _normalize_levels(data.get("resistance_levels"), candles, "resistance", current)
    direction, buy, sell = _choose_direction(data, candles, buy, sell, market_summary)
    direction, buy, sell, level_pressure = _apply_level_pressure(
        candles, current, supports, resistances, direction, buy, sell
    )
    probability = max(buy, sell) if direction == "غير واضح" else (buy if direction == "صاعد" else sell)

    # في حالة الغموض نحتفظ بسيناريو مراقبة فقط ولا نعرض صفقة مؤكدة مختلقة.
    working_direction = direction
    if working_direction not in {"صاعد", "هابط"}:
        working_direction = "صاعد" if buy >= sell else "هابط"

    entry, entry_kind, confirmation = _nearest_entry(data, working_direction, current, supports, resistances)
    confirmation = _short_confirmation(working_direction, entry_kind, confirmation)
    if direction not in {"صاعد", "هابط"}:
        confirmation = "انتظار توافق H4 وH1 وظهور شمعة تأكيد"
    stop, stop_reason = _validated_stop(data, working_direction, entry, candles, supports, resistances)
    targets = _validated_targets(data, working_direction, entry, stop, supports, resistances)

    frames = (market_summary or {}).get("frames") if isinstance(market_summary, dict) else {}
    h4_direction = str((frames.get("H4") or {}).get("direction") or "غير واضح") if isinstance(frames, dict) else "غير واضح"
    h1_direction = str((frames.get("H1") or {}).get("direction") or "غير واضح") if isinstance(frames, dict) else "غير واضح"
    alignment = int((market_summary or {}).get("alignment") or 0) if isinstance(market_summary, dict) else 0
    higher_aligned = direction in {"صاعد", "هابط"} and h4_direction == direction and h1_direction == direction
    warnings = bool((market_summary or {}).get("warnings")) if isinstance(market_summary, dict) else False
    geometry_valid = (
        (working_direction == "صاعد" and stop < entry and all(target > entry for target in targets))
        or (working_direction == "هابط" and stop > entry and all(target < entry for target in targets))
    )

    model_state = str(data.get("setup_state") or "مراقبة")
    opposing_pressure = (
        int(level_pressure.get("resistance_pressure") or 0)
        if working_direction == "صاعد"
        else int(level_pressure.get("support_pressure") or 0)
    )
    if direction not in {"صاعد", "هابط"} or probability < 58 or entry_kind == "مراقبة":
        draw_mode = "watch"
    elif (
        probability >= 72
        and model_state == "مؤكد"
        and higher_aligned
        and alignment >= 75
        and geometry_valid
        and not warnings
        and opposing_pressure < 8
    ):
        draw_mode = "confirmed"
    else:
        draw_mode = "conditional"

    pattern_confidence = max(0, min(100, int(data.get("pattern_confidence") or 0)))
    if pattern_confidence < 60:
        data["pattern_lines"] = []
        data["pattern_path"] = []
        data["pattern_type"] = "لا يوجد"

    scenario = " ".join(str(data.get("scenario") or "").split())[:70]
    if draw_mode == "watch":
        scenario = "مراقبة حتى تتوافق الفريمات وتظهر شمعة تأكيد"
    elif not scenario:
        scenario = "استمرار السيناريو بعد تحقق شرط الدخول"

    data.update(
        {
            "chart_readable": bool(image_was_readable and image_current is not None),
            "candles": candles,
            "current_price": round(current, 2),
            "current_price_y_ratio": round(current_price_y_ratio, 4) if current_price_y_ratio is not None else None,
            "current_price_source": "chart_image" if image_current is not None else "market_fallback",
            "price_range_source": "chart_image" if _number(data.get("image_price_high")) is not None and _number(data.get("image_price_low")) is not None else "market_candles_fallback",
            "image_price_high": round(image_price_high, 2) if image_price_high is not None else None,
            "image_price_low": round(image_price_low, 2) if image_price_low is not None else None,
            "image_axis_labels": image_axis_labels,
            "market_last_close": round(market_close, 2),
            "buy_probability": buy,
            "sell_probability": sell,
            "direction": direction,
            "analysis_direction": working_direction,
            "trade_side": "مراقبة" if draw_mode == "watch" else ("شراء" if working_direction == "صاعد" else "بيع"),
            "trade_probability": probability,
            "draw_mode": draw_mode,
            "support_levels": supports,
            "resistance_levels": resistances,
            "entry": entry,
            "entry_kind": entry_kind,
            "confirmation": confirmation,
            "stop_loss": stop,
            "stop_reason": " ".join(stop_reason.split())[:52],
            "target_1": targets[0],
            "target_2": targets[1],
            "target_3": targets[2],
            "scenario": scenario,
            "note": " ".join(str(data.get("note") or "").split())[:80],
            "market_data_source": (market_summary or {}).get("source"),
            "market_data_fetched_at": (market_summary or {}).get("fetched_at"),
            "market_timezone": (market_summary or {}).get("timezone", "Asia/Muscat"),
            "market_latest_candle_time": (market_summary or {}).get("latest_candle_time"),
            "market_m5_latest_candle_time": (market_summary or {}).get("m5_latest_candle_time"),
            "market_direction": (market_summary or {}).get("direction", "غير واضح"),
            "frame_alignment": alignment,
            "frame_directions": frames if isinstance(frames, dict) else {},
            "level_pressure": level_pressure,
            "market_data_cache": (market_summary or {}).get("cache", {}),
            "market_data_warnings": (market_summary or {}).get("warnings", []),
        }
    )
    return data


def _analyze(path: Path) -> dict[str, Any]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("متغير OPENAI_API_KEY غير موجود في Railway.")

    try:
        market_data = fetch_market_data()
        context_candles = max(24, min(80, int(os.getenv("MARKET_CONTEXT_CANDLES", "40"))))
        market_context = compact_market_context(
            market_data,
            candles_per_frame=context_candles,
        )
        # نرسل نافذة سوق مرنة لـ M5؛ الرسم النهائي سيستخدم بيانات المزود نفسها.
        market_frames = market_context.get("frames", {})
        if isinstance(market_frames, dict) and isinstance(market_frames.get("M5"), list):
            prompt_m5_count = max(20, min(60, int(os.getenv("PROMPT_M5_CANDLES", "40"))))
            market_frames["M5"] = market_frames["M5"][-prompt_m5_count:]
        market_summary = _build_market_summary(market_data)
    except MarketDataError as exc:
        raise RuntimeError(f"تعذر جلب بيانات الفريمات: {exc}") from exc

    prompt = f"""أنت محرك SaleeM Gold Analyst المتخصص في الذهب XAUUSD، وتنفذ الصفقة على فريم خمس دقائق بعد مراجعة الفريمات العليا.

===== الدستور النهائي الملزم =====
{load_final_spec()}
===== نهاية الدستور =====

===== بيانات السوق الحية المجلوبة تلقائيًا =====
الملخص الحسابي للفريمات:
{json.dumps(market_summary, ensure_ascii=False)}

شموع السوق من Twelve Data:
{json.dumps(market_context, ensure_ascii=False)}
===== نهاية بيانات السوق =====

استخدم H4 لتحديد الاتجاه الرئيسي، وH1 لبنية السوق، وM15 لمنطقة التفعيل، وM5 لتوقيت الدخول.
لا تستنتج اتجاه الفريمات العليا من صورة M5؛ بيانات Twelve Data هي مرجع الاتجاه والبنية فقط.
قد يختلف سعر Twelve Data قليلًا عن وسيط المستخدم، لذلك استخدم صورة المستخدم مرجعًا نهائيًا لأسعار الدخول والوقف والأهداف، واستخدم البيانات الخارجية لتأكيد الاتجاه.
إذا تعارض H4 وH1 مع صفقة M5، اخفض الاحتمال واجعل setup_state مشروطًا أو مراقبة، ولا تصف الصفقة بأنها مؤكدة.

اقرأ صورة الشارت المرفوعة لاستخراج بيانات محور السعر:
1) current_price: السعر الحالي الظاهر في ملصق السعر بجانب آخر شمعة.
2) current_price_y_ratio: موضع الخط الأفقي المرتبط بالسعر الحالي داخل منطقة الشارت المرئية؛ 0.0 أعلى الشارت و1.0 أسفله. خذ مركز خط السعر نفسه، وليس مركز الصورة أو آخر شمعة. إذا لم يظهر خط السعر بوضوح فأعد null.
3) image_price_high: أعلى سعر ظاهر في أعلى محور الأسعار داخل الصورة.
4) image_price_low: أدنى سعر ظاهر في أسفل محور الأسعار داخل الصورة.
5) image_axis_labels: أعد نقاط الارتكاز اللازمة لبناء محور الصورة حسابيًا. لكل عنصر أعد:
   - price: الرقم الظاهر على محور السعر في الصورة.
   - y_ratio: موضع مركز الرقم الرأسي داخل منطقة الشارت المرئية، حيث 0.0 أعلى الشارت و1.0 أسفله.
   المطلوب بالترتيب: أعلى رقم ظاهر كاملًا، ثم الرقم الذي تحته مباشرة بلا تخطي، ثم أدنى رقم ظاهر كاملًا. أعد هذه العناصر الثلاثة على الأقل، ويمكن إرجاع الأرقام الوسطية الواضحة أيضًا، لكن البرنامج سيعتمد أول عنصرين لحساب الخطوة السعرية والمسافة الرأسية وسيستخدم العنصر الأخير حدًا سفليًا للتحقق والتوقف. لا تستخدم رقمًا مقصوصًا عند الحافة، ولا تختَر الرقم الثاني من منتصف السلسلة، ولا تستنتج أرقامًا غير ظاهرة.
تأكد أن image_price_low < current_price < image_price_high. إذا تعذر رقم الحد الأعلى أو الأدنى فقط فأعده null، لكن ابذل محاولة دقيقة لقراءته.
لا تعِد بناء الشموع من الصورة؛ أعد candles=[] لأن البرنامج سيستخدم شموع M5 الحقيقية من Twelve Data عند الرسم.
السعر الحالي في current_price يجب أن يكون من صورة المستخدم، وليس من آخر إغلاق في بيانات Twelve Data.
يجب أن يطابق current_price_y_ratio الخط الأفقي الحقيقي الخارج من ملصق السعر الحالي، لأن البرنامج سيستخدمه كنقطة تثبيت لجميع خطوط الرسم ومحور السعر الأيمن.
اجعل chart_readable=false إذا تعذرت قراءة السعر الحالي. وإذا لم تستطع قراءة أول سعر كامل، والسعر الذي يليه مباشرة، وأدنى سعر كامل، فأعد image_axis_labels=[] ولا تخمّن الأرقام؛ التطبيق سيطلب من المستخدم تفعيل Auto-scale والتقاط صورة جديدة بدل رسم محور تقريبي.

التحليل المطلوب:
- اختر سيناريو واحدًا فقط، وهو الأعلى احتمالًا.
- BUY وSELL مجموعهما 100، ولا تستخدم 0 أو 100.
- عند ضعف التأكيد، لا تقل لا توجد صفقة؛ أعطِ أقرب نقطة تفعيل مشروطة مع اتجاه متوقع.
- حدد أقرب دعمين وأقرب مقاومتين مهمين اعتمادًا على بيانات السوق المرفقة وموضع السعر الظاهر في الصورة.
- strength من 0 إلى 100 حسب عدد اللمسات، قوة الرفض، حداثة المستوى، وتوافقه مع بنية السوق.
- touches عدد اللمسات أو الاختبارات الواضحة.
- اجمع المستويات المتقاربة، ولا تعد المستوى نفسه مرتين.
- entry قريب وواقعي، بعد اختراق أو كسر أو إعادة اختبار أو تأكيد واضح.
- stop_loss قريب من الدخول ومن بنية الشارت: خلف أقرب قمة/قاع محلي خلال آخر خمس شمعات أو أقرب مستوى إبطال. لا تستخدم قمة أو قاع بعيدة. غالبًا تكون المسافة بين 0.6 و4.0 دولار حسب تذبذب M5.
- ضع ثلاثة أهداف مرتبة TP1 ثم TP2 ثم TP3، ولا تضع هدفًا تم تجاوزه.
- M/قمتان يدعم الهبوط بعد كسر خط العنق أو إعادة اختبار فاشلة.
- W/قاعان يدعم الصعود بعد اختراق خط العنق أو إعادة اختبار ناجحة.
- pattern_lines وpattern_path إحداثيات نسبية داخل مساحة الشارت المعاد رسمها: 0,0 أعلى اليسار و1,1 أسفل اليمين.
- لا ترسم نموذجًا إلا إذا كان واضحًا. لا تنشئ خطوطًا عشوائية.
- confirmation وscenario وnote نصوص عربية قصيرة وواضحة.

النتيجة النهائية سيعيد البرنامج رسمها داخل تصميم SaleeM. يحسب محور السعر الأيمن من أعلى رقم كامل والرقم الذي يليه مباشرة: الفرق بين السعرين هو price_step والفرق بين موضعيهما هو pixel_step، ثم يستخدم أدنى رقم كامل للتحقق من انتظام السلسلة. بعد ذلك يزيل أي انحراف رأسي صغير ناتج عن قص الصورة أو تغيير حجمها بواسطة current_price والخط الحقيقي current_price_y_ratio. تستخدم أرقام المحور والشموع والدعم والمقاومة والدخول والوقف والأهداف التحويل الحسابي نفسه. إذا لم تنجح المعايرة بدقة، لن يرسم البرنامج محورًا بديلًا؛ سيطلب من المستخدم تفعيل Auto-scale أو «الضبط التلقائي» والتقاط صورة جديدة. تظهر منطقة الربح باللون الأخضر ومنطقة الوقف باللون الأحمر. خطوط الدعم زرقاء فاتحة متصلة، وخطوط المقاومة بنفسجية متصلة، وخطوط TP خضراء متصلة. السهم يتبع الاتجاه الفعلي صعودًا أو هبوطًا ولا يكون صاعدًا افتراضيًا. يظهر Order Block كعنصر ثانوي فقط: أسفل السعر في السيناريو الصاعد أو أعلى السعر في السيناريو الهابط. ثم يرسم FVG وشريط الجلسات والدخول والوقف وثلاثة أهداف والملاحظات بوضوح.

الذاكرة المرجعية للقراءة فقط:
{memory_context(KNOWLEDGE_DIR)}
"""

    body = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "max_output_tokens": max(2000, min(8000, int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "5000")))),
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
                "name": "saleem_two_hour_reconstructed_chart",
                "strict": True,
                "schema": ANALYSIS_SCHEMA,
            }
        },
    }

    max_attempts = max(1, min(4, int(os.getenv("OPENAI_RETRIES", "2"))))
    response: httpx.Response | None = None

    with httpx.Client(timeout=150) as client:
        for attempt in range(1, max_attempts + 1):
            response = client.post(
                OPENAI_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if response.status_code != 429 or attempt == max_attempts:
                break

            # المحاولات الفاشلة تُحتسب ضمن الحد؛ لذلك ننتظر بدل التكرار السريع.
            retry_after = response.headers.get("retry-after")
            try:
                delay = float(retry_after) if retry_after else (3.0 * attempt)
            except ValueError:
                delay = 3.0 * attempt
            time.sleep(min(20.0, delay + random.uniform(0.25, 1.0)))

    if response is None:
        raise RuntimeError("خطأ خدمة التحليل: لم يتم إرسال الطلب.")

    if response.status_code >= 400:
        request_id = response.headers.get("x-request-id", "")
        error_type = ""
        error_code = ""
        error_message = ""
        try:
            payload = response.json()
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            if isinstance(error, dict):
                error_type = str(error.get("type") or "")
                error_code = str(error.get("code") or "")
                error_message = str(error.get("message") or "")
        except ValueError:
            error_message = response.text[:300]

        logging.error(
            "OpenAI request failed: status=%s type=%s code=%s request_id=%s message=%s",
            response.status_code, error_type, error_code, request_id, error_message,
        )

        if response.status_code == 429:
            combined = f"{error_type} {error_code} {error_message}".lower()
            if "insufficient_quota" in combined or "quota" in combined:
                raise RuntimeError(
                    "خطأ خدمة التحليل (429): رصيد أو حد الإنفاق للمشروع غير متاح."
                )
            if "token" in combined:
                raise RuntimeError(
                    "خطأ خدمة التحليل (429): تم تجاوز حد الرموز في الدقيقة؛ "
                    "تم تقليل حجم الطلب واستخدام النموذج الأخف، انتظر دقيقة ثم أعد المحاولة."
                )
            raise RuntimeError(
                "خطأ خدمة التحليل (429): تم بلوغ حد الطلبات مؤقتًا؛ انتظر دقيقة ثم أعد المحاولة."
            )

        detail = error_code or error_type or "خطأ غير معروف"
        raise RuntimeError(
            f"خطأ خدمة التحليل ({response.status_code}): {detail}."
        )
    model_data = json.loads(_text(response.json()))

    # السعر الحالي يؤخذ من صورة المستخدم، بينما الشموع والتوقيتات من مزود السوق.
    image_current = _number(model_data.get("current_price"))
    market_m5 = []
    raw_frames = market_data.get("frames") if isinstance(market_data, dict) else None
    if isinstance(raw_frames, dict) and isinstance(raw_frames.get("M5"), list):
        display_count = max(12, min(48, int(os.getenv("CHART_CANDLE_COUNT", "30"))))
        market_m5 = raw_frames["M5"][-display_count:]

    normalized_market = _normalize_candles(market_m5)
    market_last = float(normalized_market[-1]["close"])
    offset = (float(image_current) - market_last) if image_current is not None else 0.0

    # مواءمة سعر مزود السوق مع سعر وسيط المستخدم دون تغيير شكل الحركة.
    if abs(offset) > 0.001:
        for candle in normalized_market:
            for key_name in ("open", "high", "low", "close"):
                candle[key_name] = round(float(candle[key_name]) + offset, 2)

    model_data["candles"] = normalized_market
    model_data["_image_current_price"] = image_current
    model_data["_image_chart_readable"] = bool(model_data.get("chart_readable"))
    model_data["current_price"] = image_current if image_current is not None else normalized_market[-1]["close"]
    # ندمج مستويات النموذج مع المستويات المشتقة من شموع السوق بعد مواءمتها.
    # لا نحذفها لأن H1 وM15 قد يحتويان مقاومات أو دعومًا لا تظهر بوضوح في نافذة M5.
    model_data["market_price_offset"] = round(offset, 3)

    return _validate_analysis(model_data, market_summary=market_summary)


def analyze_chart_image(image_path: Path, symbol: str, timeframe: str) -> dict[str, Any]:
    analysis = _analyze(image_path)
    axis_ok, axis_reason = validate_uploaded_axis(analysis, image_path)
    if not axis_ok:
        raise AxisCalibrationError(
            "تعذر ضبط محور الأسعار بدقة. استخدم Reset Vertical Scale أو فعّل Auto-scale / «الضبط التلقائي» "
            "في الشارت، وتأكد من ظهور محور الأسعار كاملًا وخط السعر الحالي، "
            f"ثم التقط صورة جديدة وأعد المحاولة. السبب: {axis_reason}"
        )
    png = render_result(analysis, chart_background_path=image_path)
    return {
        **analysis,
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "window": f"{len(analysis.get('candles') or [])} شمعة من بيانات السوق",
        "result_url": "data:image/png;base64," + base64.b64encode(png).decode(),
    }
