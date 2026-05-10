#!/usr/bin/env bash
# Запускает или подключается к tmux-сессии "crypto" в /root/Crypto.
# Использование: bash /root/Crypto/ops/crypto-shell.sh
#   - С Mac/iMac/iPhone: ssh root@187.124.41.13 -t /root/Crypto/ops/crypto-shell.sh
#   - Прямо на VPS: ./ops/crypto-shell.sh
SESSION="crypto"
WORKDIR="/root/Crypto"

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Подключаюсь к существующей tmux-сессии \"$SESSION\"..."
    exec tmux attach -t "$SESSION"
else
    echo "Создаю новую tmux-сессию \"$SESSION\" в $WORKDIR..."
    exec tmux new-session -s "$SESSION" -c "$WORKDIR"
fi
