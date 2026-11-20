#!/usr/bin/env bash
# Arrête Chess Coach lancé par ./start.sh (serveur web, synchro et moteurs Stockfish).
cd "$(dirname "$0")"
RUN_DIR="run"

stop_one() {  # $1 = nom, $2 = fichier pid
  local name="$1" pidfile="$2" pid
  [ -f "$pidfile" ] || { echo "$name : pas lancé."; return; }
  pid="$(cat "$pidfile")"
  if kill -0 "$pid" 2>/dev/null; then
    # Le processus est chef de son groupe (set -m dans start.sh) : on arrête tout le groupe.
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
    for _ in $(seq 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
    if kill -0 "$pid" 2>/dev/null; then
      kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null
    fi
    echo "$name : arrêté."
  else
    echo "$name : déjà arrêté."
  fi
  rm -f "$pidfile"
}

stop_one "Synchro Chess.com" "$RUN_DIR/sync.pid"
stop_one "Serveur web" "$RUN_DIR/server.pid"
rm -f "$RUN_DIR/port"
