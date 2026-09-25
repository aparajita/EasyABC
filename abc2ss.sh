#!/usr/bin/env bash
#
# Converts ABC files to MusicXML that SongScribe opens: abc2xml.py --songscribe.
# All arguments pass through to abc2xml.py; run with -h for its options.

set -euo pipefail

# Resolved through the /usr/local/bin symlink, so the project's .venv is found from anywhere.
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

# pyparsing prints a deprecation warning for each grammar rule in abc2xml.py.
export PYTHONWARNINGS=ignore

exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/abc2xml.py" --songscribe "$@"
