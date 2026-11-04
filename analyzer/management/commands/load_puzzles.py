from django.core.management.base import BaseCommand

from analyzer.services import training


class Command(BaseCommand):
    help = "Charge la banque d'exercices fournie avec Chess Coach (analyzer/data/puzzles.json)."

    def handle(self, *args, **opts):
        added = training.load_bank()
        self.stdout.write(self.style.SUCCESS(f"{added} exercice(s) ajouté(s) depuis la banque intégrée."))
