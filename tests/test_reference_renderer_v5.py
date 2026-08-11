from io import BytesIO
from PIL import Image

from app.services.analyzer import _select_reference_visual_template
from app.engine.renderer import (
    _build_reference_visual_scene,
    _reference_template_kind,
    _resolve_reference_trade_plan,
    render_result,
)


def _candles(count=110):
    rows=[]
    price=4300.0
    for i in range(count):
        close=price + (0.35 if i % 4 else -0.18)
        rows.append({
            'time': f'2026-08-10 {10 + (i//12):02d}:{(i*5)%60:02d}:00',
            'open': price,
            'high': max(price, close)+0.28,
            'low': min(price, close)-0.28,
            'close': close,
        })
        price=close
    return rows


def _m_analysis(score=78):
    candles=_candles()
    return {
        'candles': candles,
        'current_price': candles[-1]['close'],
        'visual_current_price': candles[-1]['close'],
        'reconstructed_market_chart': True,
        'pattern_type': 'M',
        'pattern_status': 'candidate',
        'pattern_confidence': score,
        'reference_match_score': score,
        'pattern_bias': 'هابط',
        'pattern_overlays': [{
            'name':'M','timeframe':'M5','bias':'هابط','status':'candidate','confidence':score,
            'reference_match_score':score,
            'geometry':{
                'window_size':110,
                'anchors':[{'index':70,'price':4317.0,'role':'pivot'},{'index':78,'price':4313.0,'role':'neck'},{'index':88,'price':4317.1,'role':'pivot'}],
                'lines':[{'p1':[70,4313.0],'p2':[88,4313.0],'role':'neckline'}],
                'path':[[70,4317.0],[78,4313.0],[88,4317.1]],
                'trigger':4313.0,'stop':4317.5,'target':4308.5,'breakout_index':None,
            },
        }],
        'support_levels':[{'price':4313.0,'strength':82}],
        'resistance_levels':[{'price':4317.1,'strength':84}],
        'reference_scenario_available':False,
        'action_summary': {'primary_side':'wait','is_confirmed':False},
    }


def test_v5_selects_multiple_tops_as_visual_template_only():
    template, reason=_select_reference_visual_template(_m_analysis())
    assert template == 'multiple_tops'
    assert reason == ''


def test_v5_rejects_reference_drawing_below_68_without_changing_pattern():
    analysis=_m_analysis(67)
    template, reason=_select_reference_visual_template(analysis)
    assert template is None
    assert reason == 'pattern_score_below_68'
    assert analysis['pattern_type'] == 'M'


def test_v5_unbroken_symmetrical_triangle_stays_neutral_visual_rejection():
    template, reason=_select_reference_visual_template({
        'pattern_type':'مثلث متماثل','pattern_status':'candidate','pattern_confidence':90,
        'reference_match_score':90,'reference_scenario_confidence':0,
    })
    assert template is None
    assert reason == 'symmetrical_triangle_unbroken_neutral'


def test_v5_scene_has_left_history_and_future_room():
    analysis=_m_analysis()
    analysis['visual_template_id']='multiple_tops'
    scene=_build_reference_visual_scene(analysis)
    assert 100 <= len(scene['candles']) <= 120
    assert scene['template_id'] == 'multiple_tops'
    assert scene['future_space_ratio'] >= 0.20


def test_v5_candidate_plan_keeps_entry_cancel_target():
    plan=_resolve_reference_trade_plan(_m_analysis())
    assert plan is not None
    assert plan['confirmed'] is False
    assert plan['side'] == 'sell'
    assert plan['entry'] == 4313.0
    assert plan['stop'] == 4317.5
    assert plan['target'] == 4308.5


def test_v5_renderer_outputs_reference_sheet_with_generated_axis():
    analysis=_m_analysis()
    analysis['visual_template_id']='multiple_tops'
    png=render_result(analysis)
    with Image.open(BytesIO(png)) as image:
        assert image.size == (1920,1080)
        assert image.mode in {'RGB','RGBA'}
        # Light educational-sheet background and non-empty plot.
        assert sum(image.convert('RGB').getpixel((20,20))) > 600
        assert image.convert('RGB').getbbox() is not None
