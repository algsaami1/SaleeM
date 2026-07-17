from __future__ import annotations
from typing import Any


def clamp_percent(value: Any, low: int = 5, high: int = 95) -> int:
    try:
        return max(low, min(high, int(round(float(value)))))
    except (TypeError, ValueError):
        return 50


def normalize_analysis(data: dict[str, Any]) -> dict[str, Any]:
    buy = clamp_percent(data.get("buy_probability", 50))
    sell = 100 - buy
    data["buy_probability"] = buy
    data["sell_probability"] = sell
    data["note"] = " ".join(str(data.get("note", "")).split())[:82]
    data["direction"] = data.get("direction", "غير واضح")
    data["scenario"] = str(data.get("scenario", "غير واضح"))[:46]
    return data
