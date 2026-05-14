"""Диагностика конфигурации бота — что работает, что не настроено.

Не запускает сделки. Только проверяет:
- .env подгружается? Какие ключи присутствуют?
- BingX VST credentials — формат?
- Anthropic API ключ — формат?
- Опциональные источники (FRED, Groq, Apify, Telegram) — задано ли?
- Outcomes DB существует? Сколько записей?
- Зависимости (httpx, pydantic, etc) импортируются?

Запуск:
    .venv/bin/python -m scripts.diagnose

Output: текст в stdout с ✓ / ✗ / ⚠ маркерами для каждой проверки.
Exit code:
- 0 если все critical (Anthropic + BingX VST) ok
- 1 если что-то critical missing
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

OK = "✓"
FAIL = "✗"
WARN = "⚠"


def _check_env_file() -> tuple[bool, str]:
    """True если .env есть."""
    env = Path(".env")
    if env.exists():
        return True, f"{OK} .env найден ({env.absolute()})"
    return False, f"{FAIL} .env не найден — скопируй .env.example и заполни"


def _check_env_var(name: str, *, required: bool = False) -> tuple[bool, str]:
    """Проверка одной env-переменной (читает через pydantic, не os.getenv)."""
    import os

    value = os.getenv(name, "").strip()
    if value:
        last4 = value[-4:] if len(value) > 4 else "***"
        return True, f"{OK} {name} задан (...{last4})"
    marker = FAIL if required else WARN
    return False, f"{marker} {name} НЕ задан"


def _check_anthropic() -> tuple[bool, str]:
    """Anthropic через pydantic-settings (с .env поддержкой)."""
    try:
        from core.agents.settings import AnthropicSettings

        s = AnthropicSettings()
        if s.configured:
            assert s.api_key is not None
            last4 = s.api_key[-4:]
            return True, f"{OK} ANTHROPIC_API_KEY (...{last4})"
        return False, f"{FAIL} ANTHROPIC_API_KEY не задан — LLM-runner не запустится"
    except Exception as e:
        return False, f"{FAIL} AnthropicSettings ошибка: {e}"


def _check_fred() -> tuple[bool, str]:
    try:
        from parsers.macro.settings import FREDSettings

        s = FREDSettings()
        if s.configured:
            assert s.api_key is not None
            return True, f"{OK} FRED_API_KEY (...{s.api_key[-4:]})"
        return False, f"{WARN} FRED_API_KEY не задан — macro работает без FRED"
    except Exception as e:
        return False, f"{WARN} FREDSettings ошибка: {e}"


def _check_bingx() -> tuple[bool, str]:
    try:
        from adapters.bingx.settings import BingXSettings

        s = BingXSettings()
        env = s.env
        if env == "live":
            return False, f"{FAIL} BINGX_ENV=live — нельзя без явного подтверждения! Поставь vst."
        if not s.has_credentials():
            return False, f"{FAIL} BINGX_{env.upper()}_API_KEY/SECRET не заданы"
        return True, f"{OK} BingX {env} credentials присутствуют"
    except Exception as e:
        return False, f"{FAIL} BingXSettings ошибка: {e}"


def _check_telegram() -> tuple[bool, str]:
    try:
        from core.alerts.settings import TelegramSettings

        s = TelegramSettings()
        if s.configured:
            return True, f"{OK} Telegram настроен (chat_id обрезан)"
        return False, f"{WARN} TELEGRAM_BOT_TOKEN/CHAT_ID не заданы — алерты пойдут в stdout"
    except Exception as e:
        return False, f"{WARN} TelegramSettings ошибка: {e}"


def _check_dependencies() -> tuple[bool, list[str]]:
    """Проверка ключевых dependency-модулей."""
    modules = [
        "httpx",
        "pydantic",
        "pydantic_settings",
        "respx",
        "sqlite3",
    ]
    results: list[str] = []
    all_ok = True
    for mod in modules:
        try:
            importlib.import_module(mod)
            results.append(f"  {OK} {mod}")
        except ImportError:
            results.append(f"  {FAIL} {mod} — pip install отсутствует")
            all_ok = False
    return all_ok, results


def _check_outcomes_db(db_path: Path) -> tuple[bool, list[str]]:
    """Layer 6: outcomes journal."""
    if not db_path.exists():
        return True, [
            f"{WARN} Outcomes DB не существует ({db_path})",
            "    Будет создан при первом запуске llm_runner с --outcomes-db",
        ]
    try:
        from core.postmortem.logger import TradeOutcomeLogger

        log = TradeOutcomeLogger(db_path)
        all_outcomes = list(log.iter_all())
        wins = [o for o in all_outcomes if o.is_win]
        losses = [o for o in all_outcomes if o.is_loss]
        open_t = sum(1 for o in all_outcomes if not o.is_closed)
        return True, [
            f"{OK} Outcomes DB: {len(all_outcomes)} записей",
            f"    wins={len(wins)}, losses={len(losses)}, open={open_t}",
        ]
    except Exception as e:
        return False, [f"{FAIL} TradeOutcomeLogger ошибка: {e}"]


def run_diagnostics(*, outcomes_db: Path) -> int:
    """Печатает результаты. Возвращает exit code."""
    print("=" * 60)
    print("Crypto Bot — Diagnostic Report")
    print("=" * 60)

    critical_ok = True

    print("\n[1] .env file")
    env_ok, msg = _check_env_file()
    print(f"  {msg}")
    if not env_ok:
        critical_ok = False

    print("\n[2] Critical credentials")
    for check in (_check_anthropic, _check_bingx):
        ok, msg = check()
        print(f"  {msg}")
        if not ok:
            critical_ok = False

    print("\n[3] Optional data sources")
    for check in (_check_fred, _check_telegram):
        _, msg = check()
        print(f"  {msg}")

    print("\n[4] Optional API keys (env-only, no settings class)")
    for name in ("GROQ_API_KEY", "APIFY_TOKEN", "COINGLASS_API_KEY"):
        _, msg = _check_env_var(name, required=False)
        print(f"  {msg}")

    print("\n[5] Python dependencies")
    deps_ok, dep_lines = _check_dependencies()
    for line in dep_lines:
        print(line)
    if not deps_ok:
        critical_ok = False

    print("\n[6] Layer 6 outcomes journal")
    _, outcome_lines = _check_outcomes_db(outcomes_db)
    for line in outcome_lines:
        print(line)

    print("\n" + "=" * 60)
    if critical_ok:
        print(f"{OK} Critical checks passed — bot готов к запуску")
        print("  Запусти: python -m runners.llm_runner --strategy btc_breakout --dry-run")
        return 0
    print(f"{FAIL} Есть critical issues — bot не запустится")
    print("  Проверь .env и сообщения выше")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnostic check для бота")
    parser.add_argument(
        "--outcomes-db",
        default="ops/llm-outcomes.sqlite",
        help="Путь к outcomes SQLite для проверки",
    )
    args = parser.parse_args()
    sys.exit(run_diagnostics(outcomes_db=Path(args.outcomes_db)))


if __name__ == "__main__":
    main()
