#!/usr/bin/env sh
set -eu

if [ -f .venv/bin/activate ]; then
  . .venv/bin/activate
fi

exec python -m flask --app src.app:create_app run --host 127.0.0.1 --port 5000

