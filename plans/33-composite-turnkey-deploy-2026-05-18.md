# План 33 — composite: turnkey backtest + изолированный VPS-деплой

## Дата: 2026-05-18 · База: планы 31-32

## Что сделано (оба «и то и то»)

### (б) Turnkey backtest — `scripts/composite_backtest.py`
Coinglass-backfill (liq/OI/CVD/funding) → провайдеры →
CompositeSignalStrategy → BacktestEngine + IS/OOS split. Чистая логика
(`TsFundingProvider` anti-look-ahead, `build_providers`) — 3 unit-теста
на fake-клиенте, без сети/ключа. **Honest gate:** нет
`COINGLASS_API_KEY` → выходит без фейковых чисел.

Запуск (окружение с ключом + .env):
```
.venv/bin/python -m scripts.composite_backtest \
  --symbol BTC-USDT --candles data/candles/btc-usdt-15m.jsonl \
  --interval 15m --months 12 --split-fraction 0.6
# повторить для ETH-USDT; затем оценить по критерию iter#4
```
(Здесь НЕ исполнено: в эфемерном контейнере нет ключа — не имитирую.)

### (а) Изолированный деплой — `docker-compose.composite.yml`
Отдельные контейнеры `crypto-comp-eth/btc`, сеть `crypto-comp-net`,
volume `crypto-comp-data` — НЕ пересекается с D3 (crypto-btc/eth/xrp).
composite уже в `live_runner` choices.

Деплой на VPS (ПОСЛЕ прохождения критерия — не раньше):
```
ssh <vps>
cd /opt/crypto && git pull
# в /etc/crypto/.env должны быть BINGX_VST_* и COINGLASS_API_KEY
docker compose -f scripts/deploy/docker-compose.composite.yml build
docker compose -f scripts/deploy/docker-compose.composite.yml up -d
docker compose -f scripts/deploy/docker-compose.composite.yml logs -f
```

## Жёсткий порядок (не нарушать)

1. backfill-WF (`composite_backtest`) ETH+BTC → критерий iter#4
   (PF>1.5 И PnL>+2% И OOS+≥2/3).
2. **Прошёл** → forward-test на демо (pre-registered, план 31:
   ETH+BTC, ≥4 нед; kill −5% экв / 5 losses подряд / PF<0.8@30).
3. **Не прошёл** → зафиксировать в retro, composite НЕ деплоить.
   Не подгонять параметры (оверфит-дисциплина).

## Блокеры (честно)
- `COINGLASS_API_KEY` отсутствует в этой сессии → backtest/демо
  исполняются в окружении с ключом (VPS/локально), не отсюда.
- Live Coinglass-провайдеры в `live_runner` ещё не подключены
  (composite там = безопасный no-op). Перед демо нужна live-wiring
  фаза — отдельный шаг после прохождения критерия.

## Definition of Done (этой итерации)
- Скрипт + 3 теста зелёные; compose-файл изолирован; гейты зелёные.
- Точные команды для обоих путей зафиксированы.
- Прод/D3 не тронуты; демо не включено; фейковых прогонов нет.
