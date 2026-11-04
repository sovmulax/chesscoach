"""Métriques d'une partie à partir de l'analyse moteur.

Toutes les pertes sont exprimées en points de « chances de gain » (0–100 %),
avec la formule de Lichess. Seuils : imprécision ≥ 10, erreur ≥ 20, gaffe ≥ 30.
"""
import collections
import math
import statistics

import chess

METRICS_VERSION = 5

INACCURACY = 10
MISTAKE = 20
BLUNDER = 30

WINNING = 85  # chances de gain à partir desquelles une position est « gagnante »
LOSING = 15
EQUAL_OR_BETTER = 45

PIECE_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}

PHASES = ("opening", "middlegame", "endgame")
CLASSES = ("best", "good", "inaccuracy", "mistake", "blunder")


def win_pct(cp):
    cp = max(-1500, min(1500, cp))
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def move_accuracy(loss):
    return max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * loss) - 3.1669))


def phase_of(board, ply):
    if ply < 20:
        return "opening"
    npm = sum(PIECE_VALUE[p.piece_type] for p in board.piece_map().values()
              if p.piece_type not in (chess.PAWN, chess.KING))
    return "endgame" if npm <= 20 else "middlegame"


def classify(loss, played_best):
    if loss >= BLUNDER:
        return "blunder"
    if loss >= MISTAKE:
        return "mistake"
    if loss >= INACCURACY:
        return "inaccuracy"
    if played_best or loss < 2:
        return "best"
    return "good"


def _strip(san):
    return (san or "").rstrip("+#")


def compute_game_stats(plies, player_color, result=None):
    """plies = sortie de engine.analyze_pgn ; player_color = 'w' ou 'b'."""
    pc = chess.WHITE if player_color == "w" else chess.BLACK
    psign = 1 if pc == chess.WHITE else -1
    n = len(plies) - 1
    moves = []

    for i in range(n):
        p, nxt = plies[i], plies[i + 1]
        board = chess.Board(p["fen"])
        mover = board.turn
        mine = mover == pc
        msign = 1 if mover == chess.WHITE else -1
        wp_b = win_pct(msign * p["cp"])
        wp_a = win_pct(msign * nxt["cp"])
        loss = max(0.0, wp_b - wp_a)
        move = chess.Move.from_uci(p["uci"])
        piece = board.piece_at(move.from_square)
        played_best = p.get("best_uci") == p["uci"]
        cls = classify(loss, played_best)
        tags = []

        mate_b = p["mate"] * msign if p.get("mate") is not None else None  # >0 : le joueur au trait mate
        mate_a = nxt["mate"] * msign if nxt.get("mate") is not None else None
        delivered_mate = bool(nxt.get("final") and nxt.get("outcome") == "checkmate")
        if mate_b and mate_b > 0 and not delivered_mate and abs(mate_b) <= 3:
            if not (mate_a and mate_a > 0):
                tags.append("missed_mate")  # le mat forcé est perdu
            if mate_b == 1:
                tags.append("missed_mate_1")  # mat en 1 sur l'échiquier, non joué
        if mate_a and mate_a < 0 and not (mate_b and mate_b < 0) and loss >= MISTAKE:
            tags.append("allowed_mate")
        if "missed_mate" in tags and cls in ("best", "good"):
            cls = "inaccuracy"  # rater un mat court reste une faute, même si la position reste gagnante

        rec = {
            "i": i,
            "n": i // 2 + 1,
            "mine": mine,
            "san": p["san"],
            "uci": p["uci"],
            "best": p.get("best"),
            "best_uci": p.get("best_uci"),
            "pv": p.get("pv") or [],
            "loss": round(loss, 1),
            "wp_before": round(wp_b, 1),
            "wp_after": round(wp_a, 1),
            "cls": cls,
            "phase": phase_of(board, i),
            "piece": piece.symbol().lower() if piece else "?",
            "mate_before": mate_b,
            "mate_after": mate_a,
            "clock": p.get("clock"),
            "castle": board.is_castling(move),
            "capture": board.is_capture(move),
        }

        nb = nxt.get("best_uci")
        if nb and loss >= MISTAKE:
            b2 = board.copy()
            b2.push(move)
            reply = chess.Move.from_uci(nb)
            if b2.is_capture(reply):
                if b2.is_en_passant(reply):
                    cap_sym = "p"
                else:
                    cap = b2.piece_at(reply.to_square)
                    cap_sym = cap.symbol().lower() if cap else "p"
                tags.append("hanging")
                rec["reply"] = nxt.get("best")
                rec["captured"] = cap_sym
                rec["captured_square"] = chess.square_name(reply.to_square)
                rec["captured_is_moved"] = reply.to_square == move.to_square
            else:
                rec["reply"] = nxt.get("best")
        if nxt.get("final") and nxt.get("outcome") == "stalemate" and wp_b >= 80:
            tags.append("stalemate")
        clock = p.get("clock")
        if clock is not None and clock < 30 and loss >= MISTAKE:
            tags.append("time_trouble")
        rec["tags"] = tags
        moves.append(rec)

    # Gaffe adverse non punie : l'adversaire gaffe, la réponse perd au moins 20 points.
    for k in range(1, len(moves)):
        prev, cur = moves[k - 1], moves[k]
        if prev["cls"] == "blunder" and cur["loss"] >= MISTAKE:
            cur["tags"].append("missed_punish")
            cur["punish_of"] = prev["san"]

    return {"version": METRICS_VERSION, "moves": moves, **_game_summary(plies, moves, psign, pc, result)}


def _game_summary(plies, moves, psign, pc, result):
    mine = [m for m in moves if m["mine"]]
    opp = [m for m in moves if not m["mine"]]
    wp_series = [round(win_pct(psign * p["cp"]), 1) for p in plies]

    def counts(lst):
        c = collections.Counter(m["cls"] for m in lst)
        return {k: c.get(k, 0) for k in CLASSES}

    def phases(lst):
        out = {}
        for ph in PHASES:
            sub = [m for m in lst if m["phase"] == ph]
            out[ph] = {
                "moves": len(sub),
                "blunders": sum(1 for m in sub if m["cls"] == "blunder"),
                "mistakes": sum(1 for m in sub if m["cls"] == "mistake"),
                "loss_sum": round(sum(m["loss"] for m in sub), 1),
            }
        return out

    first = next((m for m in moves if m["cls"] == "blunder"), None)
    first_mine = next((m for m in mine if m["cls"] == "blunder"), None)
    hanging = [m for m in mine if "hanging" in m["tags"]]
    material_lost = collections.Counter(m.get("captured") for m in hanging if m.get("captured"))
    motifs = [f"{_strip(m['san'])}|{_strip(m.get('reply'))}" for m in hanging
              if m.get("captured_is_moved") and m["piece"] != "p"]
    castled = next((m["n"] for m in mine if m["castle"]), None)
    has_clock = any(m.get("clock") is not None for m in moves)
    eval10 = psign * plies[20]["cp"] if len(plies) > 20 else None
    score = {"win": 1.0, "draw": 0.5, "loss": 0.0}.get(result)

    key = sorted(
        [m for m in moves if (m["mine"] and (m["cls"] in ("blunder", "mistake") or m["tags"]))
         or (not m["mine"] and m["cls"] == "blunder")],
        key=lambda m: -m["loss"],
    )[:10]

    return {
        "accuracy": round(statistics.mean(move_accuracy(m["loss"]) for m in mine), 1) if mine else None,
        "opp_accuracy": round(statistics.mean(move_accuracy(m["loss"]) for m in opp), 1) if opp else None,
        "counts": {"mine": counts(mine), "opp": counts(opp)},
        "phases": {"mine": phases(mine), "opp": phases(opp)},
        "wp_series": wp_series,
        # Positions atteintes après TES coups : c'est là qu'une position est « à toi »
        "max_wp": max((m["wp_after"] for m in mine), default=wp_series[0]),
        "min_wp": min((m["wp_after"] for m in mine), default=wp_series[0]),
        "eval10": eval10,
        "first_blunder": {
            "by": None if first is None else ("me" if first["mine"] else "opp"),
            "ply": None if first is None else first["i"],
        },
        "first_own_blunder_wp": first_mine["wp_before"] if first_mine else None,
        "first_own_blunder_move": first_mine["n"] if first_mine else None,
        "lost_from_equal": bool(score == 0.0 and first_mine and first_mine["wp_before"] >= EQUAL_OR_BETTER),
        "castled_move": castled,
        "missed_mates": sum(1 for m in mine if "missed_mate" in m["tags"]),
        "missed_mates_1": sum(1 for m in mine if "missed_mate_1" in m["tags"]),
        "allowed_mates": sum(1 for m in mine if "allowed_mate" in m["tags"]),
        "hanging": len(hanging),
        "hanging_other": sum(1 for m in hanging if not m.get("captured_is_moved")),
        "material_lost": dict(material_lost),
        "motifs": motifs,
        "opp_blunders": sum(1 for m in opp if m["cls"] == "blunder"),
        "unpunished": sum(1 for m in mine if "missed_punish" in m["tags"]),
        "stalemate_while_winning": any("stalemate" in m["tags"] for m in mine),
        "time_trouble_errors": sum(1 for m in mine if "time_trouble" in m["tags"]),
        "has_clock": has_clock,
        "key_moments": [m["i"] for m in key],
    }
