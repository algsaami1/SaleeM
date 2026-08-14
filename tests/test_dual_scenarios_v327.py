from __future__ import annotations

from app.services.analyzer import (
    _enrich_dual_scenarios,
    _scalp_targets,
)


def _candles(start: float = 100.0, count: int = 30) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    price = start
    for index in range(count):
        close = price + (0.18 if index % 3 else -0.08)
        rows.append(
            {
                "time": f"2026-07-30T10:{index:02d}:00",
                "open": price,
                "high": max(price, close) + 0.16,
                "low": min(price, close) - 0.16,
                "close": close,
            }
        )
        price = close
    return rows


def _analysis() -> dict:
    candles = _candles()
    current = float(candles[-1]["close"])
    return {
        "candles": candles,
        "current_price": current,
        "market_last_close": current,
        "buy_probability": 62,
        "sell_probability": 38,
        "market_status": "active",
        "market_status_label": "السوق نشط",
        "current_movement": "صاعد",
        "pattern_type": "W",
        "pattern_confidence": 76,
        "pattern_bias": "صاعد",
        "support_levels": [
            {"price": round(current - 0.45, 2), "strength": 79, "touches": 3},
            {"price": round(current - 1.20, 2), "strength": 72, "touches": 2},
        ],
        "resistance_levels": [
            {"price": round(current + 0.40, 2), "strength": 74, "touches": 3},
            {"price": round(current + 1.10, 2), "strength": 80, "touches": 4},
        ],
        "confirmed_limit_swings": {
            "troughs": [
                {
                    "price": round(current - 1.55, 2),
                    "strength": 83,
                    "touches": 3,
                    "timeframe": "H1",
                }
            ],
            "peaks": [
                {
                    "price": round(current + 1.65, 2),
                    "strength": 85,
                    "touches": 3,
                    "timeframe": "H1",
                }
            ],
        },
        "frame_directions": {
            "H4": {"direction": "صاعد"},
            "H1": {"direction": "صاعد"},
            "M15": {"direction": "صاعد"},
            "M5": {"direction": "صاعد"},
        },
    }


def test_every_analysis_contains_independent_buy_and_sell_scenarios(monkeypatch):
    monkeypatch.setenv("SALEEM_SCALP_POINT_SIZE", "0.10")
    result = _enrich_dual_scenarios(_analysis())

    assert result["buy_scenario_details"]["side"] == "buy"
    assert result["sell_scenario_details"]["side"] == "sell"
    assert result["buy_scenario_details"]["trigger_price"] is not None
    assert result["sell_scenario_details"]["trigger_price"] is not None
    assert result["sell_scenario_details"]["state"] in {"مؤكد", "مراقبة"}
    assert result["dual_scenario_renderer_status"] == "cards-below-image-active"


def test_higher_timeframe_bullish_context_reduces_but_never_removes_sell_plan():
    result = _enrich_dual_scenarios(_analysis())
    sell = result["sell_scenario_details"]

    assert sell["score"] == 38
    assert sell["label"] == "بيع"
    assert sell["blocking_reasons"]
    assert any("H4" in reason or "الفريمات الكبيرة" in reason for reason in sell["blocking_reasons"])


def test_five_and_ten_point_targets_use_configurable_point_size(monkeypatch):
    monkeypatch.setenv("SALEEM_SCALP_POINT_SIZE", "0.10")
    analysis = _analysis()
    analysis["resistance_levels"] = []
    analysis["confirmed_limit_swings"] = {"troughs": [], "peaks": []}

    targets = _scalp_targets(analysis, direction="صاعد", entry=100.0)

    assert targets["raw_5_point_target"] == 100.5
    assert targets["raw_10_point_target"] == 101.0
    assert targets["quick_target"] == 100.5
    assert targets["extended_target"] == 101.0


def test_real_resistance_before_five_points_caps_quick_target(monkeypatch):
    monkeypatch.setenv("SALEEM_SCALP_POINT_SIZE", "0.10")
    analysis = _analysis()
    analysis["resistance_levels"] = [{"price": 100.3, "strength": 85, "touches": 4}]
    analysis["confirmed_limit_swings"] = {"troughs": [], "peaks": []}

    targets = _scalp_targets(analysis, direction="صاعد", entry=100.0)

    assert targets["quick_target"] == 100.3
    assert targets["quick_target_basis"] == "مستوى سوق قبل الهدف"
    assert targets["extended_target"] == 101.0


def test_probable_peak_and_trough_are_exposed_for_later_design():
    result = _enrich_dual_scenarios(_analysis())

    assert result["most_probable_peak"] is not None
    assert result["most_probable_trough"] is not None
    assert result["most_probable_peak"]["price"] > result["current_price"]
    assert result["most_probable_trough"]["price"] < result["current_price"]


def test_dual_cards_can_be_conditional_while_overall_decision_waits_for_confirmation():
    result = _enrich_dual_scenarios(_analysis())

    assert result["buy_scenario_details"]["state"] == "مشروط"
    assert result["dual_scenario_decision"]["label"] == "القرار الآن: مراقبة"
    assert "سيناريو الشراء" not in result["dual_scenario_decision"]["label"]
