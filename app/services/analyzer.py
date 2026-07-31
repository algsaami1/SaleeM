from __future__ import annotations

import base64
import copy
import hashlib
import json
import logging
import os
import random
import statistics
import threading
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from PIL import Image, ImageEnhance

from app.engine.memory_engine import memory_context
from app.engine.pattern_engine import review_market_patterns
from app.engine.renderer import (
    AxisCalibrationError,
    detect_market_zone_presence,
    prepare_chart_viewport_image,
    render_result,
    validate_uploaded_axis,
)
from app.services.market_data import (
    MarketDataError,
    compact_market_context,
    fetch_market_data,
)
from app.services.system_status import system_status_store

OPENAI_URL = "https://api.openai.com/v1/responses"
BASE_DIR = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
SPEC_PATH = BASE_DIR / "SALEEM_FINAL_SPEC.md"
PERMANENT_PROMPT_PATH = KNOWLEDGE_DIR / "09_rules" / "PERMANENT_ANALYSIS_PROMPT.md"


def load_final_spec() -> str:
    """قراءة دستور SaleeM النهائي دون تعديله."""
    if not SPEC_PATH.exists():
        raise RuntimeError("ملف SALEEM_FINAL_SPEC.md غير موجود في المجلد الرئيسي للمشروع.")
    return SPEC_PATH.read_text(encoding="utf-8").strip()


def load_permanent_analysis_prompt() -> str:
    """قراءة قاعدة التحليل الدائمة التي تُحقن في كل طلب تحليل."""
    if not PERMANENT_PROMPT_PATH.exists():
        raise RuntimeError(
            "ملف قاعدة التحليل الدائمة PERMANENT_ANALYSIS_PROMPT.md غير موجود."
        )
    return PERMANENT_PROMPT_PATH.read_text(encoding="utf-8").strip()


CONFIRMED_PROBABILITY = 64
CONDITIONAL_PROBABILITY = 55
MAX_ENTRY_DISTANCE = 8.0
MIN_STOP_DISTANCE = 0.6
MAX_STOP_DISTANCE = 4.0
STOP_ATR_MULTIPLIER = 1.10
DUAL_SCENARIO_CONFIRMED_PROBABILITY = 70
DUAL_SCENARIO_CONDITIONAL_PROBABILITY = 55
DEFAULT_SCALP_POINT_SIZE = 0.10


def _nearest_level_price(levels: Any, current_price: float, *, side: str) -> float | None:
    """Select the nearest valid support or resistance price for the summary."""
    values: list[float] = []
    for item in levels if isinstance(levels, list) else []:
        if not isinstance(item, dict):
            continue
        value = _number(item.get("price"))
        if value is not None:
            values.append(float(value))
    if not values:
        return None

    if side == "support":
        preferred = [value for value in values if value <= current_price]
        return max(preferred) if preferred else min(values, key=lambda value: abs(value - current_price))

    preferred = [value for value in values if value >= current_price]
    return min(preferred) if preferred else min(values, key=lambda value: abs(value - current_price))


def _nearest_real_level_price(levels: Any, current_price: float, *, side: str) -> float | None:
    """Return the nearest non-projected level, with a safe fallback.

    The breakout sentence must point to a real market level whenever one is
    available. Projected drawing-only levels are used only when the provider
    did not return a historical support/resistance level at all.
    """
    iterable = levels if isinstance(levels, list) else []
    real_levels = [
        item
        for item in iterable
        if isinstance(item, dict) and str(item.get("source") or "") != "projected"
    ]
    return _nearest_level_price(real_levels or levels, current_price, side=side)


def _market_reason_factors(analysis: dict[str, Any]) -> list[str]:
    """Build short evidence phrases without target prices."""
    direction = str(analysis.get("direction") or "غير واضح")
    factors: list[str] = []

    frames = analysis.get("frame_directions") if isinstance(analysis.get("frame_directions"), dict) else {}
    m15_item = frames.get("M15") if isinstance(frames, dict) else None
    m5_item = frames.get("M5") if isinstance(frames, dict) else None
    m15 = str(m15_item.get("direction") or "غير واضح") if isinstance(m15_item, dict) else str(m15_item or "غير واضح")
    m5 = str(m5_item.get("direction") or "غير واضح") if isinstance(m5_item, dict) else str(m5_item or "غير واضح")
    if m15 == m5 and m15 in {"صاعد", "هابط"}:
        factors.append(f"توافق M15 وM5 على اتجاه {m15}")
    elif m15 in {"صاعد", "هابط"} and m5 in {"صاعد", "هابط"} and m15 != m5:
        factors.append("تعارض M15 وM5")

    pattern = str(analysis.get("pattern_type") or "لا يوجد")
    pattern_confidence = int(analysis.get("pattern_confidence") or 0)
    if pattern != "لا يوجد" and pattern_confidence >= 60:
        factors.append(f"نموذج {pattern}")

    if direction == "صاعد":
        factors.append("السيولة فوق القمة الأخيرة")
    elif direction == "هابط":
        factors.append("السيولة أسفل القاع الأخير")
    else:
        factors.append("السيولة موزعة عند طرفي النطاق")

    zones = detect_market_zone_presence(analysis)
    zone_names: list[str] = []
    if zones.get("order_block"):
        zone_names.append("منطقة أوامر (Order Block)")
    if zones.get("fvg"):
        zone_names.append("فجوة سعرية (FVG)")
    if zone_names:
        factors.append(" و".join(zone_names))

    # Keep the sentence compact and deterministic.
    unique: list[str] = []
    for factor in factors:
        if factor not in unique:
            unique.append(factor)
    return unique[:4]


def _build_result_explanation(analysis: dict[str, Any]) -> dict[str, Any]:
    """Build a detailed but non-repetitive explanation for the result page.

    The quick cards remain short. This structure powers the collapsed
    "لماذا ظهرت النتيجة؟" panel with frames, structure, momentum, liquidity,
    zones, patterns, confirmation, opposing factors and available news data.
    No news or market event is invented when it is absent from the inputs.
    """
    direction = str(analysis.get("higher_timeframe_direction") or analysis.get("direction") or "غير واضح")
    current_movement = str(analysis.get("current_movement") or "غير واضح")
    movement_strength = str(analysis.get("current_movement_strength") or "ضعيف")
    frames_raw = analysis.get("frame_directions") if isinstance(analysis.get("frame_directions"), dict) else {}

    frames: list[dict[str, str]] = []
    for timeframe in ("H4", "H1", "M15", "M5"):
        raw = frames_raw.get(timeframe)
        if isinstance(raw, dict):
            frame_direction = str(raw.get("direction") or "غير واضح")
            detail = str(raw.get("reason") or raw.get("label") or "").strip()
        else:
            frame_direction = str(raw or "غير واضح")
            detail = ""
        frames.append({"timeframe": timeframe, "direction": frame_direction, "detail": detail[:120]})

    pattern = str(analysis.get("pattern_type") or "لا يوجد")
    pattern_confidence = max(0, min(100, int(analysis.get("pattern_confidence") or 0)))
    pattern_timeframe = str(analysis.get("pattern_timeframe") or "M5")
    if pattern == "لا يوجد" or pattern_confidence < 60:
        pattern_text = "لا يوجد نموذج مكتمل وواضح على الشموع المغلقة حاليًا."
    else:
        pattern_text = f"النموذج الأقرب: {pattern} على {pattern_timeframe} بثقة {pattern_confidence}٪."

    zones = detect_market_zone_presence(analysis)
    zone_parts: list[str] = []
    if zones.get("order_block"):
        zone_parts.append("منطقة أوامر")
    if zones.get("fvg"):
        zone_parts.append("فجوة سعرية")
    zone_text = " و".join(zone_parts) if zone_parts else "لا توجد منطقة أوامر أو فجوة سعرية قوية ظاهرة في النطاق الحالي."

    supports = [item for item in (analysis.get("support_levels") or []) if isinstance(item, dict)]
    resistances = [item for item in (analysis.get("resistance_levels") or []) if isinstance(item, dict)]
    nearest_support = _number(supports[0].get("price")) if supports else None
    nearest_resistance = _number(resistances[0].get("price")) if resistances else None
    level_parts: list[str] = []
    if nearest_support is not None:
        level_parts.append(f"الدعم الأقرب {nearest_support:.2f}")
    if nearest_resistance is not None:
        level_parts.append(f"المقاومة الأقرب {nearest_resistance:.2f}")
    levels_text = "، ".join(level_parts) if level_parts else "لم تتوفر مستويات مؤكدة كافية ضمن النطاق المقروء."

    peak = analysis.get("most_probable_peak") if isinstance(analysis.get("most_probable_peak"), dict) else {}
    trough = analysis.get("most_probable_trough") if isinstance(analysis.get("most_probable_trough"), dict) else {}
    peak_price = _number(peak.get("price"))
    trough_price = _number(trough.get("price"))
    if direction == "صاعد":
        liquidity_text = "السيولة المرجحة أعلى القمم الأخيرة"
        if peak_price is not None:
            liquidity_text += f" قرب {peak_price:.2f}"
    elif direction == "هابط":
        liquidity_text = "السيولة المرجحة أسفل القيعان الأخيرة"
        if trough_price is not None:
            liquidity_text += f" قرب {trough_price:.2f}"
    else:
        liquidity_text = "السيولة موزعة عند طرفي النطاق، لذلك لا توجد جهة مكتملة التأكيد."

    confirmation = str(analysis.get("confirmation_explanation") or analysis.get("confirmation") or "بانتظار تأكيد واضح على شمعة M5 مغلقة")
    invalidation = str(analysis.get("invalidation_condition") or "يُلغى السيناريو عند كسر البنية المقابلة")
    decision = analysis.get("dual_scenario_decision") if isinstance(analysis.get("dual_scenario_decision"), dict) else {}
    decision_reason = str(decision.get("reason") or analysis.get("scenario") or "تتم مراقبة السيناريوهين حتى اكتمال التفعيل")
    waiting_for = str(decision.get("waiting_for") or analysis.get("entry_activation_reason") or "إغلاق شمعة التفعيل")

    warnings = [str(item) for item in (analysis.get("market_data_warnings") or []) if str(item).strip()]
    opposition_parts = [confirmation, f"الإلغاء: {invalidation}"]
    if warnings:
        opposition_parts.append("تنبيه البيانات: " + "، ".join(warnings[:2]))

    macro_note = str(analysis.get("macro_note") or "لا تتوفر بيانات أخبار مؤكدة ضمن مدخلات هذا التحليل.")
    if not macro_note.strip():
        macro_note = "لا تتوفر بيانات أخبار مؤكدة ضمن مدخلات هذا التحليل."

    technical_reasons = _market_reason_factors(analysis)
    if not technical_reasons:
        technical_reasons = ["القرار مبني على توافق الفريمات والبنية ومستويات السوق المتاحة"]

    return {
        "summary": str(analysis.get("market_reading_comment") or "تمت مراجعة الاتجاه والبنية والزخم والسيولة قبل تحديد النتيجة."),
        "decision_reason": decision_reason,
        "waiting_for": waiting_for,
        "frames": frames,
        "structure": f"الاتجاه العام {direction}، والحركة الحالية {current_movement} بقوة {movement_strength}.",
        "momentum": f"الزخم الحالي {movement_strength}، واتجاه حركة M5 الأخيرة {current_movement}.",
        "liquidity": liquidity_text,
        "zones": zone_text,
        "levels": levels_text,
        "pattern": pattern_text,
        "pattern_review": str(analysis.get("pattern_review_summary") or pattern_text),
        "confirmation": confirmation,
        "opposition": opposition_parts,
        "technical_reasons": technical_reasons,
        "news": macro_note,
        "news_available": not ("لا تتوفر" in macro_note or "غير متوفر" in macro_note),
    }


def _build_market_reading_comment(analysis: dict[str, Any]) -> str:
    """Short user-friendly explanation without crowding the UI."""
    direction = str(analysis.get("direction") or "غير واضح")
    prefix = {
        "صاعد": "القراءة تميل للصعود",
        "هابط": "القراءة تميل للهبوط",
        "عرضي": "القراءة عرضية",
        "غير واضح": "القراءة غير واضحة",
    }.get(direction, "القراءة غير واضحة")
    factors = _market_reason_factors(analysis)[:3]
    current = float(_number(analysis.get("current_price")) or 0.0)
    support = _nearest_real_level_price(analysis.get("support_levels"), current, side="support")
    resistance = _nearest_real_level_price(analysis.get("resistance_levels"), current, side="resistance")
    parts: list[str] = []
    if factors:
        parts.append("، ".join(factors))
    if support is not None and resistance is not None:
        parts.append(f"الدعم {support:.2f} والمقاومة {resistance:.2f}")
    elif support is not None:
        parts.append(f"الدعم {support:.2f}")
    elif resistance is not None:
        parts.append(f"المقاومة {resistance:.2f}")
    if not parts:
        return prefix + "."
    comment = prefix + ": " + " — ".join(parts) + "."
    return comment if len(comment) <= 150 else comment[:147].rstrip(" ،.-") + "..."


def _build_breakout_summary(analysis: dict[str, Any]) -> str:
    """Short decisive levels in simple Arabic."""
    current = float(_number(analysis.get("current_price")) or 0.0)
    support = _nearest_real_level_price(analysis.get("support_levels"), current, side="support")
    resistance = _nearest_real_level_price(analysis.get("resistance_levels"), current, side="resistance")
    if resistance is not None and support is not None:
        return f"فوق {resistance:.2f} صعود، وتحت {support:.2f} هبوط."
    if resistance is not None:
        return f"فوق {resistance:.2f} ترجح الحركة للصعود."
    if support is not None:
        return f"تحت {support:.2f} ترجح الحركة للهبوط."
    return "لا يوجد كسر واضح الآن."


def _confirmed_limit_candidates(
    analysis: dict[str, Any],
    *,
    side: str,
    current: float,
) -> list[dict[str, Any]]:
    """Return only confirmed swing troughs/peaks from real market frames.

    Buy Limit may use a confirmed trough below market. Sell Limit may use a
    confirmed peak above market. No projected level, fixed-distance fallback,
    or fabricated waiting area is allowed here.
    """
    swings = analysis.get("confirmed_limit_swings")
    if not isinstance(swings, dict):
        return []
    source_key = "troughs" if side == "buy" else "peaks"
    candidates: list[dict[str, Any]] = []
    for item in swings.get(source_key) or []:
        if not isinstance(item, dict):
            continue
        price = _number(item.get("price"))
        if price is None:
            continue
        price = float(price)
        if side == "buy" and price >= current:
            continue
        if side == "sell" and price <= current:
            continue
        if str(item.get("source") or "") != "confirmed_swing":
            continue
        candidates.append(
            {
                **item,
                "price": round(price, 2),
                "strength": max(1, min(95, int(item.get("strength") or 0))),
                "touches": max(1, min(12, int(item.get("touches") or 1))),
                "timeframe": str(item.get("timeframe") or "H1"),
                "confirmation_frames": list(item.get("confirmation_frames") or []),
                "level_atr": max(0.01, float(_number(item.get("level_atr")) or 1.0)),
            }
        )
    return candidates


def _pick_confirmed_limit_level(
    analysis: dict[str, Any],
    *,
    side: str,
    current: float,
    atr: float,
) -> dict[str, Any] | None:
    """Pick the strongest confirmed peak/trough without imposing a distance."""
    candidates = _confirmed_limit_candidates(analysis, side=side, current=current)
    if not candidates:
        return None

    frame_bonus = {"H4": 16.0, "H1": 12.0, "M15": 5.0, "M5": 1.0}
    ranked: list[tuple[float, float, dict[str, Any]]] = []
    for item in candidates:
        distance = abs(current - float(item["price"]))
        # Once a swing is confirmed, its ranking must not drift with every new
        # screenshot.  Current distance is reported to the user but is not used
        # to replace one valid peak/trough with another.
        confirmations = len(set(item.get("confirmation_frames") or []))
        score = (
            float(item["strength"])
            + frame_bonus.get(str(item.get("timeframe") or ""), 0.0)
            + min(10.0, confirmations * 2.5)
            + min(6.0, int(item.get("touches") or 1) * 1.2)
        )
        stable_tie = str(item.get("time") or "")
        ranked.append((score, stable_tie, item))
    _, _, selected = max(ranked, key=lambda value: (value[0], value[1]))
    return {
        **selected,
        "distance": round(abs(current - float(selected["price"])), 2),
        "projected": False,
    }


def _limit_recommendation_probability(
    analysis: dict[str, Any],
    *,
    side: str,
    level: dict[str, Any],
) -> int:
    """Estimate setup strength; this is explicitly not a win guarantee."""
    base = int(analysis.get("buy_probability") or 50) if side == "buy" else int(analysis.get("sell_probability") or 50)
    strength = int(level.get("strength") or 45)
    expected_direction = "صاعد" if side == "buy" else "هابط"
    frames = analysis.get("frame_directions") if isinstance(analysis.get("frame_directions"), dict) else {}
    frame_items = [frames.get(name) for name in ("H4", "H1", "M15", "M5")]
    matching = sum(
        1
        for item in frame_items
        if isinstance(item, dict) and str(item.get("direction") or "") == expected_direction
    )
    frame_score = 50 if not any(isinstance(item, dict) for item in frame_items) else matching * 25
    confirmations = len(set(level.get("confirmation_frames") or []))
    confirmation_score = min(100, 45 + confirmations * 14)
    warning_penalty = 6 if analysis.get("market_data_warnings") else 0
    estimate = round(
        base * 0.34
        + strength * 0.34
        + frame_score * 0.18
        + confirmation_score * 0.14
        - warning_penalty
    )
    return max(40, min(88, int(estimate)))


def _opposing_target_levels(
    analysis: dict[str, Any],
    *,
    side: str,
    entry: float,
) -> list[float]:
    """Collect real opposing swing/market levels before risk projections."""
    values: list[float] = []
    swings = analysis.get("confirmed_limit_swings")
    swing_key = "peaks" if side == "buy" else "troughs"
    if isinstance(swings, dict):
        for item in swings.get(swing_key) or []:
            if not isinstance(item, dict):
                continue
            value = _number(item.get("price"))
            if value is not None:
                values.append(float(value))

    # Do not use the moving nearest M5 support/resistance list here.  Limit
    # recommendations are long-waiting plans and their targets must stay tied
    # to confirmed opposing swings (or fixed risk multiples) until invalidated.

    valid = [value for value in values if (value > entry if side == "buy" else value < entry)]
    valid.sort(reverse=side == "sell")
    unique: list[float] = []
    for value in valid:
        if not unique or all(abs(value - known) >= 0.25 for known in unique):
            unique.append(value)
    return unique


def _build_one_limit_plan(
    analysis: dict[str, Any],
    *,
    side: str,
    current: float,
    atr: float,
) -> dict[str, Any] | None:
    level = _pick_confirmed_limit_level(analysis, side=side, current=current, atr=atr)
    if level is None:
        return None

    pivot = float(level["price"])
    level_atr = max(0.25, float(level.get("level_atr") or atr))
    zone_half_width = max(0.20, min(1.80, level_atr * 0.12))
    stop_buffer = max(0.90, min(5.50, level_atr * 0.28))

    if side == "buy":
        zone_low = pivot
        zone_high = pivot + zone_half_width * 2.0
        entry = pivot + zone_half_width * 0.85
        stop = pivot - stop_buffer
    else:
        zone_low = pivot - zone_half_width * 2.0
        zone_high = pivot
        entry = pivot - zone_half_width * 0.85
        stop = pivot + stop_buffer

    risk = max(0.80, abs(entry - stop))
    real_targets = _opposing_target_levels(analysis, side=side, entry=entry)
    targets: list[float] = []
    # Use only meaningful opposing levels that are sufficiently far away.  The
    # ordering is deterministic, so the same confirmed pivot keeps the same
    # targets until its invalidation condition is met.
    for value in real_targets:
        if side == "buy" and value >= entry + risk * 1.55:
            targets.append(value)
        elif side == "sell" and value <= entry - risk * 1.55:
            targets.append(value)
        if len(targets) == 3:
            break

    multipliers = (2.0, 3.2, 4.8)
    for multiplier in multipliers:
        if len(targets) >= 3:
            break
        projected = entry + risk * multiplier if side == "buy" else entry - risk * multiplier
        if targets:
            if side == "buy":
                projected = max(projected, targets[-1] + max(level_atr * 0.55, 0.60))
            else:
                projected = min(projected, targets[-1] - max(level_atr * 0.55, 0.60))
        targets.append(projected)

    source_frame = str(level.get("timeframe") or "H1")
    pivot_label = "قاع" if side == "buy" else "قمة"
    reason_parts = [f"{pivot_label} مؤكد من {source_frame}"]
    if level.get("confirmation_frames"):
        reason_parts.append(f"تأكيد من {', '.join(level.get('confirmation_frames') or [])}")

    zones = detect_market_zone_presence(analysis)
    if zones.get("order_block"):
        reason_parts.append("منطقة أوامر قريبة")
    if zones.get("fvg"):
        reason_parts.append("فجوة سعرية داعمة")

    pattern = str(analysis.get("pattern_type") or "لا يوجد")
    pattern_confidence = int(analysis.get("pattern_confidence") or 0)
    if pattern != "لا يوجد" and pattern_confidence >= 60:
        reason_parts.append(f"نموذج {pattern}")

    reason_parts.append("سيولة سفلية متوقعة" if side == "buy" else "سيولة علوية متوقعة")
    short_reason = "، ".join(reason_parts[:4])
    reason = "السبب: " + "، ".join(reason_parts) + ". الأهداف موزعة على البنية المقابلة دون ضمان."
    pivot_time = str(level.get("time") or "unknown")
    plan_seed = f"{side}|{source_frame}|{pivot_time}|{pivot:.3f}"
    plan_id = hashlib.sha256(plan_seed.encode("utf-8")).hexdigest()[:12]
    confirmations = sorted(set(level.get("confirmation_frames") or []))
    confirmed_conditions = int(level.get("strength") or 0) >= 75 and len(confirmations) >= 2
    invalidation = (
        f"إغلاق شمعة {source_frame} تحت {stop:.2f}"
        if side == "buy"
        else f"إغلاق شمعة {source_frame} فوق {stop:.2f}"
    )
    return {
        "order_type": "Buy Limit" if side == "buy" else "Sell Limit",
        "entry": round(entry, 2),
        "pivot_price": round(pivot, 2),
        "pivot_type": "قاع مؤكد" if side == "buy" else "قمة مؤكدة",
        "pivot_timeframe": source_frame,
        "zone_low": round(min(zone_low, zone_high), 2),
        "zone_high": round(max(zone_low, zone_high), 2),
        "stop_loss": round(stop, 2),
        "target_1": round(targets[0], 2),
        "target_2": round(targets[1], 2),
        "target_3": round(targets[2], 2),
        "distance_to_entry": round(abs(current - entry), 2),
        "estimated_success": _limit_recommendation_probability(analysis, side=side, level=level),
        "level_strength": int(level.get("strength") or 0),
        "source": "confirmed_swing",
        "reason": reason,
        "short_reason": short_reason,
        "plan_id": plan_id,
        "locked": True,
        "entry_outside_loss_zone": True,
        "confirmation_label": "مؤكدة الشروط" if confirmed_conditions else "المستوى مؤكد",
        "invalidation_condition": invalidation,
        "validity": "ثابتة حتى كسر القمة/القاع أو ظهور إلغاء بنيوي",
        "guaranteed": False,
    }






def _buy_limit_peak_change_outlook(analysis: dict[str, Any], buy_plan: dict[str, Any]) -> dict[str, Any] | None:
    """Return two Buy Limit probability cases.

    Case 1 is the current probability. Case 2 improves if the market forms a
    higher confirmed peak while the confirmed trough remains valid.
    """
    swings = analysis.get("confirmed_limit_swings")
    if not isinstance(swings, dict):
        return None

    peaks: list[float] = []
    for item in swings.get("peaks") or []:
        if not isinstance(item, dict):
            continue
        price = _number(item.get("price"))
        if price is not None:
            peaks.append(float(price))
    if not peaks:
        return None

    current_case = int(buy_plan.get("estimated_success") or 0)
    highest_peak = max(peaks)
    base_bonus = 6
    if str(analysis.get("higher_timeframe_direction") or "") == "صاعد":
        base_bonus += 3
    if str(analysis.get("direction") or "") == "صاعد":
        base_bonus += 2
    if int(analysis.get("pattern_confidence") or 0) >= 60:
        base_bonus += 1
    improved = max(current_case + 4, min(92, current_case + base_bonus))

    return {
        "current_label": "الاحتمال الحالي",
        "current_probability": current_case,
        "change_label": f"إذا ظهرت قمة أعلى فوق {highest_peak:.2f}",
        "change_probability": improved,
        "reference_peak": round(highest_peak, 2),
        "note": (
            f"إذا تكوّنت قمة أعلى وثبت الإغلاق فوق {highest_peak:.2f} مع بقاء القاع المعتمد سليمًا، "
            f"ترتفع قوة Buy Limit إلى {improved}٪ تقريبًا."
        ),
    }


def _sell_limit_trough_change_outlook(analysis: dict[str, Any], sell_plan: dict[str, Any]) -> dict[str, Any] | None:
    """Return two Sell Limit probability cases.

    Case 1 is the current probability. Case 2 improves if the market forms a
    lower confirmed trough while the confirmed peak remains valid.
    """
    swings = analysis.get("confirmed_limit_swings")
    if not isinstance(swings, dict):
        return None

    troughs: list[float] = []
    for item in swings.get("troughs") or []:
        if not isinstance(item, dict):
            continue
        price = _number(item.get("price"))
        if price is not None:
            troughs.append(float(price))
    if not troughs:
        return None

    current_case = int(sell_plan.get("estimated_success") or 0)
    lowest_trough = min(troughs)
    base_bonus = 6
    if str(analysis.get("higher_timeframe_direction") or "") == "هابط":
        base_bonus += 3
    if str(analysis.get("direction") or "") == "هابط":
        base_bonus += 2
    if int(analysis.get("pattern_confidence") or 0) >= 60:
        base_bonus += 1
    improved = max(current_case + 4, min(92, current_case + base_bonus))

    return {
        "current_label": "الاحتمال الحالي",
        "current_probability": current_case,
        "change_label": f"إذا ظهر قاع أدنى تحت {lowest_trough:.2f}",
        "change_probability": improved,
        "reference_trough": round(lowest_trough, 2),
        "note": (
            f"إذا تكوّن قاع أدنى وثبت الإغلاق تحت {lowest_trough:.2f} مع بقاء القمة المعتمدة سليمًا، "
            f"ترتفع قوة Sell Limit إلى {improved}٪ تقريبًا."
        ),
    }


def _build_limit_recommendations(analysis: dict[str, Any]) -> dict[str, Any]:
    """Build manual limit plans strictly from confirmed swing lows/highs."""
    market_activity = analysis.get("market_activity")
    active = bool(market_activity.get("active")) if isinstance(market_activity, dict) else analysis.get("draw_mode") != "inactive"
    if not active or analysis.get("draw_mode") == "inactive":
        return {
            "available": False,
            "reason": "التوصية غير متاحة حتى يفتح السوق وتتحدث شموع M5.",
            "disclaimer": "النسب تقديرية وغير مضمونة، ولا تنفذ أي صفقة تلقائيًا.",
        }

    current = float(_number(analysis.get("current_price")) or 0.0)
    candles = [item for item in (analysis.get("candles") or []) if isinstance(item, dict)]
    atr = max(0.25, _atr(candles))
    buy_plan = _build_one_limit_plan(analysis, side="buy", current=current, atr=atr)
    sell_plan = _build_one_limit_plan(analysis, side="sell", current=current, atr=atr)

    if buy_plan is None and sell_plan is None:
        return {
            "available": False,
            "reason": "لا توجد قمة أو قاع صالح للتوصية حاليًا.",
            "disclaimer": "النسب تقديرية وغير مضمونة، ولا تنفذ أي صفقة تلقائيًا.",
        }

    if buy_plan is not None:
        outlook = _buy_limit_peak_change_outlook(analysis, buy_plan)
        if outlook is not None:
            buy_plan["probability_scenarios"] = outlook
    if sell_plan is not None:
        outlook = _sell_limit_trough_change_outlook(analysis, sell_plan)
        if outlook is not None:
            sell_plan["probability_scenarios"] = outlook

    result: dict[str, Any] = {
        "available": True,
        "current_price": round(current, 2),
        "buy_limit": buy_plan,
        "sell_limit": sell_plan,
        "disclaimer": "نسبة القوة تقديرية وغير مضمونة. راجع السعر والسبريد قبل إدخال الأوامر يدويًا في MT5.",
    }

    if buy_plan is not None and sell_plan is not None:
        buy_rate = int(buy_plan["estimated_success"])
        sell_rate = int(sell_plan["estimated_success"])
        # Do not call one side stronger when the difference is only noise.
        if buy_rate - sell_rate >= 10:
            result["stronger"] = "buy_limit"
        elif sell_rate - buy_rate >= 10:
            result["stronger"] = "sell_limit"
        else:
            result["stronger"] = "equal"
    elif buy_plan is not None:
        result["stronger"] = "buy_limit"
    else:
        result["stronger"] = "sell_limit"
    return result


def _parse_market_candle_time(value: Any, timezone_name: str) -> datetime | None:
    """Parse a provider candle time and normalize it to UTC.

    Twelve Data returns naive timestamps in the requested market-data timezone,
    while tests and some providers may return ISO timestamps with an offset.
    """
    text = str(value or "").strip()
    if not text:
        return None

    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                parsed = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
    if parsed is None:
        return None

    if parsed.tzinfo is None:
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name or "Asia/Muscat"))
        except ZoneInfoNotFoundError:
            parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _market_activity_status(
    market_summary: dict[str, Any] | None,
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Return whether fresh M5 data is available for a live trade decision.

    A stale M5 fallback or an old latest M5 candle produces one neutral state:
    ``السوق مغلق/البيانات غير محدثة``.  This avoids presenting old Friday or
    failed-provider data as a new technical ``watch`` signal.
    """
    if not isinstance(market_summary, dict):
        return {"active": True, "code": "unknown", "label": "بيانات السوق غير متاحة", "age_minutes": None}

    cache = market_summary.get("cache")
    frame_cache = cache.get("frames") if isinstance(cache, dict) else None
    m5_cache = frame_cache.get("M5") if isinstance(frame_cache, dict) else None
    if isinstance(m5_cache, dict) and str(m5_cache.get("status") or "") == "stale_fallback":
        return {
            "active": False,
            "code": "stale",
            "label": "السوق مغلق/البيانات غير محدثة",
            "age_minutes": None,
        }

    latest = market_summary.get("m5_latest_candle_time") or market_summary.get("latest_candle_time")
    latest_utc = _parse_market_candle_time(latest, str(market_summary.get("timezone") or "Asia/Muscat"))
    if latest_utc is None:
        # Do not break test/offline flows that do not include timestamps. In the
        # production path a timestamp is supplied by the market-data service.
        return {"active": True, "code": "unknown", "label": "وقت السوق غير متاح", "age_minutes": None}

    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age_minutes = max(0.0, (now.astimezone(timezone.utc) - latest_utc).total_seconds() / 60.0)
    try:
        max_age = max(7.0, min(60.0, float(os.getenv("MARKET_DATA_MAX_M5_AGE_MINUTES", "15"))))
    except ValueError:
        max_age = 15.0

    if age_minutes > max_age:
        return {
            "active": False,
            "code": "closed_or_stale",
            "label": "السوق مغلق/البيانات غير محدثة",
            "age_minutes": round(age_minutes, 1),
        }
    return {"active": True, "code": "live", "label": "السوق مباشر", "age_minutes": round(age_minutes, 1)}


def _is_candle_like_pixel(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, a = pixel
    if a < 120:
        return False
    brightness = (r + g + b) / 3.0
    if brightness < 45 or brightness > 245:
        return False
    chroma = max(r, g, b) - min(r, g, b)
    if chroma < 26:
        return False
    greenish = g >= r + 6 and g >= b - 8
    reddish = r >= g + 16 and r >= b + 8
    return greenish or reddish


def _detect_chart_box(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Best-effort detection of the visible chart rectangle inside app screenshots.

    The crop rule is strict: keep the chart *together with* its original right
    price axis, then allow the final renderer to shift that captured part left.
    Losing a slice from the far left is acceptable; losing the right price axis
    is not.
    """
    rgba = image.convert("RGBA")
    width, height = rgba.size
    if width < 120 or height < 160:
        return None

    px = rgba.load()
    row_step = 2 if height > 1200 else 1
    col_step = 2 if width > 700 else 1

    search_top = int(height * 0.10)
    search_bottom = int(height * 0.92)
    row_hits: list[int] = []
    min_row_hits = max(3, int(width * 0.004))
    for y in range(search_top, search_bottom, row_step):
        hits = 0
        for x in range(0, width, col_step):
            if _is_candle_like_pixel(px[x, y]):
                hits += 1
        row_hits.append(hits)

    active_rows = [search_top + idx * row_step for idx, hits in enumerate(row_hits) if hits >= min_row_hits]
    if len(active_rows) < 8:
        return None

    candle_top = min(active_rows)
    candle_bottom = max(active_rows)
    candle_height = max(40, candle_bottom - candle_top)

    col_top = max(0, candle_top - int(candle_height * 0.18))
    col_bottom = min(height, candle_bottom + int(candle_height * 0.18))
    min_col_hits = max(4, int((col_bottom - col_top) / max(20, 1 / row_step)))
    active_cols: list[int] = []
    for x in range(0, width, col_step):
        hits = 0
        for y in range(col_top, col_bottom, row_step):
            if _is_candle_like_pixel(px[x, y]):
                hits += 1
        if hits >= min_col_hits:
            active_cols.append(x)

    if len(active_cols) < 6:
        return None

    candle_left = min(active_cols)
    candle_right = max(active_cols)
    candle_width = max(40, candle_right - candle_left)

    # نحتفظ بهامش أصغر يسارًا لأن اختفاء جزء يسير من اليسار مقبول، بينما
    # يجب الحفاظ على محور الأسعار اليميني الأصلي كاملًا قدر الإمكان.
    left = max(0, candle_left - int(candle_width * 0.18))
    right = min(width, candle_right + int(candle_width * 0.62))
    top = max(0, candle_top - int(candle_height * 0.26))
    bottom = min(height, candle_bottom + int(candle_height * 0.34))

    # Prefer a visible right-side price axis when present.
    min_axis_width = max(60, int(width * 0.11))
    if right - candle_right < min_axis_width:
        right = min(width, candle_right + min_axis_width)

    if width - right < int(width * 0.04):
        right = width

    if right - left < int(width * 0.35) or bottom - top < int(height * 0.35):
        return None
    return int(left), int(top), int(right), int(bottom)


def _enhance_chart_crop(crop: Image.Image) -> Image.Image:
    """Improve readability of source-axis digits without changing geometry."""
    enhanced = crop.convert("RGBA")
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.08)
    enhanced = ImageEnhance.Sharpness(enhanced).enhance(1.18)

    axis_start = max(0, int(enhanced.width * 0.74))
    axis_strip = enhanced.crop((axis_start, 0, enhanced.width, enhanced.height))
    axis_strip = ImageEnhance.Contrast(axis_strip).enhance(1.30)
    axis_strip = ImageEnhance.Sharpness(axis_strip).enhance(1.90)
    axis_strip = ImageEnhance.Brightness(axis_strip).enhance(1.02)
    enhanced.paste(axis_strip, (axis_start, 0))
    return enhanced


def _prepare_analysis_image(image_path: Path) -> tuple[Path, dict[str, Any]]:
    """Create the same clean chart viewport used by the final renderer.

    Geometry extraction and final rendering must see identical pixels. This
    prevents the AI geometry reader from using the broker toolbar while the
    renderer uses another crop, which previously shifted every price line.
    """
    meta: dict[str, Any] = {"used_smart_crop": False}
    prepared, viewport_meta = prepare_chart_viewport_image(image_path)
    if prepared is None:
        return image_path, meta
    try:
        crop_path = image_path.with_name(f"{image_path.stem}_chartviewport.png")
        prepared.save(crop_path)
    except Exception:
        return image_path, meta

    meta.update(viewport_meta)
    meta.update({
        "used_smart_crop": True,
        "smart_crop_mode": "canonical_chart_viewport",
        "smart_crop_size": [prepared.width, prepared.height],
    })
    return crop_path, meta

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
                "قناة هابطة", "قناة صاعدة", "M", "W", "كسر وإعادة اختبار", "لا يوجد",
            ],
        },
        "pattern_confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "pattern_lines": {"type": "array", "items": LINE, "maxItems": 4},
        "pattern_path": {"type": "array", "items": POINT, "maxItems": 12},
        "scenario": {"type": "string"},
        "bullish_scenario": {"type": "string"},
        "bearish_scenario": {"type": "string"},
        "invalidation_condition": {"type": "string"},
        "macro_note": {"type": "string"},
        "note": {"type": "string"},
        "memory_matches": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
    },
    "required": [
        "chart_readable", "candles", "direction", "buy_probability", "sell_probability",
        "setup_state", "entry_kind", "confirmation", "current_price", "current_price_y_ratio", "image_price_high",
        "image_price_low", "image_axis_labels", "support_levels", "resistance_levels", "entry", "stop_loss",
        "stop_reason", "target_1", "target_2",
        "target_3", "pattern_type", "pattern_confidence", "pattern_lines", "pattern_path",
        "scenario", "bullish_scenario", "bearish_scenario",
        "invalidation_condition", "macro_note", "note", "memory_matches",
    ],
}

GEOMETRY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "chart_readable": {"type": "boolean"},
        "current_price": NUM_NULL,
        "current_price_y_ratio": NUM_NULL,
        "image_price_high": NUM_NULL,
        "image_price_low": NUM_NULL,
        "image_axis_labels": {"type": "array", "items": AXIS_LABEL, "maxItems": 24},
    },
    "required": [
        "chart_readable",
        "current_price",
        "current_price_y_ratio",
        "image_price_high",
        "image_price_low",
        "image_axis_labels",
    ],
}

MARKET_DECISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "direction": {"type": "string", "enum": ["صاعد", "هابط", "عرضي", "غير واضح"]},
        "buy_probability": {"type": "integer", "minimum": 5, "maximum": 95},
        "sell_probability": {"type": "integer", "minimum": 5, "maximum": 95},
        "setup_state": {"type": "string", "enum": ["مؤكد", "مشروط", "مراقبة", "غير صالح"]},
        "entry_kind": {"type": "string", "enum": ["مباشر", "اختراق", "إعادة اختبار", "مراقبة"]},
        "confirmation": {"type": "string"},
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
                "قناة هابطة", "قناة صاعدة", "M", "W", "كسر وإعادة اختبار", "لا يوجد",
            ],
        },
        "pattern_confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "pattern_lines": {"type": "array", "items": LINE, "maxItems": 4},
        "pattern_path": {"type": "array", "items": POINT, "maxItems": 12},
        "scenario": {"type": "string"},
        "bullish_scenario": {"type": "string"},
        "bearish_scenario": {"type": "string"},
        "invalidation_condition": {"type": "string"},
        "macro_note": {"type": "string"},
        "note": {"type": "string"},
        "memory_matches": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
    },
    "required": [
        "direction", "buy_probability", "sell_probability", "setup_state",
        "entry_kind", "confirmation", "support_levels", "resistance_levels",
        "entry", "stop_loss", "stop_reason", "target_1", "target_2", "target_3",
        "pattern_type", "pattern_confidence", "pattern_lines", "pattern_path",
        "scenario", "bullish_scenario", "bearish_scenario",
        "invalidation_condition", "macro_note", "note", "memory_matches",
    ],
}

ANALYSIS_SNAPSHOT_CACHE_VERSION = 7
_TIMEFRAME_SECONDS = {"M5": 300, "M15": 900, "H1": 3600, "H4": 14400}
_ANALYSIS_SNAPSHOT_CACHE_LOCK = threading.Lock()
_ANALYSIS_SNAPSHOT_DECISION_LOCK = threading.Lock()



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




def _request_structured_openai(
    *,
    prompt: str,
    schema: dict[str, Any],
    schema_name: str,
    image_path: Path | None = None,
    max_output_tokens: int = 5000,
) -> dict[str, Any]:
    """Send one strict structured-output request with shared retry handling."""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("متغير OPENAI_API_KEY غير موجود في Railway.")

    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    if image_path is not None:
        content.append({"type": "input_image", "image_url": _data_url(image_path)})

    body = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "max_output_tokens": max(1200, min(8000, int(max_output_tokens))),
        "input": [{"role": "user", "content": content}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
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
            response.status_code,
            error_type,
            error_code,
            request_id,
            error_message,
        )
        if response.status_code == 429:
            combined = f"{error_type} {error_code} {error_message}".lower()
            if "insufficient_quota" in combined or "quota" in combined:
                raise RuntimeError("خطأ خدمة التحليل (429): رصيد أو حد الإنفاق للمشروع غير متاح.")
            if "token" in combined:
                raise RuntimeError(
                    "خطأ خدمة التحليل (429): تم تجاوز حد الرموز في الدقيقة؛ "
                    "تم تقليل حجم الطلب واستخدام النموذج الأخف، انتظر دقيقة ثم أعد المحاولة."
                )
            raise RuntimeError(
                "خطأ خدمة التحليل (429): تم بلوغ حد الطلبات مؤقتًا؛ انتظر دقيقة ثم أعد المحاولة."
            )
        detail = error_code or error_type or "خطأ غير معروف"
        raise RuntimeError(f"خطأ خدمة التحليل ({response.status_code}): {detail}.")

    try:
        response_payload = response.json()
        system_status_store.record_openai_response(
            model=str(body.get("model") or ""),
            usage=response_payload.get("usage") if isinstance(response_payload, dict) else None,
            request_id=response.headers.get("x-request-id", ""),
        )
        return json.loads(_text(response_payload))
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("لم ترجع خدمة التحليل JSON صالحًا.") from exc


def _analysis_snapshot_cache_path() -> Path:
    return Path(
        os.getenv(
            "ANALYSIS_SNAPSHOT_CACHE_PATH",
            "/tmp/saleem_analysis_snapshot_cache.json",
        ).strip()
    )


def _market_reference_time(
    market_context: dict[str, Any],
    *,
    now_utc: datetime | None = None,
) -> datetime:
    """Return the instant used to decide whether provider candles are closed."""
    if now_utc is not None:
        return now_utc.astimezone(timezone.utc) if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc)

    fetched_at = _parse_market_candle_time(
        market_context.get("fetched_at"),
        str(market_context.get("timezone") or "Asia/Muscat"),
    )
    return fetched_at or datetime.now(timezone.utc)


def _closed_frame_candles(
    timeframe: str,
    candles: Any,
    *,
    market_context: dict[str, Any],
    now_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return only fully closed candles for one timeframe.

    Twelve Data timestamps represent candle start times.  A candle is accepted
    only after its full timeframe duration has elapsed.  If timestamps cannot be
    parsed, the conservative fallback drops the tail candle because it is the
    most likely still-forming candle.
    """
    raw_rows = [copy.deepcopy(c) for c in candles if isinstance(c, dict)] if isinstance(candles, list) else []
    if not raw_rows:
        return []

    duration = _TIMEFRAME_SECONDS.get(str(timeframe).upper())
    if duration is None:
        return raw_rows[:-1] if len(raw_rows) > 1 else raw_rows

    reference = _market_reference_time(market_context, now_utc=now_utc)
    try:
        grace = max(0.0, min(30.0, float(os.getenv("CLOSED_CANDLE_GRACE_SECONDS", "3"))))
    except ValueError:
        grace = 3.0
    cutoff = reference.timestamp() - grace

    parsed_any = False
    closed: list[dict[str, Any]] = []
    for candle in raw_rows:
        start = _parse_market_candle_time(
            candle.get("time") or candle.get("datetime"),
            str(market_context.get("timezone") or "Asia/Muscat"),
        )
        if start is None:
            continue
        parsed_any = True
        if start.timestamp() + duration <= cutoff:
            closed.append(candle)

    if parsed_any:
        return closed
    return raw_rows[:-1] if len(raw_rows) > 1 else raw_rows


def _closed_market_context(
    market_context: dict[str, Any],
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Build the immutable analytical input from closed candles only."""
    result = copy.deepcopy(market_context)
    frames = market_context.get("frames") if isinstance(market_context, dict) else None
    closed_frames: dict[str, list[dict[str, Any]]] = {}
    for timeframe in ("H4", "H1", "M15", "M5"):
        candles = frames.get(timeframe) if isinstance(frames, dict) else None
        closed_frames[timeframe] = _closed_frame_candles(
            timeframe,
            candles,
            market_context=market_context,
            now_utc=now_utc,
        )

    m5 = closed_frames.get("M5") or []
    if not m5:
        raise RuntimeError("لا توجد شمعة M5 مغلقة صالحة لبناء نسخة التحليل.")

    last_closed = m5[-1]
    last_closed_time = str(last_closed.get("time") or last_closed.get("datetime") or "").strip()
    if not last_closed_time:
        raise RuntimeError("تعذر تحديد وقت آخر شمعة M5 مغلقة.")

    result["frames"] = closed_frames
    result["latest_candle_time"] = last_closed_time
    result["m5_last_closed_candle_time"] = last_closed_time
    result["analysis_candle_mode"] = "closed_only"
    return result


def _analysis_rules_fingerprint() -> str:
    """Invalidate cached decisions whenever rules, knowledge or code policy changes."""
    digest = hashlib.sha256()
    for path in (SPEC_PATH, PERMANENT_PROMPT_PATH):
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(str(path).encode("utf-8"))
    if KNOWLEDGE_DIR.exists():
        for path in sorted(KNOWLEDGE_DIR.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".json", ".md", ".svg"}:
                continue
            digest.update(str(path.relative_to(KNOWLEDGE_DIR)).encode("utf-8"))
            try:
                digest.update(path.read_bytes())
            except OSError:
                continue
    return digest.hexdigest()[:20]


def _frame_candle_fingerprint(frames: Any) -> str:
    """Hash recent closed OHLC values, not only the candle timestamp."""
    payload: dict[str, Any] = {}
    for timeframe, keep in (("H4", 10), ("H1", 14), ("M15", 20), ("M5", 24)):
        candles = frames.get(timeframe) if isinstance(frames, dict) else None
        rows: list[list[Any]] = []
        for item in candles[-keep:] if isinstance(candles, list) else []:
            if not isinstance(item, dict):
                continue
            rows.append([
                item.get("time") or item.get("datetime"),
                item.get("open"), item.get("high"), item.get("low"), item.get("close"),
            ])
        payload[timeframe] = rows
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _stable_market_snapshot_payload(market_context: dict[str, Any]) -> dict[str, Any]:
    """Use the latest CLOSED M5 candle plus data/rules fingerprints as key."""
    closed_context = (
        market_context
        if str(market_context.get("analysis_candle_mode") or "") == "closed_only"
        else _closed_market_context(market_context)
    )
    frames = closed_context.get("frames") or {}
    m5 = frames.get("M5") or [] if isinstance(frames, dict) else []
    last_closed = m5[-1] if m5 else {}
    return {
        "version": ANALYSIS_SNAPSHOT_CACHE_VERSION,
        "symbol": str(closed_context.get("symbol") or "XAU/USD"),
        "timeframe": "M5",
        "last_closed_m5_time": str(
            closed_context.get("m5_last_closed_candle_time")
            or last_closed.get("time")
            or last_closed.get("datetime")
            or ""
        ),
        "rules_hash": _analysis_rules_fingerprint(),
    }


def _market_snapshot_key(market_context: dict[str, Any]) -> str:
    payload = _stable_market_snapshot_payload(market_context)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _load_analysis_snapshot_cache() -> dict[str, Any]:
    path = _analysis_snapshot_cache_path()
    if not path.exists():
        return {"version": ANALYSIS_SNAPSHOT_CACHE_VERSION, "entries": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": ANALYSIS_SNAPSHOT_CACHE_VERSION, "entries": {}}
    if not isinstance(payload, dict) or payload.get("version") != ANALYSIS_SNAPSHOT_CACHE_VERSION:
        return {"version": ANALYSIS_SNAPSHOT_CACHE_VERSION, "entries": {}}
    if not isinstance(payload.get("entries"), dict):
        payload["entries"] = {}
    return payload


def _read_cached_market_decision(snapshot_key: str) -> dict[str, Any] | None:
    if os.getenv("ANALYSIS_SNAPSHOT_CACHE_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        return None
    with _ANALYSIS_SNAPSHOT_CACHE_LOCK:
        payload = _load_analysis_snapshot_cache()
        item = payload.get("entries", {}).get(snapshot_key)
        if not isinstance(item, dict) or not isinstance(item.get("decision"), dict):
            return None
        return copy.deepcopy(item["decision"])


def _write_cached_market_decision(snapshot_key: str, decision: dict[str, Any]) -> None:
    if os.getenv("ANALYSIS_SNAPSHOT_CACHE_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        return
    path = _analysis_snapshot_cache_path()
    try:
        max_entries = max(4, min(96, int(os.getenv("ANALYSIS_SNAPSHOT_CACHE_ENTRIES", "24"))))
    except ValueError:
        max_entries = 24
    with _ANALYSIS_SNAPSHOT_CACHE_LOCK:
        payload = _load_analysis_snapshot_cache()
        entries = payload.setdefault("entries", {})
        entries[snapshot_key] = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "decision": copy.deepcopy(decision),
        }
        ordered = sorted(
            entries.items(),
            key=lambda pair: str((pair[1] or {}).get("saved_at") or ""),
            reverse=True,
        )[:max_entries]
        payload["entries"] = dict(ordered)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(path.suffix + ".tmp")
            temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            temp.replace(path)
        except OSError:
            logging.warning("تعذر حفظ قفل اتساق التحليل في %s", path)


def _extract_chart_geometry(path: Path) -> dict[str, Any]:
    """Read only broker price geometry; never ask the image to decide the trade."""
    prompt = """أنت قارئ هندسي لمحور سعر شارت XAUUSD فقط. هذه ليست مهمة تحليل سوق.

ممنوع تمامًا استنتاج الاتجاه أو الدعم أو المقاومة أو الدخول أو الأهداف من شكل الشموع.
استخدم الصورة فقط لاستخراج الإحداثيات السعرية التالية من بوكس الشارت ومحور السعر اليميني الأصلي:
- chart_readable: true فقط إذا أمكن قراءة ملصق السعر الحالي أو محور متناسق.
- current_price: الرقم الظاهر في ملصق السعر الحالي المرتبط بآخر شمعة. لا تستخدم رقم أمر التداول العلوي.
- current_price_y_ratio: موضع مركز خط السعر الحالي داخل بوكس الشارت؛ 0 أعلى و1 أسفل.
- image_price_high وimage_price_low: أعلى وأدنى رقمين واضحين على المحور.
- image_axis_labels: كل أرقام المحور الواضحة من الأعلى للأسفل مع y_ratio لمركز كل رقم.

إذا كانت الصورة كاملة للهاتف أو تحتوي شريط أمر تداول، تجاهل كل العناصر خارج بوكس الشارت. لا تخمّن رقمًا مقصوصًا، ولا تعِد أي نتيجة تحليلية."""
    geometry = _request_structured_openai(
        prompt=prompt,
        schema=GEOMETRY_SCHEMA,
        schema_name="saleem_chart_geometry_only",
        image_path=path,
        max_output_tokens=1400,
    )
    geometry["image_axis_labels"] = _normalize_axis_labels(geometry.get("image_axis_labels"))
    return geometry


def _market_decision_prompt(
    market_context: dict[str, Any],
    market_summary: dict[str, Any],
) -> str:
    return f"""أنت محرك القرار السوقي الثابت في SaleeM لتحليل الذهب XAUUSD وتنفيذ M5.

هذه المرحلة لا تستقبل صورة شارت مطلقًا. بيانات الشموع المرفقة مغلقة بالكامل، وآخر شمعة M5 مغلقة هي مفتاح نسخة التحليل. لذلك يجب أن يكون القرار مبنيًا حصريًا على بيانات السوق المرفقة:
- H4 للاتجاه الرئيسي.
- H1 للبنية.
- M15 للتفعيل.
- M5 للتوقيت.

===== دستور SaleeM المعتمد =====
{load_final_spec()}
===== نهاية الدستور =====

===== قاعدة التحليل الدائمة =====
{load_permanent_analysis_prompt()}
===== نهاية القاعدة =====

قواعد الاتساق الملزمة، وهي الأعلى أولوية في هذه المرحلة:
1) لا تستخدم شكل لقطة الشاشة أو الزوم أو وجود أمر تداول في أي قرار.
2) لا تستخدم الشمعة الجارية في الاتجاه أو الحالة أو المستويات؛ استخدم الشموع المغلقة فقط.
3) لا يبدأ قرار جديد إلا عندما يتغير توقيت آخر شمعة M5 مغلقة.
4) جميع أسعار support/resistance/entry/stop/targets تكون على مقياس Twelve Data الحالي فقط.
5) الصورة ستستخدم لاحقًا في مرحلة مستقلة لمعايرة محور الوسيط وإسقاط الأسعار، فلا تعدّل القرار لتناسب أي مساحة مرئية.
6) لنفس مفتاح آخر شمعة M5 مغلقة يجب أن تعيد نفس الاتجاه والحالة والاحتمالات والمستويات.
7) لا يوجد انحياز شراء أو بيع. لا تحوّل التعادل إلى صعود. إذا اتفق M15 وM5 على حركة قوية معاكسة لـ H4/H1 فاعرض الحركة القصيرة أو استخدم مراقبة، ولا تكرر الاتجاه القديم آليًا.
8) لا تجعل كل النتائج مشروطًا: أقل من 55% مراقبة؛ 55 إلى أقل من 70% مشروط فقط مع تفعيل M15/M5 واضح؛ و70% فأكثر يصبح مؤكدًا عند توافق M15 وM5 وتأكيد شمعة M5 مغلقة وعدم وجود تعارض يمنع التنفيذ.
9) اختر أقرب دعمين وأقرب مقاومتين حقيقيين من بيانات السوق، واجمع المستويات المتقاربة.
10) اجعل النصوص الشرطية بلا أسعار رقمية داخل الجمل؛ الأسعار موجودة في الحقول الرقمية المنفصلة.
11) entry قريب وواقعي، والوقف خلف أقرب إبطال محلي، وثلاثة أهداف مرتبة في جهة الصفقة.
12) راجع صراحةً نموذج M ونموذج W والمثلثات والأوتاد والقنوات والكسر وإعادة الاختبار. أعد اسم النموذج بالحرف M أو W بدل قمتان أو قاعان، ولا تُرجع نموذجًا إلا إذا اكتملت بنيته على الشموع المغلقة، واكتب في memory_matches القواعد أو النماذج التي طابقتها فعلًا.
13) أنشئ في النص الداخلي احتمال شراء واحتمال بيع مستقلين ولا تمنع أحدهما بسبب اتجاه الفريمات العليا؛ الاتجاه المخالف يخفض القوة فقط. واجهة الرسم الحالية قد تعرض القرار الأساسي وحده، بينما يبني الكود لاحقًا السيناريوهين رقميًا بصورة حتمية.
14) pattern_lines وpattern_path نسبية لنافذة M5 المرفقة، ولا ترسم نموذجًا غير واضح.

ملخص الفريمات الحسابي:
{json.dumps(market_summary, ensure_ascii=False)}

بيانات الشموع:
{json.dumps(market_context, ensure_ascii=False)}

الذاكرة المرجعية للقراءة فقط:
{memory_context(KNOWLEDGE_DIR)}
"""


def _get_market_decision(
    market_context: dict[str, Any],
    market_summary: dict[str, Any],
) -> tuple[dict[str, Any], str, bool]:
    snapshot_key = _market_snapshot_key(market_context)
    cached = _read_cached_market_decision(snapshot_key)
    if cached is not None:
        return cached, snapshot_key, True

    # A second check under one process-wide decision lock prevents two uploads
    # of the same chart from generating different first decisions concurrently.
    with _ANALYSIS_SNAPSHOT_DECISION_LOCK:
        cached = _read_cached_market_decision(snapshot_key)
        if cached is not None:
            return cached, snapshot_key, True
        decision = _request_structured_openai(
            prompt=_market_decision_prompt(market_context, market_summary),
            schema=MARKET_DECISION_SCHEMA,
            schema_name="saleem_market_snapshot_decision",
            max_output_tokens=max(2600, min(5200, int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "3900")))),
        )
        _write_cached_market_decision(snapshot_key, decision)
        return decision, snapshot_key, False


def _shift_numeric_price(value: Any, offset: float) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return round(float(number) + offset, 2)


def _bind_market_analysis_to_image(
    canonical: dict[str, Any],
    geometry: dict[str, Any],
    *,
    snapshot_key: str,
    snapshot_reused: bool,
) -> dict[str, Any]:
    """Project one immutable market decision onto the uploaded broker axis."""
    result = copy.deepcopy(canonical)
    provider_current = float(canonical.get("current_price") or canonical.get("market_last_close") or 0.0)
    image_current = _number(geometry.get("current_price"))
    chart_readable = bool(geometry.get("chart_readable") and image_current is not None)
    displayed_current = float(image_current) if image_current is not None else provider_current
    offset = displayed_current - provider_current

    shifted_candles: list[dict[str, Any]] = []
    for candle in result.get("candles") or []:
        if not isinstance(candle, dict):
            continue
        shifted = dict(candle)
        for key in ("open", "high", "low", "close"):
            shifted[key] = _shift_numeric_price(candle.get(key), offset)
        shifted_candles.append(shifted)
    result["candles"] = shifted_candles

    for level_key in ("support_levels", "resistance_levels"):
        shifted_levels: list[dict[str, Any]] = []
        for level in result.get(level_key) or []:
            if not isinstance(level, dict):
                continue
            shifted = dict(level)
            shifted["price"] = _shift_numeric_price(level.get("price"), offset)
            shifted_levels.append(shifted)
        result[level_key] = shifted_levels

    swings = result.get("confirmed_limit_swings")
    if isinstance(swings, dict):
        shifted_swings: dict[str, list[dict[str, Any]]] = {"troughs": [], "peaks": []}
        for swing_key in ("troughs", "peaks"):
            for item in swings.get(swing_key) or []:
                if not isinstance(item, dict):
                    continue
                shifted = dict(item)
                shifted["price"] = _shift_numeric_price(item.get("price"), offset)
                shifted_swings[swing_key].append(shifted)
        result["confirmed_limit_swings"] = shifted_swings

    for key in ("entry", "stop_loss", "target_1", "target_2", "target_3"):
        result[key] = _shift_numeric_price(result.get(key), offset)

    pressure = result.get("level_pressure")
    if isinstance(pressure, dict):
        pressure = dict(pressure)
        for key in ("nearest_resistance", "nearest_support"):
            pressure[key] = _shift_numeric_price(pressure.get(key), offset)
        result["level_pressure"] = pressure

    labels = _normalize_axis_labels(geometry.get("image_axis_labels"))
    current_y = _number(geometry.get("current_price_y_ratio")) if image_current is not None else None
    if current_y is not None:
        current_y = max(0.0, min(1.0, float(current_y)))

    image_high = _number(geometry.get("image_price_high"))
    image_low = _number(geometry.get("image_price_low"))
    if len(labels) >= 2:
        image_high = max(float(labels[0]["price"]), image_high or float("-inf"))
        image_low = min(float(labels[-1]["price"]), image_low or float("inf"))
    if image_high is None or image_high <= displayed_current:
        image_high = max(float(candle["high"]) for candle in shifted_candles)
    if image_low is None or image_low >= displayed_current:
        image_low = min(float(candle["low"]) for candle in shifted_candles)

    result.update(
        {
            "chart_readable": chart_readable,
            "current_price": round(displayed_current, 2),
            "current_price_y_ratio": round(current_y, 4) if current_y is not None else None,
            "current_price_source": "chart_image" if image_current is not None else "market_fallback",
            "image_price_high": round(float(image_high), 2),
            "image_price_low": round(float(image_low), 2),
            "image_axis_labels": labels,
            "price_range_source": "chart_image" if len(labels) >= 2 else "market_candles_fallback",
            "provider_market_last_close": round(provider_current, 2),
            "market_price_offset": round(offset, 3),
            "analysis_snapshot_key": snapshot_key,
            "analysis_snapshot_reused": bool(snapshot_reused),
            "analysis_consistency_lock": "last_closed_m5",
            "analysis_input_role": "market_data_only",
            "image_input_role": "axis_geometry_only",
            "price_projection_mode": "closed_m5_decision_projected_once_to_broker_axis",
        }
    )

    if (
        result.get("draw_mode") == "conditional"
        and result.get("entry_activation_status") != "active"
        and result.get("entry") is not None
        and result.get("direction") in {"صاعد", "هابط"}
    ):
        side = "فوق" if result.get("direction") == "صاعد" else "تحت"
        activation_reason = f"بانتظار إغلاق وثبات {side} {float(result['entry']):.1f}"
        result["entry_activation_reason"] = activation_reason
        result["confirmation"] = activation_reason
        result["scenario"] = (
            f"الاتجاه العام {result.get('higher_timeframe_direction') or 'غير واضح'} "
            f"والحركة الحالية {result.get('current_movement') or 'غير واضح'}؛ "
            f"{activation_reason}"
        )[:92]

    if result.get("draw_mode") in {"conditional", "confirmed"} and result.get("stop_loss") is not None:
        result["invalidation_condition"] = (
            f"إلغاء السيناريو عند تجاوز وقف الخسارة {float(result['stop_loss']):.1f}"
        )
    return result

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



def _raw_frame_candles(raw: Any) -> list[dict[str, Any]]:
    """Normalize higher-frame candles for swing detection without UI limits."""
    result: list[dict[str, Any]] = []
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
        result.append(
            {
                "time": _normalize_candle_time(item.get("time"), index),
                "open": open_,
                "high": true_high,
                "low": true_low,
                "close": close,
            }
        )
    return result[-120:]


def _frame_atr(candles: list[dict[str, Any]], periods: int = 14) -> float:
    sample = candles[-periods:] if candles else []
    if not sample:
        return 1.0
    return max(0.01, sum(float(item["high"]) - float(item["low"]) for item in sample) / len(sample))


def _extract_confirmed_frame_swings(raw: Any, timeframe: str) -> list[dict[str, Any]]:
    """Extract confirmed pivot highs/lows with candles on both sides."""
    candles = _raw_frame_candles(raw)
    settings = {
        "H4": (2, 82),
        "H1": (2, 76),
        "M15": (3, 64),
        "M5": (4, 54),
    }
    window, base_strength = settings.get(timeframe, (3, 58))
    if len(candles) < window * 2 + 5:
        return []
    atr = _frame_atr(candles)
    points: list[dict[str, Any]] = []

    for index in range(window, len(candles) - window):
        candle = candles[index]
        left = candles[index - window:index]
        right = candles[index + 1:index + window + 1]
        high = float(candle["high"])
        low = float(candle["low"])
        left_high = max(float(item["high"]) for item in left)
        right_high = max(float(item["high"]) for item in right)
        left_low = min(float(item["low"]) for item in left)
        right_low = min(float(item["low"]) for item in right)

        is_peak = high > left_high and high >= right_high
        is_trough = low < left_low and low <= right_low
        age = len(candles) - 1 - index

        if is_peak:
            reversal_depth = min(high - left_low, high - right_low)
            if reversal_depth >= atr * 0.48:
                tolerance = max(0.15, atr * 0.16)
                touches = sum(1 for item in candles if abs(float(item["high"]) - high) <= tolerance)
                prominence = reversal_depth / atr
                strength = int(round(base_strength + min(10.0, prominence * 3.0) + min(6, touches) - min(10.0, age * 0.16)))
                points.append(
                    {
                        "kind": "peak",
                        "price": round(high, 3),
                        "time": candle.get("time"),
                        "timeframe": timeframe,
                        "strength": max(45, min(95, strength)),
                        "touches": max(1, touches),
                        "level_atr": round(atr, 3),
                        "age": age,
                    }
                )

        if is_trough:
            reversal_depth = min(left_high - low, right_high - low)
            if reversal_depth >= atr * 0.48:
                tolerance = max(0.15, atr * 0.16)
                touches = sum(1 for item in candles if abs(float(item["low"]) - low) <= tolerance)
                prominence = reversal_depth / atr
                strength = int(round(base_strength + min(10.0, prominence * 3.0) + min(6, touches) - min(10.0, age * 0.16)))
                points.append(
                    {
                        "kind": "trough",
                        "price": round(low, 3),
                        "time": candle.get("time"),
                        "timeframe": timeframe,
                        "strength": max(45, min(95, strength)),
                        "touches": max(1, touches),
                        "level_atr": round(atr, 3),
                        "age": age,
                    }
                )
    return points


def _build_confirmed_limit_swings(frames: Any, current: float) -> dict[str, list[dict[str, Any]]]:
    """Build higher-frame swing levels for manual Buy/Sell Limit plans.

    A level must originate from a real confirmed pivot. H4/H1 are primary;
    M15/M5 only confirm a nearby higher-frame peak or trough.
    """
    if not isinstance(frames, dict):
        return {"troughs": [], "peaks": []}

    all_points: list[dict[str, Any]] = []
    by_frame: dict[str, list[dict[str, Any]]] = {}
    for timeframe in ("H4", "H1", "M15", "M5"):
        points = _extract_confirmed_frame_swings(frames.get(timeframe), timeframe)
        by_frame[timeframe] = points
        all_points.extend(points)

    result: dict[str, list[dict[str, Any]]] = {"troughs": [], "peaks": []}
    primary = [point for point in all_points if point.get("timeframe") in {"H4", "H1"}]
    for point in primary:
        kind = str(point.get("kind"))
        price = float(point["price"])
        if kind == "trough" and price >= current:
            continue
        if kind == "peak" and price <= current:
            continue

        tolerance = max(0.25, min(3.0, float(point.get("level_atr") or 1.0) * 0.34))
        confirming_frames: list[str] = []
        for timeframe in ("H4", "H1", "M15", "M5"):
            if timeframe == point.get("timeframe"):
                confirming_frames.append(timeframe)
                continue
            if any(
                other.get("kind") == kind
                and abs(float(other["price"]) - price) <= tolerance
                for other in by_frame.get(timeframe, [])
            ):
                confirming_frames.append(timeframe)

        strength = int(point.get("strength") or 0)
        if "M15" in confirming_frames:
            strength += 4
        if "M5" in confirming_frames:
            strength += 3
        if "H4" in confirming_frames and "H1" in confirming_frames:
            strength += 6

        item = {
            **point,
            "strength": max(50, min(95, strength)),
            "source": "confirmed_swing",
            "confirmation_frames": confirming_frames,
        }
        key = "troughs" if kind == "trough" else "peaks"
        result[key].append(item)

    for key in ("troughs", "peaks"):
        ordered = sorted(
            result[key],
            key=lambda item: (
                -int(item.get("strength") or 0),
                int(item.get("age") or 999),
                abs(float(item["price"]) - current),
            ),
        )
        deduped: list[dict[str, Any]] = []
        for item in ordered:
            tolerance = max(0.25, min(2.5, float(item.get("level_atr") or 1.0) * 0.24))
            if any(abs(float(item["price"]) - float(existing["price"])) <= tolerance for existing in deduped):
                continue
            deduped.append(item)
        result[key] = deduped[:8]
    return result



def _scalp_point_size() -> float:
    """Return the broker-point size used for the educational +5/+10 targets.

    Gold brokers do not all name a "point" the same way. SaleeM therefore
    keeps the conversion configurable and always returns the final price too.
    The default is 0.10 USD per point: five points = 0.50 USD and ten = 1.00.
    """
    try:
        value = float(os.getenv("SALEEM_SCALP_POINT_SIZE", str(DEFAULT_SCALP_POINT_SIZE)))
    except (TypeError, ValueError):
        value = DEFAULT_SCALP_POINT_SIZE
    return max(0.01, min(5.0, value))


def _analysis_frame_direction(analysis: dict[str, Any], timeframe: str) -> str:
    frames = analysis.get("frame_directions")
    item = frames.get(timeframe) if isinstance(frames, dict) else None
    if isinstance(item, dict):
        return str(item.get("direction") or "غير واضح")
    return str(item or "غير واضح")


def _pattern_short_name(value: Any) -> str:
    name = str(value or "لا يوجد")
    return {"قمتان": "M", "قاعان": "W"}.get(name, name)


def _structural_candidates(
    analysis: dict[str, Any],
    *,
    kind: str,
    reference_price: float,
) -> list[dict[str, Any]]:
    """Collect real support/resistance and confirmed swings for one side."""
    candidates: list[dict[str, Any]] = []
    if kind == "peak":
        level_key, swing_key = "resistance_levels", "peaks"
        valid = lambda price: price > reference_price
        default_source = "مقاومة"
    else:
        level_key, swing_key = "support_levels", "troughs"
        valid = lambda price: price < reference_price
        default_source = "دعم"

    for item in analysis.get(level_key) or []:
        if not isinstance(item, dict):
            continue
        price = _number(item.get("price"))
        if price is None or not valid(float(price)):
            continue
        candidates.append(
            {
                "price": round(float(price), 2),
                "strength": max(0, min(100, int(item.get("strength") or 50))),
                "touches": max(1, int(item.get("touches") or 1)),
                "timeframe": "",
                "source": default_source,
            }
        )

    swings = analysis.get("confirmed_limit_swings")
    if isinstance(swings, dict):
        for item in swings.get(swing_key) or []:
            if not isinstance(item, dict):
                continue
            price = _number(item.get("price"))
            if price is None or not valid(float(price)):
                continue
            timeframe = str(item.get("timeframe") or "")
            candidates.append(
                {
                    "price": round(float(price), 2),
                    "strength": max(0, min(100, int(item.get("strength") or 55))),
                    "touches": max(1, int(item.get("touches") or 1)),
                    "timeframe": timeframe,
                    "source": f"{'قمة' if kind == 'peak' else 'قاع'} مؤكد{(' ' + timeframe) if timeframe else ''}",
                }
            )

    # Merge near-identical levels while preserving the strongest evidence.
    point_size = _scalp_point_size()
    tolerance = max(0.05, point_size * 0.75)
    ordered = sorted(candidates, key=lambda item: abs(float(item["price"]) - reference_price))
    merged: list[dict[str, Any]] = []
    for item in ordered:
        duplicate = next(
            (existing for existing in merged if abs(float(existing["price"]) - float(item["price"])) <= tolerance),
            None,
        )
        if duplicate is None:
            merged.append(item)
        elif int(item.get("strength") or 0) > int(duplicate.get("strength") or 0):
            duplicate.update(item)
    return merged


def _most_probable_extreme(
    analysis: dict[str, Any],
    *,
    kind: str,
) -> dict[str, Any] | None:
    """Choose the most plausible next peak/trough, balancing strength and distance."""
    current = float(analysis.get("current_price") or analysis.get("market_last_close") or 0.0)
    try:
        candles = _normalize_candles(analysis.get("candles"))
    except RuntimeError:
        candles = [
            item for item in (analysis.get("candles") or [])
            if isinstance(item, dict) and all(_number(item.get(key)) is not None for key in ("open", "high", "low", "close"))
        ]
    atr = max(0.05, _atr(candles)) if candles else 1.0
    candidates = _structural_candidates(analysis, kind=kind, reference_price=current)
    if not candidates:
        return None

    timeframe_bonus = {"H4": 10, "H1": 8, "M15": 5, "M5": 2, "": 0}
    for item in candidates:
        distance = abs(float(item["price"]) - current)
        strength = int(item.get("strength") or 50)
        touches = min(5, int(item.get("touches") or 1))
        proximity_penalty = min(32.0, (distance / atr) * 5.5)
        item["selection_score"] = round(
            strength
            + timeframe_bonus.get(str(item.get("timeframe") or ""), 0)
            + touches * 1.2
            - proximity_penalty,
            2,
        )
        item["distance"] = round(distance, 2)
    best = max(
        candidates,
        key=lambda item: (
            float(item.get("selection_score") or 0.0),
            -float(item.get("distance") or 0.0),
        ),
    )
    return {
        "price": round(float(best["price"]), 2),
        "strength": int(best.get("strength") or 0),
        "source": str(best.get("source") or ("قمة" if kind == "peak" else "قاع")),
        "timeframe": str(best.get("timeframe") or ""),
        "distance": round(float(best.get("distance") or 0.0), 2),
    }


def _scalp_targets(
    analysis: dict[str, Any],
    *,
    direction: str,
    entry: float,
) -> dict[str, Any]:
    """Build +5/+10 point targets and stop them at nearer real barriers."""
    point_size = _scalp_point_size()
    sign = 1.0 if direction == "صاعد" else -1.0
    raw_quick = round(entry + sign * 5 * point_size, 2)
    raw_extended = round(entry + sign * 10 * point_size, 2)
    kind = "peak" if direction == "صاعد" else "trough"
    candidates = _structural_candidates(analysis, kind=kind, reference_price=entry)
    prices = sorted(
        {round(float(item["price"]), 2) for item in candidates},
        reverse=direction == "هابط",
    )

    def before_or_at(value: float, limit: float) -> bool:
        return value <= limit if direction == "صاعد" else value >= limit

    within_ten = [price for price in prices if before_or_at(price, raw_extended)]
    quick = within_ten[0] if within_ten else raw_quick
    quick_basis = "مستوى سوق قبل الهدف" if within_ten else "5 نقاط"

    later_levels = [
        price for price in within_ten
        if (price > quick if direction == "صاعد" else price < quick)
    ]
    extended = later_levels[0] if later_levels else raw_extended
    extended_basis = "المستوى التالي قبل 10 نقاط" if later_levels else "10 نقاط"

    # Keep the extended target beyond the quick target after rounding.
    minimum_step = max(0.01, point_size)
    if direction == "صاعد" and extended <= quick:
        extended = round(max(raw_extended, quick + minimum_step), 2)
        extended_basis = "10 نقاط"
    elif direction == "هابط" and extended >= quick:
        extended = round(min(raw_extended, quick - minimum_step), 2)
        extended_basis = "10 نقاط"

    return {
        "point_size": round(point_size, 3),
        "quick_points": round(abs(quick - entry) / point_size, 1),
        "extended_points": round(abs(extended - entry) / point_size, 1),
        "quick_target": round(quick, 2),
        "extended_target": round(extended, 2),
        "quick_target_basis": quick_basis,
        "extended_target_basis": extended_basis,
        "raw_5_point_target": raw_quick,
        "raw_10_point_target": raw_extended,
    }


def _dual_scenario_reasons(
    analysis: dict[str, Any],
    *,
    direction: str,
    entry: float,
    entry_active: bool,
    closed_confirmed: bool,
) -> tuple[list[str], list[str]]:
    side_label = "الشراء" if direction == "صاعد" else "البيع"
    supporting: list[str] = []
    blocking: list[str] = []
    h4 = _analysis_frame_direction(analysis, "H4")
    h1 = _analysis_frame_direction(analysis, "H1")
    m15 = _analysis_frame_direction(analysis, "M15")
    m5 = _analysis_frame_direction(analysis, "M5")
    current_movement = str(analysis.get("current_movement") or "غير واضح")
    desired = direction
    opposite = "هابط" if desired == "صاعد" else "صاعد"

    higher_support = sum(frame == desired for frame in (h4, h1))
    higher_opposition = sum(frame == opposite for frame in (h4, h1))
    lower_support = sum(frame == desired for frame in (m15, m5))

    if higher_support == 2:
        supporting.append(f"H4 وH1 يدعمان {side_label}")
    elif higher_support == 1:
        supporting.append(f"أحد الفريمين الكبيرين يدعم {side_label}")
    if higher_opposition == 2:
        blocking.append(f"{side_label} عكس اتجاه H4 وH1")
    elif higher_opposition == 1:
        blocking.append("يوجد تعارض مع أحد الفريمات الكبيرة")

    if lower_support == 2:
        supporting.append(f"M15 وM5 متوافقان على اتجاه {desired}")
    elif lower_support == 1:
        supporting.append(f"أحد فريمي التفعيل يدعم {side_label}")
    else:
        blocking.append("M15 وM5 لا يؤكدان السيناريو معًا")

    if current_movement == desired:
        supporting.append(f"الحركة الحالية {desired}")
    elif current_movement == opposite:
        blocking.append(f"الحركة الحالية {opposite} وتعاكس السيناريو")

    pattern = _pattern_short_name(analysis.get("pattern_type"))
    confidence = int(analysis.get("pattern_confidence") or 0)
    pattern_bias = str(analysis.get("pattern_bias") or "محايد")
    if confidence >= 60 and (
        (direction == "صاعد" and pattern_bias in {"صاعد", "شراء"})
        or (direction == "هابط" and pattern_bias in {"هابط", "بيع"})
    ):
        supporting.append(f"نموذج {pattern} يدعم السيناريو")
    elif confidence >= 60 and pattern_bias not in {"محايد", "غير واضح"}:
        blocking.append(f"نموذج {pattern} يميل للجهة المقابلة")

    current = float(analysis.get("current_price") or 0.0)
    candles = _normalize_candles(analysis.get("candles"))
    atr = max(0.05, _atr(candles)) if candles else 1.0
    if direction == "صاعد":
        support = _nearest_level_price(analysis.get("support_levels"), current, side="support")
        resistance = _nearest_level_price(analysis.get("resistance_levels"), current, side="resistance")
        if support is not None and 0 <= current - support <= atr * 0.9:
            supporting.append("السعر قريب من دعم صالح للارتداد")
        if resistance is not None and 0 <= resistance - current <= atr * 0.65:
            blocking.append("توجد مقاومة قريبة أمام الشراء")
    else:
        resistance = _nearest_level_price(analysis.get("resistance_levels"), current, side="resistance")
        support = _nearest_level_price(analysis.get("support_levels"), current, side="support")
        if resistance is not None and 0 <= resistance - current <= atr * 0.9:
            supporting.append("السعر قريب من مقاومة صالحة للرفض")
        if support is not None and 0 <= current - support <= atr * 0.65:
            blocking.append("يوجد دعم قريب أمام البيع")

    if not closed_confirmed:
        blocking.append("لا توجد شمعة M5 مغلقة تؤكد الجهة بعد")
    if not entry_active:
        blocking.append("شرط التفعيل لم يكتمل بعد")

    # Preserve order and keep the API concise.
    supporting = list(dict.fromkeys(supporting))[:4]
    blocking = list(dict.fromkeys(blocking))[:4]
    if not supporting:
        supporting = ["السيناريو قائم للمراقبة لكنه يحتاج دليلًا إضافيًا"]
    return supporting, blocking


def _scenario_display_reason(supporting: list[str], blocking: list[str]) -> str:
    """Choose one useful, non-repetitive reason for the compact scenario card."""
    generic = "السيناريو قائم للمراقبة لكنه يحتاج دليلًا إضافيًا"
    concrete = [item for item in supporting if item and item != generic]
    if concrete:
        # Prefer the most concrete market-location reason, then timeframe agreement.
        priorities = ("دعم", "مقاومة", "نموذج", "H4", "H1", "M15", "M5", "الحركة")
        for keyword in priorities:
            match = next((item for item in concrete if keyword in item), None)
            if match:
                return match
        return concrete[0]
    if blocking:
        return blocking[0]
    return generic


def _build_side_scenario(analysis: dict[str, Any], *, side: str) -> dict[str, Any]:
    direction = "صاعد" if side == "buy" else "هابط"
    side_ar = "شراء" if side == "buy" else "بيع"
    current = float(analysis.get("current_price") or analysis.get("market_last_close") or 0.0)
    candles = _normalize_candles(analysis.get("candles"))
    supports = [item for item in analysis.get("support_levels") or [] if isinstance(item, dict)]
    resistances = [item for item in analysis.get("resistance_levels") or [] if isinstance(item, dict)]

    # Build each side independently; never reuse the primary scenario's entry.
    entry, entry_kind, confirmation = _nearest_entry({}, direction, current, supports, resistances)
    confirmation = _short_confirmation(direction, entry_kind, confirmation)
    cancel, cancel_reason = _validated_stop({}, direction, entry, candles, supports, resistances)
    activation = _entry_activation_state(candles, direction, entry, entry_kind)
    active = bool(activation.get("active"))
    closed_confirmed = _closed_m5_confirmation(candles, direction)
    m15 = _analysis_frame_direction(analysis, "M15")
    m5 = _analysis_frame_direction(analysis, "M5")
    lower_aligned = m15 == direction and m5 == direction
    score = int(analysis.get("buy_probability") if side == "buy" else analysis.get("sell_probability") or 0)

    market_active = str(analysis.get("market_status") or "active") == "active"
    if (
        market_active
        and score >= DUAL_SCENARIO_CONFIRMED_PROBABILITY
        and lower_aligned
        and closed_confirmed
        and active
        and entry_kind != "مراقبة"
    ):
        state_code, state = "confirmed", "مؤكد"
    else:
        # بطاقات السيناريو المستقلة لا تستخدم حالة «مشروط»؛ ما لم يكتمل
        # التفعيل فعليًا يبقى السيناريو ضمن المراقبة مع عرض شرطه بوضوح.
        state_code, state = "watch", "مراقبة"

    if not market_active:
        waiting_for = str(analysis.get("market_status_label") or "عودة بيانات M5 الحديثة")
    elif state_code == "confirmed":
        waiting_for = "السيناريو متفعل على شمعة M5 مغلقة"
    elif entry_kind == "اختراق" and direction == "صاعد":
        waiting_for = f"إغلاق M5 فوق {entry:.2f} ثم ثبات أو إعادة اختبار"
    elif entry_kind == "اختراق" and direction == "هابط":
        waiting_for = f"إغلاق M5 تحت {entry:.2f} ثم إعادة اختبار فاشلة"
    elif entry_kind == "إعادة اختبار" and direction == "صاعد":
        waiting_for = f"رفض الدعم عند {entry:.2f} ثم إغلاق M5 صاعد"
    elif entry_kind == "إعادة اختبار" and direction == "هابط":
        waiting_for = f"رفض المقاومة عند {entry:.2f} ثم إغلاق M5 هابط"
    else:
        waiting_for = f"تكوّن مستوى تفعيل واضح لسيناريو {side_ar}"

    targets = _scalp_targets(analysis, direction=direction, entry=entry)
    supporting, blocking = _dual_scenario_reasons(
        analysis,
        direction=direction,
        entry=entry,
        entry_active=active,
        closed_confirmed=closed_confirmed,
    )
    probable = _most_probable_extreme(analysis, kind="peak" if side == "buy" else "trough")
    why_not_now = (
        "اكتملت شروط السيناريو"
        if state_code == "confirmed"
        else "، ".join(blocking[:2]) if blocking else waiting_for
    )
    activation_close = _number(activation.get("last_close"))
    arrow_start_price = (
        float(activation_close)
        if active and activation_close is not None
        else float(entry)
    )
    display_activation = (
        str(activation.get("reason") or waiting_for)
        if state_code == "confirmed"
        else waiting_for
    )
    display_reason = _scenario_display_reason(supporting, blocking)
    display_target = (
        _number(probable.get("price"))
        if isinstance(probable, dict)
        else None
    )
    if display_target is None:
        display_target = _number(targets.get("extended_target"))

    return {
        "side": side,
        "label": side_ar,
        "state": state,
        "state_code": state_code,
        "score": max(5, min(95, score)),
        "trigger_price": round(entry, 2),
        "trigger_type": entry_kind,
        "trigger_condition": confirmation,
        "is_active": active,
        "activation_status": str(activation.get("status") or "waiting"),
        "activation_reason": str(activation.get("reason") or waiting_for),
        "activation_candle_close": round(float(activation_close), 3) if activation_close is not None else None,
        "arrow_start_price": round(float(arrow_start_price), 3),
        "arrow_start_source": "activation_close" if active and activation_close is not None else "trigger_level",
        "display_activation": display_activation,
        "display_reason": display_reason,
        "display_target": round(float(display_target), 2) if display_target is not None else None,
        "cancel_price": round(cancel, 2),
        "cancel_reason": cancel_reason,
        **targets,
        "most_probable_peak" if side == "buy" else "most_probable_trough": probable,
        "supporting_reasons": supporting,
        "blocking_reasons": blocking,
        "why_not_now": why_not_now,
        "waiting_for": waiting_for,
        "distance_to_trigger": round(abs(entry - current), 2),
        "uses_closed_m5_confirmation": bool(closed_confirmed),
        "lower_frames_aligned": bool(lower_aligned),
    }


def _compare_dual_scenarios(
    buy_scenario: dict[str, Any],
    sell_scenario: dict[str, Any],
) -> dict[str, Any]:
    state_rank = {"confirmed": 2, "watch": 1}
    buy_rank = state_rank.get(str(buy_scenario.get("state_code")), 1)
    sell_rank = state_rank.get(str(sell_scenario.get("state_code")), 1)
    buy_score = int(buy_scenario.get("score") or 0)
    sell_score = int(sell_scenario.get("score") or 0)
    buy_distance = float(buy_scenario.get("distance_to_trigger") or 999.0)
    sell_distance = float(sell_scenario.get("distance_to_trigger") or 999.0)

    closest = "شراء" if buy_distance < sell_distance else "بيع" if sell_distance < buy_distance else "متساوي"
    preferred = "wait"
    preferred_ar = "انتظار"
    chosen: dict[str, Any] | None = None

    # لا نرفع أي سيناريو إلى قرار مباشر إلا إذا كان مؤكدًا فعليًا.
    if buy_rank > sell_rank and str(buy_scenario.get("state_code")) == "confirmed":
        chosen, preferred, preferred_ar = buy_scenario, "buy", "شراء"
    elif sell_rank > buy_rank and str(sell_scenario.get("state_code")) == "confirmed":
        chosen, preferred, preferred_ar = sell_scenario, "sell", "بيع"
    elif buy_rank == sell_rank == 2:
        if abs(buy_score - sell_score) >= 6:
            if buy_score > sell_score:
                chosen, preferred, preferred_ar = buy_scenario, "buy", "شراء"
            else:
                chosen, preferred, preferred_ar = sell_scenario, "sell", "بيع"
        else:
            # Two opposite confirmed scenarios are contradictory; never invent a side.
            chosen = None

    if chosen is None:
        reason = (
            "وضع المراقبة مفعل: يعرض SaleeM سيناريو الشراء وسيناريو البيع معًا "
            "حتى يكتمل التفعيل على شمعة M5 مغلقة."
        )
        waiting_for = (
            buy_scenario.get("waiting_for")
            if closest == "شراء"
            else sell_scenario.get("waiting_for")
            if closest == "بيع"
            else "انتظار أول شرط واضح على شمعة M5 مغلقة"
        )
        label = "القرار الآن: مراقبة"
    else:
        reason = (
            f"سيناريو {preferred_ar} أقوى ({int(chosen.get('score') or 0)}٪) "
            f"وحالته {chosen.get('state')}"
        )
        waiting_for = chosen.get("waiting_for")
        label = f"الأقرب الآن: {preferred_ar}"

    return {
        "preferred": preferred,
        "preferred_label": preferred_ar,
        "label": label,
        "reason": reason,
        "waiting_for": waiting_for,
        "closest_to_activation": closest,
        "score_gap": abs(buy_score - sell_score),
    }


def _scenario_priority(analysis: dict[str, Any], scenario: dict[str, Any], *, side: str) -> float:
    """Rank a watch scenario without turning it into a confirmed trade.

    The rank rewards real multi-timeframe agreement and proximity to the
    trigger, then leaves the UI in monitoring until a closed M5 candle
    actually activates the setup.
    """
    direction = "صاعد" if side == "buy" else "هابط"
    score = float(scenario.get("score") or 0)
    try:
        candles = _normalize_candles(analysis.get("candles"))
    except RuntimeError:
        candles = [
            item for item in (analysis.get("candles") or [])
            if isinstance(item, dict) and all(_number(item.get(key)) is not None for key in ("open", "high", "low", "close"))
        ]
    atr = max(0.05, _atr(candles)) if candles else 1.0
    distance = float(scenario.get("distance_to_trigger") or 0.0)
    proximity_penalty = min(16.0, distance / atr * 4.0)

    h4 = _analysis_frame_direction(analysis, "H4")
    h1 = _analysis_frame_direction(analysis, "H1")
    m15 = _analysis_frame_direction(analysis, "M15")
    m5 = _analysis_frame_direction(analysis, "M5")

    higher_bonus = 8.0 if h4 == h1 == direction else 4.0 if direction in {h4, h1} else 0.0
    lower_bonus = 8.0 if m15 == m5 == direction else 3.0 if direction in {m15, m5} else 0.0
    activation_bonus = 10.0 if bool(scenario.get("is_active")) else 0.0
    return round(score + higher_bonus + lower_bonus + activation_bonus - proximity_penalty, 2)


def _build_action_summary(analysis: dict[str, Any]) -> dict[str, Any]:
    """Build one concise, deterministic answer for the result page.

    The user sees one action first. Detailed frames, liquidity, patterns and
    news remain available in collapsed panels, so the page is useful without
    becoming noisy.
    """
    buy = analysis.get("buy_scenario_details") if isinstance(analysis.get("buy_scenario_details"), dict) else {}
    sell = analysis.get("sell_scenario_details") if isinstance(analysis.get("sell_scenario_details"), dict) else {}
    market_active = str(analysis.get("market_status") or "active") == "active"

    if not market_active or str(analysis.get("draw_mode") or "") == "inactive":
        return {
            "code": "inactive",
            "title": "لا دخول الآن",
            "badge": "السوق غير جاهز",
            "instruction": str(analysis.get("market_status_label") or "انتظر عودة بيانات M5 الحديثة"),
            "reason": "لا يصدر SaleeM قرارًا من بيانات قديمة أو سوق غير نشط.",
            "trigger": None,
            "target": None,
            "cancel": None,
            "strength": 0,
            "primary_side": "wait",
            "is_confirmed": False,
        }

    buy_confirmed = str(buy.get("state_code")) == "confirmed"
    sell_confirmed = str(sell.get("state_code")) == "confirmed"
    buy_score = int(buy.get("score") or 0)
    sell_score = int(sell.get("score") or 0)

    chosen: dict[str, Any] | None = None
    side = "wait"
    confirmed = False
    if buy_confirmed and not sell_confirmed:
        chosen, side, confirmed = buy, "buy", True
    elif sell_confirmed and not buy_confirmed:
        chosen, side, confirmed = sell, "sell", True
    elif buy_confirmed and sell_confirmed and abs(buy_score - sell_score) >= 8:
        chosen, side, confirmed = (buy, "buy", True) if buy_score > sell_score else (sell, "sell", True)

    if chosen is None:
        buy_rank = _scenario_priority(analysis, buy, side="buy")
        sell_rank = _scenario_priority(analysis, sell, side="sell")
        rank_gap = abs(buy_rank - sell_rank)
        strongest_score = max(buy_score, sell_score)

        # Very weak or contradictory readings produce a direct no-trade answer.
        if strongest_score < 50 or (rank_gap < 7 and not bool(buy.get("lower_frames_aligned")) and not bool(sell.get("lower_frames_aligned"))):
            buy_trigger = _number(buy.get("trigger_price"))
            sell_trigger = _number(sell.get("trigger_price"))
            if buy_trigger is not None and sell_trigger is not None:
                instruction = f"لا تدخل؛ انتظر إغلاق M5 فوق {buy_trigger:.2f} للشراء أو تحت {sell_trigger:.2f} للبيع"
            else:
                instruction = "لا تدخل حتى يظهر تفعيل واضح على شمعة M5 مغلقة"
            return {
                "code": "no_trade",
                "title": "عدم دخول الآن",
                "badge": "الشروط غير مكتملة",
                "instruction": instruction,
                "reason": "قوة الاتجاه أو توافق الفريمات غير كافيين لقرار آمن وواضح.",
                "trigger": None,
                "target": None,
                "cancel": None,
                "strength": strongest_score,
                "primary_side": "wait",
                "is_confirmed": False,
                "buy_rank": buy_rank,
                "sell_rank": sell_rank,
            }

        if rank_gap >= 7:
            chosen, side = (buy, "buy") if buy_rank > sell_rank else (sell, "sell")
        else:
            buy_trigger = _number(buy.get("trigger_price"))
            sell_trigger = _number(sell.get("trigger_price"))
            instruction = "انتظر أول إغلاق M5 واضح عند أحد مستويي التفعيل"
            if buy_trigger is not None and sell_trigger is not None:
                instruction = f"شراء فوق {buy_trigger:.2f} أو بيع تحت {sell_trigger:.2f} بعد إغلاق M5"
            return {
                "code": "watch",
                "title": "مراقبة",
                "badge": "لا أفضلية واضحة",
                "instruction": instruction,
                "reason": "سيناريو الشراء والبيع متقاربان؛ لا يتم تحويل التعادل إلى صفقة.",
                "trigger": None,
                "target": None,
                "cancel": None,
                "strength": strongest_score,
                "primary_side": "wait",
                "is_confirmed": False,
                "buy_rank": buy_rank,
                "sell_rank": sell_rank,
            }

    side_ar = "شراء" if side == "buy" else "بيع"
    code = side if confirmed else "watch_" + side
    trigger = _number(chosen.get("trigger_price"))
    target = _number(chosen.get("display_target"))
    cancel = _number(chosen.get("cancel_price"))
    activation_close = _number(chosen.get("activation_candle_close"))

    if confirmed:
        title = f"{side_ar} مؤكد"
        badge = "مفعّل بإغلاق M5"
        if activation_close is not None:
            instruction = f"السيناريو متفعل من إغلاق M5 عند {activation_close:.2f}; راقب الثبات ولا تطارد السعر بعيدًا عن التفعيل"
        else:
            instruction = str(chosen.get("activation_reason") or f"تم تفعيل سيناريو {side_ar}")
    else:
        title = f"مراقبة {side_ar}"
        badge = "الأقرب للتفعيل"
        instruction = str(chosen.get("display_activation") or chosen.get("waiting_for") or f"انتظار تفعيل {side_ar}")

    return {
        "code": code,
        "title": title,
        "badge": badge,
        "instruction": instruction,
        "reason": str(chosen.get("display_reason") or "بانتظار دليل فني أوضح"),
        "trigger": round(float(trigger), 2) if trigger is not None else None,
        "target": round(float(target), 2) if target is not None else None,
        "cancel": round(float(cancel), 2) if cancel is not None else None,
        "strength": int(chosen.get("score") or 0),
        "primary_side": side,
        "is_confirmed": confirmed,
    }


def _enrich_dual_scenarios(analysis: dict[str, Any]) -> dict[str, Any]:
    """Attach independent buy/sell plans without changing the current renderer."""
    result = copy.deepcopy(analysis)
    # Normalize old cached labels defensively, although cache v7 invalidates them.
    result["pattern_type"] = _pattern_short_name(result.get("pattern_type"))
    buy_scenario = _build_side_scenario(result, side="buy")
    sell_scenario = _build_side_scenario(result, side="sell")
    result["buy_scenario_details"] = buy_scenario
    result["sell_scenario_details"] = sell_scenario
    result["dual_scenario_decision"] = _compare_dual_scenarios(buy_scenario, sell_scenario)
    result["most_probable_peak"] = buy_scenario.get("most_probable_peak")
    result["most_probable_trough"] = sell_scenario.get("most_probable_trough")
    result["scalp_target_policy"] = {
        "quick_points": 5,
        "extended_points": 10,
        "point_size": _scalp_point_size(),
        "rule": "يُستخدم مستوى السوق الأقرب إذا اعترض طريق هدف 5 أو 10 نقاط",
    }
    result["dual_scenario_renderer_status"] = "cards-below-image-active"
    return result



def _current_m5_movement(candles: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe the latest CLOSED M5 movement independently from H4/H1.

    The broader trend may remain bullish while the most recent closed candles
    are falling. Keeping this field separate prevents the UI from presenting a
    bullish forecast as if it were the current price movement.
    """
    valid: list[dict[str, float]] = []
    for candle in candles[-8:]:
        if not isinstance(candle, dict):
            continue
        values = [_number(candle.get(key)) for key in ("open", "high", "low", "close")]
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

    if len(valid) < 3:
        return {"direction": "غير واضح", "strength": "ضعيف", "score": 0.0}

    atr = max(
        0.01,
        sum(max(0.01, item["high"] - item["low"]) for item in valid) / len(valid),
    )
    lookback = min(4, len(valid) - 1)
    close_move = (valid[-1]["close"] - valid[-1 - lookback]["close"]) / atr
    last_impulse = (valid[-1]["close"] - valid[-2]["close"]) / atr
    recent = valid[-3:]
    body_pressure = sum(item["close"] - item["open"] for item in recent) / (atr * len(recent))
    score = _clip(close_move * 0.55 + last_impulse * 0.25 + body_pressure * 0.20, -3.0, 3.0)

    if score >= 0.12:
        direction = "صاعد"
    elif score <= -0.12:
        direction = "هابط"
    else:
        direction = "عرضي"

    magnitude = abs(score)
    if magnitude >= 0.95:
        strength = "قوي"
    elif magnitude >= 0.38:
        strength = "متوسط"
    else:
        strength = "ضعيف"
    return {
        "direction": direction,
        "strength": strength,
        "score": round(score, 3),
        "last_close": round(valid[-1]["close"], 3),
    }


def _entry_activation_state(
    candles: list[dict[str, Any]],
    direction: str,
    entry: float,
    entry_kind: str,
) -> dict[str, Any]:
    """Return whether a directional scenario has actually activated.

    A conditional setup may be valid as a plan while price is still below a
    bullish trigger (or above a bearish trigger). In that state targets remain
    reference levels, but no directional path or risk/reward zone is drawn.
    """
    movement = _current_m5_movement(candles)
    if not candles or direction not in {"صاعد", "هابط"}:
        return {
            "active": False,
            "status": "waiting",
            "reason": "بانتظار اتجاه واضح على شموع M5 المغلقة",
            "buffer": 0.0,
            "movement": movement,
        }

    last_close = float(_number(candles[-1].get("close")) or entry)
    atr = max(0.01, _atr(candles))
    buffer = max(0.05, min(0.45, atr * 0.08))
    movement_direction = str(movement.get("direction") or "غير واضح")
    candle_confirmation = _closed_m5_confirmation(candles, direction)

    if direction == "صاعد":
        if entry_kind == "إعادة اختبار":
            correct_side = last_close >= entry - buffer
        else:
            correct_side = last_close > entry + buffer
        active = bool(correct_side and movement_direction == "صاعد" and candle_confirmation)
        reason = (
            "تم تفعيل الصعود بإغلاق وثبات فوق مستوى الدخول"
            if active
            else f"بانتظار إغلاق وثبات فوق {entry:.1f}"
        )
    else:
        if entry_kind == "إعادة اختبار":
            correct_side = last_close <= entry + buffer
        else:
            correct_side = last_close < entry - buffer
        active = bool(correct_side and movement_direction == "هابط" and candle_confirmation)
        reason = (
            "تم تفعيل الهبوط بإغلاق وثبات تحت مستوى الدخول"
            if active
            else f"بانتظار إغلاق وثبات تحت {entry:.1f}"
        )

    return {
        "active": active,
        "status": "active" if active else "waiting",
        "reason": reason,
        "buffer": round(buffer, 3),
        "last_close": round(last_close, 3),
        "movement": movement,
        "closed_m5_confirmed": bool(candle_confirmation),
    }

def _closed_m5_confirmation(candles: list[dict[str, Any]], direction: str) -> bool:
    """Require actual closed-M5 continuation, sweep or rejection evidence."""
    if len(candles) < 4 or direction not in {"صاعد", "هابط"}:
        return False
    last = candles[-1]
    previous = candles[-2]
    before = candles[-3]
    body = max(0.01, abs(float(last["close"]) - float(last["open"])))
    upper_wick = max(0.0, float(last["high"]) - max(float(last["open"]), float(last["close"])))
    lower_wick = max(0.0, min(float(last["open"]), float(last["close"])) - float(last["low"]))
    previous_mid = (float(previous["high"]) + float(previous["low"])) / 2.0
    if direction == "صاعد":
        breakout = float(last["close"]) > float(previous["high"])
        continuation = (
            float(last["close"]) > float(last["open"])
            and float(last["close"]) > float(previous["close"]) > float(before["close"])
        )
        rejection = (
            float(last["close"]) > float(last["open"])
            and lower_wick >= body * 1.15
            and float(last["close"]) >= previous_mid
        )
        liquidity_sweep = (
            float(last["low"]) < min(float(previous["low"]), float(before["low"]))
            and float(last["close"]) > float(previous["close"])
        )
        return breakout or continuation or rejection or liquidity_sweep
    breakdown = float(last["close"]) < float(previous["low"])
    continuation = (
        float(last["close"]) < float(last["open"])
        and float(last["close"]) < float(previous["close"]) < float(before["close"])
    )
    rejection = (
        float(last["close"]) < float(last["open"])
        and upper_wick >= body * 1.15
        and float(last["close"]) <= previous_mid
    )
    liquidity_sweep = (
        float(last["high"]) > max(float(previous["high"]), float(before["high"]))
        and float(last["close"]) < float(previous["close"])
    )
    return breakdown or continuation or rejection or liquidity_sweep


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

    # A nearby support/resistance may weaken or neutralize an existing signal,
    # but it may not create a new direction from a neutral result. This removes
    # the repeated bullish bias caused by always being near some support.
    if direction not in {"صاعد", "هابط"}:
        if margin > 10:
            if buy_final > sell_final:
                buy_final, sell_final = 55, 45
            else:
                buy_final, sell_final = 45, 55
        return "غير واضح", buy_final, sell_final, context

    preferred_is_buy = direction == "صاعد"
    still_preferred = buy_final > sell_final if preferred_is_buy else sell_final > buy_final
    if margin < 12 or not still_preferred:
        adjusted_direction = "غير واضح"
    else:
        adjusted_direction = direction

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
    impulse_move = (closes[-1] - closes[-4]) / atr
    recent_move = (closes[-1] - closes[-9]) / atr
    broad_index = max(0, len(closes) - 32)
    broad_move = (closes[-1] - closes[broad_index]) / atr

    # Read the most recent closed-candle structure symmetrically.  This term is
    # deliberately sensitive to lower highs/lows so a sharp bearish turn is not
    # hidden by an older bullish moving average (and vice versa).
    recent = valid[-6:]
    older = valid[-12:-6]
    recent_high = sum(item["high"] for item in recent) / len(recent)
    recent_low = sum(item["low"] for item in recent) / len(recent)
    older_high = sum(item["high"] for item in older) / len(older)
    older_low = sum(item["low"] for item in older) / len(older)
    structure_move = ((recent_high - older_high) + (recent_low - older_low)) / (2.0 * atr)

    signed_pressure = sum(
        (item["close"] - item["open"]) / max(0.01, item["high"] - item["low"])
        for item in valid[-5:]
    ) / 5.0

    score = _clip(
        ((fast - slow) / atr) * 0.22
        + impulse_move * 0.28
        + recent_move * 0.24
        + structure_move * 0.16
        + signed_pressure * 0.08
        + broad_move * 0.02,
        -3.0,
        3.0,
    )

    if score > 0.18:
        direction = "صاعد"
    elif score < -0.18:
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



def _apply_pattern_review(data: dict[str, Any]) -> dict[str, Any]:
    """Use the deterministic closed-candle model review as source of truth."""
    review = data.get("_pattern_review")
    if not isinstance(review, dict):
        review = {}
    checked = list(review.get("checked_patterns") or [])
    available = bool(review.get("available"))
    model_pattern = str(data.get("pattern_type") or "لا يوجد")
    model_confidence = max(0, min(100, int(data.get("pattern_confidence") or 0)))

    if available:
        pattern_type = str(review.get("pattern_type") or "لا يوجد")
        confidence = max(0, min(100, int(review.get("pattern_confidence") or 0)))
        if model_pattern == pattern_type and model_confidence >= 55:
            confidence = min(94, confidence + 4)
        timeframe = str(review.get("pattern_timeframe") or "M5")
        evidence = str(review.get("pattern_evidence") or "اكتمل النموذج على الشموع المغلقة")
        summary = f"رُوجعت {len(checked)} نماذج؛ الأقرب {pattern_type} على {timeframe} بثقة {confidence}٪: {evidence}."
        data["pattern_type"] = pattern_type
        data["pattern_confidence"] = confidence
        data["pattern_lines"] = []
        data["pattern_path"] = []
        data["pattern_bias"] = str(review.get("pattern_bias") or "محايد")
        data["pattern_timeframe"] = timeframe
    else:
        data["pattern_type"] = "لا يوجد"
        data["pattern_confidence"] = 0
        data["pattern_lines"] = []
        data["pattern_path"] = []
        data["pattern_bias"] = "محايد"
        data["pattern_timeframe"] = ""
        summary = f"رُوجعت {len(checked)} نماذج على M5 وM15 وH1، ولم يكتمل نموذج هندسي بشروط كافية."

    data["pattern_review_summary"] = summary[:260]
    data["pattern_candidates_checked"] = checked
    data["pattern_review_candidates"] = list(review.get("candidates") or [])[:4]
    return data

def _choose_direction(
    data: dict[str, Any],
    candles: list[dict[str, Any]],
    buy: int,
    sell: int,
    market_summary: dict[str, Any] | None = None,
) -> tuple[str, int, int]:
    """Choose the current actionable direction with M15/M5 as activation.

    H4 and H1 describe context and may raise/lower confidence, but they cannot
    keep the displayed direction bullish while both activation frames and
    recent closed M5 price action are bearish. The language-model vote is only
    a small advisory input; permanent rules are enforced here deterministically.
    """
    atr = max(0.01, _atr(candles))
    full_move = _clip(
        (float(candles[-1]["close"]) - float(candles[0]["close"])) / atr,
        -4.0,
        4.0,
    )
    recent_index = max(0, len(candles) - 7)
    recent_move = _clip(
        (float(candles[-1]["close"]) - float(candles[recent_index]["close"])) / atr,
        -4.0,
        4.0,
    )
    impulse_index = max(0, len(candles) - 4)
    impulse_move = _clip(
        (float(candles[-1]["close"]) - float(candles[impulse_index]["close"])) / atr,
        -4.0,
        4.0,
    )
    m5_price_score = full_move * 0.18 + recent_move * 0.50 + impulse_move * 0.32
    model_score = _clip((buy - sell) / 45.0, -2.0, 2.0)

    frames = (market_summary or {}).get("frames") if isinstance(market_summary, dict) else {}

    def frame_info(name: str) -> tuple[str, float, float]:
        item = frames.get(name) if isinstance(frames, dict) else None
        if not isinstance(item, dict):
            return "غير واضح", 0.0, 0.0
        direction = str(item.get("direction") or "غير واضح")
        try:
            score = _clip(float(item.get("score") or 0.0), -3.0, 3.0)
            confidence = _clip(float(item.get("confidence") or 0.0) / 100.0, 0.0, 1.0)
        except (TypeError, ValueError):
            return direction, 0.0, 0.0
        return direction, score, confidence

    h4, h4_score, h4_conf = frame_info("H4")
    h1, h1_score, h1_conf = frame_info("H1")
    m15, m15_score, m15_conf = frame_info("M15")
    m5, m5_score, m5_conf = frame_info("M5")

    lower_score = (
        m15_score * 0.58 * max(0.45, m15_conf)
        + m5_score * 0.42 * max(0.45, m5_conf)
    )
    higher_score = (
        h4_score * 0.44 * max(0.35, h4_conf)
        + h1_score * 0.56 * max(0.35, h1_conf)
    )

    lower_aligned = m15 in {"صاعد", "هابط"} and m15 == m5
    lower_conflict = m15 in {"صاعد", "هابط"} and m5 in {"صاعد", "هابط"} and m15 != m5
    higher_aligned = h4 in {"صاعد", "هابط"} and h4 == h1

    direction = "غير واضح"
    evidence_score = 0.0
    short_term_against_context = False

    if lower_aligned:
        sign = 1.0 if m15 == "صاعد" else -1.0
        price_supports = m5_price_score * sign >= 0.12
        if abs(lower_score) >= 0.14 or price_supports:
            direction = m15
            evidence_score = abs(lower_score) * 0.62 + max(0.0, m5_price_score * sign) * 0.38
            short_term_against_context = (
                (h4 in {"صاعد", "هابط"} and h4 != direction)
                or (h1 in {"صاعد", "هابط"} and h1 != direction)
            )
    elif lower_conflict:
        # A conflict between activation and timing is always monitoring; do not
        # let H4/H1 or the model manufacture a directional result.
        direction = "غير واضح"
    else:
        # One lower frame can lead only when closed M5 movement confirms it.
        if m15 in {"صاعد", "هابط"}:
            sign = 1.0 if m15 == "صاعد" else -1.0
            if m5_price_score * sign >= 0.42 and abs(m15_score) >= 0.18:
                direction = m15
                evidence_score = abs(m15_score) * 0.55 + abs(m5_price_score) * 0.45
        if direction == "غير واضح" and m5 in {"صاعد", "هابط"}:
            sign = 1.0 if m5 == "صاعد" else -1.0
            if m5_price_score * sign >= 0.70 and abs(m5_score) >= 0.35:
                direction = m5
                evidence_score = abs(m5_score) * 0.45 + abs(m5_price_score) * 0.55

    if direction == "غير واضح" and not lower_conflict:
        # Broad trend is used only if lower-price action agrees. It cannot act
        # alone, which removes the persistent upward bias.
        combined = (
            lower_score * 0.40
            + m5_price_score * 0.37
            + higher_score * 0.18
            + model_score * 0.05
        )
        lower_or_price_present = abs(lower_score) >= 0.16 or abs(m5_price_score) >= 0.42
        if lower_or_price_present and abs(combined) >= 0.38:
            direction = "صاعد" if combined > 0 else "هابط"
            evidence_score = abs(combined)

    if direction == "غير واضح":
        directional_hint = lower_score * 0.55 + m5_price_score * 0.40 + model_score * 0.05
        edge = int(round(min(5.0, abs(directional_hint) * 7.0)))
        if directional_hint > 0:
            return "غير واضح", 50 + edge, 50 - edge
        if directional_hint < 0:
            return "غير واضح", 50 - edge, 50 + edge
        return "غير واضح", 50, 50

    sign = 1.0 if direction == "صاعد" else -1.0
    agreement = 0
    for frame_direction in (h4, h1, m15, m5):
        if frame_direction == direction:
            agreement += 1
        elif frame_direction in {"صاعد", "هابط"}:
            agreement -= 1

    raw_probability = int(round(_clip(54 + evidence_score * 14 + max(0, agreement) * 2, 54, 88)))

    if lower_aligned and m15 == direction:
        raw_probability = max(raw_probability, 60)
    if lower_conflict:
        raw_probability = min(raw_probability, 54)
    if short_term_against_context:
        raw_probability = min(raw_probability, 68)
    elif higher_aligned and h4 == direction:
        raw_probability = min(90, raw_probability + 4)
    elif higher_aligned and h4 != direction:
        raw_probability = min(raw_probability, 64)

    # Strong opposite recent movement always caps confidence, even if the
    # broader averages still point the other way.
    if m5_price_score * sign < -0.35:
        raw_probability = min(raw_probability, 56)
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

    # الحسابات الهندسية قد تحتاج جهة مؤقتة، لكن الجهة المعروضة تبقى
    # "غير واضح" عند التعادل ولا تتحول افتراضيًا إلى شراء.
    calculation_direction = direction
    if calculation_direction not in {"صاعد", "هابط"}:
        recent_delta = float(candles[-1]["close"]) - float(candles[max(0, len(candles) - 4)]["close"])
        if recent_delta > 0:
            calculation_direction = "صاعد"
        elif recent_delta < 0:
            calculation_direction = "هابط"
        elif buy > sell:
            calculation_direction = "صاعد"
        else:
            calculation_direction = "هابط"

    entry, entry_kind, confirmation = _nearest_entry(data, calculation_direction, current, supports, resistances)
    confirmation = _short_confirmation(calculation_direction, entry_kind, confirmation)
    if direction not in {"صاعد", "هابط"}:
        confirmation = "انتظار توافق M15 وM5 مع بنية H1/H4"
    stop, stop_reason = _validated_stop(data, calculation_direction, entry, candles, supports, resistances)
    targets = _validated_targets(data, calculation_direction, entry, stop, supports, resistances)

    # Pattern evidence is applied before selecting the final state so completed
    # patterns can support a real confirmation instead of being display-only.
    data = _apply_pattern_review(data)
    pattern_confidence = max(0, min(100, int(data.get("pattern_confidence") or 0)))
    if pattern_confidence < 60:
        data["pattern_lines"] = []
        data["pattern_path"] = []
        data["pattern_type"] = "لا يوجد"

    frames = (market_summary or {}).get("frames") if isinstance(market_summary, dict) else {}
    h4_direction = str((frames.get("H4") or {}).get("direction") or "غير واضح") if isinstance(frames, dict) else "غير واضح"
    h1_direction = str((frames.get("H1") or {}).get("direction") or "غير واضح") if isinstance(frames, dict) else "غير واضح"
    m15_direction = str((frames.get("M15") or {}).get("direction") or "غير واضح") if isinstance(frames, dict) else "غير واضح"
    m5_direction = str((frames.get("M5") or {}).get("direction") or "غير واضح") if isinstance(frames, dict) else "غير واضح"
    alignment = int((market_summary or {}).get("alignment") or 0) if isinstance(market_summary, dict) else 0
    higher_aligned = direction in {"صاعد", "هابط"} and h4_direction == direction and h1_direction == direction
    lower_aligned = direction in {"صاعد", "هابط"} and m15_direction == direction and m5_direction == direction
    lower_support = direction in {"صاعد", "هابط"} and (m15_direction == direction or m5_direction == direction)
    lower_conflict = (
        direction in {"صاعد", "هابط"}
        and m15_direction in {"صاعد", "هابط"}
        and m5_direction in {"صاعد", "هابط"}
        and m15_direction == m5_direction
        and m15_direction != direction
    )
    warnings = bool((market_summary or {}).get("warnings")) if isinstance(market_summary, dict) else False
    geometry_valid = (
        (calculation_direction == "صاعد" and stop < entry and all(target > entry for target in targets))
        or (calculation_direction == "هابط" and stop > entry and all(target < entry for target in targets))
    )

    model_state = str(data.get("setup_state") or "مراقبة")
    opposing_pressure = (
        int(level_pressure.get("resistance_pressure") or 0)
        if calculation_direction == "صاعد"
        else int(level_pressure.get("support_pressure") or 0)
    )
    market_activity = _market_activity_status(market_summary)
    clear_scenario = (
        direction in {"صاعد", "هابط"}
        and entry_kind != "مراقبة"
        and geometry_valid
    )
    price_action_confirmed = _closed_m5_confirmation(candles, direction)
    activation = _entry_activation_state(candles, direction, entry, entry_kind)
    current_movement = dict(activation.get("movement") or _current_m5_movement(candles))
    entry_activated = bool(activation.get("active"))
    movement_direction = str(current_movement.get("direction") or "غير واضح")
    movement_opposes_direction = (
        direction in {"صاعد", "هابط"}
        and movement_direction in {"صاعد", "هابط"}
        and movement_direction != direction
    )

    if h4_direction in {"صاعد", "هابط"} and h1_direction in {"صاعد", "هابط"}:
        higher_timeframe_direction = h4_direction if h4_direction == h1_direction else "مختلط"
    elif h1_direction in {"صاعد", "هابط"}:
        higher_timeframe_direction = h1_direction
    elif h4_direction in {"صاعد", "هابط"}:
        higher_timeframe_direction = h4_direction
    else:
        higher_timeframe_direction = "غير واضح"

    higher_supportive = higher_aligned or (direction in {"صاعد", "هابط"} and (h4_direction == direction or h1_direction == direction))
    higher_both_opposed = (
        direction in {"صاعد", "هابط"}
        and h4_direction in {"صاعد", "هابط"}
        and h1_direction in {"صاعد", "هابط"}
        and h4_direction != direction
        and h1_direction != direction
    )
    pattern_bias = str(data.get("pattern_bias") or "محايد")
    aligned_pattern = (
        pattern_confidence >= 60
        and (
            (direction == "صاعد" and pattern_bias in {"صاعد", "شراء"})
            or (direction == "هابط" and pattern_bias in {"هابط", "بيع"})
        )
    )
    zones = detect_market_zone_presence(data)
    zone_confluence = bool(zones.get("order_block") or zones.get("fvg"))
    pressure_limit = 13 if aligned_pattern or zone_confluence else 11
    context_acceptable = not higher_both_opposed or probability >= 76 or aligned_pattern
    confirmation_complete = (
        probability >= CONFIRMED_PROBABILITY
        and lower_aligned
        and price_action_confirmed
        and entry_activated
        and context_acceptable
        and geometry_valid
        and not warnings
        and opposing_pressure <= pressure_limit
        and model_state != "غير صالح"
    )

    if not market_activity["active"]:
        draw_mode = "inactive"
    elif probability < CONDITIONAL_PROBABILITY or not clear_scenario or model_state == "غير صالح":
        draw_mode = "watch"
    elif lower_conflict:
        # تعارض M15 وM5 مع الجهة المختارة يلغي حالة مشروط بدل تكرارها.
        draw_mode = "watch"
    elif movement_opposes_direction and not entry_activated:
        # إذا كانت الحركة الحالية تعاكس الجهة ولم يتفعّل الدخول بعد فلا نرفع
        # النتيجة إلى شراء/بيع مشروط حفاظًا على مصداقية التحليل.
        draw_mode = "watch"
    elif confirmation_complete:
        draw_mode = "confirmed"
    elif lower_aligned and clear_scenario:
        # Conditional requires an actual M15+M5 activation agreement. One lower
        # frame alone is not enough, which prevents nearly every result from
        # being labelled conditional.
        draw_mode = "conditional"
    else:
        draw_mode = "watch"

    missing_confirmation: list[str] = []
    if not lower_aligned:
        missing_confirmation.append("توافق M15 وM5")
    if not price_action_confirmed:
        missing_confirmation.append("شمعة M5 مؤكدة")
    if movement_opposes_direction and not entry_activated:
        missing_confirmation.append("الحركة الحالية تعاكس الاتجاه")
    if direction in {"صاعد", "هابط"} and not entry_activated:
        missing_confirmation.append(
            "إغلاق وثبات فوق الدخول" if direction == "صاعد" else "إغلاق وثبات تحت الدخول"
        )
    if probability < CONFIRMED_PROBABILITY:
        missing_confirmation.append(f"قوة {CONFIRMED_PROBABILITY}٪ فأعلى")
    if not context_acceptable:
        missing_confirmation.append("عدم تعارض H4 وH1 مع الحركة")
    if opposing_pressure > pressure_limit:
        missing_confirmation.append("ابتعاد الضغط المعاكس")
    if warnings:
        missing_confirmation.append("بيانات سوق سليمة")
    if not geometry_valid:
        missing_confirmation.append("دخول ووقف وأهداف صحيحة")
    confirmation_explanation = (
        "اكتملت شروط التأكيد على الشموع المغلقة."
        if confirmation_complete
        else "ينقص التأكيد: " + "، ".join(missing_confirmation[:3]) + "."
        if missing_confirmation
        else "السيناريو غير واضح بما يكفي للتأكيد."
    )

    if draw_mode == "watch":
        # المراقبة نقطة قرار محايدة: Entry يساوي السعر الحالي، ولا يوجد
        # Cancel أو Stop ظاهر. لا نرسم مسارًا اتجاهيًا قبل وضوح الحركة.
        entry = round(current, 2)
        entry_kind = "مراقبة"
        confirmation = "انتظار توافق الفريمات وظهور شمعة تأكيد"
    elif draw_mode == "inactive":
        entry = round(current, 2)
        entry_kind = "مراقبة"
        confirmation = market_activity["label"]
    elif draw_mode == "conditional" and not entry_activated:
        confirmation = str(activation.get("reason") or confirmation)

    directional_path_enabled = bool(
        draw_mode == "confirmed"
        or (draw_mode == "conditional" and entry_activated)
    )
    show_targets_as_active = directional_path_enabled

    scenario = " ".join(str(data.get("scenario") or "").split())[:92]
    bullish_scenario = " ".join(str(data.get("bullish_scenario") or "").split())[:150]
    bearish_scenario = " ".join(str(data.get("bearish_scenario") or "").split())[:150]
    invalidation_condition = " ".join(
        str(data.get("invalidation_condition") or "").split()
    )[:110]
    macro_note = " ".join(str(data.get("macro_note") or "").split())[:150]

    if not bullish_scenario:
        bullish_scenario = "إذا ثبت السعر فوق المقاومة الأقرب فإن الحركة تتجه نحو الهدف الصاعد التالي"
    if not bearish_scenario:
        bearish_scenario = "إذا أغلق السعر تحت الدعم الأقرب فإن الحركة تتجه نحو الهدف الهابط التالي"
    if not invalidation_condition:
        invalidation_condition = (
            f"إلغاء السيناريو عند تجاوز وقف الخسارة {stop:.2f}"
            if draw_mode in {"conditional", "confirmed"}
            else "إلغاء الفكرة عند كسر البنية المقابلة قبل ظهور شرط التفعيل"
        )
    if not macro_note:
        macro_note = "لا تتوفر بيانات أخبار أو DXY ضمن المدخلات الحالية"

    if draw_mode == "inactive":
        scenario = market_activity["label"]
        bullish_scenario = "بانتظار عودة شموع M5 الحديثة قبل تقييم سيناريو الصعود"
        bearish_scenario = "بانتظار عودة شموع M5 الحديثة قبل تقييم سيناريو الهبوط"
        invalidation_condition = "لا يوجد سيناريو تنفيذي أثناء توقف السوق أو قدم البيانات"
    elif draw_mode == "watch":
        if movement_opposes_direction and direction in {"صاعد", "هابط"}:
            scenario = (
                f"الاتجاه العام {higher_timeframe_direction} لكن الحركة الحالية {movement_direction}؛ "
                f"{activation.get('reason') or 'بانتظار التفعيل'}"
            )[:92]
        else:
            scenario = "إذا توافقت الفريمات وظهرت شمعة تأكيد فإن أقرب سيناريو يتفعّل"
    elif draw_mode == "conditional" and not entry_activated:
        movement_label = str(current_movement.get("direction") or "غير واضح")
        scenario = (
            f"الاتجاه العام {higher_timeframe_direction} والحركة الحالية {movement_label}؛ "
            f"{activation.get('reason') or 'بانتظار تفعيل الدخول'}"
        )[:92]
    elif not scenario:
        scenario = "إذا تحقق شرط الدخول فإن السيناريو يستمر نحو الأهداف المحددة"

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
            "analysis_direction": direction,
            "higher_timeframe_direction": higher_timeframe_direction,
            "current_movement": str(current_movement.get("direction") or "غير واضح"),
            "current_movement_strength": str(current_movement.get("strength") or "ضعيف"),
            "current_movement_score": float(current_movement.get("score") or 0.0),
            "entry_activation_status": str(activation.get("status") or "waiting"),
            "entry_activation_reason": str(activation.get("reason") or "بانتظار تفعيل الدخول"),
            "entry_confirmation_buffer": float(activation.get("buffer") or 0.0),
            "directional_path_enabled": directional_path_enabled,
            "show_targets_as_active": show_targets_as_active,
            "trade_side": (
                market_activity["label"]
                if draw_mode == "inactive"
                else (
                    "مراقبة"
                    if draw_mode == "watch"
                    else (
                        ("شراء مؤكد" if direction == "صاعد" else "بيع مؤكد")
                        if draw_mode == "confirmed"
                        else ("شراء مشروط" if direction == "صاعد" else "بيع مشروط")
                    )
                )
            ),
            "trade_probability": probability,
            "draw_mode": draw_mode,
            "confirmation_status": (
                "شراء مؤكد" if draw_mode == "confirmed" and direction == "صاعد"
                else "بيع مؤكد" if draw_mode == "confirmed" and direction == "هابط"
                else "شراء مشروط" if draw_mode == "conditional" and direction == "صاعد"
                else "بيع مشروط" if draw_mode == "conditional" and direction == "هابط"
                else "مراقبة"
            ),
            "confirmation_evidence": {
                "m15_m5_aligned": bool(lower_aligned),
                "closed_m5_confirmed": bool(price_action_confirmed),
                "higher_frame_supportive": bool(higher_supportive),
                "geometry_valid": bool(geometry_valid),
                "warnings_clear": not warnings,
                "pattern_aligned": bool(aligned_pattern),
                "zone_confluence": bool(zone_confluence),
            },
            "confirmation_explanation": confirmation_explanation,
            "market_activity": market_activity,
            "market_status": market_activity["code"],
            "market_status_label": market_activity["label"],
            "support_levels": supports,
            "resistance_levels": resistances,
            "entry": entry,
            "entry_outside_loss_zone": bool(geometry_valid),
            "entry_kind": entry_kind,
            "confirmation": confirmation,
            "stop_loss": stop,
            "stop_reason": " ".join(stop_reason.split())[:52],
            "target_1": targets[0],
            "target_2": targets[1],
            "target_3": targets[2],
            "scenario": scenario,
            "bullish_scenario": bullish_scenario,
            "bearish_scenario": bearish_scenario,
            "invalidation_condition": invalidation_condition,
            "macro_note": macro_note,
            "analysis_style": "سكالب تعليمي — XAUUSD — تنفيذ M5 مع مراجعة M15/H1/H4",
            "note": " ".join(str(data.get("note") or "").split())[:100],
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
    """Analyze closed market candles once, then project the result onto this image.

    The latest CLOSED M5 candle is the immutable version key.  The currently
    forming candle may supply a live fallback price, but it cannot change the
    direction, state, support/resistance, entry, stop, or targets.
    """
    try:
        market_data = fetch_market_data()
        context_candles = max(24, min(64, int(os.getenv("MARKET_CONTEXT_CANDLES", "32"))))
        raw_market_context = compact_market_context(
            market_data,
            candles_per_frame=context_candles,
        )
        market_context = _closed_market_context(raw_market_context)
        market_frames = market_context.get("frames", {})
        if isinstance(market_frames, dict) and isinstance(market_frames.get("M5"), list):
            prompt_m5_count = max(20, min(60, int(os.getenv("PROMPT_M5_CANDLES", "40"))))
            market_frames["M5"] = market_frames["M5"][-prompt_m5_count:]

        closed_market_data = copy.deepcopy(market_data)
        closed_market_data["frames"] = copy.deepcopy(market_context.get("frames") or {})
        closed_market_data["latest_candle_time"] = market_context.get("m5_last_closed_candle_time")
        market_summary = _build_market_summary(closed_market_data)
        market_summary["m5_last_closed_candle_time"] = market_context.get("m5_last_closed_candle_time")
        market_summary["analysis_candle_mode"] = "closed_only"
    except MarketDataError as exc:
        raise RuntimeError(f"تعذر جلب بيانات الفريمات: {exc}") from exc

    raw_frames = market_data.get("frames") if isinstance(market_data, dict) else None
    raw_m5 = raw_frames.get("M5") if isinstance(raw_frames, dict) else None
    live_m5 = [c for c in raw_m5 if isinstance(c, dict)] if isinstance(raw_m5, list) else []
    closed_m5 = (market_context.get("frames") or {}).get("M5") or []
    display_count = max(12, min(48, int(os.getenv("CHART_CANDLE_COUNT", "30"))))
    normalized_market = _normalize_candles(closed_m5[-display_count:])
    if not normalized_market:
        raise RuntimeError("لا توجد شموع M5 مغلقة كافية للتحليل.")

    provider_closed_price = float(normalized_market[-1]["close"])
    provider_live_price = provider_closed_price
    if live_m5:
        provider_live_price = float(_number(live_m5[-1].get("close")) or provider_closed_price)

    # Two isolated inputs: geometry from the screenshot, decision from CLOSED market data.
    geometry = _extract_chart_geometry(path)
    market_decision, snapshot_key, snapshot_reused = _get_market_decision(
        market_context,
        market_summary,
    )

    pattern_review = review_market_patterns(market_context.get("frames") or {})

    canonical_input = {
        **market_decision,
        "_pattern_review": pattern_review,
        "chart_readable": False,
        "_image_chart_readable": False,
        "_image_current_price": None,
        "candles": normalized_market,
        "current_price": provider_closed_price,
        "current_price_y_ratio": None,
        "image_price_high": None,
        "image_price_low": None,
        "image_axis_labels": [],
    }
    canonical = _validate_analysis(canonical_input, market_summary=market_summary)
    canonical["confirmed_limit_swings"] = _build_confirmed_limit_swings(
        market_context.get("frames") or {},
        provider_closed_price,
    )
    canonical.update(
        {
            "analysis_snapshot_key": snapshot_key,
            "analysis_snapshot_reused": bool(snapshot_reused),
            "analysis_consistency_lock": "last_closed_m5",
            "analysis_last_closed_m5_time": market_context.get("m5_last_closed_candle_time"),
            "analysis_candle_mode": "closed_only",
            "analysis_rules_hash": _analysis_rules_fingerprint(),
            "rules_audit_summary": (
                f"طُبقت قواعد H4/H1/M15/M5، ورُوجعت {len(pattern_review.get('checked_patterns') or [])} "
                "نماذج على الشموع المغلقة، ثم فُرضت قواعد منع الانحياز والتأكيد برمجيًا."
            ),
            "provider_closed_m5_price": round(provider_closed_price, 3),
            "provider_live_price": round(provider_live_price, 3),
        }
    )
    projected = _bind_market_analysis_to_image(
        canonical,
        geometry,
        snapshot_key=snapshot_key,
        snapshot_reused=snapshot_reused,
    )
    return _enrich_dual_scenarios(projected)


def analyze_chart_image(image_path: Path, symbol: str, timeframe: str) -> dict[str, Any]:
    prepared_image_path, crop_meta = _prepare_analysis_image(image_path)
    analysis = _analyze(prepared_image_path)
    axis_ok, axis_reason = validate_uploaded_axis(analysis, prepared_image_path)
    if not axis_ok:
        analysis["axis_warning"] = (
            "تم استخدام وضع احتياطي لأن قراءة محور الأسعار من الصورة لم تكن كاملة: " + axis_reason
        )
        analysis["axis_validation_passed"] = False
    else:
        analysis["axis_warning"] = ""
        analysis["axis_validation_passed"] = True

    if crop_meta.get("used_smart_crop"):
        analysis["axis_warning"] = (
            (analysis.get("axis_warning") + " ") if analysis.get("axis_warning") else ""
        ) + "استخدم التطبيق نافذة موحدة للشارت ومحور الأسعار، وأزال شريط أمر التداول العلوي بالقص عند ظهوره قبل معايرة الأسعار."

    analysis["market_reading_comment"] = _build_market_reading_comment(analysis)
    analysis["breakout_summary"] = _build_breakout_summary(analysis)
    analysis["limit_recommendations"] = _build_limit_recommendations(analysis)
    analysis["action_summary"] = _build_action_summary(analysis)
    analysis["result_explanation"] = _build_result_explanation(analysis)

    # The smart crop is used only to help read prices. The final image always uses
    # the original upload so the fixed production layout remains identical.
    png = render_result(analysis, chart_background_path=image_path)
    return {
        **analysis,
        **crop_meta,
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "window": f"{len(analysis.get('candles') or [])} شمعة من بيانات السوق",
        "result_url": "data:image/png;base64," + base64.b64encode(png).decode(),
    }
