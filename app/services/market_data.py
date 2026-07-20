from __future__ import annotations

import copy
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import httpx


DEFAULT_FRAME_COUNTS: dict[str, int] = {
    "M5": 200,
    "M15": 200,
    "H1": 200,
    "H4": 150,
}

INTERVALS: dict[str, str] = {
    "M5": "5min",
    "M15": "15min",
    "H1": "1h",
    "H4": "4h",
}

# نحدّث كل فريم قبل اكتمال شمعته التالية بقليل.
DEFAULT_CACHE_TTLS: dict[str, int] = {
    "M5": 240,      # 4 دقائق
    "M15": 840,     # 14 دقيقة
    "H1": 3300,     # 55 دقيقة
    "H4": 14400,    # 4 ساعات
}

CACHE_VERSION = 3
_CACHE_LOCK = threading.Lock()


class MarketDataError(RuntimeError):
    """خطأ واضح عند تعذر جلب بيانات السوق أو التحقق منها."""


@dataclass(frozen=True)
class TwelveDataConfig:
    api_key: str
    base_url: str = "https://api.twelvedata.com"
    symbol: str = "XAU/USD"
    timezone_name: str = "UTC"
    timeout_seconds: float = 30.0
    retries: int = 3
    cache_path: Path = Path("/tmp/saleem_market_data_cache.json")
    cache_ttls: Mapping[str, int] | None = None

    @classmethod
    def from_env(cls) -> "TwelveDataConfig":
        api_key = os.getenv("TWELVE_DATA_API_KEY", "").strip()
        if not api_key:
            raise MarketDataError(
                "متغير TWELVE_DATA_API_KEY غير موجود في Railway Variables."
            )

        base_url = os.getenv(
            "TWELVE_DATA_BASE_URL",
            "https://api.twelvedata.com",
        ).strip().rstrip("/")

        symbol = os.getenv("TWELVE_DATA_SYMBOL", "XAU/USD").strip()
        timezone_name = os.getenv("TWELVE_DATA_TIMEZONE", "UTC").strip()
        cache_path = Path(
            os.getenv(
                "MARKET_DATA_CACHE_PATH",
                "/tmp/saleem_market_data_cache.json",
            ).strip()
        )

        try:
            timeout_seconds = float(
                os.getenv("TWELVE_DATA_TIMEOUT_SECONDS", "30")
            )
            retries = int(os.getenv("TWELVE_DATA_RETRIES", "3"))
            cache_ttls = {
                "M5": int(os.getenv("MARKET_DATA_CACHE_M5_SECONDS", "240")),
                "M15": int(os.getenv("MARKET_DATA_CACHE_M15_SECONDS", "840")),
                "H1": int(os.getenv("MARKET_DATA_CACHE_H1_SECONDS", "3300")),
                "H4": int(os.getenv("MARKET_DATA_CACHE_H4_SECONDS", "14400")),
            }
        except ValueError as exc:
            raise MarketDataError(
                "أحد متغيرات Twelve Data أو التخزين المؤقت غير صحيح."
            ) from exc

        return cls(
            api_key=api_key,
            base_url=base_url,
            symbol=symbol,
            timezone_name=timezone_name or "UTC",
            timeout_seconds=max(5.0, timeout_seconds),
            retries=max(1, min(5, retries)),
            cache_path=cache_path,
            cache_ttls={
                frame: max(30, min(86400, seconds))
                for frame, seconds in cache_ttls.items()
            },
        )


class TwelveDataClient:
    """جلب شموع الذهب من Twelve Data دون تنفيذ أوامر تداول."""

    def __init__(self, config: TwelveDataConfig | None = None) -> None:
        self.config = config or TwelveDataConfig.from_env()
        self._client = httpx.Client(
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
            headers={
                "Accept": "application/json",
                "User-Agent": "SaleeM-Gold-Analyst/2.4",
            },
        )
        self.last_credit_info: dict[str, str | None] = {
            "used": None,
            "left": None,
        }

    def __enter__(self) -> "TwelveDataClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _request_json(
        self,
        endpoint: str,
        params: Mapping[str, Any],
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        request_params = dict(params)
        request_params["apikey"] = self.config.api_key

        for attempt in range(1, self.config.retries + 1):
            try:
                response = self._client.get(endpoint, params=request_params)
                self.last_credit_info = {
                    "used": response.headers.get("api-credits-used"),
                    "left": response.headers.get("api-credits-left"),
                }

                try:
                    payload = response.json()
                except ValueError as exc:
                    raise MarketDataError(
                        "استجابة Twelve Data ليست JSON صالحًا."
                    ) from exc

                if response.status_code == 200:
                    if not isinstance(payload, dict):
                        raise MarketDataError(
                            "استجابة Twelve Data ليست كائنًا صالحًا."
                        )
                    if str(payload.get("status", "")).lower() == "error":
                        raise MarketDataError(
                            "خطأ Twelve Data "
                            f"({payload.get('code')}): "
                            f"{payload.get('message') or 'خطأ غير معروف'}"
                        )
                    return payload

                message = ""
                if isinstance(payload, dict):
                    message = str(
                        payload.get("message")
                        or payload.get("status")
                        or ""
                    )

                if response.status_code in {401, 403}:
                    raise MarketDataError(
                        "مفتاح Twelve Data غير صالح أو لا يملك صلاحية "
                        f"الوصول إلى {self.config.symbol}."
                    )
                if response.status_code == 429:
                    last_error = MarketDataError(
                        "تم بلوغ حد Twelve Data المؤقت."
                    )
                elif 500 <= response.status_code < 600:
                    last_error = MarketDataError(
                        "خدمة Twelve Data غير متاحة مؤقتًا "
                        f"({response.status_code})."
                    )
                else:
                    raise MarketDataError(
                        f"فشل طلب Twelve Data ({response.status_code}): "
                        f"{message or 'خطأ غير معروف'}"
                    )

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc

            if attempt < self.config.retries:
                time.sleep(min(4.0, 0.75 * (2 ** (attempt - 1))))

        raise MarketDataError(
            f"تعذر الاتصال بـ Twelve Data بعد {self.config.retries} محاولات."
        ) from last_error

    def fetch_candles(
        self,
        timeframe: str,
        count: int,
    ) -> list[dict[str, Any]]:
        timeframe = timeframe.strip().upper()
        interval = INTERVALS.get(timeframe)
        if interval is None:
            raise MarketDataError(
                f"الفريم {timeframe} غير مدعوم. المتاح: {', '.join(INTERVALS)}."
            )
        if not 2 <= count <= 5000:
            raise MarketDataError("عدد الشموع يجب أن يكون بين 2 و5000.")

        payload = self._request_json(
            "/time_series",
            params={
                "symbol": self.config.symbol,
                "interval": interval,
                "outputsize": int(count),
                "format": "JSON",
                "order": "asc",
                "timezone": self.config.timezone_name,
                "dp": 5,
            },
        )

        raw_values = payload.get("values")
        if not isinstance(raw_values, list):
            raise MarketDataError(
                f"لم تُرجع Twelve Data شموعًا لفريم {timeframe}."
            )

        candles: list[dict[str, Any]] = []
        for raw in raw_values:
            if not isinstance(raw, dict):
                continue
            try:
                open_price = float(raw["open"])
                high_price = float(raw["high"])
                low_price = float(raw["low"])
                close_price = float(raw["close"])
            except (KeyError, TypeError, ValueError):
                continue

            true_high = max(high_price, open_price, close_price)
            true_low = min(low_price, open_price, close_price)
            if true_high <= true_low:
                continue

            volume_value = raw.get("volume")
            try:
                volume = int(float(volume_value)) if volume_value is not None else 0
            except (TypeError, ValueError):
                volume = 0

            candles.append(
                {
                    "time": str(raw.get("datetime") or ""),
                    "open": round(open_price, 3),
                    "high": round(true_high, 3),
                    "low": round(true_low, 3),
                    "close": round(close_price, 3),
                    "volume": max(0, volume),
                }
            )

        minimum_required = min(20, max(2, count // 4))
        if len(candles) < minimum_required:
            raise MarketDataError(
                f"عدد شموع {timeframe} الصالحة قليل جدًا: {len(candles)}."
            )
        return candles


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_cache(config: TwelveDataConfig) -> dict[str, Any]:
    return {
        "version": CACHE_VERSION,
        "source": "Twelve Data",
        "symbol": config.symbol,
        "timezone": config.timezone_name,
        "saved_at": None,
        "frames": {},
    }


def _delete_cache_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _load_cache(config: TwelveDataConfig) -> dict[str, Any]:
    path = config.cache_path
    if not path.exists():
        return _empty_cache(config)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _delete_cache_file(path)
        return _empty_cache(config)

    if not isinstance(payload, dict):
        _delete_cache_file(path)
        return _empty_cache(config)

    if (
        payload.get("version") != CACHE_VERSION
        or payload.get("source") != "Twelve Data"
        or payload.get("symbol") != config.symbol
        or payload.get("timezone") != config.timezone_name
        or not isinstance(payload.get("frames"), dict)
    ):
        _delete_cache_file(path)
        return _empty_cache(config)
    return payload


def _write_cache_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
    except OSError as exc:
        raise MarketDataError(
            f"تعذر حفظ ملف بيانات السوق في {path}."
        ) from exc


def _cached_candles(entry: Any, required_count: int) -> list[dict[str, Any]] | None:
    if not isinstance(entry, dict):
        return None
    candles = entry.get("candles")
    if not isinstance(candles, list) or len(candles) < required_count:
        return None
    return candles[-required_count:]


def _entry_is_fresh(entry: Any, now_epoch: float, required_count: int) -> bool:
    candles = _cached_candles(entry, required_count)
    expires_at = entry.get("expires_at_epoch") if isinstance(entry, dict) else None
    return (
        candles is not None
        and isinstance(expires_at, (int, float))
        and now_epoch < float(expires_at)
    )


def fetch_market_data(
    frame_counts: Mapping[str, int] | None = None,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    يجلب فقط الفريمات المنتهية صلاحيتها ويحفظها داخل ملف JSON واحد.

    عند تعطل المزود مؤقتًا، يستخدم آخر نسخة محفوظة للفريم المنتهي بدل إيقاف
    التحليل، ويعلّمها بالحالة stale_fallback كي يعرف المحلل أنها قديمة.
    """
    config = TwelveDataConfig.from_env()
    requested = {
        str(frame).strip().upper(): int(count)
        for frame, count in dict(frame_counts or DEFAULT_FRAME_COUNTS).items()
    }
    unknown_frames = set(requested) - set(INTERVALS)
    if unknown_frames:
        raise MarketDataError(
            "فريمات غير مدعومة: " + ", ".join(sorted(unknown_frames))
        )

    now_epoch = time.time()
    cache_ttls = dict(config.cache_ttls or DEFAULT_CACHE_TTLS)

    with _CACHE_LOCK:
        cache = _load_cache(config)
        cached_frames = cache.setdefault("frames", {})
        result_frames: dict[str, list[dict[str, Any]]] = {}
        cache_status: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        refreshed_any = False
        client: TwelveDataClient | None = None
        last_credit_info: dict[str, str | None] = {"used": None, "left": None}

        try:
            for timeframe, count in requested.items():
                entry = cached_frames.get(timeframe)
                if (
                    not force_refresh
                    and _entry_is_fresh(entry, now_epoch, count)
                ):
                    result_frames[timeframe] = copy.deepcopy(
                        _cached_candles(entry, count) or []
                    )
                    cache_status[timeframe] = {
                        "status": "cached",
                        "fetched_at": entry.get("fetched_at"),
                        "expires_at": entry.get("expires_at"),
                        "ttl_seconds": cache_ttls[timeframe],
                    }
                    continue

                try:
                    if client is None:
                        client = TwelveDataClient(config)
                    candles = client.fetch_candles(timeframe, count)
                    fetched_epoch = time.time()
                    expires_epoch = fetched_epoch + cache_ttls[timeframe]
                    fetched_at = datetime.fromtimestamp(
                        fetched_epoch, tz=timezone.utc
                    ).isoformat()
                    expires_at = datetime.fromtimestamp(
                        expires_epoch, tz=timezone.utc
                    ).isoformat()

                    cached_frames[timeframe] = {
                        "fetched_at": fetched_at,
                        "fetched_at_epoch": fetched_epoch,
                        "expires_at": expires_at,
                        "expires_at_epoch": expires_epoch,
                        "count": len(candles),
                        "candles": candles,
                    }
                    result_frames[timeframe] = copy.deepcopy(candles)
                    cache_status[timeframe] = {
                        "status": "updated",
                        "fetched_at": fetched_at,
                        "expires_at": expires_at,
                        "ttl_seconds": cache_ttls[timeframe],
                    }
                    refreshed_any = True
                    last_credit_info = dict(client.last_credit_info)

                except MarketDataError as exc:
                    stale = _cached_candles(entry, count)
                    if stale is None:
                        raise
                    result_frames[timeframe] = copy.deepcopy(stale)
                    cache_status[timeframe] = {
                        "status": "stale_fallback",
                        "fetched_at": entry.get("fetched_at"),
                        "expires_at": entry.get("expires_at"),
                        "ttl_seconds": cache_ttls[timeframe],
                    }
                    warnings.append(f"{timeframe}: {exc}")
        finally:
            if client is not None:
                client.close()

        if refreshed_any:
            cache["saved_at"] = _utc_now_iso()
            cache["frames"] = cached_frames
            _write_cache_atomic(config.cache_path, cache)

        latest_times = [
            candles[-1]["time"]
            for candles in result_frames.values()
            if candles
        ]
        return {
            "source": "Twelve Data",
            "symbol": config.symbol,
            "timezone": config.timezone_name,
            "fetched_at": _utc_now_iso(),
            "latest_candle_time": max(latest_times) if latest_times else None,
            "frames": result_frames,
            "cache": {
                "path": str(config.cache_path),
                "persistent": str(config.cache_path).startswith("/data/"),
                "frames": cache_status,
            },
            "warnings": warnings,
            "credit_info": last_credit_info,
        }


def clear_market_data_cache() -> bool:
    """حذف ملف التخزين المؤقت يدويًا عند الحاجة."""
    config = TwelveDataConfig.from_env()
    with _CACHE_LOCK:
        existed = config.cache_path.exists()
        _delete_cache_file(config.cache_path)
        return existed


def compact_market_context(
    market_data: Mapping[str, Any],
    *,
    candles_per_frame: int = 120,
) -> dict[str, Any]:
    """تقليل البيانات قبل إرسالها إلى OpenAI لتقليل حجم الطلب."""
    raw_frames = market_data.get("frames")
    if not isinstance(raw_frames, Mapping):
        raise MarketDataError("market_data لا يحتوي على frames صالحة.")

    keep = max(20, min(500, int(candles_per_frame)))
    compact_frames: dict[str, list[dict[str, Any]]] = {}
    for timeframe, candles in raw_frames.items():
        if isinstance(candles, list):
            compact_frames[str(timeframe)] = candles[-keep:]

    return {
        "source": market_data.get("source"),
        "symbol": market_data.get("symbol"),
        "timezone": market_data.get("timezone"),
        "fetched_at": market_data.get("fetched_at"),
        "latest_candle_time": market_data.get("latest_candle_time"),
        "cache": market_data.get("cache"),
        "warnings": market_data.get("warnings"),
        "frames": compact_frames,
    }
