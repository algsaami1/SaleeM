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


CONFIRMED_PROBABILITY = 70
CONDITIONAL_PROBABILITY = 55
MAX_ENTRY_DISTANCE = 8.0
MIN_STOP_DISTANCE = 0.6
MAX_STOP_DISTANCE = 4.0
STOP_ATR_MULTIPLIER = 1.10


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


def _build_market_reading_comment(analysis: dict[str, Any]) -> str:
    """Build a fresh neutral reading from the latest closed-candle evidence.

    Unlike the old direction-only template, this sentence includes timeframe
    agreement, recent M5 momentum, the deterministic pattern review and nearby
    levels. It remains educational, contains no execution recommendation and is
    capped at 220 characters.
    """
    direction = str(analysis.get("direction") or "غير واضح")
    frames = analysis.get("frame_directions")

    def frame_direction(name: str) -> str:
        item = frames.get(name) if isinstance(frames, dict) else None
        if isinstance(item, dict):
            return str(item.get("direction") or "غير واضح")
        return str(item or "غير واضح")

    h4, h1, m15, m5 = [frame_direction(name) for name in ("H4", "H1", "M15", "M5")]
    if m15 == m5 and m15 in {"صاعد", "هابط"}:
        frame_text = f"M15 وM5 متفقان على اتجاه {m15}"
    elif m15 in {"صاعد", "هابط"} and m5 in {"صاعد", "هابط"} and m15 != m5:
        frame_text = "M15 وM5 متعارضان"
    elif h4 == h1 and h4 in {"صاعد", "هابط"}:
        frame_text = f"H4 وH1 {h4}ان مع تفعيل قصير غير مكتمل"
    else:
        frame_text = "الفريمات متداخلة بلا توافق كامل"

    candles = analysis.get("candles") if isinstance(analysis.get("candles"), list) else []
    momentum_text = "زخم M5 غير محسوم"
    candle_text = ""
    if len(candles) >= 5:
        try:
            atr = max(0.01, _atr(candles))
            move = (float(candles[-1]["close"]) - float(candles[-5]["close"])) / atr
            if move >= 0.65:
                momentum_text = "زخم M5 صاعد"
            elif move <= -0.65:
                momentum_text = "زخم M5 هابط"
            else:
                momentum_text = "زخم M5 متوازن"
            last = candles[-1]
            body = abs(float(last["close"]) - float(last["open"]))
            upper = max(0.0, float(last["high"]) - max(float(last["open"]), float(last["close"])))
            lower = max(0.0, min(float(last["open"]), float(last["close"])) - float(last["low"]))
            if upper > max(body * 1.4, atr * 0.18):
                candle_text = "ورفض علوي ظاهر"
            elif lower > max(body * 1.4, atr * 0.18):
                candle_text = "ورفض سفلي ظاهر"
        except (TypeError, ValueError, KeyError):
            pass

    current = float(_number(analysis.get("current_price")) or 0.0)
    support = _nearest_level_price(analysis.get("support_levels"), current, side="support")
    resistance = _nearest_level_price(analysis.get("resistance_levels"), current, side="resistance")
    if support is not None and resistance is not None:
        levels_text = f"الدعم {support:.2f} والمقاومة {resistance:.2f}"
    elif support is not None:
        levels_text = f"الدعم الأقرب {support:.2f}"
    elif resistance is not None:
        levels_text = f"المقاومة الأقرب {resistance:.2f}"
    else:
        levels_text = "المستويات القريبة لم تتأكد"

    pattern = str(analysis.get("pattern_type") or "لا يوجد")
    pattern_confidence = int(analysis.get("pattern_confidence") or 0)
    if pattern != "لا يوجد" and pattern_confidence >= 60:
        pattern_text = f"ورُصد {pattern} بثقة {pattern_confidence}٪"
    else:
        pattern_text = "ولا يوجد نموذج هندسي مكتمل"

    direction_text = {
        "صاعد": "البنية الحالية صاعدة",
        "هابط": "البنية الحالية هابطة",
        "عرضي": "البنية الحالية عرضية",
        "غير واضح": "البنية الحالية غير محسومة",
    }.get(direction, "البنية الحالية غير محسومة")
    liquidity_text = {
        "صاعد": "السيولة الأقرب فوق القمة الأخيرة",
        "هابط": "السيولة الأقرب أسفل القاع الأخير",
        "عرضي": "السيولة موزعة عند طرفي النطاق",
        "غير واضح": "السيولة موزعة حول القمم والقيعان القريبة",
    }.get(direction, "السيولة موزعة حول القمم والقيعان القريبة")
    zones = detect_market_zone_presence(analysis)
    zone_names: list[str] = []
    if zones.get("order_block"):
        zone_names.append("Order Block")
    if zones.get("fvg"):
        zone_names.append("FVG")
    zones_text = f"ورُصد {' و'.join(zone_names)}" if zone_names else ""

    clauses = [
        f"{direction_text}؛ {frame_text}",
        f"{momentum_text} {candle_text}".strip(),
        pattern_text,
        f"{liquidity_text}؛ {levels_text}",
        zones_text,
    ]
    comment = "، ".join(clause for clause in clauses if clause).replace("، ،", "،") + "."
    if len(comment) <= 220:
        return comment

    # Remove lower-priority clauses before truncating a numeric level.
    for index in (2, 1):
        reduced = [clause for pos, clause in enumerate(clauses) if pos != index]
        candidate = "، ".join(clause for clause in reduced if clause) + "."
        if len(candidate) <= 220:
            return candidate
    return comment[:217].rstrip(" ،.") + "..."


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
    reason = (
        f"مبنية على {pivot_label} مؤكد من {source_frame}"
        + (
            f" ومتوافق مع {', '.join(level.get('confirmation_frames') or [])}."
            if level.get("confirmation_frames")
            else "."
        )
    )
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
        "plan_id": plan_id,
        "locked": True,
        "confirmation_label": "مؤكدة الشروط" if confirmed_conditions else "المستوى مؤكد",
        "invalidation_condition": invalidation,
        "validity": "ثابتة حتى كسر القمة/القاع أو ظهور إلغاء بنيوي",
        "guaranteed": False,
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
                "قناة هابطة", "قناة صاعدة", "قمتان", "قاعان", "كسر وإعادة اختبار", "لا يوجد",
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
                "قناة هابطة", "قناة صاعدة", "قمتان", "قاعان", "كسر وإعادة اختبار", "لا يوجد",
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

ANALYSIS_SNAPSHOT_CACHE_VERSION = 5
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
        return json.loads(_text(response.json()))
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
        max_output_tokens=2200,
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
12) راجع صراحةً نماذج القمتين والقاعين والمثلثات والأوتاد والقنوات والكسر وإعادة الاختبار. لا تُرجع نموذجًا إلا إذا اكتملت بنيته على الشموع المغلقة، واكتب في memory_matches القواعد أو النماذج التي طابقتها فعلًا.
13) pattern_lines وpattern_path نسبية لنافذة M5 المرفقة، ولا ترسم نموذجًا غير واضح.

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
            max_output_tokens=max(2500, min(7000, int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "5000")))),
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


def _closed_m5_confirmation(candles: list[dict[str, Any]], direction: str) -> bool:
    """Require actual closed-M5 continuation/break evidence for confirmation."""
    if len(candles) < 4 or direction not in {"صاعد", "هابط"}:
        return False
    last = candles[-1]
    previous = candles[-2]
    before = candles[-3]
    if direction == "صاعد":
        breakout = float(last["close"]) > float(previous["high"])
        continuation = (
            float(last["close"]) > float(last["open"])
            and float(last["close"]) > float(previous["close"]) > float(before["close"])
        )
        return breakout or continuation
    breakdown = float(last["close"]) < float(previous["low"])
    continuation = (
        float(last["close"]) < float(last["open"])
        and float(last["close"]) < float(previous["close"]) < float(before["close"])
    )
    return breakdown or continuation


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
    higher_supportive = higher_aligned or (direction in {"صاعد", "هابط"} and (h4_direction == direction or h1_direction == direction))
    confirmation_complete = (
        probability >= CONFIRMED_PROBABILITY
        and lower_aligned
        and price_action_confirmed
        and higher_supportive
        and geometry_valid
        and not warnings
        and opposing_pressure < 8
        and model_state != "غير صالح"
    )

    if not market_activity["active"]:
        draw_mode = "inactive"
    elif probability < CONDITIONAL_PROBABILITY or not clear_scenario or model_state == "غير صالح":
        draw_mode = "watch"
    elif lower_conflict:
        # تعارض M15 وM5 مع الجهة المختارة يلغي حالة مشروط بدل تكرارها.
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

    if draw_mode == "watch":
        # المراقبة نقطة قرار محايدة: Entry يساوي السعر الحالي، ولا يوجد
        # Cancel أو Stop ظاهر. يبدأ السهمان من هذا السعر نفسه.
        entry = round(current, 2)
        entry_kind = "مراقبة"
        confirmation = "انتظار توافق الفريمات وظهور شمعة تأكيد"
    elif draw_mode == "inactive":
        entry = round(current, 2)
        entry_kind = "مراقبة"
        confirmation = market_activity["label"]

    data = _apply_pattern_review(data)
    pattern_confidence = max(0, min(100, int(data.get("pattern_confidence") or 0)))
    if pattern_confidence < 60:
        data["pattern_lines"] = []
        data["pattern_path"] = []
        data["pattern_type"] = "لا يوجد"

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
        scenario = "إذا توافقت الفريمات وظهرت شمعة تأكيد فإن أقرب سيناريو يتفعّل"
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
            },
            "market_activity": market_activity,
            "market_status": market_activity["code"],
            "market_status_label": market_activity["label"],
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
        context_candles = max(24, min(80, int(os.getenv("MARKET_CONTEXT_CANDLES", "40"))))
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
    return _bind_market_analysis_to_image(
        canonical,
        geometry,
        snapshot_key=snapshot_key,
        snapshot_reused=snapshot_reused,
    )


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
    analysis["limit_recommendations"] = _build_limit_recommendations(analysis)

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
