import json
from pathlib import Path

from app.services import market_data


def _candles(count: int, start: float = 4000.0):
    result = []
    price = start
    for index in range(count):
        result.append(
            {
                "time": f"2026-07-20 00:{index:02d}:00",
                "open": price,
                "high": price + 1.0,
                "low": price - 0.5,
                "close": price + 0.4,
                "volume": 10,
            }
        )
        price += 0.4
    return result


def test_disk_cache_reuses_fresh_frames(monkeypatch, tmp_path: Path):
    cache_path = tmp_path / "market.json"
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    monkeypatch.setenv("MARKET_DATA_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("MARKET_DATA_CACHE_M5_SECONDS", "600")
    monkeypatch.setenv("MARKET_DATA_CACHE_H4_SECONDS", "600")

    calls: list[str] = []

    def fake_fetch(self, timeframe: str, count: int):
        calls.append(timeframe)
        return _candles(count, 4000.0 if timeframe == "M5" else 3900.0)

    monkeypatch.setattr(market_data.TwelveDataClient, "fetch_candles", fake_fetch)

    first = market_data.fetch_market_data({"M5": 30, "H4": 30})
    second = market_data.fetch_market_data({"M5": 30, "H4": 30})

    assert calls == ["M5", "H4"]
    assert cache_path.exists()
    assert first["cache"]["frames"]["M5"]["status"] == "updated"
    assert second["cache"]["frames"]["M5"]["status"] == "cached"


def test_only_expired_frame_is_replaced(monkeypatch, tmp_path: Path):
    cache_path = tmp_path / "market.json"
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    monkeypatch.setenv("MARKET_DATA_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("MARKET_DATA_CACHE_M5_SECONDS", "600")
    monkeypatch.setenv("MARKET_DATA_CACHE_H4_SECONDS", "600")

    calls: list[str] = []

    def fake_fetch(self, timeframe: str, count: int):
        calls.append(timeframe)
        return _candles(count)

    monkeypatch.setattr(market_data.TwelveDataClient, "fetch_candles", fake_fetch)
    market_data.fetch_market_data({"M5": 30, "H4": 30})
    calls.clear()

    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    payload["frames"]["M5"]["expires_at_epoch"] = 0
    cache_path.write_text(json.dumps(payload), encoding="utf-8")

    result = market_data.fetch_market_data({"M5": 30, "H4": 30})

    assert calls == ["M5"]
    assert result["cache"]["frames"]["M5"]["status"] == "updated"
    assert result["cache"]["frames"]["H4"]["status"] == "cached"
