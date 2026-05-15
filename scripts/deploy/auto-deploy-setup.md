# Auto-deploy через GitHub Actions

После настройки **каждый merge в main** автоматически деплоится на VPS:
1. Pull кода
2. Rebuild Docker image
3. Restart контейнеров
4. Если что-то упало — Telegram алерт пользователю

## Что нужно от тебя — один раз 10 минут

### 1. Сгенерировать SSH-ключ для GitHub Actions

На VPS вставь:
```bash
ssh-keygen -t ed25519 -f /root/.ssh/github_actions_deploy -N "" -C "github-actions-deploy"
cat /root/.ssh/github_actions_deploy.pub >> /root/.ssh/authorized_keys
cat /root/.ssh/github_actions_deploy
```

Последняя команда выведет **приватный ключ** (начинается с `-----BEGIN OPENSSH PRIVATE KEY-----`). Скопируй ВСЁ.

### 2. Добавь секреты в GitHub repo

Открой: **https://github.com/stupolus/Crypto/settings/secrets/actions**

Кнопка **«New repository secret»** для каждого из 5 секретов:

| Name | Value | Откуда |
|------|-------|--------|
| `VPS_HOST` | `187.124.41.13` | IP VPS |
| `VPS_USER` | `root` | пользователь |
| `VPS_SSH_KEY` | весь приватный ключ из шага 1 | ВКЛЮЧАЯ строки `BEGIN/END` |
| `TELEGRAM_BOT_TOKEN` | `8689070121:AAH...` | уже в .env, на случай deploy fail алерта |
| `TELEGRAM_CHAT_ID` | `239373620` | тот же что в .env |

### 3. Включить деплой

Открой: **https://github.com/stupolus/Crypto/settings/variables/actions**

Кнопка **«New repository variable»**:
- Name: `DEPLOY_ENABLED`
- Value: `true`

Это safety switch — без этой переменной workflow no-op. Если что-то сломается, выставь `false` и временно отключи auto-deploy.

### 4. Тест: Manual trigger

Открой: **https://github.com/stupolus/Crypto/actions/workflows/deploy.yml**

Кнопка **«Run workflow»** → ветка `main` → **Run workflow**.

Через ~1 мин увидишь зелёный чекмарк. Если красный — открой run → читай логи.

### 5. С этого момента

Каждый раз когда я (Claude) мержу PR в main:
1. GitHub Actions автоматически запускает deploy.yml
2. Pull + build + up на VPS
3. Если упало — приходит Telegram алерт «🚨 Auto-deploy failed»
4. Если ок — `docker ps` через 60s показывает healthy

Тебе **больше не надо вставлять SSH-команды** для деплоя.

## Откат

Если auto-deploy сломал что-то:
1. На VPS: `cd /opt/crypto-bot && git reset --hard <PREVIOUS_COMMIT> && docker compose -f scripts/deploy/docker-compose.yml up -d --force-recreate`
2. В GitHub: set `DEPLOY_ENABLED=false` чтобы остановить будущие auto-deploys
3. Скажи мне — фикшу PR'ом

## Безопасность

- Приватный SSH-ключ в GitHub secret (encrypted at rest, доступен только runner'у workflow)
- `BatchMode=yes` — никаких interactive prompts на VPS, deploy fails чисто если что
- `concurrency: deploy-main` + `cancel-in-progress: false` — не отменяем активный deploy
- `set -euo pipefail` на VPS-стороне — любая ошибка прерывает скрипт
- Telegram алерт на failure — мгновенный feedback

## Что НЕ делает auto-deploy

- ❌ Database migrations (у нас SQLite, миграции пока не нужны)
- ❌ Backup VPS volumes (это отдельная задача, через cron)
- ❌ Rolling update (zero-downtime) — restart прерывает 30-60 сек, для D3 OK

При live (фаза 2+) — добавим healthcheck-based readiness wait, чтобы downtime был < 5 сек.
