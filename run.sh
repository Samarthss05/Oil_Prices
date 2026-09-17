#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PROJECT_DIR"
export PYTHONPATH="$PROJECT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
if [ ! -x "$PROJECT_DIR/.venv/bin/python" ]; then
  echo "Create .venv with Python 3.12+ and install requirements.lock first; see README.md." >&2
  exit 1
fi
if [ "$#" -eq 0 ]; then
  set -- run --refresh --open
fi
exec "$PROJECT_DIR/.venv/bin/python" -m retail_outlook.cli "$@"
