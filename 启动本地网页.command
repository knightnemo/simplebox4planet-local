#!/bin/zsh
set -eu
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo '缺少 Python 环境。请先按 LOCAL_WEB.md 安装依赖。'
  exit 1
fi
exec .venv/bin/python launch.py
