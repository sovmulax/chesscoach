#!/usr/bin/env bash
# Démarre Chess Coach sur http://127.0.0.1:8000
cd "$(dirname "$0")"
python3 manage.py migrate --noinput >/dev/null
exec python3 manage.py runserver 127.0.0.1:8000
