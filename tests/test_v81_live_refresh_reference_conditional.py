from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v81_home_uses_live_refresh_without_image_input():
    html = (ROOT / "app/templates/index.html").read_text(encoding="utf-8")
    first = html.split("{% if result %}", 1)[0]
    assert 'action="/refresh"' in first
    assert 'id="image-input"' not in first
    assert "تحديث الشارت" in first
    assert "مراجعة النماذج والذاكرة المرجعية" in first


def test_v81_conditional_is_not_rendered_as_watch():
    html = (ROOT / "app/templates/index.html").read_text(encoding="utf-8")
    assert "result.draw_mode == 'conditional'" in html
    assert "شراء مشروط" in html
    assert "بيع مشروط" in html


def test_v81_market_only_entrypoint_and_reference_gate_exist():
    analyzer = (ROOT / "app/services/analyzer.py").read_text(encoding="utf-8")
    assert "def analyze_market(" in analyzer
    assert "def _run_reference_review_v81(" in analyzer
    assert "reference_reviewed" in analyzer
    assert "reference_score" in analyzer
    assert "_candidate_pattern_plan_v81" in analyzer


def test_v81_refresh_route_exists():
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert '@app.post("/refresh"' in main
    assert "analyze_market" in main


def test_pattern_engine_is_still_single_deterministic_engine():
    analyzer = (ROOT / "app/services/analyzer.py").read_text(encoding="utf-8")
    assert "review_market_patterns" in analyzer
    assert "reference_scenario_engine" in analyzer or "compat_smoke_only" in analyzer
