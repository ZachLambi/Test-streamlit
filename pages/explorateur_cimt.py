"""Page — Explorateur CIMT (Commerce interprovincial et international, StatCan)."""

import streamlit as st
from explorateur_commun import afficher_onglet_directionnel

st.title("CIMT — Commerce international par province (StatCan)")
st.caption("Toutes provinces canadiennes, par produit et partenaire (CAD)")

afficher_onglet_directionnel("CIMT")
