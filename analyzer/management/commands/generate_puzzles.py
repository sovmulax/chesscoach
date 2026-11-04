from django.core.management.base import BaseCommand, CommandError

from analyzer.models import Export
from analyzer.services import jobs


class Command(BaseCommand):
    help = "Crée des exercices à partir de tes erreurs dans les parties analysées d'un export."

    def add_arguments(self, parser):
        parser.add_argument("export", type=int, help="numéro de l'export")
        parser.add_argument("--games", type=int, default=150, help="nombre max de parties à parcourir (défaut 150)")
        parser.add_argument("--time", type=float, default=0.25, help="secondes de calcul par position (défaut 0,25)")

    def handle(self, *args, **opts):
        if not Export.objects.filter(pk=opts["export"]).exists():
            raise CommandError(f"Export {opts['export']} introuvable.")
        created = jobs._run_puzzles(opts["export"], opts["games"], opts["time"])
        self.stdout.write(self.style.SUCCESS(jobs.puzzle_job_status(opts["export"])["message"] or f"{created} exercices"))
