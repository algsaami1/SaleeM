import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image
from starlette.concurrency import run_in_threadpool

from app.services.analyzer import analyze_chart_image, load_final_spec

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"

# يتأكد عند التشغيل أن الدستور النهائي موجود داخل النسخة المنشورة.
load_final_spec()

app = FastAPI(
    title="SaleeM",
    version="2.5.1",
    description="Analyzes XAUUSD M5 with automatic M15/H1/H4 market context and a fixed SaleeM visual template.",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "result": None, "error": None},
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": "SaleeM",
        "version": "2.5.1",
        "timeframe": "M5",
        "symbol": "XAUUSD",
        "window": "2h / 24 candles",
        "storage": "per-timeframe-json-cache",
        "memory": "read-only",
        "renderer": "saleem-fixed-poster-v2.1-close-stop",
        "ui": "saleem-clean-hero-progress-save-share",
        "market_data": "Twelve Data: M5/M15/H1/H4",
        "openai_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "twelve_data_configured": bool(os.getenv("TWELVE_DATA_API_KEY", "").strip()),
        "cache_policy": "M5=4m,M15=14m,H1=55m,H4=4h",
        "cache_path": os.getenv("MARKET_DATA_CACHE_PATH", "/tmp/saleem_market_data_cache.json"),
        "trade_mode": "single-highest-probability-scenario",
        "targets": 3,
        "support_resistance": "nearest-two-strength-weighted-lines",
        "title": "تحليل SaleeM - XAUUSD - M5 - آخر ساعتين",
    }


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, image: UploadFile | None = File(None)):
    allowed_types = {"image/png", "image/jpeg", "image/webp"}
    if not image or not image.filename:
        raise HTTPException(status_code=400, detail="يرجى اختيار صورة الشارت.")
    if image.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="يرجى رفع صورة PNG أو JPG أو WEBP.")

    raw = await image.read()
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="حجم الصورة أكبر من 12 ميجابايت.")

    suffix = Path(image.filename).suffix.lower() or ".png"
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp.write(raw)
            temp_path = Path(temp.name)

        with Image.open(temp_path) as source:
            source.verify()

        result = await run_in_threadpool(
            analyze_chart_image,
            temp_path,
            "XAUUSD",
            "M5",
        )
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "result": result, "error": None},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logging.exception("SaleeM analysis failed")
        technical_message = str(exc).strip()
        safe_prefixes = (
            "متغير OPENAI_API_KEY",
            "تعذر جلب بيانات الفريمات",
            "خطأ خدمة التحليل",
        )
        if technical_message.startswith(safe_prefixes):
            error_message = technical_message
        else:
            error_message = (
                "تعذر إنشاء التحليل بدقة. اعرض 24 شمعة كاملة على M5 "
                "مع محور الأسعار واضحًا، ثم حاول مرة أخرى."
            )
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "result": None,
                "error": error_message,
            },
            status_code=500,
        )
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
