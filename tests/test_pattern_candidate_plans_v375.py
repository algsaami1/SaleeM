import math

from app.engine.pattern_engine import _channel_or_triangle, _flag_or_pennant


def _triangle(kind: str):
    rows=[{'open':105.0,'high':106.0,'low':104.0,'close':105.0} for _ in range(36)]
    peaks=[8,14,20,26,32]
    troughs=[5,11,17,23,29]
    if kind == 'asc':
        for j,i in enumerate(peaks):
            rows[i]={'open':108.5,'high':110.0,'low':108.0,'close':109.0}
        for j,i in enumerate(troughs):
            low=99+1.2*j
            rows[i]={'open':low+1.5,'high':low+2.0,'low':low,'close':low+1.0}
        rows[-1]={'open':106.5,'high':108,'low':106,'close':107}
    elif kind == 'desc':
        for j,i in enumerate(peaks):
            high=111-1.2*j
            rows[i]={'open':high-1.5,'high':high,'low':high-2,'close':high-1}
        for j,i in enumerate(troughs):
            rows[i]={'open':101.5,'high':102,'low':100,'close':101}
        rows[-1]={'open':104,'high':105,'low':102,'close':103}
    else:
        for j,i in enumerate(peaks):
            high=112-1.0*j
            rows[i]={'open':high-1,'high':high,'low':high-1.5,'close':high-0.5}
        for j,i in enumerate(troughs):
            low=98+1.0*j
            rows[i]={'open':low+1,'high':low+1.5,'low':low,'close':low+0.5}
        rows[-1]={'open':105,'high':106,'low':104.5,'close':105.2}
    return rows


def _wedge(direction: str):
    rows=[]
    for i in range(36):
        if direction == 'rising':
            lower=98+0.23*i
            upper=107+0.09*i
        else:
            upper=112-0.23*i
            lower=103-0.09*i
        phase=math.sin(2*math.pi*i/6)
        mid=(upper+lower)/2
        amp=(upper-lower)/2*0.92
        close=mid+amp*phase
        open_=close-0.1*math.cos(i)
        rows.append({
            'open':open_,
            'high':max(open_,close)+0.25,
            'low':min(open_,close)-0.25,
            'close':close,
        })
    return rows


def _flag(bull: bool, contracting: bool):
    rows=[]
    price=100.0
    for i in range(14):
        close=price+(0.05 if i%2==0 else -0.04)
        rows.append({'open':price,'high':max(price,close)+0.15,'low':min(price,close)-0.15,'close':close})
        price=close
    step=1.8 if bull else -1.8
    for _ in range(7):
        o=price; c=o+step
        rows.append({'open':o,'high':max(o,c)+0.25,'low':min(o,c)-0.25,'close':c})
        price=c
    base=price
    for i in range(15):
        center=base + ((-0.12*i) if bull else (0.12*i))
        amp=(1.2*(1-i/22) if contracting else 1.1)
        val=center+amp*math.sin(2*math.pi*i/4)
        o=val-0.1*math.cos(i)
        rows.append({'open':o,'high':max(o,val)+0.25,'low':min(o,val)-0.25,'close':val})
    return rows


def _assert_candidate_plan(candidate, expected_name):
    assert candidate is not None
    assert candidate.name == expected_name
    assert candidate.status == 'candidate'
    assert candidate.geometry['breakout_index'] is None
    assert candidate.geometry['trigger'] is not None
    assert candidate.geometry['stop'] is not None
    assert candidate.geometry['target'] is not None


def test_candidate_ascending_and_descending_triangles_keep_conditional_plan():
    _assert_candidate_plan(_channel_or_triangle(_triangle('asc'), timeframe='M5'), 'مثلث صاعد')
    _assert_candidate_plan(_channel_or_triangle(_triangle('desc'), timeframe='M5'), 'مثلث هابط')


def test_candidate_rising_and_falling_wedges_keep_conditional_plan():
    _assert_candidate_plan(_channel_or_triangle(_wedge('rising'), timeframe='M5'), 'وتد صاعد')
    _assert_candidate_plan(_channel_or_triangle(_wedge('falling'), timeframe='M5'), 'وتد هابط')


def test_candidate_flag_and_pennant_keep_conditional_plan_without_confirmation():
    _assert_candidate_plan(_flag_or_pennant(_flag(True, False), timeframe='M5'), 'علم صاعد')
    _assert_candidate_plan(_flag_or_pennant(_flag(True, True), timeframe='M5'), 'راية صاعدة')
    _assert_candidate_plan(_flag_or_pennant(_flag(False, False), timeframe='M5'), 'علم هابط')
    _assert_candidate_plan(_flag_or_pennant(_flag(False, True), timeframe='M5'), 'راية هابطة')


def test_unbroken_symmetrical_triangle_stays_neutral_without_plan_direction():
    candidate=_channel_or_triangle(_triangle('sym'), timeframe='M5')
    assert candidate is not None
    assert candidate.name == 'مثلث متماثل'
    assert candidate.status == 'candidate'
    assert candidate.bias == 'محايد'
    assert candidate.geometry['trigger'] is None
    assert candidate.geometry['stop'] is None
    assert candidate.geometry['target'] is None
    assert candidate.geometry['breakout_index'] is None
