from copy import deepcopy

from app.services.analyzer import _build_limit_recommendations, _market_frame_signal
from tests.test_limit_recommendations_v320 import _analysis


def _turning_bearish_frame():
    candles = []
    price = 4000.0
    # Older section rises slowly.
    for index in range(30):
        open_ = price
        close = price + 0.35
        candles.append({"open": open_, "high": close + 0.35, "low": open_ - 0.25, "close": close})
        price = close
    # Recent closed candles reverse sharply with lower highs/lows.
    for drop in (0.9, 1.1, 1.3, 1.5, 1.2, 1.4):
        open_ = price
        close = price - drop
        candles.append({"open": open_, "high": open_ + 0.18, "low": close - 0.30, "close": close})
        price = close
    return candles


def test_recent_bearish_reversal_is_not_hidden_by_older_bullish_history():
    signal = _market_frame_signal(_turning_bearish_frame())
    assert signal["direction"] == "هابط"
    assert signal["score"] < 0


def test_limit_plan_prices_stay_fixed_while_current_price_moves():
    first_analysis = _analysis()
    first = _build_limit_recommendations(first_analysis)

    second_analysis = deepcopy(first_analysis)
    second_analysis["current_price"] = 4051.25
    # Change rolling M5 volatility; confirmed H1 swing geometry must stay fixed.
    for candle in second_analysis["candles"][-8:]:
        candle["high"] += 1.8
        candle["low"] -= 1.8
    second = _build_limit_recommendations(second_analysis)

    for side in ("buy_limit", "sell_limit"):
        first_plan = first[side]
        second_plan = second[side]
        for key in ("entry", "stop_loss", "target_1", "target_2", "target_3", "plan_id"):
            assert first_plan[key] == second_plan[key]
        assert first_plan["locked"] is True
        assert "مؤكد" in first_plan["confirmation_label"]
        assert first_plan["guaranteed"] is False
        assert "إغلاق شمعة" in first_plan["invalidation_condition"]


def test_result_template_shows_explicit_confirmed_buy_and_sell_labels():
    from pathlib import Path

    html = (Path(__file__).resolve().parents[1] / "app" / "templates" / "index.html").read_text(encoding="utf-8")
    assert "شراء مؤكد" in html
    assert "بيع مؤكد" in html
    assert "ثابتة حتى الإلغاء" in html
    assert html.count('id="limit-recommendations-card"') == 1


def test_recent_bullish_reversal_is_not_hidden_by_older_bearish_history():
    bearish = _turning_bearish_frame()
    mirrored = []
    anchor = 8000.0
    for candle in bearish:
        mirrored.append(
            {
                "open": anchor - candle["open"],
                "high": anchor - candle["low"],
                "low": anchor - candle["high"],
                "close": anchor - candle["close"],
            }
        )
    signal = _market_frame_signal(mirrored)
    assert signal["direction"] == "صاعد"
    assert signal["score"] > 0
