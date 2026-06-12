#!/usr/bin/env bash
# Удаление Kronos-песочницы.
#
# Главный проектный .venv не трогается — Kronos ставился в свой
# собственный venv внутри kronos_integration/.venv/, а исходники — в
# kronos_integration/Kronos/. Оба удаляются вместе с папкой через
# `git rm -r kronos_integration`.
#
# Этот скрипт чистит ТОЛЬКО HuggingFace-кэш весов, который лежит вне
# репозитория.

set -euo pipefail

HUB="$HOME/.cache/huggingface/hub"
echo ">>> Очистка кэша моделей Kronos в: $HUB"
for repo in \
    "models--NeoQuasar--Kronos-mini" \
    "models--NeoQuasar--Kronos-small" \
    "models--NeoQuasar--Kronos-base" \
    "models--NeoQuasar--Kronos-Tokenizer-2k" \
    "models--NeoQuasar--Kronos-Tokenizer-base"; do
    rm -rf "$HUB/$repo"
done

echo ""
echo "HuggingFace-кэш Kronos удалён."
echo "Чтобы удалить и саму папку (venv + исходники) + закоммитить:"
echo "  git rm -r kronos_integration && git commit -m 'Remove Kronos'"
