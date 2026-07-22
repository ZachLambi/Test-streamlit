"""
Page — Rang commercial (QC / États américains)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Intégration réelle d'analyse_rang_commerce_v3.py, PORTÉE : Québec / État(s)
américain(s) seulement. Pays/Pays et Province/Pays viendront une fois
Comtrade réconcilié (voir resume_reconciliation_comtrade.txt).

UI v3 (20 juillet 2026, 2e refonte après retour utilisateur) :
  - Reprend la structure de exporter_excel_formate() du script original
    (section RÉSUMÉ + section Détail par produit avec médailles OR/ARGENT/
    BRONZE) plutôt qu'un classeur de données brutes.
  - st.tabs() DANS LA PAGE (pas la barre latérale) pour séparer Résumé /
    Détail par produit / Tendance / Données complètes.
  - Le graphique à barres a été retiré (jugé peu adapté pour communiquer
    un CLASSEMENT) -- remplacé par un graphique de TENDANCE du rang dans
    le temps (pertinent seulement si plusieurs années sont sélectionnées).
"""

import streamlit as st
import pandas as pd

import donnees as d
from rang_commercial_logique import (
    extraire_provincial, substituer_isq, extraire_pays_pour_etat,
    calculer_rangs, construire_detail_produit, resume_stats, top25_sh4_isq,
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
                help="**DE (Fournisseur)** : QC/provinces (production réelle, CIMT/ISQ) "
                     "vs pays étrangers (Census, pays d'origine réelle) -- bases "
                     "cohérentes des deux côtés, aucun biais connu.\n\n"
                     "**TI (Client)** ⚠️ : QC/provinces (CIMT, importations totales) vs "
                     "exportations de l'état (Census, méthode *Origin of Movement* -- "
                     "attribuées à l'état d'où le bien a commencé son parcours "
                     "d'exportation, souvent un port, PAS nécessairement l'état "
                     "producteur). Un état enclavé sans grand port peut être "
                     "sous-représenté, un état-port sur-représenté -- biais documenté "
                     "par le Census Bureau lui-même (~5 % de la valeur d'exportation "
                     "non attribuable à un état). Non corrigeable avec les données "
                     "disponibles -- à garder en tête pour l'interprétation du côté "
                     "Client seulement.",
            )
        else:
            st.caption("DE et TI sont calculés automatiquement en mode Top25 "
                       "(les codes SH4 sont déterminés séparément en TE et TI).",
                       help="**DE (Fournisseur)** : QC/provinces (production réelle, "
                            "CIMT/ISQ) vs pays étrangers (Census, pays d'origine réelle) "
                            "-- bases cohérentes des deux côtés, aucun biais connu.\n\n"
                            "**TI (Client)** ⚠️ : QC/provinces (CIMT, importations "
                            "totales) vs exportations de l'état (Census, méthode "
                            "*Origin of Movement* -- attribuées à l'état d'où le bien a "
                            "commencé son parcours d'exportation, souvent un port, PAS "
                            "nécessairement l'état producteur). Un état enclavé sans "
                            "grand port peut être sous-représenté, un état-port "
                            "sur-représenté -- biais documenté par le Census Bureau "
                            "lui-même (~5 % de la valeur d'exportation non attribuable "
                            "à un état). Non corrigeable avec les données disponibles "
                            "-- à garder en tête pour l'interprétation du côté Client "
                            "seulement.")
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
                if not df_pays.empty:
                    df_pays = d.convertir_devise(df_pays, devise_rc)

            st.write("Construction du détail par produit...")
            df_detail = construire_detail_produit(df_resultat, df_pays, noms_geo)

            statut.update(label="Extraction terminée", state="complete")

        st.session_state[cle_session] = df_resultat
        st.session_state["rc_df_detail"] = df_detail
        # Gèle la devise utilisée POUR CETTE EXTRACTION -- ne doit plus
        # bouger tant qu'une nouvelle extraction n'est pas lancée, même si
        # le widget "rc_devise" change entre-temps (voir usage de
        # devise_resultat, pas devise_rc, dans tout l'affichage ci-dessous).
        st.session_state["rc_devise_resultat"] = devise_rc

df_affiche = st.session_state.get(cle_session, pd.DataFrame())
df_detail = st.session_state.get("rc_df_detail", pd.DataFrame())
devise_resultat = st.session_state.get("rc_devise_resultat", "Native (par source)")

if df_affiche.empty:
    st.info("Configure tes filtres dans la barre latérale, puis clique **Extraire**.")
else:
    noms_geo = d.referentiel_geo()
    unite = devise_resultat if devise_resultat != "Native (par source)" else ""

    onglet_resume, onglet_detail, onglet_tendance, onglet_donnees = st.tabs(
        ["📋 Résumé", "🔍 Détail par produit", "📈 Tendance", "📄 Données complètes"]
    )

    # ── ONGLET RÉSUMÉ ──────────────────────────────────────────────────────
    with onglet_resume:
        stats = resume_stats(df_detail)
        st.subheader(f"{stats['nb_produits']} produit(s) analysé(s)")

        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Total flux Québec", f"{stats['total_flux']:,.0f} {unite}")
        c2.metric("📊 Rang moyen", stats["rang_moyen"] if stats["rang_moyen"] is not None else "N/D")
        c3.metric("🥇 Rang #1", f"{stats['rang1']} / {stats['nb_total']}")

        c4, c5, c6 = st.columns(3)
        c4.metric("🥈 Rang ≤ 2", f"{stats['rang2']} / {stats['nb_total']}")
        c5.metric("🎯 Rang ≤ 5", f"{stats['rang5']} / {stats['nb_total']}")
        c6.metric("🏅 Rang ≤ 10", f"{stats['rang10']} / {stats['nb_total']}")

    # ── ONGLET DÉTAIL PAR PRODUIT (médailles) ───────────────────────────────
    with onglet_detail:
        if df_detail.empty:
            st.info("Aucun résultat à détailler.")
        else:
            df_aff = df_detail.copy()
            df_aff["Partenaire"] = df_aff["partenaire"].map(lambda c: noms_geo.get(c, c))
            df_aff = df_aff.sort_values("rang_qc")

            def _medaille(rang: int) -> str:
                return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rang, "")

            df_aff.insert(0, "", df_aff["rang_qc"].map(_medaille))
            df_aff = df_aff.rename(columns={
                "hs6": "Code SH4", "annee": "Année", "flux": "Flux",
                "rang_qc": "Rang Québec", "nb_total": "Nb fournisseurs",
                "valeur_qc": f"Flux Québec ({unite})",
                "top_nom": "1er fournisseur/client", "top_valeur": f"Valeur #1 ({unite})",
            })
            colonnes = ["", "Code SH4", "Partenaire", "Année", "Flux", "Rang Québec",
                        "Nb fournisseurs", f"Flux Québec ({unite})",
                        "1er fournisseur/client", f"Valeur #1 ({unite})"]

            st.dataframe(
                df_aff[colonnes], width='stretch', height=420, hide_index=True,
                column_config={
                    f"Flux Québec ({unite})": st.column_config.NumberColumn(format="%,.0f"),
                    f"Valeur #1 ({unite})": st.column_config.NumberColumn(format="%,.0f"),
                },
            )

    # ── ONGLET TENDANCE ───────────────────────────────────────────────────
    with onglet_tendance:
        if len(annees_selectionnees) <= 1:
            st.info("Sélectionne une plage de plusieurs années dans la barre latérale "
                    "pour voir l'évolution du rang dans le temps.")
        elif df_detail.empty:
            st.info("Aucun résultat à afficher.")
        else:
            import plotly.express as px

            df_tendance = df_detail.copy()
            df_tendance["Partenaire"] = df_tendance["partenaire"].map(lambda c: noms_geo.get(c, c))
            df_tendance["Série"] = (
                df_tendance["Partenaire"] + " · SH4 " + df_tendance["hs6"] + " · " + df_tendance["flux"]
            )
            fig = px.line(
                df_tendance.sort_values("annee"), x="annee", y="rang_qc", color="Série",
                markers=True,
                labels={"annee": "Année", "rang_qc": "Rang du Québec (1 = meilleur)"},
                title="Évolution du rang du Québec dans le temps",
            )
            fig.update_yaxes(autorange="reversed")  # rang 1 en haut, plus intuitif
            st.plotly_chart(fig, width='stretch')

    # ── ONGLET DONNÉES COMPLÈTES ───────────────────────────────────────────
    with onglet_donnees:
        df_lisible = df_affiche.copy()
        df_lisible["Province"] = df_lisible["province"].map(lambda c: noms_geo.get(c, c))
        df_lisible["Partenaire"] = df_lisible["partenaire"].map(lambda c: noms_geo.get(c, c))
        colonnes_affichage = ["annee", "flux", "Province", "Partenaire", "hs6", "valeur",
                               "Rang_vs_provinces", "Nb_provinces",
                               "Rang_vs_tous_fournisseurs", "Nb_fournisseurs_total"]
        colonnes_affichage = [c for c in colonnes_affichage if c in df_lisible.columns]

        st.caption(f"{len(df_lisible):,} ligne(s) — inclut chaque province individuellement, "
                   "pas seulement le Québec (pour audit/export).")
        st.dataframe(df_lisible[colonnes_affichage], width='stretch', height=420)

        col1, col2, _ = st.columns([1, 1, 2])
        with col1:
            st.download_button(
                "📥 Excel", data=exporter_excel({"Rang commercial": df_lisible[colonnes_affichage]}, devise_resultat),
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