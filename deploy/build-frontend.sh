#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}/frontend"
if ! command -v npm >/dev/null 2>&1; then
  echo "未找到 npm，请先安装 Node.js LTS。" >&2
  exit 1
fi
npm ci
npm run build
echo "产物目录: ${ROOT}/frontend/dist"
