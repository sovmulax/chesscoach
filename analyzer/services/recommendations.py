"""Transforme le résumé chiffré d'un export en diagnostic et en plan de travail.

Chaque règle compare tes chiffres à un seuil (ou à ceux de tes adversaires)
et ne se déclenche que si l'échantillon est suffisant. Les « fondamentaux »
en fin de fichier sont des conseils techniques génériques, toujours affichés.
"""
import re

from .notation import PIECE_NAMES_PLURAL, display_line, display_numbered

_DECIMAL = re.compile(r"(?<=\d)\.(?=\d)")


def _fr(text):
    """Décimales à la française dans les phrases (55.6 -> 55,6), sans toucher aux coups."""
    return _DECIMAL.sub(",", text)

LEVELS = {"critique": 0, "important": 1, "conseil": 2}

TRAINING = {
    "anti_blunder": ("Routine anti-gaffe à chaque coup",
                     "Avant de jouer : quels échecs, captures et menaces a l'adversaire après mon coup ? "
                     "Mes pièces sont-elles toutes protégées ? Surtout entre les coups 10 et 30."),
    "puzzles_hanging": ("Puzzles « pièce en prise » et « menaces », 15 min/jour",
                        "But : repérer en moins de 5 secondes une pièce non protégée, chez toi comme chez l'adversaire."),
    "puzzles_mate": ("Puzzles « mat en 1 / mat en 2 »",
                     "Habitude : regarder d'abord TOUS les échecs disponibles avant de chercher un plan."),
    "conversion": ("Convertir une position gagnante",
                   "Quand tu as l'avantage : échange les pièces, garde la sécurité de ton roi, ne prends aucun risque. "
                   "Rejoue des positions gagnantes contre l'ordinateur jusqu'au mat."),
    "endgames": ("Finales de base",
                 "Opposition roi + pion contre roi, règle du carré, mats dame + roi et tour + roi sans pat."),
    "openings": ("Réparer les ouvertures faibles",
                 "Pour chaque ligne signalée : apprends les 6–8 premiers coups et le plan typique, puis revois tes parties."),
    "review": ("Revoir chaque défaite",
               "Trouve le coup où tout a basculé (la courbe d'évaluation le montre), note la règle à retenir."),
    "time": ("Gestion de la pendule",
             "Joue vite les coups d'ouverture connus, garde du temps pour le milieu de partie, "
             "ne descends pas sous la minute dans une position compliquée."),
    "sessions": ("Sessions courtes",
                 "3 parties d'affilée maximum, puis pause ou analyse d'une partie."),
    "king_safety": ("Sécurité du roi",
                    "Roque avant le 10e coup, ne pousse pas les pions devant ton roi roqué sans raison, "
                    "compte les attaquants et les défenseurs autour de ton roi."),
}


def _f(level, fid, title, finding, actions, training=None, examples=None):
    return {"level": level, "id": fid, "title": title, "finding": finding, "actions": actions,
            "training": training or [], "examples": examples or []}


def build(summary):
    findings, strengths = [], []
    basic = summary.get("basic") or {}
    eng = summary.get("engine")
    habits = summary.get("habits") or {}

    if eng and eng["n"] >= 5:
        _engine_rules(eng, findings, strengths)
    _repeated_rules(summary, findings)
    _opening_rules(summary, findings, strengths)
    _habit_rules(basic, habits, eng, findings, strengths)

    for f in findings:
        f["finding"] = _fr(f["finding"])
    strengths = [_fr(s) for s in strengths]
    findings.sort(key=lambda f: LEVELS[f["level"]])
    plan, seen = [], {}
    for f in findings:
        for t in f["training"]:
            if t not in seen:
                seen[t] = {"id": t, "title": TRAINING[t][0], "text": TRAINING[t][1], "because": []}
                plan.append(seen[t])
            # Lien vers les constats qui justifient cet exercice (affichage uniquement)
            seen[t]["because"].append({"id": f["id"], "title": f["title"], "level": f["level"]})
    if "review" not in seen:
        plan.append({"id": "review", "title": TRAINING["review"][0], "text": TRAINING["review"][1], "because": []})
    for f in findings:
        f["training_items"] = [{"id": t, "title": TRAINING[t][0]} for t in f["training"]]
    counts = {lvl: sum(1 for f in findings if f["level"] == lvl) for lvl in LEVELS}
    return {"findings": findings, "strengths": strengths, "plan": plan[:7], "fundamentals": FUNDAMENTALS,
            "counts": counts}


def _engine_rules(eng, findings, strengths):
    fb = eng["first_blunder"]
    me, opp = fb.get("me", {"n": 0}), fb.get("opp", {"n": 0})
    if me["n"] >= 5 and me["n"] > 1.2 * max(1, opp["n"]):
        findings.append(_f(
            "critique", "first_blunder", "Tu fais la première grosse erreur plus souvent que ton adversaire",
            f"Tu gaffes en premier dans {me['n']} parties (score {me['score']} %), ton adversaire dans "
            f"{opp['n']} (score {opp.get('score')} %). À ton niveau, la première gaffe décide souvent de la partie.",
            ["Applique une vérification systématique avant chaque coup (échecs, captures, menaces).",
             "Ralentis aux moments de contact entre les pièces : c'est là que les gaffes arrivent."],
            ["anti_blunder", "puzzles_hanging"], eng["examples"]["blunders"]))
    elif opp["n"] > me["n"] and opp["n"] >= 5:
        strengths.append(f"Ton adversaire gaffe en premier plus souvent que toi ({opp['n']} parties contre {me['n']}).")

    if eng["n_losses"] >= 5:
        share = round(100 * eng["lost_from_equal"] / eng["n_losses"])
        if share >= 50:
            findings.append(_f(
                "critique", "lost_from_equal", "Tes défaites viennent surtout de tes propres gaffes",
                f"Dans {eng['lost_from_equal']} défaites sur {eng['n_losses']} ({share} %), la position était "
                f"équilibrée ou meilleure pour toi juste avant ta première grosse erreur.",
                ["Ce n'est pas un problème de niveau d'ouverture ou de stratégie : c'est la vérification "
                 "de chaque coup qui fera gagner des points.",
                 "Revois ces défaites en sautant directement au coup marqué « ?? »."],
                ["anti_blunder", "review"]))

    bpg = eng["per_game"]["blunder"]
    if bpg >= 0.5:
        findings.append(_f(
            "critique" if bpg >= 1 else "important", "blunder_rate", "Trop de gaffes par partie",
            f"{bpg} gaffe(s) par partie en moyenne (adversaires : {eng['opp_per_game']['blunder']}). "
            f"Une gaffe = un coup qui fait chuter tes chances de gain d'au moins 30 points.",
            ["Objectif réaliste : passer sous 0,7 gaffe par partie.",
             "Après avoir choisi un coup, regarde-le une dernière fois « avec les yeux de l'adversaire »."],
            ["anti_blunder"]))

    if eng["hanging_share"] and eng["hanging_share"] >= 40 and eng["hanging_n"] >= 5:
        lost = ", ".join(f"{x['n']} {PIECE_NAMES_PLURAL.get(x['piece'], x['piece'])}" for x in eng["material_lost"][:5])
        findings.append(_f(
            "critique", "hanging", "Des pièces laissées en prise",
            f"{eng['hanging_share']} % de tes gaffes laissent l'adversaire prendre du matériel dès le coup suivant "
            f"(perdu : {lost}). Dans {eng['hanging_other_share']} % de ces cas, la pièce perdue n'est pas celle "
            f"que tu viens de jouer : tu as raté une menace ou laissé une pièce sans défense.",
            ["Après chaque coup adverse, demande-toi : « Qu'est-ce qu'il menace maintenant ? »",
             "Avant ton coup : « Quelles pièces mon coup laisse-t-il sans protection ? »",
             "Une pièce non protégée est une cible : protège-la ou rends-la utile."],
            ["anti_blunder", "puzzles_hanging"], eng["examples"]["hanging"]))

    labels = {"opening": "l'ouverture", "middlegame": "le milieu de partie", "endgame": "la finale"}
    phase_actions = {
        "opening": (["Développe cavaliers et fous avant de sortir la dame.", "Roque tôt, ne joue pas deux fois la même pièce sans raison."], ["openings"]),
        "middlegame": (["C'est là que les pièces entrent en contact : vérifie les menaces à chaque coup.",
                        "Cherche les motifs tactiques classiques : fourchette, clouage, enfilade, attaque à la découverte."],
                       ["anti_blunder", "puzzles_hanging"]),
        "endgame": (["Active ton roi dès que les dames sont échangées.", "Maîtrise l'opposition et les mats de base."], ["endgames"]),
    }
    worst = None
    for ph, d in eng["phases"].items():
        if d["moves"] < 80 or d["blunder_rate"] is None or d["opp_blunder_rate"] is None:
            continue
        if d["blunder_rate"] > d["opp_blunder_rate"] * 1.15 and d["blunder_rate"] >= 1:
            # Impact = gaffes « en trop » par rapport aux adversaires, sur le nombre de coups joués
            excess = (d["blunder_rate"] - d["opp_blunder_rate"]) * d["moves"]
            if worst is None or excess > worst[1]:
                worst = (ph, excess)
        elif d["blunder_rate"] < d["opp_blunder_rate"] * 0.9:
            strengths.append(f"Dans {labels[ph]}, tu gaffes moins que tes adversaires "
                             f"({d['blunder_rate']} % de tes coups contre {d['opp_blunder_rate']} %).")
    if worst:
        ph = worst[0]
        d = eng["phases"][ph]
        acts, tr = phase_actions[ph]
        med = eng.get("first_blunder_move_median")
        findings.append(_f(
            "important", f"phase_{ph}", f"Ta zone rouge : {labels[ph]}",
            f"{d['blunder_rate']} % de tes coups y sont des gaffes, contre {d['opp_blunder_rate']} % pour tes adversaires."
            + (f" Ta première gaffe arrive en médiane au coup {med:g}." if med else ""),
            acts, tr))

    mmg = eng["missed_mate_games"]
    if mmg["n"] >= 3 and mmg["n"] / eng["n"] >= 0.08:
        findings.append(_f(
            "important", "missed_mates", "Des mats que tu ne vois pas",
            f"Dans {mmg['n']} parties, tu avais un mat en 3 coups ou moins et tu as joué autre chose "
            f"({eng['missed_mates_1']} fois un mat en 1). Résultat de ces parties : {mmg['win']} V, {mmg['draw']} N, {mmg['loss']} D.",
            ["Quand tu attaques, examine d'abord tous les échecs, même ceux qui sacrifient du matériel.",
             "Entraîne les motifs de mat : couloir, étouffé, dame + fou, deux tours."],
            ["puzzles_mate"], eng["examples"]["missed_mates"]))

    if eng["unpunished_share"] and eng["unpunished_share"] >= 25 and eng["n_opp_blunders"] >= 10:
        findings.append(_f(
            "important", "unpunished", "Les cadeaux de l'adversaire ne sont pas punis",
            f"{eng['unpunished']} gaffes adverses sur {eng['n_opp_blunders']} ({eng['unpunished_share']} %) "
            f"n'ont pas été exploitées : ta réponse a rendu l'avantage.",
            ["Après chaque coup adverse, regarde d'abord ce qu'il laisse sans défense.",
             "Un coup adverse surprenant cache souvent une erreur : cherche la prise ou l'échec."],
            ["puzzles_hanging"], eng["examples"]["unpunished"]))

    win = eng["winning"]
    if win["n"] >= 8 and eng["conversion_rate"] is not None:
        if eng["conversion_rate"] < 85:
            st = eng["stalemates_while_winning"]
            findings.append(_f(
                "important", "conversion", "Des parties gagnantes qui t'échappent",
                f"{win['n']} parties avec une position gagnante (≥ 85 % de chances) : {win['win']} gagnées, "
                f"{win['loss']} perdues, {win['draw']} nulles ({eng['conversion_rate']} % de conversion)."
                + (f" Dont {len(st)} pat(s) alors que tu gagnais." if st else ""),
                ["En position gagnante : simplifie, échange les pièces, évite les complications.",
                 "Quand l'adversaire n'a plus que son roi, vérifie à chaque coup qu'il lui reste une case (pas de pat)."],
                ["conversion", "endgames"], eng["examples"]["stalemates"]))
        else:
            strengths.append(f"Tu convertis bien tes positions gagnantes ({eng['conversion_rate']} %).")

    if eng["n"] >= 20 and eng["allowed_mates"] / eng["n"] >= 0.08:
        findings.append(_f(
            "important", "king_safety", "Ton roi se fait surprendre",
            f"{eng['allowed_mates']} coups ont autorisé un mat forcé contre toi.",
            ["Avant chaque coup, regarde les échecs possibles de l'adversaire.",
             "Garde une case de fuite pour ton roi (le fameux « couloir »)."],
            ["king_safety", "puzzles_mate"], eng["examples"]["allowed_mates"]))

    if eng["motifs"]:
        top = eng["motifs"][:4]
        txt = " ; ".join(f"{display_line([m['move']])} → {display_line([m['reply']])} ({m['n']} fois)" for m in top)
        findings.append(_f(
            "important", "motifs", "Des erreurs qui se répètent à l'identique",
            f"Mêmes coups, même punition : {txt}.",
            ["Note ces motifs : ce sont tes « pièges personnels ».",
             "Avant de jouer une pièce sur une case, regarde toutes les lignes (diagonales, colonnes) qui y mènent."],
            ["review", "anti_blunder"]))

    if eng["clock_games"] >= 10 and eng["time_trouble_share"] and eng["time_trouble_share"] >= 25:
        findings.append(_f(
            "important", "time_trouble", "La pendule te fait gaffer",
            f"{eng['time_trouble_share']} % de tes erreurs sont jouées avec moins de 30 secondes.",
            ["Joue plus vite l'ouverture, garde au moins 2 minutes pour la fin de partie."], ["time"]))

    if eng["eval10_median"] is not None and eng["eval10_median"] >= 0.2:
        strengths.append(f"Tes ouvertures te donnent l'avantage : évaluation médiane de {eng['eval10_median']:+.1f} "
                         f"après 10 coups ({eng['eval10_ahead']} % des parties à +1 pion ou mieux).")
    if eng["saved"] >= 5:
        strengths.append(f"Tu ne lâches rien : {eng['saved']} parties perdues sauvées (victoire ou nulle).")

    if eng["castle_move_median"] and eng["castle_move_median"] > 12:
        findings.append(_f(
            "conseil", "late_castle", "Tu roques tard",
            f"Roque au coup {eng['castle_move_median']:g} en médiane.",
            ["Vise le roque avant le 10e coup dans les ouvertures ouvertes."], ["king_safety"]))


def _repeated_rules(summary, findings):
    reps = summary.get("repeated_losses") or []
    if reps:
        lines = []
        for r in reps[:4]:
            col = "Blancs" if r["color"] == "w" else "Noirs"
            lines.append(f"{col} : {display_numbered(r['moves'])} ({r['losses']} défaites sur {r['n']})")
        findings.append(_f(
            "critique", "repeated", "Le même piège, plusieurs fois",
            "Séquences d'ouverture identiques perdues à plusieurs reprises : " + " · ".join(lines) + ".",
            ["Ouvre une de ces parties, trouve le coup fautif et prépare la bonne réponse.",
             "Après chaque défaite rapide (moins de 15 coups), regarde l'ouverture dans une base de données."],
            ["openings", "review"],
            [{"game_id": r["game_ids"][0], "ply": r["length"] - 1, "san": r["moves"][-1], "n": (r["length"] + 1) // 2}
             for r in reps[:4]]))


def _opening_rules(summary, findings, strengths):
    rows = summary.get("openings") or []
    weak = [r for r in rows if r["weak"]][:5]
    strong = [r for r in rows if r["strong"]][:3]
    if weak:
        txt = " ; ".join(f"{'Blancs' if r['color'] == 'w' else 'Noirs'} · {r['name']} ({r['n']} parties, {r['score']} %)" for r in weak)
        findings.append(_f(
            "conseil", "weak_openings", "Des ouvertures où tu marques peu",
            f"{txt}.",
            ["Choisis une seule réponse à apprendre pour chaque ligne et tiens-t'y.",
             "Regarde où l'évaluation chute dans ces parties : ouverture ratée ou erreur plus tard ?"],
            ["openings"]))
    for r in strong:
        strengths.append(f"{'Blancs' if r['color'] == 'w' else 'Noirs'} · {r['name']} : {r['score']} % sur {r['n']} parties.")


def _habit_rules(basic, habits, eng, findings, strengths):
    res = basic.get("results", {})
    losses = res.get("loss", 0)
    if losses >= 10:
        share = 100 * basic.get("lost_on_time", 0) / losses
        if share >= 10:
            findings.append(_f(
                "important", "timeouts", "Des défaites au temps",
                f"{basic['lost_on_time']} défaites au temps ({share:.0f} % de tes défaites).",
                ["Garde une réserve de temps, joue les coups évidents rapidement."], ["time"]))
        elif basic.get("lost_on_time", 0) == 0:
            strengths.append("Aucune défaite au temps : tu gères bien ta pendule.")

    ranks = {r["rank"]: r for r in habits.get("game_rank", [])}
    if 1 in ranks and ranks[1]["n"] >= 15:
        late = [r for k, r in ranks.items() if k >= 4 and r["n"] >= 15]
        for r in late:
            if r["score"] is not None and ranks[1]["score"] is not None and r["score"] <= ranks[1]["score"] - 10:
                findings.append(_f(
                    "conseil", "fatigue", "Baisse de régime en fin de session",
                    f"{r['label']} de la journée : {r['score']} % de score ({r['n']} parties), contre "
                    f"{ranks[1]['score']} % pour la 1re.",
                    ["Limite tes sessions à 3 parties d'affilée."], ["sessions"]))
                break

    ar = habits.get("after_result", {})
    if "loss" in ar and "win" in ar and ar["loss"]["n"] >= 20 and ar["win"]["n"] >= 20:
        if ar["loss"]["score"] <= ar["win"]["score"] - 8:
            findings.append(_f(
                "conseil", "tilt", "Effet « tilt » après une défaite",
                f"Après une défaite tu marques {ar['loss']['score']} %, après une victoire {ar['win']['score']} %.",
                ["Après une défaite, fais une pause de 5 minutes ou analyse-la avant de relancer."], ["sessions"]))

    bc = basic.get("by_color", {})
    w, b = bc.get("w", {}), bc.get("b", {})
    if w.get("n", 0) >= 20 and b.get("n", 0) >= 20 and w["score"] is not None and b["score"] is not None:
        gap = w["score"] - b["score"]
        if abs(gap) >= 8:
            weak = "Noirs" if gap > 0 else "Blancs"
            findings.append(_f(
                "conseil", "color_gap", f"Écart de niveau avec les {weak}",
                f"Blancs : {w['score']} % · Noirs : {b['score']} %.",
                [f"Concentre ton travail d'ouverture sur ton répertoire avec les {weak}."], ["openings"]))

    tc = basic.get("by_time_class", {}).get(basic.get("main_time_class"), {})
    if tc.get("n", 0) >= 100 and tc.get("elo_start") and tc.get("elo_end") is not None:
        if tc["elo_end"] - tc["elo_start"] < 30:
            findings.append(_f(
                "conseil", "plateau", "Un Elo qui stagne",
                f"{tc['n']} parties pour passer de {tc['elo_start']} à {tc['elo_end']} (pic {tc['elo_peak']}).",
                ["Jouer plus ne suffit pas : remplace une partie sur trois par 15 minutes de puzzles ou d'analyse."],
                ["review", "puzzles_hanging"]))


# ---------------------------------------------------------------------------
FUNDAMENTALS = [
    {"title": "Avant chaque coup : la check-list", "items": [
        "Qu'est-ce que le dernier coup adverse menace ? (prise, échec, fourchette, attaque sur une pièce non protégée)",
        "Échecs, captures, menaces : regarde-les pour l'adversaire, puis pour toi.",
        "Ma case d'arrivée est-elle attaquée ? Mon coup laisse-t-il une pièce sans défense ?",
        "Dernier regard « avec les yeux de l'adversaire » avant de lâcher la pièce.",
    ]},
    {"title": "Ouverture", "items": [
        "Contrôle le centre (pions e4/d4 ou e5/d5), développe les cavaliers puis les fous.",
        "Roque tôt, idéalement avant le 10e coup.",
        "Ne sors pas la dame trop tôt et ne joue pas deux fois la même pièce sans raison.",
        "Relie tes tours, puis cherche un plan (colonne ouverte, pion faible, case forte).",
    ]},
    {"title": "Milieu de partie", "items": [
        "Une pièce non protégée est une pièce en danger : protège-la ou rends-la active.",
        "Motifs à connaître : fourchette, clouage, enfilade, attaque à la découverte, surcharge, déviation.",
        "Améliore ta pièce la moins active quand il n'y a rien de tactique.",
        "En avance de matériel, échange les pièces (pas les pions).",
    ]},
    {"title": "Convertir un avantage", "items": [
        "Simplifie : chaque échange rapproche la victoire quand tu as plus de matériel.",
        "Ne laisse pas de contre-jeu : sécurité du roi d'abord, gains de matériel ensuite.",
        "Contre un roi seul : mats dame + roi et tour + roi, en vérifiant à chaque coup qu'il reste une case (pas de pat).",
    ]},
    {"title": "Finales", "items": [
        "Le roi devient une pièce d'attaque : centralise-le dès que les dames sont parties.",
        "Roi + pion contre roi : le roi devant le pion, et l'opposition.",
        "Règle du carré pour savoir si un pion passé peut être rattrapé.",
        "Les tours se placent derrière les pions passés.",
    ]},
    {"title": "Pendule (parties de 10 minutes)", "items": [
        "Environ 15 à 20 secondes par coup en moyenne : vite à l'ouverture, plus de temps au milieu de partie.",
        "Ne descends pas sous 1 minute dans une position compliquée : simplifie avant.",
    ]},
    {"title": "Méthode de progression", "items": [
        "Puzzles chaque jour (15 minutes), thèmes ciblés sur tes faiblesses.",
        "Analyse chaque défaite : trouve le coup décisif et la règle à retenir.",
        "Joue de temps en temps des cadences plus lentes (15+10) pour ancrer les bons réflexes.",
    ]},
]
