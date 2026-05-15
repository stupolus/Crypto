# Multi-strategy systemd instances

Каждый файл `<SYMBOL>.conf` — это drop-in override для template unit
`crypto-llm-runner@.service`. Override меняет переменные `STRATEGY` и
`INTERVAL` для конкретной instance.

## ⚠ Symbol mapping (BingX VST реальные имена)

| Asset | Strategy | BingX VST symbol |
|-------|----------|------------------|
| Gold | gold_safety_haven | **XAUT-USDT** (Tether Gold) |
| Oil WTI | oil_eia_avoid | **NCCO1OILWTI2USD-USDT** |
| Tesla | stock_earnings_avoid | **NCSKTSLA2USD-USDT** |
| NVIDIA | stock_earnings_avoid | **NCSKNVDA2USD-USDT** |

Старые имена (`XAU-USDT`, `CL-USDT`, `TSLA-USDT`) на BingX VST не существуют —
runner упадёт с error `109425 ... not exist`.

## Установка одной стратегии (на VPS)

Пример для Gold:

```bash
# 1. Скопировать override
sudo mkdir -p /etc/systemd/system/crypto-llm-runner@XAUT-USDT.service.d/
sudo cp /opt/crypto/scripts/deploy/runner-overrides/XAUT-USDT.conf \
    /etc/systemd/system/crypto-llm-runner@XAUT-USDT.service.d/override.conf

# 2. Reload + enable + start
sudo systemctl daemon-reload
sudo systemctl enable --now crypto-llm-runner@XAUT-USDT.service

# 3. Логи
journalctl -u crypto-llm-runner@XAUT-USDT -f
```

## Установка всех 3 новых стратегий разом

```bash
for sym in XAUT-USDT NCCO1OILWTI2USD-USDT NCSKTSLA2USD-USDT; do
  sudo mkdir -p /etc/systemd/system/crypto-llm-runner@${sym}.service.d/
  sudo cp /opt/crypto/scripts/deploy/runner-overrides/${sym}.conf \
      /etc/systemd/system/crypto-llm-runner@${sym}.service.d/override.conf
done
sudo systemctl daemon-reload
sudo systemctl enable --now crypto-llm-runner@XAUT-USDT.service
sudo systemctl enable --now crypto-llm-runner@NCCO1OILWTI2USD-USDT.service
sudo systemctl enable --now crypto-llm-runner@NCSKTSLA2USD-USDT.service
```

## Backwards-compat

Существующий `crypto-llm-runner@BTC-USDT.service` продолжает работать
без override (по дефолту использует `STRATEGY=btc_breakout`, `INTERVAL=15m`).

## Список ресурсов на VPS per instance

Каждый запуск пишет в `/var/lib/crypto/`:
- `llm-<SYMBOL>-metrics.jsonl` — JSON-lines metrics
- `llm-<SYMBOL>.sqlite` — order journal
- `llm-<SYMBOL>-outcomes.sqlite` — Layer 6 trade outcomes
- `llm-<SYMBOL>.heartbeat` — UptimeRobot health check

Файлы изолированы по symbol — instances не конфликтуют.

## Каскадный stop

```bash
sudo systemctl stop \
    crypto-llm-runner@XAUT-USDT \
    crypto-llm-runner@NCCO1OILWTI2USD-USDT \
    crypto-llm-runner@NCSKTSLA2USD-USDT
```

## Удаление старых упавших instance (с неверными именами)

Если уже создал `@XAU-USDT.service.d/`, `@CL-USDT.service.d/`,
`@TSLA-USDT.service.d/` — почисти:

```bash
for old in XAU-USDT CL-USDT TSLA-USDT; do
  sudo systemctl disable --now crypto-llm-runner@${old}.service 2>/dev/null
  sudo rm -rf /etc/systemd/system/crypto-llm-runner@${old}.service.d/
done
sudo systemctl daemon-reload
```

## Emergency halt всех instance

```bash
sudo touch /var/lib/crypto/halt
```

Все runner'ы видят файл и отказываются открывать новые сделки. Удалить
файл = снять halt.
