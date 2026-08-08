from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from app.engine.renderer import render_share_snapshot
from app.services.analyzer import _merge_reference_pattern_review

ROOT = Path(__file__).resolve().parents[1]


def _candidate(name: str, confidence: int, bias: str = "هابط") -> dict:
    return {
        "name": name,
        "confidence": confidence,
        "timeframe": "M5",
        "bias": bias,
        "evidence": "هندسة حقيقية على M5",
        "status": "candidate",
        "geometry": {
            "window_size": 30,
            "anchors": [
                {"index": 8, "price": 4350.0, "role": "pivot"},
                {"index": 14, "price": 4350.2, "role": "pivot"},
                {"index": 21, "price": 4350.1, "role": "pivot"},
            ],
            "lines": [],
            "path": [[8, 4350.0], [14, 4350.2], [21, 4350.1]],
            "trigger": 4345.0,
            "stop": 4351.0,
            "target": 4339.0,
            "breakout_index": None,
        },
    }


def test_source_atlas_and_raw_library_are_bundled():
    source_dir = ROOT / "knowledge" / "10_reference_images" / "source_models"
    assert (source_dir / "source_model_atlas.webp").exists()
    assert (source_dir / "source_model_catalog.json").exists()
    raw = [
        path
        for path in (source_dir / "raw").iterdir()
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    ]
    assert len(raw) == 82


def test_visual_source_match_selects_one_verified_m5_pattern():
    triple = _candidate("قمة ثلاثية", 72)
    triangle = _candidate("مثلث هابط", 80)
    review = {
        "available": True,
        "pattern_type": "مثلث هابط",
        "pattern_confidence": 80,
        "pattern_timeframe": "M5",
        "pattern_bias": "هابط",
        "pattern_status": "candidate",
        "pattern_evidence": "مثلث",
        "checked_patterns": ["M", "W"],
        "extended_checked_patterns": ["M", "W", "قمة ثلاثية"],
        "overlay_patterns": [triangle],
        "candidates": [triangle, triple],
    }
    visual = {
        "matched": True,
        "pattern_family": "triple_top_bottom",
        "source_reference_id": "archive_2_06",
        "visual_score": 88,
        "bias": "هابط",
        "evidence": "ثلاث قمم متقاربة عند مقاومة واحدة",
    }

    merged = _merge_reference_pattern_review(review, visual)
    assert merged["pattern_type"] == "قمة ثلاثية"
    assert merged["reference_source_id"] == "archive_2_06"
    assert merged["reference_match_status"] == "matched_and_verified"
    assert len(merged["overlay_patterns"]) == 1
    assert merged["overlay_patterns"][0]["name"] == "قمة ثلاثية"


def test_visual_match_never_invents_geometry_when_m5_does_not_verify_it():
    triangle = _candidate("مثلث هابط", 78)
    review = {
        "available": True,
        "pattern_type": "مثلث هابط",
        "pattern_confidence": 78,
        "pattern_timeframe": "M5",
        "pattern_bias": "هابط",
        "pattern_status": "candidate",
        "pattern_evidence": "مثلث",
        "checked_patterns": ["M", "W"],
        "extended_checked_patterns": ["M", "W", "مثلث هابط"],
        "overlay_patterns": [triangle],
        "candidates": [triangle],
    }
    visual = {
        "matched": True,
        "pattern_family": "triple_top_bottom",
        "source_reference_id": "archive_2_06",
        "visual_score": 91,
        "bias": "هابط",
        "evidence": "تشابه بصري فقط",
    }

    merged = _merge_reference_pattern_review(review, visual)
    assert merged["pattern_type"] == "مثلث هابط"
    assert merged["reference_match_status"] == "visual_match_not_verified_by_m5_geometry"
    assert len(merged["overlay_patterns"]) == 1
    assert merged["overlay_patterns"][0]["name"] == "مثلث هابط"


def test_share_snapshot_reserves_rule_panel_below_chart():
    chart = Image.new("RGB", (1200, 600), "white")
    buf = io.BytesIO()
    chart.save(buf, format="PNG")
    analysis = {
        "draw_mode": "watch",
        "direction": "هابط",
        "higher_timeframe_direction": "هابط",
        "current_movement": "هابط",
        "pattern_type": "قمة ثلاثية",
        "pattern_status": "candidate",
        "pattern_reference_source_id": "archive_2_06",
        "pattern_reference_rule": "ثلاث قمم متقاربة عند مقاومة واحدة مع خط عنق واضح.",
        "pattern_reference_visual_evidence": "تكرار القمم والرفض من نفس المنطقة.",
        "pattern_confidence": 76,
        "current_price": 4344.92,
        "support_levels": [{"price": 4342.60, "strength": 80}],
        "resistance_levels": [{"price": 4348.80, "strength": 82}],
        "decision_zone": {},
        "rule_check": {"match_percent": 75},
        "action_summary": {
            "code": "watch",
            "primary_side": "wait",
            "is_confirmed": False,
            "title": "مراقبة",
            "instruction": "بانتظار تأكيد النموذج",
            "badge": "مراقبة",
        },
    }
    png = render_share_snapshot(analysis, buf.getvalue())
    with Image.open(io.BytesIO(png)) as result:
        assert result.width >= 1200
        # Header + chart + the new rule panel + action row + margins.
        assert result.height > 1200


def test_v361_spec_states_rule_footer_and_single_model():
    spec = (ROOT / "docs" / "SALEEM_PATTERN_MATCHING_OVERLAY_SPEC_V361.md").read_text(encoding="utf-8")
    assert "نموذج واحد فقط" in spec
    assert "سهم التوقع" in spec
    assert "أسفل الشارت مباشرة" in spec
