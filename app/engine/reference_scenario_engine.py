"""Reference-scenario matcher for SaleeM v7.3.

This module converts the user's approved reference examples into deterministic
scenario templates.  Visual similarity may rank a template, but no scenario is
accepted unless the closed M5 candles independently provide the required
structure.  The engine never fabricates price anchors, Order Blocks, FVGs,
liquidity sweeps, or directional breaks.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any


@dataclass(frozen=True)
class ScenarioTemplate:
    scenario_id: str
    label_ar: str
    bias: str
    rule_ar: str
    required: tuple[str, ...]
    optional: tuple[str, ...] = ()
    source_reference_id: str = ""


SCENARIOS: tuple[ScenarioTemplate, ...] = (
    ScenarioTemplate(
        "trend_reversal_choch_ifvg",
        "انعكاس اتجاه + CHOCH + IFVG",
        "صاعد",
        "هبوط سابق ثم تغير بنيوي CHOCH/BOS، عودة إلى فجوة/منطقة طلب، ثم استمرار صاعد.",
        ("choch_bull", "bullish_impulse"),
        ("fvg", "order_block", "liquidity_sweep_low", "bos_bull"),
        "result_01",
    ),
    ScenarioTemplate(
        "bullish_engulfing_orderblock",
        "ابتلاع شرائي عند Order Block",
        "صاعد",
        "منطقة أوامر حقيقية مع ابتلاع شرائي أو اندفاع صاعد بعد سحب سيولة/كسر بنيوي.",
        ("order_block", "bullish_engulfing"),
        ("bos_bull", "choch_bull", "liquidity_sweep_low"),
        "result_02",
    ),
    ScenarioTemplate(
        "bearish_fvg_liquidity_double_top",
        "سحب سيولة + FVG + قمة مزدوجة",
        "هابط",
        "سحب سيولة أعلى القمم ثم رفض داخل/قرب FVG مع قمة مزدوجة أو ضغط هابط وكسر بنيوي.",
        ("liquidity_sweep_high", "bearish_impulse"),
        ("double_top", "fvg", "bos_bear", "choch_bear"),
        "result_03",
    ),
    ScenarioTemplate(
        "inverse_head_shoulders_ob",
        "رأس وكتفين مقلوب + CHOCH + Order Block",
        "صاعد",
        "رأس وكتفين مقلوب مثبت على قيعان حقيقية، ثم CHOCH/كسر عنق مع دعم من Order Block.",
        ("inverse_head_shoulders", "bullish_impulse"),
        ("choch_bull", "order_block", "bos_bull"),
        "result_04",
    ),
    ScenarioTemplate(
        "bearish_bos_ob_retest",
        "BOS هابط + Order Block + إعادة اختبار",
        "هابط",
        "كسر هيكل هابط، ثم ارتداد إلى منطقة أوامر/مقاومة وفشل الاستعادة قبل استمرار الهبوط.",
        ("bos_bear", "bearish_impulse"),
        ("order_block", "break_retest", "fvg"),
        "result_05",
    ),
    ScenarioTemplate(
        "distribution_structure_sequence",
        "توزيع: Sweep → MSS/CHOCH → BOS → تجميع",
        "هابط",
        "سحب سيولة من الأعلى ثم تغير بنيوي هابط، BOS، وتجميع/إعادة اختبار تحت منطقة عرض قبل الهبوط.",
        ("liquidity_sweep_high", "bos_bear"),
        ("choch_bear", "order_block", "range", "idm"),
        "result_06",
    ),
    ScenarioTemplate(
        "multiple_tops_breakdown",
        "M / قمم متعددة + ضغط على الدعم",
        "هابط",
        "قمتان أو أكثر عند مقاومة واحدة مع فشل الاختراق؛ يبقى السيناريو مرشحًا أثناء الضغط على الدعم/العنق، ويصبح أقوى بعد كسر الدعم.",
        ("bearish_top_pattern",),
        ("bearish_impulse", "bos_bear", "break_retest", "liquidity_sweep_high"),
        "result_07",
    ),
    ScenarioTemplate(
        "bullish_smc_reversal",
        "انعكاس SMC صاعد",
        "صاعد",
        "Liquidity Sweep/Grab أسفل قاع، ثم CHOCH/BOS صاعد مع Order Block قريب واستمرار أعلى.",
        ("liquidity_sweep_low", "choch_bull"),
        ("order_block", "bos_bull", "bullish_engulfing"),
        "result_08",
    ),
    ScenarioTemplate(
        "smart_money_sellside_reversal",
        "Sell-side Sweep → BOS/CHOCH → Order Block",
        "صاعد",
        "اتجاه هابط سابق يسحب سيولة البيع أسفل القاع ثم يتحول عبر BOS/CHOCH إلى صعود مدعوم بمنطقة أوامر.",
        ("liquidity_sweep_low", "bullish_impulse"),
        ("bos_bull", "choch_bull", "order_block"),
        "result_09",
    ),
)


def _num(value: Any) -> float | None:
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
        vals = [_num(item.get(k)) for k in ("open", "high", "low", "close")]
        if any(v is None for v in vals):
            continue
        o, h, l, c = (float(v) for v in vals)
        rows.append({"open": o, "high": max(h, o, c), "low": min(l, o, c), "close": c})
    return rows


def _atr(candles: list[dict[str, float]], n: int = 24) -> float:
    rows = candles[-n:]
    return max(0.01, median([max(0.01, r["high"] - r["low"]) for r in rows])) if rows else 0.01


def _pivots(candles: list[dict[str, float]], window: int = 2) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    if len(candles) < window * 2 + 3:
        return highs, lows
    for i in range(window, len(candles) - window):
        h = candles[i]["high"]
        l = candles[i]["low"]
        neighbors = candles[i-window:i] + candles[i+1:i+1+window]
        if h >= max(r["high"] for r in neighbors):
            highs.append((i, h))
        if l <= min(r["low"] for r in neighbors):
            lows.append((i, l))
    return highs, lows


def _structure_events(candles: list[dict[str, float]]) -> list[dict[str, Any]]:
    highs, lows = _pivots(candles)
    atr = _atr(candles)
    tol = atr * 0.05
    high_map = {i: p for i, p in highs}
    low_map = {i: p for i, p in lows}
    active_high: tuple[int, float] | None = None
    active_low: tuple[int, float] | None = None
    broken_h: set[int] = set()
    broken_l: set[int] = set()
    side_state: str | None = None
    out: list[dict[str, Any]] = []
    for j in range(len(candles)):
        known = j - 2
        if known in high_map:
            active_high = (known, high_map[known])
        if known in low_map:
            active_low = (known, low_map[known])
        close = candles[j]["close"]
        candidate: dict[str, Any] | None = None
        if active_high and active_high[0] not in broken_h and close > active_high[1] + tol:
            candidate = {
                "side": "bull",
                "swing_index": active_high[0],
                "anchor_index": active_high[0],
                "break_index": j,
                "price": active_high[1],
                "price_level": active_high[1],
                "break_close": close,
                "validation_reason": "closed_M5_above_real_swing_high",
            }
            broken_h.add(active_high[0])
        if active_low and active_low[0] not in broken_l and close < active_low[1] - tol:
            bear = {
                "side": "bear",
                "swing_index": active_low[0],
                "anchor_index": active_low[0],
                "break_index": j,
                "price": active_low[1],
                "price_level": active_low[1],
                "break_close": close,
                "validation_reason": "closed_M5_below_real_swing_low",
            }
            broken_l.add(active_low[0])
            if candidate is None or (active_low[1] - close) > (close - float(candidate["price"])):
                candidate = bear
        if candidate is None:
            continue
        side = str(candidate["side"])
        label = "BOS" if side_state is None or side_state == side else "CHOCH"
        if label == "CHOCH" or side_state is None:
            side_state = side
        candidate["label"] = label
        out.append(candidate)
    return out[-6:]


def _fvg(candles: list[dict[str, float]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(2, len(candles)):
        a, c = candles[i-2], candles[i]
        if a["high"] < c["low"]:
            out.append({
                "index": i,
                "anchor_index": i - 2,
                "source_indices": [i - 2, i - 1, i],
                "low": a["high"],
                "high": c["low"],
                "price_level": (a["high"] + c["low"]) / 2.0,
                "side": "bull",
                "validation_reason": "real_three_candle_bullish_gap",
            })
        elif a["low"] > c["high"]:
            out.append({
                "index": i,
                "anchor_index": i - 2,
                "source_indices": [i - 2, i - 1, i],
                "low": c["high"],
                "high": a["low"],
                "price_level": (c["high"] + a["low"]) / 2.0,
                "side": "bear",
                "validation_reason": "real_three_candle_bearish_gap",
            })
    return out[-16:]


def _order_blocks(candles: list[dict[str, float]]) -> list[dict[str, Any]]:
    if len(candles) < 5:
        return []
    bodies = [abs(r["close"] - r["open"]) for r in candles]
    baseline = max(0.01, median(bodies))
    out: list[dict[str, Any]] = []
    for i in range(1, len(candles)):
        prev, impulse = candles[i-1], candles[i]
        body = abs(impulse["close"] - impulse["open"])
        prev_bull = prev["close"] >= prev["open"]
        impulse_bull = impulse["close"] >= impulse["open"]
        if body < baseline * 1.35 or prev_bull == impulse_bull:
            continue
        out.append({
            "index": i-1,
            "anchor_index": i-1,
            "low": prev["low"],
            "high": prev["high"],
            "price_level": (prev["low"] + prev["high"]) / 2.0,
            "strength": min(100, int(58 + body / baseline * 12)),
            "side": "bull" if impulse_bull else "bear",
            "impulse_index": i,
            "validation_reason": "last_opposite_candle_before_real_impulse",
        })
    return out[-8:]


def _engulfing(candles: list[dict[str, float]]) -> dict[str, Any] | None:
    for i in range(len(candles)-1, max(0, len(candles)-10), -1):
        if i <= 0:
            break
        a, b = candles[i-1], candles[i]
        a_low, a_high = sorted((a["open"], a["close"]))
        b_low, b_high = sorted((b["open"], b["close"]))
        if b["close"] > b["open"] and a["close"] < a["open"] and b_low <= a_low and b_high >= a_high:
            return {"index": i, "side": "bull"}
        if b["close"] < b["open"] and a["close"] > a["open"] and b_low <= a_low and b_high >= a_high:
            return {"index": i, "side": "bear"}
    return None


def _liquidity_sweeps(candles: list[dict[str, float]]) -> list[dict[str, Any]]:
    highs, lows = _pivots(candles)
    atr = _atr(candles)
    out: list[dict[str, Any]] = []
    recent_floor = max(3, len(candles) - 42)
    for i in range(recent_floor, len(candles)):
        row = candles[i]
        prior_h = [(idx, p) for idx, p in highs if idx < i]
        prior_l = [(idx, p) for idx, p in lows if idx < i]
        if prior_h:
            anchor_idx, ref = prior_h[-1]
            if row["high"] > ref + atr * 0.05 and row["close"] < ref:
                out.append({
                    "index": i,
                    "anchor_index": anchor_idx,
                    "price": ref,
                    "price_level": ref,
                    "side": "high",
                    "source": "pivot",
                    "validation_reason": "wick_above_real_pivot_and_close_back_below",
                })
        if prior_l:
            anchor_idx, ref = prior_l[-1]
            if row["low"] < ref - atr * 0.05 and row["close"] > ref:
                out.append({
                    "index": i,
                    "anchor_index": anchor_idx,
                    "price": ref,
                    "price_level": ref,
                    "side": "low",
                    "source": "pivot",
                    "validation_reason": "wick_below_real_pivot_and_close_back_above",
                })

    # Equal-high/equal-low liquidity is stronger for the teaching drawing.
    # Detect the sweep against the real cluster level and prefer it when present.
    for side in ("high", "low"):
        cluster = _equal_liquidity_cluster(candles, side)
        if not cluster:
            continue
        points = cluster.get("points") or []
        if not points:
            continue
        last_idx = max(int(p.get("index") or 0) for p in points if isinstance(p, dict))
        level = float(cluster["price"])
        for i in range(max(last_idx + 1, recent_floor), len(candles)):
            row = candles[i]
            if side == "high":
                swept = row["high"] > level + atr * 0.05 and row["close"] < level
            else:
                swept = row["low"] < level - atr * 0.05 and row["close"] > level
            if swept:
                out.append({
                    "index": i,
                    "anchor_index": last_idx,
                    "price": level,
                    "price_level": level,
                    "side": side,
                    "source": "equal_liquidity",
                    "validation_reason": (
                        "wick_above_equal_highs_and_close_back_below"
                        if side == "high"
                        else "wick_below_equal_lows_and_close_back_above"
                    ),
                })

    dedup: dict[tuple[int, str], dict[str, Any]] = {}
    for item in out:
        key = (int(item["index"]), str(item["side"]))
        # equal-liquidity geometry is more explanatory than the single-pivot fallback.
        if key not in dedup or item.get("source") == "equal_liquidity":
            dedup[key] = item
    return sorted(dedup.values(), key=lambda x: int(x["index"]))[-4:]


def _equal_liquidity_cluster(candles: list[dict[str, float]], side: str) -> dict[str, Any] | None:
    """Find 2-3 real pivot highs/lows sharing one liquidity level.

    The cluster is price-derived only.  It is used by the renderer for the
    reference-style 1st/2nd/3rd Top (or Bottom) circles and for the
    sell-side/buy-side liquidity band.  No synthetic anchor is created.
    """
    highs, lows = _pivots(candles)
    pivots = highs if side == "high" else lows
    if len(pivots) < 2:
        return None
    atr = _atr(candles)
    tol = max(0.03, atr * 0.42)
    recent = pivots[-14:]
    best: tuple[float, list[tuple[int, float]]] | None = None
    for _idx, anchor_price in recent:
        members = [(i, p) for i, p in recent if abs(p - anchor_price) <= tol]
        # Keep distinct swing events rather than neighbouring candles around
        # the same local wick.
        spaced: list[tuple[int, float]] = []
        for item in members:
            if not spaced or item[0] - spaced[-1][0] >= 3:
                spaced.append(item)
            elif abs(item[1] - anchor_price) < abs(spaced[-1][1] - anchor_price):
                spaced[-1] = item
        if len(spaced) < 2:
            continue
        prices = [p for _, p in spaced]
        spread = max(prices) - min(prices)
        recency = spaced[-1][0] / max(1, len(candles) - 1)
        score = min(3, len(spaced)) * 100.0 + recency * 18.0 - (spread / max(tol, 1e-9)) * 9.0
        if best is None or score > best[0]:
            best = (score, spaced)
    if best is None:
        return None
    members = best[1][-3:]
    level = median([p for _, p in members])
    return {
        "side": side,
        "price": float(level),
        "tolerance": float(tol),
        "points": [{"index": int(i), "price": float(p)} for i, p in members],
        "count": len(members),
    }


def _trend_lines(candles: list[dict[str, float]]) -> dict[str, dict[str, Any] | None]:
    """Return the most recent real rising-low / falling-high trend line."""
    highs, lows = _pivots(candles)
    atr = _atr(candles)

    bull = None
    for a, b in zip(lows[-12:-1], lows[-11:]):
        if b[0] - a[0] >= 3 and b[1] > a[1] + atr * 0.06:
            bull = {"p1": [int(a[0]), float(a[1])], "p2": [int(b[0]), float(b[1])], "side": "bull"}

    bear = None
    for a, b in zip(highs[-12:-1], highs[-11:]):
        if b[0] - a[0] >= 3 and b[1] < a[1] - atr * 0.06:
            bear = {"p1": [int(a[0]), float(a[1])], "p2": [int(b[0]), float(b[1])], "side": "bear"}

    return {"bull": bull, "bear": bear}


def _latest_side(items: list[dict[str, Any]], side: str) -> dict[str, Any] | None:
    for item in reversed(items):
        if str(item.get("side") or "") == side:
            return item
    return None


def _first_side_after(items: list[dict[str, Any]], side: str, anchor_index: int | None, max_distance: int = 16) -> dict[str, Any] | None:
    if anchor_index is None:
        return None
    candidates = [
        item for item in items
        if str(item.get("side") or "") == side
        and anchor_index <= int(item.get("index") or -10_000) <= anchor_index + max_distance
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: int(item.get("index") or 0))


def _range_state(candles: list[dict[str, float]]) -> bool:
    if len(candles) < 10:
        return False
    atr = _atr(candles)
    recent = candles[-8:]
    span = max(r["high"] for r in recent) - min(r["low"] for r in recent)
    net = abs(recent[-1]["close"] - recent[0]["close"])
    return span <= atr * 3.8 and net <= atr * 1.15


def _classical_features(pattern_review: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for item in pattern_review.get("candidates") or []:
        if not isinstance(item, dict) or str(item.get("timeframe") or "") != "M5":
            continue
        if int(item.get("confidence") or 0) < 58:
            continue
        name = str(item.get("name") or "")
        if name == "M":
            out.add("double_top")
            out.add("bearish_top_pattern")
        if name == "W": out.add("double_bottom")
        if name == "قمة ثلاثية":
            out.add("multiple_tops")
            out.add("bearish_top_pattern")
        if name == "قاع ثلاثي": out.add("multiple_bottoms")
        if "رأس وكتفين مقلوب" in name: out.add("inverse_head_shoulders")
        elif "رأس وكتفين" in name: out.add("head_shoulders")
        if name == "كسر وإعادة اختبار": out.add("break_retest")
    return out


def build_reference_features(frames: Any, pattern_review: dict[str, Any]) -> dict[str, Any]:
    m5 = _normalize((frames or {}).get("M5") if isinstance(frames, dict) else [])
    if not m5:
        return {"features": [], "geometry": {}}
    atr = _atr(m5)
    structures = _structure_events(m5)
    gaps = _fvg(m5)
    blocks = _order_blocks(m5)
    sweeps = _liquidity_sweeps(m5)
    engulf = _engulfing(m5)
    equal_highs = _equal_liquidity_cluster(m5, "high")
    equal_lows = _equal_liquidity_cluster(m5, "low")
    trend_lines = _trend_lines(m5)
    features = _classical_features(pattern_review)
    for event in structures:
        side = str(event.get("side"))
        label = str(event.get("label"))
        if label == "BOS": features.add("bos_bull" if side == "bull" else "bos_bear")
        if label == "CHOCH": features.add("choch_bull" if side == "bull" else "choch_bear")
    if gaps: features.add("fvg")
    if blocks: features.add("order_block")
    if any(s.get("side") == "high" for s in sweeps): features.add("liquidity_sweep_high")
    if any(s.get("side") == "low" for s in sweeps): features.add("liquidity_sweep_low")
    if equal_highs and int(equal_highs.get("count") or 0) >= 2: features.add("equal_highs")
    if equal_lows and int(equal_lows.get("count") or 0) >= 2: features.add("equal_lows")
    if engulf:
        features.add("bullish_engulfing" if engulf["side"] == "bull" else "bearish_engulfing")
    if _range_state(m5): features.add("range")
    if structures and len(structures) >= 2: features.add("idm")
    if len(m5) >= 4:
        move = m5[-1]["close"] - m5[-4]["close"]
        if move > atr * 0.75: features.add("bullish_impulse")
        elif move < -atr * 0.75: features.add("bearish_impulse")
        else:
            # A recent break itself is enough to mark directional impulse.
            last = structures[-1] if structures else None
            if last and int(last.get("break_index", -99)) >= len(m5) - 5:
                features.add("bullish_impulse" if last.get("side") == "bull" else "bearish_impulse")

    return {
        "features": sorted(features),
        "geometry": {
            "window_size": len(m5),
            "structure_events": structures,
            "fvg": gaps[-1] if gaps else None,
            "fvgs": gaps[-16:],
            "fvg_bull": _latest_side(gaps, "bull"),
            "fvg_bear": _latest_side(gaps, "bear"),
            "order_block": blocks[-1] if blocks else None,
            "order_blocks": blocks[-8:],
            "order_block_bull": _latest_side(blocks, "bull"),
            "order_block_bear": _latest_side(blocks, "bear"),
            "liquidity_sweep": sweeps[-1] if sweeps else None,
            "liquidity_sweep_high": _latest_side(sweeps, "high"),
            "liquidity_sweep_low": _latest_side(sweeps, "low"),
            "equal_highs": equal_highs,
            "equal_lows": equal_lows,
            "trend_line_bull": trend_lines.get("bull"),
            "trend_line_bear": trend_lines.get("bear"),
            "engulfing": engulf,
        },
    }


def review_reference_scenarios(
    frames: Any,
    pattern_review: dict[str, Any],
    visual_match: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one closest *verified* scenario from the approved reference memory."""
    built = build_reference_features(frames, pattern_review)
    features = set(built.get("features") or [])
    if not features:
        return {
            "available": False,
            "scenario_id": "none",
            "label_ar": "لا يوجد سيناريو مرجعي مكتمل",
            "confidence": 0,
            "status": "none",
            "bias": "محايد",
            "source_reference_id": "",
            "rule_ar": "",
            "evidence": "لا توجد هندسة M5 كافية لمطابقة سيناريو مرجعي.",
            "features": [],
            "geometry": built.get("geometry") or {},
            "draw_components": [],
        }

    visual_id = str((visual_match or {}).get("scenario_reference_id") or "").strip()
    visual_score = max(0, min(100, int((visual_match or {}).get("scenario_score") or 0)))
    ranked: list[tuple[float, ScenarioTemplate, list[str], list[str]]] = []
    for template in SCENARIOS:
        req_present = [f for f in template.required if f in features]
        opt_present = [f for f in template.optional if f in features]
        req_ratio = len(req_present) / max(1, len(template.required))
        score = req_ratio * 72.0 + min(22.0, len(opt_present) * 7.0)
        if visual_id == template.source_reference_id and visual_score >= 55:
            score += min(10.0, visual_score * 0.10)
        # Visual similarity cannot rescue missing hard structure.
        if req_ratio < 1.0:
            score -= 32.0 * (1.0 - req_ratio)
        ranked.append((score, template, req_present, opt_present))

    ranked.sort(key=lambda x: x[0], reverse=True)
    score, template, req_present, opt_present = ranked[0]
    hard_ok = len(req_present) == len(template.required)
    confidence = max(0, min(96, int(round(score))))
    available = hard_ok and confidence >= 60
    if not available:
        return {
            "available": False,
            "scenario_id": "none",
            "label_ar": "لا يوجد سيناريو مرجعي مكتمل",
            "confidence": 0,
            "status": "none",
            "bias": "محايد",
            "source_reference_id": "",
            "rule_ar": "",
            "evidence": "أقرب مرجع لم يحقق جميع الشروط الهندسية الإلزامية على M5.",
            "features": sorted(features),
            "geometry": built.get("geometry") or {},
            "draw_components": [],
            "closest_rejected_id": template.scenario_id,
            "closest_rejected_score": confidence,
        }

    geometry = dict(built.get("geometry") or {})
    side_key = "bear" if template.bias == "هابط" else "bull"
    sweep_key = "liquidity_sweep_high" if template.bias == "هابط" else "liquidity_sweep_low"
    geometry["liquidity_sweep"] = geometry.get(sweep_key) or geometry.get("liquidity_sweep")
    sweep_index = None
    if isinstance(geometry.get("liquidity_sweep"), dict):
        try: sweep_index = int(geometry["liquidity_sweep"].get("index"))
        except (TypeError, ValueError): sweep_index = None
    side_fvgs = list(geometry.get("fvgs") or [])
    side_blocks = list(geometry.get("order_blocks") or [])
    # Directional zones are strict.  A bearish reference may never borrow a
    # bullish FVG/OB (and vice versa) just to complete the picture.  Prefer the
    # first same-side zone created around/after the sweep, then the latest
    # same-side real zone.  If neither exists the component is omitted.
    geometry["fvg"] = (
        _first_side_after(side_fvgs, side_key, sweep_index, 18)
        or geometry.get(f"fvg_{side_key}")
    )
    geometry["order_block"] = (
        _first_side_after(side_blocks, side_key, max(0, (sweep_index or 0) - 2), 10)
        or geometry.get(f"order_block_{side_key}")
    )

    def _anchored(item: Any, *, needs_range: bool = False) -> bool:
        if not isinstance(item, dict):
            return False
        anchor = item.get("anchor_index", item.get("swing_index", item.get("index")))
        reason = str(item.get("validation_reason") or "").strip()
        level = item.get("price_level", item.get("price"))
        if anchor is None or level is None or not reason:
            return False
        if needs_range and (item.get("low") is None or item.get("high") is None):
            return False
        return True

    valid_structure = [
        event for event in (geometry.get("structure_events") or [])
        if _anchored(event) and event.get("break_index") is not None
    ]
    geometry["structure_events"] = valid_structure

    status = "confirmed" if confidence >= 78 and len(opt_present) >= 1 else "candidate"
    draw: list[str] = ["expectation_arrow"]
    if valid_structure:
        draw.append("structure")
    if _anchored(geometry.get("order_block"), needs_range=True):
        draw.append("order_block")
    if _anchored(geometry.get("fvg"), needs_range=True):
        draw.append("fvg")
    if _anchored(geometry.get("liquidity_sweep")):
        draw.append("liquidity")
    if "bullish_engulfing" in features or "bearish_engulfing" in features: draw.append("engulfing")
    if any(f in features for f in ("double_top", "multiple_tops", "inverse_head_shoulders", "head_shoulders", "break_retest")):
        draw.append("pattern")

    evidence_bits = req_present + opt_present[:3]
    return {
        "available": True,
        "scenario_id": template.scenario_id,
        "label_ar": template.label_ar,
        "confidence": confidence,
        "status": status,
        "bias": template.bias,
        "source_reference_id": template.source_reference_id,
        "rule_ar": template.rule_ar,
        "evidence": " + ".join(evidence_bits),
        "features": sorted(features),
        "geometry": geometry,
        "draw_components": draw,
        "visual_reference_score": visual_score if visual_id == template.source_reference_id else 0,
    }
