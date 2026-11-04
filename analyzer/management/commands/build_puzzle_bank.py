"""Outil de développement : (re)génère la banque d'exercices intégrée.

Stockfish joue contre lui-même à des niveaux variés ; chaque gaffe qui donne une
position gagnante à l'adversaire devient un exercice candidat, vérifié ensuite à
pleine force (solution unique, thèmes détectés, difficulté estimée).

    python manage.py build_puzzle_bank --games 400 --append
"""
import datetime as dt
import hashlib
import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import chess
import chess.engine
from django.conf import settings
from django.core.management.base import BaseCommand

from analyzer.services import engine as engine_mod
from analyzer.services import metrics, puzzles, training


def _wp(info, color):
    sc = info["score"].pov(color)
    if sc.is_mate():
        return 100.0 if sc.mate() > 0 else 0.0
    return metrics.win_pct(sc.score())


class Command(BaseCommand):
    help = "(Développement) Génère la banque d'exercices intégrée par auto-parties de Stockfish."

    @staticmethod
    def is_trivial(p):
        """Simple pièce en prise en un coup : utile, mais déjà très représenté."""
        keys = set(p["themes"]) - {"opening", "middlegame", "endgame", "oneMove"}
        return "oneMove" in p["themes"] and keys <= {"hangingPiece"}

    def add_arguments(self, parser):
        parser.add_argument("--games", type=int, default=200)
        parser.add_argument("--out", default=str(training.BANK_FILE))
        parser.add_argument("--time", type=float, default=0.25, help="secondes par position pour la vérification")
        parser.add_argument("--workers", type=int, default=settings.ANALYSIS_WORKERS)
        parser.add_argument("--seed", type=int, default=2026)
        parser.add_argument("--append", action="store_true", help="ajouter aux exercices déjà présents dans le fichier")
        parser.add_argument("--per-game", type=int, default=5, help="candidats max par partie")
        parser.add_argument("--skill", default="0-8", help="niveaux Stockfish des auto-parties (ex. 4-12)")
        parser.add_argument("--noise", default="0.06,0.1,0.14", help="proportions de coups aléatoires")
        parser.add_argument("--rich-only", action="store_true",
                            help="ne garder que les exercices riches (pas les simples pièces en prise en un coup)")
        parser.add_argument("--rerate", action="store_true", help="recalculer la difficulté des exercices du fichier")

    def handle(self, *args, **opts):
        rng = random.Random(opts["seed"])
        seeds = [rng.randrange(1 << 30) for _ in range(opts["games"])]
        local = threading.local()
        engines, lock = [], threading.Lock()

        def get_engine():
            if not getattr(local, "eng", None):
                local.eng = engine_mod.open_engine()
                with lock:
                    engines.append(local.eng)
            return local.eng

        def one_game(seed):
            r = random.Random(seed)
            eng = get_engine()
            board = chess.Board()
            for _ in range(r.randint(2, 7)):
                board.push(r.choice(list(board.legal_moves)))
            lo, hi = (int(x) for x in opts["skill"].split("-"))
            skill = {chess.WHITE: r.randint(lo, hi), chess.BLACK: r.randint(lo, hi)}
            noise = r.choice([float(x) for x in opts["noise"].split(",")])
            history = []
            while not board.is_game_over() and board.ply() < 180:
                if r.random() < noise:
                    mv = r.choice(list(board.legal_moves))
                else:
                    eng.configure({"Skill Level": skill[board.turn]})
                    mv = eng.play(board, chess.engine.Limit(time=0.01)).move
                history.append((board.fen(), mv.uci()))
                board.push(mv)
            eng.configure({"Skill Level": 20})
            # Repérage rapide des gaffes : chances de gain du joueur au trait, avant et après son coup
            evals = []
            b = chess.Board()
            for fen, _ in history:
                b.set_fen(fen)
                evals.append(eng.analyse(b, chess.engine.Limit(time=0.02)))
            candidates = []
            for k in range(len(history) - 1):
                fen, uci = history[k]
                mover = chess.Board(fen).turn
                before = _wp(evals[k], mover)
                after = _wp(evals[k + 1], mover)
                if before - after >= 25 and after <= 35:
                    candidates.append((fen, uci))
            r.shuffle(candidates)
            out = []
            for fen, uci in candidates[: opts["per_game"]]:
                p = puzzles.make_puzzle(eng, fen, uci, opts["time"])
                if p and not (opts["rich_only"] and self.is_trivial(p)):
                    out.append(p)
            return out

        def rerate(p):
            eng = get_engine()
            board = chess.Board(p["fen"])
            moves = p["moves"].split()
            board.push(chess.Move.from_uci(moves[0]))
            p["rating"] = puzzles.estimate_rating(eng, board, moves[1], len(moves) // 2, set(p["themes"]))
            return p

        found = {}
        if opts["append"]:
            try:
                with open(opts["out"], encoding="utf-8") as fh:
                    for p in json.load(fh)["puzzles"]:
                        found[p["uid"]] = p
            except FileNotFoundError:
                pass
        start = len(found)
        if opts["rerate"] and found:
            with ThreadPoolExecutor(max_workers=max(1, opts["workers"])) as pool:
                list(pool.map(rerate, list(found.values())))
            self.stdout.write(f"{len(found)} exercices réévalués.")
        try:
            with ThreadPoolExecutor(max_workers=max(1, opts["workers"])) as pool:
                futs = [pool.submit(one_game, s) for s in seeds]
                for n, fut in enumerate(as_completed(futs), 1):
                    try:
                        for p in fut.result():
                            key = p["fen"] + "|" + p["moves"]
                            p["uid"] = "cc-" + hashlib.sha1(key.encode()).hexdigest()[:10]
                            found[p["uid"]] = p
                    except Exception as exc:  # noqa: BLE001
                        self.stderr.write(f"partie ignorée : {exc}")
                    if n % 10 == 0:
                        self.stdout.write(f"{n} / {len(seeds)} parties · {len(found) - start} nouveaux exercices")
        finally:
            for e in engines:
                try:
                    e.quit()
                except Exception:  # noqa: BLE001
                    pass

        for e in engines:
            try:
                e.quit()
            except Exception:  # noqa: BLE001
                pass
        items = sorted(found.values(), key=lambda p: (p["rating"], p["uid"]))
        data = {"version": 1, "generated": dt.date.today().isoformat(), "count": len(items),
                "source": "Exercices générés par Stockfish (auto-parties) pour Chess Coach",
                "puzzles": [{"uid": p["uid"], "fen": p["fen"], "moves": p["moves"], "rating": p["rating"],
                             "themes": p["themes"]} for p in items]}
        with open(opts["out"], "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
            fh.write("\n")
        self.stdout.write(self.style.SUCCESS(f"{len(items)} exercices dans {opts['out']} ({len(items) - start} nouveaux)."))
