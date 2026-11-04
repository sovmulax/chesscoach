from django.db import models
from django.urls import reverse


class Export(models.Model):
    """Un lot de parties : un fichier PGN importé ou un compte Chess.com synchronisé."""

    KIND_PGN = "pgn"
    KIND_CHESSCOM = "chesscom"
    KIND_CHOICES = [(KIND_PGN, "Fichier PGN"), (KIND_CHESSCOM, "Compte Chess.com")]

    STATUS_IDLE = "idle"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_IDLE, "En attente"),
        (STATUS_RUNNING, "Analyse en cours"),
        (STATUS_DONE, "Analysé"),
        (STATUS_ERROR, "Erreur"),
    ]

    name = models.CharField("nom", max_length=200)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_PGN)
    player = models.CharField("joueur analysé", max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    # Analyse moteur
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_IDLE)
    analysis_time = models.FloatField("temps par position (s)", default=0.05)
    job_message = models.CharField(max_length=300, blank=True)
    job_started_at = models.DateTimeField(null=True, blank=True)
    job_finished_at = models.DateTimeField(null=True, blank=True)
    job_heartbeat = models.DateTimeField(null=True, blank=True)

    # Chess.com
    time_classes = models.CharField(
        "cadences synchronisées", max_length=100, blank=True,
        help_text="ex. rapid,blitz — vide = toutes",
    )
    auto_analyze = models.BooleanField("analyser automatiquement les nouvelles parties", default=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    sync_message = models.CharField(max_length=300, blank=True)
    synced_archives = models.JSONField(default=dict, blank=True)  # {"2026/05": "etag ou date"}

    # Résumé mis en cache (recalculé quand des parties sont ajoutées/analysées)
    summary = models.JSONField(null=True, blank=True)
    summary_key = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("analyzer:export_detail", args=[self.pk])

    @property
    def is_chesscom(self):
        return self.kind == self.KIND_CHESSCOM

    @property
    def time_class_list(self):
        return [t.strip() for t in self.time_classes.split(",") if t.strip()]


class Game(models.Model):
    STATUS_PENDING = "pending"
    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Non analysée"),
        (STATUS_QUEUED, "En file"),
        (STATUS_RUNNING, "En cours"),
        (STATUS_DONE, "Analysée"),
        (STATUS_ERROR, "Erreur"),
    ]

    export = models.ForeignKey(Export, on_delete=models.CASCADE, related_name="games")
    uid = models.CharField(max_length=200, help_text="identifiant unique (URL Chess.com ou empreinte)")
    pgn = models.TextField()
    headers = models.JSONField(default=dict)

    played_at = models.DateTimeField(null=True, blank=True)
    date = models.CharField(max_length=20, blank=True)
    white = models.CharField(max_length=100)
    black = models.CharField(max_length=100)
    white_elo = models.IntegerField(null=True, blank=True)
    black_elo = models.IntegerField(null=True, blank=True)
    result = models.CharField(max_length=10)
    termination = models.CharField(max_length=200, blank=True)
    termination_kind = models.CharField(max_length=30, blank=True)
    time_control = models.CharField(max_length=30, blank=True)
    time_class = models.CharField(max_length=20, blank=True)
    url = models.URLField(max_length=300, blank=True)

    player_color = models.CharField(max_length=1, choices=[("w", "Blancs"), ("b", "Noirs")])
    player_result = models.CharField(max_length=5, choices=[("win", "Victoire"), ("draw", "Nulle"), ("loss", "Défaite")])
    player_elo = models.IntegerField(null=True, blank=True)
    opponent = models.CharField(max_length=100)
    opponent_elo = models.IntegerField(null=True, blank=True)

    opening_name = models.CharField(max_length=200, blank=True)
    opening_moves = models.CharField(max_length=200, blank=True)
    num_plies = models.IntegerField(default=0)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    analysis_time = models.FloatField(null=True, blank=True)
    analysis = models.JSONField(null=True, blank=True)  # sortie brute du moteur, une entrée par position
    stats = models.JSONField(null=True, blank=True)  # métriques calculées (coups annotés + stats partie)
    analyzed_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["played_at", "id"]
        constraints = [models.UniqueConstraint(fields=["export", "uid"], name="unique_game_per_export")]
        indexes = [models.Index(fields=["export", "status"])]

    def __str__(self):
        return f"{self.white} – {self.black} ({self.date})"

    def get_absolute_url(self):
        return reverse("analyzer:game_detail", args=[self.pk])

    @property
    def is_analyzed(self):
        return self.status == self.STATUS_DONE and self.stats is not None

    @property
    def move_count(self):
        return (self.num_plies + 1) // 2

    @property
    def score(self):
        return {"win": 1.0, "draw": 0.5, "loss": 0.0}[self.player_result]


# ---------------------------------------------------------------------------
# Entraînement : exercices à thème et parties de référence.
# Tables ajoutées sans toucher aux modèles Export / Game ci-dessus.
# ---------------------------------------------------------------------------
class Puzzle(models.Model):
    """Un exercice au format Lichess : position, puis coup adverse « déclencheur » et solution.

    `moves` = coups UCI séparés par des espaces : le 1er est joué par l'adversaire
    (il crée l'occasion), puis alternent coup du joueur / réponse adverse.
    """

    SOURCE_BANK = "bank"
    SOURCE_GAME = "game"
    SOURCE_IMPORT = "import"
    SOURCE_CHOICES = [
        (SOURCE_BANK, "Banque intégrée"),
        (SOURCE_GAME, "Tirée de tes parties"),
        (SOURCE_IMPORT, "Importée"),
    ]

    uid = models.CharField(max_length=64, unique=True)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=SOURCE_BANK)
    fen = models.CharField("position avant le coup adverse", max_length=100)
    moves = models.CharField("coups UCI (coup adverse puis solution)", max_length=400)
    alternatives = models.CharField("autres premiers coups acceptés (UCI)", max_length=200, blank=True)
    rating = models.IntegerField("difficulté", default=1500)
    themes = models.CharField(max_length=400, blank=True,
                              help_text="clés de thèmes séparées et encadrées par des espaces")
    game = models.ForeignKey(Game, null=True, blank=True, on_delete=models.SET_NULL, related_name="puzzles")
    ply = models.IntegerField(null=True, blank=True, help_text="indice du coup dans la partie d'origine")
    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["rating", "id"]
        indexes = [models.Index(fields=["source", "rating"])]

    def __str__(self):
        return f"Exercice {self.uid} ({self.rating})"

    @property
    def theme_list(self):
        return self.themes.split()

    @property
    def move_list(self):
        return self.moves.split()

    @property
    def player_moves(self):
        return len(self.move_list) // 2


class PuzzleAttempt(models.Model):
    """Une tentative de résolution (historique conservé pour suivre la progression)."""

    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE, related_name="attempts")
    theme = models.CharField("thème travaillé", max_length=40, blank=True)
    solved = models.BooleanField("réussi du premier coup")
    mistakes = models.IntegerField(default=0)
    used_hint = models.BooleanField(default=False)
    seconds = models.FloatField(null=True, blank=True)
    puzzle_rating = models.IntegerField("difficulté de l'exercice au moment de l'essai", null=True, blank=True)
    rating_before = models.IntegerField()
    rating_after = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["created_at"])]

    def __str__(self):
        return f"{'✓' if self.solved else '✗'} {self.puzzle.uid}"


class PuzzleScan(models.Model):
    """Partie déjà parcourue pour en tirer des exercices (évite de refaire le travail)."""

    game = models.OneToOneField(Game, on_delete=models.CASCADE, related_name="puzzle_scan")
    scanned_at = models.DateTimeField(auto_now=True)
    created = models.IntegerField(default=0)

    def __str__(self):
        return f"Partie {self.game_id} : {self.created} exercice(s)"


class ReferenceStudy(models.Model):
    """Progression sur une partie de référence (catalogue : analyzer/data/reference_games.json)."""

    slug = models.SlugField(max_length=80, unique=True)
    viewed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    guess_correct = models.IntegerField(default=0)
    guess_total = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.slug

    @property
    def guess_score(self):
        return round(100 * self.guess_correct / self.guess_total) if self.guess_total else None
