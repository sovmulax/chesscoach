"""Identification simple des ouvertures à partir des premiers coups (SAN anglais).

On cherche le plus long préfixe connu. Si le PGN contient un en-tête ECOUrl
(exports Chess.com récents), son nom est utilisé en priorité.
"""
import re

# Séquences en SAN anglais, séparées par des espaces -> nom français.
OPENINGS = {
    # 1.e4
    "e4": "Ouverture du pion roi",
    "e4 e5": "Partie ouverte",
    "e4 e5 Nf3": "Partie ouverte, 2.Cf3",
    "e4 e5 Nf3 Nc6": "Partie ouverte, 2…Cc6",
    "e4 e5 Nf3 Nc6 Bb5": "Partie espagnole",
    "e4 e5 Nf3 Nc6 Bc4": "Partie italienne",
    "e4 e5 Nf3 Nc6 Bc4 Bc5": "Partie italienne, Giuoco Piano",
    "e4 e5 Nf3 Nc6 Bc4 Nf6": "Défense des deux cavaliers",
    "e4 e5 Nf3 Nc6 d4": "Partie écossaise",
    "e4 e5 Nf3 Nc6 Nc3": "Partie des trois/quatre cavaliers",
    "e4 e5 Nf3 Nf6": "Défense Petrov",
    "e4 e5 Nf3 d6": "Défense Philidor",
    "e4 e5 Nf3 f6": "Défense Damiano",
    "e4 e5 Bc4": "Ouverture du fou",
    "e4 e5 Nc3": "Partie viennoise",
    "e4 e5 f4": "Gambit du roi",
    "e4 e5 d4": "Gambit du centre",
    "e4 e5 Qh5": "Attaque Parham (2.Dh5)",
    "e4 e5 Qf3": "Ouverture 2.Df3",
    "e4 c5": "Défense sicilienne",
    "e4 c5 Nf3": "Sicilienne, 2.Cf3",
    "e4 c5 Nf3 d6 d4": "Sicilienne ouverte (2…d6)",
    "e4 c5 Nf3 Nc6 d4": "Sicilienne ouverte (2…Cc6)",
    "e4 c5 Nf3 e6 d4": "Sicilienne ouverte (2…e6)",
    "e4 c5 Nf3 Nc6 Bb5": "Sicilienne Rossolimo",
    "e4 c5 Nf3 d6 Bb5+": "Sicilienne Moscou",
    "e4 c5 d4": "Sicilienne, 2.d4",
    "e4 c5 d4 cxd4 c3": "Sicilienne, gambit Smith-Morra",
    "e4 c5 Nc3": "Sicilienne fermée",
    "e4 c5 c3": "Sicilienne Alapine",
    "e4 c5 f4": "Sicilienne, attaque Grand Prix",
    "e4 c5 Bc4": "Sicilienne, 2.Fc4 (Bowdler)",
    "e4 c5 d3": "Sicilienne, 2.d3",
    "e4 c5 Qh5": "Sicilienne, 2.Dh5",
    "e4 e6": "Défense française",
    "e4 e6 d4 d5 e5": "Française, variante d'avance",
    "e4 e6 d4 d5 exd5": "Française, variante d'échange",
    "e4 e6 d4 d5 Nc3": "Française, 3.Cc3",
    "e4 e6 d4 d5 Nd2": "Française Tarrasch",
    "e4 c6": "Défense Caro-Kann",
    "e4 c6 d4 d5 e5": "Caro-Kann, variante d'avance",
    "e4 d5": "Défense scandinave",
    "e4 d5 exd5 Qxd5": "Scandinave, 2…Dxd5",
    "e4 d6": "Défense Pirc",
    "e4 g6": "Défense moderne",
    "e4 Nf6": "Défense Alekhine",
    "e4 Nc6": "Défense Nimzowitsch",
    "e4 b6": "Défense Owen",
    "e4 a6": "Défense St. George",
    # 1.d4
    "d4": "Ouverture du pion dame",
    "d4 d5": "Jeu du pion dame",
    "d4 d5 c4": "Gambit dame",
    "d4 d5 c4 e6": "Gambit dame refusé",
    "d4 d5 c4 dxc4": "Gambit dame accepté",
    "d4 d5 c4 c6": "Défense slave",
    "d4 d5 Bf4": "Système de Londres",
    "d4 d5 Nf3 Nf6 Bf4": "Système de Londres",
    "d4 d5 e3": "Système Colle / 2.e3",
    "d4 d5 Nf3": "Jeu du pion dame, 2.Cf3",
    "d4 d5 Bg5": "Attaque Levitsky",
    "d4 d5 e4": "Gambit Blackmar-Diemer",
    "d4 Nf6": "Défense indienne",
    "d4 Nf6 c4 g6": "Indienne du roi / Grünfeld",
    "d4 Nf6 c4 e6": "Nimzo / Ouest-indienne",
    "d4 Nf6 c4 c5": "Défense Benoni",
    "d4 Nf6 Bf4": "Système de Londres",
    "d4 Nf6 Nf3": "Indienne, 2.Cf3",
    "d4 Nf6 Bg5": "Attaque Trompowsky",
    "d4 e6": "Ouverture du pion dame, 1…e6",
    "d4 e6 Bf4": "Système de Londres (1…e6)",
    "d4 f5": "Défense hollandaise",
    "d4 e5": "Gambit Englund",
    "d4 c5": "Défense Benoni ancienne",
    "d4 c6": "Ouverture du pion dame, 1…c6",
    "d4 c6 Bf4": "Système de Londres (1…c6)",
    "d4 d6": "Ouverture du pion dame, 1…d6",
    "d4 g6": "Défense moderne (1.d4 g6)",
    "d4 b6": "Défense anglaise (1…b6)",
    "d4 Nc6": "Défense Tchigorine (1…Cc6)",
    # Autres
    "c4": "Ouverture anglaise",
    "Nf3": "Ouverture Réti",
    "b3": "Ouverture Larsen",
    "f4": "Ouverture Bird",
    "g3": "Ouverture Benko (1.g3)",
    "e3": "Ouverture Van't Kruijs (1.e3)",
    "d3": "Ouverture Mieses (1.d3)",
    "Nc3": "Ouverture Dunst (1.Cc3)",
    "b4": "Ouverture polonaise",
    "a3": "Ouverture Anderssen (1.a3)",
    "h3": "Ouverture Clemenz (1.h3)",
}

_MAX_LEN = max(len(k.split()) for k in OPENINGS)


def name_from_eco_url(url):
    """https://www.chess.com/openings/Sicilian-Defense-Closed-2...d6 -> 'Sicilian Defense Closed'."""
    if not url:
        return ""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    slug = re.split(r"-\d", slug)[0]  # retire la suite de coups "…-3.Nc3"
    return slug.replace("-", " ").strip()


def identify(sans, headers=None):
    """Retourne le nom de l'ouverture pour une liste de coups SAN (anglais)."""
    headers = headers or {}
    eco_name = name_from_eco_url(headers.get("ECOUrl", ""))
    best, depth = "", 0
    for n in range(min(len(sans), _MAX_LEN), 0, -1):
        key = " ".join(sans[:n])
        if key in OPENINGS:
            best, depth = OPENINGS[key], n
            break
    # Notre table (en français) est préférée dès qu'elle reconnaît au moins
    # deux demi-coups ; sinon on se rabat sur le nom fourni par Chess.com.
    if depth >= 2 or not eco_name:
        return best or "Ouverture irrégulière"
    return eco_name
