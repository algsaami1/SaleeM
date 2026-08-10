from io import BytesIO
from pathlib import Path

from PIL import Image

from app.engine.renderer import render_result
from app.services.analyzer import _apply_manual_visual_calibration, _bind_market_analysis_to_image, _prepare_analysis_image

ROOT = Path(__file__).resolve().parents[1]


def _candles(count=32):
    out=[]
    price=4340.0
    for i in range(count):
        close=price + (0.35 if i % 3 else -0.20)
        out.append({
            'time': f'2026-08-08 20:{i%60:02d}:00',
            'open': price,
            'high': max(price, close)+0.25,
            'low': min(price, close)-0.25,
            'close': close,
        })
        price=close
    return out


def test_portrait_upload_is_visual_reference_and_not_landscape_gated(tmp_path):
    src=tmp_path/'portrait.png'
    Image.new('RGB',(700,1200),'white').save(src)
    _path, meta=_prepare_analysis_image(src)
    assert meta['reference_orientation']=='portrait'
    assert meta['source_chart_preserved'] is True
    assert meta['reconstructed_market_chart'] is True
    assert meta['force_landscape_output'] is True
    assert meta['output_chart_orientation'] == 'landscape'
    main=(ROOT/'app'/'main.py').read_text(encoding='utf-8')
    assert 'يجب التقاط صورة الشارت بشكل أفقي' not in main


def test_market_ohlc_is_not_shifted_to_screenshot_price():
    canonical={
        'candles': _candles(8),
        'current_price': 4342.0,
        'entry': 4343.0,
        'stop_loss': 4340.5,
        'target_1': 4345.0,
        'target_2': 4346.0,
        'target_3': 4347.0,
        'support_levels': [{'price':4340.0}],
        'resistance_levels': [{'price':4345.0}],
        'direction':'صاعد',
        'draw_mode':'watch',
    }
    original_first=canonical['candles'][0]['open']
    result=_bind_market_analysis_to_image(
        canonical,
        {
            'chart_readable': True,
            'current_price': 4352.0,
            'current_price_y_ratio': 0.5,
            'image_price_high': 4360.0,
            'image_price_low': 4330.0,
            'image_axis_labels': [],
        },
        snapshot_key='x',
        snapshot_reused=False,
    )
    assert result['candles'][0]['open']==original_first
    assert result['entry']==4343.0
    assert result['current_price']==4342.0
    assert result['visual_current_price']==4352.0
    assert result['price_projection_mode']=='market_ohlc_preserved_no_screenshot_translation'


def test_render_result_preserves_portrait_uploaded_pixels_when_no_overlay(tmp_path):
    source=tmp_path/'source.png'
    Image.new('RGB',(700,1200),(10,10,10)).save(source)
    analysis={
        'candles': _candles(34),
        'current_price': 4344.2,
        'visual_current_price': 4344.3,
        'support_levels': [{'price':4341.5,'strength':80}],
        'resistance_levels': [{'price':4346.8,'strength':80}],
        'pattern_overlays': [],
        'reference_scenario_available': False,
        'chart_reference_meta': {
            'reference_aspect_ratio': 700/1200,
            'reference_orientation':'portrait',
            'reference_theme':'light',
        },
    }
    png=render_result(analysis, chart_background_path=source)
    with Image.open(BytesIO(png)) as out:
        assert out.height > out.width
        assert out.size == (700, 1200)
        # With no verified scenario/pattern and no usable S/R, the original pixels remain intact.
        assert out.convert('RGB').getpixel((out.width//2,out.height//2)) == (10,10,10)


def test_portrait_analysis_mode_renders_generated_landscape_ohlc(tmp_path):
    source=tmp_path/'portrait-source.png'
    Image.new('RGB',(700,1200),(10,10,10)).save(source)
    analysis={
        'candles': _candles(34),
        'current_price': 4344.2,
        'visual_current_price': 4344.3,
        'support_levels': [{'price':4341.5,'strength':80}],
        'resistance_levels': [{'price':4346.8,'strength':80}],
        'pattern_overlays': [],
        'reference_scenario_available': False,
        'reconstructed_market_chart': True,
        'force_landscape_output': True,
        'output_chart_orientation': 'landscape',
        'chart_reference_meta': {
            'reference_aspect_ratio': 700/1200,
            'reference_orientation':'portrait',
            'reference_theme':'light',
        },
    }
    png=render_result(analysis, chart_background_path=source)
    with Image.open(BytesIO(png)) as out:
        assert out.width > out.height
        assert out.size == (1600, 900)
        assert out.convert('RGB').getpixel((out.width//2,out.height//2)) != (10,10,10)


def test_manual_axis_calibration_changes_visual_reference_only():
    analysis={
        'current_price': 4342.0,
        'entry': 4343.0,
        'stop_loss': 4340.5,
        'target_1': 4345.0,
        'direction': 'صاعد',
    }
    ok=_apply_manual_visual_calibration(
        analysis,
        {'current_price': 4344.81, 'axis_high': 4352.51, 'axis_low': 4306.91},
    )
    assert ok is True
    assert analysis['current_price'] == 4342.0
    assert analysis['entry'] == 4343.0
    assert analysis['stop_loss'] == 4340.5
    assert analysis['target_1'] == 4345.0
    assert analysis['direction'] == 'صاعد'
    assert analysis['visual_current_price'] == 4344.81
    assert analysis['image_price_high'] == 4352.51
    assert analysis['image_price_low'] == 4306.91
    assert analysis['manual_axis_calibration'] is True


def test_landscape_upload_is_also_calibration_only_and_reconstructed(tmp_path):
    src=tmp_path/'landscape.png'
    Image.new('RGB',(1200,700),'white').save(src)
    _path, meta=_prepare_analysis_image(src)
    assert meta['reference_orientation']=='landscape'
    assert meta['reconstructed_market_chart'] is True
    assert meta['force_landscape_output'] is True
    assert meta['output_chart_orientation']=='landscape'
    assert meta['educational_reference_style']=='library_video'
    assert int(meta['reference_library_rule_count']) == 43


def test_library_video_reconstruction_keeps_more_left_history_and_future_room(tmp_path):
    source=tmp_path/'portrait.png'
    Image.new('RGB',(700,1200),'white').save(source)
    candles=_candles(90)
    analysis={
        'candles': candles,
        'current_price': float(candles[-1]['close']),
        'support_levels': [{'price': float(candles[-1]['close'])-1.2, 'strength':80}],
        'resistance_levels': [{'price': float(candles[-1]['close'])+2.2, 'strength':80}],
        'reconstructed_market_chart': True,
        'force_landscape_output': True,
        'output_chart_orientation':'landscape',
        'educational_reference_style':'library_video',
        'pattern_type':'M',
        'pattern_bias':'هابط',
        'pattern_overlays':[{
            'name':'M','timeframe':'M5','bias':'هابط','status':'candidate','confidence':76,
            'reference_match_score':74,
            'geometry':{
                'window_size':90,
                'anchors':[{'index':55,'price':4348.0,'role':'pivot'},{'index':63,'price':4345.0,'role':'neck'},{'index':72,'price':4348.1,'role':'pivot'}],
                'lines':[{'p1':[55,4345.0],'p2':[72,4345.0],'role':'neckline'}],
                'path':[[55,4348.0],[63,4345.0],[72,4348.1]],
                'trigger':4345.0,'stop':4348.4,'target':4341.6,'breakout_index':None,
            },
        }],
        'reference_scenario_available':False,
    }
    png=render_result(analysis, chart_background_path=source)
    with Image.open(BytesIO(png)) as out:
        assert out.size==(1600,900)
        # Permanent video/library style is dark, not the white source screenshot.
        px=out.convert('RGB').getpixel((20,20))
        assert sum(px) < 120
