from app.engine.renderer import (
    _build_reference_visual_scene,
    _reference_setup_status,
    _reference_trade_lifecycle,
    _resolve_reference_trade_plan,
)


def _candles(count=96, start=4380.0):
    out=[]
    price=start
    for i in range(count):
        close=price + (0.15 if i % 3 else -0.08)
        out.append({"time":f"2026-08-11 {8+i//12:02d}:{(i*5)%60:02d}:00","open":price,"high":max(price,close)+0.2,"low":min(price,close)-0.2,"close":close})
        price=close
    return out


def _analysis(*, pattern_status="candidate", current=4386.0, action_confirmed=False):
    side="sell"
    return {
        "candles": _candles(),
        "reconstructed_market_chart": True,
        "current_price": current,
        "pattern_type": "M",
        "pattern_status": pattern_status,
        "pattern_confidence": 86,
        "reference_match_score": 86,
        "reference_visual_score": 86,
        "visual_template_id": "multiple_tops",
        "pattern_bias": "هابط",
        "pattern_overlays": [{
            "name":"M","status":pattern_status,"bias":"هابط","confidence":86,
            "geometry":{"window_size":96,"anchors":[],"lines":[],"path":[],"trigger":4389.2,"stop":4390.93,"target":4369.92,"breakout_index":80 if pattern_status=="confirmed" else None},
        }],
        "action_summary": {"primary_side":side if action_confirmed else "wait","is_confirmed":action_confirmed},
        "entry":4389.2,"stop_loss":4390.93,"target_1":4369.92,
    }


def test_candidate_is_conditional_entry_cancel_target():
    a=_analysis(pattern_status="candidate", current=4386.0, action_confirmed=False)
    plan=_resolve_reference_trade_plan(a)
    life=_reference_trade_lifecycle(a, plan)
    assert plan["confirmed"] is False
    assert plan["pattern_confirmed"] is False
    assert life["state"] == "conditional"
    assert _reference_setup_status(a) == "CANDIDATE"


def test_confirmed_pattern_without_execution_gate_is_watch_not_fake_confirmed_trade():
    a=_analysis(pattern_status="confirmed", current=4386.0, action_confirmed=False)
    plan=_resolve_reference_trade_plan(a)
    life=_reference_trade_lifecycle(a, plan)
    assert plan["confirmed"] is False
    assert plan["pattern_confirmed"] is True
    assert life["state"] == "conditional"
    assert _reference_setup_status(a) == "PATTERN CONFIRMED · WATCH"


def test_execution_confirmed_plan_target_hit_is_not_redrawn_as_new_entry():
    a=_analysis(pattern_status="confirmed", current=4368.0, action_confirmed=True)
    plan=_resolve_reference_trade_plan(a)
    life=_reference_trade_lifecycle(a, plan)
    assert life["state"] == "target_hit"
    assert _reference_setup_status(a) == "TARGET HIT"
    scene=_build_reference_visual_scene(a)
    assert scene["trade_lifecycle"]["state"] == "target_hit"
    assert scene["future_space_ratio"] >= 0.20


def test_execution_confirmed_plan_invalidated_is_not_redrawn_as_new_entry():
    a=_analysis(pattern_status="confirmed", current=4392.0, action_confirmed=True)
    plan=_resolve_reference_trade_plan(a)
    life=_reference_trade_lifecycle(a, plan)
    assert life["state"] == "invalidated"
    assert _reference_setup_status(a) == "SETUP INVALIDATED"


def test_candidate_already_beyond_target_is_expired_not_target_hit():
    a=_analysis(pattern_status="candidate", current=4368.0, action_confirmed=False)
    plan=_resolve_reference_trade_plan(a)
    life=_reference_trade_lifecycle(a, plan)
    assert life["state"] == "expired"
    assert _reference_setup_status(a) == "SETUP EXPIRED"
