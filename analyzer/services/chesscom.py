"""Synchronisation avec l'API publique de Chess.com (gratuite, sans clé ni connexion).

Doc : https://support.chess.com/en/articles/9650547-published-data-api
  /pub/player/{user}/games/archives      -> liste des archives mensuelles
  /pub/player/{user}/games/{YYYY}/{MM}   -> parties du mois (JSON, avec le PGN)

Les requêtes sont faites une par une (Chess.com limite les appels parallèles).
Le mois en cours est re-téléchargé à chaque synchro ; les mois passés une seule fois.
"""
import io
import json
import logging
import time
import urllib.error
import urllib.request

import chess.pgn
from django.conf import settings
from django.utils import timezone

from ..models import Export
from .pgn_import import add_games

log = logging.getLogger("analyzer")
BASE = "https://api.chess.com/pub/player"


class ChessComError(RuntimeError):
    pass


def _get(url, etag=None, retries=3):
    """GET JSON. Retourne (données | None si 304, etag)."""
    headers = {"User-Agent": settings.CHESSCOM_USER_AGENT, "Accept": "application/json"}
    if etag:
        headers["If-None-Match"] = etag
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8")), resp.headers.get("ETag")
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return None, etag
            if exc.code == 404:
                raise ChessComError("Joueur ou archive introuvable sur Chess.com (404).") from exc
            if exc.code == 429 and attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise ChessComError(f"Chess.com a répondu {exc.code}.") from exc
        except urllib.error.URLError as exc:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            raise ChessComError(f"Impossible de joindre Chess.com : {exc.reason}") from exc
    raise ChessComError("Chess.com ne répond pas.")


def check_player(username):
    data, _ = _get(f"{BASE}/{username.lower()}")
    return data.get("username") or username


def archive_key(url):
    """.../games/2026/05 -> '2026/05'"""
    parts = url.rstrip("/").split("/")
    return f"{parts[-2]}/{parts[-1]}"


def archives_to_fetch(archive_urls, synced, full=False):
    if full or not synced:
        return list(archive_urls)
    latest = max(synced) if synced else ""
    # Mois jamais synchronisés + le dernier mois synchronisé (et tout ce qui suit),
    # car le mois en cours continue de recevoir des parties.
    return [u for u in archive_urls if archive_key(u) not in synced or archive_key(u) >= latest]


def games_from_archive(data, time_classes=None):
    items = []
    for g in data.get("games", []):
        if g.get("rules", "chess") != "chess" or not g.get("pgn"):
            continue
        if time_classes and g.get("time_class") not in time_classes:
            continue
        game = chess.pgn.read_game(io.StringIO(g["pgn"]))
        if game is None:
            continue
        items.append((game, g["pgn"], {
            "url": g.get("url", ""),
            "end_time": g.get("end_time"),
            "time_class": g.get("time_class", ""),
        }))
    return items


def sync_export(export, full=False, progress=None):
    """Télécharge les nouvelles parties du compte. Retourne (nb ajoutées, message)."""
    if export.kind != Export.KIND_CHESSCOM:
        raise ChessComError("Cet export n'est pas lié à un compte Chess.com.")
    user = export.player.lower()
    Export.objects.filter(pk=export.pk).update(sync_message="Synchronisation en cours…")
    data, _ = _get(f"{BASE}/{user}/games/archives")
    urls = data.get("archives", [])
    synced = dict(export.synced_archives or {})
    todo = archives_to_fetch(urls, synced, full)
    added_total = 0
    for i, url in enumerate(todo, 1):
        key = archive_key(url)
        prev = synced.get(key) or {}
        Export.objects.filter(pk=export.pk).update(
            sync_message=f"Archive {key} ({i}/{len(todo)}) — {added_total} nouvelles parties")
        month, etag = _get(url, etag=None if full else prev.get("etag"))
        if month is not None:
            added, _ = add_games(export, games_from_archive(month, export.time_class_list))
            added_total += added
        synced[key] = {"etag": etag, "at": timezone.now().isoformat()}
        if progress:
            progress(i, len(todo), added_total)
        time.sleep(0.3)  # politesse envers l'API
    export.synced_archives = synced
    export.last_sync_at = timezone.now()
    export.sync_message = (f"{added_total} nouvelle(s) partie(s) importée(s) depuis {len(todo)} archive(s) mensuelle(s)."
                           if todo else "Aucune archive à télécharger.")
    export.save(update_fields=["synced_archives", "last_sync_at", "sync_message"])
    return added_total, export.sync_message


def create_chesscom_export(username, time_classes="", auto_analyze=True, analysis_time=None):
    real = check_player(username)
    existing = Export.objects.filter(kind=Export.KIND_CHESSCOM, player__iexact=real).first()
    if existing:
        return existing, False
    export = Export.objects.create(
        name=f"Chess.com · {real}", kind=Export.KIND_CHESSCOM, player=real,
        time_classes=time_classes, auto_analyze=auto_analyze,
        analysis_time=analysis_time or settings.ANALYSIS_TIME_BULK,
    )
    return export, True
