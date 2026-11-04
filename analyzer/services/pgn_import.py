"""Lecture des fichiers PGN et création des parties en base."""
import collections
import datetime as dt
import hashlib
import io
import re

import chess
import chess.pgn
from django.db import transaction
from django.utils import timezone

from ..models import Export, Game
from . import openings

OPENING_PLIES = 10


def decode(data):
    if isinstance(data, str):
        return data.lstrip("﻿")
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def split_games(pgn_text):
    """Découpe un texte PGN en parties python-chess (ignore les parties illisibles)."""
    stream = io.StringIO(pgn_text)
    games = []
    while True:
        try:
            game = chess.pgn.read_game(stream)
        except Exception:  # noqa: BLE001 - un PGN corrompu ne doit pas tout bloquer
            continue
        if game is None:
            break
        if game.errors and not list(game.mainline_moves()):
            continue
        games.append(game)
    return games


def detect_player(games):
    """Le joueur présent dans le plus de parties est le propriétaire de l'export."""
    counter = collections.Counter()
    for g in games:
        for side in ("White", "Black"):
            name = g.headers.get(side, "").strip()
            if name and name != "?":
                counter[name.lower()] += 1
    if not counter:
        return ""
    name_lower = counter.most_common(1)[0][0]
    for g in games:  # retrouve la casse d'origine
        for side in ("White", "Black"):
            if g.headers.get(side, "").lower() == name_lower:
                return g.headers[side]
    return name_lower


def time_class_from_control(tc):
    """Approximation des cadences Chess.com : bullet < 3 min, blitz < 10 min, sinon rapide."""
    if not tc or tc in ("-", "?"):
        return ""
    if "/" in tc:
        return "daily"
    m = re.match(r"(\d+)(?:\+(\d+))?", tc)
    if not m:
        return ""
    base, inc = int(m.group(1)), int(m.group(2) or 0)
    est = base + 40 * inc
    if est < 180:
        return "bullet"
    if est < 600:
        return "blitz"
    return "rapid"


def termination_kind(text, result):
    t = (text or "").lower()
    if result == "1/2-1/2":
        if "pat" in t.split() or "stalemate" in t or "par pat" in t:
            return "stalemate"
        if "répétition" in t or "repetition" in t:
            return "repetition"
        if "accord" in t or "agreement" in t:
            return "agreement"
        if "matériel" in t or "material" in t:
            return "insufficient"
        if "50" in t:
            return "fifty"
        if "temps" in t or "time" in t:
            return "timeout_draw"
        return "draw"
    if "abandonnée" in t or "abandoned" in t:
        return "abandoned"
    if "abandon" in t or "resign" in t:
        return "resignation"
    if "temps" in t or "time" in t:
        return "timeout"
    if "mat" in t or "checkmate" in t:
        return "checkmate"
    return "other"


TERMINATION_LABELS = {
    "checkmate": "Échec et mat", "resignation": "Abandon", "timeout": "Au temps",
    "abandoned": "Partie quittée", "stalemate": "Pat", "repetition": "Répétition",
    "agreement": "Accord mutuel", "insufficient": "Manque de matériel",
    "fifty": "Règle des 50 coups", "timeout_draw": "Temps vs manque de matériel",
    "draw": "Nulle", "other": "Autre",
}


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_played_at(headers, end_time_unix=None):
    if end_time_unix:
        return dt.datetime.fromtimestamp(int(end_time_unix), tz=dt.timezone.utc)
    date = headers.get("UTCDate") or headers.get("EndDate") or headers.get("Date") or ""
    clock = headers.get("UTCTime") or headers.get("EndTime") or "00:00:00"
    clock = clock.split(" ")[0]
    try:
        d = dt.datetime.strptime(f"{date} {clock}", "%Y.%m.%d %H:%M:%S")
        return d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        try:
            return dt.datetime.strptime(date, "%Y.%m.%d").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            return None


def game_uid(game, pgn_text, url=""):
    if url:
        return url
    link = game.headers.get("Link", "")
    if link:
        return link
    h = game.headers
    basis = "|".join([h.get("White", ""), h.get("Black", ""), h.get("Date", ""),
                      h.get("UTCTime", "") or h.get("EndTime", ""), str(game.mainline_moves())])
    return "sha1:" + hashlib.sha1(basis.encode()).hexdigest()


def build_game(export, game, pgn_text, player, extra=None):
    """Construit (sans sauvegarder) un objet Game. Retourne None si le joueur n'y figure pas."""
    extra = extra or {}
    h = game.headers
    white, black = h.get("White", "?"), h.get("Black", "?")
    if white.lower() == player.lower():
        color = "w"
    elif black.lower() == player.lower():
        color = "b"
    else:
        return None
    result = h.get("Result", "*")
    if result == "1/2-1/2":
        pres = "draw"
    elif result == "1-0":
        pres = "win" if color == "w" else "loss"
    elif result == "0-1":
        pres = "win" if color == "b" else "loss"
    else:
        return None  # partie en cours / sans résultat

    board = game.board()
    sans = []
    for i, move in enumerate(game.mainline_moves()):
        if i < OPENING_PLIES:
            sans.append(board.san(move))
        board.push(move)
    num_plies = board.ply() - game.board().ply()

    tc = h.get("TimeControl", "")
    wel, bel = _int(h.get("WhiteElo")), _int(h.get("BlackElo"))
    return Game(
        export=export,
        uid=game_uid(game, pgn_text, extra.get("url", "")),
        pgn=pgn_text,
        headers=dict(h),
        played_at=parse_played_at(h, extra.get("end_time")),
        date=h.get("Date", "").replace("?", ""),
        white=white, black=black, white_elo=wel, black_elo=bel,
        result=result,
        termination=h.get("Termination", ""),
        termination_kind=termination_kind(h.get("Termination", ""), result),
        time_control=tc,
        time_class=extra.get("time_class") or time_class_from_control(tc),
        url=extra.get("url") or h.get("Link", ""),
        player_color=color,
        player_result=pres,
        player_elo=wel if color == "w" else bel,
        opponent=black if color == "w" else white,
        opponent_elo=bel if color == "w" else wel,
        opening_name=openings.identify(sans, h),
        opening_moves=" ".join(sans),
        num_plies=num_plies,
    )


def game_to_pgn(game):
    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=True)
    return game.accept(exporter)


def add_games(export, items):
    """items = liste de (chess.pgn.Game, pgn_text, extra). Retourne (ajoutées, ignorées)."""
    existing = set(export.games.values_list("uid", flat=True))
    new, skipped = [], 0
    for game, text, extra in items:
        obj = build_game(export, game, text, export.player, extra)
        if obj is None or obj.uid in existing:
            skipped += 1
            continue
        existing.add(obj.uid)
        new.append(obj)
    with transaction.atomic():
        Game.objects.bulk_create(new, batch_size=200)
    if new:
        export.summary_key = ""  # invalide le cache du résumé
        export.save(update_fields=["summary_key"])
    return len(new), skipped


def import_pgn_text(pgn_text, name="", player="", analysis_time=None):
    """Crée un Export depuis un texte PGN. Retourne (export, ajoutées, ignorées)."""
    from django.conf import settings

    text = decode(pgn_text)
    games = split_games(text)
    if not games:
        raise ValueError("Aucune partie lisible dans ce fichier PGN.")
    player = player.strip() or detect_player(games)
    if not name:
        name = f"Export {player} du {timezone.localdate():%d/%m/%Y}"
    export = Export.objects.create(
        name=name, kind=Export.KIND_PGN, player=player,
        analysis_time=analysis_time or settings.ANALYSIS_TIME_BULK,
    )
    items = [(g, game_to_pgn(g), {}) for g in games]
    added, skipped = add_games(export, items)
    return export, added, skipped
