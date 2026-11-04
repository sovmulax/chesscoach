"""Agrégation des statistiques d'un export (toutes parties + parties analysées)."""
import collections
import statistics

from django.utils import timezone

from . import metrics
from .pgn_import import TERMINATION_LABELS

SUMMARY_VERSION = 4


def _score(games):
    if not games:
        return None
    return round(100 * sum(g.score for g in games) / len(games), 1)


def _wdl(games):
    c = collections.Counter(g.player_result for g in games)
    return {"win": c.get("win", 0), "draw": c.get("draw", 0), "loss": c.get("loss", 0),
            "n": len(games), "score": _score(games)}


def _pct(a, b):
    return round(100 * a / b, 1) if b else None


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def summary_cache_key(export, games):
    analyzed = [g for g in games if g.is_analyzed]
    last = max((g.analyzed_at for g in analyzed if g.analyzed_at), default=None)
    return f"v{SUMMARY_VERSION}-m{metrics.METRICS_VERSION}-{len(games)}-{len(analyzed)}-{last.timestamp() if last else 0}"


def compute_summary(games):
    games = sorted(games, key=lambda g: (g.played_at or timezone.now(), g.id))
    out = {"version": SUMMARY_VERSION, "n_games": len(games)}
    if not games:
        return out
    out["basic"] = _basic(games)
    out["openings"] = _openings(games)
    out["habits"] = _habits(games)
    out["repeated_losses"] = _repeated_losses(games)
    analyzed = [g for g in games if g.is_analyzed]
    out["n_analyzed"] = len(analyzed)
    if analyzed:
        out["engine"] = _engine(analyzed)
    return out


# ---------------------------------------------------------------------------
def _basic(games):
    res = _wdl(games)
    by_color = {c: _wdl([g for g in games if g.player_color == c]) for c in ("w", "b")}
    by_tc = {}
    for tc in sorted({g.time_class or "?" for g in games}):
        sub = [g for g in games if (g.time_class or "?") == tc]
        elos = [(g.played_at.isoformat() if g.played_at else g.date, g.player_elo) for g in sub if g.player_elo]
        info = _wdl(sub)
        if elos:
            vals = [e for _, e in elos]
            peak_i = max(range(len(vals)), key=lambda i: vals[i])
            low_i = min(range(len(vals)), key=lambda i: vals[i])
            info.update({
                "elo_start": vals[0], "elo_end": vals[-1], "elo_peak": vals[peak_i],
                "elo_peak_date": elos[peak_i][0][:10], "elo_low": vals[low_i],
                "elo_low_date": elos[low_i][0][:10], "elo_series": elos,
            })
        by_tc[tc] = info
    main_tc = max(by_tc, key=lambda k: by_tc[k]["n"])
    diffs = [g.opponent_elo - g.player_elo for g in games if g.opponent_elo and g.player_elo]
    term = collections.Counter((g.player_result, g.termination_kind) for g in games)
    terminations = [
        {"result": r, "kind": k, "label": TERMINATION_LABELS.get(k, k), "n": n}
        for (r, k), n in sorted(term.items(), key=lambda kv: -kv[1])
    ]
    by_month = collections.OrderedDict()
    for g in games:
        key = g.played_at.strftime("%Y-%m") if g.played_at else (g.date[:7].replace(".", "-") or "?")
        by_month.setdefault(key, []).append(g)
    months = []
    for k, sub in by_month.items():
        elos = [g.player_elo for g in sub if g.player_elo and (g.time_class or "?") == main_tc]
        acc = [g.stats["accuracy"] for g in sub if g.is_analyzed and g.stats.get("accuracy") is not None]
        months.append({"month": k, "n": len(sub), "score": _score(sub),
                       "elo_start": elos[0] if elos else None, "elo_end": elos[-1] if elos else None,
                       "accuracy": round(statistics.mean(acc), 1) if acc else None})
    return {
        "results": res,
        "by_color": by_color,
        "by_time_class": by_tc,
        "main_time_class": main_tc,
        "avg_opp_elo_diff": round(statistics.mean(diffs), 1) if diffs else None,
        "avg_moves": round(statistics.mean(g.num_plies for g in games) / 2, 1),
        "terminations": terminations,
        "lost_on_time": term.get(("loss", "timeout"), 0),
        "won_on_time": term.get(("win", "timeout"), 0),
        "months": months,
        "first_date": games[0].played_at.date().isoformat() if games[0].played_at else games[0].date,
        "last_date": games[-1].played_at.date().isoformat() if games[-1].played_at else games[-1].date,
    }


def _openings(games):
    groups = collections.defaultdict(list)
    for g in games:
        groups[(g.player_color, g.opening_name)].append(g)
    rows = []
    for (color, name), sub in groups.items():
        ev = [g.stats.get("eval10") for g in sub if g.is_analyzed]
        med = _median(ev)
        r = _wdl(sub)
        r.update({
            "color": color, "name": name,
            "eval10": round(med / 100, 2) if med is not None else None,
            "weak": r["n"] >= 4 and r["score"] is not None and r["score"] <= 40,
            "strong": r["n"] >= 4 and r["score"] is not None and r["score"] >= 60,
            "game_ids": [g.id for g in sub][:50],
        })
        rows.append(r)
    rows.sort(key=lambda r: -r["n"])
    return rows


def _habits(games):
    # Rang de la partie dans la journée (heure locale) et partie suivant un résultat.
    by_day = collections.OrderedDict()
    for g in games:
        if g.played_at:
            day = timezone.localtime(g.played_at).date()
            by_day.setdefault(day, []).append(g)
    rank = collections.defaultdict(list)
    after = collections.defaultdict(list)
    for day, sub in by_day.items():
        for i, g in enumerate(sub):
            rank[min(i + 1, 5)].append(g)
            if i > 0:
                after[sub[i - 1].player_result].append(g)
    hours = collections.defaultdict(list)
    buckets = [(0, 6, "Nuit (0 h – 6 h)"), (6, 12, "Matin (6 h – 12 h)"),
               (12, 18, "Après-midi (12 h – 18 h)"), (18, 24, "Soir (18 h – 24 h)")]
    for g in games:
        if g.played_at:
            h = timezone.localtime(g.played_at).hour
            for a, b, label in buckets:
                if a <= h < b:
                    hours[label].append(g)

    def acc(sub):
        vals = [g.stats["accuracy"] for g in sub if g.is_analyzed and g.stats.get("accuracy") is not None]
        return round(statistics.mean(vals), 1) if vals else None

    return {
        "game_rank": [{"rank": k, "label": f"{k}{'re' if k == 1 else 'e'} partie" + (" et +" if k == 5 else ""),
                       "n": len(v), "score": _score(v), "accuracy": acc(v)} for k, v in sorted(rank.items())],
        "after_result": {k: {"n": len(v), "score": _score(v), "accuracy": acc(v)} for k, v in after.items()},
        "hours": [{"label": label, "n": len(hours[label]), "score": _score(hours[label]),
                   "accuracy": acc(hours[label])} for _, _, label in buckets if hours[label]],
        "days_played": len(by_day),
        "games_per_day": round(len(games) / len(by_day), 1) if by_day else None,
    }


def _repeated_losses(games):
    """Séquences d'ouverture identiques perdues au moins deux fois (pièges récurrents)."""
    found = []
    seen_games = set()
    for length in (10, 9, 8, 7, 6):
        groups = collections.defaultdict(list)
        for g in games:
            moves = g.opening_moves.split()
            if len(moves) >= length:
                groups[(g.player_color, " ".join(moves[:length]))].append(g)
        for (color, seq), sub in groups.items():
            losses = [g for g in sub if g.player_result == "loss"]
            if len(losses) >= 2 and len(losses) / len(sub) >= 0.6:
                ids = frozenset(g.id for g in losses)
                if ids <= seen_games:
                    continue
                seen_games |= ids
                found.append({"color": color, "moves": seq.split(), "losses": len(losses), "n": len(sub),
                              "game_ids": sorted(ids), "length": length})
    return found[:8]


# ---------------------------------------------------------------------------
def _engine(games):
    G = len(games)
    all_mine = []
    all_opp = []
    for g in games:
        for m in g.stats["moves"]:
            m = dict(m)
            m["game_id"] = g.id
            (all_mine if m["mine"] else all_opp).append(m)

    def per_game(lst, cls):
        return round(sum(1 for m in lst if m["cls"] == cls) / G, 2)

    # Phases
    phases = {}
    for ph in metrics.PHASES:
        mm = [m for m in all_mine if m["phase"] == ph]
        oo = [m for m in all_opp if m["phase"] == ph]
        phases[ph] = {
            "moves": len(mm),
            "blunder_rate": _pct(sum(1 for m in mm if m["cls"] == "blunder"), len(mm)),
            "opp_blunder_rate": _pct(sum(1 for m in oo if m["cls"] == "blunder"), len(oo)),
            "error_rate": _pct(sum(1 for m in mm if m["cls"] in ("blunder", "mistake")), len(mm)),
            "opp_error_rate": _pct(sum(1 for m in oo if m["cls"] in ("blunder", "mistake")), len(oo)),
            "avg_loss": round(statistics.mean(m["loss"] for m in mm), 2) if mm else None,
        }

    # Première gaffe
    fb = collections.defaultdict(list)
    for g in games:
        fb[g.stats["first_blunder"]["by"] or "none"].append(g)
    first_blunder = {k: {"n": len(v), "score": _score(v)} for k, v in fb.items()}

    # Anatomie des gaffes
    blunders = [m for m in all_mine if m["cls"] == "blunder"]
    hanging_bl = [m for m in blunders if "hanging" in m["tags"]]
    lost = collections.Counter(m.get("captured") for m in hanging_bl if m.get("captured"))
    by_piece_moved = collections.Counter(m["piece"] for m in blunders)
    motif_counter = collections.Counter()
    motif_games = collections.defaultdict(list)
    for g in games:
        for mt in g.stats.get("motifs", []):
            motif_counter[mt] += 1
            motif_games[mt].append(g.id)
    motifs = [{"move": k.split("|")[0], "reply": k.split("|")[1], "n": n, "game_ids": motif_games[k][:10]}
              for k, n in motif_counter.most_common() if n >= 2][:8]
    first_moves = [g.stats.get("first_own_blunder_move") for g in games if g.stats.get("first_own_blunder_move")]

    # Occasions
    mm_games = [g for g in games if g.stats["missed_mates"]]
    winning = [g for g in games if g.stats["max_wp"] >= metrics.WINNING]
    losing = [g for g in games if g.stats["min_wp"] <= metrics.LOSING]
    losses = [g for g in games if g.player_result == "loss"]
    opp_bl = sum(g.stats["opp_blunders"] for g in games)
    unpunished = sum(g.stats["unpunished"] for g in games)

    # Ouverture : éval au coup 10
    ev = [g.stats["eval10"] for g in games if g.stats.get("eval10") is not None]

    # Roque
    castled = [g for g in games if g.stats.get("castled_move")]
    not_castled = [g for g in games if not g.stats.get("castled_move") and g.num_plies >= 30]

    # Pendule
    clock_games = [g for g in games if g.stats.get("has_clock")]
    tt_errors = sum(g.stats.get("time_trouble_errors", 0) for g in clock_games)
    errors_with_clock = sum(1 for g in clock_games for m in g.stats["moves"]
                            if m["mine"] and m["cls"] in ("mistake", "blunder"))

    def examples(pred, limit=6):
        sel = sorted([m for m in all_mine if pred(m)], key=lambda m: -m["loss"])[:limit]
        return [{"game_id": m["game_id"], "ply": m["i"], "san": m["san"], "best": m.get("best"),
                 "loss": m["loss"], "n": m["n"], "mine_color": "w" if m["i"] % 2 == 0 else "b"} for m in sel]

    acc = [g.stats["accuracy"] for g in games if g.stats.get("accuracy") is not None]
    oacc = [g.stats["opp_accuracy"] for g in games if g.stats.get("opp_accuracy") is not None]
    return {
        "n": G,
        "accuracy": round(statistics.mean(acc), 1) if acc else None,
        "opp_accuracy": round(statistics.mean(oacc), 1) if oacc else None,
        "per_game": {c: per_game(all_mine, c) for c in ("blunder", "mistake", "inaccuracy")},
        "opp_per_game": {c: per_game(all_opp, c) for c in ("blunder", "mistake", "inaccuracy")},
        "n_blunders": len(blunders),
        "n_opp_blunders": opp_bl,
        "phases": phases,
        "first_blunder": first_blunder,
        "first_blunder_move_median": _median(first_moves),
        "hanging_share": _pct(len(hanging_bl), len(blunders)),
        "hanging_n": len(hanging_bl),
        "hanging_other_share": _pct(sum(1 for m in hanging_bl if not m.get("captured_is_moved")), len(hanging_bl)),
        "material_lost": [{"piece": k, "n": v} for k, v in lost.most_common()],
        "blunder_piece_moved": [{"piece": k, "n": v} for k, v in by_piece_moved.most_common()],
        "allowed_mates": sum(g.stats["allowed_mates"] for g in games),
        "motifs": motifs,
        "lost_from_equal": sum(1 for g in losses if g.stats.get("lost_from_equal")),
        "n_losses": len(losses),
        "missed_mate_games": _wdl(mm_games),
        "missed_mates_1": sum(g.stats["missed_mates_1"] for g in games),
        "missed_mates_1_games": sum(1 for g in games if g.stats["missed_mates_1"]),
        "unpunished": unpunished,
        "unpunished_share": _pct(unpunished, opp_bl),
        "winning": _wdl(winning),
        "conversion_rate": _pct(sum(1 for g in winning if g.player_result == "win"), len(winning)),
        "losing": _wdl(losing),
        "saved": sum(1 for g in losing if g.player_result != "loss"),
        "stalemates_while_winning": [g.id for g in games if g.stats.get("stalemate_while_winning")],
        "eval10_median": round(_median(ev) / 100, 2) if ev else None,
        "eval10_ahead": _pct(sum(1 for e in ev if e >= 100), len(ev)),
        "eval10_behind": _pct(sum(1 for e in ev if e <= -100), len(ev)),
        "castled": _wdl(castled),
        "not_castled": _wdl(not_castled),
        "castle_move_median": _median([g.stats["castled_move"] for g in castled]),
        "clock_games": len(clock_games),
        "time_trouble_errors": tt_errors,
        "time_trouble_share": _pct(tt_errors, errors_with_clock),
        "examples": {
            "blunders": examples(lambda m: m["cls"] == "blunder"),
            "hanging": examples(lambda m: "hanging" in m["tags"] and m["cls"] == "blunder"),
            "missed_mates": examples(lambda m: "missed_mate" in m["tags"]),
            "allowed_mates": examples(lambda m: "allowed_mate" in m["tags"]),
            "unpunished": examples(lambda m: "missed_punish" in m["tags"]),
            "stalemates": examples(lambda m: "stalemate" in m["tags"]),
        },
    }
