"""Entraînement : classement aux exercices, choix du prochain exercice, statistiques par thème,
recommandations tirées du diagnostic, création d'exercices depuis tes parties."""
import collections
import csv
import datetime as dt
import json
import logging
import random
from pathlib import Path

import chess
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from ..models import Export, Game, Puzzle, PuzzleAttempt, PuzzleScan, PuzzleSprint
from . import puzzle_themes, puzzles
from .notation import display

log = logging.getLogger("analyzer")

DEFAULT_RATING = 1200
BANK_FILE = Path(__file__).resolve().parent.parent / "data" / "puzzles.json"


# ---------------------------------------------------------------------------
# Classement (Elo simplifié)
# ---------------------------------------------------------------------------
def initial_rating():
    """Point de départ : ton dernier Elo connu (borné), sinon 1200."""
    elo = (Game.objects.filter(player_elo__isnull=False).order_by("-played_at", "-id")
           .values_list("player_elo", flat=True).first())
    return max(600, min(2200, elo)) if elo else DEFAULT_RATING


def current_rating():
    last = PuzzleAttempt.objects.order_by("-created_at", "-id").values_list("rating_after", flat=True).first()
    return last if last is not None else initial_rating()


def _expected(player, opponent):
    return 1 / (1 + 10 ** ((opponent - player) / 400))


@transaction.atomic
def record_attempt(puzzle, solved, mistakes=0, used_hint=False, seconds=None, theme=""):
    before = current_rating()
    n = PuzzleAttempt.objects.count()
    k = 40 if n < 20 else 24 if n < 100 else 16
    exp = _expected(before, puzzle.rating)
    score = 1.0 if solved else 0.0
    after = int(round(before + k * (score - exp)))
    attempt = PuzzleAttempt.objects.create(
        puzzle=puzzle, theme=theme[:40], solved=solved, mistakes=mistakes, used_hint=used_hint,
        seconds=seconds, puzzle_rating=puzzle.rating, rating_before=before, rating_after=after)
    # La difficulté de l'exercice s'ajuste doucement aux résultats
    Puzzle.objects.filter(pk=puzzle.pk).update(rating=max(400, min(3000, int(round(puzzle.rating + 8 * (exp - score))))))
    return attempt


def streak():
    """Exercices réussis d'affilée (les plus récents)."""
    n = 0
    for solved in PuzzleAttempt.objects.order_by("-created_at", "-id").values_list("solved", flat=True)[:500]:
        if not solved:
            break
        n += 1
    return n


def failed_puzzle_ids():
    """Exercices dont la dernière tentative est un échec (à réviser)."""
    last = {}
    for pid, solved in PuzzleAttempt.objects.order_by("created_at", "id").values_list("puzzle_id", "solved"):
        last[pid] = solved
    return [pid for pid, ok in last.items() if not ok]


# ---------------------------------------------------------------------------
# Choix du prochain exercice
# ---------------------------------------------------------------------------
def queryset_for(theme):
    qs = Puzzle.objects.all()
    if theme == "mine":
        return qs.filter(source=Puzzle.SOURCE_GAME)
    if theme == "review":
        return qs.filter(id__in=failed_puzzle_ids())
    if theme and theme != "mix":
        return qs.filter(themes__contains=f" {theme} ")
    return qs


def next_puzzle(theme="mix", exclude=()):
    qs = queryset_for(theme).exclude(id__in=list(exclude))
    if theme == "review":
        ids = list(qs.values_list("id", flat=True))
        return Puzzle.objects.get(pk=random.choice(ids)) if ids else None
    target = current_rating()
    unseen = qs.filter(attempts__isnull=True)
    for window in (80, 160, 260, 420, 700):
        ids = list(unseen.filter(rating__gte=target - window, rating__lte=target + window)
                   .values_list("id", flat=True)[:400])
        if ids:
            return Puzzle.objects.get(pk=random.choice(ids))
    ids = list(unseen.values_list("id", flat=True)[:400])
    if ids:
        return Puzzle.objects.get(pk=random.choice(ids))
    # Tout a déjà été vu : on repasse d'abord par les échecs, puis au hasard
    failed = list(qs.filter(id__in=failed_puzzle_ids()).values_list("id", flat=True))
    pool = failed or list(qs.values_list("id", flat=True)[:400])
    return Puzzle.objects.get(pk=random.choice(pool)) if pool else None


# ---------------------------------------------------------------------------
# Exercice du jour et course contre la montre
# ---------------------------------------------------------------------------
SPRINT_DURATIONS = (180, 300)
SPRINT_MAX_MISTAKES = 3


def daily_puzzle(day=None):
    """Le même exercice pour toute la journée (hors exercices tirés de tes parties). -> (exercice, déjà fait ?)"""
    day = day or timezone.localdate()
    qs = Puzzle.objects.exclude(source=Puzzle.SOURCE_GAME).order_by("id")
    ids = list(qs.filter(rating__gte=750, rating__lte=2000).values_list("id", flat=True)) or list(qs.values_list("id", flat=True))
    if not ids:
        return None, False
    puzzle = Puzzle.objects.get(pk=random.Random(day.toordinal()).choice(ids))
    start = timezone.make_aware(dt.datetime.combine(day, dt.time.min))
    done = PuzzleAttempt.objects.filter(puzzle=puzzle, created_at__gte=start,
                                        created_at__lt=start + dt.timedelta(days=1)).exists()
    return puzzle, done


def sprint_start_rating():
    return max(450, current_rating() - 350)


def sprint_batch(start, offset=0, n=12, exclude=()):
    """Exercices de difficulté croissante (≈ +30 points par exercice) pour la course."""
    used = set(exclude)
    pool = list(Puzzle.objects.exclude(source=Puzzle.SOURCE_GAME).values_list("id", "rating"))
    out = []
    for i in range(offset, offset + n):
        target = start + 30 * i
        near = sorted((abs(r - target), pid) for pid, r in pool if pid not in used)
        if not near:
            break
        close = [pid for d, pid in near[:8] if d <= 60]
        pid = random.choice(close) if close else near[0][1]
        used.add(pid)
        out.append(pid)
    found = Puzzle.objects.in_bulk(out)
    return sorted((found[i] for i in out), key=lambda p: p.rating)


def record_sprint(duration, score, mistakes, best_rating=None):
    previous = sprint_best(duration)
    run = PuzzleSprint.objects.create(duration=duration, score=max(0, score), mistakes=max(0, mistakes),
                                      best_rating=best_rating)
    return run, previous is None or run.score > previous


def sprint_best(duration):
    return (PuzzleSprint.objects.filter(duration=duration).order_by("-score")
            .values_list("score", flat=True).first())


def sprint_stats():
    return {
        "best": {d: sprint_best(d) for d in SPRINT_DURATIONS},
        "recent": list(PuzzleSprint.objects.all()[:10]),
        "runs": PuzzleSprint.objects.count(),
    }


# ---------------------------------------------------------------------------
# Statistiques
# ---------------------------------------------------------------------------
def _keys(themes, source):
    keys = set(themes.split())
    if source == Puzzle.SOURCE_GAME:
        keys.add("mine")
    return keys


def theme_counts():
    counts = collections.Counter()
    for themes, source in Puzzle.objects.values_list("themes", "source"):
        counts.update(_keys(themes, source))
    return counts


def theme_stats():
    """Par thème : tentatives, réussites, temps moyen, performance (formule de performance Elo)."""
    acc = collections.defaultdict(lambda: {"n": 0, "solved": 0, "seconds": [], "ratings": [], "last": None})
    rows = (PuzzleAttempt.objects.order_by("created_at", "id")
            .values_list("puzzle__themes", "puzzle__source", "solved", "seconds", "puzzle_rating", "created_at"))
    for themes, source, solved, seconds, prating, created in rows:
        for key in _keys(themes, source):
            d = acc[key]
            d["n"] += 1
            d["solved"] += int(solved)
            if seconds:
                d["seconds"].append(seconds)
            if prating:
                d["ratings"].append(prating)
            d["last"] = created
    out = {}
    for key, d in acc.items():
        rate = 100 * d["solved"] / d["n"]
        avg_r = sum(d["ratings"]) / len(d["ratings"]) if d["ratings"] else None
        perf = int(round(avg_r + 400 * (2 * d["solved"] - d["n"]) / d["n"])) if avg_r else None
        out[key] = {
            "n": d["n"], "solved": d["solved"], "rate": round(rate),
            "seconds": round(sum(d["seconds"]) / len(d["seconds"])) if d["seconds"] else None,
            "perf": perf, "last": d["last"],
        }
    return out


def overview():
    attempts = PuzzleAttempt.objects.count()
    solved = PuzzleAttempt.objects.filter(solved=True).count()
    today = timezone.localdate()
    since = timezone.now() - dt.timedelta(days=30)
    per_day = collections.Counter(
        timezone.localtime(c).date() for c in PuzzleAttempt.objects.filter(created_at__gte=since).values_list("created_at", flat=True))
    days = [{"date": today - dt.timedelta(days=i), "n": per_day.get(today - dt.timedelta(days=i), 0)} for i in range(29, -1, -1)]
    active_streak = 0
    for d in reversed(days):
        if d["n"]:
            active_streak += 1
        elif d["date"] != today:
            break
    history = list(PuzzleAttempt.objects.order_by("-created_at", "-id").values_list("rating_after", flat=True)[:200])[::-1]
    return {
        "rating": current_rating(), "attempts": attempts, "solved": solved,
        "rate": round(100 * solved / attempts) if attempts else None,
        "streak": streak(), "days": days, "active_days_streak": active_streak,
        "history": ([initial_rating()] if attempts <= 200 else []) + history,
        "today": per_day.get(today, 0), "to_review": len(failed_puzzle_ids()),
    }


# ---------------------------------------------------------------------------
# Recommandations à partir du diagnostic
# ---------------------------------------------------------------------------
def latest_export():
    return Export.objects.exclude(summary=None).order_by("-created_at").first()


def recommended_themes(recs, counts=None, limit=6):
    """Thèmes d'exercices liés aux constats du diagnostic, dans l'ordre des priorités."""
    counts = theme_counts() if counts is None else counts
    out, seen = [], set()
    for f in (recs or {}).get("findings", []):
        for key in puzzle_themes.FINDING_THEMES.get(f["id"], []):
            if key in seen or not (counts.get(key) or key in ("mix", "mine")):
                continue
            seen.add(key)
            item = puzzle_themes.info(key)
            item.update({"because": f["title"], "level": f["level"], "count": counts.get(key, 0)})
            out.append(item)
    return out[:limit]


# ---------------------------------------------------------------------------
# Banque d'exercices fournie et import Lichess
# ---------------------------------------------------------------------------
def _theme_field(keys):
    return " " + " ".join(sorted(set(keys))) + " " if keys else ""


def load_bank(path=BANK_FILE):
    """Charge la banque intégrée (idempotent : les exercices déjà présents sont ignorés)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 0
    before = Puzzle.objects.filter(source=Puzzle.SOURCE_BANK).count()
    Puzzle.objects.bulk_create([
        Puzzle(uid=p["uid"], source=Puzzle.SOURCE_BANK, fen=p["fen"], moves=p["moves"], rating=p["rating"],
               themes=_theme_field(p["themes"]))
        for p in data.get("puzzles", [])
    ], ignore_conflicts=True, batch_size=500)
    return Puzzle.objects.filter(source=Puzzle.SOURCE_BANK).count() - before


_bank_checked = False


def ensure_bank():
    """Charge la banque intégrée (et ses nouveautés après une mise à jour), une fois par processus."""
    global _bank_checked
    if not _bank_checked or not Puzzle.objects.filter(source=Puzzle.SOURCE_BANK).exists():
        load_bank()
        _bank_checked = True


def import_lichess_csv(stream, limit=None, themes=None, min_rating=0, max_rating=4000, min_popularity=-100):
    """Importe la base libre de Lichess (CSV : PuzzleId,FEN,Moves,Rating,…,Themes,…)."""
    wanted = set(themes or [])
    batch, added, seen = [], 0, 0
    for row in csv.reader(stream):
        if not row or row[0] == "PuzzleId":
            continue
        try:
            pid, fen, moves, rating, popularity, tags = row[0], row[1], row[2], int(row[3]), int(row[5]), row[7].split()
        except (IndexError, ValueError):
            continue
        if not (min_rating <= rating <= max_rating) or popularity < min_popularity:
            continue
        if wanted and not wanted & set(tags):
            continue
        seen += 1
        batch.append(Puzzle(uid=f"lichess-{pid}", source=Puzzle.SOURCE_IMPORT, fen=fen, moves=moves,
                            rating=rating, themes=_theme_field(tags)))
        if len(batch) >= 1000:
            Puzzle.objects.bulk_create(batch, ignore_conflicts=True)
            added += len(batch)
            batch = []
        if limit and seen >= limit:
            break
    if batch:
        Puzzle.objects.bulk_create(batch, ignore_conflicts=True)
        added += len(batch)
    return added


# ---------------------------------------------------------------------------
# Exercices tirés de tes parties
# ---------------------------------------------------------------------------
def candidate_games(export, limit_games=150):
    """Parties analysées pas encore parcourues (ou réanalysées depuis), les plus récentes d'abord."""
    todo = (export.games.filter(status=Game.STATUS_DONE).exclude(analysis=None)
            .filter(Q(puzzle_scan__isnull=True) | Q(puzzle_scan__scanned_at__lt=F("analyzed_at")))
            .order_by("-played_at", "-id"))
    return list(todo[:limit_games])


def game_candidates(game):
    """Tes erreurs dans une partie : (indice du coup, données du coup)."""
    for m in (game.stats or {}).get("moves", []):
        if m["i"] > 0 and m["mine"] and m["cls"] in ("mistake", "blunder"):
            yield m


def puzzle_from_mistake(eng, game, m, seconds=0.25):
    """Construit (sans l'enregistrer) l'exercice correspondant à une erreur de la partie."""
    i = m["i"]
    fen, setup = game.analysis[i - 1]["fen"], game.analysis[i - 1]["uci"]
    p = puzzles.make_puzzle(eng, fen, setup, seconds)
    alternatives = []
    if p:
        keys = set(p["themes"]) | {"mine"}
        if "missed_punish" in m.get("tags", []):
            keys.add("punish")
    else:
        board = chess.Board(fen)
        board.push(chess.Move.from_uci(setup))
        res = puzzles.build_safe_move(eng, board, m["uci"], seconds)
        if not res:
            return None
        best, alternatives = res
        moves = [setup, best]
        keys = puzzles.detect_themes(fen, moves) | {"mine", "avoidBlunder"}
        keys -= {"hangingPiece"} if not board.is_capture(chess.Move.from_uci(best)) else set()
        if "allowed_mate" in m.get("tags", []):
            keys.add("defensiveMove")
        rating = puzzles.estimate_rating(eng, board, best, 1, keys)
        p = {"fen": fen, "moves": " ".join(moves), "rating": rating, "themes": sorted(keys)}
    when = timezone.localtime(game.played_at).strftime("%d/%m/%Y") if game.played_at else game.date
    p.update({
        "uid": f"g{game.pk}-{i}", "alternatives": " ".join(alternatives), "ply": i,
        "note": f"Partie du {when} contre {game.opponent} : tu as joué {display(m['san'])} au coup {m['n']}.",
    })
    p["themes"] = sorted(p["themes"])
    return p


def save_game_puzzles(game, items):
    created = 0
    for p in items:
        _, made = Puzzle.objects.update_or_create(uid=p["uid"], defaults={
            "source": Puzzle.SOURCE_GAME, "fen": p["fen"], "moves": p["moves"], "alternatives": p["alternatives"],
            "rating": p["rating"], "themes": _theme_field(p["themes"]), "game": game, "ply": p["ply"], "note": p["note"]})
        created += int(made)
    PuzzleScan.objects.update_or_create(game=game, defaults={"created": len(items)})
    return created
