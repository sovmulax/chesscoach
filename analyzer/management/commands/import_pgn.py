from django.core.management.base import BaseCommand, CommandError

from analyzer.services import jobs, pgn_import


class Command(BaseCommand):
    help = "Importe un fichier PGN (export Chess.com, Lichess…) et peut lancer l'analyse Stockfish."

    def add_arguments(self, parser):
        parser.add_argument("pgn", help="chemin du fichier .pgn")
        parser.add_argument("--player", default="", help="pseudo à analyser (détecté automatiquement sinon)")
        parser.add_argument("--name", default="", help="nom de l'export")
        parser.add_argument("--analyze", action="store_true", help="lancer l'analyse moteur tout de suite")
        parser.add_argument("--time", type=float, default=None, help="secondes par position (défaut : ANALYSIS_TIME_BULK)")

    def handle(self, *args, **opts):
        try:
            with open(opts["pgn"], "rb") as fh:
                data = fh.read()
        except OSError as exc:
            raise CommandError(str(exc)) from exc
        export, added, skipped = pgn_import.import_pgn_text(data, opts["name"], opts["player"], opts["time"])
        self.stdout.write(self.style.SUCCESS(
            f"Export #{export.pk} « {export.name} » : {added} parties importées pour {export.player}"
            + (f", {skipped} ignorées" if skipped else "")))
        if opts["analyze"]:
            self.stdout.write("Analyse en cours (Ctrl+C pour arrêter, relancer analyze_export pour reprendre)…")
            jobs._run_export(export.pk, opts["time"], False)
            export.refresh_from_db()
            self.stdout.write(self.style.SUCCESS(export.job_message))
