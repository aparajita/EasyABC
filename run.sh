#!/usr/bin/env bash
# Runs EasyABC from source, building first when the venv or the bundled tools are missing.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

built=1

if [[ ! -x .venv/bin/python ]]; then
  built=0
fi

for tool in abcm2ps abc2abc abc2midi midi2abc; do
  if [[ ! -x "bin/$tool" ]]; then
    built=0
  fi
done

if [[ "$built" -eq 0 ]]; then
  ./build.sh
fi

exec .venv/bin/python easy_abc.py "$@"
