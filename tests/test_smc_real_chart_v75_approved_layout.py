from PIL import Image, ImageDraw

import app.engine.renderer as renderer


def _rows(count=42):
    rows=[]
    price=4380.0
    for i in range(count):
        close=price + (0.55 if i % 3 else -0.32)
        rows.append({
            'time': f'2026-08-11T{17 + (i*5)//60:02d}:{(i*5)%60:02d}:00',
            'open': price,
            'high': max(price, close)+0.24,
            'low': min(price, close)-0.22,
            'close': close,
        })
        price=close
    return rows


def _price_y(price: float) -> int:
    return int(round(100 + (4405.0 - float(price)) * 35.0))


def test_v75_image_flow_keeps_broad_real_m5_context():
    rows=_rows(42)
    analysis={
        'candles': rows,
        'render_candles': rows,
        'render_visible_candle_count': 42,
    }
    window, offset=renderer._reconstructed_window(analysis)
    assert len(window) == 40
    assert offset == 2


def test_v75_stale_reference_plan_levels_can_stay_in_nearby_price_range():
    rows=_rows(42)
    analysis={
        'candles': rows,
        'render_candles': rows,
        'render_visible_candle_count': 42,
        'current_price': rows[-1]['close'],
        'draw_mode': 'watch',
        'action_summary': {'primary_side':'wait','is_confirmed':False},
        'pattern_overlays':[{
            'bias':'هابط','status':'candidate',
            'geometry':{'trigger':4388.0,'stop':4391.0,'target':4384.0},
        }],
    }
    lo, hi=renderer._reconstructed_price_range(analysis, rows)
    assert lo < 4384.0 < hi
    assert lo < 4388.0 < hi
    assert lo < 4391.0 < hi


def test_v75_dual_watch_paths_can_share_one_approved_entry(monkeypatch):
    analysis={
        'draw_mode':'watch',
        'action_summary':{'primary_side':'wait','is_confirmed':False},
        'decision_zone':{'active':True},
        'dual_scenario_decision':{'score_gap':2},
        'buy_scenario_details':{'trigger_price':4392.0,'display_target':4398.0},
        'sell_scenario_details':{'trigger_price':4388.0,'display_target':4382.0},
    }
    captured=[]
    original=renderer._recon_arrow

    def spy(draw, points, color, *, width=3, dashed=False):
        captured.append(points)
        return original(draw, points, color, width=width, dashed=dashed)

    monkeypatch.setattr(renderer, '_recon_arrow', spy)
    image=Image.new('RGBA',(1600,900),(255,255,255,255))
    draw=ImageDraw.Draw(image)
    assert renderer._draw_reference_dual_watch_paths(
        draw, analysis, _price_y, (20,95,1425,575), 1050,
        renderer._font(14,True,True), origin_entry=4390.0,
    ) is True
    assert len(captured) == 2
    assert captured[0][0][1] == _price_y(4392.0)
    assert captured[1][0][1] == 575 - 16  # off-screen trigger is clipped into the future lane
