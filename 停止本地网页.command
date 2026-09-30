#!/bin/zsh
set -eu
cd "$(dirname "$0")"
exec .venv/bin/python launch.py --stop
