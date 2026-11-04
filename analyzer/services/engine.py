"""Pilotage de Stockfish via python-chess."""
import io
import os
import shutil

import chess
import chess.engine
import chess.pgn
from django.conf import settings

MATE_SCORE = 10000

_CANDIDATES = [
    "/usr/games/stockfish",
    "/usr/bin/stockfish",
    "/usr/local/bin/stockfish",
    "/opt/homebrew/bin/stockfish",
    r"C:\Program Files\stockfish\stockfish.exe",
    r"C:\stockfish\stockfish.exe",
]


class EngineNotFound(RuntimeError):
    pass


def find_stockfish():
    path = getattr(settings, "STOCKFISH_PATH", "") or ""
    if path:
        if os.path.exists(path) or shutil.which(path):
            return shutil.which(path) or path
        raise EngineNotFound(f"STOCKFISH_PATH pointe vers « {path} », introuvable.")
    for name in ("stockfish", "stockfish.exe"):
        found = shutil.which(name)
        if found:
            return found
    for cand in _CANDIDATES:
        if os.path.exists(cand):
            return cand
    raise EngineNotFound(
        "Stockfish est introuvable. Installe-le (voir README) ou indique son chemin "
        "dans la variable d'environnement STOCKFISH_PATH."
    )


def engine_available():
    try:
        find_stockfish()
        return True
    except EngineNotFound:
        return False


def open_engine():
    eng = chess.engine.SimpleEngine.popen_uci(find_stockfish())
    eng.configure({"Threads": 1, "Hash": getattr(settings, "STOCKFISH_HASH_MB", 64)})
    return eng


def _score(info):
    """Évaluation en centipions du point de vue des Blancs ; les mats deviennent ±(10000 - 10·n)."""
    s = info["score"].white()
    if s.is_mate():
        m = s.mate()
        if m == 0:
            return (-MATE_SCORE, 0)
        return ((MATE_SCORE - abs(m) * 10) * (1 if m > 0 else -1), m)
    return (s.score(), None)


def analyze_pgn(pgn_text, eng, time_per_position=0.05):
    """Analyse chaque position de la partie.

    Retourne une liste de dicts : une entrée par position AVANT chaque coup
    (fen, san, uci, cp, mate, best, best_uci, pv, clock) + une entrée finale.
    """
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("PGN illisible")
    board = game.board()
    plies = []
    limit = chess.engine.Limit(time=time_per_position)
    for node in game.mainline():
        move = node.move
        info = eng.analyse(board, limit)
        cp, mate = _score(info)
        pv = info.get("pv") or []
        best = pv[0] if pv else None
        pv_san = []
        tmp = board.copy()
        for mv in pv[:5]:
            try:
                pv_san.append(tmp.san(mv))
                tmp.push(mv)
            except (ValueError, AssertionError):
                break
        plies.append({
            "fen": board.fen(),
            "san": board.san(move),
            "uci": move.uci(),
            "cp": cp,
            "mate": mate,
            "best": pv_san[0] if pv_san else None,
            "best_uci": best.uci() if best else None,
            "pv": pv_san,
            "clock": node.clock(),
        })
        board.push(move)
    if board.is_game_over():
        outcome = board.outcome()
        cp = 0 if outcome.winner is None else (MATE_SCORE if outcome.winner else -MATE_SCORE)
        plies.append({"fen": board.fen(), "cp": cp, "mate": None, "final": True,
                      "outcome": outcome.termination.name.lower()})
    else:
        info = eng.analyse(board, limit)
        cp, mate = _score(info)
        plies.append({"fen": board.fen(), "cp": cp, "mate": mate, "final": True, "outcome": None})
    return plies


def positions_without_engine(pgn_text):
    """FEN + coups d'une partie, pour l'afficher même si elle n'est pas analysée."""
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    board = game.board()
    plies = []
    for node in game.mainline():
        plies.append({"fen": board.fen(), "san": board.san(node.move), "uci": node.move.uci(),
                      "clock": node.clock()})
        board.push(node.move)
    plies.append({"fen": board.fen(), "final": True})
    return plies
