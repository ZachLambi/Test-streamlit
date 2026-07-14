"""
Page — Portrait défense (emplacement réservé)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTÉGRATION PAS ENCORE FAITE — cette page réserve la place et esquisse la
forme prévue (14 juillet 2026), pour que la structure de navigation soit
déjà en place quand Portrait_defense_commerce.py sera branché.

Contrairement à l'explorateur (pages/explorateur_*.py), cette page N'AURA
PAS de sélecteurs côté A/côté B/HS génériques — la logique (classification
des produits défense en MILITAIRE/D-U aéro/D-U non aéro, rapprochement
ISED+ISQ+BACI+Comtrade, rangs de fournisseurs mondiaux, ventilation
provinciale) est déjà décidée dans le script, pas à reconfigurer par
l'utilisateur à chaque requête. UI prévue, minimale :
  - Plage d'années (peut-être fixe/glissante selon dispo des 4 sources)
  - Bouton "Générer le portrait"
  - Tableaux clés affichés à l'écran (mêmes sections que l'Excel produit
    aujourd'hui par le script : rangs mondiaux, ventilation provinciale)
  - Export Excel formaté — même fichier que le script produit déjà en
    Colab, généré ici directement dans l'app plutôt qu'en local
"""

import streamlit as st

st.title("🛡️ Portrait défense")
st.caption("Commerce international des produits de défense — ISED, ISQ, BACI, Comtrade")

st.info(
    "**Intégration en cours.** Cette page réserve la place dans la navigation — "
    "le script `Portrait_defense_commerce.py` (actuellement exécuté séparément "
    "en Colab) sera branché ici dans une prochaine passe.",
    icon="🚧",
)

with st.container(border=True):
    st.markdown("**Forme prévue une fois branché**")
    st.markdown(
        "- Plage d'années\n"
        "- Bouton **Générer le portrait** (pas de filtres génériques — la "
        "classification des produits défense et le rapprochement multi-sources "
        "sont déjà décidés dans le script)\n"
        "- Tableaux clés à l'écran : rangs de fournisseurs mondiaux, "
        "ventilation provinciale\n"
        "- Export Excel formaté, même contenu que le script produit "
        "aujourd'hui"
    )
