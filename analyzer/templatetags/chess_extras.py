from django import template

from ..services.notation import PIECE_NAMES, PIECE_NAMES_PLURAL, display, display_line, display_numbered
from ..services.pgn_import import TERMINATION_LABELS

register = template.Library()


@register.filter
def san(value):
    return display(value)


@register.filter
def line(value):
    return display_numbered(value or [])


@register.filter
def frdate(value):
    """'2026-06-20' -> '20/06/2026'"""
    if not value or not isinstance(value, str) or len(value) < 10:
        return value or "—"
    y, m, d = value[:10].replace(".", "-").split("-")
    return f"{d}/{m}/{y}"


@register.filter
def get(d, key):
    if d is None:
        return None
    try:
        return d.get(key)
    except AttributeError:
        try:
            return d[key]
        except (KeyError, IndexError, TypeError):
            return None


@register.filter
def piece_plural(sym):
    return PIECE_NAMES_PLURAL.get(sym, sym)


@register.filter
def piece_name(sym):
    return PIECE_NAMES.get(sym, sym)


@register.filter
def num(value, digits=1):
    """Nombre au format français : 12.5 -> 12,5 ; None -> —."""
    if value is None or value == "":
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return value
    digits = int(digits)
    txt = f"{v:.{digits}f}" if digits else f"{v:.0f}"
    if digits and txt.endswith("0" * digits):
        txt = txt[: -(digits + 1)]
    return txt.replace(".", ",").replace("-", "−")


@register.filter
def signed(value, digits=1):
    if value is None:
        return "—"
    v = float(value)
    s = num(abs(v), digits)
    return ("+" if v > 0 else "−" if v < 0 else "") + s


@register.filter
def pawns(cp):
    """Centipions -> pions signés ; les mats (±10000) deviennent « mat »."""
    if cp is None:
        return "—"
    if abs(cp) >= 9000:
        return "mat pour toi" if cp > 0 else "mat contre toi"
    return signed(cp / 100, 1)


@register.filter
def term_label(kind):
    return TERMINATION_LABELS.get(kind, kind)


@register.filter
def pct_width(value, maximum):
    try:
        return max(2, round(100 * float(value) / float(maximum))) if float(maximum) else 0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def color_label(c):
    return {"w": "Blancs", "b": "Noirs"}.get(c, c)


@register.filter
def result_label(r):
    return {"win": "Victoire", "draw": "Nulle", "loss": "Défaite"}.get(r, r)


@register.filter
def level_label(level):
    return {"critique": "Priorité 1", "important": "Priorité 2", "conseil": "À surveiller"}.get(level, level)


@register.filter
def phase_label(p):
    return {"opening": "Ouverture", "middlegame": "Milieu de partie", "endgame": "Finale"}.get(p, p)
