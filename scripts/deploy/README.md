# Деплой на VPS

См. полный план: [`plans/16-деплой-24-7.md`](../../plans/16-деплой-24-7.md).

## Быстрый старт (40 минут от пустого VPS)

### 1. На своём компе

```bash
# Подключиться к VPS:
ssh root@<твой-ip>

# Если первый раз — провайдер должен был дать пароль или ты сам добавил SSH-ключ.
```

### 2. На VPS (под root через sudo)

```bash
# Скачать install.sh:
wget https://raw.githubusercontent.com/stupolus/Crypto/main/scripts/deploy/install.sh

# Запустить:
sudo bash install.sh
```

Скрипт идемпотентный — можно запускать повторно для обновления.

### 3. Заполнить .env

```bash
sudo nano /etc/crypto/.env
```

Минимум:
- `BINGX_VST_API_KEY` и `BINGX_VST_API_SECRET` (для D3 demo)

Рекомендую:
- `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` (для алертов на телефон)

### 4. Включить раннеры

```bash
sudo systemctl enable --now crypto-runner@BTC-USDT
sudo systemctl enable --now crypto-runner@ETH-USDT
sudo systemctl enable --now crypto-runner@XRP-USDT
```

### 5. Проверка

```bash
# Статус каждого раннера:
sudo systemctl status crypto-runner@BTC-USDT

# Лайв-лог всех раннеров:
sudo journalctl -u 'crypto-runner@*' -f

# Через 15 минут — близкие events должны прилететь:
sudo journalctl -u crypto-runner@BTC-USDT | grep "candle closed"
```

## Обновление кода

```bash
# На VPS:
sudo -u crypto git -C /opt/crypto pull origin main
sudo -u crypto /opt/crypto/.venv/bin/pip install -e /opt/crypto[dev]
sudo systemctl restart 'crypto-runner@*'
```

## Откат

```bash
# Stop всё:
sudo systemctl stop 'crypto-runner@*'
sudo systemctl disable 'crypto-runner@*'

# Удалить (опасно — journal/metrics удалятся):
sudo rm -rf /var/lib/crypto /opt/crypto /etc/crypto
sudo userdel -r crypto
sudo rm /etc/systemd/system/crypto-runner@.service
sudo rm /etc/logrotate.d/crypto
```

## Безопасность

- `.env` `chmod 600`, owner `root:crypto` — только crypto-user читает.
- `crypto` пользователь без sudo, не может править systemd.
- ufw: открыт только SSH (22). Порт 8080 (healthz) — открывается отдельно по IP UptimeRobot.
- fail2ban защищает SSH.
- systemd unit: `NoNewPrivileges`, `ProtectSystem=strict`, `MemoryDenyWriteExecute`.
- BingX API ключи — **только торговые** (без Withdraw!), IP whitelist на IP VPS.
