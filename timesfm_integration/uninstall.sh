#!/usr/bin/env bash
# Fully remove TimesFM from this machine and project.
# Usage: bash timesfm_integration/uninstall.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==> Uninstalling pip packages (timesfm, torch)..."
pip uninstall -y timesfm torch || true

echo "==> Removing HuggingFace model cache..."
rm -rf "$HOME/.cache/huggingface/hub/models--google--timesfm-2.0-500m-pytorch" || true

echo "==> Removing integration folder..."
rm -rf "$SCRIPT_DIR"

echo ""
echo "TimesFM полностью удалён."
echo "Не забудь закоммитить удаление папки:"
echo "    cd $REPO_ROOT && git add -A && git commit -m 'Remove TimesFM'"
