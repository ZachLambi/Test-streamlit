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

import html as _html

import streamlit as st
import pandas as pd

import donnees as d
from rang_commercial_logique import (
    calculer_rangs, construire_detail_produit, construire_top10_produit,
    resume_stats, top25_sh4_isq, top_produits_isq, extraire_et_classer,
    classement_commerce_total, agreger_categorie, CATEGORIES_FIXES,
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

# Fond légèrement plus foncé que le blanc par défaut pour le container des
# stats de rang (Rang 1 / Rang ≤ 3 / Rang moyen) -- but "outlined" visuellement
# du reste de l'onglet. Ciblé par préfixe de clé (rc_stats_rang_DE /
# rc_stats_rang_TI, un par flux/onglet) via [class*=...] plutôt qu'une classe
# exacte, pour couvrir les deux onglets Fournisseur/Client avec une seule règle.
st.markdown(
    """
    <style>
    div[class*="st-key-rc_stats_rang_"] {
        background-color: rgba(120, 130, 145, 0.16);
        border-radius: 0.6rem;
        padding: 0.9rem 1rem 0.3rem 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


_COULEURS_MEDAILLE = {1: ("#d4af37", "#ffffff"), 2: ("#9aa1ac", "#ffffff"), 3: ("#b08d57", "#ffffff")}


_COULEUR_HIGHLIGHT = "#1d6fd6"  # bleu -- QC dans les top10, ou #1 dans le top25 produits
_ICONE_HIGHLIGHT = "⚜️"


def _html_leaderboard(lignes: list[dict], unite: str, libelle_colonne: str) -> str:
    """Rendu HTML type 'site web' (liste/leaderboard), réutilisé pour le
    top 10 par produit ET le top 25 produits -- remplace le st.dataframe,
    jugé trop lourd (mini-tableur avec en-têtes/scrollbar) pour une liste
    qu'on scanne d'un coup d'œil plutôt qu'on trie/exporte.

    Chaque élément de `lignes` est un dict :
      rang (int), titre (str), valeur (float),
      sous_titre (str, optionnel), highlight (bool, optionnel).
    Une ligne 'highlight' ressort par un fond bleu teinté + bordure gauche +
    icône ⚜️, pas seulement le texte -- pour rester visible même hors podium."""
    entete = (
        '<div style="display:flex; align-items:center; padding:0.2rem 0.6rem; '
        'font-size:0.72rem; color:#8a909c; text-transform:uppercase; letter-spacing:0.03em;">'
        '<div style="flex:0 0 28px;"></div>'
        f'<div style="flex:1; margin-left:0.7rem;">{_html.escape(libelle_colonne)}</div>'
        f'<div>Valeur ({_html.escape(unite) if unite else "native"})</div>'
        '</div>'
    )
    blocs = [entete]
    for l in lignes:
        rang = int(l["rang"])
        titre, valeur = l["titre"], l["valeur"]
        sous_titre = l.get("sous_titre")
        highlight = bool(l.get("highlight", False))

        bg_badge, fg_badge = _COULEURS_MEDAILLE.get(rang, ("#e4e7ec", "#5b6270"))
        fond_ligne = (f"background:{_COULEUR_HIGHLIGHT}14; border-left:3px solid {_COULEUR_HIGHLIGHT};"
                      if highlight else "border-left:3px solid transparent;")
        poids = "700" if highlight else "400"
        titre_affiche = (f"{_ICONE_HIGHLIGHT} " if highlight else "") + _html.escape(str(titre))
        valeur_fmt = f"{valeur:,.0f}".replace(",", "\u202f")

        bloc_titre = f'<div style="font-weight:{poids};">{titre_affiche}</div>'
        if sous_titre:
            bloc_titre += (f'<div style="font-size:0.72rem; color:#8a909c; margin-top:0.05rem;">'
                           f'{_html.escape(str(sous_titre))}</div>')

        blocs.append(
            '<div style="display:flex; align-items:center; padding:0.4rem 0.6rem; '
            f'{fond_ligne} border-radius:0.3rem;">'
            f'<div style="flex:0 0 28px; height:28px; border-radius:50%; background:{bg_badge}; '
            f'color:{fg_badge}; display:flex; align-items:center; justify-content:center; '
            f'font-size:0.78rem; font-weight:700; flex-shrink:0; align-self:flex-start; margin-top:0.1rem;">{rang}</div>'
            f'<div style="flex:1; margin-left:0.7rem;">{bloc_titre}</div>'
            f'<div style="font-variant-numeric:tabular-nums; font-weight:{poids}; white-space:nowrap;">{valeur_fmt}</div>'
            '</div>'
        )
    return '<div style="display:flex; flex-direction:column; gap:0.15rem;">' + "".join(blocs) + "</div>"


def _afficher_bloc_flux(flux_val: str, prefixe: str, df_affiche: pd.DataFrame,
                         df_detail: pd.DataFrame, df_top10: pd.DataFrame, unite: str,
                         annees_selectionnees: list[int], noms_geo: dict,
                         devise_resultat: str) -> None:
    """Affiche les 4 sous-onglets (Résumé/Détail/Tendance/Données) pour UN
    SEUL sens de flux (DE=Fournisseur ou TI=Client) -- appelée une fois par
    onglet de haut niveau, sur les mêmes df_affiche/df_detail/df_top10
    filtrés."""
    df_flux = df_affiche[df_affiche["flux"] == flux_val] if not df_affiche.empty else df_affiche
    df_detail_flux = df_detail[df_detail["flux"] == flux_val] if not df_detail.empty else df_detail
    df_top10_flux = df_top10[df_top10["flux"] == flux_val] if not df_top10.empty else df_top10

    if df_flux.empty:
        st.info("Aucun résultat pour ce sens de flux — vérifie qu'il est coché "
                 "dans la barre latérale.")
        return

    onglet_resume, onglet_detail, onglet_proportions, onglet_donnees = st.tabs(
        ["📋 Top 25", "🔍 Détail par produit", "🥧 Proportions", "📄 Données complètes"]
    )

    # ── ONGLET RÉSUMÉ ──────────────────────────────────────────────────────
    with onglet_resume:
        stats = resume_stats(df_detail_flux)
        st.subheader(f"{stats['nb_produits']} produit(s) analysé(s)")

        # Total flux Québec SEUL, pleine largeur, rien à côté -- pour être
        # certain que le montant ne soit jamais tronqué/"cropped".
        st.metric("💰 Total flux Québec", f"{stats['total_flux']:,.0f} {unite}")

        with st.container(key=f"rc_stats_rang_{prefixe}", border=True):
            c1, c2, c3 = st.columns(3)
            c1.metric("🥇 Rang 1", f"{stats['rang1']} / {stats['nb_total']}")
            c2.metric("🎯 Rang ≤ 3", f"{stats['rang3']} / {stats['nb_total']}")
            c3.metric("📊 Rang moyen", stats["rang_moyen"] if stats["rang_moyen"] is not None else "N/D")

        # Top 25 produits -- même UI liste que le top 10 par produit (badge
        # de rang, ⚜️ bleu sur les produits où le Québec est #1), à la place
        # de l'ancien tableau dataframe. Triés par rang_qc (comme avant),
        # pas par valeur -- un produit où QC est #1 ressort en premier.
        with st.container(key=f"rc_top25_{prefixe}", border=True):
            if df_detail_flux.empty:
                st.info("Aucun résultat à détailler.")
            else:
                df_tri = df_detail_flux.sort_values("rang_qc").copy()
                df_tri["Partenaire"] = df_tri["partenaire"].map(lambda c: noms_geo.get(c, c))
                plusieurs_partenaires_resume = df_tri["Partenaire"].nunique() > 1

                lignes_top25 = []
                for _, r in df_tri.iterrows():
                    titre = f"SH4 {r['hs6']}"
                    if plusieurs_partenaires_resume:
                        titre += f" · {r['Partenaire']}"
                    sous_titre = (f"1er : {r['top_nom']} ({r['top_valeur']:,.0f} {unite}) "
                                  f"· {r['nb_total']} au total")
                    lignes_top25.append({
                        "rang": r["rang_qc"], "titre": titre, "valeur": r["valeur_qc"],
                        "sous_titre": sous_titre, "highlight": r["rang_qc"] == 1,
                    })
                st.markdown(
                    _html_leaderboard(lignes_top25, unite, "Produit"), unsafe_allow_html=True
                )

                st.caption("Format du fichier téléchargé à finaliser — export brut pour l'instant.")
                col_dl1, col_dl2, _ = st.columns([1, 1, 2])
                with col_dl1:
                    st.download_button(
                        "📥 Top 25 produits — Excel",
                        data=exporter_excel({"Top produits": df_tri}, devise_resultat),
                        file_name=f"rang_commercial_top_produits_{prefixe}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        width='stretch', key=f"rc_dl_top25_xlsx_{prefixe}",
                    )
                with col_dl2:
                    st.download_button(
                        "📥 Top 25 produits — CSV",
                        data=exporter_csv(df_tri),
                        file_name=f"rang_commercial_top_produits_{prefixe}.csv", mime="text/csv",
                        width='stretch', key=f"rc_dl_top25_csv_{prefixe}",
                    )

    # ── ONGLET DÉTAIL PAR PRODUIT (top 10 empilés, un container par SH4) ────
    with onglet_detail:
        if df_top10_flux.empty:
            st.info("Aucun résultat à détailler.")
        else:
            groupes = df_top10_flux[["partenaire", "hs6", "annee"]].drop_duplicates()
            plusieurs_partenaires = groupes["partenaire"].nunique() > 1
            plusieurs_annees = groupes["annee"].nunique() > 1
            # Ordre croissant de code SH4 (ex : 1201, 1345, 3452...).
            groupes = groupes.sort_values(["hs6", "annee", "partenaire"])

            st.caption(f"{len(groupes)} produit(s) — top {min(10, int(df_top10_flux['rang'].max()))} "
                       "fournisseurs/clients par produit, Québec ⚜️ mis en évidence.")

            col_dl1, col_dl2, _ = st.columns([1, 1, 2])
            df_top10_export = df_top10_flux.copy()
            df_top10_export["Partenaire"] = df_top10_export["partenaire"].map(lambda c: noms_geo.get(c, c))
            with col_dl1:
                st.download_button(
                    "📥 Top 10 par produit — Excel",
                    data=exporter_excel({"Top 10 par produit": df_top10_export}, devise_resultat),
                    file_name=f"rang_commercial_top10_par_produit_{prefixe}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width='stretch', key=f"rc_dl_top10_xlsx_{prefixe}",
                )
            with col_dl2:
                st.download_button(
                    "📥 Top 10 par produit — CSV",
                    data=exporter_csv(df_top10_export),
                    file_name=f"rang_commercial_top10_par_produit_{prefixe}.csv", mime="text/csv",
                    width='stretch', key=f"rc_dl_top10_csv_{prefixe}",
                )
            st.caption("Format du fichier téléchargé à finaliser — export brut pour l'instant.")

            for _, g in groupes.iterrows():
                sous = df_top10_flux[
                    (df_top10_flux["partenaire"] == g["partenaire"]) &
                    (df_top10_flux["hs6"] == g["hs6"]) &
                    (df_top10_flux["annee"] == g["annee"])
                ].sort_values("rang")

                titre = [f"SH4 {g['hs6']}"]
                if plusieurs_partenaires:
                    titre.append(noms_geo.get(g["partenaire"], g["partenaire"]))
                if plusieurs_annees:
                    titre.append(str(g["annee"]))

                lignes_top10 = [
                    {"rang": r["rang"], "titre": r["nom"], "valeur": r["valeur"], "highlight": r["est_qc"]}
                    for _, r in sous.iterrows()
                ]

                cle_container = f"rc_top10_{prefixe}_{g['hs6']}_{g['partenaire']}_{g['annee']}"
                with st.container(key=cle_container, border=True):
                    st.markdown(f"**{' · '.join(titre)}**")
                    st.markdown(
                        _html_leaderboard(lignes_top10, unite, "Fournisseur / Client"),
                        unsafe_allow_html=True,
                    )

    # ── ONGLET PROPORTIONS (pie chart, remplace Tendance -- une seule année
    # sélectionnable maintenant, un graphique d'évolution n'a plus de sens) ─
    with onglet_proportions:
        if df_detail_flux.empty:
            st.info("Aucun résultat à afficher.")
        else:
            import plotly.express as px

            df_pie = df_detail_flux.copy()
            df_pie["Produit"] = "SH4 " + df_pie["hs6"].astype(str)
            fig = px.pie(
                df_pie, values="valeur_qc", names="Produit",
                title="Proportion de chaque produit dans le flux Québec (Top 25)",
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig, width='stretch', key=f"rc_pie_{prefixe}")

    # ── ONGLET DONNÉES COMPLÈTES ───────────────────────────────────────────
    with onglet_donnees:
        df_lisible = df_flux.copy()
        df_lisible["Province"] = df_lisible["province"].map(lambda c: noms_geo.get(c, c))
        df_lisible["Partenaire"] = df_lisible["partenaire"].map(lambda c: noms_geo.get(c, c))
        colonnes_affichage = ["annee", "Province", "Partenaire", "hs6", "valeur",
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
                file_name=f"rang_commercial_qc_etats_{prefixe}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width='stretch', key=f"rc_dl_xlsx_{prefixe}",
            )
        with col2:
            st.download_button(
                "📥 CSV", data=exporter_csv(df_lisible[colonnes_affichage]),
                file_name=f"rang_commercial_qc_etats_{prefixe}.csv", mime="text/csv",
                width='stretch', key=f"rc_dl_csv_{prefixe}",
            )

with st.sidebar:
    with st.container(border=True):
        st.markdown("**Mode**")
        mode = st.radio(
            "Mode", options=["Sélection personnalisée", "Preset Top25"],
            label_visibility="collapsed", key="rc_mode",
        )

    annee_min_dispo, annee_max_dispo = d.lister_annees_disponibles("CIMT")
    annees_disponibles = list(range(annee_max_dispo, annee_min_dispo - 1, -1))  # plus récente d'abord

    with st.container(border=True):
        st.markdown("**Flux et période**")
        annee_choisie = st.selectbox(
            "Année", options=annees_disponibles, index=0, key="rc_annee",
        )
        annees_selectionnees = [annee_choisie]

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
            "Devise", options=["USD", "CAD"],
            index=0, key="rc_devise", label_visibility="collapsed",
            help="Pas d'option 'Native (par source)' ici -- cet outil compare "
                 "le Québec à des provinces (CIMT/ISQ, natif CAD) ET à des "
                 "pays étrangers (Census, natif USD) dans le MÊME classement. "
                 "Comparer sans harmoniser la devise n'aurait aucun sens.",
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
                         f"{noms_geo.get(etats_selectionnes[0], etats_selectionnes[0])} "
                         f"(ISQ, séparément Fournisseur/DE et Client/TI)...")
                codes_par_flux = top25_sh4_isq(annees_selectionnees, etats_selectionnes[0])
                st.write(f"Fournisseur (DE) : {len(codes_par_flux['DE'])} codes retenus : "
                         f"{', '.join(codes_par_flux['DE']) or '—'}")
                st.write(f"Client (TI) : {len(codes_par_flux['TI'])} codes retenus : "
                         f"{', '.join(codes_par_flux['TI']) or '—'}")
                flux_a_extraire = {"DE": codes_par_flux["DE"], "TI": codes_par_flux["TI"]}
            else:
                flux_a_extraire = {f: codes_sh4_selectionnes for f in flux_cochees}

            # Une extraction SÉPARÉE par sens de flux, chacune restreinte à
            # ses propres codes -- jamais les deux flux sur la même liste
            # (voir docstring de top25_sh4_isq pour le bug que ça évite).
            # extraire_et_classer() gère aussi l'harmonisation de devise
            # avant classement (voir son docstring).
            st.write("Ventilation provinciale (CIMT), substitution ISQ, "
                     "fournisseurs étrangers (Census), classement...")
            morceaux_provincial, morceaux_pays = [], []
            for flux_val, codes_flux in flux_a_extraire.items():
                if not codes_flux:
                    continue
                dfp, dfy = extraire_et_classer(
                    annees_selectionnees, flux_val, etats_selectionnes, codes_flux, devise_rc
                )
                morceaux_provincial.append(dfp)
                morceaux_pays.append(dfy)
            df_resultat = (pd.concat(morceaux_provincial, ignore_index=True)
                           if morceaux_provincial else pd.DataFrame())
            df_pays = (pd.concat(morceaux_pays, ignore_index=True)
                       if morceaux_pays else pd.DataFrame())

            st.write("Construction du détail par produit...")
            df_detail = construire_detail_produit(df_resultat, df_pays, noms_geo)
            df_top10 = construire_top10_produit(df_resultat, df_pays, noms_geo)

            # ── VUE D'ENSEMBLE -- indépendante de la sélection Top25/
            # personnalisée en cours, toujours "tous produits" ISQ pour le
            # premier état sélectionné (voir plan_action_rang_commercial.txt
            # section 4). ────────────────────────────────────────────────
            st.write("Vue d'ensemble : top 5 tous produits, classement "
                     "inter-états, catégories fixes...")
            etat_ve = etats_selectionnes[0]
            top5 = {
                "DE": top_produits_isq(annees_selectionnees, etat_ve, "DE", 5),
                "TI": top_produits_isq(annees_selectionnees, etat_ve, "TI", 5),
            }
            etats_univers = [c for c, t in d.lister_entites_cote("CIMT", "b") if t == "ETAT_US"]
            classement_total = classement_commerce_total(annees_selectionnees, etats_univers, etat_ve)

            categories_resultat: dict[str, dict[str, pd.DataFrame]] = {}
            for nom_cat, codes_cat in CATEGORIES_FIXES.items():
                categories_resultat[nom_cat] = {}
                for flux_val in ("DE", "TI"):
                    dfp_cat, dfy_cat = extraire_et_classer(
                        annees_selectionnees, flux_val, [etat_ve], codes_cat, devise_rc
                    )
                    df_detail_cat = construire_detail_produit(dfp_cat, dfy_cat, noms_geo)
                    dfp_agg, dfy_agg = agreger_categorie(dfp_cat, dfy_cat, f"Total {nom_cat}")
                    df_res_agg = calculer_rangs(dfp_agg, dfy_agg)
                    df_total_cat = construire_detail_produit(df_res_agg, dfy_agg, noms_geo)
                    categories_resultat[nom_cat][flux_val] = pd.concat(
                        [df_detail_cat, df_total_cat], ignore_index=True
                    )

            statut.update(label="Extraction terminée", state="complete")

        st.session_state[cle_session] = df_resultat
        st.session_state["rc_df_detail"] = df_detail
        st.session_state["rc_df_top10"] = df_top10
        st.session_state["rc_top5"] = top5
        st.session_state["rc_classement_total"] = classement_total
        st.session_state["rc_categories"] = categories_resultat
        st.session_state["rc_etat_ve"] = etat_ve
        # Gèle la devise utilisée POUR CETTE EXTRACTION -- ne doit plus
        # bouger tant qu'une nouvelle extraction n'est pas lancée, même si
        # le widget "rc_devise" change entre-temps (voir usage de
        # devise_resultat, pas devise_rc, dans tout l'affichage ci-dessous).
        st.session_state["rc_devise_resultat"] = devise_rc

df_affiche = st.session_state.get(cle_session, pd.DataFrame())
df_detail = st.session_state.get("rc_df_detail", pd.DataFrame())
df_top10 = st.session_state.get("rc_df_top10", pd.DataFrame())
top5 = st.session_state.get("rc_top5", {})
classement_total = st.session_state.get("rc_classement_total", {})
categories_resultat = st.session_state.get("rc_categories", {})
etat_ve = st.session_state.get("rc_etat_ve")
devise_resultat = st.session_state.get("rc_devise_resultat", "USD")


def _afficher_vue_ensemble(top5: dict, classement_total: dict, categories_resultat: dict,
                            etat_ve: str, unite: str, noms_geo: dict) -> None:
    """Vue d'ensemble -- indépendante de la sélection Top25/personnalisée en
    cours, toujours 'tous produits' (ISQ) pour le premier état sélectionné.
    Top 5 export/import + commerce total TOUJOURS affichés ensemble (pas
    scindés Fournisseur/Client) ; seules les catégories fixes changent de
    sens, via leurs propres sous-onglets."""
    if not top5 or not classement_total:
        st.info("Configure tes filtres dans la barre latérale, puis clique **Extraire**.")
        return

    nom_etat = noms_geo.get(etat_ve, etat_ve)
    st.subheader(f"Commerce Québec ↔ {nom_etat} — tous produits")

    col_exp, col_imp = st.columns(2)
    for col, cle_flux, titre_bloc, cle_container in [
        (col_exp, "DE", "🚚 Top 5 exportés QC → état", "rc_ve_top5_de"),
        (col_imp, "TI", "🛒 Top 5 importés QC ← état", "rc_ve_top5_ti"),
    ]:
        with col:
            with st.container(key=cle_container, border=True):
                st.markdown(f"**{titre_bloc}**")
                df5 = top5.get(cle_flux)
                if df5 is None or df5.empty:
                    st.info("Aucune donnée.")
                else:
                    lignes5 = [
                        {"rang": i + 1, "titre": f"SH4 {r.hs6}", "valeur": r.valeur}
                        for i, r in enumerate(df5.itertuples())
                    ]
                    st.markdown(_html_leaderboard(lignes5, unite, "Produit"), unsafe_allow_html=True)

    with st.container(key="rc_ve_total", border=True):
        st.markdown(f"**Commerce total avec {nom_etat}** — tous produits, "
                    "parmi les 54 juridictions américaines (50 états + D.C. "
                    "+ Porto Rico + Îles Vierges + Autres États non identifiés)")
        c1, c2, c3 = st.columns(3)
        for col, cle_flux, label in [
            (c1, "DE", "Exportations QC → état"), (c2, "TI", "Importations QC ← état"),
            (c3, "TOTAL", "Commerce bilatéral total"),
        ]:
            info = classement_total.get(cle_flux, {})
            with col:
                st.metric(label, f"{info.get('valeur', 0) / 1e9:,.2f} G$ {unite}")
                rang, nb_total = info.get("rang"), info.get("nb_total", 54)
                st.caption(f"Rang #{rang}/{nb_total} · {info.get('part_pct', 0):.2f} % du total US")

    st.divider()
    st.markdown("### Catégories fixes")
    st.caption("Seule section de cette page qui change de sens selon l'onglet choisi.")
    onglet_fourn_cat, onglet_client_cat = st.tabs(["🚚 Fournisseur", "🛒 Client"])
    for onglet_cat, flux_val in [(onglet_fourn_cat, "DE"), (onglet_client_cat, "TI")]:
        with onglet_cat:
            for nom_cat in CATEGORIES_FIXES:
                df_cat = categories_resultat.get(nom_cat, {}).get(flux_val, pd.DataFrame())
                with st.container(key=f"rc_ve_cat_{nom_cat}_{flux_val}", border=True):
                    st.markdown(f"**{nom_cat}**")
                    if df_cat.empty:
                        st.info("Aucun résultat.")
                        continue
                    est_total_mask = df_cat["hs6"].astype(str).str.startswith("Total ")
                    df_codes = df_cat[~est_total_mask].sort_values("rang_qc")
                    df_total_ligne = df_cat[est_total_mask]
                    df_ordonne = pd.concat([df_codes, df_total_ligne], ignore_index=True)

                    lignes_cat = []
                    for _, r in df_ordonne.iterrows():
                        est_total = str(r["hs6"]).startswith("Total ")
                        titre = r["hs6"] if est_total else f"SH4 {r['hs6']}"
                        sous_titre = (f"1er : {r['top_nom']} ({r['top_valeur']:,.0f} {unite}) "
                                      f"· {r['nb_total']} au total")
                        lignes_cat.append({
                            "rang": r["rang_qc"], "titre": titre, "valeur": r["valeur_qc"],
                            "sous_titre": sous_titre, "highlight": est_total or r["rang_qc"] == 1,
                        })
                    st.markdown(
                        _html_leaderboard(lignes_cat, unite, "Produit"), unsafe_allow_html=True
                    )


if df_affiche.empty:
    st.info("Configure tes filtres dans la barre latérale, puis clique **Extraire**.")
else:
    noms_geo = d.referentiel_geo()
    unite = devise_resultat

    onglet_fournisseur, onglet_client, onglet_vue_ensemble = st.tabs([
        "🚚 Fournisseur — le Québec vend à l'état (DE)",
        "🛒 Client — le Québec achète de l'état (TI)",
        "📊 Vue d'ensemble",
    ])

    with onglet_fournisseur:
        _afficher_bloc_flux("DE", "de", df_affiche, df_detail, df_top10, unite,
                             annees_selectionnees, noms_geo, devise_resultat)
    with onglet_client:
        _afficher_bloc_flux("TI", "ti", df_affiche, df_detail, df_top10, unite,
                             annees_selectionnees, noms_geo, devise_resultat)
    with onglet_vue_ensemble:
        _afficher_vue_ensemble(top5, classement_total, categories_resultat,
                                etat_ve, unite, noms_geo)