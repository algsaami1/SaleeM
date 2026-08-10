from app.engine.renderer import (
    _reference_confirmation_label,
    _reference_primary_title,
)


def test_primary_pattern_is_single_visual_headline():
    analysis = {
        'pattern_type': 'راية صاعدة',
        'reference_scenario_available': True,
        'reference_scenario_id': 'bullish_engulfing_orderblock',
        'reference_scenario_draw_components': ['structure', 'order_block', 'fvg'],
        'reference_scenario_geometry': {
            'structure_events': [{'label': 'BOS'}],
        },
    }
    assert _reference_primary_title(analysis) == 'BULL PENNANT'
    helper = _reference_confirmation_label(analysis)
    assert 'ORDER BLOCK REVERSAL' not in helper
    assert 'OB' in helper


def test_confirmation_is_compact_confluence_not_second_model():
    analysis = {
        'pattern_type': 'M',
        'reference_scenario_available': True,
        'reference_scenario_draw_components': ['structure', 'order_block', 'fvg', 'liquidity', 'engulfing'],
        'reference_scenario_geometry': {
            'structure_events': [{'label': 'CHOCH'}],
        },
    }
    helper = _reference_confirmation_label(analysis)
    assert helper.endswith('CONFIRMATION')
    assert helper.count('+') <= 2
