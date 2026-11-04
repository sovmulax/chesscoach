"""Parties de référence : catalogue (analyzer/data/reference_games.json), recommandations, données du lecteur.

Chaque partie est vérifiée au chargement avec python-chess (coups légaux, mat final
quand il est annoncé) : une entrée erronée est ignorée et signalée dans les logs.
"""
import functools
import io
import json
import logging
from pathlib import Path

import chess
import chess.pgn

from .notation import display

log = logging.getLogger("analyzer")

CATALOGUE_FILE = Path(__file__).resolve().parent.parent / "data" / "reference_games.json"

LEVELS = [("debutant", "Débutant"), ("intermediaire", "Intermédiaire"), ("avance", "Avancé")]
LEVEL_INDEX = {k: i for i, (k, _) in enumerate(LEVELS)}
LEVEL_LABELS = dict(LEVELS)

THEMES = {
    "vigilance": "Vigilance face aux menaces",
    "opening_traps": "Pièges d'ouverture",
    "development": "Développement",
    "king_safety": "Sécurité du roi",
    "open_lines": "Lignes ouvertes",
    "pin": "Clouage",
    "greed": "Gourmandise punie",
    "sacrifice": "Sacrifice",
    "double_check": "Échec double et découverte",
    "deflection": "Déviation",
    "mating_attack": "Attaque contre le roi",
    "coordination": "Coordination des pièces",
    "endgame": "Finale",
    "king_activity": "Roi actif",
    "conversion": "Convertir un avantage",
}

# Constat du diagnostic -> thèmes des parties qui l'illustrent
FINDING_REFS = {
    "first_blunder": ["vigilance", "greed"],
    "lost_from_equal": ["vigilance", "greed"],
    "blunder_rate": ["vigilance"],
    "hanging": ["vigilance", "greed", "pin"],
    "missed_mates": ["mating_attack", "double_check", "sacrifice"],
    "unpunished": ["greed", "development", "open_lines"],
    "conversion": ["conversion", "endgame", "coordination"],
    "king_safety": ["king_safety", "mating_attack"],
    "late_castle": ["king_safety", "development"],
    "motifs": ["vigilance", "pin"],
    "repeated": ["opening_traps", "development"],
    "weak_openings": ["development", "opening_traps"],
    "phase_opening": ["development", "opening_traps"],
    "phase_middlegame": ["mating_attack", "sacrifice", "coordination"],
    "phase_endgame": ["endgame", "king_activity", "conversion"],
    "color_gap": ["development"],
    "plateau": ["coordination", "conversion"],
}
LEVEL_WEIGHT = {"critique": 3, "important": 2, "conseil": 1}

# Thème d'une partie -> thème d'exercices pour s'entraîner dessus
PUZZLE_THEMES = {
    "vigilance": "hangingPiece", "opening_traps": "opening", "development": "opening", "king_safety": "defensiveMove",
    "open_lines": "sacrifice", "pin": "pin", "greed": "hangingPiece", "sacrifice": "sacrifice",
    "double_check": "doubleCheck", "deflection": "deflection", "mating_attack": "mate", "coordination": "fork",
    "endgame": "endgame", "king_activity": "pawnEndgame", "conversion": "endgame",
}


def _moves(entry):
    text = entry["pgn"]
    if entry.get("fen"):
        text = f'[SetUp "1"]\n[FEN "{entry["fen"]}"]\n\n{text}'
    game = chess.pgn.read_game(io.StringIO(text))
    board = chess.Board(entry["fen"]) if entry.get("fen") else chess.Board()
    out = []
    for mv in game.mainline_moves():
        if not board.is_legal(mv):
            raise ValueError(f"coup illégal {mv} après {len(out)} demi-coups")
        out.append(mv)
        board.push(mv)
    if not out:
        raise ValueError("aucun coup")
    if entry.get("expect_mate") and not board.is_checkmate():
        raise ValueError("la position finale devrait être mat")
    return out


@functools.lru_cache(maxsize=1)
def _load():
    data = json.loads(CATALOGUE_FILE.read_text(encoding="utf-8"))
    games = []
    for entry in data["games"]:
        try:
            _moves(entry)
        except Exception as exc:  # noqa: BLE001
            log.warning("Partie de référence « %s » ignorée : %s", entry.get("slug"), exc)
            continue
        entry = dict(entry)
        entry["level_label"] = LEVEL_LABELS.get(entry["level"], entry["level"])
        entry["theme_labels"] = [THEMES.get(t, t) for t in entry["themes"]]
        entry["n_moves"] = (len(_moves(entry)) + 1) // 2
        games.append(entry)
    return games


def catalogue():
    return list(_load())


def get(slug):
    return next((g for g in _load() if g["slug"] == slug), None)


def player_level(export):
    """Niveau estimé d'après l'Elo de la cadence principale de l'export."""
    try:
        basic = export.summary["basic"]
        elo = basic["by_time_class"][basic["main_time_class"]].get("elo_end")
    except (AttributeError, KeyError, TypeError):
        return None
    if not elo:
        return None
    return "debutant" if elo < 1200 else "intermediaire" if elo < 1700 else "avance"


def recommend(export, recs, limit=4):
    """Parties à étudier : celles qui illustrent tes faiblesses, à ton niveau, pas encore étudiées."""
    from ..models import ReferenceStudy

    level = player_level(export)
    done = set(ReferenceStudy.objects.exclude(completed_at=None).values_list("slug", flat=True))
    scored = []
    for order, g in enumerate(_load()):
        score, reasons = 0, []
        for f in (recs or {}).get("findings", []):
            if set(FINDING_REFS.get(f["id"], [])) & set(g["themes"]):
                score += LEVEL_WEIGHT.get(f["level"], 1)
                if f["title"] not in reasons:
                    reasons.append(f["title"])
        if level:
            gap = abs(LEVEL_INDEX[g["level"]] - LEVEL_INDEX[level])
            score += {0: 2, 1: 1}.get(gap, -2)
        if g["slug"] in done:
            score -= 4
        scored.append((-score, order, {**g, "reasons": reasons[:2], "studied": g["slug"] in done}))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [item for _, _, item in scored[:limit]]


def payload(entry):
    """Positions, coups, notes et coups légaux (mode « devine le coup ») pour le lecteur."""
    board = chess.Board(entry["fen"]) if entry.get("fen") else chess.Board()
    hero = entry.get("hero", "w")
    fens, moves = [board.fen()], []
    notes = entry.get("notes", {})
    for i, mv in enumerate(_moves(entry)):
        white = board.turn == chess.WHITE
        n = board.fullmove_number
        key = f"{n}{'w' if white else 'b'}"
        san = board.san(mv)
        item = {"i": i, "san": display(san), "uci": mv.uci(), "label": f"{n}{'.' if white else '…'}{display(san)}",
                "note": notes.get(key), "color": "w" if white else "b"}
        if entry.get("guess", True) and (("w" if white else "b") == hero):
            item["legal"] = [m.uci() for m in board.legal_moves]
        moves.append(item)
        board.push(mv)
        fens.append(board.fen())
    return {
        "fens": fens, "moves": moves, "orientation": hero, "hero": hero,
        "players": {"w": {"name": entry["white"], "elo": None}, "b": {"name": entry["black"], "elo": None}},
        "guess": bool(entry.get("guess", True)), "slug": entry["slug"], "result": entry["result"],
    }
