import io
import unittest
from unittest import mock

import chess.pgn
from django.test import TestCase, override_settings

from analyzer.models import Export, Game
from analyzer.services import chesscom, engine, jobs, metrics, openings, pgn_import, recommendations, summary
from analyzer.services.notation import display_numbered, to_fr

SAMPLE_PGN = """[Event "Live Chess"]
[Site "Chess.com"]
[Date "2026.05.23"]
[White "moi"]
[Black "adv1"]
[Result "0-1"]
[WhiteElo "726"]
[BlackElo "729"]
[TimeControl "600"]
[EndTime "21:56:44 GMT+0000"]
[Termination "adv1 a gagné par échec et mat"]

1. d4 e5 2. dxe5 Nc6 3. Nf3 Qe7 4. Bf4 Qb4+ 5. Qd2 Qxb2 6. Qc3 Bb4 7. Qxb4 Qxb4+
8. Bd2 Qb2 9. Bc3 Qc1# 0-1

[Event "Live Chess"]
[Site "Chess.com"]
[Date "2026.05.24"]
[White "adv2"]
[Black "moi"]
[Result "1-0"]
[WhiteElo "730"]
[BlackElo "720"]
[TimeControl "180+2"]
[EndTime "10:00:00 GMT+0000"]
[Termination "adv2 a gagné par échec et mat"]

1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0
"""

SCHOLAR_PGN = "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0"


def fake_plies(pgn, cps, mates=None, final_outcome="checkmate"):
    """Construit une « analyse » sans moteur : cp donnés pour chaque position avant coup."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    board = game.board()
    plies = []
    mates = mates or {}
    for i, mv in enumerate(game.mainline_moves()):
        plies.append({"fen": board.fen(), "san": board.san(mv), "uci": mv.uci(), "cp": cps[i],
                      "mate": mates.get(i), "best": None, "best_uci": None, "pv": [], "clock": None})
        board.push(mv)
    plies.append({"fen": board.fen(), "cp": 10000 if final_outcome else 0, "mate": None,
                  "final": True, "outcome": final_outcome})
    return plies


class NotationTests(TestCase):
    def test_to_fr(self):
        self.assertEqual(to_fr("Nxe5+"), "Cxe5+")
        self.assertEqual(to_fr("e8=Q#"), "e8=D#")
        self.assertEqual(to_fr("O-O-O"), "O-O-O")
        self.assertEqual(to_fr("Kg6"), "Rg6")
        self.assertEqual(display_numbered(["d4", "e5", "dxe5"]), "1.d4 e5 2.dxe5")

    def test_openings(self):
        self.assertEqual(openings.identify(["d4", "d5", "Bf4", "Nf6"]), "Système de Londres")
        self.assertEqual(openings.identify(["e4", "c5", "f4"]), "Sicilienne, attaque Grand Prix")
        self.assertEqual(openings.identify(["d4", "e5", "dxe5"]), "Gambit Englund")

    def test_time_class_and_termination(self):
        self.assertEqual(pgn_import.time_class_from_control("600"), "rapid")
        self.assertEqual(pgn_import.time_class_from_control("180+2"), "blitz")
        self.assertEqual(pgn_import.time_class_from_control("60"), "bullet")
        self.assertEqual(pgn_import.time_class_from_control("1/86400"), "daily")
        self.assertEqual(pgn_import.termination_kind("X a gagné par échec et mat", "1-0"), "checkmate")
        self.assertEqual(pgn_import.termination_kind("Partie nulle par manque de matériel", "1/2-1/2"), "insufficient")
        self.assertEqual(pgn_import.termination_kind("Partie nulle par pat", "1/2-1/2"), "stalemate")
        self.assertEqual(pgn_import.termination_kind("X a gagné – partie abandonnée", "1-0"), "abandoned")
        self.assertEqual(pgn_import.termination_kind("X won by resignation", "1-0"), "resignation")


class ImportTests(TestCase):
    def test_import_detects_player_and_dedups(self):
        export, added, skipped = pgn_import.import_pgn_text(SAMPLE_PGN.encode())
        self.assertEqual(export.player, "moi")
        self.assertEqual(added, 2)
        g1, g2 = export.games.order_by("played_at")
        self.assertEqual((g1.player_color, g1.player_result, g1.opening_name), ("w", "loss", "Gambit Englund"))
        self.assertEqual((g2.player_color, g2.player_result, g2.time_class), ("b", "loss", "blitz"))
        # Réimporter les mêmes parties dans l'export n'ajoute rien
        items = [(g, pgn_import.game_to_pgn(g), {}) for g in pgn_import.split_games(SAMPLE_PGN)]
        self.assertEqual(pgn_import.add_games(export, items), (0, 2))


class MetricsTests(TestCase):
    def test_allowed_mate_and_blunder(self):
        # positions avant : e4, e5, Qh5, Nc6, Bc4, Nf6(gaffe), Qxf7#
        plies = fake_plies(SCHOLAR_PGN, [30, 30, 0, 20, 30, 30, 9990], mates={6: 1})
        st = metrics.compute_game_stats(plies, "b", "loss")
        nf6 = st["moves"][5]
        self.assertEqual(nf6["san"], "Nf6")
        self.assertEqual(nf6["cls"], "blunder")
        self.assertIn("allowed_mate", nf6["tags"])
        self.assertEqual(st["counts"]["mine"]["blunder"], 1)
        self.assertEqual(st["first_blunder"]["by"], "me")
        self.assertTrue(st["lost_from_equal"])
        self.assertEqual(st["missed_mates"], 0)  # Qxf7# est joué par l'adversaire

    def test_missed_mate_for_white(self):
        pgn = "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qe2 Bc5 *"
        plies = fake_plies(pgn, [30, 30, 0, 20, 30, 30, 9990, 0], mates={6: 1}, final_outcome=None)
        plies[-1]["cp"] = 0
        st = metrics.compute_game_stats(plies, "w", "draw")
        qe2 = st["moves"][6]
        self.assertIn("missed_mate", qe2["tags"])
        self.assertIn("missed_mate_1", qe2["tags"])
        self.assertEqual(st["missed_mates_1"], 1)


class SummaryAndViewsTests(TestCase):
    def setUp(self):
        self.export, _, _ = pgn_import.import_pgn_text(SAMPLE_PGN.encode())
        g = self.export.games.get(black="moi")
        jobs.save_analysis(g, fake_plies(SCHOLAR_PGN, [30, 30, 0, 20, 30, 30, 9990], mates={6: 1}), 0.01)

    def test_summary_and_recommendations(self):
        s = summary.compute_summary(list(self.export.games.all()))
        self.assertEqual(s["n_games"], 2)
        self.assertEqual(s["n_analyzed"], 1)
        self.assertEqual(s["basic"]["results"]["loss"], 2)
        recs = recommendations.build(s)
        self.assertTrue(recs["fundamentals"])
        self.assertTrue(recs["plan"])

    def test_pages(self):
        game = self.export.games.get(black="moi")
        for url in ["/", f"/exports/{self.export.pk}/", f"/exports/{self.export.pk}/parties/",
                    f"/parties/{game.pk}/", f"/parties/{game.pk}/?coup=5", f"/exports/{self.export.pk}/statut.json"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_upload(self):
        f = io.BytesIO(SAMPLE_PGN.encode())
        f.name = "parties.pgn"
        r = self.client.post("/", {"pgn_file": f, "name": "Test", "player": "", "analysis_time": "0.05"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Export.objects.filter(name="Test").exists())


class ChessComTests(TestCase):
    ARCHIVE = {"games": [
        {"url": "https://www.chess.com/game/live/1", "pgn": SAMPLE_PGN.split("\n\n[Event")[0] + "\n",
         "time_class": "rapid", "rules": "chess", "end_time": 1779573404},
        {"url": "https://www.chess.com/game/live/2", "pgn": "[Event \"x\"]\n[White \"moi\"]\n[Black \"z\"]\n[Result \"1-0\"]\n\n1. e4 1-0",
         "time_class": "bullet", "rules": "chess960", "end_time": 1779573404},
    ]}

    def test_archives_to_fetch(self):
        urls = [f"https://api.chess.com/pub/player/moi/games/2026/{m:02d}" for m in (5, 6, 7)]
        self.assertEqual(chesscom.archives_to_fetch(urls, {}), urls)
        synced = {"2026/05": {}, "2026/06": {}}
        self.assertEqual(chesscom.archives_to_fetch(urls, synced), urls[1:])

    def test_sync_adds_then_dedups(self):
        export = Export.objects.create(name="cc", kind=Export.KIND_CHESSCOM, player="moi")

        def fake_get(url, etag=None, retries=3):
            if url.endswith("/archives"):
                return {"archives": ["https://api.chess.com/pub/player/moi/games/2026/05"]}, None
            return self.ARCHIVE, '"e1"'

        with mock.patch.object(chesscom, "_get", side_effect=fake_get), mock.patch.object(chesscom.time, "sleep"):
            added, _ = chesscom.sync_export(export)
            self.assertEqual(added, 1)  # la partie chess960 est ignorée
            export.refresh_from_db()
            added2, _ = chesscom.sync_export(export)
            self.assertEqual(added2, 0)
        g = export.games.get()
        self.assertEqual(g.uid, "https://www.chess.com/game/live/1")
        self.assertEqual(g.time_class, "rapid")


@unittest.skipUnless(engine.engine_available(), "Stockfish non installé")
class EngineIntegrationTests(TestCase):
    def test_real_engine_on_short_game(self):
        export, _, _ = pgn_import.import_pgn_text(SAMPLE_PGN.encode())
        with override_settings(ANALYSIS_WORKERS=1):
            jobs._run_export(export.pk, 0.01, False)
        export.refresh_from_db()
        self.assertEqual(export.status, Export.STATUS_DONE)
        self.assertEqual(export.games.filter(status=Game.STATUS_DONE).count(), 2)
        scholar = export.games.get(black="moi")
        nf6 = scholar.stats["moves"][5]
        self.assertEqual(nf6["cls"], "blunder")
