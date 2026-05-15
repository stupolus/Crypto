# Multi-strategy systemd instances

Каждый файл `<SYMBOL>.conf` — это drop-in override для template unit
`crypto-llm-runner@.service`. Override меняет переменные `STRATEGY` и
`INTERVAL` для конкретной instance.

## Установка одной стратегии (на VPS)

Пример для Gold (XAU-USDT, gold_safety_haven, 1h):

```bash
# 1. Скопировать override
sudo mkdir -p /etc/systemd/system/crypto-llm-runner@XAU-USDT.service.d/
sudo cp /opt/crypto/scripts/deploy/runner-overrides/XAU-USDT.conf \
    /etc/systemd/system/crypto-llm-runner@XAU-USDT.service.d/override.conf

# 2. Reload + enable + start
sudo systemctl daemon-reload
sudo systemctl enable --now crypto-llm-runner@XAU-USDT.service

# 3. Логи
journalctl -u crypto-llm-runner@XAU-USDT -f
```

## Установка всех 3 новых стратегий разом

```bash
for sym in XAU-USDT CL-USDT TSLA-USDT; do
  sudo mkdir -p /etc/systemd/system/crypto-llm-runner@${sym}.service.d/
  sudo cp /opt/crypto/scripts/deploy/runner-overrides/${sym}.conf \
      /etc/systemd/system/crypto-llm-runner@${sym}.service.d/override.conf
done
sudo systemctl daemon-reload
sudo systemctl enable --now crypto-llm-runner@XAU-USDT.service
sudo systemctl enable --now crypto-llm-runner@CL-USDT.service
sudo systemctl enable --now crypto-llm-runner@TSLA-USDT.service
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
sudo systemctl stop crypto-llm-runner@XAU-USDT crypto-llm-runner@CL-USDT crypto-llm-runner@TSLA-USDT
```

## Emergency halt всех instance

```bash
sudo touch /var/lib/crypto/halt
```

Все runner'ы видят файл и отказываются открывать новые сделки. Удалить
файл = снять halt.
