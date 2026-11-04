"""Catalogue des thèmes d'exercices.

Les clés reprennent celles de la base d'exercices libre de Lichess (licence CC0),
ce qui permet d'importer cette base telle quelle (commande `import_puzzles`).
Quelques thèmes propres à Chess Coach s'y ajoutent (« mine », « avoidBlunder »…).
"""

CATEGORIES = [
    ("perso", "Pour toi"),
    ("mat", "Mats"),
    ("tactique", "Motifs tactiques"),
    ("finale", "Finales"),
    ("phase", "Phases de jeu"),
    ("longueur", "Longueur"),
]

# clé : (libellé, description, icône, catégorie)
THEMES = {
    # --- Propres à Chess Coach --------------------------------------------
    "mine": ("Tes positions", "Des positions tirées de tes propres parties, là où tu t'es trompé.", "king", "perso"),
    "avoidBlunder": ("Éviter la gaffe", "Trouve un coup sûr dans une position où une gaffe a été jouée.", "shield", "perso"),
    "punish": ("Punir une gaffe", "L'adversaire vient de se tromper : trouve comment en profiter.", "gift", "perso"),

    # --- Mats ---------------------------------------------------------------
    "mate": ("Mat", "Toutes les combinaisons qui se terminent par un mat.", "crown", "mat"),
    "mateIn1": ("Mat en 1", "Un seul coup suffit : repère-le en un coup d'œil.", "crown", "mat"),
    "mateIn2": ("Mat en 2", "Deux coups pour mater, souvent après un échec forçant.", "crown", "mat"),
    "mateIn3": ("Mat en 3", "Une séquence forcée de trois coups.", "crown", "mat"),
    "mateIn4": ("Mat en 4", "Des combinaisons de mat plus longues.", "crown", "mat"),
    "mateIn5": ("Mat en 5 ou plus", "Des combinaisons de mat très longues.", "crown", "mat"),
    "backRankMate": ("Mat du couloir", "Le roi est enfermé derrière ses propres pions sur sa dernière rangée.", "crown", "mat"),
    "smotheredMate": ("Mat étouffé", "Le cavalier mate un roi entouré de ses propres pièces.", "crown", "mat"),
    "anastasiaMate": ("Mat d'Anastasia", "Cavalier et tour (ou dame) piègent le roi contre le bord.", "crown", "mat"),
    "arabianMate": ("Mat arabe", "Cavalier et tour mattent le roi dans le coin.", "crown", "mat"),
    "bodenMate": ("Mat de Boden", "Deux fous croisés mattent le roi roqué.", "crown", "mat"),
    "doubleBishopMate": ("Mat des deux fous", "Deux fous sur des diagonales voisines.", "crown", "mat"),
    "dovetailMate": ("Mat en queue d'aronde", "La dame mate, le roi bloqué par ses propres pièces.", "crown", "mat"),
    "hookMate": ("Mat du crochet", "Tour, cavalier et pion coordonnés autour du roi.", "crown", "mat"),

    # --- Tactique ------------------------------------------------------------
    "fork": ("Fourchette", "Une pièce attaque deux cibles à la fois.", "zap", "tactique"),
    "pin": ("Clouage", "Une pièce ne peut pas bouger sans exposer une pièce plus importante.", "target", "tactique"),
    "skewer": ("Enfilade", "Attaque d'une pièce de valeur qui, en s'écartant, laisse prendre celle de derrière.", "target", "tactique"),
    "discoveredAttack": ("Attaque à la découverte", "Une pièce bouge et démasque l'attaque d'une autre.", "eye", "tactique"),
    "doubleCheck": ("Échec double", "Deux pièces donnent échec en même temps : seul le roi peut bouger.", "zap", "tactique"),
    "hangingPiece": ("Pièce en prise", "Une pièce sans défense attend d'être prise.", "gift", "tactique"),
    "trappedPiece": ("Pièce piégée", "Une pièce n'a plus de case de fuite.", "target", "tactique"),
    "sacrifice": ("Sacrifice", "Céder du matériel pour obtenir davantage.", "flame", "tactique"),
    "deflection": ("Déviation", "Détourner une pièce de sa tâche de défense.", "arrow-right", "tactique"),
    "attraction": ("Attraction", "Attirer une pièce adverse sur une case fatale.", "target", "tactique"),
    "clearance": ("Dégagement", "Libérer une case ou une ligne pour une autre pièce.", "arrow-right", "tactique"),
    "interference": ("Interception", "Couper la liaison entre deux pièces adverses.", "x", "tactique"),
    "intermezzo": ("Coup intermédiaire", "Un coup inattendu avant la reprise évidente.", "zap", "tactique"),
    "xRayAttack": ("Rayons X", "Une pièce agit à travers une autre.", "eye", "tactique"),
    "capturingDefender": ("Élimination du défenseur", "Prendre la pièce qui en protège une autre.", "trash", "tactique"),
    "exposedKing": ("Roi exposé", "Profiter d'un roi mal protégé.", "king", "tactique"),
    "kingsideAttack": ("Attaque à l'aile roi", "Attaque contre le roi roqué.", "flame", "tactique"),
    "queensideAttack": ("Attaque à l'aile dame", "Attaque contre le roi roqué côté dame.", "flame", "tactique"),
    "quietMove": ("Coup tranquille", "Ni échec ni prise, mais une menace imparable.", "bulb", "tactique"),
    "defensiveMove": ("Défense", "Trouve le seul coup qui sauve la position.", "shield", "tactique"),
    "zugzwang": ("Zugzwang", "L'adversaire aimerait passer son tour : chaque coup l'affaiblit.", "clock", "tactique"),
    "advancedPawn": ("Pion avancé", "Un pion proche de la promotion fait la différence.", "arrow-right", "tactique"),
    "promotion": ("Promotion", "Mener un pion à dame (ou ailleurs !).", "crown", "tactique"),
    "underPromotion": ("Sous-promotion", "Promouvoir en tour, fou ou cavalier plutôt qu'en dame.", "crown", "tactique"),
    "enPassant": ("Prise en passant", "La règle de la prise en passant au service de la tactique.", "arrow-right", "tactique"),
    "castling": ("Roque", "Le roque comme coup tactique.", "king", "tactique"),

    # --- Finales -------------------------------------------------------------
    "endgame": ("Finale", "Peu de pièces : précision et roi actif.", "king", "finale"),
    "pawnEndgame": ("Finale de pions", "Rois et pions seulement : opposition et course.", "king", "finale"),
    "rookEndgame": ("Finale de tours", "Les finales les plus fréquentes.", "king", "finale"),
    "queenEndgame": ("Finale de dames", "Échecs perpétuels et pions passés.", "king", "finale"),
    "bishopEndgame": ("Finale de fous", "Couleur des cases et pions bloqués.", "king", "finale"),
    "knightEndgame": ("Finale de cavaliers", "Les cavaliers et leurs sauts.", "king", "finale"),
    "queenRookEndgame": ("Finale dame et tour", "Dame et tour contre dame et tour.", "king", "finale"),

    # --- Phases --------------------------------------------------------------
    "opening": ("Ouverture", "Les pièges et occasions des premiers coups.", "book", "phase"),
    "middlegame": ("Milieu de partie", "Quand les pièces entrent en contact.", "swords", "phase"),

    # --- Longueur ------------------------------------------------------------
    "oneMove": ("En un coup", "Un seul coup à trouver : idéal pour l'échauffement.", "zap", "longueur"),
    "short": ("Court (2 coups)", "Deux coups à trouver.", "list", "longueur"),
    "long": ("Long (3 coups)", "Trois coups à enchaîner.", "list", "longueur"),
    "veryLong": ("Très long (4 coups et +)", "Calcul en profondeur.", "list", "longueur"),
}

# Modes spéciaux de la page d'entraînement (pas des thèmes stockés)
MODES = {
    "mix": ("Exercices variés", "Tous thèmes confondus, à ton niveau.", "zap"),
    "review": ("Révisions", "Les exercices que tu as ratés, à retenter.", "repeat"),
}

# Constat du diagnostic -> thèmes d'exercices qui le travaillent
FINDING_THEMES = {
    "first_blunder": ["avoidBlunder", "hangingPiece", "fork"],
    "lost_from_equal": ["avoidBlunder", "defensiveMove", "hangingPiece"],
    "blunder_rate": ["avoidBlunder", "hangingPiece", "fork"],
    "hanging": ["hangingPiece", "fork", "pin", "discoveredAttack"],
    "missed_mates": ["mateIn1", "mateIn2", "backRankMate"],
    "unpunished": ["punish", "hangingPiece", "fork"],
    "conversion": ["endgame", "promotion", "advancedPawn"],
    "king_safety": ["defensiveMove", "backRankMate", "mateIn2"],
    "late_castle": ["defensiveMove", "exposedKing"],
    "motifs": ["mine", "hangingPiece"],
    "time_trouble": ["oneMove", "mateIn1"],
    "timeouts": ["oneMove", "mateIn1"],
    "repeated": ["opening", "mine"],
    "weak_openings": ["opening"],
    "phase_opening": ["opening", "hangingPiece"],
    "phase_middlegame": ["middlegame", "fork", "pin"],
    "phase_endgame": ["endgame", "pawnEndgame", "rookEndgame"],
    "fatigue": ["mine"],
    "tilt": ["mine"],
    "plateau": ["mix", "mine"],
    "color_gap": ["opening"],
}


def label(key):
    if key in THEMES:
        return THEMES[key][0]
    if key in MODES:
        return MODES[key][0]
    return key


def info(key):
    if key in THEMES:
        lab, desc, icon, cat = THEMES[key]
        return {"key": key, "label": lab, "description": desc, "icon": icon, "category": cat}
    if key in MODES:
        lab, desc, icon = MODES[key]
        return {"key": key, "label": lab, "description": desc, "icon": icon, "category": "mode"}
    return {"key": key, "label": key, "description": "", "icon": "bulb", "category": "autre"}


def is_known(key):
    return key in THEMES or key in MODES
