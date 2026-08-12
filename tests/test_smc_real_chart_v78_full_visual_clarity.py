from pathlib import Path

from app.engine import renderer


def test_v78_uses_single_full_canvas_and_no_compact_css():
    assert renderer._reconstructed_dimensions({}) == (1920, 1080)
    css = Path('app/static/style.css').read_text()
    assert 'V7.8 — FULL VISUAL CLARITY ONLY' in css
    assert 'v3.73 COMPACT CHART + REAL PAN/ZOOM' not in css
    assert 'aspect-ratio:16 / 9' in css


def test_v78_render_window_is_32_to_40_for_image_context():
    candles = []
    price = 4400.0
    for i in range(60):
        close = price + (0.3 if i % 2 else -0.2)
        candles.append({
            'time': f'2026-08-12 10:{i%60:02d}:00',
            'open': price,
            'high': max(price, close) + 0.2,
            'low': min(price, close) - 0.2,
            'close': close,
        })
        price = close
    window, _ = renderer._reconstructed_window({
        'render_candles': candles,
        'render_visible_candle_count': 60,
    })
    assert len(window) == 40
    window, _ = renderer._reconstructed_window({
        'render_candles': candles,
        'render_visible_candle_count': 8,
    })
    assert len(window) == 32


def test_v78_analyzer_marks_full_only_profile():
    source = Path('app/services/analyzer.py').read_text()
    assert 'analysis["render_profile"] = "full_only"' in source
    assert 'analysis["compact_chart_enabled"] = False' in source
    assert 'analysis["smc_real_chart_style_version"] = "v7.9"' in source


def test_v78_watch_cards_do_not_add_conditional_entry_targets():
    source = Path('app/engine/renderer.py').read_text()
    body = source[source.index('def _draw_reference_price_axis_and_cards'):source.index('def _draw_reference_legend')]
    assert 'if confirmed and plan:' in body
    assert 'Any non-confirmed state is visually a WATCH state' in body
    assert 'BUY {buy_score}% IF' in body
    assert 'SELL {sell_score}% IF' in body
    assert '("ENTRY IF"' not in body


def test_v78_card_layout_has_auto_repel_and_connectors():
    source = Path('app/engine/renderer.py').read_text()
    body = source[source.index('def _draw_reference_price_axis_and_cards'):source.index('def _draw_reference_legend')]
    assert 'min_gap = 40' in body
    assert 'display_y' in body
    assert 'exact_y' in body
    assert 'connector' in body
    assert 'corridor_left' in body


def test_v78_watch_paths_are_compact_and_score_weighted():
    source = Path('app/engine/renderer.py').read_text()
    body = source[source.index('def _draw_reference_dual_watch_paths'):source.index('def _draw_reference_trade_plan')]
    assert 'strongest = "buy" if buy_score >= sell_score else "sell"' in body
    assert 'max_vertical = 118' in body
    assert 'entry = _number(scenario.get("trigger_price"))' in body
    assert 'origin_entry' in body  # kept only as ignored compatibility arg
