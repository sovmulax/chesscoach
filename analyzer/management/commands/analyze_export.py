from django.core.management.base import BaseCommand, CommandError

from analyzer.models import Export
from analyzer.services import jobs


class Command(BaseCommand):
    help = "Analyse avec Stockfish les parties d'un export (reprend là où l'analyse s'est arrêtée)."

    def add_arguments(self, parser):
        parser.add_argument("export_id", type=int)
        parser.add_argument("--time", type=float, default=None, help="secondes par position")
        parser.add_argument("--reanalyze", action="store_true", help="réanalyser aussi les parties déjà faites")

    def handle(self, *args, **opts):
        if not Export.objects.filter(pk=opts["export_id"]).exists():
            raise CommandError("Export introuvable.")
        jobs._run_export(opts["export_id"], opts["time"], opts["reanalyze"])
        self.stdout.write(self.style.SUCCESS(Export.objects.get(pk=opts["export_id"]).job_message))
