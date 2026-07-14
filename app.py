"""
app.py — Point d'entrée / routeur du dashboard BDD universelle
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Structure multi-pages (st.Page / st.navigation, 14 juillet 2026) — remplace
l'ancien app.py à onglet unique (st.tabs, un onglet par source). Deux
sections dans la navigation :

  Explorateur de données   — ISQ / CIMT / Census / BACI, filtres génériques
                              (flux, géographie, produits, métriques),
                              extraction à la demande. Logique partagée
                              dans explorateur_commun.py, une page mince
                              par source dans pages/explorateur_*.py.

  Rapports sectoriels      — analyses pré-configurées, pas de filtres
                              génériques (la logique métier est déjà
                              décidée dans le script sous-jacent). Portrait
                              défense pour l'instant (pages/portrait_defense.py,
                              emplacement réservé — intégration du script à
                              venir), d'autres pourront suivre (aérospatiale,
                              énergie... cohérent avec les secteurs déjà
                              couverts par le skill veille-sectorielle-qc).

Ce fichier ne contient plus lui-même l'UI d'un onglet — seulement les
éléments COMMUNS à toutes les pages (config de page, titre global, avis
mode test/référentiel géo), affichés au-dessus du widget de navigation,
puis le routeur proprement dit.

Ce fichier suppose donnees.py, export.py et explorateur_commun.py dans le
même dossier, et un sous-dossier pages/ contenant les scripts de chaque
page.
"""

import streamlit as st

from donnees import MODE_TEST, REFERENTIEL_GEO_DISPONIBLE

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

pages = {
    "Explorateur de données": [
        st.Page("pages/explorateur_isq.py", title="ISQ", icon="🍁"),
        st.Page("pages/explorateur_cimt.py", title="CIMT", icon="🍁"),
        st.Page("pages/explorateur_census.py", title="Census", icon="🇺🇸"),
        st.Page("pages/explorateur_baci.py", title="BACI", icon="🌐"),
    ],
    "Rapports sectoriels": [
        st.Page("pages/portrait_defense.py", title="Portrait défense", icon="🛡️"),
    ],
}

pg = st.navigation(pages, position="sidebar")
pg.run()