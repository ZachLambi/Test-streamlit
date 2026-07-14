"""
Page — Rang commercial (emplacement réservé)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTÉGRATION PAS ENCORE FAITE — cette page réserve la place et esquisse la
forme prévue (14 juillet 2026), à partir de la lecture de
analyse_rang_commerce_v3.py. Aucune logique du script n'est reprise ici,
volontairement — juste la structure d'entrées/sorties pour que la place
soit prête le jour où l'intégration commence.

Contrairement à Portrait défense (entièrement pré-configuré, aucune entrée
utilisateur), ce script a une vraie logique conversationnelle à 4
questions (demander_flux, demander_annees, demander_codes_sh4,
demander_partenaires) — donc cette page AURA des contrôles utilisateur,
mais pas les mêmes que l'explorateur générique (pas de côté A/côté B/HS à
la ISQ/CIMT — la logique de rang/part de marché est spécifique à ce script).

Deux modes distincts identifiés dans le script, prévus comme deux onglets
ou un sélecteur de mode sur cette page :

  1. Analyse complète (run()) — 4 entrées séquentielles :
       - Flux : Exportations / Importations / Les deux
       - Années : plage 1990-présent
       - Codes SH4 : un ou plusieurs codes à 4 chiffres
       - Partenaire(s) : État(s) américain(s) / Pays / Région(s) ou bloc(s)
         commercial(aux) / Tous les pays
     Sources croisées selon le type de partenaire : ISED (toujours),
     US Census Bureau API (si état américain), UN Comtrade API (si pays
     étranger), avec substitution ISQ. Sortie : Excel formaté avec rangs
     et parts de marché (exporter_excel_formate).

  2. Preset "Top25" (run_top25()) — entrées minimales (années + UN SEUL
     partenaire, pas de codes SH4 ni de flux à saisir) : détermine
     automatiquement les 25 premiers codes SH4 en exports ET en imports
     via un scrape ISQ (searchType=Top25_4), puis lance l'analyse complète
     pour chaque flux séparément. Produit 2 fichiers Excel (exports,
     imports). Si le partenaire est un état américain, ajoute aussi un
     tableau de commerce bilatéral Québec ↔ TOUS les états (rang, part de
     marché) — tableau bonus spécifique à ce cas.

Étant donné le volume de requêtes HTTP en direct (ISED + Census/Comtrade +
ISQ, potentiellement plusieurs par code SH4 × partenaire), cette page
devra vraisemblablement afficher une progression (comme le spinner déjà
utilisé dans l'explorateur, mais probablement avec un détail par étape
étant donné les temps d'exécution plus longs qu'une requête DuckDB locale).
"""

import streamlit as st

st.title("🏆 Rang commercial")
st.caption("Rang et part de marché du Canada/Québec chez ses partenaires commerciaux — ISED, Census, Comtrade, ISQ")

st.info(
    "**Intégration en cours.** Cette page réserve la place dans la navigation — "
    "le script `analyse_rang_commerce_v3.py` (actuellement exécuté séparément "
    "en Colab) sera branché ici dans une prochaine passe.",
    icon="🚧",
)

with st.container(border=True):
    st.markdown("**Forme prévue une fois branché — deux modes**")
    st.markdown(
        "**1. Analyse complète**\n"
        "- Flux : Exportations / Importations / Les deux\n"
        "- Années\n"
        "- Codes SH4 (un ou plusieurs)\n"
        "- Partenaire(s) : États américains / Pays / Régions-blocs / Tous les pays\n"
        "- Sortie : Excel formaté avec rangs et parts de marché\n"
    )
    st.markdown(
        "**2. Preset Top25**\n"
        "- Années + un seul partenaire (pas de codes SH4 à saisir — "
        "déterminés automatiquement via l'ISQ)\n"
        "- Sortie : 2 fichiers Excel (exports, imports) + tableau bilatéral "
        "tous états si le partenaire est un état américain\n"
    )
    st.caption(
        "Requêtes en direct (ISED, Census/Comtrade, ISQ) — temps d'exécution "
        "plus long qu'une requête DuckDB locale, affichage de progression à "
        "prévoir."
    )
