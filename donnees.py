"""
donnees.py — Couche de données pour le dashboard bdd universelle
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Interroge les parquets des 4 sources directement via DuckDB (pas d'import
dans une base — DuckDB lit les parquets sur disque/GCS avec pushdown de
prédicats) et calcule les métriques dérivées sur le résultat déjà filtré.

IMPORTANT — unités non harmonisées entre sources (voir décision prise) :
ISQ/CIMT en CAD, Census/BACI en USD (BACI en milliers USD en plus). Ce
module NE CONVERTIT RIEN — il retourne les valeurs telles quelles avec la
source explicite sur chaque ligne. L'interface doit afficher clairement la
devise/unité par source plutôt que de laisser croire à un total comparable.
"""

from pathlib import Path
import duckdb
import pandas as pd

# ── Configuration des chemins parquet par source ─────────────────────────────
# À ajuster une fois les fichiers migrés sur GCS (remplacer par des URLs
# gs://... — DuckDB lit gs:// nativement via l'extension httpfs).
SOURCES_PARQUET = {
    "ISQ":    "/content/drive/MyDrive/Scripts_de_récolte_et_analyse_de_données/Base de données universelle/ISQ/Parquets/isq_annuel.parquet",
    "CIMT":   "/content/drive/MyDrive/Scripts_de_récolte_et_analyse_de_données/Base de données universelle/CIMT/Parquets/cimt_annuel.parquet",
    "CENSUS": "/content/drive/MyDrive/Scripts_de_récolte_et_analyse_de_données/Base de données universelle/Census/Parquets/census_sh6_annuel.parquet",
    "BACI":   "/content/drive/MyDrive/Scripts_de_récolte_et_analyse_de_données/Base de données universelle/BACI/Parquets/baci_annuel.parquet",
}

# Devise/unité par source — affichée à côté des valeurs dans l'UI
UNITE_PAR_SOURCE = {
    "ISQ": "CAD", "CIMT": "CAD", "CENSUS": "USD", "BACI": "milliers USD",
}


def _con():
    return duckdb.connect()


def extraire(
    sources: list[str],
    annees: list[int] | None = None,
    flux: list[str] | None = None,
    partenaires: list[str] | None = None,
    hs6_prefixes: list[str] | None = None,
    chemins: dict[str, str] | None = None,
) -> pd.DataFrame:
    """
    Extraction filtrée multi-sources. Retourne l'UNION des sources cochées,
    chacune gardant sa colonne `source` d'origine — aucune agrégation
    inter-source n'est faite ici (unités non harmonisées, voir module docstring).

    partenaires : filtre sur origine OU destination (peu importe le sens du flux)
    hs6_prefixes : filtre par préfixe de code HS (ex: "87" matche tout HS2=87)
    chemins : override des chemins par défaut (utile pour les tests, ou GCS)
    """
    chemins = chemins or SOURCES_PARQUET
    frames = []
    con = _con()

    for src in sources:
        if src not in chemins:
            continue
        path = chemins[src]
        if not Path(path).exists():
            continue  # source non disponible localement — ignorée silencieusement

        conditions = []
        params = []

        if annees:
            conditions.append(f"annee IN ({','.join('?' * len(annees))})")
            params.extend(annees)
        if flux:
            conditions.append(f"flux IN ({','.join('?' * len(flux))})")
            params.extend(flux)
        if partenaires:
            ph = ",".join("?" * len(partenaires))
            conditions.append(f"(origine IN ({ph}) OR destination IN ({ph}))")
            params.extend(partenaires)
            params.extend(partenaires)
        if hs6_prefixes:
            sous_conditions = " OR ".join(["hs6 LIKE ?"] * len(hs6_prefixes))
            conditions.append(f"({sous_conditions})")
            params.extend([f"{p}%" for p in hs6_prefixes])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        requete = f"SELECT * FROM read_parquet(?) {where}"

        df = con.execute(requete, [path] + params).fetchdf()
        if not df.empty:
            frames.append(df)

    con.close()
    if not frames:
        return pd.DataFrame(columns=[
            "annee", "source", "flux", "origine", "type_ori",
            "destination", "type_dest", "hs6", "valeur",
        ])
    return pd.concat(frames, ignore_index=True)


# ═══════════════════════════════════════════════════════════════════════════
# CALCULS — appliqués sur le résultat déjà filtré, par groupe logique
# (source, flux, origine, destination, hs6) pour ne comparer que des séries
# homogènes entre elles.
# ═══════════════════════════════════════════════════════════════════════════

_CLES_GROUPE = ["source", "flux", "origine", "destination", "hs6"]


def ajouter_variation_annuelle(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute 'variation_pct' = % de variation vs l'année précédente,
    au sein de chaque série homogène (même source/flux/partenaire/produit)."""
    if df.empty:
        return df
    df = df.sort_values(_CLES_GROUPE + ["annee"]).copy()
    df["valeur_precedente"] = df.groupby(_CLES_GROUPE)["valeur"].shift(1)
    df["variation_pct"] = (
        (df["valeur"] - df["valeur_precedente"]) / df["valeur_precedente"] * 100
    ).round(2)
    return df.drop(columns=["valeur_precedente"])


def ajouter_cagr(df: pd.DataFrame, n_annees: int = 5) -> pd.DataFrame:
    """Ajoute 'cagr_Nans_pct' = taux de croissance annuel composé sur les
    N dernières années disponibles dans CHAQUE série (pas nécessairement
    calendaire — si une série n'a que 3 ans de données, le calcul se fait
    sur les 3 ans disponibles et n_annees_reel l'indique)."""
    if df.empty:
        return df

    def _cagr_serie(groupe: pd.DataFrame) -> pd.Series:
        g = groupe.sort_values("annee")
        g_fenetre = g.tail(n_annees + 1)  # N périodes de croissance = N+1 points
        if len(g_fenetre) < 2:
            return pd.Series({f"cagr_{n_annees}ans_pct": None, "n_annees_reel": len(g_fenetre) - 1 if len(g_fenetre) else 0})
        val_debut, val_fin = g_fenetre["valeur"].iloc[0], g_fenetre["valeur"].iloc[-1]
        n_periodes = len(g_fenetre) - 1
        if val_debut <= 0 or n_periodes == 0:
            cagr = None
        else:
            cagr = (round((((val_fin / val_debut) ** (1 / n_periodes)) - 1) * 100, 2))
        return pd.Series({f"cagr_{n_annees}ans_pct": cagr, "n_annees_reel": n_periodes})

    resultats = df.groupby(_CLES_GROUPE, group_keys=True).apply(_cagr_serie, include_groups=False)
    return df.merge(resultats.reset_index(), on=_CLES_GROUPE, how="left")


def ajouter_part_marche(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute 'part_marche_pct' = part de la ligne dans le total
    (source, flux, destination OU origine selon le sens, hs6, annee) —
    i.e. la part du partenaire dans le total du produit pour cette
    année/flux/source, PAS un total tous partenaires confondus mal défini."""
    if df.empty:
        return df
    df = df.copy()
    # Le "sujet" dont on mesure la part = le partenaire (l'autre bout que
    # l'entité fixe du flux — ex: pour un flux TE d'ISQ, le partenaire est
    # 'destination'; on utilise ici simplement les deux colonnes ensemble
    # comme identifiant de partenaire pour rester générique entre sources).
    cles_total = ["source", "flux", "hs6", "annee"]
    totaux = df.groupby(cles_total)["valeur"].transform("sum")
    df["part_marche_pct"] = (df["valeur"] / totaux * 100).round(2)
    return df


def ajouter_rang(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute 'rang' = position de la ligne (par valeur décroissante) au
    sein de (source, flux, hs6, annee) — ex: rang du partenaire pour ce
    produit cette année-là, dans la sélection actuelle uniquement (le rang
    n'est valide que sur les partenaires inclus dans l'extraction, pas
    nécessairement le rang mondial réel si la sélection est partielle)."""
    if df.empty:
        return df
    df = df.copy()
    df["rang"] = (
        df.groupby(["source", "flux", "hs6", "annee"])["valeur"]
        .rank(method="min", ascending=False)
        .astype(int)
    )
    return df


METRIQUES_DISPONIBLES = {
    "variation_annuelle": ("Variation annuelle (%)", ajouter_variation_annuelle),
    "cagr": ("Taux de croissance composé (CAGR)", ajouter_cagr),
    "part_marche": ("Part de marché (%)", ajouter_part_marche),
    "rang": ("Rang parmi la sélection", ajouter_rang),
}


def appliquer_metriques(df: pd.DataFrame, cles_metriques: list[str], cagr_n_annees: int = 5) -> pd.DataFrame:
    """Applique les métriques cochées, dans un ordre fixe pour éviter les
    dépendances de colonnes entre calculs."""
    resultat = df
    for cle in ["variation_annuelle", "cagr", "part_marche", "rang"]:
        if cle in cles_metriques:
            _, fonction = METRIQUES_DISPONIBLES[cle]
            resultat = fonction(resultat, cagr_n_annees) if cle == "cagr" else fonction(resultat)
    return resultat
