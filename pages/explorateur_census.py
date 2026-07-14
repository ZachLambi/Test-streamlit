"""Page — Explorateur US Census Bureau (State Exports/Imports by HS)."""

import streamlit as st
from explorateur_commun import afficher_onglet_directionnel

st.title("Census — US Census Bureau")
st.caption("Commerce international par état américain, par produit et partenaire (USD)")

afficher_onglet_directionnel("CENSUS")
