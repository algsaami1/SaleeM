from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import httpx


_STATUS_LOCK = threading.Lock()
_MUSCAT = ZoneInfo("Asia/Muscat")


class SystemStatusStore:
    """مخزن خفيف لإحصاءات SaleeM دون حفظ أسماء أو بيانات شخصية."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(
            os.getenv(
                "SALEEM_SYSTEM_STATUS_PATH",
                "/tmp/saleem_system_status.json",
            ).strip()
        )

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "version": 1,
            "users": {},
            "analyses": [],
            "openai_requests": [],
        }

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty()
        if not isinstance(payload, dict):
            return self._empty()
        payload.setdefault("users", {})
        payload.setdefault("analyses", [])
        payload.setdefault("openai_requests", [])
        if not isinstance(payload["users"], dict):
            payload["users"] = {}
        if not isinstance(payload["analyses"], list):
            payload["analyses"] = []
        if not isinstance(payload["openai_requests"], list):
            payload["openai_requests"] = []
        return payload

    def _write(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    @staticmethod
    def _trim(payload: dict[str, Any], now_epoch: float) -> None:
        keep_after = now_epoch - (40 * 86400)
        payload["analyses"] = [
            item
            for item in payload.get("analyses", [])
            if isinstance(item, (int, float)) and float(item) >= keep_after
        ]
        payload["openai_requests"] = [
            item
            for item in payload.get("openai_requests", [])
            if isinstance(item, dict)
            and isinstance(item.get("timestamp"), (int, float))
            and float(item["timestamp"]) >= keep_after
        ]

    def touch_user(self, user_id: str) -> None:
        cleaned = str(user_id or "").strip()
        if not cleaned:
            return
        now_epoch = time.time()
        with _STATUS_LOCK:
            payload = self._read()
            users = payload["users"]
            existing = users.get(cleaned) if isinstance(users.get(cleaned), dict) else None
            # لا نكتب الملف مع كل طلب ثابت من المستخدم نفسه.
            if existing and now_epoch - float(existing.get("last_seen", 0) or 0) < 45:
                return
            users[cleaned] = {
                "first_seen": float(existing.get("first_seen", now_epoch)) if existing else now_epoch,
                "last_seen": now_epoch,
            }
            self._trim(payload, now_epoch)
            self._write(payload)

    def record_analysis(self) -> None:
        now_epoch = time.time()
        with _STATUS_LOCK:
            payload = self._read()
            payload["analyses"].append(now_epoch)
            self._trim(payload, now_epoch)
            self._write(payload)

    def record_openai_response(
        self,
        *,
        model: str,
        usage: Mapping[str, Any] | None,
        request_id: str = "",
    ) -> None:
        usage = usage if isinstance(usage, Mapping) else {}
        input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        input_details = usage.get("input_tokens_details")
        cached_tokens = 0
        if isinstance(input_details, Mapping):
            cached_tokens = int(input_details.get("cached_tokens") or 0)
        cost = estimate_openai_cost(
            model=model,
            input_tokens=input_tokens,
            cached_tokens=cached_tokens,
            output_tokens=output_tokens,
        )
        now_epoch = time.time()
        entry = {
            "timestamp": now_epoch,
            "model": model,
            "input_tokens": input_tokens,
            "cached_tokens": cached_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": round(cost, 8),
            "request_id": request_id[-24:] if request_id else "",
        }
        with _STATUS_LOCK:
            payload = self._read()
            payload["openai_requests"].append(entry)
            self._trim(payload, now_epoch)
            self._write(payload)

    def local_summary(self) -> dict[str, Any]:
        now_epoch = time.time()
        today = datetime.now(_MUSCAT).date()
        month_start = datetime.now(_MUSCAT).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        today_start = datetime.now(_MUSCAT).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        with _STATUS_LOCK:
            payload = self._read()
        users = payload.get("users", {})
        valid_users = [item for item in users.values() if isinstance(item, dict)]
        active_today = sum(
            1
            for item in valid_users
            if datetime.fromtimestamp(float(item.get("last_seen", 0) or 0), _MUSCAT).date() == today
        )
        online_now = sum(
            1
            for item in valid_users
            if now_epoch - float(item.get("last_seen", 0) or 0) <= 300
        )
        analyses = [float(value) for value in payload.get("analyses", []) if isinstance(value, (int, float))]
        requests = [item for item in payload.get("openai_requests", []) if isinstance(item, dict)]
        today_requests = [item for item in requests if float(item.get("timestamp", 0) or 0) >= today_start]
        month_requests = [item for item in requests if float(item.get("timestamp", 0) or 0) >= month_start]
        last_request = requests[-1] if requests else {}
        return {
            "users": {
                "total": len(valid_users),
                "today": active_today,
                "online": online_now,
                "analyses_today": sum(1 for value in analyses if value >= today_start),
            },
            "openai_local": {
                "used_today_usd": round(sum(float(item.get("estimated_cost_usd", 0) or 0) for item in today_requests), 4),
                "used_month_usd": round(sum(float(item.get("estimated_cost_usd", 0) or 0) for item in month_requests), 4),
                "last_analysis_usd": round(float(last_request.get("estimated_cost_usd", 0) or 0), 4),
                "model": str(last_request.get("model") or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")),
                "last_request_at": _format_oman_time(last_request.get("timestamp")),
            },
        }


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except ValueError:
        return default


def estimate_openai_cost(
    *,
    model: str,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
) -> float:
    """تكلفة تقريبية قابلة للتعديل من Railway عند تغيّر سعر النموذج."""
    default_rates = {
        "gpt-4.1-mini": (0.40, 0.10, 1.60),
        "gpt-4o-mini": (0.15, 0.075, 0.60),
    }
    input_rate, cached_rate, output_rate = default_rates.get(
        str(model or "").strip(),
        (0.40, 0.10, 1.60),
    )
    input_rate = _float_env("OPENAI_INPUT_USD_PER_MILLION", input_rate)
    cached_rate = _float_env("OPENAI_CACHED_USD_PER_MILLION", cached_rate)
    output_rate = _float_env("OPENAI_OUTPUT_USD_PER_MILLION", output_rate)
    cached = max(0, min(int(cached_tokens), int(input_tokens)))
    uncached = max(0, int(input_tokens) - cached)
    return (
        (uncached * input_rate)
        + (cached * cached_rate)
        + (max(0, int(output_tokens)) * output_rate)
    ) / 1_000_000


def _format_oman_time(value: Any) -> str | None:
    try:
        epoch = float(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(epoch, _MUSCAT).strftime("%Y-%m-%d %H:%M:%S")


def fetch_openai_costs() -> dict[str, Any] | None:
    """يجلب تكلفة المؤسسة الرسمية عند إضافة Admin API Key؛ لا يعيد مفاتيح سرية."""
    key = os.getenv("OPENAI_ADMIN_KEY", "").strip()
    if not key:
        return None

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    params = {
        "start_time": int(month_start.timestamp()),
        "end_time": int(now.timestamp()) + 1,
        "bucket_width": "1d",
        "limit": 31,
    }
    try:
        response = httpx.get(
            "https://api.openai.com/v1/organization/costs",
            params=params,
            headers={"Authorization": f"Bearer {key}"},
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return {"status": "error"}

    month_cost = 0.0
    today_cost = 0.0
    for bucket in payload.get("data", []) if isinstance(payload, dict) else []:
        if not isinstance(bucket, dict):
            continue
        bucket_cost = 0.0
        for item in bucket.get("results", []) if isinstance(bucket.get("results"), list) else []:
            if not isinstance(item, dict):
                continue
            amount = item.get("amount")
            if isinstance(amount, dict):
                try:
                    bucket_cost += float(amount.get("value") or 0)
                except (TypeError, ValueError):
                    pass
        month_cost += bucket_cost
        try:
            if float(bucket.get("start_time") or 0) >= today_start.timestamp():
                today_cost += bucket_cost
        except (TypeError, ValueError):
            pass

    return {
        "status": "connected",
        "used_today_usd": round(today_cost, 4),
        "used_month_usd": round(month_cost, 4),
    }


system_status_store = SystemStatusStore()
