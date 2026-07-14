"""Page — Explorateur BACI (CEPII, commerce mondial pays-à-pays)."""

import streamlit as st
from explorateur_commun import afficher_onglet_symetrique

st.title("BACI — Commerce mondial pays-à-pays (CEPII)")
st.caption("N'importe quelle paire de pays, par produit (milliers USD)")

afficher_onglet_symetrique("BACI")
