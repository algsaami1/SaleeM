from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image

from app.services.analyzer import analyze_chart_image

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"

app = FastAPI(
    title="SaleeM Gold Analyst",
    version="1.0.0",
    description="Gold XAUUSD M5 analysis rendered directly on the uploaded chart.",
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
        "app": "SaleeM Gold Analyst",
        "version": "1.0.0",
        "timeframe": "M5",
        "symbol": "XAUUSD",
        "storage": "temporary-only",
        "memory": "read-only",
        "renderer": "axis-calibrated-nearest-trade-v4",
        "trade_mode": "highest-probability-nearest-entry",
        "max_drawn_trades": 1,
        "stop_policy": "validated-chart-structure-and-read-only-memory",
    }


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(
    request: Request,
    image: UploadFile | None = File(None),
    symbol: str = Form("XAUUSD"),
    timeframe: str = Form("M5"),
):
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

        with Image.open(temp_path) as img:
            img.verify()

        result = analyze_chart_image(
            image_path=temp_path,
            symbol=symbol.strip().upper() or "XAUUSD",
            timeframe=timeframe.strip().upper() or "M5",
        )

        return templates.TemplateResponse(
            "index.html",
            {"request": request, "result": result, "error": None},
        )
    except HTTPException:
        raise
    except Exception as exc:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "result": None, "error": str(exc)},
            status_code=500,
        )
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
