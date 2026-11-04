"""Conversion de la notation algébrique anglaise (K Q R B N) vers le français (R D T F C)."""
from django.conf import settings

EN_TO_FR = {"K": "R", "Q": "D", "R": "T", "B": "F", "N": "C"}

PIECE_NAMES = {
    "p": "pion", "n": "cavalier", "b": "fou", "r": "tour", "q": "dame", "k": "roi",
}
PIECE_NAMES_PLURAL = {
    "p": "pions", "n": "cavaliers", "b": "fous", "r": "tours", "q": "dames", "k": "rois",
}


def to_fr(san):
    """'Nxe5+' -> 'Cxe5+', 'e8=Q#' -> 'e8=D#'. Laisse O-O tel quel."""
    if not san:
        return san or ""
    if san.startswith("O-O"):
        return san
    out = EN_TO_FR.get(san[0], san[0]) + san[1:]
    if "=" in out:
        i = out.index("=")
        if i + 1 < len(out):
            out = out[: i + 1] + EN_TO_FR.get(out[i + 1], out[i + 1]) + out[i + 2:]
    return out


def display(san):
    """Notation selon le réglage CHESSCOACH_NOTATION."""
    if getattr(settings, "NOTATION", "fr") == "fr":
        return to_fr(san)
    return san or ""


def display_line(sans):
    return " ".join(display(s) for s in sans)


def display_numbered(sans, start_ply=0):
    """['e4','c5','Nf3'] -> '1.e4 c5 2.Cf3'"""
    out = []
    for k, s in enumerate(sans):
        ply = start_ply + k
        if ply % 2 == 0:
            out.append(f"{ply // 2 + 1}.{display(s)}")
        elif k == 0:
            out.append(f"{ply // 2 + 1}…{display(s)}")
        else:
            out.append(display(s))
    return " ".join(out)


def move_label(ply_index, san):
    """ply 0 -> '1.e4', ply 1 -> '1…e5'."""
    n = ply_index // 2 + 1
    sep = "." if ply_index % 2 == 0 else "…"
    return f"{n}{sep}{display(san)}"
