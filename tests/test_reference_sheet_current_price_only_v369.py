from pathlib import Path

from app.services.analyzer import GEOMETRY_SCHEMA, _apply_manual_visual_calibration
from app.engine.renderer import _reconstructed_window

ROOT = Path(__file__).resolve().parents[1]


def _candles(count=115):
    rows=[]
    price=4300.0
    for i in range(count):
        close=price + (0.15 if i % 2 else -0.05)
        rows.append({
            'time': f'2026-08-10 10:{i%60:02d}:00',
            'open': price,
            'high': max(price, close)+0.2,
            'low': min(price, close)-0.2,
            'close': close,
        })
        price=close
    return rows


def test_geometry_schema_reads_current_price_only():
    assert GEOMETRY_SCHEMA['required'] == ['chart_readable', 'current_price']
    assert 'image_price_high' not in GEOMETRY_SCHEMA['properties']
    assert 'image_price_low' not in GEOMETRY_SCHEMA['properties']
    assert 'image_axis_labels' not in GEOMETRY_SCHEMA['properties']


def test_manual_current_price_never_builds_axis_or_changes_market_price():
    analysis={'current_price':4321.5,'entry':4323.0,'direction':'صاعد'}
    assert _apply_manual_visual_calibration(analysis, {'current_price':4322.4}) is True
    assert analysis['current_price'] == 4321.5
    assert analysis['entry'] == 4323.0
    assert analysis['visual_current_price'] == 4322.4
    assert analysis['image_price_high'] is None
    assert analysis['image_price_low'] is None
    assert analysis['image_axis_labels'] == []
    assert analysis['image_axis_mode'] == 'disabled'


def test_upload_form_exposes_only_current_price_reference():
    html=(ROOT/'app'/'templates'/'index.html').read_text(encoding='utf-8')
    assert 'name="current_price_ref"' in html
    assert 'name="axis_high_ref"' not in html
    assert 'name="axis_low_ref"' not in html
    assert 'أعلى المحور' not in html
    assert 'أدنى المحور' not in html


def test_reference_sheet_keeps_more_market_history_left():
    candles=_candles(115)
    window, offset=_reconstructed_window({'candles':candles})
    assert len(window) >= 100
    assert offset == len(candles)-len(window)
