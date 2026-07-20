"""
Page — Rang commercial (QC / États américains)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Intégration réelle d'analyse_rang_commerce_v3.py, PORTÉE : Québec / État(s)
américain(s) seulement. Pays/Pays et Province/Pays viendront une fois
Comtrade réconcilié (voir resume_reconciliation_comtrade.txt).

UI (20 juillet 2026, refonte après retour utilisateur -- "juste un classeur"
n'était pas assez lisible) :
  - Sélecteur (produit × état × année × flux) pour choisir QUEL point
    précis visualiser en détail, plutôt que de tout empiler dans un seul
    tableau géant.
  - Cartes de métriques (rang provincial, rang mondial) pour le point
    sélectionné.
  - Graphique à barres du classement complet (provinces + pays), Québec
    mis en évidence par une couleur distincte.
  - Tableau détaillé complet toujours disponible, mais replié par défaut
    (st.expander) -- pour l'export, pas la lecture au premier coup d'œil.
"""

import streamlit as st
import pandas as pd

import donnees as d
from rang_commercial_logique import (
    extraire_provincial, substituer_isq, extraire_pays_pour_etat,
    calculer_rangs, top25_sh4_isq,
)
from export import exporter_excel, exporter_csv

st.title("🏆 Rang commercial — Québec / États américains")
st.caption("Classement du Québec parmi les provinces et l'ensemble des fournisseurs "
           "d'un état américain — CIMT, Census, ISQ")

st.info(
    "Portée actuelle : Québec / État(s) américain(s) seulement. Le classement "
    "Pays/Pays et Province/Pays arrivera une fois la réconciliation Comtrade "
    "terminée.", icon="ℹ️",
)

with st.sidebar:
    with st.container(border=True):
        st.markdown("**Mode**")
        mode = st.radio(
            "Mode", options=["Sélection personnalisée", "Preset Top25"],
            label_visibility="collapsed", key="rc_mode",
        )

    annee_min_dispo, annee_max_dispo = d.lister_annees_disponibles("CIMT")

    with st.container(border=True):
        st.markdown("**Flux et période**")
        if annee_min_dispo == annee_max_dispo:
            st.caption(f"Année disponible : {annee_min_dispo}")
            annees_selectionnees = [annee_min_dispo]
        else:
            annee_min, annee_max = st.slider(
                "Années", min_value=annee_min_dispo, max_value=annee_max_dispo,
                value=(annee_min_dispo, annee_max_dispo), key="rc_annees",
            )
            annees_selectionnees = list(range(annee_min, annee_max + 1))

        if mode == "Sélection personnalisée":
            flux_cochees = st.multiselect(
                "Flux", options=["DE", "TI"], default=["DE", "TI"], key="rc_flux",
            )
        else:
            st.caption("DE et TI sont calculés automatiquement en mode Top25 "
                       "(les codes SH4 sont déterminés séparément en TE et TI).")
            flux_cochees = ["DE", "TI"]

    with st.container(border=True):
        st.markdown("**État(s) américain(s)**")
        entites_etats = [
            (c, t) for c, t in d.lister_entites_cote("CIMT", "b") if t == "ETAT_US"
        ]
        noms_geo = d.referentiel_geo()
        options_etats = sorted([noms_geo.get(c, c) for c, _ in entites_etats])
        libelle_vers_code = {noms_geo.get(c, c): c for c, _ in entites_etats}

        if mode == "Preset Top25":
            choix_etat = st.selectbox(
                "État (un seul en mode Top25)", options=options_etats, key="rc_etat_unique",
            )
            etats_selectionnes = [libelle_vers_code[choix_etat]] if choix_etat else []
        else:
            choix_etats = st.multiselect("État(s)", options=options_etats, key="rc_etats_multi")
            etats_selectionnes = [libelle_vers_code[c] for c in choix_etats]

    codes_sh4_selectionnes = None
    if mode == "Sélection personnalisée":
        with st.container(border=True):
            st.markdown("**Produits (SH4)**")
            codes_par_niveau = d.codes_hs_par_niveau("CIMT")
            cle_sh2, cle_sh4 = "rc_hs2", "rc_hs4"
            deja_sh4 = st.session_state.get(cle_sh4, [])
            options_sh4 = codes_par_niveau[4] + [c for c in deja_sh4 if c not in codes_par_niveau[4]]
            choix_sh2 = st.multiselect("SH2 (chapitre — inclut tout le SH4 en dessous)",
                                        options=codes_par_niveau[2], key=cle_sh2)
            choix_sh4 = st.multiselect("SH4 (position)", options=options_sh4, key=cle_sh4)
            codes_sh4_selectionnes = sorted(set(choix_sh2) | set(choix_sh4)) or None
            st.caption("Au moins un code SH2 ou SH4 requis — pas d'option "
                       "« tous les produits » pour cet outil.")

    with st.container(border=True):
        st.markdown("**Devise d'affichage**")
        devise_rc = st.radio(
            "Devise", options=["USD", "CAD", "Native (par source)"],
            index=0, key="rc_devise", label_visibility="collapsed",
        )

    lancer = st.button("Extraire", type="primary", width='stretch', key="rc_extraire")

cle_session = "rc_resultat"

if lancer:
    erreurs = []
    if not etats_selectionnes:
        erreurs.append("Choisis au moins un état américain.")
    if mode == "Sélection personnalisée" and not codes_sh4_selectionnes:
        erreurs.append("Choisis au moins un code SH2 ou SH4.")
    if mode == "Sélection personnalisée" and not flux_cochees:
        erreurs.append("Coche au moins un flux.")

    if erreurs:
        for e in erreurs:
            st.warning(e)
    else:
        with st.status("Extraction en cours...", expanded=True) as statut:
            if mode == "Preset Top25":
                st.write(f"Détermination des 25 codes SH4 les plus importants pour "
                         f"{noms_geo.get(etats_selectionnes[0], etats_selectionnes[0])} (ISQ, TE+TI)...")
                codes_sh4_selectionnes = top25_sh4_isq(annees_selectionnees, etats_selectionnes[0])
                st.write(f"{len(codes_sh4_selectionnes)} codes retenus : {', '.join(codes_sh4_selectionnes)}")

            st.write("Ventilation provinciale (CIMT)...")
            df_provincial = extraire_provincial(
                annees_selectionnees, flux_cochees, etats_selectionnes, codes_sh4_selectionnes
            )
            st.write("Substitution des valeurs Québec (ISQ)...")
            df_provincial = substituer_isq(
                df_provincial, annees_selectionnees, flux_cochees,
                etats_selectionnes, codes_sh4_selectionnes
            )
            st.write("Fournisseurs étrangers de l'état visé (Census)...")
            df_pays = extraire_pays_pour_etat(
                annees_selectionnees, flux_cochees, etats_selectionnes, codes_sh4_selectionnes
            )
            st.write("Calcul des classements...")
            df_resultat = calculer_rangs(df_provincial, df_pays)

            if devise_rc != "Native (par source)" and not df_resultat.empty:
                df_resultat = d.convertir_devise(df_resultat, devise_rc)

            statut.update(label="Extraction terminée", state="complete")

        st.session_state[cle_session] = df_resultat
        st.session_state["rc_df_pays"] = df_pays

df_affiche = st.session_state.get(cle_session, pd.DataFrame())
df_pays_affiche = st.session_state.get("rc_df_pays", pd.DataFrame())

if df_affiche.empty:
    st.info("Configure tes filtres dans la barre latérale, puis clique **Extraire**.")
else:
    noms_geo = d.referentiel_geo()
    df_lisible = df_affiche.copy()
    df_lisible["Province"] = df_lisible["province"].map(lambda c: noms_geo.get(c, c))
    df_lisible["Partenaire"] = df_lisible["partenaire"].map(lambda c: noms_geo.get(c, c))

    # ── Sélecteur du point précis à visualiser en détail ─────────────────
    df_qc = df_lisible[df_lisible["province"] == "PQC"]
    if df_qc.empty:
        st.warning("Aucune ligne Québec dans ce résultat — impossible d'afficher le détail visuel, "
                   "mais le tableau complet reste disponible plus bas.")
    else:
        st.subheader("Détail d'un point précis")
        combos = (df_qc[["Partenaire", "hs6", "annee", "flux"]]
                  .drop_duplicates().sort_values(["Partenaire", "hs6", "annee", "flux"]))
        libelles_combos = [
            f"{r.Partenaire} · SH4 {r.hs6} · {r.annee} · {r.flux}" for r in combos.itertuples()
        ]
        choix_combo = st.selectbox("Point à visualiser", options=libelles_combos, key="rc_combo_detail")
        idx_combo = libelles_combos.index(choix_combo)
        partenaire_sel, hs4_sel, annee_sel, flux_sel = combos.iloc[idx_combo][
            ["Partenaire", "hs6", "annee", "flux"]
        ]

        ligne_qc = df_qc[
            (df_qc["Partenaire"] == partenaire_sel) & (df_qc["hs6"] == hs4_sel) &
            (df_qc["annee"] == annee_sel) & (df_qc["flux"] == flux_sel)
        ].iloc[0]
        code_partenaire_sel = ligne_qc["partenaire"]  # code brut, pas le libellé -- pour filtrer les données

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Rang provincial", f"{int(ligne_qc['Rang_vs_provinces'])} / {int(ligne_qc['Nb_provinces'])}")
        col2.metric("Rang mondial (provinces + pays)",
                    f"{int(ligne_qc['Rang_vs_tous_fournisseurs'])} / {int(ligne_qc['Nb_fournisseurs_total'])}")
        col3.metric("Valeur Québec", f"{ligne_qc['valeur']:,.0f} {devise_rc if devise_rc != 'Native (par source)' else ''}")
        col4.metric("Concurrents", f"{int(ligne_qc['Nb_fournisseurs_total']) - 1}")

        # ── Graphique à barres : classement complet, Québec en évidence ──
        masque_groupe = (
            (df_lisible["partenaire"] == code_partenaire_sel) & (df_lisible["hs6"] == hs4_sel) &
            (df_lisible["annee"] == annee_sel) & (df_lisible["flux"] == flux_sel)
        )
        provinces_groupe = df_lisible[masque_groupe][["Province", "valeur"]].rename(columns={"Province": "Entité"})

        pays_groupe = pd.DataFrame()
        if not df_pays_affiche.empty:
            masque_pays = (
                (df_pays_affiche["partenaire"] == code_partenaire_sel) & (df_pays_affiche["hs6"] == hs4_sel) &
                (df_pays_affiche["annee"] == annee_sel) & (df_pays_affiche["flux"] == flux_sel)
            )
            df_pays_sel = df_pays_affiche[masque_pays].copy()
            if not df_pays_sel.empty:
                colonne_pays = "origine" if flux_sel == "DE" else "destination"
                df_pays_sel["Entité"] = df_pays_sel[colonne_pays].map(lambda c: noms_geo.get(c, c))
                pays_groupe = df_pays_sel[["Entité", "valeur"]]

        df_graphique = pd.concat([provinces_groupe, pays_groupe], ignore_index=True)
        df_graphique = df_graphique.sort_values("valeur", ascending=True).tail(15)  # top 15 pour rester lisible
        df_graphique["Couleur"] = df_graphique["Entité"].apply(
            lambda e: "Québec" if e == "Québec" else "Autre"
        )

        import plotly.express as px
        fig = px.bar(
            df_graphique, x="valeur", y="Entité", orientation="h",
            color="Couleur", color_discrete_map={"Québec": "#1f77b4", "Autre": "#d3d3d3"},
            labels={"valeur": f"Valeur ({devise_rc})", "Entité": ""},
            title=f"Classement — {partenaire_sel}, SH4 {hs4_sel}, {annee_sel}, {flux_sel} (top 15 affichés)",
        )
        fig.update_layout(showlegend=False, height=450)
        st.plotly_chart(fig, width='stretch')

    # ── Tableau complet, replié par défaut ────────────────────────────────
    with st.expander(f"Tableau détaillé complet — {len(df_lisible):,} ligne(s)"):
        colonnes_affichage = ["annee", "flux", "Province", "Partenaire", "hs6", "valeur",
                               "Rang_vs_provinces", "Nb_provinces",
                               "Rang_vs_tous_fournisseurs", "Nb_fournisseurs_total"]
        colonnes_affichage = [c for c in colonnes_affichage if c in df_lisible.columns]
        st.dataframe(df_lisible[colonnes_affichage], width='stretch', height=420)

        col1, col2, _ = st.columns([1, 1, 2])
        with col1:
            st.download_button(
                "📥 Excel", data=exporter_excel({"Rang commercial": df_lisible[colonnes_affichage]}, devise_rc),
                file_name="rang_commercial_qc_etats.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width='stretch', key="rc_dl_xlsx",
            )
        with col2:
            st.download_button(
                "📥 CSV", data=exporter_csv(df_lisible[colonnes_affichage]),
                file_name="rang_commercial_qc_etats.csv", mime="text/csv",
                width='stretch', key="rc_dl_csv",
            )
