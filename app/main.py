from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image

from app.services.analyzer import analyze_chart_image

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
UPLOAD_DIR = STATIC_DIR / "uploads"
RESULT_DIR = STATIC_DIR / "results"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="SaleeM Gold Chart Analyzer",
    version="0.1.0",
    description="MVP for analyzing GOLD M5 chart screenshots.",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "result": None,
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok", "app": "SaleeM"}


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(
    request: Request,
    image: UploadFile = File(...),
    symbol: str = Form("GOLD"),
    timeframe: str = Form("M5"),
):
    allowed_types = {"image/png", "image/jpeg", "image/webp"}

    if image.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="يرجى رفع صورة PNG أو JPG أو WEBP.",
        )

    raw = await image.read()
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="حجم الصورة أكبر من 12 ميجابايت.",
        )

    suffix = Path(image.filename or "chart.png").suffix.lower() or ".png"
    upload_name = f"{uuid4().hex}{suffix}"
    upload_path = UPLOAD_DIR / upload_name
    upload_path.write_bytes(raw)

    try:
        with Image.open(upload_path) as img:
            img.verify()
    except Exception as exc:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail="الملف المرفوع ليس صورة صالحة.",
        ) from exc

    result = analyze_chart_image(
        image_path=upload_path,
        symbol=symbol.strip().upper() or "GOLD",
        timeframe=timeframe.strip().upper() or "M5",
        result_dir=RESULT_DIR,
    )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "result": result,
        },
    )
