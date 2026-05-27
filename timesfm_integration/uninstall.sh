#!/usr/bin/env bash
# Удаление TimesFM-песочницы.
#
# Главный проектный .venv не трогается — TimesFM был установлен в свой
# собственный venv внутри timesfm_integration/.venv/, который удаляется
# вместе с папкой через `git rm -r timesfm_integration`.
#
# Этот скрипт чистит ТОЛЬКО HuggingFace-кэш модели (~2 ГБ), который
# лежит вне репозитория.

set -euo pipefail

CACHE_DIR="$HOME/.cache/huggingface/hub/models--google--timesfm-2.0-500m-pytorch"
echo ">>> Очистка кэша модели: $CACHE_DIR"
rm -rf "$CACHE_DIR"

echo ""
echo "HuggingFace-кэш TimesFM удалён."
echo "Чтобы удалить и саму папку (вместе с venv) + закоммитить:"
echo "  git rm -r timesfm_integration && git commit -m 'Remove TimesFM'"
