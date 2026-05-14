"""Unit-тесты ``PastMistakesRetriever``."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import DecisionContext, ExitData
from core.postmortem.past_mistakes import (
    PastMistakesRetriever,
    summaries_to_prompt_text,
)


def _make_logger_with_trades(tmp_path: Path) -> TradeOutcomeLogger:
    """Создаём logger с 5 закрытыми сделками для теста.

    BTC-USDT × 3 (2 SL, 1 TP1)
    ETH-USDT × 2 (1 SL, 1 TIMEOUT)
    """
    log = TradeOutcomeLogger(tmp_path / "test.sqlite")

    def add(trade_id: str, symbol: str, side: str, exit_reason: str, pnl_pct: str) -> None:
        ctx = DecisionContext(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            entry_time_ms=1_700_000_000_000,
            entry_price=Decimal("80500"),
            size=Decimal("0.1"),
            signal_candidate={"x": 1},
            market_analyst={},
            sentiment_analyst={},
            risk_overseer={},
            macro_analyst={},
            coordinator={},
        )
        log.record_entry(ctx)
        # Уникальный exit_time_ms для DESC ordering
        offset = int(trade_id.split("_")[-1]) * 1000
        log.record_exit(
            trade_id,
            ExitData(
                exit_time_ms=1_700_000_900_000 + offset,
                exit_price=Decimal("80000"),
                pnl_usd=Decimal("-50") if "loss" in trade_id else Decimal("50"),
                pnl_pct=Decimal(pnl_pct),
                exit_reason=exit_reason,
                holding_time_min=15,
            ),
        )

    add("btc_loss_1", "BTC-USDT", "BUY", "SL", "-0.5")
    add("btc_loss_2", "BTC-USDT", "BUY", "SL", "-0.7")
    add("btc_win_3", "BTC-USDT", "BUY", "TP1", "1.5")  # not loss → не в recent_losses
    add("eth_loss_4", "ETH-USDT", "SELL", "SL", "-0.3")
    add("eth_loss_5", "ETH-USDT", "BUY", "TIMEOUT", "-0.1")

    return log


def test_find_similar_btc_returns_btc_losses(tmp_path: Path) -> None:
    log = _make_logger_with_trades(tmp_path)
    retriever = PastMistakesRetriever(log)
    results = retriever.find_similar(symbol="BTC-USDT", limit=5)
    assert len(results) == 2  # обе BTC SL'ки
    assert all(s.symbol == "BTC-USDT" for s in results)
    # DESC by exit_time → btc_loss_2 первая (offset больше)
    assert results[0].trade_id == "btc_loss_2"


def test_find_similar_eth_returns_eth_losses(tmp_path: Path) -> None:
    log = _make_logger_with_trades(tmp_path)
    retriever = PastMistakesRetriever(log)
    results = retriever.find_similar(symbol="ETH-USDT", limit=5)
    assert len(results) == 2
    reasons = {s.exit_reason for s in results}
    assert reasons == {"SL", "TIMEOUT"}


def test_find_similar_respects_limit(tmp_path: Path) -> None:
    log = _make_logger_with_trades(tmp_path)
    retriever = PastMistakesRetriever(log)
    results = retriever.find_similar(symbol="BTC-USDT", limit=1)
    assert len(results) == 1


def test_find_similar_unknown_symbol_empty(tmp_path: Path) -> None:
    log = _make_logger_with_trades(tmp_path)
    retriever = PastMistakesRetriever(log)
    results = retriever.find_similar(symbol="DOGE-USDT", limit=3)
    assert results == []


def test_find_similar_filters_exit_reasons(tmp_path: Path) -> None:
    """С exit_reasons=("SL",) — только SL, не TIMEOUT."""
    log = _make_logger_with_trades(tmp_path)
    retriever = PastMistakesRetriever(log)
    results = retriever.find_similar(symbol="ETH-USDT", limit=5, exit_reasons=("SL",))
    assert len(results) == 1
    assert results[0].exit_reason == "SL"


def test_find_similar_zero_limit_returns_empty(tmp_path: Path) -> None:
    log = _make_logger_with_trades(tmp_path)
    retriever = PastMistakesRetriever(log)
    assert retriever.find_similar(symbol="BTC-USDT", limit=0) == []


def test_summary_contains_key_data(tmp_path: Path) -> None:
    log = _make_logger_with_trades(tmp_path)
    retriever = PastMistakesRetriever(log)
    results = retriever.find_similar(symbol="BTC-USDT", limit=1)
    summary = results[0].summary
    assert "BUY" in summary
    assert "BTC-USDT" in summary
    assert "SL" in summary
    assert "%" in summary


def test_summaries_to_prompt_text_empty() -> None:
    assert summaries_to_prompt_text([]) == ""


def test_summaries_to_prompt_text_formatted(tmp_path: Path) -> None:
    log = _make_logger_with_trades(tmp_path)
    retriever = PastMistakesRetriever(log)
    results = retriever.find_similar(symbol="BTC-USDT", limit=2)
    text = summaries_to_prompt_text(results)
    assert "Past mistakes" in text
    assert "BTC-USDT" in text
    # Каждая строка в bullet формате
    assert text.count("- ") == 2


def test_empty_logger_returns_empty(tmp_path: Path) -> None:
    """Без записей → empty список."""
    log = TradeOutcomeLogger(tmp_path / "empty.sqlite")
    retriever = PastMistakesRetriever(log)
    assert retriever.find_similar(symbol="BTC-USDT") == []
