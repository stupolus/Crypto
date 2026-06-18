# Связность из dev-контейнера и деплой на VPS

Дата: 2026-05-22. Автономный режим (goal).

## Проверено (факты)

- BingX prod (open-api.bingx.com): `ExchangeNotAvailable` — заблокировано.
- BingX VST (open-api-vst.bingx.com): `ExchangeNotAvailable` — заблокировано.
- VPS 187.124.41.13:22 (SSH): TCP timeout — заблокировано.

→ Сетевая политика dev-контейнера блокирует исходящие соединения к биржам и к VPS.
Ни коннект к BingX (даже с VST-ключами), ни SSH-деплой отсюда невозможны — это
жёсткое ограничение окружения, не выбор.

## Безопасность (важно)

- Root-пароль VPS был прислан в чате открытым текстом — это раскрытие секрета.
  Рекомендация: **сменить пароль немедленно**; перейти на SSH-ключи; отключить
  password-auth (`PasswordAuthentication no`, `PermitRootLogin prohibit-password`).
  Пароль нигде не сохранён и в git не попадает.

## Как запускать (на VPS или через CI, где есть сеть)

```bash
# разведка инструментов (Шаг 0)
cd gold-bot && python -m scripts.recon_universe --md journal/step0-universe.md

# smoke VST (читает BINGX_VST_*, sandbox по умолчанию)
python -m scripts.smoke_exchange --exchange bingx --symbol BTC/USDT:USDT
```

Деплой: у корневого проекта есть `.github/workflows/deploy.yml` (SSH→VPS по секретам
`VPS_HOST`/`VPS_SSH_KEY`), который работает из GitHub-раннеров (у них есть сеть).
gold-bot получит свой деплой-план (07) — Docker + systemd/compose.

## Решение

VST-путь зашит в код: `BingXAdapter(vst=True)` по умолчанию; скрипты читают
`BINGX_VST_*`; live только явным `BINGX_LIVE=1`. Коннект/деплой — этап на VPS, не из контейнера.
