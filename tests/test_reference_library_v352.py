from __future__ import annotations

from app.engine.pattern_engine import review_market_patterns
from app.engine.reference_matcher import load_reference_library, match_reference_scenarios


def _candle(value: float, index: int) -> dict[str, float | str]:
    return {
        "time": f"2026-08-09T12:{index:02d}:00",
        "open": value + 0.12,
        "high": value + 0.30,
        "low": value - 0.30,
        "close": value,
    }


def _double_top_rows() -> list[dict[str, float | str]]:
    rows = [_candle(100 + (index % 4) * 0.1, index) for index in range(20)]
    sequence = [
        100.2, 100.8, 101.8, 103.0, 104.8, 103.8, 102.2, 101.0,
        102.0, 103.4, 104.7, 103.7, 102.0, 100.5, 99.8, 99.2,
    ]
    rows.extend(_candle(value, 20 + index) for index, value in enumerate(sequence))
    return rows


def test_reference_library_contains_extracted_rule_families_and_no_fabrication_marks():
    library = load_reference_library()
    refs = library["references"]
    assert len(refs) >= 40
    ids = {item["id"] for item in refs}
    assert {"REV_W_BULL", "REV_M_BEAR", "SMC_CHOCH_BULL", "PA_BREAK_RETEST_BEAR"}.issubset(ids)
    cup = next(item for item in refs if item["id"] == "REV_CUP_HANDLE_BULL")
    assert cup["implementation"] == "library_only_no_fabrication"


def test_confirmed_m_maps_to_strong_reference_and_prefers_m5_for_chart_match():
    rows = _double_top_rows()
    frames = {"M5": rows, "M15": rows, "H1": rows, "H4": rows}
    pattern_review = review_market_patterns(frames)
    review = match_reference_scenarios(frames, pattern_review)
    primary = review["primary_match"]
    assert primary["reference_id"] == "REV_M_BEAR"
    assert primary["candidate_timeframe"] == "M5"
    assert primary["score"] >= 78
    assert primary["execution_eligible"] is True
    assert review["overlay_patterns"][0]["reference_id"] == "REV_M_BEAR"


def test_reference_matcher_never_creates_overlay_without_deterministic_pattern_geometry():
    rows = [_candle(100 + index * 0.01, index) for index in range(36)]
    frames = {"M5": rows, "M15": rows, "H1": rows, "H4": rows}
    pattern_review = {
        "available": False,
        "candidates": [],
        "overlay_patterns": [],
    }
    review = match_reference_scenarios(frames, pattern_review)
    assert review["overlay_patterns"] == []


def test_reference_ranked_overlays_remain_m5_and_max_two():
    rows = _double_top_rows()
    frames = {"M5": rows, "M15": rows, "H1": rows, "H4": rows}
    review = match_reference_scenarios(frames, review_market_patterns(frames))
    assert len(review["overlay_patterns"]) <= 2
    assert all(item["timeframe"] == "M5" for item in review["overlay_patterns"])
    assert all(int(item["reference_match_score"]) >= 68 for item in review["overlay_patterns"])
