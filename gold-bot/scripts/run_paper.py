"""Запуск paper-runner'а на VPS.

Использование:
    python -m scripts.run_paper                       # config/paper.yaml + risk.yaml
    python -m scripts.run_paper --dry-run             # одна итерация и выход (smoke)
    python -m scripts.run_paper --once                # один цикл step() и выход

Никаких реальных ордеров не делает (CLAUDE.md §6, plan 06). Адаптер
используется только для fetch_markets/fetch_ohlcv.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal

from exchanges.bingx import BingXAdapter
from exchanges.bybit import BybitAdapter
from exchanges.ccxt_base import CcxtAdapter
from exchanges.logging_utils import configure_logging
from paper.config import load_paper_config
from paper.journal import PaperJournal
from paper.reporter import build_reporter_from_env
from paper.runner import PaperRunner
from risk.config import load_risk_config
from strategies.mean_reversion_vwap.config import load_params
from strategies.mean_reversion_vwap.strategy import MeanReversionVWAP


def _build_adapter(exchange: str) -> CcxtAdapter:
    # Для paper берём публичные котировки с продакшна; ключи не нужны.
    if exchange == "bingx":
        return BingXAdapter("", "", vst=False)
    return BybitAdapter("", "", testnet=False)


async def _main(once: bool, dry_run: bool) -> None:
    cfg = load_paper_config()
    risk_cfg = load_risk_config()
    params = load_params()
    secrets = [
        os.environ.get("GOLDBOT_TG_TOKEN", ""),
        os.environ.get("BINGX_LIVE_API_KEY", ""),
        os.environ.get("BINGX_LIVE_API_SECRET", ""),
        os.environ.get("BYBIT_LIVE_API_KEY", ""),
        os.environ.get("BYBIT_LIVE_API_SECRET", ""),
    ]
    configure_logging(level=logging.INFO, secrets=secrets)
    log = logging.getLogger("gold_bot")
    adapter = _build_adapter(cfg.exchange)
    journal = PaperJournal(cfg.journal_path)
    reporter = build_reporter_from_env()
    runner = PaperRunner(
        adapter=adapter,
        cfg=cfg,
        risk_cfg=risk_cfg,
        strategy_factory=lambda _sym: MeanReversionVWAP(params, risk_cfg.risk_pct_base),
        journal=journal,
        reporter=reporter,
    )
    try:
        if dry_run:
            await runner.warmup()
            log.info("paper.dry_run.done")
            return
        if once:
            await runner.warmup()
            snaps = await runner.step()
            log.info("paper.once.done snapshots=%d", len(snaps))
            return

        stop = asyncio.Event()

        def _on_signal() -> None:
            log.info("paper.signal.stop")
            stop.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _on_signal)
        await runner.run_forever(stop_event=stop)
    finally:
        await adapter.close()
        journal.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper-runner gold-bot")
    parser.add_argument(
        "--once", action="store_true", help="Один цикл step() и выйти (для CI/смоука)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Только warmup, без polling-цикла")
    args = parser.parse_args()
    asyncio.run(_main(once=args.once, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
