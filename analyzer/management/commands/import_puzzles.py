import io

from django.core.management.base import BaseCommand, CommandError

from analyzer.services import training


class Command(BaseCommand):
    help = ("Importe la base d'exercices libre de Lichess (CC0) : https://database.lichess.org/#puzzles. "
            "Fichier .csv, ou .csv.zst si le module « zstandard » est installé.")

    def add_arguments(self, parser):
        parser.add_argument("path", help="lichess_db_puzzle.csv (ou .csv.zst)")
        parser.add_argument("--max", type=int, default=20000, help="nombre max d'exercices (défaut 20000)")
        parser.add_argument("--themes", default="", help="thèmes à garder, séparés par des virgules (ex. fork,pin)")
        parser.add_argument("--min-rating", type=int, default=400)
        parser.add_argument("--max-rating", type=int, default=2600)
        parser.add_argument("--min-popularity", type=int, default=50, help="popularité Lichess minimale (-100 à 100)")

    def handle(self, *args, **opts):
        path = opts["path"]
        try:
            if path.endswith(".zst"):
                try:
                    import zstandard
                except ImportError as exc:
                    raise CommandError("Décompresse d'abord le fichier (zstd -d) ou installe « zstandard ».") from exc
                raw = zstandard.ZstdDecompressor().stream_reader(open(path, "rb"))
                stream = io.TextIOWrapper(raw, encoding="utf-8")
            else:
                stream = open(path, encoding="utf-8")
        except OSError as exc:
            raise CommandError(str(exc)) from exc
        with stream:
            added = training.import_lichess_csv(
                stream, limit=opts["max"], themes=[t for t in opts["themes"].split(",") if t],
                min_rating=opts["min_rating"], max_rating=opts["max_rating"], min_popularity=opts["min_popularity"])
        self.stdout.write(self.style.SUCCESS(f"{added} exercice(s) importé(s)."))
