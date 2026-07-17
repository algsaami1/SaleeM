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
    title="SaleeM Gold Analyst",
    version="0.5.0",
    description="Gold XAUUSD M5 chart analysis with a single annotated image output.",
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
            "error": None,
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok", "app": "SaleeM Gold Analyst", "timeframe": "M5", "symbol": "XAUUSD"}


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(
    request: Request,
    image: UploadFile | None = File(None),
    symbol: str = Form("XAUUSD"),
    timeframe: str = Form("M5"),
):
    allowed_types = {"image/png", "image/jpeg", "image/webp"}
    raw: bytes
    suffix = ".png"

    if not image or not image.filename:
        raise HTTPException(status_code=400, detail="يرجى اختيار صورة الشارت.")

    if image.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="يرجى رفع صورة PNG أو JPG أو WEBP.")

    raw = await image.read()
    suffix = Path(image.filename).suffix.lower() or ".png"

    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="حجم الصورة أكبر من 12 ميجابايت.")

    upload_name = f"{uuid4().hex}{suffix}"
    upload_path = UPLOAD_DIR / upload_name
    upload_path.write_bytes(raw)

    try:
        with Image.open(upload_path) as img:
            img.verify()
    except Exception as exc:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="الملف المرفوع ليس صورة صالحة.") from exc

    try:
        result = analyze_chart_image(
            image_path=upload_path,
            symbol=symbol.strip().upper() or "XAUUSD",
            timeframe=timeframe.strip().upper() or "M5",
            result_dir=RESULT_DIR,
        )
    except Exception as exc:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "result": None, "error": str(exc)},
            status_code=500,
        )

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "result": result, "error": None},
    )
