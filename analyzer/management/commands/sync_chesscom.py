from django.core.management.base import BaseCommand, CommandError

from analyzer.models import Export
from analyzer.services import chesscom, jobs


class Command(BaseCommand):
    help = ("Synchronise les comptes Chess.com (nouvelles parties) et les analyse. "
            "À planifier une fois par jour (cron, Planificateur de tâches Windows).")

    def add_arguments(self, parser):
        parser.add_argument("--user", default="", help="pseudo Chess.com (crée le compte s'il n'existe pas)")
        parser.add_argument("--time-classes", default="", help="ex. rapid,blitz (création seulement)")
        parser.add_argument("--full", action="store_true", help="retélécharger toutes les archives")
        parser.add_argument("--no-analyze", action="store_true", help="ne pas lancer Stockfish après la synchro")

    def handle(self, *args, **opts):
        if opts["user"]:
            try:
                export, created = chesscom.create_chesscom_export(opts["user"], opts["time_classes"])
            except chesscom.ChessComError as exc:
                raise CommandError(str(exc)) from exc
            if created:
                self.stdout.write(f"Compte {export.player} ajouté (export #{export.pk}).")
            exports = [export]
        else:
            exports = list(Export.objects.filter(kind=Export.KIND_CHESSCOM))
        if not exports:
            raise CommandError("Aucun compte Chess.com. Utilise --user <pseudo>.")
        for export in exports:
            def progress(i, n, added, export=export):
                self.stdout.write(f"  {export.player} : archive {i}/{n}, {added} nouvelles parties")
            try:
                added, msg = chesscom.sync_export(export, full=opts["full"], progress=progress)
            except chesscom.ChessComError as exc:
                self.stderr.write(self.style.ERROR(f"{export.player} : {exc}"))
                continue
            self.stdout.write(self.style.SUCCESS(f"{export.player} : {msg}"))
            if added and not opts["no_analyze"] and export.auto_analyze:
                jobs._run_export(export.pk, None, False)
                export.refresh_from_db()
                self.stdout.write(self.style.SUCCESS(f"{export.player} : {export.job_message}"))
