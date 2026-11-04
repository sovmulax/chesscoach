"""Exercices : détection des thèmes, construction avec Stockfish, données pour l'échiquier.

Un exercice suit le format de la base libre de Lichess :
  - `fen`   : la position AVANT le coup adverse qui crée l'occasion ;
  - `moves` : ce coup adverse, puis la solution (coup du joueur, réponse, coup du joueur…).

Règle de qualité (comme pour les bases d'exercices classiques) : à chaque étape,
le coup du joueur doit être nettement le meilleur, sinon la ligne s'arrête là.
Seule exception : au dernier coup, tout mat est accepté.
"""
import chess
import chess.engine

from . import metrics
from .notation import display

VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}

# Seuils (points de chances de gain, 0–100)
WINNING_WP = 70        # la solution doit mener à une position gagnante…
UNIQUE_GAP = 22        # … nettement meilleure que la 2e meilleure option
SAFE_GAP = 8           # « Éviter la gaffe » : coups acceptés à moins de 8 points du meilleur
MAX_SAFE_MOVES = 4     # au-delà, la position n'est pas assez critique pour un exercice


# ---------------------------------------------------------------------------
# Outils d'échiquier
# ---------------------------------------------------------------------------
def _material(board, color):
    return sum(VALUES[p.piece_type] for p in board.piece_map().values()
               if p.color == color and p.piece_type != chess.KING)


def _npm(board):
    return sum(VALUES[p.piece_type] for p in board.piece_map().values()
               if p.piece_type not in (chess.PAWN, chess.KING))


def _endgame_kind(board):
    types = {p.piece_type for p in board.piece_map().values() if p.piece_type not in (chess.PAWN, chess.KING)}
    return {
        frozenset(): "pawnEndgame",
        frozenset({chess.ROOK}): "rookEndgame",
        frozenset({chess.QUEEN}): "queenEndgame",
        frozenset({chess.BISHOP}): "bishopEndgame",
        frozenset({chess.KNIGHT}): "knightEndgame",
        frozenset({chess.QUEEN, chess.ROOK}): "queenRookEndgame",
    }.get(frozenset(types))


def _sign(x):
    return (x > 0) - (x < 0)


def _beyond(board, origin, target):
    """Première pièce rencontrée derrière `target` sur la ligne origin -> target."""
    df = _sign(chess.square_file(target) - chess.square_file(origin))
    dr = _sign(chess.square_rank(target) - chess.square_rank(origin))
    f, r = chess.square_file(target) + df, chess.square_rank(target) + dr
    while 0 <= f <= 7 and 0 <= r <= 7:
        sq = chess.square(f, r)
        if board.piece_at(sq):
            return sq
        f, r = f + df, r + dr
    return None


def _valuable_targets(board, sq, player):
    """Pièces adverses attaquées depuis `sq` qui comptent : roi, pièce plus chère ou sans défense."""
    piece = board.piece_at(sq)
    out = []
    for t in board.attacks(sq):
        tp = board.piece_at(t)
        if not tp or tp.color == player:
            continue
        if tp.piece_type == chess.KING:
            out.append(t)
        elif VALUES[tp.piece_type] >= 3 and (
                VALUES[tp.piece_type] > VALUES[piece.piece_type] or not board.is_attacked_by(not player, t)):
            out.append(t)
    return out


# ---------------------------------------------------------------------------
# Détection des thèmes
# ---------------------------------------------------------------------------
def detect_themes(fen, moves):
    """Thèmes d'un exercice (fen + coups UCI au format Lichess), déduits de la géométrie de la solution."""
    board = chess.Board(fen)
    board.push(chess.Move.from_uci(moves[0]))
    player = board.turn
    sol = [chess.Move.from_uci(u) for u in moves[1:]]
    themes = set()
    n_player = (len(sol) + 1) // 2
    themes.add({1: "oneMove", 2: "short", 3: "long"}.get(n_player, "veryLong"))

    if _npm(board) <= 20:
        themes.add("endgame")
        kind = _endgame_kind(board)
        if kind:
            themes.add(kind)
    elif board.fullmove_number <= 12:
        themes.add("opening")
    else:
        themes.add("middlegame")

    start_balance = _material(board, player) - _material(board, not player)
    min_balance = start_balance
    b = board.copy()
    captured_later = []  # cases des prises du joueur après chaque coup (pour valider fourchette / enfilade)
    forks, skewers = [], []
    for idx, mv in enumerate(sol):
        if idx % 2 == 0:  # coup du joueur
            piece = b.piece_at(mv.from_square)
            if idx > 0 and b.is_capture(mv):
                captured_later.append(mv.to_square)
            if mv.promotion:
                themes.add("promotion")
                if mv.promotion != chess.QUEEN:
                    themes.add("underPromotion")
            if piece and piece.piece_type == chess.PAWN:
                rank = chess.square_rank(mv.to_square)
                if (rank >= 5 if player == chess.WHITE else rank <= 2):
                    themes.add("advancedPawn")
            if b.is_en_passant(mv):
                themes.add("enPassant")
            if b.is_castling(mv):
                themes.add("castling")
            if idx == 0:
                if b.is_capture(mv) and not b.is_en_passant(mv):
                    victim = b.piece_at(mv.to_square)
                    if victim and VALUES[victim.piece_type] >= 3 and not b.is_attacked_by(not player, mv.to_square) and n_player <= 2:
                        themes.add("hangingPiece")
                if not b.is_capture(mv) and not b.gives_check(mv) and not mv.promotion:
                    themes.add("quietMove")
            # Attaques déjà possibles avant le coup (pour l'attaque à la découverte)
            before = {s: set(b.attacks(s)) for s, p in b.piece_map().items()
                      if p.color == player and p.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN) and s != mv.from_square}
            b.push(mv)
            if len(b.checkers()) >= 2:
                themes.add("doubleCheck")
            moved = b.piece_at(mv.to_square)
            if moved:
                tg = _valuable_targets(b, mv.to_square, player)
                if len(tg) >= 2:
                    forks.append(set(tg))
                if moved.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN):
                    for t in b.attacks(mv.to_square):
                        tp = b.piece_at(t)
                        if tp and tp.color != player and tp.piece_type in (chess.KING, chess.QUEEN, chess.ROOK):
                            behind = _beyond(b, mv.to_square, t)
                            bp = b.piece_at(behind) if behind is not None else None
                            if bp and bp.color != player and VALUES[bp.piece_type] < VALUES[tp.piece_type]:
                                skewers.append(behind)
                # Clouage créé par la pièce jouée, ou attaque d'une pièce déjà clouée
                for s, p in b.piece_map().items():
                    if p.color != player and p.piece_type != chess.KING and VALUES[p.piece_type] >= 3 and b.is_pinned(not player, s):
                        if mv.to_square in chess.SquareSet(b.pin(not player, s)) or s in b.attacks(mv.to_square):
                            themes.add("pin")
            for s, att in before.items():
                if b.piece_at(s) is None:
                    continue
                for t in set(b.attacks(s)) - att:
                    tp = b.piece_at(t)
                    if tp and tp.color != player and (tp.piece_type == chess.KING or VALUES[tp.piece_type] >= 3) \
                            and mv.from_square in chess.SquareSet(chess.between(s, t)):
                        themes.add("discoveredAttack")
            min_balance = min(min_balance, _material(b, player) - _material(b, not player))
        else:  # réponse adverse
            b.push(mv)
            min_balance = min(min_balance, _material(b, player) - _material(b, not player))

    if any(f & set(captured_later) for f in forks) or (forks and b.is_checkmate()):
        themes.add("fork")
    if any(s in captured_later for s in skewers):
        themes.add("skewer")
    if min_balance <= start_balance - 2:
        themes.add("sacrifice")

    if b.is_checkmate():
        themes.add("mate")
        themes.add(f"mateIn{min(n_player, 5)}")
        loser = b.turn
        ksq = b.king(loser)
        checkers = list(b.checkers())
        kf, kr = chess.square_file(ksq), chess.square_rank(ksq)
        if len(checkers) == 1 and b.piece_at(checkers[0]).piece_type == chess.KNIGHT:
            around = [s for s in chess.SquareSet(chess.BB_KING_ATTACKS[ksq])]
            if all(b.piece_at(s) and b.piece_at(s).color == loser for s in around):
                themes.add("smotheredMate")
        back = 0 if loser == chess.WHITE else 7
        if kr == back and checkers and all(
                b.piece_at(c).piece_type in (chess.ROOK, chess.QUEEN) and chess.square_rank(c) == back for c in checkers):
            fwd_rank = back + (1 if loser == chess.WHITE else -1)
            fwd = [chess.square(f, fwd_rank) for f in (kf - 1, kf, kf + 1) if 0 <= f <= 7]
            own = [s for s in fwd if b.piece_at(s) and b.piece_at(s).color == loser]
            if len(own) >= 2 and all(s in own or b.is_attacked_by(not loser, s) for s in fwd):
                themes.add("backRankMate")
    return themes


# ---------------------------------------------------------------------------
# Construction avec Stockfish
# ---------------------------------------------------------------------------
def _wp(score):
    if score.is_mate():
        m = score.mate()
        return 100.0 if m > 0 else 0.0
    return metrics.win_pct(score.score())


def _lines(eng, board, seconds, multipv=1):
    infos = eng.analyse(board, chess.engine.Limit(time=seconds), multipv=multipv)
    if isinstance(infos, dict):
        infos = [infos]
    out = []
    for inf in infos:
        if not inf.get("pv"):
            continue
        sc = inf["score"].pov(board.turn)
        out.append({"move": inf["pv"][0], "score": sc, "wp": _wp(sc),
                    "mate": sc.mate() if sc.is_mate() else None})
    return out


def _mate_ambiguous(second, n):
    """Une 2e option qui mate aussi vite rend l'étape ambiguë."""
    return bool(second and second["mate"] is not None and 0 < second["mate"] <= n + 1)


def build_solution(eng, board, seconds=0.25, max_player=4):
    """Solution forcée depuis `board` (joueur au trait). Retourne (coups UCI, infos) ou None."""
    lines = _lines(eng, board, seconds, 3)
    if len(lines) < 2:
        return None  # coup unique ou partie finie : pas un exercice
    best, second = lines[0], lines[1]
    b = board.copy()
    moves = []

    if best["mate"] is not None and best["mate"] > 0:
        n = best["mate"]
        if n > 5 or (n > 1 and _mate_ambiguous(second, n)):
            return None
        for step in range(n):
            remaining = n - step
            if step > 0:
                ls = _lines(eng, b, seconds, 2)
                if not ls or ls[0]["mate"] is None or ls[0]["mate"] <= 0:
                    return None
                best = ls[0]
                if remaining > 1 and _mate_ambiguous(ls[1] if len(ls) > 1 else None, best["mate"]):
                    return None
            b.push(best["move"])
            moves.append(best["move"].uci())
            if b.is_checkmate():
                break
            reply = _lines(eng, b, seconds / 2, 1)
            if not reply:
                return None
            b.push(reply[0]["move"])
            moves.append(reply[0]["move"].uci())
        if not b.is_checkmate():
            return None
        return moves, {"mate": n, "wp": 100.0}

    if best["wp"] < WINNING_WP or best["wp"] - second["wp"] < UNIQUE_GAP:
        return None
    first_wp = best["wp"]
    for step in range(max_player):
        if step > 0:
            ls = _lines(eng, b, seconds, 2)
            if len(ls) < 2:
                break
            best, second = ls
            if best["mate"] is not None and best["mate"] > 0:
                if _mate_ambiguous(second, best["mate"]):
                    break
            elif best["wp"] < WINNING_WP or best["wp"] - second["wp"] < UNIQUE_GAP:
                break
        b.push(best["move"])
        moves.append(best["move"].uci())
        if b.is_game_over() or step + 1 >= max_player:
            break
        reply = _lines(eng, b, seconds / 2, 1)
        if not reply:
            break
        b.push(reply[0]["move"])
        moves.append(reply[0]["move"].uci())
    if len(moves) % 2 == 0:  # l'exercice se termine toujours par un coup du joueur
        moves.pop()
    return moves, {"mate": None, "wp": first_wp}


def build_safe_move(eng, board, avoid_uci, seconds=0.3):
    """« Éviter la gaffe » : coups sûrs dans une position critique. Retourne (meilleur, autres) ou None."""
    lines = _lines(eng, board, seconds, MAX_SAFE_MOVES + 2)
    if len(lines) < 2:
        return None
    top = lines[0]["wp"]
    good = [ln["move"].uci() for ln in lines if ln["wp"] >= top - SAFE_GAP]
    if avoid_uci in good:
        good.remove(avoid_uci)
    if not good or len(good) > MAX_SAFE_MOVES or len(good) == len(lines):
        return None
    return good[0], good[1:]


def estimate_rating(eng, board, first_uci, n_player, themes):
    """Difficulté estimée : profondeur à partir de laquelle Stockfish trouve (et garde) le 1er coup."""
    found = None
    for depth in range(1, 15):
        inf = eng.analyse(board, chess.engine.Limit(depth=depth))
        pv = inf.get("pv") or []
        if pv and pv[0].uci() == first_uci:
            found = found or depth
        else:
            found = None
    depth = found or 15
    rating = 480 + 120 * depth + 170 * (n_player - 1)
    if "quietMove" in themes:
        rating += 150
    if "sacrifice" in themes:
        rating += 120
    if "mate" in themes and n_player == 1:
        rating -= 80
    return int(max(450, min(2700, rating)))


def make_puzzle(eng, fen, setup_uci, seconds=0.25):
    """Exercice gagnant (tactique ou mat) après le coup `setup_uci` joué depuis `fen`. Dict ou None."""
    board = chess.Board(fen)
    board.push(chess.Move.from_uci(setup_uci))
    if board.is_game_over():
        return None
    res = build_solution(eng, board, seconds)
    if not res:
        return None
    sol, _ = res
    moves = [setup_uci] + sol
    themes = detect_themes(fen, moves)
    n_player = (len(sol) + 1) // 2
    rating = estimate_rating(eng, board, sol[0], n_player, themes)
    return {"fen": fen, "moves": " ".join(moves), "rating": rating, "themes": sorted(themes)}


# ---------------------------------------------------------------------------
# Données pour l'échiquier interactif
# ---------------------------------------------------------------------------
def payload(puzzle):
    """Toutes les positions possibles de l'exercice : l'interface n'a pas besoin de connaître les règles."""
    from . import puzzle_themes

    board = chess.Board(puzzle.fen)
    moves = puzzle.move_list
    setup = chess.Move.from_uci(moves[0])
    setup_san = board.san(setup)
    board.push(setup)
    steps = []
    alternatives = puzzle.alternatives.split()
    for k in range(1, len(moves), 2):
        sol = chess.Move.from_uci(moves[k])
        legal = {}
        for mv in board.legal_moves:
            b2 = board.copy(stack=False)
            san = board.san(mv)
            b2.push(mv)
            legal[mv.uci()] = {"san": display(san), "fen": b2.fen(), "mate": b2.is_checkmate()}
        step = {"fen": board.fen(), "solution": sol.uci(), "solution_san": display(board.san(sol)),
                "accept": [sol.uci()] + (alternatives if k == 1 else []), "legal": legal, "reply": None}
        board.push(sol)
        if k + 1 < len(moves):
            rep = chess.Move.from_uci(moves[k + 1])
            rep_san = board.san(rep)
            board.push(rep)
            step["reply"] = {"uci": rep.uci(), "san": display(rep_san), "fen": board.fen()}
        steps.append(step)
    themes = [puzzle_themes.info(t) for t in puzzle.theme_list if puzzle_themes.is_known(t)]
    data = {
        "id": puzzle.pk, "uid": puzzle.uid, "rating": puzzle.rating, "source": puzzle.source,
        "start_fen": puzzle.fen, "setup": {"uci": setup.uci(), "san": display(setup_san), "fen": steps[0]["fen"] if steps else board.fen()},
        "color": "w" if chess.Board(steps[0]["fen"]).turn == chess.WHITE else "b",
        "steps": steps, "themes": themes, "note": puzzle.note,
    }
    if puzzle.game_id:
        # ?coup=n affiche la position après le coup n : ici, juste avant ton erreur
        data["game_url"] = (f"/parties/{puzzle.game_id}/?coup={puzzle.ply - 1}" if puzzle.ply
                            else f"/parties/{puzzle.game_id}/")
    return data
