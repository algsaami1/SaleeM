from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PatternCandidate:
    name: str
    confidence: int
    timeframe: str
    bias: str
    evidence: str
    status: str = "candidate"  # candidate | confirmed
    geometry: dict[str, Any] = field(default_factory=dict)


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


def _line_value(p1: tuple[int, float], p2: tuple[int, float], x: int) -> float:
    if p2[0] == p1[0]:
        return float(p2[1])
    ratio = (x - p1[0]) / (p2[0] - p1[0])
    return float(p1[1] + (p2[1] - p1[1]) * ratio)


def _extreme_between(
    candles: list[dict[str, float]],
    start: int,
    end: int,
    *,
    kind: str,
) -> tuple[int, float] | None:
    lo = max(0, min(start, end) + 1)
    hi = min(len(candles), max(start, end))
    if hi <= lo:
        return None
    key = "low" if kind == "low" else "high"
    indices = range(lo, hi)
    idx = min(indices, key=lambda i: candles[i][key]) if kind == "low" else max(indices, key=lambda i: candles[i][key])
    return idx, float(candles[idx][key])


def _geom(
    candles: list[dict[str, float]],
    *,
    anchors: list[tuple[int, float, str]],
    lines: list[tuple[tuple[int, float], tuple[int, float], str]],
    path: list[tuple[int, float]] | None = None,
    trigger: float | None = None,
    stop: float | None = None,
    target: float | None = None,
    breakout_index: int | None = None,
) -> dict[str, Any]:
    return {
        "window_size": len(candles),
        "anchors": [
            {"index": int(idx), "price": round(float(price), 6), "role": role}
            for idx, price, role in anchors
        ],
        "lines": [
            {
                "p1": [int(p1[0]), round(float(p1[1]), 6)],
                "p2": [int(p2[0]), round(float(p2[1]), 6)],
                "role": role,
            }
            for p1, p2, role in lines
        ],
        "path": [[int(idx), round(float(price), 6)] for idx, price in (path or [])],
        "trigger": round(float(trigger), 6) if trigger is not None else None,
        "stop": round(float(stop), 6) if stop is not None else None,
        "target": round(float(target), 6) if target is not None else None,
        "breakout_index": int(breakout_index) if breakout_index is not None else None,
    }


def _double_pattern(candles: list[dict[str, float]], *, timeframe: str, side: str) -> PatternCandidate | None:
    """Detect W/M using only the real three-point core plus a real breakout.

    The visual skeleton is deliberately strict:
    W = low1 -> neckline high -> low2 -> breakout (confirmed only)
    M = high1 -> neckline low -> high2 -> breakout (confirmed only)
    No decorative leg before the first pivot and no guessed leg after the
    second pivot are permitted.
    """
    atr = _atr(candles)
    peaks, troughs = _pivots(candles)
    pivots = peaks if side == "top" else troughs
    if len(pivots) < 2:
        return None
    best: PatternCandidate | None = None
    for first_pos in range(max(0, len(pivots) - 6), len(pivots) - 1):
        for second_pos in range(first_pos + 1, len(pivots)):
            first_index, first_price = pivots[first_pos]
            second_index, second_price = pivots[second_pos]
            separation = second_index - first_index
            if separation < 4 or separation > 30:
                continue
            equality = abs(second_price - first_price) / atr
            if equality > 0.55:
                continue

            breakout_index: int | None = None
            breakout_price: float | None = None
            if side == "top":
                neck = _extreme_between(candles, first_index, second_index, kind="low")
                if neck is None:
                    continue
                neck_index, neckline = neck
                depth = (min(first_price, second_price) - neckline) / atr
                bias, name = "هابط", "M"
                evidence = "قمتان متقاربتان يفصل بينهما قاع واضح"
                stop = max(first_price, second_price) + atr * 0.18
                target = neckline - max(atr * 0.8, min(first_price, second_price) - neckline)
                for idx in range(second_index + 1, len(candles)):
                    if candles[idx]["close"] < neckline - atr * 0.04:
                        breakout_index = idx
                        breakout_price = float(candles[idx]["close"])
                        break
            else:
                neck = _extreme_between(candles, first_index, second_index, kind="high")
                if neck is None:
                    continue
                neck_index, neckline = neck
                depth = (neckline - max(first_price, second_price)) / atr
                bias, name = "صاعد", "W"
                evidence = "قاعان متقاربان يفصل بينهما ارتداد واضح"
                stop = min(first_price, second_price) - atr * 0.18
                target = neckline + max(atr * 0.8, neckline - max(first_price, second_price))
                for idx in range(second_index + 1, len(candles)):
                    if candles[idx]["close"] > neckline + atr * 0.04:
                        breakout_index = idx
                        breakout_price = float(candles[idx]["close"])
                        break

            if depth < 0.65:
                continue
            confirmed = breakout_index is not None
            confidence = 58 + min(12, int(depth * 6)) + max(0, 10 - int(equality * 15))
            status = "confirmed" if confirmed else "candidate"
            if confirmed:
                confidence += 12
                evidence += " مع كسر خط العنق"
            if second_index >= len(candles) - 8:
                confidence += 4

            path_points: list[tuple[int, float]] = [
                (first_index, first_price),
                (neck_index, neckline),
                (second_index, second_price),
            ]
            if confirmed and breakout_index is not None and breakout_price is not None:
                path_points.append((breakout_index, breakout_price))

            geometry = _geom(
                candles,
                anchors=[
                    (first_index, first_price, "pivot"),
                    (neck_index, neckline, "neck"),
                    (second_index, second_price, "pivot"),
                ],
                lines=[((first_index, neckline), ((breakout_index if confirmed and breakout_index is not None else second_index), neckline), "neckline")],
                path=path_points,
                trigger=neckline,
                stop=stop,
                target=target,
                breakout_index=breakout_index if confirmed else None,
            )
            candidate = PatternCandidate(name, min(94, confidence), timeframe, bias, evidence, status, geometry)
            if best is None or candidate.confidence > best.confidence:
                best = candidate
    return best

def _triple_pattern(candles: list[dict[str, float]], *, timeframe: str, side: str) -> PatternCandidate | None:
    atr = _atr(candles)
    peaks, troughs = _pivots(candles)
    pivots = peaks if side == "top" else troughs
    if len(pivots) < 3:
        return None
    best: PatternCandidate | None = None
    latest = pivots[-6:]
    for a in range(len(latest) - 2):
        p1, p2, p3 = latest[a], latest[a + 1], latest[a + 2]
        if p2[0] - p1[0] < 3 or p3[0] - p2[0] < 3:
            continue
        spread = (max(p1[1], p2[1], p3[1]) - min(p1[1], p2[1], p3[1])) / atr
        if spread > 0.72:
            continue
        if side == "top":
            n1 = _extreme_between(candles, p1[0], p2[0], kind="low")
            n2 = _extreme_between(candles, p2[0], p3[0], kind="low")
            if not n1 or not n2:
                continue
            neckline = min(n1[1], n2[1])
            depth = (min(p1[1], p2[1], p3[1]) - neckline) / atr
            confirmed = candles[-1]["close"] < neckline - atr * 0.04
            bias, name = "هابط", "قمة ثلاثية"
            evidence = "ثلاث قمم متقاربة مع خط عنق واضح"
            stop = max(p1[1], p2[1], p3[1]) + atr * 0.18
            target = neckline - max(atr, min(p1[1], p2[1], p3[1]) - neckline)
        else:
            n1 = _extreme_between(candles, p1[0], p2[0], kind="high")
            n2 = _extreme_between(candles, p2[0], p3[0], kind="high")
            if not n1 or not n2:
                continue
            neckline = max(n1[1], n2[1])
            depth = (neckline - max(p1[1], p2[1], p3[1])) / atr
            confirmed = candles[-1]["close"] > neckline + atr * 0.04
            bias, name = "صاعد", "قاع ثلاثي"
            evidence = "ثلاث قيعان متقاربة مع خط عنق واضح"
            stop = min(p1[1], p2[1], p3[1]) - atr * 0.18
            target = neckline + max(atr, neckline - max(p1[1], p2[1], p3[1]))
        if depth < 0.70:
            continue
        confidence = 62 + min(12, int(depth * 5)) + max(0, 8 - int(spread * 10)) + (10 if confirmed else 0)
        if confirmed:
            evidence += " وتم كسر خط العنق"
        geometry = _geom(
            candles,
            anchors=[(p1[0], p1[1], "pivot"), (p2[0], p2[1], "pivot"), (p3[0], p3[1], "pivot")],
            lines=[((p1[0], neckline), (len(candles) - 1, neckline), "neckline")],
            path=[p1, p2, p3],
            trigger=neckline,
            stop=stop,
            target=target,
            breakout_index=len(candles) - 1 if confirmed else None,
        )
        candidate = PatternCandidate(name, min(94, confidence), timeframe, bias, evidence, "confirmed" if confirmed else "candidate", geometry)
        if best is None or candidate.confidence > best.confidence:
            best = candidate
    return best


def _head_shoulders(candles: list[dict[str, float]], *, timeframe: str, inverse: bool) -> PatternCandidate | None:
    atr = _atr(candles)
    peaks, troughs = _pivots(candles)
    main = troughs if inverse else peaks
    if len(main) < 3:
        return None
    best: PatternCandidate | None = None
    for pos in range(max(0, len(main) - 6), len(main) - 2):
        left, head, right = main[pos], main[pos + 1], main[pos + 2]
        if head[0] - left[0] < 3 or right[0] - head[0] < 3:
            continue
        shoulder_diff = abs(left[1] - right[1]) / atr
        if shoulder_diff > 0.85:
            continue
        if inverse:
            head_extension = (min(left[1], right[1]) - head[1]) / atr
            n1 = _extreme_between(candles, left[0], head[0], kind="high")
            n2 = _extreme_between(candles, head[0], right[0], kind="high")
            if not n1 or not n2 or head_extension < 0.55:
                continue
            neck_now = _line_value(n1, n2, len(candles) - 1)
            confirmed = candles[-1]["close"] > neck_now + atr * 0.05
            bias, name = "صاعد", "رأس وكتفين مقلوب"
            evidence = "كتفان متقاربان ورأس أعمق مع خط عنق"
            stop = right[1] - atr * 0.18
            head_neck = _line_value(n1, n2, head[0])
            target = neck_now + max(atr, head_neck - head[1])
        else:
            head_extension = (head[1] - max(left[1], right[1])) / atr
            n1 = _extreme_between(candles, left[0], head[0], kind="low")
            n2 = _extreme_between(candles, head[0], right[0], kind="low")
            if not n1 or not n2 or head_extension < 0.55:
                continue
            neck_now = _line_value(n1, n2, len(candles) - 1)
            confirmed = candles[-1]["close"] < neck_now - atr * 0.05
            bias, name = "هابط", "رأس وكتفين"
            evidence = "كتفان متقاربان ورأس أعلى مع خط عنق"
            stop = right[1] + atr * 0.18
            head_neck = _line_value(n1, n2, head[0])
            target = neck_now - max(atr, head[1] - head_neck)
        confidence = 64 + min(14, int(head_extension * 7)) + max(0, 8 - int(shoulder_diff * 8)) + (10 if confirmed else 0)
        if confirmed:
            evidence += " وتم كسر خط العنق"
        geometry = _geom(
            candles,
            anchors=[(left[0], left[1], "shoulder"), (head[0], head[1], "head"), (right[0], right[1], "shoulder"), (n1[0], n1[1], "neck"), (n2[0], n2[1], "neck")],
            lines=[(n1, n2, "neckline")],
            path=[left, head, right],
            trigger=neck_now,
            stop=stop,
            target=target,
            breakout_index=len(candles) - 1 if confirmed else None,
        )
        candidate = PatternCandidate(name, min(95, confidence), timeframe, bias, evidence, "confirmed" if confirmed else "candidate", geometry)
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
    np = peak_slope / atr
    nt = trough_slope / atr
    latest_width = peaks[-1][1] - troughs[-1][1]
    early_width = peaks[0][1] - troughs[0][1]
    contracting = latest_width > 0 and early_width > 0 and latest_width < early_width * 0.78
    last_i = len(candles) - 1
    upper_now = _line_value(peaks[0], peaks[-1], last_i)
    lower_now = _line_value(troughs[0], troughs[-1], last_i)
    close = candles[-1]["close"]

    name = ""
    bias = "محايد"
    evidence = ""
    confidence = 0
    status = "candidate"
    trigger: float | None = None
    stop: float | None = None
    target: float | None = None

    if abs(np - nt) <= 0.06 and abs(np) >= 0.035:
        if np > 0:
            name, bias = "قناة صاعدة", "صاعد"
            evidence = "قمم وقيعان تتحرك داخل مسارين صاعدين متوازيين"
        else:
            name, bias = "قناة هابطة", "هابط"
            evidence = "قمم وقيعان تتحرك داخل مسارين هابطين متوازيين"
        confidence = 64 + min(18, int(abs(np) * 120))
    elif contracting:
        if np < -0.025 and nt > 0.025:
            name, evidence, confidence = "مثلث متماثل", "قمم هابطة وقيعان صاعدة مع تقلص واضح في النطاق", 68
            if close > upper_now + atr * 0.05:
                bias, status, trigger = "صاعد", "confirmed", upper_now
                target, stop = upper_now + max(atr, early_width), lower_now - atr * 0.12
            elif close < lower_now - atr * 0.05:
                bias, status, trigger = "هابط", "confirmed", lower_now
                target, stop = lower_now - max(atr, early_width), upper_now + atr * 0.12
        elif abs(np) <= 0.03 and nt > 0.035:
            name, bias, evidence, confidence = "مثلث صاعد", "صاعد", "قمم شبه ثابتة وقيعان صاعدة تضغط نحو المقاومة", 67
            if close > upper_now + atr * 0.05:
                status, trigger, target, stop = "confirmed", upper_now, upper_now + max(atr, early_width), lower_now - atr * 0.12
        elif np < -0.035 and abs(nt) <= 0.03:
            name, bias, evidence, confidence = "مثلث هابط", "هابط", "قيعان شبه ثابتة وقمم هابطة تضغط نحو الدعم", 67
            if close < lower_now - atr * 0.05:
                status, trigger, target, stop = "confirmed", lower_now, lower_now - max(atr, early_width), upper_now + atr * 0.12
        elif np > 0.02 and nt > 0.04 and nt > np:
            name, bias, evidence, confidence = "وتد صاعد", "هابط", "قمم وقيعان صاعدة لكن القيعان تتقارب من القمم", 64
            if close < lower_now - atr * 0.05:
                status, trigger, target, stop = "confirmed", lower_now, lower_now - max(atr, early_width), upper_now + atr * 0.12
        elif np < -0.04 and nt < -0.02 and np < nt:
            name, bias, evidence, confidence = "وتد هابط", "صاعد", "قمم وقيعان هابطة لكن القمم تتقارب من القيعان", 64
            if close > upper_now + atr * 0.05:
                status, trigger, target, stop = "confirmed", upper_now, upper_now + max(atr, early_width), lower_now - atr * 0.12
    if not name:
        return None
    if status == "confirmed":
        confidence += 10
        evidence += " مع كسر مؤكد"
    geometry = _geom(
        candles,
        anchors=[(peaks[0][0], peaks[0][1], "upper"), (peaks[-1][0], peaks[-1][1], "upper"), (troughs[0][0], troughs[0][1], "lower"), (troughs[-1][0], troughs[-1][1], "lower")],
        lines=[(peaks[0], peaks[-1], "upper"), (troughs[0], troughs[-1], "lower")],
        trigger=trigger,
        stop=stop,
        target=target,
        breakout_index=last_i if status == "confirmed" else None,
    )
    return PatternCandidate(name, min(94, confidence), timeframe, bias, evidence, status, geometry)


def _rectangle(candles: list[dict[str, float]], *, timeframe: str) -> PatternCandidate | None:
    atr = _atr(candles)
    peaks, troughs = _pivots(candles)
    peaks, troughs = peaks[-4:], troughs[-4:]
    if len(peaks) < 3 or len(troughs) < 3:
        return None
    top = sum(p[1] for p in peaks) / len(peaks)
    bottom = sum(p[1] for p in troughs) / len(troughs)
    if top - bottom < atr * 1.2:
        return None
    if max(abs(p[1] - top) for p in peaks) > atr * 0.55 or max(abs(p[1] - bottom) for p in troughs) > atr * 0.55:
        return None
    close = candles[-1]["close"]
    status, bias, trigger, target, stop = "candidate", "محايد", None, None, None
    if close > top + atr * 0.05:
        status, bias, trigger = "confirmed", "صاعد", top
        target, stop = top + (top - bottom), bottom - atr * 0.12
    elif close < bottom - atr * 0.05:
        status, bias, trigger = "confirmed", "هابط", bottom
        target, stop = bottom - (top - bottom), top + atr * 0.12
    start = min(peaks[0][0], troughs[0][0])
    end = max(peaks[-1][0], troughs[-1][0])
    geometry = _geom(
        candles,
        anchors=[(peaks[-1][0], top, "upper"), (troughs[-1][0], bottom, "lower")],
        lines=[((start, top), (end, top), "upper"), ((start, bottom), (end, bottom), "lower")],
        trigger=trigger,
        stop=stop,
        target=target,
        breakout_index=len(candles) - 1 if status == "confirmed" else None,
    )
    evidence = "تذبذب أفقي بين حد مقاومة وحد دعم واضحين"
    if status == "confirmed":
        evidence += " مع خروج مؤكد من النطاق"
    return PatternCandidate("مستطيل", 66 + (10 if status == "confirmed" else 0), timeframe, bias, evidence, status, geometry)


def _flag_or_pennant(candles: list[dict[str, float]], *, timeframe: str) -> PatternCandidate | None:
    if len(candles) < 24:
        return None
    atr = _atr(candles)
    start = max(0, len(candles) - 22)
    impulse = candles[start:start + 7]
    consolidation = candles[start + 7:]
    if len(consolidation) < 10:
        return None
    impulse_move = impulse[-1]["close"] - impulse[0]["open"]
    if abs(impulse_move) < atr * 2.6:
        return None
    local_peaks, local_troughs = _pivots(consolidation, window=1)
    if len(local_peaks) < 2 or len(local_troughs) < 2:
        return None
    peaks = [(idx + start + 7, price) for idx, price in local_peaks[-3:]]
    troughs = [(idx + start + 7, price) for idx, price in local_troughs[-3:]]
    np = _linear_slope(peaks) / atr
    nt = _linear_slope(troughs) / atr
    bullish_impulse = impulse_move > 0
    early_width = peaks[0][1] - troughs[0][1]
    late_width = peaks[-1][1] - troughs[-1][1]
    contracting = early_width > 0 and late_width > 0 and late_width < early_width * 0.72
    parallel = abs(np - nt) <= 0.08
    if not (contracting or parallel):
        return None
    if bullish_impulse and parallel and np <= 0.04:
        name, bias = "علم صاعد", "صاعد"
    elif (not bullish_impulse) and parallel and np >= -0.04:
        name, bias = "علم هابط", "هابط"
    elif bullish_impulse and contracting:
        name, bias = "راية صاعدة", "صاعد"
    elif (not bullish_impulse) and contracting:
        name, bias = "راية هابطة", "هابط"
    else:
        return None
    last_i = len(candles) - 1
    upper_now = _line_value(peaks[0], peaks[-1], last_i)
    lower_now = _line_value(troughs[0], troughs[-1], last_i)
    close = candles[-1]["close"]
    confirmed = close > upper_now + atr * 0.05 if bullish_impulse else close < lower_now - atr * 0.05
    trigger = upper_now if bullish_impulse else lower_now
    target = trigger + impulse_move if bullish_impulse else trigger + impulse_move
    stop = lower_now - atr * 0.12 if bullish_impulse else upper_now + atr * 0.12
    geometry = _geom(
        candles,
        anchors=[(peaks[0][0], peaks[0][1], "upper"), (peaks[-1][0], peaks[-1][1], "upper"), (troughs[0][0], troughs[0][1], "lower"), (troughs[-1][0], troughs[-1][1], "lower")],
        lines=[(peaks[0], peaks[-1], "upper"), (troughs[0], troughs[-1], "lower")],
        trigger=trigger if confirmed else None,
        stop=stop if confirmed else None,
        target=target if confirmed else None,
        breakout_index=last_i if confirmed else None,
    )
    evidence = "اندفاع واضح تلاه تماسك قصير داخل حدود هندسية"
    if confirmed:
        evidence += " ثم استكمال مؤكد في اتجاه الاندفاع"
    return PatternCandidate(name, 64 + (10 if confirmed else 0), timeframe, bias, evidence, "confirmed" if confirmed else "candidate", geometry)


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
            geometry = _geom(candles, anchors=[(len(candles) - 1, prior_high, "retest")], lines=[((len(candles) - 20, prior_high), (len(candles) - 1, prior_high), "trigger")], trigger=prior_high, target=prior_high + atr * 2.0, stop=prior_high - atr * 0.6, breakout_index=len(candles) - 1)
            return PatternCandidate("كسر وإعادة اختبار", 72, timeframe, "صاعد", "اختراق مقاومة سابقة ثم عودة لاختبارها والثبات فوقها", "confirmed", geometry)
    if min(row["close"] for row in recent[:-1]) < prior_low - atr * 0.12:
        retest_high = max(row["high"] for row in recent)
        if retest_high >= prior_low - atr * 0.30 and last_close <= prior_low:
            geometry = _geom(candles, anchors=[(len(candles) - 1, prior_low, "retest")], lines=[((len(candles) - 20, prior_low), (len(candles) - 1, prior_low), "trigger")], trigger=prior_low, target=prior_low - atr * 2.0, stop=prior_low + atr * 0.6, breakout_index=len(candles) - 1)
            return PatternCandidate("كسر وإعادة اختبار", 72, timeframe, "هابط", "كسر دعم سابق ثم عودة لاختباره والفشل تحته", "confirmed", geometry)
    return None


def _serialize(candidate: PatternCandidate) -> dict[str, Any]:
    return {
        "name": candidate.name,
        "confidence": int(candidate.confidence),
        "timeframe": candidate.timeframe,
        "bias": candidate.bias,
        "evidence": candidate.evidence,
        "status": candidate.status,
        "geometry": candidate.geometry,
    }


def review_market_patterns(frames: Any) -> dict[str, Any]:
    """Review closed-candle patterns and return only geometry tied to real pivots.

    Rendering geometry is intentionally limited to M5 because the displayed
    screenshot is an M5 chart. Higher-timeframe patterns can still support the
    decision card, but are never projected onto an M5 screenshot with guessed X
    coordinates.
    """
    candidates: list[PatternCandidate] = []
    # Keep the original ten-item audit list for backward compatibility.
    checked = [
        "M", "W", "مثلث متماثل", "مثلث صاعد", "مثلث هابط",
        "وتد صاعد", "وتد هابط", "قناة صاعدة", "قناة هابطة", "كسر وإعادة اختبار",
    ]
    extended_checked = checked + [
        "قمة ثلاثية", "قاع ثلاثي", "رأس وكتفين", "رأس وكتفين مقلوب",
        "مستطيل", "علم صاعد", "علم هابط", "راية صاعدة", "راية هابطة",
    ]
    for timeframe, minimum in (("M5", 26), ("M15", 24), ("H1", 24)):
        source = frames.get(timeframe) if isinstance(frames, dict) else None
        candles = _normalize(source)
        if len(candles) < minimum:
            continue
        window = candles[-48:]
        detections = (
            _double_pattern(window, timeframe=timeframe, side="top"),
            _double_pattern(window, timeframe=timeframe, side="bottom"),
            _triple_pattern(window, timeframe=timeframe, side="top"),
            _triple_pattern(window, timeframe=timeframe, side="bottom"),
            _head_shoulders(window, timeframe=timeframe, inverse=False),
            _head_shoulders(window, timeframe=timeframe, inverse=True),
            _channel_or_triangle(window, timeframe=timeframe),
            _rectangle(window, timeframe=timeframe),
            _flag_or_pennant(window, timeframe=timeframe),
            _break_retest(window, timeframe=timeframe),
        )
        candidates.extend(candidate for candidate in detections if candidate is not None)

    timeframe_bonus = {"H1": 5, "M15": 4, "M5": 2}
    status_bonus = {"confirmed": 8, "candidate": 0}
    candidates.sort(
        key=lambda item: (
            item.confidence + timeframe_bonus.get(item.timeframe, 0) + status_bonus.get(item.status, 0),
            item.confidence,
        ),
        reverse=True,
    )
    best = candidates[0] if candidates else None
    accepted = best is not None and best.confidence >= 60

    m5 = [item for item in candidates if item.timeframe == "M5" and item.confidence >= 60]
    overlay: list[PatternCandidate] = []
    seen: set[str] = set()
    for item in m5:
        # v3.61: one closest model only.  The visual source-atlas matcher may
        # later replace this primary choice, but the renderer never receives a
        # stack of competing patterns.
        family = (
            "multi_top_bottom" if item.name in {"M", "W", "قمة ثلاثية", "قاع ثلاثي"}
            else "hs" if "رأس" in item.name
            else "triangle_wedge" if any(word in item.name for word in ("مثلث", "وتد"))
            else item.name
        )
        if family in seen:
            continue
        overlay.append(item)
        seen.add(family)
        if len(overlay) >= 1:
            break

    return {
        "available": accepted,
        "pattern_type": best.name if accepted else "لا يوجد",
        "pattern_confidence": best.confidence if accepted else 0,
        "pattern_timeframe": best.timeframe if accepted else "",
        "pattern_bias": best.bias if accepted else "محايد",
        "pattern_status": best.status if accepted else "none",
        "pattern_evidence": best.evidence if accepted else "لم يكتمل نموذج هندسي بشروط كافية",
        "checked_patterns": checked,
        "extended_checked_patterns": extended_checked,
        "overlay_patterns": [_serialize(item) for item in overlay],
        "candidates": [_serialize(item) for item in candidates[:6]],
    }
