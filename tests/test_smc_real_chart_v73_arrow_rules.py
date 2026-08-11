from PIL import Image, ImageDraw

import app.engine.renderer as renderer
from app.engine.reference_scenario_engine import _fvg, _order_blocks, _structure_events
from app.services.analyzer import _apply_scenario_freshness_guard


def _price_y(price: float) -> int:
    # 4400 -> 100, 4380 -> 700
    return int(round(100 + (4400.0 - float(price)) * 30.0))


def _confirmed_analysis(current=4394.0):
    return {
        "current_price": current,
        "entry": 4390.0,
        "stop_loss": 4387.0,
        "target_1": 4393.0,
        "target_2": 4396.0,
        "target_3": 4399.0,
        "draw_mode": "confirmed",
        "action_summary": {"primary_side": "buy", "is_confirmed": True, "code": "buy"},
    }


def test_v73_confirmed_plan_exposes_tp1_tp2_tp3():
    plan = renderer._resolve_reference_trade_plan(_confirmed_analysis())
    assert plan is not None
    assert plan["source"] == "execution"
    assert plan["targets"] == [4393.0, 4396.0, 4399.0]
    assert plan["entry"] == 4390.0


def test_v73_confirmed_plan_stays_active_after_tp1_and_completes_at_tp3():
    analysis = _confirmed_analysis(current=4394.0)
    state = renderer._reference_trade_lifecycle(analysis)
    assert state["state"] == "active"
    assert state["targets_reached"] == 1

    analysis["current_price"] = 4400.0
    state = renderer._reference_trade_lifecycle(analysis)
    assert state["state"] == "target_hit"
    assert state["targets_reached"] == 3


def test_v73_freshness_guard_keeps_confirmed_plan_through_partial_targets():
    candles = [
        {"open": 4388 + i * 0.1, "high": 4388.5 + i * 0.1, "low": 4387.5 + i * 0.1, "close": 4388.2 + i * 0.1}
        for i in range(30)
    ]
    analysis = {
        **_confirmed_analysis(current=4394.0),
        "candles": candles,
        "direction": "صاعد",
        "higher_timeframe_direction": "صاعد",
        "buy_scenario_details": {},
        "sell_scenario_details": {},
        "show_targets_as_active": True,
    }
    _apply_scenario_freshness_guard(analysis)
    assert analysis["scenario_expired"] is False
    assert analysis["scenario_freshness"] == "progress"
    assert analysis["scenario_targets_reached"] == 1

    analysis["current_price"] = 4400.0
    _apply_scenario_freshness_guard(analysis)
    assert analysis["scenario_expired"] is True
    assert analysis["draw_mode"] == "watch"


def test_v73_primary_arrow_starts_exactly_at_entry_and_has_break_retest_bend(monkeypatch):
    analysis = _confirmed_analysis()
    captured = []
    original = renderer._recon_arrow

    def spy(draw, points, color, *, width=3, dashed=False):
        captured.append((points, dashed))
        return original(draw, points, color, width=width, dashed=dashed)

    projected = []
    def projected_spy(draw, **kwargs):
        projected.append(kwargs)

    monkeypatch.setattr(renderer, "_recon_arrow", spy)
    monkeypatch.setattr(renderer, "_draw_reference_projected_candles", projected_spy)

    image = Image.new("RGBA", (1600, 900), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    renderer._draw_reference_trade_plan(
        draw, analysis, _price_y, (58, 112, 1418, 718), 1010, renderer._font(14, True, True)
    )

    plan_arrows = [points for points, _ in captured if len(points) == 4]
    assert len(plan_arrows) == 1
    points = plan_arrows[0]
    assert points[0][1] == _price_y(4390.0)  # ENTRY origin
    assert points[1][1] != points[2][1]      # deliberate break/retest bend
    assert projected and projected[0]["targets"] == [4393.0, 4396.0, 4399.0]


def test_v73_dual_paths_are_watch_only_and_each_starts_at_its_entry(monkeypatch):
    analysis = {
        "draw_mode": "watch",
        "action_summary": {"primary_side": "wait", "is_confirmed": False, "code": "watch"},
        "decision_zone": {"active": True},
        "dual_scenario_decision": {"score_gap": 2},
        "buy_scenario_details": {"trigger_price": 4392.0, "display_target": 4398.0},
        "sell_scenario_details": {"trigger_price": 4388.0, "display_target": 4382.0},
    }
    captured = []
    original = renderer._recon_arrow

    def spy(draw, points, color, *, width=3, dashed=False):
        captured.append((points, dashed))
        return original(draw, points, color, width=width, dashed=dashed)

    monkeypatch.setattr(renderer, "_recon_arrow", spy)
    image = Image.new("RGBA", (1600, 900), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    assert renderer._draw_reference_dual_watch_paths(
        draw, analysis, _price_y, (58, 112, 1418, 718), 1010, renderer._font(14, True, True)
    ) is True
    assert len(captured) == 2
    starts = sorted(points[0][1] for points, _ in captured)
    assert starts == sorted([_price_y(4392.0), _price_y(4388.0)])
    assert all(dashed for _, dashed in captured)


def test_v73_smc_geometry_carries_anchor_price_and_reason():
    candles = [
        {"open": 10.0, "high": 10.3, "low": 9.7, "close": 10.1},
        {"open": 10.2, "high": 10.4, "low": 9.9, "close": 10.0},
        {"open": 10.2, "high": 11.7, "low": 10.1, "close": 11.5},
        {"open": 11.5, "high": 11.7, "low": 11.2, "close": 11.4},
        {"open": 11.4, "high": 11.5, "low": 10.8, "close": 10.9},
        {"open": 10.9, "high": 11.0, "low": 10.0, "close": 10.1},
        {"open": 10.1, "high": 10.2, "low": 9.3, "close": 9.5},
    ]
    gaps = _fvg(candles)
    assert gaps
    assert all(item.get("anchor_index") is not None for item in gaps)
    assert all(item.get("price_level") is not None for item in gaps)
    assert all(item.get("validation_reason") for item in gaps)

    blocks = _order_blocks(candles)
    assert blocks
    assert all(item.get("anchor_index") is not None for item in blocks)
    assert all(item.get("price_level") is not None for item in blocks)
    assert all(item.get("validation_reason") for item in blocks)

    # Structure events may be absent in this tiny synthetic series, but whenever
    # one exists it must carry the same audit triple.
    for item in _structure_events(candles):
        assert item.get("anchor_index") is not None
        assert item.get("price_level") is not None
        assert item.get("validation_reason")
