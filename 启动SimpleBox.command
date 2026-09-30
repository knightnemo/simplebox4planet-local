#!/bin/zsh
set -eu
cd "$(dirname "$0")"
model="$PWD/local/SimpleBox4Planet.xlsx"
if [[ ! -f "$model" ]]; then
  mkdir -p local
  cp SimpleBox4Planet/SimpleBoxSubOriginal.xlsx "$model"
fi
open -a "Microsoft Excel" "$model"
