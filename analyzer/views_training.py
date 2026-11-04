"""Pages d'entraînement : exercices à thème et parties de référence."""
import json

import chess
import chess.svg
from django.contrib import messages
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Export, Game, Puzzle, PuzzleAttempt, PuzzleSprint, ReferenceStudy
from .services import engine, jobs, puzzle_themes, puzzles, recommendations, references, training


def _pieces():
    return {k: v for k, v in chess.svg.PIECES.items()}


def _recs_for(export):
    if export and export.summary and export.summary.get("n_games"):
        return recommendations.build(export.summary)
    return None


# ---------------------------------------------------------------------------
# Exercices
# ---------------------------------------------------------------------------
def training_home(request):
    training.ensure_bank()
    counts = training.theme_counts()
    stats = training.theme_stats()
    export = training.latest_export()
    recs = _recs_for(export)
    categories = []
    for cat, cat_label in puzzle_themes.CATEGORIES:
        items = []
        for key, (label, desc, icon, c) in puzzle_themes.THEMES.items():
            if c != cat or (not counts.get(key) and key != "mine"):
                continue
            items.append({"key": key, "label": label, "description": desc, "icon": icon,
                          "count": counts.get(key, 0), "stats": stats.get(key)})
        if items:
            categories.append({"key": cat, "label": cat_label, "items": items})
    exports = (Export.objects.annotate(
        n_done=Count("games", filter=Q(games__status=Game.STATUS_DONE), distinct=True),
        n_puzzles=Count("games__puzzles", distinct=True),
        n_scanned=Count("games__puzzle_scan", distinct=True),
    ).order_by("-created_at"))
    for e in exports:
        e.puzzle_job = jobs.puzzle_job_status(e.pk)
    return render(request, "analyzer/training_home.html", {
        "ov": training.overview(), "categories": categories, "counts": counts,
        "recommended": training.recommended_themes(recs, counts), "rec_export": export,
        "exports": exports, "engine_ok": engine.engine_available(),
        "total": Puzzle.objects.count(),
        "modes": [puzzle_themes.info("mix"), puzzle_themes.info("review")],
        "references": references.recommend(export, recs, limit=3),
        "daily": _daily(),
        "sprint_best": training.sprint_stats()["best"],
        "pieces": _pieces(),
    })


def _daily():
    puzzle, done = training.daily_puzzle()
    if not puzzle:
        return None
    board = chess.Board(puzzle.fen)
    setup = puzzle.move_list[0]
    board.push_uci(setup)
    return {"puzzle": puzzle, "done": done, "fen": board.fen(), "last": setup,
            "color": "w" if board.turn == chess.WHITE else "b",
            "themes": [puzzle_themes.info(t) for t in puzzle.theme_list
                       if puzzle_themes.is_known(t) and puzzle_themes.info(t)["category"] in ("mat", "tactique", "finale")][:2]}


def _theme_or_404(theme):
    if not puzzle_themes.is_known(theme):
        raise Http404("Thème inconnu")
    return puzzle_themes.info(theme)


def training_play(request, theme):
    info = _theme_or_404(theme)
    training.ensure_bank()
    puzzle = None
    pid = request.GET.get("id")
    if pid and pid.isdigit():
        puzzle = Puzzle.objects.filter(pk=int(pid)).first()
    if puzzle is None:
        puzzle = training.next_puzzle(theme)
    return render(request, "analyzer/training_play.html", {
        "theme": info, "puzzle": puzzle,
        "payload": puzzles.payload(puzzle) if puzzle else None,
        "pieces": _pieces(), "rating": training.current_rating(), "streak": training.streak(),
        "available": training.queryset_for(theme).count(),
        "themes_menu": [(k, v[0]) for k, v in puzzle_themes.THEMES.items() if training.queryset_for(k).exists()],
    })


def training_next(request):
    theme = request.GET.get("theme") or "mix"
    _theme_or_404(theme)
    exclude = [int(x) for x in request.GET.get("exclude", "").split(",") if x.isdigit()][-200:]
    puzzle = training.next_puzzle(theme, exclude)
    if puzzle is None:
        return JsonResponse({"empty": True})
    return JsonResponse({"puzzle": puzzles.payload(puzzle)})


@require_POST
def training_attempt(request, pk):
    puzzle = get_object_or_404(Puzzle, pk=pk)
    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"error": "JSON invalide"}, status=400)
    seconds = data.get("seconds")
    attempt = training.record_attempt(
        puzzle, solved=bool(data.get("solved")), mistakes=int(data.get("mistakes") or 0),
        used_hint=bool(data.get("used_hint")), seconds=float(seconds) if seconds is not None else None,
        theme=str(data.get("theme") or ""))
    return JsonResponse({
        "rating_before": attempt.rating_before, "rating_after": attempt.rating_after,
        "delta": attempt.rating_after - attempt.rating_before, "streak": training.streak(),
        "puzzle_rating": attempt.puzzle_rating,
    })


def training_progress(request):
    stats = training.theme_stats()
    rows = []
    for key, st in stats.items():
        if not puzzle_themes.is_known(key) or puzzle_themes.info(key)["category"] == "longueur":
            continue
        rows.append({**puzzle_themes.info(key), **st})
    rows.sort(key=lambda r: -r["n"])
    ranked = [r for r in rows if r["n"] >= 5]
    strong = sorted(ranked, key=lambda r: -r["rate"])[:3]
    weak = sorted(ranked, key=lambda r: r["rate"])[:3]
    recent = list(PuzzleAttempt.objects.select_related("puzzle").order_by("-created_at", "-id")[:30])
    for a in recent:
        a.theme_labels = [puzzle_themes.label(t) for t in a.puzzle.theme_list
                          if puzzle_themes.is_known(t) and puzzle_themes.info(t)["category"] not in ("longueur", "phase")][:3]
    return render(request, "analyzer/training_progress.html", {
        "ov": training.overview(), "rows": rows, "strong": strong,
        "weak": [w for w in weak if w not in strong or w["rate"] < 60], "recent": recent,
    })


def training_sprint(request):
    training.ensure_bank()
    return render(request, "analyzer/training_sprint.html", {
        "stats": training.sprint_stats(), "durations": training.SPRINT_DURATIONS,
        "max_mistakes": training.SPRINT_MAX_MISTAKES, "pieces": _pieces(),
        "start": training.sprint_start_rating(), "rating": training.current_rating(),
    })


def training_sprint_batch(request):
    def as_int(name, default):
        v = request.GET.get(name, "")
        return int(v) if v.lstrip("-").isdigit() else default
    start = as_int("start", training.sprint_start_rating())
    exclude = [int(x) for x in request.GET.get("exclude", "").split(",") if x.isdigit()]
    items = training.sprint_batch(start, offset=max(0, as_int("offset", 0)), n=min(20, max(1, as_int("n", 12))),
                                  exclude=exclude)
    return JsonResponse({"start": start, "puzzles": [puzzles.payload(p) for p in items]})


@require_POST
def training_sprint_result(request):
    try:
        data = json.loads(request.body or "{}")
        duration = int(data.get("duration"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "données invalides"}, status=400)
    if duration not in training.SPRINT_DURATIONS:
        return JsonResponse({"error": "durée invalide"}, status=400)
    run, record = training.record_sprint(duration, int(data.get("score") or 0), int(data.get("mistakes") or 0),
                                         data.get("best_rating"))
    return JsonResponse({"score": run.score, "record": record, "best": training.sprint_best(duration)})


@require_POST
def training_generate(request, pk):
    export = get_object_or_404(Export, pk=pk)
    if not engine.engine_available():
        messages.error(request, "Stockfish est introuvable : impossible de vérifier les exercices.")
    elif jobs.start_puzzle_generation(export.pk):
        messages.success(request, f"Création d'exercices à partir des parties de « {export.name} » lancée.")
    else:
        messages.info(request, "La création d'exercices est déjà en cours pour cet export.")
    return redirect(request.POST.get("next") or "analyzer:training_home")


def training_generate_status(request, pk):
    get_object_or_404(Export, pk=pk)
    data = jobs.puzzle_job_status(pk)
    data["n_puzzles"] = Puzzle.objects.filter(game__export_id=pk).count()
    return JsonResponse(data)


# ---------------------------------------------------------------------------
# Parties de référence
# ---------------------------------------------------------------------------
def reference_list(request):
    export = None
    eid = request.GET.get("export")
    if eid and eid.isdigit():
        export = Export.objects.filter(pk=int(eid)).first()
    export = export or training.latest_export()
    recs = _recs_for(export)
    level = request.GET.get("niveau") or ""
    theme = request.GET.get("theme") or ""
    games = references.catalogue()
    studies = {s.slug: s for s in ReferenceStudy.objects.all()}
    items = []
    for g in games:
        if level and g["level"] != level:
            continue
        if theme and theme not in g["themes"]:
            continue
        items.append({**g, "study": studies.get(g["slug"])})
    return render(request, "analyzer/reference_list.html", {
        "items": items, "recommended": references.recommend(export, recs, limit=4), "export": export,
        "levels": references.LEVELS, "themes": references.THEMES, "level": level, "theme": theme,
        "player_level": references.player_level(export),
        "exports": Export.objects.order_by("-created_at"),
    })


def reference_detail(request, slug):
    game = references.get(slug)
    if not game:
        raise Http404("Partie de référence inconnue")
    study, _ = ReferenceStudy.objects.get_or_create(slug=slug)
    study.viewed_at = timezone.now()
    study.save(update_fields=["viewed_at", "updated_at"])
    others = [g for g in references.catalogue() if g["slug"] != slug and set(g["themes"]) & set(game["themes"])][:3]
    counts = training.theme_counts()
    related, seen = [], set()
    for t in game["themes"]:
        key = references.PUZZLE_THEMES.get(t)
        if key and key not in seen and counts.get(key):
            seen.add(key)
            related.append(puzzle_themes.info(key))
    return render(request, "analyzer/reference_detail.html", {
        "ref": game, "study": study, "payload": references.payload(game), "pieces": _pieces(), "others": others,
        "related_themes": related,
    })


@require_POST
def reference_progress(request, slug):
    if not references.get(slug):
        raise Http404
    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"error": "JSON invalide"}, status=400)
    study, _ = ReferenceStudy.objects.get_or_create(slug=slug)
    if data.get("completed"):
        study.completed_at = timezone.now()
    if "guess_total" in data:
        study.guess_total = int(data["guess_total"])
        study.guess_correct = int(data.get("guess_correct") or 0)
    study.save()
    return JsonResponse({"ok": True, "guess_score": study.guess_score,
                         "completed": bool(study.completed_at)})
