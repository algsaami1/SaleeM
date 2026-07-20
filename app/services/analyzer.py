from __future__ import annotations

import base64
import json
import logging
import os
import random
import statistics
import time
from pathlib import Path
from typing import Any

import httpx

from app.engine.memory_engine import memory_context
from app.engine.renderer import render_result
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

ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "chart_readable": {"type": "boolean"},
        "candles": {"type": "array", "items": CANDLE, "minItems": 0, "maxItems": 24},
        "direction": {"type": "string", "enum": ["صاعد", "هابط", "عرضي", "غير واضح"]},
        "buy_probability": {"type": "integer", "minimum": 5, "maximum": 95},
        "sell_probability": {"type": "integer", "minimum": 5, "maximum": 95},
        "setup_state": {"type": "string", "enum": ["مؤكد", "مشروط", "مراقبة", "غير صالح"]},
        "entry_kind": {"type": "string", "enum": ["مباشر", "اختراق", "إعادة اختبار", "مراقبة"]},
        "confirmation": {"type": "string"},
        "current_price": NUM_NULL,
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
        "setup_state", "entry_kind", "confirmation", "current_price", "support_levels",
        "resistance_levels", "entry", "stop_loss", "stop_reason", "target_1", "target_2",
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



def _normalize_candles(raw: Any) -> list[dict[str, Any]]:
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
                "time": str(item.get("time") or f"-{(23 - index) * 5}m")[:8],
                "open": round(open_, 2),
                "high": round(true_high, 2),
                "low": round(true_low, 2),
                "close": round(close, 2),
            }
        )

    candles = candles[-24:]
    if len(candles) != 24:
        raise RuntimeError("يجب أن تظهر 24 شمعة كاملة لآخر ساعتين على فريم خمس دقائق.")

    ranges = [max(0.01, c["high"] - c["low"]) for c in candles]
    median_range = statistics.median(ranges)
    if median_range <= 0:
        raise RuntimeError("تعذر معايرة حركة الشموع من الصورة.")

    # رفض الأخطاء الكبيرة الناتجة عن قراءة رقم من المحور على أنه شمعة.
    for index, candle in enumerate(candles):
        if candle["high"] - candle["low"] > median_range * 8:
            raise RuntimeError("توجد شمعة غير مقروءة بدقة. قرّب الشارت وأظهر محور السعر.")
        if index:
            previous_close = candles[index - 1]["close"]
            if abs(candle["open"] - previous_close) > median_range * 6:
                raise RuntimeError("تعذر تتبع تسلسل الشموع بسبب عدم وضوح الصورة.")

    return candles


def _atr(candles: list[dict[str, Any]], periods: int = 8) -> float:
    sample = candles[-periods:] if candles else []
    if not sample:
        return 2.0
    ranges = [max(0.01, float(c["high"]) - float(c["low"])) for c in sample]
    return sum(ranges) / len(ranges)


def _cluster_levels(candles: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    if not candles:
        return []
    prices = [float(c["low"] if kind == "support" else c["high"]) for c in candles]
    total_range = max(prices) - min(prices)
    tolerance = max(0.35, total_range * 0.035)
    clusters: list[list[float]] = []
    for price in sorted(prices):
        for cluster in clusters:
            center = sum(cluster) / len(cluster)
            if abs(price - center) <= tolerance:
                cluster.append(price)
                break
        else:
            clusters.append([price])

    levels: list[dict[str, Any]] = []
    for cluster in clusters:
        touches = len(cluster)
        if touches < 2:
            continue
        center = sum(cluster) / touches
        strength = min(92, 48 + touches * 8)
        levels.append({"price": round(center, 2), "strength": strength, "touches": min(touches, 12)})
    return sorted(levels, key=lambda level: (-int(level["strength"]), -int(level["touches"])))[:4]


def _normalize_levels(raw: Any, candles: list[dict[str, Any]], kind: str, current: float) -> list[dict[str, Any]]:
    levels: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        price = _number(item.get("price"))
        if price is None:
            continue
        # الدعم يجب أن يكون أسفل/قريبًا من السعر، والمقاومة أعلى/قريبة منه.
        side_tolerance = max(0.25, _atr(candles) * 0.20)
        if kind == "support" and price > current + side_tolerance:
            continue
        if kind == "resistance" and price < current - side_tolerance:
            continue
        strength = max(35, min(95, int(item.get("strength") or 50)))
        touches = max(1, min(12, int(item.get("touches") or 1)))
        levels.append({"price": round(price, 2), "strength": strength, "touches": touches})

    if len(levels) < 2:
        existing = {round(float(level["price"]), 1) for level in levels}
        side_tolerance = max(0.25, _atr(candles) * 0.20)
        for derived in _cluster_levels(candles, kind):
            price = float(derived["price"])
            if kind == "support" and price > current + side_tolerance:
                continue
            if kind == "resistance" and price < current - side_tolerance:
                continue
            if round(price, 1) not in existing:
                levels.append(derived)
                existing.add(round(price, 1))

    # قوة المستوى أولًا ثم قربه من السعر الحالي، مع دمج المستويات المتقاربة.
    levels.sort(key=lambda level: (-(float(level["strength"]) - abs(float(level["price"]) - current) * 1.5)))
    merged: list[dict[str, Any]] = []
    merge_distance = max(0.35, _atr(candles) * 0.35)
    for level in levels:
        if any(abs(float(level["price"]) - float(other["price"])) <= merge_distance for other in merged):
            continue
        merged.append(level)
        if len(merged) == 2:
            break
    return sorted(merged, key=lambda level: float(level["price"]), reverse=True)


def _normalize_probabilities(data: dict[str, Any]) -> tuple[int, int]:
    try:
        buy = max(5, min(95, int(round(float(data.get("buy_probability", 50))))))
    except (TypeError, ValueError):
        buy = 50
    sell = 100 - buy
    return buy, sell


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

    return {
        "source": market_data.get("source"),
        "symbol": market_data.get("symbol"),
        "fetched_at": market_data.get("fetched_at"),
        "latest_candle_time": market_data.get("latest_candle_time"),
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
    atr = max(0.01, _atr(candles))
    full_move = (float(candles[-1]["close"]) - float(candles[0]["close"])) / atr
    recent_move = (float(candles[-1]["close"]) - float(candles[-6]["close"])) / atr
    model_bias = (buy - sell) / 20.0

    image_score = model_bias * 0.45 + full_move * 0.35 + recent_move * 0.20
    higher_score = 0.0
    if isinstance(market_summary, dict):
        try:
            higher_score = float(market_summary.get("score") or 0.0)
        except (TypeError, ValueError):
            higher_score = 0.0

    # M5 والصورة مسؤولان عن التوقيت، والفريمات العليا تمنع الدخول عكس الاتجاه العام.
    score = image_score * 0.58 + higher_score * 0.42

    if score > 0.18:
        direction = "صاعد"
    elif score < -0.18:
        direction = "هابط"
    else:
        direction = "صاعد" if float(candles[-1]["close"]) >= float(candles[-6]["close"]) else "هابط"

    structure_agrees = (direction == "صاعد" and full_move >= 0) or (direction == "هابط" and full_move <= 0)
    selected = buy if direction == "صاعد" else sell
    probability = max(52, min(88, selected if structure_agrees else min(selected, 64)))

    if isinstance(market_summary, dict):
        higher_direction = str(market_summary.get("direction") or "عرضي")
        alignment = int(market_summary.get("alignment") or 50)
        if higher_direction in {"صاعد", "هابط"} and higher_direction != direction:
            probability = min(probability, 60)
        elif higher_direction == direction:
            probability = min(90, probability + max(0, alignment - 50) // 8)
        else:
            probability = min(probability, 64)
        if market_summary.get("warnings"):
            probability = min(probability, 62)

    buy_final = probability if direction == "صاعد" else 100 - probability
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

    if len(unique) < 3:
        raise RuntimeError("تعذر تكوين ثلاثة أهداف منطقية داخل السيناريو.")
    return unique


def _validate_analysis(
    data: dict[str, Any],
    market_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if data.get("chart_readable") is False:
        raise RuntimeError("الصورة أو محور الأسعار غير واضحين بما يكفي للتحليل.")
    candles = _normalize_candles(data.get("candles"))
    current = float(candles[-1]["close"])
    buy, sell = _normalize_probabilities(data)
    direction, buy, sell = _choose_direction(data, candles, buy, sell, market_summary)
    probability = buy if direction == "صاعد" else sell
    supports = _normalize_levels(data.get("support_levels"), candles, "support", current)
    resistances = _normalize_levels(data.get("resistance_levels"), candles, "resistance", current)
    entry, entry_kind, confirmation = _nearest_entry(data, direction, current, supports, resistances)
    stop, stop_reason = _validated_stop(data, direction, entry, candles, supports, resistances)
    targets = _validated_targets(data, direction, entry, stop, supports, resistances)

    model_state = str(data.get("setup_state") or "مراقبة")
    if probability >= CONFIRMED_PROBABILITY and model_state == "مؤكد":
        draw_mode = "confirmed"
    elif probability >= CONDITIONAL_PROBABILITY:
        draw_mode = "conditional"
    else:
        draw_mode = "watch"

    pattern_confidence = max(0, min(100, int(data.get("pattern_confidence") or 0)))
    if pattern_confidence < 60:
        data["pattern_lines"] = []
        data["pattern_path"] = []
        data["pattern_type"] = "لا يوجد"

    data.update(
        {
            "chart_readable": True,
            "candles": candles,
            "current_price": round(current, 2),
            "buy_probability": buy,
            "sell_probability": sell,
            "direction": direction,
            "trade_side": "شراء" if direction == "صاعد" else "بيع",
            "trade_probability": probability,
            "draw_mode": draw_mode,
            "support_levels": supports,
            "resistance_levels": resistances,
            "entry": entry,
            "entry_kind": entry_kind,
            "confirmation": " ".join(confirmation.split())[:70],
            "stop_loss": stop,
            "stop_reason": " ".join(stop_reason.split())[:65],
            "target_1": targets[0],
            "target_2": targets[1],
            "target_3": targets[2],
            "scenario": " ".join(str(data.get("scenario") or "").split())[:85],
            "note": " ".join(str(data.get("note") or "").split())[:90],
            "market_data_source": (market_summary or {}).get("source"),
            "market_data_fetched_at": (market_summary or {}).get("fetched_at"),
            "market_direction": (market_summary or {}).get("direction", "غير واضح"),
            "frame_alignment": int((market_summary or {}).get("alignment") or 0),
            "frame_directions": (market_summary or {}).get("frames", {}),
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
        # صورة M5 هي المرجع التنفيذي، لذلك نكتفي بآخر 24 شمعة خارجية له
        # ونحتفظ بسياق أكبر قليلًا للفريمات العليا فقط.
        market_frames = market_context.get("frames", {})
        if isinstance(market_frames, dict) and isinstance(market_frames.get("M5"), list):
            market_frames["M5"] = market_frames["M5"][-24:]
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

اقرأ صورة الشارت المرفوعة، ثم أعد بناء آخر ساعتين فقط: آخر 24 شمعة M5 من أقصى يمين الشارت، مرتبة من الأقدم إلى الأحدث.
استخرج OHLC لكل شمعة اعتمادًا على جسم الشمعة وذيولها ومحور الأسعار. استخدم السعر الحالي من إغلاق آخر شمعة.
إذا كانت بعض القيم غير مطبوعة حرفيًا، قدّرها بدقة من محور السعر، لكن لا تغيّر ترتيب واتجاه الشموع.
اجعل chart_readable=false فقط إذا كانت الشموع أو محور الأسعار غير قابلين للقراءة إطلاقًا، وفي هذه الحالة أعد candles=[] ولا تخترع شموعًا.

التحليل المطلوب:
- اختر سيناريو واحدًا فقط، وهو الأعلى احتمالًا.
- BUY وSELL مجموعهما 100، ولا تستخدم 0 أو 100.
- عند ضعف التأكيد، لا تقل لا توجد صفقة؛ أعطِ أقرب نقطة تفعيل مشروطة مع اتجاه متوقع.
- حدد أقرب دعمين وأقرب مقاومتين مهمين خلال آخر 24 شمعة.
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

النتيجة النهائية سيعيد البرنامج رسمها كصورة جديدة: 24 شمعة، دعم ومقاومة، سهم واحد، دخول، وقف، ثلاثة أهداف، وملاحظات أسفل الشارت.

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
    return _validate_analysis(
        json.loads(_text(response.json())),
        market_summary=market_summary,
    )


def analyze_chart_image(image_path: Path, symbol: str, timeframe: str) -> dict[str, Any]:
    analysis = _analyze(image_path)
    png = render_result(analysis)
    return {
        **analysis,
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "window": "آخر ساعتين",
        "result_url": "data:image/png;base64," + base64.b64encode(png).decode(),
    }
