import logging
import os
import re
import uuid
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
from app.services.market_data import market_status_snapshot
from app.services.system_status import fetch_openai_costs, system_status_store

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


@app.middleware("http")
async def track_anonymous_user(request: Request, call_next):
    """عدّ مستخدمًا مجهولًا عبر ملف تعريف ارتباط ثابت دون حفظ اسم أو عنوان IP."""
    path = request.url.path
    visitor_id = request.cookies.get("saleem_uid", "").strip()
    new_visitor = not visitor_id
    if new_visitor:
        visitor_id = uuid.uuid4().hex
    if not path.startswith("/static/") and path != "/health":
        try:
            system_status_store.touch_user(visitor_id)
        except Exception:
            logging.exception("SaleeM user counter failed; request will continue")
    response = await call_next(request)
    if new_visitor:
        response.set_cookie(
            "saleem_uid",
            visitor_id,
            max_age=31536000,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
        )
    return response


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
    try:
        summary = feedback_store.summary()
    except Exception:
        logging.exception("SaleeM feedback summary failed; using an empty summary")
        summary = {
            "average_rating": 0,
            "rating_count": 0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "open": 0,
            "no_trade": 0,
        }
    return {
        "request": request,
        "result": result,
        "error": error,
        "axis_retry": axis_retry,
        "summary": summary,
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
        "renderer": "saleem-authentic-educational-overlay-v3.67.0",
        "ui": "saleem-original-chart-overlay-ui-v3.67.0",
        "market_data": "Twelve Data: M5/M15/H1/H4",
        "openai_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "twelve_data_configured": bool(os.getenv("TWELVE_DATA_API_KEY", "").strip()),
        "cache_policy": "M5=4m,M15=14m,H1=55m,H4=4h",
        "cache_path": os.getenv("MARKET_DATA_CACHE_PATH", "/tmp/saleem_market_data_cache.json"),
        "analysis_cache_path": os.getenv("ANALYSIS_SNAPSHOT_CACHE_PATH", "/tmp/saleem_analysis_snapshot_cache.json"),
        "decision_pipeline": "original-chart+market-confirmation+reference-scenario+educational-overlay",
        "feedback_store_path": os.getenv("SALEEM_FEEDBACK_STORE_PATH", "/tmp/saleem_feedback_store.json"),
        "system_status_path": os.getenv("SALEEM_SYSTEM_STATUS_PATH", "/tmp/saleem_system_status.json"),
        "system_status_access": "direct-no-pin",
        "owner_email_configured": bool(owner_email()),
        "email_configured": email_configured(),
        "smtp_configured": False,
        "email_provider": delivery_provider(),
        "trade_mode": "dual-buy-sell-logic+adaptive-primary-scenario+confirmed-swing-limit-plans",
        "targets": 3,
        "dual_scenarios": "cards-below-image-active",
        "scalp_targets": "+5/+10 configurable points with structural barriers",
        "limit_recommendations": "stable-confirmed-swing-limit-plans-with-fixed-until-invalidation-targets",
        "support_resistance": "adaptive-decision-zone+nearest-outer-levels",
        "title": "تحليل SaleeM - XAUUSD - M5",
    }


@app.get("/api/summary")
async def summary_api():
    return feedback_store.summary()


@app.get("/api/system-status")
async def system_status_api():
    # تفتح لوحة حالة التطبيق مباشرة دون رمز سري.
    # لا تعيد الواجهة أي مفاتيح API أو قيم سرية.
    local = system_status_store.local_summary()
    official_costs = await run_in_threadpool(fetch_openai_costs)
    openai_local = local["openai_local"]
    if isinstance(official_costs, dict) and official_costs.get("status") == "connected":
        used_today = float(official_costs.get("used_today_usd") or 0)
        used_month = float(official_costs.get("used_month_usd") or 0)
        cost_source = "رسمي"
    else:
        used_today = float(openai_local.get("used_today_usd") or 0)
        used_month = float(openai_local.get("used_month_usd") or 0)
        cost_source = "تقديري"

    try:
        credit_total = float(os.getenv("OPENAI_CREDIT_USD", "").strip())
    except ValueError:
        credit_total = 0.0
    remaining = round(max(0.0, credit_total - used_month), 2) if credit_total > 0 else None

    return {
        "app": {
            "status": "يعمل",
            "version": __version__,
        },
        "users": local["users"],
        "market": market_status_snapshot(),
        "openai": {
            "status": "متصل" if os.getenv("OPENAI_API_KEY", "").strip() else "غير متصل",
            "balance_usd": remaining,
            "credit_total_usd": round(credit_total, 2) if credit_total > 0 else None,
            "used_today_usd": round(used_today, 4),
            "used_month_usd": round(used_month, 4),
            "last_analysis_usd": openai_local.get("last_analysis_usd", 0),
            "model": openai_local.get("model"),
            "cost_source": cost_source,
        },
        "system": {
            "cache": "يعمل",
            "last_error": "لا يوجد",
        },
    }


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
            # v3.67 accepts portrait, square and landscape charts. The uploaded
            # pixels remain the final background for the educational overlay.
            if min(width, height) < 280:
                raise HTTPException(
                    status_code=400,
                    detail="أبعاد صورة الشارت صغيرة جدًا. ارفع صورة أوضح لقراءة السعر والشكل العام.",
                )

        result = await run_in_threadpool(
            analyze_chart_image,
            temp_path,
            "XAUUSD",
            "M5",
        )
        system_status_store.record_analysis()
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
