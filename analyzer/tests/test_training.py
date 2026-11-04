"""Tests de l'entraînement : thèmes, exercices, classement, banque intégrée, parties de référence."""
import io
import json
import unittest

import chess
from django.test import TestCase

from analyzer.models import Puzzle, PuzzleAttempt, ReferenceStudy
from analyzer.services import engine, puzzle_themes, puzzles, references, training

# Format Lichess : position AVANT le coup adverse, puis ce coup et la solution.
BACK_RANK = ("6k1/5ppp/8/n7/8/8/8/R5K1 b - - 0 1", ["a5c4", "a1a8"])
SMOTHERED = ("6rk/1p4pp/8/6N1/8/8/8/6K1 b - - 0 1", ["b7b6", "g5f7"])
FORK = ("4k3/8/r7/1N6/8/8/8/4K3 b - - 0 1", ["a6a8", "b5c7", "e8d7", "c7a8"])


def make(uid, fen_moves, rating=1200, themes=None, alternatives=""):
    fen, moves = fen_moves
    keys = themes if themes is not None else sorted(puzzles.detect_themes(fen, moves))
    return Puzzle.objects.create(uid=uid, fen=fen, moves=" ".join(moves), rating=rating,
                                 themes=" " + " ".join(keys) + " ", alternatives=alternatives)


class ThemeDetectionTests(TestCase):
    def test_back_rank_mate(self):
        t = puzzles.detect_themes(*BACK_RANK)
        self.assertTrue({"mate", "mateIn1", "backRankMate", "oneMove"} <= t, t)

    def test_smothered_mate(self):
        t = puzzles.detect_themes(*SMOTHERED)
        self.assertTrue({"mate", "mateIn1", "smotheredMate"} <= t, t)

    def test_knight_fork(self):
        t = puzzles.detect_themes(*FORK)
        self.assertIn("fork", t)
        self.assertIn("short", t)
        self.assertIn("endgame", t)

    def test_catalogue_labels(self):
        for key in puzzle_themes.FINDING_THEMES.values():
            for k in key:
                self.assertTrue(puzzle_themes.is_known(k), k)


class PuzzlePayloadTests(TestCase):
    def test_payload_has_every_position(self):
        p = make("t-fork", FORK, alternatives="")
        data = puzzles.payload(p)
        self.assertEqual(data["color"], "w")
        self.assertEqual(len(data["steps"]), 2)
        first = data["steps"][0]
        self.assertEqual(first["solution"], "b5c7")
        self.assertIn("b5c7", first["legal"])
        self.assertEqual(first["reply"]["uci"], "e8d7")
        self.assertIsNone(data["steps"][1]["reply"])
        # Chaque coup légal porte la position obtenue : l'interface n'a pas besoin des règles
        b = chess.Board(first["fen"])
        self.assertEqual(len(first["legal"]), b.legal_moves.count())

    def test_mate_flag_and_alternatives(self):
        p = make("t-br", BACK_RANK, alternatives="a1a7")
        step = puzzles.payload(p)["steps"][0]
        self.assertTrue(step["legal"]["a1a8"]["mate"])
        self.assertEqual(step["accept"], ["a1a8", "a1a7"])


class RatingAndSelectionTests(TestCase):
    def setUp(self):
        self.easy = make("t1", BACK_RANK, rating=900)
        self.mid = make("t2", SMOTHERED, rating=1200)
        self.hard = make("t3", FORK, rating=1500)

    def test_rating_moves_with_results(self):
        start = training.current_rating()
        a = training.record_attempt(self.mid, solved=True, seconds=10, theme="mix")
        self.assertGreater(a.rating_after, start)
        b = training.record_attempt(self.hard, solved=False, theme="mix")
        self.assertLess(b.rating_after, b.rating_before)
        self.assertEqual(training.current_rating(), b.rating_after)
        self.hard.refresh_from_db()
        self.assertGreater(self.hard.rating, 1500)  # raté : l'exercice devient un peu plus « difficile »
        self.assertEqual(training.streak(), 0)

    def test_next_puzzle_prefers_unseen_and_review(self):
        training.record_attempt(self.easy, solved=False)
        nxt = training.next_puzzle("mix")
        self.assertNotEqual(nxt.pk, self.easy.pk)
        self.assertEqual(training.failed_puzzle_ids(), [self.easy.pk])
        self.assertEqual(training.next_puzzle("review").pk, self.easy.pk)
        self.assertEqual(training.next_puzzle("smotheredMate").pk, self.mid.pk)
        self.assertIsNone(training.next_puzzle("promotion"))

    def test_theme_stats(self):
        training.record_attempt(self.easy, solved=True)
        training.record_attempt(self.mid, solved=False)
        st = training.theme_stats()
        self.assertEqual(st["mate"]["n"], 2)
        self.assertEqual(st["mate"]["solved"], 1)
        self.assertEqual(st["backRankMate"]["rate"], 100)


class BankAndImportTests(TestCase):
    def test_shipped_bank_is_valid(self):
        added = training.load_bank()
        self.assertGreater(added, 50)
        self.assertEqual(training.load_bank(), 0)  # idempotent
        for p in Puzzle.objects.all():
            moves = p.move_list
            self.assertGreaterEqual(len(moves), 2, p.uid)
            self.assertEqual(len(moves) % 2, 0, p.uid)  # coup adverse + coups du joueur/réponses, finit par le joueur
            data = puzzles.payload(p)  # lève une exception si un coup est illégal
            for step in data["steps"]:
                self.assertIn(step["solution"], step["legal"], p.uid)

    def test_lichess_csv_import(self):
        csv_text = (
            "PuzzleId,FEN,Moves,Rating,RatingDeviation,Popularity,NbPlays,Themes,GameUrl,OpeningTags\n"
            "00008,r6k/pp2r2p/4Rp1Q/3p4/8/1N1P2R1/PqP2bPP/7K b - - 0 24,f2g3 e6e7 b2b1 b3c1 b1c1 h6c1,1913,75,94,6331,crushing hangingPiece long middlegame,https://lichess.org/787zsVup/black#48,\n"
            "0000D,5rk1/1p3ppp/pq3b2/8/8/1P1Q1N2/P4PPP/3R2K1 w - - 2 27,d3d6 f8d8 d6d8 f6d8,1580,74,96,17000,advantage endgame short,https://lichess.org/F8M8OS71#53,\n"
        )
        added = training.import_lichess_csv(io.StringIO(csv_text), themes=["hangingPiece"])
        self.assertEqual(added, 1)
        p = Puzzle.objects.get(uid="lichess-00008")
        self.assertIn("hangingPiece", p.theme_list)
        self.assertEqual(puzzles.payload(p)["color"], "w")


class ReferenceTests(TestCase):
    def test_catalogue_complete_and_valid(self):
        with open(references.CATALOGUE_FILE, encoding="utf-8") as fh:
            raw = json.load(fh)["games"]
        games = references.catalogue()
        self.assertEqual(len(games), len(raw), "une partie du catalogue est invalide")
        for g in games:
            data = references.payload(g)
            self.assertEqual(len(data["fens"]), len(data["moves"]) + 1)
            noted = sum(1 for m in data["moves"] if m["note"])
            self.assertEqual(noted, len(g["notes"]), f"note mal placée dans {g['slug']}")
            for t in g["themes"]:
                self.assertIn(t, references.THEMES)

    def test_recommendations_follow_findings(self):
        recs = {"findings": [{"id": "missed_mates", "level": "critique", "title": "Des mats que tu ne vois pas"}]}
        out = references.recommend(None, recs, limit=3)
        self.assertTrue(all("mating_attack" in g["themes"] or "double_check" in g["themes"] or "sacrifice" in g["themes"]
                            for g in out))
        self.assertIn("Des mats que tu ne vois pas", out[0]["reasons"])


class TrainingViewsTests(TestCase):
    def setUp(self):
        self.p = make("v1", FORK, rating=1100)

    def test_pages(self):
        slug = references.catalogue()[0]["slug"]
        for url in ["/exercices/", "/exercices/jouer/mix/", "/exercices/jouer/fork/", "/exercices/jouer/review/",
                    "/exercices/jouer/mine/", "/exercices/progression/", "/references/", f"/references/{slug}/",
                    "/references/?niveau=avance", "/exercices/api/suivant/?theme=fork"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get("/exercices/jouer/nimporte/").status_code, 404)
        self.assertEqual(self.client.get("/references/nimporte/").status_code, 404)

    def test_attempt_api_saves_result(self):
        r = self.client.post(f"/exercices/api/{self.p.pk}/tentative/", data=json.dumps({"solved": True, "seconds": 8}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(PuzzleAttempt.objects.count(), 1)
        self.assertGreater(r.json()["delta"], 0)

    def test_reference_progress(self):
        slug = references.catalogue()[0]["slug"]
        r = self.client.post(f"/references/{slug}/progression/", data=json.dumps({"completed": True, "guess_total": 4,
                             "guess_correct": 3}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        st = ReferenceStudy.objects.get(slug=slug)
        self.assertIsNotNone(st.completed_at)
        self.assertEqual(st.guess_score, 75)


@unittest.skipUnless(engine.engine_available(), "Stockfish non installé")
class PuzzleEngineTests(TestCase):
    def test_make_puzzle_finds_back_rank_mate(self):
        eng = engine.open_engine()
        try:
            p = puzzles.make_puzzle(eng, BACK_RANK[0], BACK_RANK[1][0], seconds=0.1)
        finally:
            eng.quit()
        self.assertIsNotNone(p)
        self.assertEqual(p["moves"].split()[1], "a1a8")
        self.assertIn("backRankMate", p["themes"])


class SprintAndDailyTests(TestCase):
    def setUp(self):
        self.a = make("s1", BACK_RANK, rating=800)
        self.b = make("s2", SMOTHERED, rating=900)
        self.c = make("s3", FORK, rating=1000)

    def test_daily_puzzle_is_stable_for_the_day(self):
        p1, done = training.daily_puzzle()
        p2, _ = training.daily_puzzle()
        self.assertEqual(p1.pk, p2.pk)
        self.assertFalse(done)
        training.record_attempt(p1, solved=True)
        self.assertTrue(training.daily_puzzle()[1])

    def test_sprint_batch_increasing_and_unique(self):
        items = training.sprint_batch(800, n=3)
        self.assertEqual(len({p.pk for p in items}), 3)
        self.assertEqual([p.rating for p in items], sorted(p.rating for p in items))

    def test_sprint_api_and_record(self):
        r = self.client.get("/exercices/api/course/?start=800&n=2")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["puzzles"]), 2)
        post = lambda body: self.client.post("/exercices/api/course/resultat/", data=json.dumps(body),
                                             content_type="application/json")
        r1 = post({"duration": 180, "score": 5, "mistakes": 3, "best_rating": 1000}).json()
        self.assertTrue(r1["record"])
        r2 = post({"duration": 180, "score": 3, "mistakes": 3}).json()
        self.assertFalse(r2["record"])
        self.assertEqual(r2["best"], 5)
        self.assertEqual(post({"duration": 42, "score": 1}).status_code, 400)
        self.assertEqual(PuzzleAttempt.objects.count(), 0)  # la course ne touche pas au classement
        self.assertEqual(self.client.get("/exercices/course/").status_code, 200)


class ApiValidationTests(TestCase):
    def test_bad_payloads_are_rejected(self):
        p = make("bad", FORK)
        post = lambda url, body: self.client.post(url, data=body, content_type="application/json")
        self.assertEqual(post(f"/exercices/api/{p.pk}/tentative/", '{"seconds": "abc"}').status_code, 400)
        self.assertEqual(post(f"/exercices/api/{p.pk}/tentative/", "[1, 2]").status_code, 400)
        self.assertEqual(post("/exercices/api/course/resultat/", '{"duration": 180, "score": "x"}').status_code, 400)
        slug = references.catalogue()[0]["slug"]
        self.assertEqual(post(f"/references/{slug}/progression/", '{"guess_total": "x"}').status_code, 400)
        self.assertEqual(PuzzleAttempt.objects.count(), 0)


class CandidateGamesTests(TestCase):
    def test_scanned_games_are_skipped_until_reanalysed(self):
        import datetime as dt

        from django.utils import timezone

        from analyzer.services import jobs, pgn_import
        from analyzer.tests.test_core import SAMPLE_PGN, SCHOLAR_PGN, fake_plies

        export, _, _ = pgn_import.import_pgn_text(SAMPLE_PGN.encode())
        game = export.games.get(black="moi")
        jobs.save_analysis(game, fake_plies(SCHOLAR_PGN, [30, 30, 0, 20, 30, 30, 9990], mates={6: 1}), 0.01)
        self.assertEqual([g.pk for g in training.candidate_games(export)], [game.pk])
        training.save_game_puzzles(game, [])
        self.assertEqual(training.candidate_games(export), [])
        export.games.filter(pk=game.pk).update(analyzed_at=timezone.now() + dt.timedelta(minutes=1))
        self.assertEqual([g.pk for g in training.candidate_games(export)], [game.pk])
