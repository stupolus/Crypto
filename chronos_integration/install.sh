#!/usr/bin/env bash
# Установка Chronos-песочницы.
#
# Chronos публикуется в PyPI (chronos-forecasting), поэтому, в отличие от
# Kronos, ничего клонировать не нужно — ставим пакет в свой venv.
#
# Главный проектный .venv не трогается. Удаление = rm -rf chronos_integration/.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/.venv"
PY="${PYTHON:-python3.11}"

echo ">>> Python: $($PY --version)"

if [ ! -d "$VENV" ]; then
    echo ">>> Создаю venv: $VENV"
    "$PY" -m venv "$VENV"
fi

echo ">>> Ставлю зависимости..."
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$HERE/requirements.txt"

echo ""
echo "Готово. Smoke-тест:"
echo "  $VENV/bin/python $HERE/example.py"
