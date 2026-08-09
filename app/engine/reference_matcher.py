from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any


_LIBRARY_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "saleem_reference_patterns_v1.json"


@lru_cache(maxsize=1)
def load_reference_library() -> dict[str, Any]:
    try:
        data = json.loads(_LIBRARY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"references": [], "matching": {}}
    if not isinstance(data, dict):
        return {"references": [], "matching": {}}
    return data


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize(candles: Any) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for item in candles if isinstance(candles, list) else []:
        if not isinstance(item, dict):
            continue
        values = [_number(item.get(key)) for key in ("open", "high", "low", "close")]
        if any(value is None for value in values):
            continue
        open_, high, low, close = [float(value) for value in values]
        rows.append(
            {
                "open": open_,
                "high": max(high, open_, close),
                "low": min(low, open_, close),
                "close": close,
            }
        )
    return rows


def _atr(candles: list[dict[str, float]], lookback: int = 24) -> float:
    rows = candles[-lookback:]
    if not rows:
        return 0.01
    return max(0.01, median(max(0.01, row["high"] - row["low"]) for row in rows))


def _pivots(candles: list[dict[str, float]], window: int = 2) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    peaks: list[tuple[int, float]] = []
    troughs: list[tuple[int, float]] = []
    if len(candles) < window * 2 + 3:
        return peaks, troughs
    for index in range(window, len(candles) - window):
        left = candles[index - window:index]
        right = candles[index + 1:index + 1 + window]
        high = candles[index]["high"]
        low = candles[index]["low"]
        if all(high >= row["high"] for row in left + right) and (
            high > max(row["high"] for row in left) or high > max(row["high"] for row in right)
        ):
            peaks.append((index, high))
        if all(low <= row["low"] for row in left + right) and (
            low < min(row["low"] for row in left) or low < min(row["low"] for row in right)
        ):
            troughs.append((index, low))
    return peaks, troughs


def _frame_trend(candles: list[dict[str, float]]) -> str:
    if len(candles) < 8:
        return "neutral"
    atr = _atr(candles)
    span = min(18, len(candles) - 1)
    delta = (candles[-1]["close"] - candles[-1 - span]["close"]) / max(0.01, atr)
    if delta >= 1.0:
        return "bullish"
    if delta <= -1.0:
        return "bearish"
    peaks, troughs = _pivots(candles[-30:])
    if len(peaks) >= 2 and len(troughs) >= 2:
        if peaks[-1][1] > peaks[-2][1] and troughs[-1][1] > troughs[-2][1]:
            return "bullish"
        if peaks[-1][1] < peaks[-2][1] and troughs[-1][1] < troughs[-2][1]:
            return "bearish"
    return "neutral"


def _latest_liquidity_sweep(candles: list[dict[str, float]]) -> str | None:
    if len(candles) < 8:
        return None
    # Review the last three closed candles so one-candle noise does not make the
    # feature disappear immediately after a valid reclaim/rejection.
    for offset in range(1, min(4, len(candles) - 5)):
        idx = len(candles) - offset
        candle = candles[idx]
        prior = candles[max(0, idx - 7):idx]
        if len(prior) < 4:
            continue
        prior_low = min(row["low"] for row in prior)
        prior_high = max(row["high"] for row in prior)
        prior_close = prior[-1]["close"]
        body = max(0.01, abs(candle["close"] - candle["open"]))
        lower_wick = max(0.0, min(candle["open"], candle["close"]) - candle["low"])
        upper_wick = max(0.0, candle["high"] - max(candle["open"], candle["close"]))
        if candle["low"] < prior_low and candle["close"] > prior_low and candle["close"] >= prior_close and lower_wick >= body * 0.75:
            return "bullish"
        if candle["high"] > prior_high and candle["close"] < prior_high and candle["close"] <= prior_close and upper_wick >= body * 0.75:
            return "bearish"
    return None


def _latest_fvg_bias(candles: list[dict[str, float]]) -> str | None:
    if len(candles) < 3:
        return None
    atr = _atr(candles)
    for i in range(len(candles) - 1, max(1, len(candles) - 18), -1):
        a = candles[i - 2]
        c = candles[i]
        if c["low"] > a["high"] + atr * 0.02:
            return "bullish"
        if c["high"] < a["low"] - atr * 0.02:
            return "bearish"
    return None


def _latest_order_block_bias(candles: list[dict[str, float]]) -> str | None:
    if len(candles) < 6:
        return None
    bodies = [abs(row["close"] - row["open"]) for row in candles[-24:]]
    baseline = max(0.01, median(bodies))
    start = max(1, len(candles) - 16)
    for i in range(len(candles) - 1, start - 1, -1):
        prev, impulse = candles[i - 1], candles[i]
        body = abs(impulse["close"] - impulse["open"])
        if body < baseline * 1.45:
            continue
        prev_bull = prev["close"] >= prev["open"]
        impulse_bull = impulse["close"] >= impulse["open"]
        if prev_bull == impulse_bull:
            continue
        return "bullish" if impulse_bull else "bearish"
    return None


def _latest_structure_event(candles: list[dict[str, float]]) -> dict[str, Any] | None:
    if len(candles) < 14:
        return None
    peaks, troughs = _pivots(candles)
    events: list[dict[str, Any]] = []
    atr = _atr(candles)
    for index in range(max(5, len(candles) - 16), len(candles)):
        close = candles[index]["close"]
        prior_peaks = [item for item in peaks if item[0] < index]
        prior_troughs = [item for item in troughs if item[0] < index]
        if prior_peaks:
            swing = prior_peaks[-1]
            if close > swing[1] + atr * 0.04:
                trend_before = "neutral"
                if len(prior_peaks) >= 2 and len(prior_troughs) >= 2:
                    if prior_peaks[-1][1] < prior_peaks[-2][1] and prior_troughs[-1][1] < prior_troughs[-2][1]:
                        trend_before = "bearish"
                    elif prior_peaks[-1][1] > prior_peaks[-2][1] and prior_troughs[-1][1] > prior_troughs[-2][1]:
                        trend_before = "bullish"
                events.append({"side": "bullish", "type": "CHOCH" if trend_before == "bearish" else "BOS", "index": index, "level": swing[1]})
        if prior_troughs:
            swing = prior_troughs[-1]
            if close < swing[1] - atr * 0.04:
                trend_before = "neutral"
                if len(prior_peaks) >= 2 and len(prior_troughs) >= 2:
                    if prior_peaks[-1][1] > prior_peaks[-2][1] and prior_troughs[-1][1] > prior_troughs[-2][1]:
                        trend_before = "bullish"
                    elif prior_peaks[-1][1] < prior_peaks[-2][1] and prior_troughs[-1][1] < prior_troughs[-2][1]:
                        trend_before = "bearish"
                events.append({"side": "bearish", "type": "CHOCH" if trend_before == "bullish" else "BOS", "index": index, "level": swing[1]})
    if not events:
        return None
    events.sort(key=lambda item: int(item["index"]))
    return events[-1]


def _reference_index() -> dict[str, dict[str, Any]]:
    refs = load_reference_library().get("references") or []
    return {str(item.get("id")): item for item in refs if isinstance(item, dict) and item.get("id")}


def _map_pattern_to_reference(name: str, bias: str) -> str | None:
    normalized = " ".join(str(name or "").split())
    bias_norm = str(bias or "")
    direct = {
        "W": "REV_W_BULL",
        "M": "REV_M_BEAR",
        "قاع ثلاثي": "REV_TRIPLE_BOTTOM_BULL",
        "قمة ثلاثية": "REV_TRIPLE_TOP_BEAR",
        "رأس وكتفين مقلوب": "REV_IHS_BULL",
        "رأس وكتفين": "REV_HS_BEAR",
        "مثلث صاعد": "CONT_ASC_TRI_BULL",
        "مثلث هابط": "CONT_DESC_TRI_BEAR",
        "وتد هابط": "REV_FALLING_WEDGE_BULL",
        "وتد صاعد": "REV_RISING_WEDGE_BEAR",
        "قناة صاعدة": "CHANNEL_ASC",
        "قناة هابطة": "CHANNEL_DESC",
        "علم صاعد": "CONT_FLAG_BULL",
        "علم هابط": "CONT_FLAG_BEAR",
        "راية صاعدة": "CONT_PENNANT_BULL",
        "راية هابطة": "CONT_PENNANT_BEAR",
    }
    if normalized == "مثلث متماثل":
        return "CONT_SYM_TRI_BULL" if bias_norm in {"صاعد", "bullish", "شراء"} else "CONT_SYM_TRI_BEAR" if bias_norm in {"هابط", "bearish", "بيع"} else None
    if normalized == "مستطيل":
        return "RANGE_RECT_BULL" if bias_norm in {"صاعد", "bullish", "شراء"} else "RANGE_RECT_BEAR" if bias_norm in {"هابط", "bearish", "بيع"} else None
    if normalized == "كسر وإعادة اختبار":
        return "PA_BREAK_RETEST_BULL" if bias_norm in {"صاعد", "bullish", "شراء"} else "PA_BREAK_RETEST_BEAR" if bias_norm in {"هابط", "bearish", "بيع"} else None
    return direct.get(normalized)


def _candidate_match_score(candidate: dict[str, Any], context: dict[str, Any]) -> int:
    confidence = max(0, min(100, int(candidate.get("confidence") or 0)))
    status = str(candidate.get("status") or "candidate")
    geometry = candidate.get("geometry") if isinstance(candidate.get("geometry"), dict) else {}
    anchors = [item for item in geometry.get("anchors") or [] if isinstance(item, dict)]
    lines = [item for item in geometry.get("lines") or [] if isinstance(item, dict)]
    path = [item for item in geometry.get("path") or [] if isinstance(item, list)]

    # Structure/anchor quality rewards real anchored geometry, not pretty shapes.
    structure_score = min(100.0, 32.0 + len(anchors) * 13.0 + len(lines) * 12.0 + min(3, len(path)) * 5.0)
    pattern_score = float(confidence)
    breakout_score = 100.0 if status == "confirmed" and geometry.get("breakout_index") is not None else 62.0 if status == "candidate" else 78.0
    position_score = 100.0 if status == "confirmed" else 64.0

    bias = str(candidate.get("bias") or "محايد")
    bias_en = "bullish" if bias in {"صاعد", "شراء", "bullish"} else "bearish" if bias in {"هابط", "بيع", "bearish"} else "neutral"
    trends = [context.get("h4_trend"), context.get("h1_trend"), context.get("m15_trend")]
    aligned = sum(1 for item in trends if item == bias_en)
    opposed = sum(1 for item in trends if item in {"bullish", "bearish"} and item != bias_en)
    if bias_en == "neutral":
        trend_score = 58.0
    elif aligned >= 2:
        trend_score = 92.0
    elif aligned == 1 and opposed <= 1:
        trend_score = 68.0
    elif opposed >= 2:
        trend_score = 34.0
    else:
        trend_score = 55.0

    confluence_score = 55.0
    confluences = [context.get("sweep"), context.get("fvg"), context.get("order_block")]
    if bias_en in {"bullish", "bearish"}:
        same = sum(1 for item in confluences if item == bias_en)
        opp = sum(1 for item in confluences if item in {"bullish", "bearish"} and item != bias_en)
        confluence_score = min(100.0, 55.0 + same * 16.0 - opp * 13.0)
        structure_event = context.get("structure") if isinstance(context.get("structure"), dict) else None
        if structure_event and structure_event.get("side") == bias_en:
            confluence_score = min(100.0, confluence_score + 14.0)

    timeframe = str(candidate.get("timeframe") or "M5")
    timeframe_recency_bonus = {"M5": 1.0, "M15": 0.93, "H1": 0.88}.get(timeframe, 0.84)
    window_size = max(1, int(geometry.get("window_size") or 1))
    relevant_indices: list[int] = []
    for anchor in anchors:
        try:
            relevant_indices.append(int(anchor.get("index")))
        except (TypeError, ValueError):
            pass
    try:
        if geometry.get("breakout_index") is not None:
            relevant_indices.append(int(geometry.get("breakout_index")))
    except (TypeError, ValueError):
        pass
    if relevant_indices:
        latest = max(relevant_indices)
        ratio = max(0.0, min(1.0, latest / max(1, window_size - 1)))
        recency_score = 55.0 + ratio * 45.0
    else:
        recency_score = 55.0
    recency_score *= timeframe_recency_bonus

    score = (
        structure_score * 0.35
        + pattern_score * 0.20
        + breakout_score * 0.15
        + position_score * 0.10
        + trend_score * 0.08
        + confluence_score * 0.07
        + recency_score * 0.05
    )
    return max(0, min(100, int(round(score))))


def _strength(score: int) -> str:
    if score >= 88:
        return "very_strong"
    if score >= 78:
        return "strong"
    if score >= 68:
        return "medium"
    return "weak"


def _make_match(ref_id: str, score: int, *, source: str, candidate: dict[str, Any] | None = None, rationale: str = "") -> dict[str, Any]:
    ref = _reference_index().get(ref_id, {})
    match = {
        "reference_id": ref_id,
        "reference_name": str(ref.get("name_ar") or ref_id),
        "family": str(ref.get("family") or ""),
        "bias": str(ref.get("bias") or "neutral"),
        "score": int(score),
        "strength": _strength(int(score)),
        "source": source,
        "rationale": rationale,
        "execution_eligible": bool(score >= 78),
    }
    if isinstance(candidate, dict):
        match["candidate_name"] = str(candidate.get("name") or "")
        match["candidate_status"] = str(candidate.get("status") or "candidate")
        match["candidate_timeframe"] = str(candidate.get("timeframe") or "")
        match["candidate_confidence"] = int(candidate.get("confidence") or 0)
        match["execution_eligible"] = bool(score >= 78 and str(candidate.get("status") or "") == "confirmed")
    return match


def match_reference_scenarios(frames: Any, pattern_review: Any) -> dict[str, Any]:
    """Match deterministic market geometry to the extracted SaleeM library.

    This engine never compares a screenshot by superficial appearance.  It only
    scores patterns/zones/events already tied to real closed-candle OHLC.  The
    returned reference id tells the renderer which *rule* is closest; actual
    overlay coordinates remain those of the current chart.
    """
    frame_map = frames if isinstance(frames, dict) else {}
    m5 = _normalize(frame_map.get("M5"))
    h4 = _normalize(frame_map.get("H4"))
    h1 = _normalize(frame_map.get("H1"))
    m15 = _normalize(frame_map.get("M15"))
    context = {
        "h4_trend": _frame_trend(h4),
        "h1_trend": _frame_trend(h1),
        "m15_trend": _frame_trend(m15),
        "m5_trend": _frame_trend(m5),
        "sweep": _latest_liquidity_sweep(m5),
        "fvg": _latest_fvg_bias(m5),
        "order_block": _latest_order_block_bias(m5),
        "structure": _latest_structure_event(m5),
    }

    matches: list[dict[str, Any]] = []
    review = pattern_review if isinstance(pattern_review, dict) else {}
    for candidate in review.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        ref_id = _map_pattern_to_reference(str(candidate.get("name") or ""), str(candidate.get("bias") or ""))
        if not ref_id:
            continue
        score = _candidate_match_score(candidate, context)
        rationale = (
            f"هندسة {candidate.get('name')} مثبتة على OHLC؛ الحالة {candidate.get('status')}، "
            f"الثقة الحتمية {int(candidate.get('confidence') or 0)}٪."
        )
        matches.append(_make_match(ref_id, score, source="deterministic_pattern", candidate=candidate, rationale=rationale))

    # Add reference scenarios that are not always represented as a classical
    # pattern skeleton but are frequent in the source videos/images.
    sweep = context.get("sweep")
    if sweep == "bullish":
        bonus = 4 if context.get("structure", {}).get("side") == "bullish" else 0
        matches.append(_make_match("SMC_SWEEP_RECLAIM_BULL", 80 + bonus, source="smc_event", rationale="سحب سيولة أسفل قاع حديث ثم استعادة على شموع M5 المغلقة."))
    elif sweep == "bearish":
        bonus = 4 if context.get("structure", {}).get("side") == "bearish" else 0
        matches.append(_make_match("SMC_SWEEP_REJECT_BEAR", 80 + bonus, source="smc_event", rationale="سحب سيولة أعلى قمة حديثة ثم رفض على شموع M5 المغلقة."))

    structure = context.get("structure") if isinstance(context.get("structure"), dict) else None
    if structure:
        side = str(structure.get("side") or "")
        typ = str(structure.get("type") or "")
        if typ == "CHOCH" and side == "bullish":
            matches.append(_make_match("SMC_CHOCH_BULL", 81, source="market_structure", rationale="كسر صاعد لآخر Swing مخالف بعد بنية هابطة حديثة."))
        elif typ == "CHOCH" and side == "bearish":
            matches.append(_make_match("SMC_CHOCH_BEAR", 81, source="market_structure", rationale="كسر هابط لآخر Swing مخالف بعد بنية صاعدة حديثة."))
        elif typ == "BOS" and side == "bullish":
            matches.append(_make_match("SMC_BOS_BULL", 78, source="market_structure", rationale="إغلاق صاعد فوق Swing High حقيقي."))
        elif typ == "BOS" and side == "bearish":
            matches.append(_make_match("SMC_BOS_BEAR", 78, source="market_structure", rationale="إغلاق هابط تحت Swing Low حقيقي."))

    # OB/FVG are confluence references.  Score remains below a strong pattern
    # unless the M5 structure points the same way, preventing zones from
    # dominating the decision merely because they exist.
    ob = context.get("order_block")
    if ob == "bullish":
        s = 72 + (7 if structure and structure.get("side") == "bullish" else 0)
        matches.append(_make_match("SMC_OB_REACTION_BULL", s, source="zone_confluence", rationale="Order Block صاعد حقيقي حديث؛ يحتاج تفاعل/رفض قبل التنفيذ."))
    elif ob == "bearish":
        s = 72 + (7 if structure and structure.get("side") == "bearish" else 0)
        matches.append(_make_match("SMC_OB_REACTION_BEAR", s, source="zone_confluence", rationale="Order Block هابط حقيقي حديث؛ يحتاج تفاعل/رفض قبل التنفيذ."))

    fvg = context.get("fvg")
    if fvg == "bullish":
        s = 70 + (7 if structure and structure.get("side") == "bullish" else 0)
        matches.append(_make_match("SMC_FVG_RETRACE_BULL", s, source="zone_confluence", rationale="FVG صاعدة حقيقية ضمن نافذة M5؛ لا تنفيذ بلا عودة/ثبات."))
    elif fvg == "bearish":
        s = 70 + (7 if structure and structure.get("side") == "bearish" else 0)
        matches.append(_make_match("SMC_FVG_RETRACE_BEAR", s, source="zone_confluence", rationale="FVG هابطة حقيقية ضمن نافذة M5؛ لا تنفيذ بلا عودة/رفض."))

    matches.sort(
        key=lambda item: (
            int(item.get("score") or 0),
            str(item.get("candidate_timeframe") or "") == "M5",
            bool(item.get("execution_eligible")),
        ),
        reverse=True,
    )

    # Enrich only the deterministic M5 overlays; do not fabricate geometry for
    # SMC references or library-only patterns.
    enriched_overlays: list[dict[str, Any]] = []
    for overlay in review.get("overlay_patterns") or []:
        if not isinstance(overlay, dict):
            continue
        ref_id = _map_pattern_to_reference(str(overlay.get("name") or ""), str(overlay.get("bias") or ""))
        if not ref_id:
            continue
        score = _candidate_match_score(overlay, context)
        if score < 68:
            continue
        item = dict(overlay)
        item["reference_id"] = ref_id
        item["reference_match_score"] = score
        item["reference_match_strength"] = _strength(score)
        enriched_overlays.append(item)
    enriched_overlays.sort(
        key=lambda item: (
            int(item.get("reference_match_score") or 0),
            str(item.get("status") or "") == "confirmed",
            int(item.get("confidence") or 0),
        ),
        reverse=True,
    )
    enriched_overlays = enriched_overlays[:2]

    best = matches[0] if matches else None
    return {
        "available": bool(best and int(best.get("score") or 0) >= 68),
        "strong_available": bool(best and int(best.get("score") or 0) >= 78),
        "primary_match": best,
        "top_matches": matches[:6],
        "overlay_patterns": enriched_overlays,
        "context": context,
        "library_version": str((load_reference_library().get("meta") or {}).get("version") or "1.0"),
        "reviewed_reference_count": len(load_reference_library().get("references") or []),
        "policy": "closest_real_rule_not_visual_copy",
    }
