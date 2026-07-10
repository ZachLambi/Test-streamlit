"""
app.py — Dashboard bdd universelle
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Panneau d'extraction unique pour les 4 sources (ISQ/CIMT/Census/BACI),
métriques calculées à la volée (variation annuelle, CAGR, part de marché,
rang), export Excel formaté ou CSV.

À lancer dans Colab avec :
    !pip install streamlit duckdb pyarrow openpyxl -q
    !wget -q -O - ipv4.icanhazip.com   # récupérer l'IP pour le tunnel
    !streamlit run app.py & npx localtunnel --port 8501
(ou toute autre méthode de tunnel habituelle — ngrok, etc.)

Ce fichier suppose donnees.py et export.py dans le même dossier.
"""

import streamlit as st
import pandas as pd

from donnees import extraire, appliquer_metriques, METRIQUES_DISPONIBLES, UNITE_PAR_SOURCE, SOURCES_PARQUET
from export import exporter_excel, exporter_csv

st.set_page_config(page_title="BDD Universelle — MRIF", layout="wide")

st.title("Base de données commerciale universelle")
st.caption("ISQ · CIMT · Census · BACI — extraction unifiée, calculs préconfigurés, export prêt à l'emploi")


# ═══════════════════════════════════════════════════════════════════════════
# BARRE LATÉRALE — PANNEAU D'EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("Extraction")

    sources_cochees = st.multiselect(
        "Sources", options=list(SOURCES_PARQUET.keys()), default=["ISQ"],
        help="Plusieurs sources cochées = résultats affichés côte à côte, "
             "PAS additionnés (unités différentes selon la source — voir note plus bas).",
    )

    annee_min, annee_max = st.slider(
        "Années", min_value=2011, max_value=2025, value=(2019, 2025),
    )
    annees_selectionnees = list(range(annee_min, annee_max + 1))

    flux_cochees = st.multiselect(
        "Flux", options=["DE", "TI", "TE"], default=["TE"],
        help="DE = domestique-export (Québec/province vers l'international) · "
             "TI = importation · TE = exportation totale",
    )

    partenaires_saisis = st.text_input(
        "Partenaires (codes séparés par virgule, ex: C9,C528)",
        help="Filtre sur origine OU destination — peu importe le sens du flux. "
             "Recherche par nom à venir; pour l'instant, codes du référentiel géo.",
    )
    partenaires = [p.strip() for p in partenaires_saisis.split(",") if p.strip()] or None

    codes_hs_saisis = st.text_input(
        "Codes HS (préfixes séparés par virgule, ex: 8703,27)",
        help="Un préfixe HS2 (ex: 27) inclut tous les HS6 qui commencent par ces chiffres.",
    )
    codes_hs = [c.strip() for c in codes_hs_saisis.split(",") if c.strip()] or None

    st.divider()
    st.header("Métriques")

    metriques_cochees = [
        cle for cle, (libelle, _) in METRIQUES_DISPONIBLES.items()
        if st.checkbox(libelle, value=(cle == "variation_annuelle"), key=f"metrique_{cle}")
    ]

    cagr_n_annees = 5
    if "cagr" in metriques_cochees:
        cagr_n_annees = st.number_input(
            "CAGR sur combien d'années", min_value=2, max_value=15, value=5,
        )

    lancer = st.button("Extraire", type="primary", width='stretch')


# ═══════════════════════════════════════════════════════════════════════════
# ZONE PRINCIPALE — RÉSULTATS
# ═══════════════════════════════════════════════════════════════════════════

if not lancer and "derniere_extraction" not in st.session_state:
    st.info("Configure ton extraction dans le panneau de gauche, puis clique **Extraire**.")
    st.stop()

if lancer:
    if not sources_cochees:
        st.warning("Coche au moins une source.")
        st.stop()

    with st.spinner("Extraction en cours..."):
        df = extraire(
            sources=sources_cochees,
            annees=annees_selectionnees,
            flux=flux_cochees or None,
            partenaires=partenaires,
            hs6_prefixes=codes_hs,
        )
        if metriques_cochees:
            df = appliquer_metriques(df, metriques_cochees, cagr_n_annees=cagr_n_annees)

    st.session_state["derniere_extraction"] = df
    st.session_state["dernieres_metriques"] = metriques_cochees

df = st.session_state.get("derniere_extraction", pd.DataFrame())

if df.empty:
    st.warning("Aucune donnée pour cette combinaison de filtres.")
    st.stop()

# Note sur les unités — toujours visible quand plusieurs sources sont affichées
sources_presentes = df["source"].unique().tolist()
if len(sources_presentes) > 1:
    note_unites = " · ".join(f"**{s}** en {UNITE_PAR_SOURCE.get(s, '?')}" for s in sources_presentes)
    st.warning(
        f"Sources en unités différentes, non additionnées : {note_unites}. "
        "Compare les tendances, pas les totaux bruts entre sources."
    )

st.subheader(f"Résultats — {len(df):,} lignes")
st.dataframe(df, width='stretch', height=450)

# ── Export ────────────────────────────────────────────────────────────────
col1, col2, _ = st.columns([1, 1, 3])
with col1:
    st.download_button(
        "📥 Télécharger en Excel",
        data=exporter_excel(df, UNITE_PAR_SOURCE),
        file_name="extraction_bdd_universelle.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width='stretch',
    )
with col2:
    st.download_button(
        "📥 Télécharger en CSV",
        data=exporter_csv(df),
        file_name="extraction_bdd_universelle.csv",
        mime="text/csv",
        width='stretch',
    )
