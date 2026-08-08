from app.engine.reference_scenario_engine import review_reference_scenarios


def _candles(values):
    rows=[]
    for i,(o,h,l,c) in enumerate(values):
        rows.append({'time':f'2026-08-08 10:{i:02d}:00','open':o,'high':h,'low':l,'close':c})
    return rows


def test_multiple_tops_reference_scenario_is_selected_from_verified_features():
    values=[]
    price=100.0
    # stable history
    for i in range(16):
        o=price; c=price + (0.15 if i%2==0 else -0.10)
        values.append((o,max(o,c)+0.25,min(o,c)-0.25,c)); price=c
    # recent bearish impulse
    for delta in (-0.5,-0.7,-0.8,-0.9):
        o=price; c=price+delta
        values.append((o,o+0.15,c-0.15,c)); price=c
    frames={'M5':_candles(values)}
    pattern_review={'candidates':[{'name':'قمة ثلاثية','confidence':82,'timeframe':'M5','status':'candidate'}]}
    result=review_reference_scenarios(frames,pattern_review,{'scenario_reference_id':'result_07','scenario_score':80})
    assert result['available'] is True
    assert result['scenario_id']=='multiple_tops_breakdown'
    assert result['source_reference_id']=='result_07'
    assert 'expectation_arrow' in result['draw_components']


def test_visual_hint_cannot_create_scenario_without_m5_geometry():
    frames={'M5':_candles([(100,100.2,99.8,100.0)]*8)}
    result=review_reference_scenarios(frames,{}, {'scenario_reference_id':'result_08','scenario_score':95})
    assert result['available'] is False
    assert result['scenario_id']=='none'
    assert result['draw_components']==[]


def test_double_top_can_be_candidate_before_breakdown_when_geometry_is_real():
    values=[]
    # enough closed M5 candles; directional impulse is intentionally absent
    for i in range(20):
        base=100.0 + (0.05 if i%2==0 else -0.04)
        values.append((base,base+0.25,base-0.25,base+0.02))
    frames={'M5':_candles(values)}
    pattern_review={'candidates':[{'name':'M','confidence':79,'timeframe':'M5','status':'candidate'}]}
    result=review_reference_scenarios(frames,pattern_review,{'scenario_reference_id':'result_07','scenario_score':78})
    assert result['available'] is True
    assert result['scenario_id']=='multiple_tops_breakdown'
    assert result['status']=='candidate'
    assert 'expectation_arrow' in result['draw_components']
    assert 'pattern' in result['draw_components']
