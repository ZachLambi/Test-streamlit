"""
app.py — Dashboard bdd universelle
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Un onglet par source (ISQ/CIMT/Census/BACI), chacun avec ses propres
filtres (années, flux, partenaires, codes HS) — plage d'années, liste de
flux et liste de partenaires calculées dynamiquement depuis les données de
CHAQUE source (pas de valeur codée en dur).

Options d'agrégation : "Tous les produits" (somme tous les HS confondus) et
"Tous les pays" (somme tous les pays, exclut le détail états-Unis pour
éviter le double comptage). Saisir un préfixe HS (ex: 8703) somme
automatiquement tous les HS6 sous ce préfixe en une seule ligne.

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
    lister_flux_disponibles, lister_partenaires, lister_annees_disponibles,
    referentiel_geo, REFERENTIEL_GEO_DISPONIBLE,
    TOUS_PARTENAIRES, TOUS_PRODUITS,
)
from export import exporter_excel, exporter_csv

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


def _libelle_partenaire(code: str, type_partenaire: str, noms: dict[str, str]) -> str:
    nom = noms.get(code, code)
    return f"{nom} — {code} ({type_partenaire})" if nom != code else f"{code} ({type_partenaire})"


def afficher_onglet_source(source: str) -> None:
    """Construit le panneau de filtres + résultats + export pour UNE source,
    entièrement indépendant des autres onglets (état, widgets, résultats)."""

    if NIVEAUX_SOURCES.get(source) == "test" and not MODE_TEST:
        st.warning(
            f"🧪 Données synthétiques (non réelles) — vrai parquet introuvable pour {source}.",
            icon="🧪",
        )

    flux_disponibles = lister_flux_disponibles(source)
    partenaires_disponibles = lister_partenaires(source)
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

        options_partenaires = [TOUS_PARTENAIRES] + [
            _libelle_partenaire(c, t, noms_geo) for c, t in partenaires_disponibles
        ]
        libelle_vers_code = {
            _libelle_partenaire(c, t, noms_geo): c for c, t in partenaires_disponibles
        }
        partenaires_choisis_libelles = st.multiselect(
            "Partenaires", options=options_partenaires,
            key=f"partenaires_{source}",
            help="Vide = tous les partenaires en détail. Filtre sur origine OU "
                 "destination. L'option 🌐 Tous les pays somme tout en excluant "
                 "les états américains (déjà comptés dans l'agrégat pays).",
        )
        agreger_partenaires = TOUS_PARTENAIRES in partenaires_choisis_libelles
        partenaires_choisis = None
        if not agreger_partenaires and partenaires_choisis_libelles:
            partenaires_choisis = [libelle_vers_code[lbl] for lbl in partenaires_choisis_libelles]

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
                    partenaires=partenaires_choisis,
                    hs6_prefixes=codes_hs,
                    agreger_partenaires=agreger_partenaires,
                )
                df = regrouper(
                    df,
                    hs6_prefixes=codes_hs,
                    agreger_produits=agreger_produits,
                    agreger_partenaires=agreger_partenaires,
                )
                if metriques_cochees:
                    df = appliquer_metriques(df, metriques_cochees, cagr_n_annees=cagr_n_annees)
            st.session_state[cle_session] = df

    df = st.session_state.get(cle_session, pd.DataFrame())

    with col_resultats:
        if df.empty:
            st.info("Configure tes filtres à gauche, puis clique **Extraire**.")
            return

        st.subheader(f"Résultats — {len(df):,} lignes ({UNITE_PAR_SOURCE.get(source, '?')})")
        st.dataframe(df, width='stretch', height=420)

        col1, col2, _ = st.columns([1, 1, 2])
        with col1:
            st.download_button(
                "📥 Excel", data=exporter_excel(df, UNITE_PAR_SOURCE),
                file_name=f"extraction_{source.lower()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width='stretch', key=f"dl_xlsx_{source}",
            )
        with col2:
            st.download_button(
                "📥 CSV", data=exporter_csv(df),
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
        afficher_onglet_source(source)