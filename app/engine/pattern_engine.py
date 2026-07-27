from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PatternCandidate:
    name: str
    confidence: int
    timeframe: str
    bias: str
    evidence: str


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
    return max(0.01, sum(max(0.01, row["high"] - row["low"]) for row in rows) / len(rows))


def _pivots(candles: list[dict[str, float]], window: int = 2) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    peaks: list[tuple[int, float]] = []
    troughs: list[tuple[int, float]] = []
    if len(candles) < window * 2 + 3:
        return peaks, troughs
    for index in range(window, len(candles) - window):
        high = candles[index]["high"]
        low = candles[index]["low"]
        left = candles[index - window:index]
        right = candles[index + 1:index + 1 + window]
        if all(high >= row["high"] for row in left + right) and (
            high > max(row["high"] for row in left) or high > max(row["high"] for row in right)
        ):
            peaks.append((index, high))
        if all(low <= row["low"] for row in left + right) and (
            low < min(row["low"] for row in left) or low < min(row["low"] for row in right)
        ):
            troughs.append((index, low))
    return peaks, troughs


def _linear_slope(points: list[tuple[int, float]]) -> float:
    if len(points) < 2:
        return 0.0
    x_mean = sum(point[0] for point in points) / len(points)
    y_mean = sum(point[1] for point in points) / len(points)
    denominator = sum((point[0] - x_mean) ** 2 for point in points)
    if denominator <= 1e-9:
        return 0.0
    return sum((point[0] - x_mean) * (point[1] - y_mean) for point in points) / denominator


def _double_pattern(
    candles: list[dict[str, float]],
    *,
    timeframe: str,
    side: str,
) -> PatternCandidate | None:
    atr = _atr(candles)
    peaks, troughs = _pivots(candles)
    pivots = peaks if side == "top" else troughs
    if len(pivots) < 2:
        return None
    # Test the latest sensible pairs, favouring recency without forcing adjacency.
    best: PatternCandidate | None = None
    for first_pos in range(max(0, len(pivots) - 5), len(pivots) - 1):
        for second_pos in range(first_pos + 1, len(pivots)):
            first_index, first_price = pivots[first_pos]
            second_index, second_price = pivots[second_pos]
            separation = second_index - first_index
            if separation < 4 or separation > 28:
                continue
            equality = abs(second_price - first_price) / atr
            if equality > 0.55:
                continue
            middle = candles[first_index + 1:second_index]
            if not middle:
                continue
            if side == "top":
                neckline = min(row["low"] for row in middle)
                depth = (min(first_price, second_price) - neckline) / atr
                confirmed = candles[-1]["close"] < neckline
                bias = "هابط"
                name = "قمتان"
                evidence = "قمتان متقاربتان يفصل بينهما قاع واضح"
            else:
                neckline = max(row["high"] for row in middle)
                depth = (neckline - max(first_price, second_price)) / atr
                confirmed = candles[-1]["close"] > neckline
                bias = "صاعد"
                name = "قاعان"
                evidence = "قاعان متقاربان يفصل بينهما ارتداد واضح"
            if depth < 0.65:
                continue
            confidence = 58
            confidence += min(12, int(depth * 6))
            confidence += max(0, 10 - int(equality * 15))
            if confirmed:
                confidence += 12
                evidence += " مع كسر خط العنق"
            if second_index >= len(candles) - 8:
                confidence += 4
            candidate = PatternCandidate(name, min(92, confidence), timeframe, bias, evidence)
            if best is None or candidate.confidence > best.confidence:
                best = candidate
    return best


def _channel_or_triangle(candles: list[dict[str, float]], *, timeframe: str) -> PatternCandidate | None:
    atr = _atr(candles)
    peaks, troughs = _pivots(candles)
    peaks = peaks[-4:]
    troughs = troughs[-4:]
    if len(peaks) < 3 or len(troughs) < 3:
        return None
    peak_slope = _linear_slope(peaks)
    trough_slope = _linear_slope(troughs)
    normalized_peak = peak_slope / atr
    normalized_trough = trough_slope / atr
    latest_width = peaks[-1][1] - troughs[-1][1]
    early_width = peaks[0][1] - troughs[0][1]
    contracting = latest_width > 0 and early_width > 0 and latest_width < early_width * 0.75

    # Parallel slopes imply a channel.
    if abs(normalized_peak - normalized_trough) <= 0.05 and abs(normalized_peak) >= 0.035:
        if normalized_peak > 0:
            return PatternCandidate(
                "قناة صاعدة", 64 + min(18, int(abs(normalized_peak) * 120)), timeframe, "صاعد",
                "قمم وقيعان تتحرك داخل مسارين صاعدين متوازيين",
            )
        return PatternCandidate(
            "قناة هابطة", 64 + min(18, int(abs(normalized_peak) * 120)), timeframe, "هابط",
            "قمم وقيعان تتحرك داخل مسارين هابطين متوازيين",
        )

    if not contracting:
        return None

    # Converging slopes imply triangle/wedge structures.
    if normalized_peak < -0.025 and normalized_trough > 0.025:
        return PatternCandidate(
            "مثلث متماثل", 68, timeframe, "محايد",
            "قمم هابطة وقيعان صاعدة مع تقلص واضح في النطاق",
        )
    if abs(normalized_peak) <= 0.025 and normalized_trough > 0.035:
        return PatternCandidate(
            "مثلث صاعد", 67, timeframe, "صاعد",
            "قمم شبه ثابتة وقيعان صاعدة تضغط نحو المقاومة",
        )
    if normalized_peak < -0.035 and abs(normalized_trough) <= 0.025:
        return PatternCandidate(
            "مثلث هابط", 67, timeframe, "هابط",
            "قيعان شبه ثابتة وقمم هابطة تضغط نحو الدعم",
        )
    if normalized_peak > 0.02 and normalized_trough > 0.04 and normalized_trough > normalized_peak:
        return PatternCandidate(
            "وتد صاعد", 64, timeframe, "هابط",
            "قمم وقيعان صاعدة لكن القيعان تتقارب من القمم",
        )
    if normalized_peak < -0.04 and normalized_trough < -0.02 and normalized_peak < normalized_trough:
        return PatternCandidate(
            "وتد هابط", 64, timeframe, "صاعد",
            "قمم وقيعان هابطة لكن القمم تتقارب من القيعان",
        )
    return None


def _break_retest(candles: list[dict[str, float]], *, timeframe: str) -> PatternCandidate | None:
    if len(candles) < 20:
        return None
    atr = _atr(candles)
    prior = candles[-20:-4]
    recent = candles[-4:]
    prior_high = max(row["high"] for row in prior)
    prior_low = min(row["low"] for row in prior)
    last_close = candles[-1]["close"]
    if max(row["close"] for row in recent[:-1]) > prior_high + atr * 0.12:
        retest_low = min(row["low"] for row in recent)
        if retest_low <= prior_high + atr * 0.30 and last_close >= prior_high:
            return PatternCandidate(
                "كسر وإعادة اختبار", 72, timeframe, "صاعد",
                "اختراق مقاومة سابقة ثم عودة لاختبارها والثبات فوقها",
            )
    if min(row["close"] for row in recent[:-1]) < prior_low - atr * 0.12:
        retest_high = max(row["high"] for row in recent)
        if retest_high >= prior_low - atr * 0.30 and last_close <= prior_low:
            return PatternCandidate(
                "كسر وإعادة اختبار", 72, timeframe, "هابط",
                "كسر دعم سابق ثم عودة لاختباره والفشل تحته",
            )
    return None


def review_market_patterns(frames: Any) -> dict[str, Any]:
    """Deterministically review supported chart patterns on closed candles.

    The review is intentionally independent of the language model. It checks
    the same published model families every run and returns the best validated
    candidate plus a short audit trail for the UI.
    """
    candidates: list[PatternCandidate] = []
    checked = [
        "قمتان", "قاعان", "مثلث متماثل", "مثلث صاعد", "مثلث هابط",
        "وتد صاعد", "وتد هابط", "قناة صاعدة", "قناة هابطة", "كسر وإعادة اختبار",
    ]
    for timeframe, minimum in (("M5", 26), ("M15", 24), ("H1", 24)):
        source = frames.get(timeframe) if isinstance(frames, dict) else None
        candles = _normalize(source)
        if len(candles) < minimum:
            continue
        window = candles[-48:]
        for candidate in (
            _double_pattern(window, timeframe=timeframe, side="top"),
            _double_pattern(window, timeframe=timeframe, side="bottom"),
            _channel_or_triangle(window, timeframe=timeframe),
            _break_retest(window, timeframe=timeframe),
        ):
            if candidate is not None:
                candidates.append(candidate)

    timeframe_bonus = {"H1": 5, "M15": 4, "M5": 2}
    candidates.sort(
        key=lambda item: (item.confidence + timeframe_bonus.get(item.timeframe, 0), item.confidence),
        reverse=True,
    )
    best = candidates[0] if candidates else None
    return {
        "available": best is not None and best.confidence >= 60,
        "pattern_type": best.name if best is not None and best.confidence >= 60 else "لا يوجد",
        "pattern_confidence": best.confidence if best is not None and best.confidence >= 60 else 0,
        "pattern_timeframe": best.timeframe if best is not None and best.confidence >= 60 else "",
        "pattern_bias": best.bias if best is not None and best.confidence >= 60 else "محايد",
        "pattern_evidence": best.evidence if best is not None and best.confidence >= 60 else "لم يكتمل نموذج هندسي بشروط كافية",
        "checked_patterns": checked,
        "candidates": [
            {
                "name": item.name,
                "confidence": item.confidence,
                "timeframe": item.timeframe,
                "bias": item.bias,
                "evidence": item.evidence,
            }
            for item in candidates[:4]
        ],
    }
