from __future__ import annotations
import io
from pathlib import Path
from typing import Any
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont


def _font(size: int, bold: bool = False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()


def _ar(v: Any) -> str:
    s = str(v)
    try:
        return get_display(arabic_reshaper.reshape(s))
    except Exception:
        return s


def _pt(norm: list[float], w: int, h: int) -> tuple[int, int]:
    x = max(0.0, min(1.0, float(norm[0])))
    y = max(0.0, min(1.0, float(norm[1])))
    return int(x*w), int(y*h)


def _line(draw: ImageDraw.ImageDraw, y: float | None, w: int, h: int, color, label: str, price: Any = None):
    if y is None: return
    yy = int(max(0.04, min(0.96, float(y))) * h)
    draw.line((0, yy, int(w*.81), yy), fill=color, width=max(2, w//450))
    text = f"{label} {price:.2f}" if isinstance(price, (int,float)) else label
    draw.rounded_rectangle((8, yy-17, 132, yy+16), radius=8, fill=(*color, 220))
    draw.text((15, yy-12), text, font=_font(max(11,w//105), True), fill="white")


def render_result(image_path: Path, a: dict[str, Any]) -> bytes:
    with Image.open(image_path).convert("RGBA") as im:
        im.thumbnail((1600, 1200))
        canvas = im.copy()
    w,h = canvas.size
    overlay = Image.new("RGBA", canvas.size, (0,0,0,0))
    draw = ImageDraw.Draw(overlay, "RGBA")

    # Zones and levels over the full chart.
    for box in a.get("fvg_boxes", [])[:3]:
        try:
            x1,y1 = _pt([box[0],box[1]],w,h); x2,y2 = _pt([box[2],box[3]],w,h)
            draw.rounded_rectangle((x1,y1,x2,y2), radius=8, fill=(126,87,194,52), outline=(126,87,194,190), width=2)
            draw.text((x1+6,y1+4), "FVG", font=_font(max(10,w//120),True), fill=(87,50,150,230))
        except Exception: pass
    _line(draw,a.get("support_y"),w,h,(28,156,125),"SUP",a.get("support"))
    _line(draw,a.get("resistance_y"),w,h,(226,91,84),"RES",a.get("resistance"))
    _line(draw,a.get("entry_y"),w,h,(45,137,239),"ENTRY",a.get("entry"))
    _line(draw,a.get("stop_loss_y"),w,h,(213,57,71),"SL",a.get("stop_loss"))
    for key,label in [("target_1_y","TP1"),("target_2_y","TP2"),("target_3_y","TP3")]:
        _line(draw,a.get(key),w,h,(37,167,98),label,a.get(key.replace("_y","")))

    # Expected path.
    points=[]
    for p in a.get("path_points", [])[:8]:
        try: points.append(_pt(p,w,h))
        except Exception: pass
    bullish = a.get("direction") == "صاعد"
    path_color = (27,166,102,235) if bullish else (222,70,70,235)
    if len(points)>=2:
        draw.line(points, fill=path_color, width=max(4,w//250), joint="curve")
        x2,y2=points[-1]; x1,y1=points[-2]
        import math
        ang=math.atan2(y2-y1,x2-x1)
        s=max(11,w//80)
        for off in (2.6,-2.6):
            draw.line((x2,y2,x2+s*math.cos(ang+off),y2+s*math.sin(ang+off)),fill=path_color,width=max(4,w//250))

    # Small right information panel, overlaid rather than shrinking chart.
    pw=max(190,int(w*.205)); px=w-pw-10; py=10; ph=min(h-20,max(250,int(h*.46)))
    draw.rounded_rectangle((px,py,w-10,py+ph),radius=18,fill=(255,255,255,225),outline=(225,220,238,230),width=2)
    fs=max(12,w//95); small=max(10,w//125)
    draw.text((px+14,py+13),"SaleeM Gold Analyst",font=_font(fs,True),fill=(34,31,51,255))
    buy=int(a.get("buy_probability",50)); sell=100-buy
    y=py+48
    draw.text((px+14,y),f"BUY  {buy}%",font=_font(fs+2,True),fill=(25,151,91,255)); y+=30
    draw.text((px+14,y),f"SELL {sell}%",font=_font(fs+2,True),fill=(211,62,69,255)); y+=38
    for lab,val in [("Trend",a.get("direction","—")),("Scenario",a.get("scenario","—"))]:
        draw.text((px+14,y),lab,font=_font(small,True),fill=(122,116,142,255)); y+=18
        draw.text((px+14,y),_ar(val),font=_font(small+1,True),fill=(44,40,62,255)); y+=30
    note=_ar(a.get("note",""))
    draw.text((px+14,py+ph-46),note,font=_font(small,True),fill=(75,70,94,255))

    out=Image.alpha_composite(canvas,overlay).convert("RGB")
    b=io.BytesIO(); out.save(b,"PNG",optimize=True); return b.getvalue()
