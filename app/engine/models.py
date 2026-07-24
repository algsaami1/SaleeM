from __future__ import annotations
from typing import Any


def clamp_percent(value: Any, low: int = 5, high: int = 95) -> int:
    try:
        return max(low, min(high, int(round(float(value)))))
    except (TypeError, ValueError):
        return 50


def normalize_analysis(data: dict[str, Any]) -> dict[str, Any]:
    """تطبيع احتياطي غير منحاز عند استخدام هذا المحرك مستقبلًا."""
    buy_raw = clamp_percent(data.get("buy_probability", 50))
    sell_raw = clamp_percent(data.get("sell_probability", 50))
    total = max(1, buy_raw + sell_raw)
    buy = max(5, min(95, int(round(buy_raw * 100 / total))))
    sell = 100 - buy
    data["buy_probability"] = buy
    data["sell_probability"] = sell
    data["note"] = " ".join(str(data.get("note", "")).split())[:82]
    data["direction"] = data.get("direction", "غير واضح")
    data["scenario"] = str(data.get("scenario", "غير واضح"))[:70]
    return data
