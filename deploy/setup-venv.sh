#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if ! command -v python3.13 >/dev/null 2>&1; then
  echo "未找到 python3.13，请先安装 Python 3.13+（见 deploy/README.md）。" >&2
  exit 1
fi
python3.13 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -e .
echo "完成。激活虚拟环境: source ${ROOT}/.venv/bin/activate"
