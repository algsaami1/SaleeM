from __future__ import annotations

import json
from pathlib import Path

from app.engine.pattern_engine import review_market_patterns
from app.services.analyzer import (
    _apply_level_pressure,
    _build_market_reading_comment,
    _choose_direction,
)
from app.services.knowledge import KnowledgeBase


def _candle(value: float, index: int) -> dict[str, float | str]:
    return {
        "time": f"2026-07-27T00:{index:02d}:00",
        "open": value + 0.12,
        "high": value + 0.30,
        "low": value - 0.30,
        "close": value,
    }


def test_closed_candle_pattern_review_detects_confirmed_double_top():
    rows = [_candle(100 + (index % 4) * 0.1, index) for index in range(20)]
    sequence = [100.2, 100.8, 101.8, 103.0, 104.8, 103.8, 102.2, 101.0,
                102.0, 103.4, 104.7, 103.7, 102.0, 100.5, 99.8, 99.2]
    rows.extend(_candle(value, 20 + index) for index, value in enumerate(sequence))

    review = review_market_patterns({"M5": rows, "M15": rows, "H1": rows})

    assert review["available"] is True
    assert review["pattern_type"] == "قمتان"
    assert review["pattern_bias"] == "هابط"
    assert review["pattern_confidence"] >= 70
    assert len(review["checked_patterns"]) == 10


def test_lower_frames_override_old_bullish_context_for_current_move():
    candles = [_candle(110 - index * 0.45, index) for index in range(30)]
    summary = {
        "frames": {
            "H4": {"direction": "صاعد", "score": 0.8, "confidence": 80},
            "H1": {"direction": "صاعد", "score": 0.5, "confidence": 75},
            "M15": {"direction": "هابط", "score": -1.0, "confidence": 82},
            "M5": {"direction": "هابط", "score": -1.2, "confidence": 86},
        },
        "warnings": [],
    }

    direction, buy, sell = _choose_direction({}, candles, 62, 38, summary)

    assert direction == "هابط"
    assert sell > buy
    assert sell <= 68  # counter-trend move remains capped, not falsely certain


def test_level_pressure_cannot_create_bullish_direction_from_neutral():
    candles = [_candle(100 + index * 0.01, index) for index in range(20)]
    direction, buy, sell, _context = _apply_level_pressure(
        candles,
        100.2,
        [{"price": 100.1, "strength": 90, "touches": 4, "source": "market"}],
        [],
        "غير واضح",
        50,
        50,
    )

    assert direction == "غير واضح"
    assert max(buy, sell) <= 55


def test_knowledge_context_is_valid_json_even_when_bounded(tmp_path: Path):
    (tmp_path / "rules.json").write_text(
        json.dumps({"rules": ["قاعدة" * 200 for _ in range(30)]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("شرح نموذج " * 500, encoding="utf-8")
    (tmp_path / "double_top.svg").write_text("<svg></svg>", encoding="utf-8")

    context = KnowledgeBase(tmp_path).prompt_context(max_chars=1800)
    payload = json.loads(context)

    assert isinstance(payload, dict)
    assert "reference_images" in payload
    assert len(context) <= 1800


def test_market_reading_comment_changes_with_pattern_and_frame_evidence(monkeypatch):
    monkeypatch.setattr(
        "app.services.analyzer.detect_market_zone_presence",
        lambda _analysis: {"order_block": False, "fvg": False},
    )
    base = {
        "direction": "هابط",
        "current_price": 100.0,
        "support_levels": [{"price": 98.5}],
        "resistance_levels": [{"price": 102.0}],
        "candles": [_candle(105 - index * 0.3, index) for index in range(20)],
        "frame_directions": {
            "H4": {"direction": "صاعد"},
            "H1": {"direction": "صاعد"},
            "M15": {"direction": "هابط"},
            "M5": {"direction": "هابط"},
        },
    }
    without_pattern = _build_market_reading_comment({**base, "pattern_type": "لا يوجد"})
    with_pattern = _build_market_reading_comment(
        {**base, "pattern_type": "قمتان", "pattern_confidence": 82}
    )

    assert without_pattern != with_pattern
    assert "M15 وM5" in with_pattern
    assert "قمتان" in with_pattern
    assert len(with_pattern) <= 220
