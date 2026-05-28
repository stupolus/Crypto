"""Тесты Donchian-breakout (синтетика, без сети)."""

from __future__ import annotations

from decimal import Decimal

from exchanges.models import OHLCV, OrderSide
from indicators.core import atr
from strategies.donchian_breakout.config import StrategyParams, load_params
from strategies.donchian_breakout.strategy import DonchianBreakout

RISK = Decimal("0.005")


def _p(**ov: object) -> StrategyParams:
    base: dict[str, object] = {
        "donchian_window": 3,
        "atr_period": 2,
        "k_stop": Decimal("2"),
        "k_tp": Decimal("3"),
        "cooldown_bars": 0,  # тесты пробоя по умолчанию без cooldown
        "session_start_hour_utc": 0,
        "session_end_hour_utc": 24,
        "asset_class": "metals",
    }
    base.update(ov)
    return StrategyParams.model_validate(base)


def _c(i: int, o: str, h: str, low: str, c: str) -> OHLCV:
    return OHLCV(
        timestamp=i * 900_000,  # 15m шаг
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal("1000"),
    )


def _flat(n: int) -> list[OHLCV]:
    """N свечей в узком диапазоне 99-101 — never breaks out."""
    return [_c(i, "100", "101", "99", "100") for i in range(n)]


def test_long_when_close_breaks_above_upper() -> None:
    # 3  «спокойных» бара + 4-й резкий бар с close > 101 (high прежних трёх)
    hist = [*_flat(3), _c(3, "100", "110", "100", "108")]
    strat = DonchianBreakout(_p(), RISK)
    a = atr(hist, 2)[-1]
    sig = strat.on_candle(hist)
    assert sig is not None
    assert sig.side is OrderSide.BUY
    assert sig.stop == Decimal("108") - Decimal("2") * a
    assert sig.take_profit == Decimal("108") + Decimal("3") * a
    assert sig.risk_pct == RISK
    assert sig.asset_class == "metals"


def test_no_signal_when_inside_channel() -> None:
    # Все бары в [99, 101] — последний close 100 не превышает upper 101
    hist = _flat(5)
    strat = DonchianBreakout(_p(), RISK)
    assert strat.on_candle(hist) is None


def test_no_signal_when_close_equals_upper() -> None:
    # Граничный случай: close == prior upper. Не пробой (строгое >).
    hist = [*_flat(3), _c(3, "100", "101", "100", "101")]
    strat = DonchianBreakout(_p(), RISK)
    assert strat.on_candle(hist) is None


def test_no_signal_out_of_session() -> None:
    # Окно 8-9: 4 бара в часе 0 — пробой отвергаем по сессии
    hist = [*_flat(3), _c(3, "100", "110", "100", "108")]
    strat = DonchianBreakout(_p(session_start_hour_utc=8, session_end_hour_utc=9), RISK)
    assert strat.on_candle(hist) is None


def test_no_signal_insufficient_data() -> None:
    # Меньше чем donchian_window+1 свечей
    strat = DonchianBreakout(_p(), RISK)
    assert strat.on_candle(_flat(2)) is None
    assert strat.on_candle(_flat(3)) is None  # ровно donchian_window, но < +1


def test_cooldown_blocks_back_to_back() -> None:
    # cooldown_bars=3: после сигнала 3 следующих бара не эмитят даже если пробой
    strat = DonchianBreakout(_p(cooldown_bars=3), RISK)
    # 3 flat + 4-й = пробой → сигнал
    h1 = [*_flat(3), _c(3, "100", "110", "100", "108")]
    assert strat.on_candle(h1) is not None
    # 5-й бар: ещё пробой (close 109 > prior max 110? нет, 109 < 110; берём 115)
    h2 = [*h1, _c(4, "108", "115", "108", "115")]
    assert strat.on_candle(h2) is None  # cooldown 1
    h3 = [*h2, _c(5, "115", "120", "115", "120")]
    assert strat.on_candle(h3) is None  # cooldown 2
    h4 = [*h3, _c(6, "120", "125", "120", "125")]
    # 3 бара с момента сигнала прошло → cooldown снят (bars_since == cooldown_bars)
    assert strat.on_candle(h4) is not None


def test_lookahead_bias_safe() -> None:
    # Канал должен строиться по history[:-1]. Если последний бар имеет
    # экстремальный high, он НЕ должен попадать в окно расчёта upper.
    # Иначе close никогда не сможет быть > upper (close ≤ high того же бара).
    # 3 спокойных + бар с close 108 (high 110): если бы learner подсматривал
    # в текущий бар, upper стал бы 110, и close 108 < 110 → no signal.
    # Корректная реализация: upper из прошлых 3 = 101 < close 108 → signal.
    hist = [*_flat(3), _c(3, "100", "110", "100", "108")]
    strat = DonchianBreakout(_p(), RISK)
    assert strat.on_candle(hist) is not None  # подтверждает что lookahead отсутствует


def test_config_loads_real_params() -> None:
    p = load_params()
    assert p.donchian_window == 50
    assert p.atr_period == 14
    assert p.k_stop == Decimal("2.0")
    assert p.k_tp == Decimal("3.5")
    assert p.session_start_hour_utc == 7
