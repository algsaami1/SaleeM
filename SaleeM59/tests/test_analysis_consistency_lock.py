from copy import deepcopy

from app.services.analyzer import (
    _bind_market_analysis_to_image,
    _closed_market_context,
    _market_snapshot_key,
    _read_cached_market_decision,
    _write_cached_market_decision,
)


def _candle(time_value: str, close: float = 4052.37):
    return {
        "time": time_value,
        "open": close - 0.2,
        "high": close + 0.4,
        "low": close - 0.5,
        "close": close,
    }


def _context(*, fetched_at: str = "2026-07-25T08:07:00+00:00"):
    return {
        "source": "Twelve Data",
        "symbol": "XAU/USD",
        "timezone": "Asia/Muscat",
        "fetched_at": fetched_at,
        "cache": {"volatile": fetched_at},
        "warnings": [],
        "frames": {
            "H4": [_candle("2026-07-25 00:00:00"), _candle("2026-07-25 04:00:00")],
            "H1": [_candle("2026-07-25 10:00:00"), _candle("2026-07-25 11:00:00")],
            "M15": [_candle("2026-07-25 11:30:00"), _candle("2026-07-25 11:45:00")],
            "M5": [
                _candle("2026-07-25 11:55:00", 4052.10),
                _candle("2026-07-25 12:00:00", 4052.37),  # last closed at 12:05
                _candle("2026-07-25 12:05:00", 4052.55),  # still forming at 12:07
            ],
        },
    }


def _canonical():
    return {
        "candles": [
            {"time": "t1", "open": 4052.0, "high": 4052.8, "low": 4051.8, "close": 4052.4},
        ],
        "current_price": 4052.4,
        "market_last_close": 4052.4,
        "direction": "هابط",
        "analysis_direction": "هابط",
        "trade_side": "بيع",
        "buy_probability": 42,
        "sell_probability": 58,
        "draw_mode": "conditional",
        "support_levels": [
            {"price": 4051.9, "strength": 75, "touches": 3},
            {"price": 4051.4, "strength": 65, "touches": 2},
        ],
        "resistance_levels": [
            {"price": 4052.8, "strength": 90, "touches": 4},
            {"price": 4053.5, "strength": 80, "touches": 3},
        ],
        "entry": 4052.5,
        "stop_loss": 4053.1,
        "target_1": 4052.0,
        "target_2": 4051.7,
        "target_3": 4051.3,
        "level_pressure": {"nearest_support": 4051.9, "nearest_resistance": 4052.8},
        "invalidation_condition": "نص قديم",
        "analysis_last_closed_m5_time": "2026-07-25 12:00:00",
        "analysis_candle_mode": "closed_only",
    }


def test_snapshot_key_uses_last_closed_m5_time_only():
    first = _context()
    second = deepcopy(first)
    second["fetched_at"] = "2026-07-25T08:08:00+00:00"
    second["cache"] = {"volatile": "changed"}
    second["frames"]["M5"][-1]["high"] += 3.0
    second["frames"]["M5"][-1]["low"] -= 3.0
    second["frames"]["M5"][-1]["close"] += 2.0

    assert _market_snapshot_key(first) == _market_snapshot_key(second)


def test_closed_context_excludes_forming_m5_candle():
    closed = _closed_market_context(_context())
    assert [item["time"] for item in closed["frames"]["M5"]] == [
        "2026-07-25 11:55:00",
        "2026-07-25 12:00:00",
    ]
    assert closed["m5_last_closed_candle_time"] == "2026-07-25 12:00:00"
    assert closed["analysis_candle_mode"] == "closed_only"


def test_snapshot_key_changes_only_after_new_m5_candle_closes():
    before_close = _context(fetched_at="2026-07-25T08:09:30+00:00")
    after_close = _context(fetched_at="2026-07-25T08:12:00+00:00")
    after_close["frames"]["M5"].append(_candle("2026-07-25 12:10:00", 4052.60))

    assert _market_snapshot_key(before_close) != _market_snapshot_key(after_close)
    closed = _closed_market_context(after_close)
    assert closed["m5_last_closed_candle_time"] == "2026-07-25 12:05:00"


def test_closed_candle_ohlc_correction_does_not_change_version_key():
    first = _context()
    corrected = deepcopy(first)
    corrected["frames"]["M5"][-2]["close"] += 0.15
    corrected["frames"]["M5"][-2]["high"] += 0.15
    assert _market_snapshot_key(first) == _market_snapshot_key(corrected)


def test_snapshot_cache_roundtrip(tmp_path, monkeypatch):
    cache_path = tmp_path / "analysis-cache.json"
    monkeypatch.setenv("ANALYSIS_SNAPSHOT_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("ANALYSIS_SNAPSHOT_CACHE_ENABLED", "1")
    decision = {"direction": "هابط", "entry": 4052.5}
    _write_cached_market_decision("snapshot-a", decision)
    loaded = _read_cached_market_decision("snapshot-a")
    assert loaded == decision
    loaded["entry"] = 1
    assert _read_cached_market_decision("snapshot-a") == decision


def test_binding_changes_only_price_coordinate_and_image_geometry():
    canonical = _canonical()
    untouched = deepcopy(canonical)
    geometry = {
        "chart_readable": True,
        "current_price": 4062.4,
        "current_price_y_ratio": 0.52,
        "image_price_high": 4066.0,
        "image_price_low": 4058.0,
        "image_axis_labels": [
            {"price": 4065.5, "y_ratio": 0.1},
            {"price": 4062.4, "y_ratio": 0.52},
            {"price": 4058.5, "y_ratio": 0.9},
        ],
    }
    result = _bind_market_analysis_to_image(
        canonical,
        geometry,
        snapshot_key="same-snapshot",
        snapshot_reused=True,
    )

    assert canonical == untouched
    assert result["direction"] == canonical["direction"]
    assert result["sell_probability"] == canonical["sell_probability"]
    assert result["entry"] == 4062.5
    assert result["stop_loss"] == 4063.1
    assert result["support_levels"][0]["price"] == 4061.9
    assert result["current_price"] == 4062.4
    assert result["current_price_y_ratio"] == 0.52
    assert result["analysis_snapshot_reused"] is True
    assert result["analysis_consistency_lock"] == "last_closed_m5"
    assert result["analysis_input_role"] == "market_data_only"
    assert result["image_input_role"] == "axis_geometry_only"


def test_same_snapshot_and_same_broker_price_keeps_one_analysis_across_zoom_levels():
    canonical = _canonical()
    zoomed = {
        "chart_readable": True,
        "current_price": 4052.37,
        "current_price_y_ratio": 0.48,
        "image_price_high": 4057.8,
        "image_price_low": 4049.4,
        "image_axis_labels": [
            {"price": 4057.79, "y_ratio": 0.08},
            {"price": 4052.59, "y_ratio": 0.46},
            {"price": 4049.47, "y_ratio": 0.90},
        ],
    }
    distant = {
        "chart_readable": True,
        "current_price": 4052.37,
        "current_price_y_ratio": 0.68,
        "image_price_high": 4064.17,
        "image_price_low": 4048.7,
        "image_axis_labels": [
            {"price": 4064.17, "y_ratio": 0.04},
            {"price": 4052.27, "y_ratio": 0.69},
            {"price": 4048.71, "y_ratio": 0.92},
        ],
    }
    a = _bind_market_analysis_to_image(canonical, zoomed, snapshot_key="k", snapshot_reused=False)
    b = _bind_market_analysis_to_image(canonical, distant, snapshot_key="k", snapshot_reused=True)

    for key in ("direction", "draw_mode", "buy_probability", "sell_probability", "entry", "stop_loss", "target_1", "target_2", "target_3"):
        assert a[key] == b[key]
    assert a["support_levels"] == b["support_levels"]
    assert a["resistance_levels"] == b["resistance_levels"]
    assert a["current_price_y_ratio"] != b["current_price_y_ratio"]
    assert a["image_axis_labels"] != b["image_axis_labels"]
