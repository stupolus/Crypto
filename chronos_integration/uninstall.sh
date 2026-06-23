#!/usr/bin/env bash
# Удаление Chronos-песочницы.
#
# Главный проектный .venv не трогается — Chronos ставился в свой
# собственный venv внутри chronos_integration/.venv/, который удаляется
# вместе с папкой через `git rm -r chronos_integration`.
#
# Этот скрипт чистит ТОЛЬКО HuggingFace-кэш весов (вне репозитория).

set -euo pipefail

HUB="$HOME/.cache/huggingface/hub"
echo ">>> Очистка кэша моделей Chronos в: $HUB"
for repo in \
    "models--amazon--chronos-bolt-tiny" \
    "models--amazon--chronos-bolt-mini" \
    "models--amazon--chronos-bolt-small" \
    "models--amazon--chronos-bolt-base" \
    "models--amazon--chronos-t5-small" \
    "models--amazon--chronos-t5-base"; do
    rm -rf "$HUB/$repo"
done

echo ""
echo "HuggingFace-кэш Chronos удалён."
echo "Чтобы удалить и саму папку (вместе с venv) + закоммитить:"
echo "  git rm -r chronos_integration && git commit -m 'Remove Chronos'"
