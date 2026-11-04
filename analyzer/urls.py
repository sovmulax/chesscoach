from django.urls import path

from . import views

app_name = "analyzer"

urlpatterns = [
    path("", views.export_list, name="export_list"),
    path("chesscom/ajouter/", views.chesscom_add, name="chesscom_add"),
    path("exports/<int:pk>/", views.export_detail, name="export_detail"),
    path("exports/<int:pk>/parties/", views.export_games, name="export_games"),
    path("exports/<int:pk>/analyser/", views.export_analyze, name="export_analyze"),
    path("exports/<int:pk>/arreter/", views.export_stop, name="export_stop"),
    path("exports/<int:pk>/synchroniser/", views.export_sync, name="export_sync"),
    path("exports/<int:pk>/reglages/", views.export_settings, name="export_settings"),
    path("exports/<int:pk>/supprimer/", views.export_delete, name="export_delete"),
    path("exports/<int:pk>/statut.json", views.export_status, name="export_status"),
    path("parties/<int:pk>/", views.game_detail, name="game_detail"),
    path("parties/<int:pk>/analyser/", views.game_analyze, name="game_analyze"),
    path("parties/<int:pk>/statut.json", views.game_status, name="game_status"),
]
