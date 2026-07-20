"""
rang_commercial_logique.py — Logique métier, Rang commercial (QC/États américains)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Adapte analyse_rang_commerce_v3.py pour fonctionner à 100% depuis les
parquets déjà en place :
  ISED (scrape en direct)  -> CIMT (parquet, ventilation par province)
  Census API (scrape)      -> Census (parquet, SH6 agrégé localement en SH4)
  ISQ (scrape en direct)   -> ISQ (parquet, substitution Québec plus précise)

Portée de cette première intégration : classement Québec/état(s) américain(s)
SEULEMENT -- Pays/Pays et Province/Pays viendront une fois Comtrade
réconcilié (voir resume_reconciliation_comtrade.txt). Les DEUX classements
du script original sont repris, pas seulement le plus simple :
  - Rang_vs_provinces         : Québec contre les autres provinces canadiennes
  - Rang_vs_tous_fournisseurs : Québec contre TOUTES les provinces ET tous
    les pays étrangers qui commercent avec l'état visé (nécessite Census)
"""

import pandas as pd
import donnees as d

# Code Canada tel que rapporté comme partenaire pays par Census -- exclu du
# classement "tous fournisseurs" pour éviter un double comptage avec le
# détail provincial déjà fourni par CIMT (Canada agrégé côté Census +
# provinces détaillées côté CIMT compteraient le même commerce deux fois).
CODE_CANADA_CENSUS = "C124"


def _agreger_sh6_vers_sh4(df: pd.DataFrame) -> pd.DataFrame:
    """Regroupe des lignes SH6 en SH4 -- somme sur les 4 premiers chiffres
    du code (colonne 'hs6', devient un vrai code SH4 après troncature),
    garde toutes les autres colonnes de regroupement intactes."""
    if df.empty:
        return df
    df = df.copy()
    df["hs6"] = df["hs6"].astype(str).str[:4]
    colonnes_groupe = [c for c in df.columns if c != "valeur"]
    return df.groupby(colonnes_groupe, as_index=False, observed=True)["valeur"].sum()


def extraire_provincial(annees: list[int], flux: list[str], etats_us: list[str],
                         codes_sh4: list[str]) -> pd.DataFrame:
    """Ventilation par province canadienne du commerce avec le(s) état(s)
    américain(s) demandé(s) -- remplace ISED, vient de CIMT."""
    df = d.extraire(
        sources=["CIMT"], annees=annees, flux=flux,
        partenaires_b=etats_us, hs6_prefixes=codes_sh4,
    )
    return _agreger_sh6_vers_sh4(df)


def substituer_isq(df_provincial: pd.DataFrame, annees: list[int], flux: list[str],
                    etats_us: list[str], codes_sh4: list[str]) -> pd.DataFrame:
    """Remplace les lignes Québec (PQC) de df_provincial par les valeurs
    ISQ correspondantes, plus précises -- même principe que la
    substitution ISED->ISQ du script original, mais depuis
    isq_annuel.parquet au lieu d'un scrape en direct."""
    df_isq = d.extraire(
        sources=["ISQ"], annees=annees, flux=flux,
        partenaires_b=etats_us, hs6_prefixes=codes_sh4,
    )
    df_isq = _agreger_sh6_vers_sh4(df_isq)
    if df_isq.empty:
        return df_provincial

    df_sans_qc = df_provincial[
        (df_provincial.get("origine") != "PQC") & (df_provincial.get("destination") != "PQC")
    ]
    return pd.concat([df_sans_qc, df_isq], ignore_index=True)


def extraire_pays_pour_etat(annees: list[int], flux: list[str], etats_us: list[str],
                             codes_sh4: list[str]) -> pd.DataFrame:
    """Ventilation par pays étranger (Canada exclu, déjà couvert par le
    détail provincial CIMT) des fournisseurs/clients du ou des état(s)
    demandé(s) -- remplace l'API Census, vient du parquet Census (SH6
    agrégé localement en SH4)."""
    df = d.extraire(
        sources=["CENSUS"], annees=annees, flux=flux,
        partenaires_a=etats_us, hs6_prefixes=codes_sh4,
    )
    if df.empty:
        return df
    # Filtre agnostique au sens du flux -- Canada peut apparaître en
    # origine (TI) ou destination (DE/TE) selon la direction.
    df = df[(df.get("origine") != CODE_CANADA_CENSUS) & (df.get("destination") != CODE_CANADA_CENSUS)]
    return _agreger_sh6_vers_sh4(df)


def calculer_rangs(df_provincial: pd.DataFrame, df_pays: pd.DataFrame) -> pd.DataFrame:
    """Calcule les deux classements sur le détail provincial (déjà
    substitué ISQ) :
      - Rang_vs_provinces : au sein du groupe (partenaire état, hs6,
        année, flux) -- classement parmi les provinces seulement.
      - Rang_vs_tous_fournisseurs : même groupe, mais comparé à
        provinces + pays étrangers combinés (df_pays).

    Méthode 'min' (ex aequo partagent le même rang, pas de rang sauté) --
    cohérent avec le script original (.rank(method='min')).
    """
    if df_provincial.empty:
        return df_provincial

    df = df_provincial.copy()
    cle_groupe = ["destination", "hs6", "annee", "flux"] if "destination" in df.columns else []
    # Le partenaire (état) est côté B -- destination pour DE/TE, origine
    # pour TI. On normalise ici sur une colonne 'partenaire' unique pour
    # que le classement ne dépende pas du sens du flux.
    est_ti = df["flux"] == "TI"
    df["partenaire"] = df["destination"].where(~est_ti, df["origine"])

    cle_groupe = ["partenaire", "hs6", "annee", "flux"]
    df["Rang_vs_provinces"] = (
        df.groupby(cle_groupe, observed=True)["valeur"].rank(ascending=False, method="min").astype("Int64")
    )
    df["Nb_provinces"] = df.groupby(cle_groupe, observed=True)["valeur"].transform("count")

    if df_pays is None or df_pays.empty:
        df["Rang_vs_tous_fournisseurs"] = df["Rang_vs_provinces"]
        df["Nb_fournisseurs_total"] = df["Nb_provinces"]
        return df

    df_p = df_pays.copy()
    est_ti_p = df_p["flux"] == "TI"
    df_p["partenaire"] = df_p["destination"].where(~est_ti_p, df_p["origine"])

    # Pour chaque groupe (partenaire état, hs4, annee, flux), rassembler
    # toutes les valeurs (provinces + pays) et calculer le rang de chaque
    # province dedans -- pas de raccourci vectorisé simple ici puisqu'on
    # compare CHAQUE ligne provinciale à un pool combiné variable par groupe.
    rangs, nb_total = [], []
    for _, ligne in df.iterrows():
        cle = (ligne["partenaire"], ligne["hs6"], ligne["annee"], ligne["flux"])
        autres_provinces = df[
            (df["partenaire"] == cle[0]) & (df["hs6"] == cle[1]) &
            (df["annee"] == cle[2]) & (df["flux"] == cle[3]) &
            (df.index != ligne.name)
        ]["valeur"].tolist()
        valeurs_pays = df_p[
            (df_p["partenaire"] == cle[0]) & (df_p["hs6"] == cle[1]) &
            (df_p["annee"] == cle[2]) & (df_p["flux"] == cle[3])
        ]["valeur"].tolist()
        pool = autres_provinces + valeurs_pays
        rangs.append(sum(1 for v in pool if v > ligne["valeur"]) + 1)
        nb_total.append(len(pool) + 1)

    df["Rang_vs_tous_fournisseurs"] = pd.array(rangs, dtype="Int64")
    df["Nb_fournisseurs_total"] = pd.array(nb_total, dtype="Int64")
    return df


def top25_sh4_isq(annees: list[int], flux: str) -> list[str]:
    """Détermine les 25 codes SH4 les plus importants pour le Québec,
    depuis isq_annuel.parquet -- remplace le scrape ISQ dédié
    (searchType=Top25_4) du script original par une simple agrégation
    locale, cohérent avec le principe déjà établi partout ailleurs dans
    ce projet (maximiser l'usage des parquets, minimiser le direct)."""
    df = d.extraire(sources=["ISQ"], annees=annees, flux=[flux])
    if df.empty:
        return []
    df = _agreger_sh6_vers_sh4(df)
    totaux = df.groupby("hs6", observed=True)["valeur"].sum().sort_values(ascending=False)
    return totaux.head(25).index.tolist()
