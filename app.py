"""
app.py — Dashboard bdd universelle
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Un onglet par source (ISQ/CIMT/Census/BACI). Deux modèles d'interface :

- Sources DIRECTIONNELLES (ISQ/CIMT/Census) : côté A = domestique
  (province/état), côté B = partenaire international. Côté A n'affiche un
  sélecteur que s'il y a plus d'une valeur possible pour cette source (ISQ
  n'en montre pas — Québec toujours implicite ; CIMT montre les provinces
  avec option "Total Canada" ; Census montre les états).
- Source SYMÉTRIQUE (BACI, pays-à-pays) : deux sélecteurs "Pays 1" /
  "Pays 2" indépendants pour choisir n'importe quelle paire à étudier.

Toutes les listes (années, flux, partenaires par côté) sont calculées
dynamiquement depuis les données de CHAQUE source — pas de valeur codée en
dur, pas d'hypothèse sur ce qu'une source "devrait" contenir.

À lancer avec :
    pip install -r requirements.txt
    streamlit run app.py

Ce fichier suppose donnees.py et export.py dans le même dossier.
"""

import streamlit as st
import pandas as pd

from donnees import (
    extraire, regrouper, appliquer_metriques, METRIQUES_DISPONIBLES, UNITE_PAR_SOURCE,
    SOURCES_PARQUET, NIVEAUX_SOURCES, MODE_TEST,
    lister_flux_disponibles, lister_entites_cote, lister_annees_disponibles,
    referentiel_geo, REFERENTIEL_GEO_DISPONIBLE, source_symetrique,
    CATEGORIE_PAYS, CATEGORIE_ETATS, TOUS_PRODUITS,
)
from export import exporter_excel, exporter_csv, mettre_en_forme_large

st.set_page_config(page_title="BDD Universelle", layout="wide")

st.title("Base de données commerciale universelle")
st.caption("ISQ · CIMT · Census · BACI — extraction unifiée, calculs préconfigurés, export prêt à l'emploi")

if MODE_TEST:
    st.info(
        "🧪 Mode test — aucune vraie donnée trouvée, l'app utilise des données "
        "synthétiques pour valider l'interface. Les valeurs affichées ne sont pas réelles.",
        icon="🧪",
    )

if not REFERENTIEL_GEO_DISPONIBLE:
    st.caption(
        "ℹ️ Référentiel géographique non trouvé (referentiel_geo.csv) — "
        "les partenaires s'affichent par code plutôt que par nom."
    )

# Libellé de l'agrégat "Total" du côté domestique, par source — CIMT
# explicitement demandé "Total (Canada)"; Census suit le même principe
# pour la cohérence (pas explicitement demandé, facile à retirer si non désiré).
LIBELLE_TOTAL_COTE_A = {"CIMT": "Total (Canada)", "CENSUS": "Total (États-Unis)"}


def _libelle_partenaire(code: str, type_partenaire: str, noms: dict[str, str]) -> str:
    """Nom seul (repli sur le code si le référentiel géo n'a pas d'entrée
    pour ce code) — pas de suffixe code/type dans l'affichage."""
    return noms.get(code, code)


def _selecteur_cote_a(source: str, entites_a: list[tuple[str, str]], noms_geo: dict[str, str]):
    """Côté domestique. Retourne (codes: list|None, agreger: bool).
    Si une seule valeur est possible pour cette source (ex: ISQ = Québec
    toujours), n'affiche RIEN — pas de sélecteur pour un choix qui n'existe pas."""
    if len(entites_a) <= 1:
        return None, False

    libelle_total = LIBELLE_TOTAL_COTE_A.get(source, "Total")
    mode = st.radio(
        "Domestique", options=[libelle_total, "Choisir précisément"],
        key=f"cote_a_mode_{source}",
    )
    if mode == libelle_total:
        return None, True

    options = [_libelle_partenaire(c, t, noms_geo) for c, t in entites_a]
    libelle_vers_code = {_libelle_partenaire(c, t, noms_geo): c for c, t in entites_a}
    choix = st.multiselect(
        "Choisir précisément", options=options, key=f"cote_a_choix_{source}",
        help="Vide = détail de toutes les entités disponibles.",
    )
    codes = [libelle_vers_code[lbl] for lbl in choix] or None
    return codes, False


def _selecteur_cote_b(source: str, entites_b: list[tuple[str, str]], noms_geo: dict[str, str]):
    """Côté partenaire. Retourne (codes: list|None, agreger: bool).
    Pays et États sont DEUX menus indépendants dont les sélections se
    combinent (pas un choix exclusif) — États absent si la source n'a
    aucun partenaire de type ETAT_US (ex: Census)."""
    pays = [(c, t) for c, t in entites_b if t == "PAYS"]
    etats = [(c, t) for c, t in entites_b if t == "ETAT_US"]
    a_des_etats = len(etats) > 0

    agreger = st.checkbox(
        "Tous les partenaires (somme, exclut le détail des états)",
        key=f"agreger_b_{source}",
        help="Somme tous les pays en une seule ligne — exclut les états, "
             "déjà comptés dans l'agrégat pays (évite le double comptage).",
    )
    if agreger:
        return None, True

    codes_choisis: list[str] = []

    options_pays = [_libelle_partenaire(c, t, noms_geo) for c, t in pays]
    libelle_vers_code_pays = {_libelle_partenaire(c, t, noms_geo): c for c, t in pays}
    choix_pays = st.multiselect(
        CATEGORIE_PAYS, options=options_pays, key=f"cote_b_pays_{source}",
        help="Vide = tous les pays en détail.",
    )
    codes_choisis += [libelle_vers_code_pays[lbl] for lbl in choix_pays]

    if a_des_etats:
        options_etats = [_libelle_partenaire(c, t, noms_geo) for c, t in etats]
        libelle_vers_code_etats = {_libelle_partenaire(c, t, noms_geo): c for c, t in etats}
        choix_etats = st.multiselect(
            CATEGORIE_ETATS, options=options_etats, key=f"cote_b_etats_{source}",
            help="Vide = tous les états en détail. Se combine avec la "
                 "sélection de pays ci-dessus (pas exclusif).",
        )
        codes_choisis += [libelle_vers_code_etats[lbl] for lbl in choix_etats]

    return (codes_choisis or None), False


def afficher_onglet_directionnel(source: str) -> None:
    """ISQ / CIMT / Census — côté A (domestique) + côté B (partenaire)."""

    flux_disponibles = lister_flux_disponibles(source)
    entites_a = lister_entites_cote(source, "a")
    entites_b = lister_entites_cote(source, "b")
    annee_min_dispo, annee_max_dispo = lister_annees_disponibles(source)
    noms_geo = referentiel_geo()

    if not flux_disponibles:
        st.error(f"Aucune donnée disponible pour {source}.")
        return

    col_filtres, col_resultats = st.columns([1, 2.2])

    with col_filtres:
        st.subheader("Filtres")

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

        partenaires_a, agreger_a = _selecteur_cote_a(source, entites_a, noms_geo)
        st.divider()
        partenaires_b, agreger_b = _selecteur_cote_b(source, entites_b, noms_geo)

        st.divider()
        agreger_produits = st.checkbox(TOUS_PRODUITS, key=f"tous_produits_{source}")
        codes_hs_saisis = st.text_input(
            "Codes HS (préfixes séparés par virgule, ex: 8703,27)",
            key=f"hs_{source}",
            disabled=agreger_produits,
            help="Saisir un préfixe (ex: 8703) somme automatiquement tous les "
                 "HS6 sous ce préfixe en une seule ligne — pas un simple filtre. "
                 "Un code HS6 complet (6 chiffres) donne le détail exact de ce produit.",
        )
        codes_hs = None if agreger_produits else (
            [c.strip() for c in codes_hs_saisis.split(",") if c.strip()] or None
        )

        st.divider()
        st.subheader("Métriques")
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

        lancer = st.button("Extraire", type="primary", width='stretch', key=f"extraire_{source}")

    cle_session = f"resultat_{source}"

    if lancer:
        if not flux_cochees:
            st.warning("Coche au moins un flux.")
        else:
            with st.spinner("Extraction en cours..."):
                df = extraire(
                    sources=[source],
                    annees=annees_selectionnees,
                    flux=flux_cochees,
                    partenaires_a=partenaires_a, agreger_a=agreger_a,
                    partenaires_b=partenaires_b, agreger_b=agreger_b,
                    hs6_prefixes=codes_hs,
                )
                df = regrouper(
                    df,
                    hs6_prefixes=codes_hs,
                    agreger_produits=agreger_produits,
                    agreger_a=agreger_a, agreger_b=agreger_b,
                )
                if metriques_cochees:
                    df = appliquer_metriques(df, metriques_cochees, cagr_n_annees=cagr_n_annees)
            st.session_state[cle_session] = df

    _afficher_resultats(source, col_resultats, cle_session)


def afficher_onglet_symetrique(source: str) -> None:
    """BACI — pays-à-pays, deux sélecteurs indépendants pour choisir une paire."""

    flux_disponibles = lister_flux_disponibles(source)
    entites = lister_entites_cote(source, "a")  # a == b pour une source symétrique
    annee_min_dispo, annee_max_dispo = lister_annees_disponibles(source)
    noms_geo = referentiel_geo()

    if not flux_disponibles:
        st.error(f"Aucune donnée disponible pour {source}.")
        return

    col_filtres, col_resultats = st.columns([1, 2.2])

    with col_filtres:
        st.subheader("Filtres")

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

        options = [_libelle_partenaire(c, t, noms_geo) for c, t in entites]
        libelle_vers_code = {_libelle_partenaire(c, t, noms_geo): c for c, t in entites}

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

        st.divider()
        agreger_produits = st.checkbox(TOUS_PRODUITS, key=f"tous_produits_{source}")
        codes_hs_saisis = st.text_input(
            "Codes HS (préfixes séparés par virgule, ex: 8703,27)",
            key=f"hs_{source}",
            disabled=agreger_produits,
            help="Saisir un préfixe (ex: 8703) somme automatiquement tous les "
                 "HS6 sous ce préfixe en une seule ligne — pas un simple filtre.",
        )
        codes_hs = None if agreger_produits else (
            [c.strip() for c in codes_hs_saisis.split(",") if c.strip()] or None
        )

        st.divider()
        st.subheader("Métriques")
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

        lancer = st.button("Extraire", type="primary", width='stretch', key=f"extraire_{source}")

    cle_session = f"resultat_{source}"

    if lancer:
        if not flux_cochees:
            st.warning("Coche au moins un flux.")
        else:
            with st.spinner("Extraction en cours..."):
                df = extraire(
                    sources=[source],
                    annees=annees_selectionnees,
                    flux=flux_cochees,
                    partenaires_a=partenaires_1,
                    partenaires_b=partenaires_2,
                    hs6_prefixes=codes_hs,
                )
                df = regrouper(df, hs6_prefixes=codes_hs, agreger_produits=agreger_produits)
                if metriques_cochees:
                    df = appliquer_metriques(df, metriques_cochees, cagr_n_annees=cagr_n_annees)
            st.session_state[cle_session] = df

    _afficher_resultats(source, col_resultats, cle_session)


def _afficher_resultats(source: str, col_resultats, cle_session: str) -> None:
    if NIVEAUX_SOURCES.get(source) == "test" and not MODE_TEST:
        st.warning(
            f"🧪 Données synthétiques (non réelles) — vrai parquet introuvable pour {source}.",
            icon="🧪",
        )

    df = st.session_state.get(cle_session, pd.DataFrame())

    with col_resultats:
        if df.empty:
            st.info("Configure tes filtres à gauche, puis clique **Extraire**.")
            return

        df_large = mettre_en_forme_large(df, referentiel_geo())

        st.subheader(f"Résultats — {len(df_large):,} lignes ({UNITE_PAR_SOURCE.get(source, '?')})")
        st.dataframe(df_large, width='stretch', height=420)

        col1, col2, _ = st.columns([1, 1, 2])
        with col1:
            st.download_button(
                "📥 Excel", data=exporter_excel(df_large, UNITE_PAR_SOURCE.get(source, "?")),
                file_name=f"extraction_{source.lower()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width='stretch', key=f"dl_xlsx_{source}",
            )
        with col2:
            st.download_button(
                "📥 CSV", data=exporter_csv(df_large),
                file_name=f"extraction_{source.lower()}.csv",
                mime="text/csv", width='stretch', key=f"dl_csv_{source}",
            )


# ═══════════════════════════════════════════════════════════════════════════
# UN ONGLET PAR SOURCE
# ═══════════════════════════════════════════════════════════════════════════

noms_sources = list(SOURCES_PARQUET.keys())
onglets = st.tabs(noms_sources)

for onglet, source in zip(onglets, noms_sources):
    with onglet:
        if source_symetrique(source):
            afficher_onglet_symetrique(source)
        else:
            afficher_onglet_directionnel(source)