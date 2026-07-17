from __future__ import annotations
import base64, json, os
from pathlib import Path
from typing import Any
import httpx
from app.engine.memory_engine import memory_context
from app.engine.models import normalize_analysis
from app.engine.renderer import render_result

OPENAI_URL='https://api.openai.com/v1/responses'
BASE_DIR=Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR=BASE_DIR/'knowledge'

NUM_NULL={"type":["number","null"]}
ANALYSIS_SCHEMA={
 "type":"object","additionalProperties":False,
 "properties":{
  "direction":{"type":"string","enum":["صاعد","هابط","عرضي","غير واضح"]},
  "buy_probability":{"type":"integer","minimum":5,"maximum":95},
  "sell_probability":{"type":"integer","minimum":5,"maximum":95},
  "current_price":NUM_NULL,"support":NUM_NULL,"resistance":NUM_NULL,"entry":NUM_NULL,"stop_loss":NUM_NULL,
  "target_1":NUM_NULL,"target_2":NUM_NULL,"target_3":NUM_NULL,
  "support_y":NUM_NULL,"resistance_y":NUM_NULL,"entry_y":NUM_NULL,"stop_loss_y":NUM_NULL,
  "target_1_y":NUM_NULL,"target_2_y":NUM_NULL,"target_3_y":NUM_NULL,
  "fvg_boxes":{"type":"array","items":{"type":"array","items":{"type":"number"},"minItems":4,"maxItems":4},"maxItems":3},
  "path_points":{"type":"array","items":{"type":"array","items":{"type":"number"},"minItems":2,"maxItems":2},"maxItems":8},
  "scenario":{"type":"string"},"note":{"type":"string"},"memory_matches":{"type":"array","items":{"type":"string"},"maxItems":4}
 },
 "required":["direction","buy_probability","sell_probability","current_price","support","resistance","entry","stop_loss","target_1","target_2","target_3","support_y","resistance_y","entry_y","stop_loss_y","target_1_y","target_2_y","target_3_y","fvg_boxes","path_points","scenario","note","memory_matches"]
}

def _data_url(path:Path)->str:
 mime={'.png':'image/png','.webp':'image/webp'}.get(path.suffix.lower(),'image/jpeg')
 return f"data:{mime};base64,"+base64.b64encode(path.read_bytes()).decode()

def _text(payload:dict[str,Any])->str:
 if isinstance(payload.get('output_text'),str): return payload['output_text']
 for item in payload.get('output',[]):
  for c in item.get('content',[]):
   if isinstance(c.get('text'),str): return c['text']
 raise RuntimeError('لم ترجع خدمة التحليل نتيجة صالحة.')

def _analyze(path:Path)->dict[str,Any]:
 key=os.getenv('OPENAI_API_KEY','').strip()
 if not key: raise RuntimeError('متغير OPENAI_API_KEY غير موجود في Railway.')
 prompt=f'''أنت محرك SaleeM Gold Analyst للذهب XAUUSD وفريم 5 دقائق فقط.
افحص الشارت، واستفد من القواعد والسيناريوهات المرجعية، ثم أرجع بيانات رسم منظمة.
- حدد دعمًا ومقاومة ودخولًا وSL وثلاثة أهداف إن كانت الأسعار مقروءة.
- BUY وSELL مجموعهما 100 ولا تستخدم 100 أو 0.
- note سطر عربي قصير جدًا لا يتجاوز 82 حرفًا.
- y values إحداثيات عمودية نسبية من 0 أعلى الصورة إلى 1 أسفلها.
- fvg_boxes بصيغة [x1,y1,x2,y2] نسبية من 0 إلى 1، فقط للمناطق الواضحة.
- path_points مسار السيناريو المتوقع على الشارت بنقاط [x,y] نسبية؛ أختر سيناريو واحدًا فقط.
- لا تخترع أسعارًا غير مقروءة واستخدم null عند عدم وضوحها.
- راجع الذاكرة للقراءة فقط ولا تحفظ هذا التحليل.
الذاكرة: {memory_context(KNOWLEDGE_DIR)}'''
 body={"model":os.getenv('OPENAI_MODEL','gpt-4.1-mini'),"input":[{"role":"user","content":[{"type":"input_text","text":prompt},{"type":"input_image","image_url":_data_url(path)}]}],"text":{"format":{"type":"json_schema","name":"saleem_overlay","strict":True,"schema":ANALYSIS_SCHEMA}}}
 with httpx.Client(timeout=120) as client:
  r=client.post(OPENAI_URL,headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},json=body)
 if r.status_code>=400: raise RuntimeError(f'خطأ خدمة التحليل ({r.status_code}): {r.text[:500]}')
 return normalize_analysis(json.loads(_text(r.json())))

def analyze_chart_image(image_path:Path,symbol:str,timeframe:str)->dict[str,Any]:
 a=_analyze(image_path)
 png=render_result(image_path,a)
 return {**a,'symbol':'XAUUSD','timeframe':'M5','result_url':'data:image/png;base64,'+base64.b64encode(png).decode()}
