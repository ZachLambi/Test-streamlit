"""Page — Explorateur ISQ (Institut de la statistique du Québec)."""

import streamlit as st
from explorateur_commun import afficher_onglet_directionnel

st.title("ISQ — Institut de la statistique du Québec")
st.caption("Commerce international du Québec, par produit et partenaire (CAD)")

afficher_onglet_directionnel("ISQ")
