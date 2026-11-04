from django.contrib import admin

from .models import Export, Game


@admin.register(Export)
class ExportAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "player", "status", "created_at", "last_sync_at")
    exclude = ("summary",)


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("__str__", "export", "player_result", "opening_name", "status")
    list_filter = ("export", "status", "player_result", "time_class")
    exclude = ("analysis", "stats")
