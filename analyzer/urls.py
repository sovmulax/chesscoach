from django.urls import path

from . import views, views_training as training

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
    # Exercices à thème
    path("exercices/", training.training_home, name="training_home"),
    path("exercices/progression/", training.training_progress, name="training_progress"),
    path("exercices/jouer/<str:theme>/", training.training_play, name="training_play"),
    path("exercices/api/suivant/", training.training_next, name="training_next"),
    path("exercices/api/<int:pk>/tentative/", training.training_attempt, name="training_attempt"),
    path("exercices/creer/<int:pk>/", training.training_generate, name="training_generate"),
    path("exercices/creer/<int:pk>/statut.json", training.training_generate_status, name="training_generate_status"),
    # Parties de référence
    path("references/", training.reference_list, name="reference_list"),
    path("references/<slug:slug>/", training.reference_detail, name="reference_detail"),
    path("references/<slug:slug>/progression/", training.reference_progress, name="reference_progress"),
]
