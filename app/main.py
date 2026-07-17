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
    version="2.1.1",
    description="Reconstructs the last two hours of XAUUSD M5 in the fixed SaleeM visual template.",
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
        "version": "2.1.0",
        "timeframe": "M5",
        "symbol": "XAUUSD",
        "window": "2h / 24 candles",
        "storage": "temporary-only",
        "memory": "read-only",
        "renderer": "saleem-fixed-poster-v2.1",
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
    except Exception:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "result": None,
                "error": (
                    "تعذر إنشاء التحليل بدقة. اعرض 24 شمعة كاملة على M5 "
                    "مع محور الأسعار واضحًا، ثم حاول مرة أخرى."
                ),
            },
            status_code=500,
        )
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
