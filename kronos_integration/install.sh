#!/usr/bin/env bash
# Установка Kronos-песочницы.
#
# Kronos не публикуется в PyPI и не имеет setup.py/pyproject — его API
# (`from model import Kronos, KronosTokenizer, KronosPredictor`) доступен
# только из исходников репозитория. Поэтому:
#   1. создаём отдельный venv внутри папки (Python 3.10+),
#   2. клонируем исходники Kronos в kronos_integration/Kronos/ (gitignore),
#   3. ставим рантайм-зависимости (CPU-сборка torch).
#
# Главный проектный .venv не трогается. Удаление = rm -rf kronos_integration/.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/.venv"
SRC="$HERE/Kronos"
PY="${PYTHON:-python3.10}"

echo ">>> Python: $($PY --version)"

if [ ! -d "$VENV" ]; then
    echo ">>> Создаю venv: $VENV"
    "$PY" -m venv "$VENV"
fi

if [ ! -d "$SRC/.git" ]; then
    echo ">>> Клонирую Kronos в: $SRC"
    git clone --depth 1 https://github.com/shiyu-coder/Kronos.git "$SRC"
else
    echo ">>> Kronos уже склонирован: $SRC"
fi

echo ">>> Ставлю зависимости..."
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$HERE/requirements.txt"

echo ""
echo "Готово. Smoke-тест:"
echo "  $VENV/bin/python $HERE/example.py"
