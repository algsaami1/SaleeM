from PIL import Image, ImageDraw

import app.engine.renderer as renderer


def _rows(count=42):
    rows=[]
    price=4380.0
    for i in range(count):
        close=price + (0.45 if i % 3 else -0.28)
        rows.append({
            'time': f'2026-08-11T{17 + (i*5)//60:02d}:{(i*5)%60:02d}:00',
            'open': price,
            'high': max(price, close)+0.22,
            'low': min(price, close)-0.20,
            'close': close,
        })
        price=close
    return rows


def test_v76_canvas_is_wide_full_hd():
    assert renderer._reconstructed_dimensions({}) == (1920, 1080)


def test_v76_watch_always_keeps_buy_and_sell_conditions_when_both_are_valid():
    analysis={
        'draw_mode':'watch',
        'action_summary':{'primary_side':'wait','is_confirmed':False},
        # Deliberately large score gap and no decision zone: V7.5 hid one path.
        'dual_scenario_decision':{'score_gap':31},
        'buy_scenario_details':{'trigger_price':4386.0,'display_target':4392.0,'score':71},
        'sell_scenario_details':{'trigger_price':4376.0,'display_target':4369.0,'score':39},
    }
    assert renderer._reference_dual_preview_needed(analysis) is True


def test_v76_event_label_box_is_below_its_real_candle_low():
    rows=_rows(6)
    image=Image.new('RGBA',(900,500),(255,255,255,255))
    draw=ImageDraw.Draw(image)
    candle_x=[100,180,260,340,420,500]
    price_max=4390.0
    price_min=4370.0
    plot=(40,40,820,440)

    def price_y(price):
        return int(round(plot[1] + (price_max-float(price))/(price_max-price_min)*(plot[3]-plot[1])))

    idx=3
    low_y=price_y(rows[idx]['low'])
    box=renderer._draw_reference_event_label_below_candle(
        draw,
        candles=rows,
        candle_x=candle_x,
        index=idx,
        price_y=price_y,
        plot=plot,
        text='BOS',
        font=renderer._font(14,True,True),
        color=(35,145,83,230),
        occupied=[],
        anchor_y=price_y(rows[idx]['close']),
    )
    assert box is not None
    assert (box[1] + box[3]) // 2 > low_y


def test_v76_confirmed_trade_still_uses_single_active_path():
    analysis={
        'draw_mode':'confirmed',
        'action_summary':{'primary_side':'buy','is_confirmed':True},
        'buy_scenario_details':{'trigger_price':4386.0,'display_target':4392.0,'score':80},
        'sell_scenario_details':{'trigger_price':4376.0,'display_target':4369.0,'score':20},
    }
    assert renderer._reference_dual_preview_needed(analysis) is False
