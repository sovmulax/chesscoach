#!/usr/bin/env bash
# Démarre Chess Coach en arrière-plan :
#   - le serveur web sur http://127.0.0.1:$CHESSCOACH_PORT (8765 par défaut) ;
#   - une boucle qui récupère tes dernières parties Chess.com toutes les
#     $CHESSCOACH_SYNC_MINUTES minutes (10 par défaut) et les analyse.
# Les deux continuent de tourner après la fermeture du terminal. Arrêt : ./stop.sh
#
# Options (variables d'environnement) :
#   CHESSCOACH_PORT=9000 ./start.sh
#   CHESSCOACH_SYNC_MINUTES=5 ./start.sh
#   CHESSCOACH_USER=pseudo ./start.sh     # relie ce compte Chess.com s'il ne l'est pas encore
set -euo pipefail
cd "$(dirname "$0")"

PORT="${CHESSCOACH_PORT:-8765}"
SYNC_MINUTES="${CHESSCOACH_SYNC_MINUTES:-10}"
RUN_DIR="run"
mkdir -p "$RUN_DIR"

# Python : environnement virtuel du projet s'il existe.
if   [ -x .venv/bin/python ]; then PY=.venv/bin/python
elif [ -x env/bin/python ];   then PY=env/bin/python
else PY=python3
fi

is_alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }

if is_alive "$RUN_DIR/server.pid" || is_alive "$RUN_DIR/sync.pid"; then
  echo "Chess Coach tourne déjà ($(cat "$RUN_DIR/port" 2>/dev/null || echo "?")). Lance ./stop.sh d'abord."
  exit 1
fi
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Le port $PORT est déjà utilisé. Choisis-en un autre : CHESSCOACH_PORT=9000 ./start.sh"
  exit 1
fi

echo "Mise à jour de la base…"
"$PY" manage.py migrate --noinput >/dev/null

SYNC_ARGS=(--every "$SYNC_MINUTES")
[ -n "${CHESSCOACH_USER:-}" ] && SYNC_ARGS+=(--user "$CHESSCOACH_USER")

# set -m : chaque processus a son propre groupe, stop.sh arrête aussi les Stockfish lancés.
set -m
nohup "$PY" manage.py runserver "127.0.0.1:$PORT" --noreload >>"$RUN_DIR/server.log" 2>&1 &
echo $! >"$RUN_DIR/server.pid"
nohup "$PY" -u manage.py sync_chesscom "${SYNC_ARGS[@]}" >>"$RUN_DIR/sync.log" 2>&1 &
echo $! >"$RUN_DIR/sync.pid"
set +m
echo "$PORT" >"$RUN_DIR/port"

# Attend que le serveur réponde (15 s max).
for _ in $(seq 30); do
  if curl -fsS -o /dev/null "http://127.0.0.1:$PORT/" 2>/dev/null; then break; fi
  if ! is_alive "$RUN_DIR/server.pid"; then
    echo "Le serveur n'a pas démarré, voir $RUN_DIR/server.log :"; tail -n 20 "$RUN_DIR/server.log"
    ./stop.sh >/dev/null 2>&1 || true
    exit 1
  fi
  sleep 0.5
done

echo "Chess Coach démarré : http://127.0.0.1:$PORT"
echo "Synchro Chess.com toutes les $SYNC_MINUTES min (journal : $RUN_DIR/sync.log)"
echo "Arrêt : ./stop.sh"
