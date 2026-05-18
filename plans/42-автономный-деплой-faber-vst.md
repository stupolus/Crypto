# План 42 — Автономный деплой Faber-VST (systemd на VPS)

## Суть (честно, как это работает)

Автономный бот = НЕ «Claude крутится в сессии». Это обычный
Python на постоянном VPS под **systemd-timer**, работающий
24/7 независимо от любых сессий. Claude строит/чинит код —
сервер его исполняет. Песочница сессии эфемерна и сервером
НЕ является; деплой — на VPS владельца (CLAUDE.md: «VPS в
Азии»), по уже существующему kit `scripts/deploy/`.

Наш `scripts/faber_vst_executor.py` уже спроектирован под это:
идемпотентный (реконсил от факт. позиции — повторный запуск
безопасен), kill-switch `ops/faber_HALT`, структурный лог,
RiskEngine-брейкеры, без look-ahead. Идеален для oneshot+timer.

## Артефакты (по образцу crypto-postmortem.{service,timer})

- `scripts/deploy/faber-vst.service` — Type=oneshot, User=crypto,
  WorkingDirectory=/opt/crypto, EnvironmentFile=/etc/crypto/.env
  (там BINGX_VST_*), hardened (NoNewPrivileges/ProtectSystem=
  strict/ProtectHome/PrivateTmp), ReadWritePaths=/opt/crypto/ops
  (лог/стейт/halt), journal-логирование.
- `scripts/deploy/faber-vst.timer` — OnCalendar ежедневно 21:00
  UTC (после закрытия US-сессии), Persistent=true (нагонит
  пропуск при простое VPS), RandomizedDelaySec=300.
- `install.sh`: ставит оба юнита (как postmortem).
- README: шаги включения на VPS.

## Что это даёт / границы (честно)

- На VPS: `systemctl enable --now faber-vst.timer` → бот сам
  ежедневно реконсилирует позицию по Faber, 24/7, без сессий,
  с авто-нагоном пропусков (Persistent), логи в journald +
  ops/faber_vst.jsonl.
- ЭТО НЕ LIVE: тот же hard-guard `BINGX_ENV==vst`; на VPS в
  `/etc/crypto/.env` должны быть ТОЛЬКО VST-ключи (live нет).
- Я не могу задеплоить за владельца: доступа к VPS из песочницы
  нет (ни IP, ни SSH). Деплой = владелец выполняет
  документированные шаги (одна команда), либо даёт способ
  доступа отдельно. Не выдаю разовые прогоны за автономность.
- Kill-switch на VPS: `touch /opt/crypto/ops/faber_HALT` —
  мгновенный стоп без остановки сервиса.

## Фазы

- 42.1 (этот файл) план.
- 42.2 .service + .timer + правка install.sh + README-блок.
- 42.3 Владелец на VPS: `git pull` в /opt/crypto →
  `sudo bash scripts/deploy/install.sh` (или ручная установка
  юнитов) → `sudo systemctl enable --now faber-vst.timer` →
  проверка `systemctl list-timers | grep faber`,
  `journalctl -u faber-vst -n 20`.
- 42.4 ≥4 нед автономной работы → вердикт по критерию плана 40.

## Жёсткие стопы

- Только VST. Юнит запускает тот же hard-guarded исполнитель.
- Live — отдельным явным «да» + пройденный demo-критерий
  (план 40) + закрытый пред-входной liq-пункт (план 41.5).
- Не деплою на сервер, к которому нет доказанного доступа;
  честно говорю, что нужно от владельца.
