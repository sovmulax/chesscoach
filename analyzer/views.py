import datetime as dt

import chess.svg
from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import AnalyzeForm, ChessComForm, PGNUploadForm
from .models import Export, Game
from .services import chesscom, engine, explain, jobs, metrics, pgn_import, recommendations, summary
from .services.notation import display, move_label

TIME_CLASS_LABELS = {"bullet": "Bullet", "blitz": "Blitz", "rapid": "Rapide", "daily": "Daily", "?": "Inconnue", "": "Inconnue"}


def _export_flags(export):
    return {
        "analysis_running": jobs.export_running(export),
        "sync_running": jobs.is_running("sync", export.pk),
    }


# ---------------------------------------------------------------------------
# Liste des exports + ajout
# ---------------------------------------------------------------------------
def export_list(request):
    if request.method == "POST":
        form = PGNUploadForm(request.POST, request.FILES)
        if form.is_valid():
            data = form.cleaned_data
            try:
                export, added, skipped = pgn_import.import_pgn_text(
                    data["pgn_file"].read(), data["name"], data["player"], float(data["analysis_time"]))
            except ValueError as exc:
                form.add_error("pgn_file", str(exc))
            else:
                messages.success(request, f"{added} parties importées pour {export.player}"
                                 + (f" ({skipped} ignorées : doublons ou joueur absent)." if skipped else "."))
                if data["analyze_now"]:
                    jobs.start_export_analysis(export.pk, float(data["analysis_time"]))
                return redirect(export)
    else:
        form = PGNUploadForm()
    exports = Export.objects.annotate(
        n_games=Count("games"), n_done=Count("games", filter=Q(games__status=Game.STATUS_DONE)))
    for e in exports:
        e.flags = _export_flags(e)
    return render(request, "analyzer/export_list.html", {
        "exports": exports, "form": form, "cc_form": ChessComForm(),
        "engine_ok": engine.engine_available(),
    })


@require_POST
def chesscom_add(request):
    form = ChessComForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Formulaire Chess.com invalide.")
        return redirect("analyzer:export_list")
    d = form.cleaned_data
    try:
        export, created = chesscom.create_chesscom_export(
            d["username"], ",".join(d["time_classes"]), d["auto_analyze"], float(d["analysis_time"]))
    except chesscom.ChessComError as exc:
        messages.error(request, str(exc))
        return redirect("analyzer:export_list")
    if created:
        messages.success(request, f"Compte {export.player} ajouté : import de tout l'historique en cours…")
    else:
        messages.info(request, f"Le compte {export.player} existe déjà : synchronisation lancée.")
    jobs.start_chesscom_sync(export.pk, full=created)
    return redirect(export)


# ---------------------------------------------------------------------------
# Tableau de bord d'un export
# ---------------------------------------------------------------------------
def _light_games(export, time_class=None):
    qs = export.games.defer("analysis", "pgn")
    if time_class:
        qs = qs.filter(time_class=time_class)
    return list(qs)


def _ensure_stats_current(export):
    outdated = export.games.filter(analysis__isnull=False).exclude(stats__version=metrics.METRICS_VERSION)
    if outdated.exists():
        jobs.refresh_stats_if_outdated(outdated)
        export.summary_key = ""


def get_summary(export, time_class=None):
    _ensure_stats_current(export)
    games = _light_games(export, time_class)
    if time_class:
        return summary.compute_summary(games), games
    key = summary.summary_cache_key(export, games)
    if export.summary is None or export.summary_key != key:
        export.summary = summary.compute_summary(games)
        export.summary_key = key
        Export.objects.filter(pk=export.pk).update(summary=export.summary, summary_key=key)
    return export.summary, games


def _maybe_auto_sync(export):
    hours = settings.CHESSCOM_AUTO_SYNC_HOURS
    if not export.is_chesscom or not hours or jobs.is_running("sync", export.pk):
        return
    if export.last_sync_at is None or timezone.now() - export.last_sync_at > dt.timedelta(hours=hours):
        jobs.start_chesscom_sync(export.pk, full=export.last_sync_at is None)


def export_detail(request, pk):
    export = get_object_or_404(Export, pk=pk)
    jobs.heal_stale(export)
    _maybe_auto_sync(export)
    tc = request.GET.get("cadence") or None
    summ, games = get_summary(export, tc)
    recs = recommendations.build(summ) if summ.get("n_games") else None
    by_id = {g.id: g for g in games}
    time_classes = (export.games.values("time_class").annotate(n=Count("id")).order_by("-n"))
    ctx = {
        "export": export, "s": summ, "recs": recs, "games_by_id": by_id,
        "time_class": tc, "time_classes": [(t["time_class"], TIME_CLASS_LABELS.get(t["time_class"], t["time_class"]), t["n"]) for t in time_classes],
        "analyze_form": AnalyzeForm(initial={"analysis_time": str(export.analysis_time)}),
        "engine_ok": engine.engine_available(),
        "tc_labels": TIME_CLASS_LABELS,
        **_export_flags(export),
        **_progress(export),
    }
    return render(request, "analyzer/export_detail.html", ctx)


def export_games(request, pk):
    export = get_object_or_404(Export, pk=pk)
    jobs.heal_stale(export)
    games = export.games.defer("analysis", "pgn").order_by("-played_at", "-id")
    return render(request, "analyzer/export_games.html", {
        "export": export, "games": games, "tc_labels": TIME_CLASS_LABELS, "engine_ok": engine.engine_available(),
        **_export_flags(export), **_progress(export),
    })


def _progress(export):
    agg = export.games.aggregate(
        total=Count("id"),
        done=Count("id", filter=Q(status=Game.STATUS_DONE)),
        errors=Count("id", filter=Q(status=Game.STATUS_ERROR)),
    )
    agg["pct"] = round(100 * agg["done"] / agg["total"]) if agg["total"] else 0
    agg["remaining"] = agg["total"] - agg["done"]
    return {"progress": agg}


@require_POST
def export_analyze(request, pk):
    export = get_object_or_404(Export, pk=pk)
    form = AnalyzeForm(request.POST)
    t = float(form.data.get("analysis_time") or export.analysis_time)
    reanalyze = bool(form.data.get("reanalyze"))
    if not engine.engine_available():
        messages.error(request, "Stockfish est introuvable : voir le README pour l'installer.")
    elif jobs.start_export_analysis(export.pk, t, reanalyze):
        messages.success(request, "Analyse lancée. Tu peux fermer la page : elle continue tant que le serveur tourne.")
    else:
        messages.info(request, "Une analyse est déjà en cours pour cet export.")
    return redirect(request.POST.get("next") or export.get_absolute_url())


@require_POST
def export_stop(request, pk):
    jobs.request_cancel("export", pk)
    messages.info(request, "Arrêt demandé : les parties déjà analysées sont conservées.")
    return redirect("analyzer:export_detail", pk=pk)


@require_POST
def export_sync(request, pk):
    export = get_object_or_404(Export, pk=pk, kind=Export.KIND_CHESSCOM)
    full = bool(request.POST.get("full"))
    if jobs.start_chesscom_sync(export.pk, full=full):
        messages.success(request, "Synchronisation Chess.com lancée.")
    else:
        messages.info(request, "Une synchronisation est déjà en cours.")
    return redirect(export)


@require_POST
def export_settings(request, pk):
    export = get_object_or_404(Export, pk=pk)
    export.name = request.POST.get("name", export.name).strip() or export.name
    if export.is_chesscom:
        export.time_classes = ",".join(request.POST.getlist("time_classes"))
        export.auto_analyze = bool(request.POST.get("auto_analyze"))
    export.save()
    messages.success(request, "Réglages enregistrés.")
    return redirect(export)


@require_POST
def export_delete(request, pk):
    export = get_object_or_404(Export, pk=pk)
    jobs.request_cancel("export", pk)
    name = export.name
    export.delete()
    messages.success(request, f"« {name} » supprimé.")
    return redirect("analyzer:export_list")


def export_status(request, pk):
    export = get_object_or_404(Export, pk=pk)
    data = _progress(export)["progress"]
    data.update({
        "status": export.status, "message": export.job_message, "sync_message": export.sync_message,
        **_export_flags(export),
    })
    return JsonResponse(data)


# ---------------------------------------------------------------------------
# Une partie
# ---------------------------------------------------------------------------
def _game_payload(game):
    """Données envoyées au JavaScript de l'échiquier."""
    if game.is_analyzed:
        plies = game.analysis
        moves = game.stats["moves"]
    else:
        plies = engine.positions_without_engine(game.pgn)
        moves = [{"i": i, "san": p["san"], "uci": p["uci"], "mine": None, "cls": None, "clock": p.get("clock")}
                 for i, p in enumerate(plies[:-1])]
    out_moves = []
    for m in moves:
        item = {
            "i": m["i"], "label": move_label(m["i"], m["san"]), "san": display(m["san"]), "uci": m["uci"],
            "cls": m.get("cls"), "mine": m.get("mine"), "clock": m.get("clock"),
        }
        if m.get("cls"):
            item.update({
                "loss": m["loss"], "best": display(m.get("best")), "best_uci": m.get("best_uci"),
                "wp_after": m["wp_after"], "tags": m.get("tags", []),
                "explain": explain.describe(m),
                "cls_label": explain.CLASS_LABELS[m["cls"]],
                "symbol": explain.CLASS_SYMBOLS.get(m["cls"], ""),
                "phase": explain.PHASE_LABELS.get(m.get("phase"), ""),
            })
        out_moves.append(item)
    return {
        "fens": [p["fen"] for p in plies],
        "moves": out_moves,
        "wp": game.stats["wp_series"] if game.is_analyzed else None,
        "orientation": game.player_color,
        "player_color": game.player_color,
        "players": {
            "w": {"name": game.white, "elo": game.white_elo},
            "b": {"name": game.black, "elo": game.black_elo},
        },
        "initial_clock": _initial_clock(game.time_control),
        "key": sorted(game.stats["key_moments"]) if game.is_analyzed else [],
        "pieces": {k: v for k, v in chess.svg.PIECES.items()},
    }


def _initial_clock(time_control):
    """'600+5' -> 600 (secondes) ; parties par correspondance ('1/86400') ou inconnues -> None."""
    base = (time_control or "").split("+")[0]
    return int(base) if base.isdigit() else None


def game_detail(request, pk):
    game = get_object_or_404(Game.objects.select_related("export"), pk=pk)
    if game.status in (Game.STATUS_QUEUED, Game.STATUS_RUNNING) and not (
            jobs.is_running("game", game.pk) or jobs.export_running(game.export)):
        game.status = Game.STATUS_DONE if game.stats else Game.STATUS_PENDING
        game.save(update_fields=["status"])
    if game.analysis and (not game.stats or game.stats.get("version") != metrics.METRICS_VERSION):
        jobs.refresh_stats_if_outdated([game])
    payload = _game_payload(game)
    key_moments = []
    if game.is_analyzed:
        by_i = {m["i"]: m for m in payload["moves"]}
        key_moments = [by_i[i] for i in sorted(game.stats["key_moments"]) if i in by_i]
    siblings = list(game.export.games.order_by("played_at", "id").values_list("id", flat=True))
    idx = siblings.index(game.id)
    ply = request.GET.get("coup")
    return render(request, "analyzer/game_detail.html", {
        "game": game, "export": game.export, "payload": payload, "key_moments": key_moments,
        "prev_id": siblings[idx - 1] if idx > 0 else None,
        "next_id": siblings[idx + 1] if idx + 1 < len(siblings) else None,
        "start_ply": int(ply) + 1 if ply and ply.isdigit() else None,
        "running": game.status in (Game.STATUS_QUEUED, Game.STATUS_RUNNING),
        "engine_ok": engine.engine_available(),
        "default_time": settings.ANALYSIS_TIME_SINGLE,
        "tc_labels": TIME_CLASS_LABELS,
        "phase_labels": explain.PHASE_LABELS,
    })


@require_POST
def game_analyze(request, pk):
    game = get_object_or_404(Game, pk=pk)
    t = float(request.POST.get("analysis_time") or settings.ANALYSIS_TIME_SINGLE)
    if not engine.engine_available():
        messages.error(request, "Stockfish est introuvable : voir le README pour l'installer.")
    elif jobs.start_game_analysis(game.pk, t):
        messages.success(request, "Analyse de la partie lancée…")
    return redirect(game)


def game_status(request, pk):
    game = get_object_or_404(Game.objects.only("status", "error"), pk=pk)
    return JsonResponse({"status": game.status, "error": game.error,
                         "running": jobs.is_running("game", pk) or game.status in ("queued", "running")})
