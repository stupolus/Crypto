# Diag 2026-05-22 — D3 (crypto-btc/eth/xrp) Up 6d (unhealthy)

## Симптом

Из логов Manus 2026-05-19: D3-контейнеры `Up 6 days (unhealthy)`. На
composite-стек (`crypto-comp-*`) это никак не влияло — у них свой
стек/сеть/volume; composite поднялся healthy. Поэтому я не пускал
этот пункт в блокер демо.

## Диагноз (по коду, без VPS-доступа)

`scripts/deploy/Dockerfile` определяет healthcheck:
```
HEALTHCHECK CMD test "$(find /var/lib/crypto/$BINGX_SYMBOL.heartbeat -mmin -2 | wc -l)" -ge 1 || exit 1
```
Heartbeat-loop живёт в `runners/live_runner.py` (`_heartbeat_loop`,
async-task с 30s интервалом, активируется при наличии флага
`--heartbeat-file`). Dockerfile CMD передаёт флаг сейчас.

Наиболее вероятная причина unhealthy (только D3, не composite):

**D3-контейнеры собраны до того, как heartbeat-фича была добавлена в
образ/CMD.** «Up 6 days» = старая инкарнация образа. Файл-heartbeat
никогда не создаётся → find отдаёт 0 → healthcheck = fail.
Restart-policy на unhealthy не триггерится (только на crash/exit) —
поэтому контейнеры живут с красной меткой, но фактически работают
(торгуют btc_breakout, как описано в retro 2026-05-13). Это
**косметика статуса**, не реальный обрыв торговли — иначе бы
restart-петля или Telegram-alert на смерть процесса.

## Безопасный фикс (VPS-side, не код)

Не трогая код/конфиг, на VPS:
```
cd /opt/crypto && git checkout main && git pull
docker compose -f scripts/deploy/docker-compose.yml build
docker compose -f scripts/deploy/docker-compose.yml up -d --force-recreate
```
Контейнеры пересоздадутся из актуального образа (с heartbeat в CMD)
→ healthcheck начнёт зеленеть в течение ~2 минут после первого touch.

## Что НЕ нужно делать

- Менять Dockerfile/healthcheck — текущая логика корректна (фича есть).
- Менять restart-policy — unhealthy без crash намеренно НЕ роняет
  контейнер (это поведение D3 6 дней подтверждает: торгует, просто
  метка красная).
- Дёргать D3 без надобности — он живёт и работает; пересоздание —
  плановое действие при следующем апгрейде, не аварийное.

## Статус

Диагностировано по коду из этой сессии. Реальный фикс = `docker
compose up -d --force-recreate` на VPS — единственная команда, я её
не выполняю отсюда. Если Manus или владелец хочет очистить метку
сейчас — выполняет одну строку выше. Если нет — D3 продолжает
работать unhealthy-косметически, без последствий.
