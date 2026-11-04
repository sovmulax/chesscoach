from django import forms

TIME_CHOICES = [
    ("0.05", "Rapide — 0,05 s par position (≈ 1 min pour 10 parties)"),
    ("0.1", "Standard — 0,1 s par position"),
    ("0.3", "Précise — 0,3 s par position (lent sur un gros export)"),
]

TIME_CLASS_CHOICES = [("bullet", "Bullet"), ("blitz", "Blitz"), ("rapid", "Rapide"), ("daily", "Daily")]


class PGNUploadForm(forms.Form):
    pgn_file = forms.FileField(label="Fichier PGN", help_text="Export Chess.com, Lichess ou tout fichier .pgn")
    name = forms.CharField(label="Nom de l'export", required=False, max_length=200)
    player = forms.CharField(label="Ton pseudo", required=False, max_length=100,
                             help_text="Laisse vide : il est détecté automatiquement.")
    analyze_now = forms.BooleanField(label="Lancer l'analyse Stockfish tout de suite", required=False, initial=True)
    analysis_time = forms.ChoiceField(label="Précision", choices=TIME_CHOICES, initial="0.05")


class ChessComForm(forms.Form):
    username = forms.CharField(label="Pseudo Chess.com", max_length=100)
    time_classes = forms.MultipleChoiceField(
        label="Cadences à importer", choices=TIME_CLASS_CHOICES, required=False,
        widget=forms.CheckboxSelectMultiple, help_text="Aucune case cochée = toutes les cadences.")
    auto_analyze = forms.BooleanField(label="Analyser automatiquement les nouvelles parties", required=False, initial=True)
    analysis_time = forms.ChoiceField(label="Précision", choices=TIME_CHOICES, initial="0.05")


class AnalyzeForm(forms.Form):
    analysis_time = forms.ChoiceField(label="Précision", choices=TIME_CHOICES, initial="0.05")
    reanalyze = forms.BooleanField(label="Réanalyser aussi les parties déjà faites", required=False)
