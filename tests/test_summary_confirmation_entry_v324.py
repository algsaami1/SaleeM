from pathlib import Path

from app.services.analyzer import (
    _build_breakout_summary,
    _build_limit_recommendations,
    _build_market_reading_comment,
    _validate_analysis,
)
from tests.test_limit_recommendations_v320 import _analysis


ROOT = Path(__file__).resolve().parents[1]


def _trend_candles(*, bullish: bool = True, count: int = 36):
    candles = []
    price = 4000.0
    step = 0.45 if bullish else -0.45
    for _ in range(count):
        open_ = price
        close = price + step
        if bullish:
            high = close + 0.25
            low = open_ - 0.20
        else:
            high = open_ + 0.20
            low = close - 0.25
        candles.append({"open": open_, "high": high, "low": low, "close": close})
        price = close
    return candles


def _confirmed_result(*, bullish: bool = True):
    candles = _trend_candles(bullish=bullish)
    current = float(candles[-1]["close"])
    direction = "صاعد" if bullish else "هابط"
    # Confirmed means the closed M5 candle has already crossed the trigger.
    entry = current - 0.50 if bullish else current + 0.50
    stop = current - 1.30 if bullish else current + 1.30
    targets = [current + value for value in (2.0, 3.0, 4.0)] if bullish else [current - value for value in (2.0, 3.0, 4.0)]
    supports = [{"price": current - 1.20, "strength": 80, "source": "market"}]
    resistances = [{"price": current + 1.20, "strength": 80, "source": "market"}]
    if bullish:
        resistances.insert(0, {"price": entry, "strength": 74, "source": "market"})
    else:
        supports.insert(0, {"price": entry, "strength": 74, "source": "market"})

    market_summary = {
        "frames": {
            name: {"direction": direction, "score": 1.5, "confidence": 86}
            for name in ("H4", "H1", "M15", "M5")
        },
        "alignment": 4,
        "warnings": [],
    }
    data = {
        "candles": candles,
        "current_price": current,
        "buy_probability": 78 if bullish else 22,
        "sell_probability": 22 if bullish else 78,
        "setup_state": "مؤكد",
        "entry": entry,
        "entry_kind": "اختراق",
        "confirmation": "إغلاق مؤكد عند مستوى التفعيل",
        "stop_loss": stop,
        "target_1": targets[0],
        "target_2": targets[1],
        "target_3": targets[2],
        "support_levels": supports,
        "resistance_levels": resistances,
    }
    return _validate_analysis(data, market_summary)


def test_complete_closed_candle_evidence_can_produce_confirmed_buy_and_sell():
    buy = _confirmed_result(bullish=True)
    sell = _confirmed_result(bullish=False)

    assert buy["draw_mode"] == "confirmed"
    assert buy["trade_side"] == "شراء مؤكد"
    assert sell["draw_mode"] == "confirmed"
    assert sell["trade_side"] == "بيع مؤكد"
    assert buy["confirmation_explanation"].startswith("اكتملت")
    assert sell["confirmation_explanation"].startswith("اكتملت")


def test_market_summary_is_short_reason_plus_numeric_breakout_levels_only(monkeypatch):
    import app.services.analyzer as analyzer

    monkeypatch.setattr(
        analyzer,
        "detect_market_zone_presence",
        lambda _analysis: {"order_block": True, "fvg": True},
    )
    result = _confirmed_result(bullish=True)

    reason = _build_market_reading_comment(result)
    breakout = _build_breakout_summary(result)

    assert reason.startswith("القراءة تميل للصعود")
    assert "السيولة" in reason
    assert "منطقة أوامر" in reason
    assert "فجوة سعرية" in reason
    assert "TP1" not in reason and "TP2" not in reason and "TP3" not in reason
    assert "فوق" in breakout
    assert "صعود" in breakout
    assert "هبوط" in breakout


def test_limit_reason_explains_confluence_without_repeating_target_prices(monkeypatch):
    import app.services.analyzer as analyzer

    monkeypatch.setattr(
        analyzer,
        "detect_market_zone_presence",
        lambda _analysis: {"order_block": True, "fvg": True},
    )
    analysis = _analysis()
    result = _build_limit_recommendations(analysis)
    buy = result["buy_limit"]

    assert "سيولة" in buy["reason"]
    assert "منطقة أوامر" in buy["reason"]
    assert "فجوة سعرية" in buy["reason"]
    assert str(buy["target_1"]) not in buy["reason"]
    assert buy["entry_outside_loss_zone"] is True


def test_ui_explanation_hides_target_numbers_and_renderer_separates_entry_from_red_zone():
    html = (ROOT / "app" / "templates" / "index.html").read_text(encoding="utf-8")
    renderer = (ROOT / "app" / "engine" / "renderer.py").read_text(encoding="utf-8")

    assert "analysis-breakout-line" in html
    assert "التفعيل" in html
    assert "أهم النقاط فقط" in html
    assert "ملخص النتيجة" in html
    assert "لا يوجد كسر مؤكد حاليًا." not in html
    assert "entry_gap = 7" in renderer
    assert "Entry is the boundary" in renderer
nderer
