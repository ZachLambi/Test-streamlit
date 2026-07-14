"""
explorateur_commun.py — Logique partagée de l'explorateur de données
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Extrait de l'ancien app.py monolithique lors du passage à une structure
multi-pages (st.Page / st.navigation) — voir app.py pour le routeur.

Deux modèles d'interface, réutilisés par chaque page pages/explorateur_*.py :
- afficher_onglet_directionnel(source) : ISQ/CIMT/Census — côté A
  (domestique) + côté B (partenaire).
- afficher_onglet_symetrique(source) : BACI — pays-à-pays, deux sélecteurs
  indépendants.

CHANGEMENTS UI (14 juillet 2026, vs l'ancien app.py à onglet unique) :
- Filtres déplacés de la colonne de gauche (st.columns([1, 2.2])) vers
  st.sidebar — les résultats récupèrent toute la largeur principale au
  lieu de ~69%. Cohabite bien avec le widget de navigation (nav en haut
  de la sidebar, filtres en dessous, par page).
- Section "Métriques" repliée dans un st.expander (fermé par défaut) —
  c'est la section la moins consultée à chaque requête, elle n'a plus
  besoin d'occuper de l'espace visuel permanent comme Flux/Géographie/
  Produits.
- Ligne de résumé compacte juste au-dessus du bouton Extraire, pour voir
  d'un coup d'œil la sélection active sans remonter dans chaque section
  (plus utile maintenant que les filtres sont dans la sidebar, donc moins
  visibles en permanence que l'ancienne disposition à deux colonnes).
"""

import streamlit as st
import pandas as pd

from donnees import (
    extraire, regrouper, appliquer_metriques_avec_recul, METRIQUES_DISPONIBLES, UNITE_PAR_SOURCE,
    SOURCES_PARQUET, NIVEAUX_SOURCES, MODE_TEST,
    lister_flux_disponibles, lister_entites_cote, lister_annees_disponibles, codes_hs_par_niveau,
    referentiel_geo, REFERENTIEL_GEO_DISPONIBLE, source_symetrique,
    CATEGORIE_PAYS, CATEGORIE_ETATS,
)
from export import exporter_excel, exporter_csv, mettre_en_forme_principal, mettre_en_forme_metrique, formater_pour_ecran

# Libellé de l'agrégat "Total" du côté domestique, par source — CIMT
# explicitement demandé "Total (Canada)"; Census suit le même principe
# pour la cohérence (pas explicitement demandé, facile à retirer si non désiré).
LIBELLE_TOTAL_COTE_A = {"CIMT": "Total (Canada)", "CENSUS": "Total (États-Unis)"}


def _libelle_partenaire(code: str, type_partenaire: str, noms: dict[str, str]) -> str:
    """Nom seul (repli sur le code si le référentiel géo n'a pas d'entrée
    pour ce code) — pas de suffixe code/type dans l'affichage."""
    return noms.get(code, code)


def _trier_par_nom(entites: list[tuple[str, str]], noms_geo: dict[str, str]) -> list[tuple[str, str]]:
    """Trie une liste de (code, type) par NOM affiché, alphabétique — pas
    par code (l'ordre par défaut de lister_entites_cote), qui ne
    correspond à l'alphabet que par coïncidence."""
    return sorted(entites, key=lambda ct: _libelle_partenaire(ct[0], ct[1], noms_geo).casefold())


TOTAL_PRODUITS = "Total (tous les produits)"
_LIBELLES_NIVEAU_HS = {2: "SH2 (chapitre)", 4: "SH4 (position)", 6: "SH6 (sous-position — détail exact)"}


def _ajouter_codes_hs_colles(cles_par_niveau: dict[int, str], cle_texte: str) -> None:
    """Callback du champ 'coller des codes' — route chaque code vers le
    bon menu (SH2/SH4/SH6) selon SA LONGUEUR en chiffres, pas besoin de
    choisir le menu à la main. Un code d'une longueur non reconnue (pas 2,
    4 ou 6 chiffres) est simplement ignoré plutôt que de deviner où le
    mettre."""
    texte = st.session_state.get(cle_texte, "")
    nouveaux = [c.strip() for c in texte.split(",") if c.strip()]
    if not nouveaux:
        return
    for code in nouveaux:
        cle = cles_par_niveau.get(len(code))
        if cle is None:
            continue
        actuel = st.session_state.get(cle, [])
        if code not in actuel:
            st.session_state[cle] = actuel + [code]
    st.session_state[cle_texte] = ""


def _selecteur_codes_hs(source: str) -> tuple[list[str] | None, bool]:
    """Sélecteur de codes HS à trois niveaux — SH2/SH4/SH6, chacun avec sa
    propre liste de codes réellement présents dans les données de cette
    source (dérivés par troncature, pas une nomenclature codée en dur), et
    dont les sélections se COMBINENT (comme Pays/États) plutôt que de
    s'écraser entre elles au changement de niveau.

    'Total (tous les produits)' est une case à cocher séparée, pas une
    entrée dans un des menus — évite l'ambiguïté "dans quel menu la mettre"
    maintenant qu'il y en a trois.

    Un champ de collage unique route chaque code vers le bon niveau selon
    sa longueur (ex: coller '87,8703,271019' remplit SH2, SH4 et SH6 en un
    coup, chacun dans son propre menu).

    Retourne (codes_hs: list[str]|None, agreger_produits: bool)."""
    codes_par_niveau = codes_hs_par_niveau(source)
    cles_par_niveau = {n: f"hs{n}_{source}" for n in (2, 4, 6)}
    cle_texte = f"hs_texte_{source}"

    agreger_produits = st.checkbox(TOTAL_PRODUITS, key=f"hs_total_{source}")

    codes_choisis: list[str] = []
    for niveau in (2, 4, 6):
        cle = cles_par_niveau[niveau]
        deja_selectionnes = st.session_state.get(cle, [])
        options = codes_par_niveau[niveau] + [
            c for c in deja_selectionnes if c not in codes_par_niveau[niveau]
        ]
        choix = st.multiselect(
            _LIBELLES_NIVEAU_HS[niveau], options=options, key=cle,
        )
        codes_choisis += choix

    st.text_input(
        "Ou coller des codes séparés par virgule (Entrée pour ajouter — "
        "routés automatiquement vers SH2/SH4/SH6 selon leur longueur)",
        key=cle_texte,
        on_change=_ajouter_codes_hs_colles, args=(cles_par_niveau, cle_texte),
    )
    st.caption(
        "Vide = détail complet. Sélectionner un SH2/SH4 somme automatiquement "
        "tous les SH6 sous ce préfixe en une seule ligne. Cocher Total en plus "
        "de codes précis ajoute une ligne de somme complète SANS retirer le "
        "détail des codes choisis."
    )

    return (codes_choisis or None), agreger_produits


def _selecteur_cote_a(source: str, entites_a: list[tuple[str, str]], noms_geo: dict[str, str]):
    """Côté domestique. Retourne (codes: list|None, agreger: bool).
    Si une seule valeur est possible pour cette source (ex: ISQ = Québec
    toujours), n'affiche RIEN — pas de sélecteur pour un choix qui n'existe pas.

    'Total (Canada)'/'Total (États-Unis)' est la PREMIÈRE option d'un seul
    menu (pas une case à cocher séparée ni un choix radio exclusif) — se
    combine avec une sélection précise plutôt que de la remplacer, même
    principe que pour les codes HS."""
    if len(entites_a) <= 1:
        return None, False

    libelle_total = LIBELLE_TOTAL_COTE_A.get(source, "Total")
    entites_triees = _trier_par_nom(entites_a, noms_geo)
    options = [libelle_total] + [_libelle_partenaire(c, t, noms_geo) for c, t in entites_triees]
    libelle_vers_code = {_libelle_partenaire(c, t, noms_geo): c for c, t in entites_triees}

    choix = st.multiselect(
        "Domestique", options=options, key=f"cote_a_{source}",
        help=f"'{libelle_total}' somme tout en une ligne. Se combine avec une "
             "sélection précise ci-dessous plutôt que de la remplacer.",
    )
    agreger = libelle_total in choix
    codes = [libelle_vers_code[lbl] for lbl in choix if lbl != libelle_total]
    return (codes or None), agreger


TOTAL_PAYS = "Total (tous les pays)"


def _selecteur_cote_b(source: str, entites_b: list[tuple[str, str]], noms_geo: dict[str, str]):
    """Côté partenaire. Retourne (codes: list|None, agreger: bool).
    Pays et États sont DEUX menus indépendants dont les sélections se
    combinent (pas un choix exclusif) — États absent si la source n'a
    aucun partenaire de type ETAT_US (ex: Census).

    'Total (tous les pays)' est la PREMIÈRE option du menu PAYS uniquement
    — pas une case à cocher séparée, et pas dupliqué dans le menu États :
    pour le total des États-Unis spécifiquement, sélectionner 'États-Unis'
    directement dans le menu Pays suffit déjà (l'agrégat pays existe comme
    entité à part entière)."""
    pays = [(c, t) for c, t in entites_b if t == "PAYS"]
    etats = [(c, t) for c, t in entites_b if t == "ETAT_US"]
    a_des_etats = len(etats) > 0

    pays_tries = _trier_par_nom(pays, noms_geo)
    options_pays = [TOTAL_PAYS] + [_libelle_partenaire(c, t, noms_geo) for c, t in pays_tries]
    libelle_vers_code_pays = {_libelle_partenaire(c, t, noms_geo): c for c, t in pays_tries}

    choix_pays = st.multiselect(
        CATEGORIE_PAYS, options=options_pays, key=f"cote_b_pays_{source}",
        help=f"'{TOTAL_PAYS}' somme tous les pays en une ligne (exclut les "
             "états, déjà comptés dans l'agrégat pays — évite le double "
             "comptage). Se combine avec une sélection précise plutôt que "
             "de la remplacer.",
    )
    agreger = TOTAL_PAYS in choix_pays
    codes_choisis = [libelle_vers_code_pays[lbl] for lbl in choix_pays if lbl != TOTAL_PAYS]

    if a_des_etats:
        etats_tries = _trier_par_nom(etats, noms_geo)
        options_etats = [_libelle_partenaire(c, t, noms_geo) for c, t in etats_tries]
        libelle_vers_code_etats = {_libelle_partenaire(c, t, noms_geo): c for c, t in etats_tries}
        choix_etats = st.multiselect(
            CATEGORIE_ETATS, options=options_etats, key=f"cote_b_etats_{source}",
            help="Vide = tous les états en détail. Se combine avec la "
                 "sélection de pays ci-dessus (pas exclusif). Pour le total "
                 "des États-Unis, sélectionner 'États-Unis' dans Pays plutôt "
                 "que d'agréger les états ici.",
        )
        codes_choisis += [libelle_vers_code_etats[lbl] for lbl in choix_etats]

    return (codes_choisis or None), agreger


def _modes_axe(agreger: bool, valeurs_precises: list[str] | None) -> list[tuple[str, list[str] | None]]:
    """Détermine les 'modes' actifs pour UN axe (produits ou partenaires
    côté B) : 'total' et/ou 'precis' — non exclusifs, comme demandé. Si
    aucun des deux n'est actif, un seul mode 'detail' (aucun filtre =
    détail complet), pour ne jamais retourner une liste vide."""
    modes: list[tuple[str, list[str] | None]] = []
    if agreger:
        modes.append(("total", None))
    if valeurs_precises:
        modes.append(("precis", valeurs_precises))
    if not modes:
        modes.append(("detail", None))
    return modes


def _extraire_combine(
    source: str, annees, flux,
    partenaires_a=None, agreger_a=False,
    partenaires_b=None, agreger_b=False,
    codes_hs=None, agreger_produits=False,
) -> pd.DataFrame:
    """'Total' n'est PAS exclusif sur les TROIS axes qui l'offrent — côté A
    (domestique), côté B (partenaires, Pays uniquement), et produits (HS).
    Si 'Total' est coché EN MÊME TEMPS qu'une sélection précise sur ce même
    axe, les deux apparaissent dans le résultat plutôt que l'un ou l'autre.

    Implémenté comme le PRODUIT CARTÉSIEN des modes actifs de chaque axe
    (voir _modes_axe) — une extraction+regroupement par combinaison, puis
    concaténation. Jusqu'à 2×2×2=8 combinaisons si les trois axes ont
    Total + précis actifs simultanément — en pratique presque toujours
    beaucoup moins, chaque axe inactif ne comptant que pour 1 mode."""
    modes_a = _modes_axe(agreger_a, partenaires_a)
    modes_b = _modes_axe(agreger_b, partenaires_b)
    modes_hs = _modes_axe(agreger_produits, codes_hs)

    morceaux = []
    for type_a, valeurs_a in modes_a:
        for type_b, valeurs_b in modes_b:
            for type_hs, valeurs_hs in modes_hs:
                df = extraire(
                    sources=[source], annees=annees, flux=flux,
                    partenaires_a=(valeurs_a if type_a == "precis" else None),
                    agreger_a=(type_a == "total"),
                    partenaires_b=(valeurs_b if type_b == "precis" else None),
                    hs6_prefixes=(valeurs_hs if type_hs == "precis" else None),
                )
                df = regrouper(
                    df,
                    hs6_prefixes=(valeurs_hs if type_hs == "precis" else None),
                    agreger_produits=(type_hs == "total"),
                    agreger_a=(type_a == "total"),
                    agreger_b=(type_b == "total"),
                )
                morceaux.append(df)

    if not morceaux:
        return pd.DataFrame()
    return pd.concat(morceaux, ignore_index=True) if len(morceaux) > 1 else morceaux[0]


def _section(titre: str):
    """Bloc visuel délimité — bordure arrondie native de Streamlit
    (st.container(border=True)), avec un titre à l'intérieur. Utilisé pour
    regrouper visuellement les filtres par thème (Flux et période,
    Géographie, Produits) dans la barre latérale."""
    conteneur = st.container(border=True)
    conteneur.markdown(f"**{titre}**")
    return conteneur


def _fragment_resume(codes: list[str] | None, agreger: bool, nom_total: str, nom_detail: str) -> str:
    """Fragment de texte court pour la ligne de résumé — décrit l'état
    d'un axe (Total + N précis / Total seul / N précis / détail complet)
    sans reproduire tous les libellés choisis un par un."""
    if agreger and codes:
        return f"{nom_total} + {len(codes)} précis"
    if agreger:
        return nom_total
    if codes:
        return f"{len(codes)} précis"
    return nom_detail


def _afficher_resume_filtres(
    annees_selectionnees: list[int], flux_cochees: list[str],
    frag_a: str | None, frag_b: str, frag_produits: str,
) -> None:
    """Ligne de résumé compacte affichée juste au-dessus du bouton
    Extraire — utile surtout depuis que les filtres sont dans la sidebar
    (moins visibles en permanence que l'ancienne disposition à deux
    colonnes). Un coup d'œil suffit pour confirmer la sélection active
    sans remonter dans chaque section."""
    morceaux = []
    if annees_selectionnees:
        a_min, a_max = min(annees_selectionnees), max(annees_selectionnees)
        morceaux.append(f"{a_min}-{a_max}" if a_min != a_max else str(a_min))
    if flux_cochees:
        morceaux.append("+".join(flux_cochees))
    if frag_a:
        morceaux.append(frag_a)
    morceaux.append(frag_b)
    morceaux.append(frag_produits)
    st.caption(" · ".join(morceaux))


def afficher_onglet_directionnel(source: str) -> None:
    """ISQ / CIMT / Census — côté A (domestique) + côté B (partenaire).
    Filtres dans la sidebar, résultats en pleine largeur du corps principal."""

    flux_disponibles = lister_flux_disponibles(source)
    entites_a = lister_entites_cote(source, "a")
    entites_b = lister_entites_cote(source, "b")
    annee_min_dispo, annee_max_dispo = lister_annees_disponibles(source)
    noms_geo = referentiel_geo()

    if not flux_disponibles:
        st.error(f"Aucune donnée disponible pour {source}.")
        return

    with st.sidebar:
        with _section("Flux et période"):
            if annee_min_dispo == annee_max_dispo:
                st.caption(f"Année disponible : {annee_min_dispo}")
                annees_selectionnees = [annee_min_dispo]
            else:
                annee_min, annee_max = st.slider(
                    "Années", min_value=annee_min_dispo, max_value=annee_max_dispo,
                    value=(annee_min_dispo, annee_max_dispo),
                    key=f"annees_{source}",
                )
                annees_selectionnees = list(range(annee_min, annee_max + 1))

            flux_cochees = st.multiselect(
                "Flux", options=flux_disponibles, default=flux_disponibles,
                key=f"flux_{source}",
            )

        with _section("Géographie"):
            partenaires_a, agreger_a = _selecteur_cote_a(source, entites_a, noms_geo)
            if len(entites_a) > 1:  # sélecteur "Domestique" réellement affiché ci-dessus
                st.divider()
            partenaires_b, agreger_b = _selecteur_cote_b(source, entites_b, noms_geo)

        with _section("Produits"):
            codes_hs, agreger_produits = _selecteur_codes_hs(source)

        with st.expander("Métriques", expanded=False):
            metriques_cochees = [
                cle for cle, (libelle, _) in METRIQUES_DISPONIBLES.items()
                if st.checkbox(libelle, value=(cle == "variation_annuelle"), key=f"metrique_{cle}_{source}")
            ]
            cagr_n_annees = 5
            if "cagr" in metriques_cochees:
                cagr_n_annees = st.number_input(
                    "CAGR sur combien d'années", min_value=2, max_value=15, value=5,
                    key=f"cagr_n_{source}",
                )

        frag_a = None
        if len(entites_a) > 1:
            frag_a = _fragment_resume(
                partenaires_a, agreger_a, LIBELLE_TOTAL_COTE_A.get(source, "Total"),
                "Détail (toutes entités)",
            )
        frag_b = _fragment_resume(partenaires_b, agreger_b, TOTAL_PAYS, "Détail (tous partenaires)")
        frag_produits = _fragment_resume(codes_hs, agreger_produits, TOTAL_PRODUITS, "Détail HS6 complet")
        _afficher_resume_filtres(annees_selectionnees, flux_cochees, frag_a, frag_b, frag_produits)

        lancer = st.button("Extraire", type="primary", width='stretch', key=f"extraire_{source}")

    cle_session = f"resultat_{source}"

    if lancer:
        if not flux_cochees:
            st.warning("Coche au moins un flux.")
        else:
            with st.spinner("Extraction en cours..."):
                # Si la variation annuelle est demandée, va chercher une année
                # de plus avant la plage choisie — juste pour permettre de
                # calculer la variation de la toute première année
                # sélectionnée. Cette année de recul est retirée du résultat
                # final par appliquer_metriques_avec_recul(), et n'influence
                # jamais le CAGR (calculé séparément, sur la vraie plage).
                annee_min_reelle = min(annees_selectionnees)
                annees_extraction = annees_selectionnees
                if "variation_annuelle" in metriques_cochees:
                    annees_extraction = [annee_min_reelle - 1] + annees_selectionnees

                df = _extraire_combine(
                    source, annees_extraction, flux_cochees,
                    partenaires_a=partenaires_a, agreger_a=agreger_a,
                    partenaires_b=partenaires_b, agreger_b=agreger_b,
                    codes_hs=codes_hs, agreger_produits=agreger_produits,
                )
                if metriques_cochees:
                    df = appliquer_metriques_avec_recul(
                        df, metriques_cochees, annee_min_reelle, cagr_n_annees=cagr_n_annees
                    )
            st.session_state[cle_session] = df

    _afficher_resultats(source, cle_session)


def afficher_onglet_symetrique(source: str) -> None:
    """BACI — pays-à-pays, deux sélecteurs indépendants pour choisir une
    paire. Filtres dans la sidebar, résultats en pleine largeur."""

    flux_disponibles = lister_flux_disponibles(source)
    entites = lister_entites_cote(source, "a")  # a == b pour une source symétrique
    annee_min_dispo, annee_max_dispo = lister_annees_disponibles(source)
    noms_geo = referentiel_geo()

    if not flux_disponibles:
        st.error(f"Aucune donnée disponible pour {source}.")
        return

    with st.sidebar:
        with _section("Flux et période"):
            if annee_min_dispo == annee_max_dispo:
                st.caption(f"Année disponible : {annee_min_dispo}")
                annees_selectionnees = [annee_min_dispo]
            else:
                annee_min, annee_max = st.slider(
                    "Années", min_value=annee_min_dispo, max_value=annee_max_dispo,
                    value=(annee_min_dispo, annee_max_dispo),
                    key=f"annees_{source}",
                )
                annees_selectionnees = list(range(annee_min, annee_max + 1))

            flux_cochees = st.multiselect(
                "Flux", options=flux_disponibles, default=flux_disponibles,
                key=f"flux_{source}",
            )

        with _section("Géographie"):
            entites_triees = _trier_par_nom(entites, noms_geo)
            options = [_libelle_partenaire(c, t, noms_geo) for c, t in entites_triees]
            libelle_vers_code = {_libelle_partenaire(c, t, noms_geo): c for c, t in entites_triees}

            choix_1 = st.multiselect(
                "Pays 1", options=options, key=f"pays1_{source}",
                help="Vide = n'importe quel pays de ce côté.",
            )
            choix_2 = st.multiselect(
                "Pays 2", options=options, key=f"pays2_{source}",
                help="Vide = n'importe quel pays de ce côté. Si les deux listes "
                     "sont remplies, seule la paire exacte est retenue (dans les "
                     "deux sens). Si une seule l'est, tout échange impliquant ce "
                     "pays est retenu.",
            )
            partenaires_1 = [libelle_vers_code[lbl] for lbl in choix_1] or None
            partenaires_2 = [libelle_vers_code[lbl] for lbl in choix_2] or None

        with _section("Produits"):
            codes_hs, agreger_produits = _selecteur_codes_hs(source)

        with st.expander("Métriques", expanded=False):
            metriques_cochees = [
                cle for cle, (libelle, _) in METRIQUES_DISPONIBLES.items()
                if st.checkbox(libelle, value=(cle == "variation_annuelle"), key=f"metrique_{cle}_{source}")
            ]
            cagr_n_annees = 5
            if "cagr" in metriques_cochees:
                cagr_n_annees = st.number_input(
                    "CAGR sur combien d'années", min_value=2, max_value=15, value=5,
                    key=f"cagr_n_{source}",
                )

        frag_geo = f"{len(choix_1) or 'toutes'} × {len(choix_2) or 'toutes'} entité(s)" \
            if (choix_1 or choix_2) else "Toutes les paires"
        frag_produits = _fragment_resume(codes_hs, agreger_produits, TOTAL_PRODUITS, "Détail HS6 complet")
        _afficher_resume_filtres(annees_selectionnees, flux_cochees, None, frag_geo, frag_produits)

        lancer = st.button("Extraire", type="primary", width='stretch', key=f"extraire_{source}")

    cle_session = f"resultat_{source}"

    if lancer:
        if not flux_cochees:
            st.warning("Coche au moins un flux.")
        else:
            with st.spinner("Extraction en cours..."):
                annee_min_reelle = min(annees_selectionnees)
                annees_extraction = annees_selectionnees
                if "variation_annuelle" in metriques_cochees:
                    annees_extraction = [annee_min_reelle - 1] + annees_selectionnees

                df = _extraire_combine(
                    source, annees_extraction, flux_cochees,
                    partenaires_a=partenaires_1, partenaires_b=partenaires_2,
                    codes_hs=codes_hs, agreger_produits=agreger_produits,
                )
                if metriques_cochees:
                    df = appliquer_metriques_avec_recul(
                        df, metriques_cochees, annee_min_reelle, cagr_n_annees=cagr_n_annees
                    )
            st.session_state[cle_session] = df

    _afficher_resultats(source, cle_session)


def _afficher_resultats(source: str, cle_session: str) -> None:
    """Affiche les résultats dans le corps principal (pleine largeur —
    plus de colonne partagée avec les filtres, désormais dans la sidebar)."""
    if NIVEAUX_SOURCES.get(source) == "test" and not MODE_TEST:
        st.warning(
            f"🧪 Données synthétiques (non réelles) — vrai parquet introuvable pour {source}.",
            icon="🧪",
        )

    df = st.session_state.get(cle_session, pd.DataFrame())

    if df.empty:
        st.info("Configure tes filtres dans la barre latérale, puis clique **Extraire**.")
        return

    noms_geo = referentiel_geo()
    avec_variation = "variation_pct" in df.columns
    avec_part_marche = "part_marche_pct" in df.columns
    avec_rang = "rang" in df.columns

    df_principal = mettre_en_forme_principal(df, noms_geo, avec_variation=avec_variation)
    df_part_marche = mettre_en_forme_metrique(df, "part_marche_pct", noms_geo) if avec_part_marche else pd.DataFrame()
    df_rang = mettre_en_forme_metrique(df, "rang", noms_geo) if avec_rang else pd.DataFrame()

    n_groupes = df_principal["Mesure"].eq("Valeur").sum() if "Mesure" in df_principal.columns else len(df_principal)
    st.subheader(f"Résultats — {n_groupes:,} série(s) ({UNITE_PAR_SOURCE.get(source, '?')})")
    st.dataframe(formater_pour_ecran(df_principal), width='stretch', height=420)

    if avec_part_marche:
        st.caption("Part de marché (%) — tableau séparé, une colonne par année")
        st.dataframe(df_part_marche, width='stretch', height=200)
    if avec_rang:
        st.caption("Rang — tableau séparé, une colonne par année")
        st.dataframe(df_rang, width='stretch', height=200)

    tables_excel = {"Extraction": df_principal}
    if avec_part_marche:
        tables_excel["Part de marché"] = df_part_marche
    if avec_rang:
        tables_excel["Rang"] = df_rang

    col1, col2, _ = st.columns([1, 1, 2])
    with col1:
        st.download_button(
            "📥 Excel", data=exporter_excel(tables_excel, UNITE_PAR_SOURCE.get(source, "?")),
            file_name=f"extraction_{source.lower()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width='stretch', key=f"dl_xlsx_{source}",
            help="Part de marché et Rang, s'ils sont cochés, sont sur des feuilles séparées.",
        )
    with col2:
        st.download_button(
            "📥 CSV", data=exporter_csv(df_principal),
            file_name=f"extraction_{source.lower()}.csv",
            mime="text/csv", width='stretch', key=f"dl_csv_{source}",
            help="Tableau principal seulement — Part de marché/Rang disponibles en Excel.",
        )
