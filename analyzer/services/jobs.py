"""Tâches longues exécutées dans des threads d'arrière-plan.

Pas besoin de Celery ni de Redis : Stockfish tourne dans ses propres
processus, donc quelques threads Python suffisent à paralléliser l'analyse.
Le thread coordinateur est le seul à écrire en base (SQLite n'aime pas les
écritures concurrentes).
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import chess.engine
from django.conf import settings
from django.db import close_old_connections, connection
from django.utils import timezone

from ..models import Export, Game
from . import engine as engine_mod
from . import metrics

log = logging.getLogger("analyzer")

_lock = threading.Lock()
_running = {}  # clé -> Thread
_cancel = set()


def is_running(kind, pk):
    with _lock:
        t = _running.get((kind, pk))
        return bool(t and t.is_alive())


HEARTBEAT_SECONDS = 120


def export_running(export):
    """Analyse en cours dans ce processus, ou dans un autre (commande en ligne) qui donne signe de vie."""
    if is_running("export", export.pk):
        return True
    return bool(export.status == Export.STATUS_RUNNING and export.job_heartbeat
                and (timezone.now() - export.job_heartbeat).total_seconds() < HEARTBEAT_SECONDS)


def request_cancel(kind, pk):
    with _lock:
        _cancel.add((kind, pk))


def _start(kind, pk, target, *args):
    key = (kind, pk)
    with _lock:
        t = _running.get(key)
        if t and t.is_alive():
            return False
        _cancel.discard(key)
        t = threading.Thread(target=_wrap, args=(key, target, args), daemon=True, name=f"{kind}-{pk}")
        _running[key] = t
        t.start()
    return True


def _wrap(key, target, args):
    close_old_connections()
    try:
        target(*args)
    except Exception:  # noqa: BLE001
        log.exception("Tâche %s en échec", key)
    finally:
        with _lock:
            _running.pop(key, None)
            _cancel.discard(key)
        connection.close()


# ---------------------------------------------------------------------------
# Sauvegarde / recalcul
# ---------------------------------------------------------------------------
def save_analysis(game, plies, time_per_position):
    game.analysis = plies
    game.stats = metrics.compute_game_stats(plies, game.player_color, game.player_result)
    game.analysis_time = time_per_position
    game.status = Game.STATUS_DONE
    game.analyzed_at = timezone.now()
    game.error = ""
    game.save(update_fields=["analysis", "stats", "analysis_time", "status", "analyzed_at", "error"])


def refresh_stats_if_outdated(games):
    """Recalcule les métriques (sans moteur) si le code des métriques a changé."""
    changed = 0
    for g in games:
        if g.analysis and (not g.stats or g.stats.get("version") != metrics.METRICS_VERSION):
            g.stats = metrics.compute_game_stats(g.analysis, g.player_color, g.player_result)
            g.save(update_fields=["stats"])
            changed += 1
    return changed


def heal_stale(export):
    """Si le serveur a redémarré pendant une analyse, remet les compteurs d'aplomb."""
    if export_running(export):
        return
    if export.status == Export.STATUS_RUNNING:
        export.status = Export.STATUS_IDLE
        export.job_message = "Analyse interrompue (serveur arrêté). Relance-la : elle reprendra où elle s'est arrêtée."
        export.save(update_fields=["status", "job_message"])
    stale = export.games.filter(status__in=[Game.STATUS_QUEUED, Game.STATUS_RUNNING])
    if stale.exists():
        for g in stale:
            if not is_running("game", g.pk):
                g.status = Game.STATUS_DONE if g.stats else Game.STATUS_PENDING
                g.save(update_fields=["status"])


# ---------------------------------------------------------------------------
# Analyse d'un export
# ---------------------------------------------------------------------------
def start_export_analysis(export_id, time_per_position=None, reanalyze=False):
    return _start("export", export_id, _run_export, export_id, time_per_position, reanalyze)


def _run_export(export_id, time_per_position, reanalyze):
    export = Export.objects.get(pk=export_id)
    t = time_per_position or export.analysis_time or settings.ANALYSIS_TIME_BULK
    qs = export.games.all()
    if not reanalyze:
        qs = qs.exclude(status=Game.STATUS_DONE)
    todo = list(qs.values_list("id", "pgn"))
    export.analysis_time = t
    export.job_started_at = timezone.now()
    export.job_finished_at = None
    if not todo:
        export.status = Export.STATUS_DONE
        export.job_message = "Toutes les parties sont déjà analysées."
        export.save()
        return
    try:
        engine_mod.find_stockfish()
    except engine_mod.EngineNotFound as exc:
        export.status = Export.STATUS_ERROR
        export.job_message = str(exc)
        export.save()
        return

    export.status = Export.STATUS_RUNNING
    export.job_heartbeat = timezone.now()
    export.job_message = f"0 / {len(todo)} parties analysées"
    export.save()
    Game.objects.filter(id__in=[gid for gid, _ in todo]).update(status=Game.STATUS_QUEUED)

    workers = max(1, min(settings.ANALYSIS_WORKERS, len(todo)))
    local = threading.local()
    engines, eng_lock = [], threading.Lock()

    def get_engine(force_new=False):
        if force_new or not getattr(local, "eng", None):
            e = engine_mod.open_engine()
            local.eng = e
            with eng_lock:
                engines.append(e)
        return local.eng

    def work(pgn):
        try:
            return engine_mod.analyze_pgn(pgn, get_engine(), t)
        except chess.engine.EngineTerminatedError:
            return engine_mod.analyze_pgn(pgn, get_engine(force_new=True), t)

    done = errors = 0
    cancelled = False
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(work, pgn): gid for gid, pgn in todo}
            for fut in as_completed(futures):
                gid = futures[fut]
                try:
                    plies = fut.result()
                    save_analysis(Game.objects.get(pk=gid), plies, t)
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    log.warning("Partie %s : %s", gid, exc)
                    Game.objects.filter(pk=gid).update(status=Game.STATUS_ERROR, error=str(exc)[:300])
                done += 1
                Export.objects.filter(pk=export_id).update(
                    job_heartbeat=timezone.now(), status=Export.STATUS_RUNNING,
                    job_message=f"{done} / {len(todo)} parties analysées" + (f" ({errors} en erreur)" if errors else ""))
                if ("export", export_id) in _cancel:
                    cancelled = True
                    for f in futures:
                        f.cancel()
                    break
    finally:
        for e in engines:
            try:
                e.quit()
            except Exception:  # noqa: BLE001
                pass
        Game.objects.filter(export_id=export_id, status__in=[Game.STATUS_QUEUED, Game.STATUS_RUNNING]).update(
            status=Game.STATUS_PENDING)

    export = Export.objects.get(pk=export_id)
    export.status = Export.STATUS_IDLE if cancelled else Export.STATUS_DONE
    export.job_finished_at = timezone.now()
    elapsed = (export.job_finished_at - export.job_started_at).total_seconds()
    export.job_message = (f"Analyse arrêtée après {done} parties." if cancelled else
                          f"{done} parties analysées en " + f"{elapsed / 60:.1f}".replace(".", ",") + " min" + (f", {errors} en erreur." if errors else "."))
    export.summary_key = ""
    export.save()


# ---------------------------------------------------------------------------
# Analyse d'une partie
# ---------------------------------------------------------------------------
def start_game_analysis(game_id, time_per_position=None):
    Game.objects.filter(pk=game_id).update(status=Game.STATUS_QUEUED, error="")
    return _start("game", game_id, _run_game, game_id, time_per_position)


def _run_game(game_id, time_per_position):
    game = Game.objects.get(pk=game_id)
    t = time_per_position or settings.ANALYSIS_TIME_SINGLE
    try:
        game.status = Game.STATUS_RUNNING
        game.save(update_fields=["status"])
        eng = engine_mod.open_engine()
        try:
            plies = engine_mod.analyze_pgn(game.pgn, eng, t)
        finally:
            eng.quit()
        save_analysis(game, plies, t)
        Export.objects.filter(pk=game.export_id).update(summary_key="")
    except Exception as exc:  # noqa: BLE001
        Game.objects.filter(pk=game_id).update(status=Game.STATUS_ERROR, error=str(exc)[:300])
        raise


# ---------------------------------------------------------------------------
# Synchronisation Chess.com
# ---------------------------------------------------------------------------
def start_chesscom_sync(export_id, full=False):
    return _start("sync", export_id, _run_sync, export_id, full)


def _run_sync(export_id, full):
    from . import chesscom

    export = Export.objects.get(pk=export_id)
    try:
        added, msg = chesscom.sync_export(export, full=full)
    except Exception as exc:  # noqa: BLE001
        Export.objects.filter(pk=export_id).update(sync_message=f"Échec de la synchro : {exc}"[:300])
        raise
    export.refresh_from_db()
    if added and export.auto_analyze and engine_mod.engine_available():
        start_export_analysis(export_id)


# ---------------------------------------------------------------------------
# Exercices tirés des parties d'un export
# ---------------------------------------------------------------------------
_puzzle_progress = {}


def puzzle_job_status(export_id):
    return {"running": is_running("puzzles", export_id), "message": _puzzle_progress.get(export_id, "")}


def start_puzzle_generation(export_id, limit_games=150, seconds=0.25):
    _puzzle_progress[export_id] = "Préparation…"
    return _start("puzzles", export_id, _run_puzzles, export_id, limit_games, seconds)


def _run_puzzles(export_id, limit_games=150, seconds=0.25):
    from . import training

    export = Export.objects.get(pk=export_id)
    games = training.candidate_games(export, limit_games)
    if not games:
        _puzzle_progress[export_id] = "Aucune nouvelle partie analysée à parcourir."
        return 0
    try:
        engine_mod.find_stockfish()
    except engine_mod.EngineNotFound as exc:
        _puzzle_progress[export_id] = str(exc)
        return 0

    local = threading.local()
    engines, eng_lock = [], threading.Lock()

    def work(game):
        if not getattr(local, "eng", None):
            local.eng = engine_mod.open_engine()
            with eng_lock:
                engines.append(local.eng)
        items = []
        for m in training.game_candidates(game):
            try:
                p = training.puzzle_from_mistake(local.eng, game, m, seconds)
            except chess.engine.EngineTerminatedError:
                local.eng = engine_mod.open_engine()
                with eng_lock:
                    engines.append(local.eng)
                continue
            if p:
                items.append(p)
        return items

    done = created = 0
    workers = max(1, min(settings.ANALYSIS_WORKERS, len(games)))
    _puzzle_progress[export_id] = f"0 / {len(games)} parties parcourues"
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(work, g): g for g in games}
            for fut in as_completed(futures):
                game = futures[fut]
                try:
                    created += training.save_game_puzzles(game, fut.result())
                except Exception as exc:  # noqa: BLE001
                    log.warning("Exercices de la partie %s : %s", game.pk, exc)
                done += 1
                _puzzle_progress[export_id] = f"{done} / {len(games)} parties parcourues · {created} exercice(s) créé(s)"
                if ("puzzles", export_id) in _cancel:
                    for f in futures:
                        f.cancel()
                    break
    finally:
        for e in engines:
            try:
                e.quit()
            except Exception:  # noqa: BLE001
                pass
    _puzzle_progress[export_id] = f"Terminé : {created} exercice(s) créé(s) à partir de {done} partie(s)."
    return created
