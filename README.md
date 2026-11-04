# Chess Coach

Application Django qui analyse tes parties d'échecs avec Stockfish et te donne :

- **par export** (un fichier PGN ou ton compte Chess.com) : un tableau de bord complet
  (résultats, Elo, gaffes par phase, pièces perdues, mats manqués, conversion,
  ouvertures, habitudes de jeu), un **diagnostic** chiffré, tes points forts,
  un **plan d'entraînement** et des **fondamentaux** génériques ;
- **par partie** : un échiquier interactif, la courbe de tes chances de gain,
  chaque coup classé (meilleur, bon, imprécision, erreur, gaffe) avec le meilleur
  coup de Stockfish et une explication (pièce en prise, mat manqué, cadeau non puni…).

Tout tourne en local : tes parties restent sur ta machine.

---

## 1. Installation

Pré-requis : **Python 3.10+** et **Stockfish**.

### Stockfish

| Système | Commande |
|---|---|
| Windows | Télécharge `stockfish-windows-x86-64-avx2.zip` sur <https://stockfishchess.org/download/>, dézippe-le (par ex. dans `C:\stockfish\`) |
| macOS | `brew install stockfish` |
| Ubuntu / Debian | `sudo apt install stockfish` |

L'application cherche Stockfish dans le `PATH` et aux emplacements usuels. Sinon,
indique son chemin :

```bash
# Windows (PowerShell)
$env:STOCKFISH_PATH="C:\stockfish\stockfish-windows-x86-64-avx2.exe"
# macOS / Linux
export STOCKFISH_PATH=/chemin/vers/stockfish
```

### L'application

```bash
cd chesscoach
python -m venv .venv
# Windows : .venv\Scripts\activate     macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Ouvre <http://127.0.0.1:8000>. (Raccourci : `lancer.bat` sous Windows, `./lancer.sh` sinon.)

---

## 2. Utilisation

### Avec un fichier PGN
Sur la page d'accueil, « Importer un fichier PGN ». Ton pseudo est détecté
automatiquement (c'est le joueur présent dans toutes les parties). Coche
« Lancer l'analyse » : elle tourne en arrière-plan, la page se met à jour.

### Avec ton compte Chess.com (sans export)
« Relier mon compte Chess.com » avec ton pseudo. L'application utilise
**l'API publique gratuite de Chess.com** (aucune clé, aucun mot de passe) :

1. la première fois, elle télécharge **tout ton historique**, mois par mois ;
2. ensuite, chaque synchronisation ne récupère que les nouveaux mois et le mois en cours ;
3. les nouvelles parties sont analysées automatiquement (désactivable).

Tu peux choisir les cadences à importer (bullet, blitz, rapide, daily) : mélanger
blitz et rapide fausse un peu les statistiques, le tableau de bord permet aussi de
filtrer par cadence.

La synchro se lance : avec le bouton « Synchroniser » ; automatiquement quand tu ouvres
le tableau de bord d'un compte si la dernière date de plus de 12 h
(`CHESSCOM_AUTO_SYNC_HOURS`) ; ou chaque jour avec une tâche planifiée (ci-dessous).

> Les données publiques de Chess.com peuvent avoir quelques heures de retard sur
> tes toutes dernières parties.

### Synchroniser automatiquement chaque jour

```bash
python manage.py sync_chesscom --user sovmulax          # 1re fois : crée le compte et importe tout
python manage.py sync_chesscom                          # ensuite : tous les comptes reliés
```

- **Windows** (Planificateur de tâches, tous les jours à 7 h) :
  ```
  schtasks /create /tn "ChessCoach sync" /sc daily /st 07:00 /tr "C:\chemin\chesscoach\.venv\Scripts\python.exe C:\chemin\chesscoach\manage.py sync_chesscom"
  ```
- **macOS / Linux** (`crontab -e`) :
  ```
  0 7 * * * cd /chemin/chesscoach && .venv/bin/python manage.py sync_chesscom >> sync.log 2>&1
  ```

### En ligne de commande (script)

```bash
python manage.py import_pgn mes_parties.pgn --analyze          # importe + analyse
python manage.py import_pgn mes_parties.pgn --player sovmulax --time 0.1
python manage.py analyze_export 3                              # reprend l'analyse de l'export n°3
python manage.py analyze_export 3 --reanalyze --time 0.3       # tout réanalyser plus finement
```

Une analyse interrompue (serveur arrêté, Ctrl+C) reprend là où elle s'est arrêtée.

---

## 3. Durée d'analyse

Le temps dépend du nombre de positions : environ 70 par partie.

| Précision | Temps par position | 300 parties sur 4 cœurs |
|---|---|---|
| Rapide | 0,05 s | ≈ 6 min |
| Standard | 0,1 s | ≈ 12 min |
| Précise | 0,3 s | ≈ 35 min |

« Rapide » suffit pour repérer les gaffes sur un gros export. Pour étudier une
partie précise, ouvre-la et clique « Réanalyser plus finement ».

---

## 4. Comment les chiffres sont calculés

- Chaque position est évaluée par Stockfish puis convertie en **chances de gain**
  (formule de Lichess). Un coup est une **imprécision** s'il fait perdre 10 points,
  une **erreur** à 20, une **gaffe** à 30.
- **Pièce en prise** : après ta gaffe, le meilleur coup adverse est une capture.
- **Mat manqué** : un mat en 3 coups ou moins existait et ton coup le laisse filer.
- **Cadeau non puni** : l'adversaire gaffe et ta réponse perd au moins 20 points.
- **Position gagnante** : au moins 85 % de chances de gain ; la conversion mesure
  combien de ces parties tu as réellement gagnées.
- **Phases** : ouverture = 10 premiers coups ; finale = peu de pièces (hors pions).

Les règles du diagnostic sont dans `analyzer/services/recommendations.py` :
chaque règle compare tes chiffres à un seuil ou à ceux de tes adversaires et ne
s'affiche que si l'échantillon est suffisant. Les **fondamentaux** (même fichier)
sont des conseils génériques toujours affichés.

---

## 5. Réglages (variables d'environnement)

| Variable | Défaut | Rôle |
|---|---|---|
| `STOCKFISH_PATH` | auto | chemin de l'exécutable Stockfish |
| `ANALYSIS_WORKERS` | nb de cœurs − 1 | moteurs lancés en parallèle |
| `ANALYSIS_TIME_BULK` | 0.05 | secondes par position (export) |
| `ANALYSIS_TIME_SINGLE` | 0.3 | secondes par position (une partie) |
| `CHESSCOACH_NOTATION` | fr | `fr` (R D T F C) ou `en` (K Q R B N) |
| `CHESSCOM_USER_AGENT` | chesscoach-django/1.0 | Chess.com recommande d'y mettre un contact |
| `CHESSCOM_AUTO_SYNC_HOURS` | 12 | synchro auto à l'ouverture (0 = jamais) |
| `TIME_ZONE` | Africa/Abidjan | fuseau pour les statistiques par heure / jour |

---

## 6. Structure du code

```
config/                     réglages Django
analyzer/
  models.py                 Export (PGN ou compte Chess.com) et Game
  services/
    pgn_import.py           lecture des PGN, détection du joueur, dédoublonnage
    chesscom.py             client de l'API publique Chess.com + synchro incrémentale
    engine.py               pilotage de Stockfish
    metrics.py              classement de chaque coup et statistiques d'une partie
    summary.py              agrégation sur un export
    recommendations.py      diagnostic, points forts, plan d'entraînement, fondamentaux
    explain.py              phrases d'explication coup par coup
    openings.py             noms d'ouvertures
    jobs.py                 analyses et synchros en arrière-plan (threads)
  management/commands/      import_pgn, analyze_export, sync_chesscom
  templates/, static/       pages HTML, CSS et JavaScript (sans dépendance externe)
  tests/                    tests (python manage.py test analyzer)
```
