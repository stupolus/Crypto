# Telegram alerts setup

**Статус:** skeleton реализован в `core/alerts/channels.py::TelegramAlerter`. Полная отправка через httpx — отложена.

Эта инструкция — для будущего, когда мы захотим включить Telegram-алерты на критичные события (D3+).

---

## 1. Создать Telegram-бота

1. В Telegram открыть [@BotFather](https://t.me/BotFather).
2. Команда: `/newbot`.
3. Имя бота: например `crypto-alerts-<your-username>-bot`.
4. **Сохранить `bot_token`** (выглядит как `123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`).

## 2. Узнать `chat_id`

1. Создать в Telegram приватный канал (или просто личный чат с ботом).
2. Добавить бота в канал как админа (с правом «Post Messages»).
3. Послать любое сообщение в канал.
4. Открыть в браузере: `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. В JSON-ответе найти `"chat":{"id":-1001234567890,...}` — это `chat_id`.

## 3. Положить в `.env`

```bash
# Только для live alerts, не нужно на dev/test
TELEGRAM_BOT_TOKEN=123456789:ABC-DEF1234ghIkl...
TELEGRAM_CHAT_ID=-1001234567890
```

`.env` в `.gitignore` — токен не уйдёт в репо.

## 4. Что нужно дописать в код

Сейчас `TelegramAlerter.send()` — TODO. Полная реализация:

```python
import httpx

async def send(self, severity: Severity, message: str) -> None:
    if not self._bot_token or not self._chat_id:
        return
    url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
    payload = {
        "chat_id": self._chat_id,
        "text": f"[{severity}] {message}",
        "parse_mode": "HTML",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.post(url, json=payload)
            r.raise_for_status()
        except Exception as exc:
            logger.warning("Telegram send failed: %s", exc)
            # Не падаем — алерт не должен ломать стратегию.
```

Плюс:
- Rate limiting (Telegram даёт 30 msg/sec per bot).
- Retry на 429.
- Optional: `disable_notification` для INFO-уровня.

## 5. Когда подключить

Не сейчас. Для:
1. D3 (4 недели demo) — alerter уже создан как `StdoutAlerter`. Видно через `journalctl` если на VPS.
2. **Перед live** — обязательно. Без алертов нельзя торговать реальные деньги.

Откладывать подключение надо до момента, когда есть критичные события:
- `OrderRejected` (compensating-close)
- `AuthError` (ключи невалидны)
- WS-разрыв > N сек
- Дневной/недельный/месячный лимит достигнут
- Кода `100001` повторяется (подпись сломалась)
- Adapter перезапускался > X раз за час

## 6. Что НЕ делать

- ❌ Не клиентить токен в код / git.
- ❌ Не отправлять INFO-уровень — забьёт канал.
- ❌ Не отправлять с every-message PII (балансы, ключи).
- ❌ Не блокировать стратегию ожиданием Telegram-ответа (try/except + log).
