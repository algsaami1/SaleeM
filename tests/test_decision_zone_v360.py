from __future__ import annotations

import io

from PIL import Image

from app.engine.renderer import render_share_snapshot
from app.services.analyzer import _build_action_summary, _build_decision_zone, _build_rule_check


def _volatile_m5_candles() -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    price = 4344.70
    for index in range(20):
        open_ = price + (0.15 if index % 2 else -0.10)
        close = open_ + (0.40 if index % 3 else -0.35)
        rows.append(
            {
                "open": open_,
                "high": max(open_, close) + 0.55,
                "low": min(open_, close) - 0.55,
                "close": close,
            }
        )
        price = close
    return rows


def _cluster_analysis() -> dict:
    return {
        "current_price": 4344.92,
        "candles": _volatile_m5_candles(),
        "support_levels": [
            {"price": 4344.68, "strength": 79},
            {"price": 4344.37, "strength": 72},
            {"price": 4340.20, "strength": 83},
        ],
        "resistance_levels": [
            {"price": 4345.54, "strength": 81},
            {"price": 4348.70, "strength": 77},
        ],
    }


def test_close_mixed_levels_are_merged_into_one_decision_zone():
    zone = _build_decision_zone(_cluster_analysis())
    assert zone["active"] is True
    assert zone["low"] == 4344.37
    assert zone["high"] == 4345.54
    assert zone["merged_supports"] == [4344.68, 4344.37]
    assert zone["merged_resistances"] == [4345.54]
    assert zone["down_trigger"] < zone["low"]
    assert zone["up_trigger"] > zone["high"]


def test_decision_zone_blocks_directional_trade_even_if_scenario_claims_confirmed():
    analysis = _cluster_analysis()
    analysis.update(
        {
            "market_status": "active",
            "draw_mode": "confirmed",
            "decision_zone": _build_decision_zone(analysis),
            "buy_scenario_details": {"state_code": "confirmed", "score": 82},
            "sell_scenario_details": {"state_code": "watch", "score": 41},
        }
    )
    summary = _build_action_summary(analysis)
    assert summary["code"] == "watch_zone"
    assert summary["title"] == "مراقبة — منطقة قرار"
    assert summary["primary_side"] == "wait"
    assert summary["is_confirmed"] is False
    assert "إغلاق M5" in summary["instruction"]


def test_strict_rule_stops_at_first_missing_gate_without_alternative_trade():
    analysis = {
        "market_status": "active",
        "draw_mode": "confirmed",
        "decision_zone": {"active": False},
        "rule_check": {
            "all_pass": False,
            "first_missing": "ينقص تفعيل M15/M5 بإغلاق M5",
        },
        "buy_scenario_details": {
            "state_code": "confirmed",
            "score": 83,
            "trigger_price": 4350.0,
        },
        "sell_scenario_details": {"state_code": "watch", "score": 35},
    }
    summary = _build_action_summary(analysis)
    assert summary["code"] == "no_signal"
    assert summary["title"] == "الإشارة غير متوفرة حالياً"
    assert summary["primary_side"] == "wait"
    assert summary["trigger"] is None
    assert "توقف" in summary["instruction"]


def test_rule_check_requires_h4_h1_alignment_75_percent_and_valid_location():
    analysis = {
        "higher_timeframe_direction": "صاعد",
        "entry_kind": "اختراق",
        "support_levels": [{"price": 4340.0}],
        "resistance_levels": [{"price": 4350.0}],
        "decision_zone": {"active": False},
        "confirmation_evidence": {
            "higher_frames_aligned": True,
            "alignment": 80,
            "m15_m5_aligned": True,
            "closed_m5_confirmed": True,
            "geometry_valid": True,
        },
    }
    check = _build_rule_check(analysis)
    assert check["all_pass"] is True

    analysis["confirmation_evidence"]["alignment"] = 70
    check = _build_rule_check(analysis)
    assert check["all_pass"] is False
    assert check["first_missing"] == "الاتجاه العام غير واضح"


def test_share_snapshot_keeps_chart_aspect_ratio_and_adds_decision_panels():
    chart = Image.new("RGB", (1200, 600), (248, 250, 252))
    buf = io.BytesIO()
    chart.save(buf, format="PNG")

    analysis = _cluster_analysis()
    analysis.update(
        {
            "decision_zone": _build_decision_zone(analysis),
            "higher_timeframe_direction": "مختلط",
            "current_movement": "عرضي",
            "pattern_type": "لا يوجد",
            "trade_probability": 58,
            "action_summary": {
                "code": "watch_zone",
                "title": "مراقبة — منطقة قرار",
                "instruction": "انتظر إغلاق M5 خارج المنطقة",
                "strength": 58,
                "primary_side": "wait",
                "is_confirmed": False,
            },
        }
    )
    output = render_share_snapshot(analysis, buf.getvalue())
    with Image.open(io.BytesIO(output)) as image:
        assert image.format == "PNG"
        assert image.width >= 1200
        assert image.height > 600
        # The embedded chart is not cropped; the saved result only adds panels.
        assert image.height >= 600 + 360 + 270
