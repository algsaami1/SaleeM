import logging
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from pydantic import BaseModel, Field
from PIL import Image
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.engine.renderer import AxisCalibrationError
from app.services.analyzer import analyze_chart_image, load_final_spec
from app.services.feedback_store import FeedbackStore
from app.services.mailer import delivery_provider, email_configured, owner_email, send_note_email

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"

# يتأكد عند التشغيل أن الدستور النهائي موجود داخل النسخة المنشورة.
load_final_spec()

app = FastAPI(
    title="SaleeM",
    version=__version__,
    description="Analyzes XAUUSD M5 with automatic M15/H1/H4 market context and a fixed SaleeM visual template.",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)
feedback_store = FeedbackStore()


def _logic_text(value: object) -> Markup:
    """تعريب كلمات الشرط وتلوينها دون السماح بإدخال HTML من النموذج."""
    safe = str(escape("" if value is None else str(value)))
    safe = re.sub(
        r"(?<![\w\u0600-\u06ff])(?:IF|إذا)(?![\w\u0600-\u06ff])",
        '<span class="logic-keyword">إذا</span>',
        safe,
        flags=re.IGNORECASE,
    )
    safe = re.sub(
        r"(?<![\w\u0600-\u06ff])(?:THEN|فإن)(?![\w\u0600-\u06ff])",
        '<span class="logic-keyword">فإن</span>',
        safe,
        flags=re.IGNORECASE,
    )
    return Markup(safe)


templates.env.filters["logic_text"] = _logic_text


class TradeFeedbackPayload(BaseModel):
    trade_result: str = Field(..., pattern="^(win|loss|open|no_trade)$")
    rating: int = Field(..., ge=1, le=5)
    notes: str | None = Field(default="", max_length=700)


class NotePayload(BaseModel):
    message: str = Field(..., min_length=1, max_length=1500)


def page_context(request: Request, *, result=None, error=None, axis_retry=False):
    return {
        "request": request,
        "result": result,
        "error": error,
        "axis_retry": axis_retry,
        "summary": feedback_store.summary(),
        "owner_email": owner_email(),
        "app_version": __version__,
    }


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html", page_context(request))


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": "SaleeM",
        "version": __version__,
        "timeframe": "M5",
        "symbol": "XAUUSD",
        "window": "flexible market candle window",
        "storage": "market-and-analysis-snapshot-json-cache",
        "memory": "read-only",
        "renderer": "saleem-market-snapshot-axis-projection-v3.22.0",
        "ui": "saleem-unified-result-template-v3.22.0",
        "market_data": "Twelve Data: M5/M15/H1/H4",
        "openai_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "twelve_data_configured": bool(os.getenv("TWELVE_DATA_API_KEY", "").strip()),
        "cache_policy": "M5=4m,M15=14m,H1=55m,H4=4h",
        "cache_path": os.getenv("MARKET_DATA_CACHE_PATH", "/tmp/saleem_market_data_cache.json"),
        "analysis_cache_path": os.getenv("ANALYSIS_SNAPSHOT_CACHE_PATH", "/tmp/saleem_analysis_snapshot_cache.json"),
        "decision_pipeline": "market-only-decision+image-only-axis-geometry",
        "feedback_store_path": os.getenv("SALEEM_FEEDBACK_STORE_PATH", "/tmp/saleem_feedback_store.json"),
        "owner_email_configured": bool(owner_email()),
        "email_configured": email_configured(),
        "smtp_configured": False,
        "email_provider": delivery_provider(),
        "trade_mode": "adaptive-primary-scenario+confirmed-swing-limit-plans",
        "targets": 3,
        "limit_recommendations": "confirmed-H4-H1-swing-buy-limit-and-sell-limit-with-estimated-non-guaranteed-rates",
        "support_resistance": "nearest-two-strength-weighted-lines",
        "title": "تحليل SaleeM - XAUUSD - M5",
    }


@app.get("/api/summary")
async def summary_api():
    return feedback_store.summary()


@app.post("/api/feedback")
async def submit_trade_feedback(payload: TradeFeedbackPayload):
    try:
        summary = feedback_store.record_feedback(
            trade_result=payload.trade_result,
            rating=payload.rating,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "ok": True,
        "message": "تم حفظ نتيجة الصفقة والتقييم وتحديث الملخص العام.",
        "summary": summary,
    }


@app.post("/api/notes")
async def submit_note(payload: NotePayload):
    try:
        feedback_store.record_note(message=payload.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    was_emailed = await run_in_threadpool(
        send_note_email,
        "ملاحظات واقتراحات من تطبيق SaleeM",
        payload.message.strip(),
    )
    if was_emailed:
        message = "تم حفظ الملاحظة وإرسال نسخة إلى بريد مالك التطبيق."
    elif not email_configured():
        message = "تم حفظ الملاحظة. أضف RESEND_API_KEY وSALEEM_EMAIL في Railway لتفعيل الإرسال عبر HTTPS."
    else:
        message = "تم حفظ الملاحظة، لكن تعذر إرسال البريد. افتح Railway Logs لمعرفة سبب الرفض."
    return JSONResponse({"ok": True, "message": message, "emailed": was_emailed})


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
        with Image.open(temp_path) as source:
            width, height = source.size
            if width * height > 40_000_000:
                raise HTTPException(
                    status_code=400,
                    detail="أبعاد الصورة كبيرة جدًا. استخدم صورة لا تتجاوز 40 مليون بكسل.",
                )

        result = await run_in_threadpool(
            analyze_chart_image,
            temp_path,
            "XAUUSD",
            "M5",
        )
        return templates.TemplateResponse(
            request,
            "index.html",
            page_context(request, result=result),
        )
    except HTTPException:
        raise
    except AxisCalibrationError as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            page_context(request, error=str(exc), axis_retry=True),
            status_code=422,
        )
    except Exception as exc:
        logging.exception("SaleeM analysis failed")
        technical_message = str(exc).strip()
        safe_prefixes = (
            "متغير OPENAI_API_KEY",
            "تعذر جلب بيانات الفريمات",
            "خطأ خدمة التحليل",
            "لم ترجع خدمة التحليل",
            "بيانات السوق المتاحة",
            "تعذر معايرة حركة",
            "تعذر تكوين",
            "ملف SALEEM_FINAL_SPEC",
        )
        sensitive_markers = ("authorization", "api_key=", "/tmp/", "traceback", "bearer ")
        lowered = technical_message.lower()
        if technical_message.startswith(safe_prefixes):
            error_message = technical_message
        elif technical_message and not any(marker in lowered for marker in sensitive_markers):
            # نظهر السبب الفعلي المختصر بدل رسالة عامة تخفي المشكلة.
            error_message = f"تعذر إنشاء التحليل: {technical_message[:220]}"
        else:
            error_message = (
                "تعذر إنشاء التحليل بسبب خطأ داخلي في البيانات أو الرسم. "
                "تم تسجيل السبب في Railway للمراجعة."
            )
        return templates.TemplateResponse(
            request,
            "index.html",
            page_context(request, error=error_message),
            status_code=500,
        )
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
