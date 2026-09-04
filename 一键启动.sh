#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$PROJECT_DIR"
if ! command -v python3 >/dev/null 2>&1; then
  printf '未找到 Python 3。请先安装 Python 3.12（或更新版本），再运行此文件。\n' >&2
  exit 1
fi
exec python3 "$PROJECT_DIR/scripts/launch.py" "$@"
