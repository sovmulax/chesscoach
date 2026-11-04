"""Phrases d'explication pour un coup annoté (affichées dans l'analyse d'une partie)."""
from .notation import PIECE_NAMES, display, display_line

CLASS_LABELS = {
    "best": "Meilleur coup",
    "good": "Bon coup",
    "inaccuracy": "Imprécision",
    "mistake": "Erreur",
    "blunder": "Gaffe",
}

CLASS_SYMBOLS = {"inaccuracy": "?!", "mistake": "?", "blunder": "??"}

PHASE_LABELS = {"opening": "Ouverture", "middlegame": "Milieu de partie", "endgame": "Finale"}


def describe(move):
    """Retourne une liste de phrases expliquant le coup (du point de vue de celui qui joue)."""
    out = []
    who_you = move["mine"]
    tags = move.get("tags", [])
    best = display(move.get("best")) if move.get("best") else None
    played = display(move["san"])

    if "missed_mate" in tags:
        n = move.get("mate_before")
        if not best:
            out.append(f"Un mat en {n} était disponible.")
        elif n == 1:
            out.append(f"Mat en 1 disponible : {best}.")
        else:
            out.append(f"Mat en {n} disponible : {display_line(move.get('pv', [])[: 2 * n - 1])}.")
    elif "missed_mate_1" in tags and best:
        out.append(f"Mat en 1 disponible : {best} (le mat reste possible, mais il était immédiat).")
    if "allowed_mate" in tags:
        n = abs(move.get("mate_after") or 0)
        out.append(f"Ce coup autorise un mat forcé en {n}." if n else "Ce coup autorise un mat forcé.")
    if "hanging" in tags and move.get("captured"):
        piece = PIECE_NAMES.get(move["captured"], "pièce")
        sq = move.get("captured_square", "")
        reply = display(move.get("reply"))
        if move.get("captured_is_moved"):
            out.append(f"La pièce jouée n'est pas protégée : {reply} prend le {piece} en {sq}.")
        else:
            out.append(f"{'Tu laisses' if who_you else 'Laisse'} le {piece} {sq} sans défense ou une menace non parée : "
                       f"{reply} le gagne.")
    elif move.get("reply") and move["cls"] in ("mistake", "blunder"):
        out.append(f"Réponse forte de l'adversaire : {display(move['reply'])}.")
    if "missed_punish" in tags:
        out.append(f"L'adversaire venait de gaffer ({display(move.get('punish_of'))}) : "
                   f"{best} permettait d'en profiter." if best else "L'adversaire venait de gaffer.")
    if "stalemate" in tags:
        out.append("Ce coup mène au pat alors que la partie était gagnée : vérifie toujours que le roi adverse a une case.")
    if "time_trouble" in tags:
        out.append(f"Joué avec moins de 30 s à la pendule ({int(move['clock'])} s).")

    if move["cls"] in ("inaccuracy", "mistake", "blunder"):
        tail = f"Chances de gain : {move['wp_before']:.0f} % → {move['wp_after']:.0f} %."
        if best and best != played:
            pv = move.get("pv", [])[:4]
            tail = (f"Meilleur : {best} ({display_line(pv)}). " if len(pv) > 1 else f"Meilleur : {best}. ") + tail
        out.append(tail)
    return out
