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
import streamlit as st

# ── Configuration des chemins parquet par source ─────────────────────────────
# À ajuster une fois les fichiers migrés sur GCS (remplacer par des URLs
# gs://... — DuckDB lit gs:// nativement via l'extension httpfs).
#
# Résolution en cascade, sans flag à activer/désactiver à la main — juste
# une détection de ce qui est réellement présent sur le disque, dans
# l'ordre de préférence suivant :
#   1. Chemin Drive réel (exécution dans Colab, Drive monté)
#   2. Vrais parquets déposés localement dans data/ (nom réel inchangé —
#      ex: isq_annuel.parquet — utile pour tester en dehors de Colab sans
#      attendre la mise en place de GCS)
#   3. Données synthétiques dans test_data/ (dernier recours, pour valider
#      l'interface quand aucune vraie donnée n'est disponible)
_ICI = Path(__file__).resolve().parent
_DOSSIER_DATA_LOCALE = _ICI / "data"
_DOSSIER_TEST = _ICI / "test_data"

_NOMS_FICHIERS_REELS = {
    "ISQ": "isq_annuel.parquet", "CIMT": "cimt_annuel.parquet",
    "CENSUS": "census_sh6_annuel.parquet", "BACI": "baci_annuel.parquet",
}

_CHEMINS_DRIVE = {
    src: f"/content/drive/MyDrive/Scripts_de_récolte_et_analyse_de_données/Base de données universelle/{src if src != 'CENSUS' else 'Census'}/Parquets/{nom}"
    for src, nom in _NOMS_FICHIERS_REELS.items()
}

_FICHIERS_TEST = {
    "ISQ": "isq_test.parquet", "CIMT": "cimt_test.parquet",
    "CENSUS": "census_test.parquet", "BACI": "baci_test.parquet",
}


def _resoudre_chemin(source: str) -> tuple[str, str]:
    """Retourne (chemin, niveau) où niveau est 'drive', 'local_reel' ou 'test'."""
    chemin_drive = Path(_CHEMINS_DRIVE[source])
    if chemin_drive.exists():
        return str(chemin_drive), "drive"

    chemin_local_reel = _DOSSIER_DATA_LOCALE / _NOMS_FICHIERS_REELS[source]
    if chemin_local_reel.exists():
        return str(chemin_local_reel), "local_reel"

    return str(_DOSSIER_TEST / _FICHIERS_TEST[source]), "test"


_RESOLUTION = {src: _resoudre_chemin(src) for src in _NOMS_FICHIERS_REELS}
SOURCES_PARQUET = {src: chemin for src, (chemin, _) in _RESOLUTION.items()}
NIVEAUX_SOURCES = {src: niveau for src, (_, niveau) in _RESOLUTION.items()}

# Mode test seulement si AUCUNE source n'a de vraies données (ni Drive ni
# dépôt local réel) — sinon on considère qu'on travaille avec de vraies
# données, même partiellement.
MODE_TEST = all(niveau == "test" for niveau in NIVEAUX_SOURCES.values())

# Devise/unité par source — affichée à côté des valeurs dans l'UI
UNITE_PAR_SOURCE = {
    "ISQ": "CAD", "CIMT": "CAD", "CENSUS": "USD", "BACI": "milliers USD",
}


def _con():
    """Connexion DuckDB partagée et réutilisée (pas une nouvelle connexion
    par appel) — ouvrir/fermer une connexion à répétition à chaque rerun
    Streamlit s'est révélé provoquer un vrai segfault dans libarrow (bug
    bas niveau partagé par DuckDB et pandas/pyarrow, pas un bug applicatif),
    observé en conditions de test. Une connexion longue-durée élimine ce
    churn et le risque associé."""
    global _CONNEXION_PARTAGEE
    if _CONNEXION_PARTAGEE is None:
        _CONNEXION_PARTAGEE = duckdb.connect()
    return _CONNEXION_PARTAGEE


_CONNEXION_PARTAGEE = None


def _mtime(chemin: str) -> float:
    """Horodatage de dernière modification — inclus dans la clé de cache
    pour invalider automatiquement si le parquet est recompilé, sans TTL
    arbitraire à deviner."""
    p = Path(chemin)
    return p.stat().st_mtime if p.exists() else 0.0


@st.cache_data(show_spinner=False)
def _lister_annees_impl(chemin: str, _mtime_cle: float) -> tuple[int, int]:
    con = _con()
    row = con.execute("SELECT MIN(annee), MAX(annee) FROM read_parquet(?)", [chemin]).fetchone()
    return (int(row[0]), int(row[1])) if row and row[0] is not None else (2011, 2025)


def lister_annees_disponibles(source: str, chemins: dict[str, str] | None = None) -> tuple[int, int]:
    """Retourne (annee_min, annee_max) réellement présentes dans le parquet
    de cette source — pas une plage codée en dur. Mis en cache par
    (chemin, mtime), même logique que les autres fonctions lister_*."""
    chemins = chemins or SOURCES_PARQUET
    chemin = chemins.get(source)
    if not chemin or not Path(chemin).exists():
        return (2011, 2025)
    return _lister_annees_impl(chemin, _mtime(chemin))


@st.cache_data(show_spinner=False)
def _lister_flux_impl(chemin: str, _mtime_cle: float) -> list[str]:
    con = _con()
    df = con.execute("SELECT DISTINCT flux FROM read_parquet(?) ORDER BY flux", [chemin]).fetchdf()
    return df["flux"].tolist()


def lister_flux_disponibles(source: str, chemins: dict[str, str] | None = None) -> list[str]:
    """Flux réellement présents dans le parquet de cette source (pas une
    liste codée en dur — CIMT n'a pas TE, BACI n'a que TE, etc.). Mis en
    cache par (chemin, mtime) — pas re-questionné à chaque interaction UI,
    seulement si le fichier a changé depuis la dernière recompilation."""
    chemins = chemins or SOURCES_PARQUET
    chemin = chemins.get(source)
    if not chemin or not Path(chemin).exists():
        return []
    return _lister_flux_impl(chemin, _mtime(chemin))


# ═══════════════════════════════════════════════════════════════════════════
# RÉFÉRENTIEL GÉOGRAPHIQUE — correspondance code -> nom lisible, + statut actif
# ═══════════════════════════════════════════════════════════════════════════
# Cherche referentiel_geo.csv (colonnes : code, nom, actif) déposé par
# l'utilisateur à la racine du repo. Si absent, repli propre : le code sert
# de "nom" et aucun code n'est considéré inactif (pas de filtrage) — pas de
# flag à activer/désactiver, détection automatique comme le reste des
# résolutions de chemins.
_CHEMIN_REFERENTIEL_CSV = _ICI / "referentiel_geo.csv"


@st.cache_data(show_spinner=False)
def _charger_referentiel_geo(_mtime_cle: float) -> tuple[dict[str, str], set[str]]:
    """Retourne (noms {code: nom}, codes_inactifs {code, ...})."""
    if _CHEMIN_REFERENTIEL_CSV.exists():
        try:
            df_ref = pd.read_csv(_CHEMIN_REFERENTIEL_CSV, dtype=str)
            col_code = next((c for c in df_ref.columns if c.lower() in ("code", "code_geo")), None)
            col_nom = next((c for c in df_ref.columns if c.lower() in ("nom", "name", "nom_pays")), None)
            col_actif = next((c for c in df_ref.columns if c.lower() == "actif"), None)
            if col_code and col_nom:
                noms = dict(zip(df_ref[col_code], df_ref[col_nom]))
                inactifs = set()
                if col_actif:
                    inactifs = set(df_ref.loc[df_ref[col_actif].astype(str).str.lower() == "false", col_code])
                return noms, inactifs
        except Exception:
            pass
    return {}, set()


def referentiel_geo() -> dict[str, str]:
    """Dict {code: nom}. Vide si aucun référentiel trouvé — les appelants
    doivent utiliser .get(code, code) pour retomber sur le code par défaut."""
    mtime = _mtime(str(_CHEMIN_REFERENTIEL_CSV)) if _CHEMIN_REFERENTIEL_CSV.exists() else 0.0
    return _charger_referentiel_geo(mtime)[0]


def codes_geo_inactifs() -> set[str]:
    """Ensemble des codes marqués actif=False dans le référentiel — vide
    si aucun référentiel trouvé (aucun filtrage dans ce cas)."""
    mtime = _mtime(str(_CHEMIN_REFERENTIEL_CSV)) if _CHEMIN_REFERENTIEL_CSV.exists() else 0.0
    return _charger_referentiel_geo(mtime)[1]


REFERENTIEL_GEO_DISPONIBLE = _CHEMIN_REFERENTIEL_CSV.exists()


@st.cache_data(show_spinner=False)
def _lister_partenaires_impl(chemin: str, _mtime_cle: float) -> list[tuple[str, str]]:
    con = _con()
    df = con.execute("""
        WITH tous AS (
            SELECT origine AS code, type_ori AS type FROM read_parquet(?)
            UNION ALL
            SELECT destination AS code, type_dest AS type FROM read_parquet(?)
        ),
        comptes AS (
            SELECT code, type, COUNT(*) AS n FROM tous GROUP BY code, type
        ),
        total AS (SELECT COUNT(*) AS n FROM read_parquet(?))
        SELECT c.code, c.type
        FROM comptes c, total t
        WHERE c.n < t.n
        ORDER BY c.type, c.code
    """, [chemin, chemin, chemin]).fetchdf()
    return list(df.itertuples(index=False, name=None))


def lister_partenaires(source: str, chemins: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """Retourne les (code, type) des partenaires disponibles pour cette
    source — PAS l'entité "maison" (ex: P24 pour ISQ). L'entité maison est
    détectée automatiquement (elle apparaît dans 100% des lignes, un
    partenaire n'apparaît que dans un sous-ensemble) plutôt que codée en
    dur par source — ISQ a un mélange pays/états américains comme
    partenaires, CIMT a un mélange pays/états, BACI n'a que des pays. Mis
    en cache par (chemin, mtime), même logique que lister_flux_disponibles.

    Les codes marqués inactifs dans le référentiel géo (0 échange confirmé
    empiriquement) sont exclus de la liste, même s'ils apparaissent par
    exception dans les données — ce filtre s'ajoute à celui, déjà en place,
    qui ne retient que les codes réellement présents dans CETTE source."""
    chemins = chemins or SOURCES_PARQUET
    chemin = chemins.get(source)
    if not chemin or not Path(chemin).exists():
        return []
    partenaires = _lister_partenaires_impl(chemin, _mtime(chemin))
    inactifs = codes_geo_inactifs()
    if inactifs:
        partenaires = [(c, t) for c, t in partenaires if c not in inactifs]
    return partenaires


TOUS_PARTENAIRES = "🌐 TOUS LES PAYS (excl. détail États-Unis, évite le double comptage)"
TOUS_PRODUITS = "🌐 TOUS LES PRODUITS (total, tous codes HS confondus)"


def extraire(
    sources: list[str],
    annees: list[int] | None = None,
    flux: list[str] | None = None,
    partenaires: list[str] | None = None,
    hs6_prefixes: list[str] | None = None,
    agreger_partenaires: bool = False,
    chemins: dict[str, str] | None = None,
) -> pd.DataFrame:
    """
    Extraction filtrée multi-sources. Retourne l'UNION des sources cochées,
    chacune gardant sa colonne `source` d'origine — aucune agrégation
    inter-source n'est faite ici (unités non harmonisées, voir module docstring).

    partenaires : filtre sur origine OU destination (peu importe le sens du flux)
    hs6_prefixes : filtre par préfixe de code HS (ex: "87" matche tout HS2=87) —
        la sommation au niveau du préfixe se fait ensuite dans regrouper(),
        pas ici (cette fonction ne fait que filtrer, jamais sommer)
    agreger_partenaires : si True, ignore `partenaires` et filtre plutôt sur
        le type de l'entité "partenaire" (le côté du flux qui n'est PAS
        l'entité maison) = PAYS uniquement, excluant les entités ETAT_US —
        ces dernières sont déjà comptées dans l'agrégat pays (ex: USA) et
        les resommer créerait un double comptage. Le vrai regroupement en
        une seule ligne se fait dans regrouper(), pas ici.
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

        if agreger_partenaires:
            # Le "partenaire" est le côté destination pour DE/TE, origine
            # pour TI — seul ce côté doit être restreint à PAYS (l'autre
            # côté est l'entité maison, dont le type n'a pas à être filtré).
            conditions.append("""
                (
                    (flux IN ('DE','TE') AND type_dest = 'PAYS')
                    OR (flux = 'TI' AND type_ori = 'PAYS')
                    OR (flux NOT IN ('DE','TE','TI') AND type_ori = 'PAYS' AND type_dest = 'PAYS')
                )
            """)
        elif partenaires:
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

    if not frames:
        return pd.DataFrame(columns=[
            "annee", "source", "flux", "origine", "type_ori",
            "destination", "type_dest", "hs6", "valeur",
        ])
    return pd.concat(frames, ignore_index=True)


def regrouper(
    df: pd.DataFrame,
    hs6_prefixes: list[str] | None = None,
    agreger_produits: bool = False,
    agreger_partenaires: bool = False,
) -> pd.DataFrame:
    """
    Somme le résultat d'extraire() au bon niveau d'agrégation — c'est ICI
    que la correction du bug SH4/SH2 se fait (extraire() ne fait QUE
    filtrer, jamais sommer, pour rester une fonction simple et prévisible).

    Niveau de regroupement des CODES HS :
      - agreger_produits=True        -> une seule ligne 'TOUS' (somme totale)
      - hs6_prefixes fourni           -> une ligne par préfixe saisi (ex: taper
                                          "8703" donne UNE ligne sommant tous
                                          les HS6 sous "8703", pas le détail)
      - ni l'un ni l'autre             -> pas de regroupement, détail HS6 complet
                                          (comportement par défaut, inchangé)

    Niveau de regroupement des PARTENAIRES :
      - agreger_partenaires=True     -> une seule ligne 'TOUS_PAYS' par
                                          (source, flux, hs_groupe, annee)
      - sinon                          -> pas de regroupement, une ligne par
                                          partenaire (comportement par défaut)

    Si aucune agrégation n'est demandée, retourne df inchangé (identité).
    """
    if df.empty:
        return df

    df = df.copy()

    # ── Niveau HS ────────────────────────────────────────────────────────
    if agreger_produits:
        df["hs6"] = "TOUS"
    elif hs6_prefixes:
        # Assigne chaque ligne au préfixe saisi le plus SPÉCIFIQUE (le plus
        # long) qu'elle matche — permet de mélanger des préfixes de
        # longueurs différentes (ex: "8703,27") sans ambiguïté.
        prefixes_tries = sorted(hs6_prefixes, key=len, reverse=True)
        groupe = pd.Series(pd.NA, index=df.index, dtype="object")
        for prefixe in prefixes_tries:
            mask = groupe.isna() & df["hs6"].str.startswith(prefixe)
            groupe[mask] = prefixe
        df["hs6"] = groupe.fillna(df["hs6"])  # sécurité : ligne non matchée garde son hs6

    # ── Niveau partenaire ────────────────────────────────────────────────
    if agreger_partenaires:
        # Le côté "maison" (province/état fixe) reste tel quel, le côté
        # "partenaire" devient un label agrégé générique.
        est_de_te = df["flux"].isin(["DE", "TE"])
        df.loc[est_de_te, "destination"] = "TOUS_PAYS"
        df.loc[est_de_te, "type_dest"] = "PAYS"
        df.loc[~est_de_te, "origine"] = "TOUS_PAYS"
        df.loc[~est_de_te, "type_ori"] = "PAYS"

    # ── Sommation, seulement si une agrégation a effectivement été demandée
    if agreger_produits or hs6_prefixes or agreger_partenaires:
        cles_groupe = ["annee", "source", "flux", "origine", "type_ori",
                        "destination", "type_dest", "hs6"]
        df = df.groupby(cles_groupe, as_index=False)["valeur"].sum()

    return df


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