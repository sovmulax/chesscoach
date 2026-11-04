"""Données communes à toutes les pages (thèmes proposés dans le panneau « Apparence »).

Les thèmes sont purement visuels : le choix est enregistré dans le navigateur
(localStorage), rien n'est stocké en base. Pour ajouter un thème, ajoute une
entrée ici et le bloc CSS correspondant dans static/analyzer/app.css.
"""

PALETTES = [
    ("classique", "Classique"),
    ("ocean", "Océan"),
    ("foret", "Forêt"),
    ("amethyste", "Améthyste"),
    ("ardoise", "Ardoise"),
]

BOARDS = [
    ("bois", "Bois"),
    ("tournoi", "Tournoi"),
    ("glace", "Glace"),
    ("ardoise", "Ardoise"),
    ("corail", "Corail"),
    ("lavande", "Lavande"),
    ("assorti", "Assorti"),
]


def appearance(request):
    return {"palettes": PALETTES, "boards": BOARDS}
