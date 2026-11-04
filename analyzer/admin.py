from django.contrib import admin

from .models import Export, Game, Puzzle, PuzzleAttempt, ReferenceStudy


@admin.register(Export)
class ExportAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "player", "status", "created_at", "last_sync_at")
    exclude = ("summary",)


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("__str__", "export", "player_result", "opening_name", "status")
    list_filter = ("export", "status", "player_result", "time_class")
    exclude = ("analysis", "stats")


@admin.register(Puzzle)
class PuzzleAdmin(admin.ModelAdmin):
    list_display = ("uid", "source", "rating", "themes", "game")
    list_filter = ("source",)
    search_fields = ("uid", "themes")
    raw_id_fields = ("game",)


@admin.register(PuzzleAttempt)
class PuzzleAttemptAdmin(admin.ModelAdmin):
    list_display = ("created_at", "puzzle", "solved", "used_hint", "rating_before", "rating_after")
    list_filter = ("solved", "used_hint")
    raw_id_fields = ("puzzle",)


@admin.register(ReferenceStudy)
class ReferenceStudyAdmin(admin.ModelAdmin):
    list_display = ("slug", "viewed_at", "completed_at", "guess_correct", "guess_total")
