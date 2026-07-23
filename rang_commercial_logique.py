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

CORRECTIF (20 juillet 2026) — trois bugs trouvés en conditions réelles (test
Ohio) :
  1. Le côté "province" de CIMT dépend du flux (origine pour TI, destination
     pour DE/TE) -- la première version lisait 'origine' sans condition,
     donc affichait le partenaire (Ohio) comme "Province" pour les lignes TI.
     Corrigé : calculer_rangs() calcule maintenant EXPLICITEMENT une colonne
     'province', flux-consciente, en plus de 'partenaire'.
  2. CIMT et Census n'ont PAS la même convention de côté pour l'état :
     CIMT   -- état = côté B (partenaire) : destination pour DE/TE, origine pour TI
     Census -- état = côté A (domestique) : origine pour DE/TE, destination pour TI
     (SENS INVERSÉ). La première version utilisait la formule CIMT pour les
     deux sources -- la clé de jointure pour Census pointait donc sur la
     mauvaise colonne selon le flux, et Rang_vs_tous_fournisseurs ne
     trouvait jamais les bonnes valeurs pays. Corrigé : formules distinctes
     par source.
  3. top25_sh4_isq() ne filtrait pas par état (sommait le commerce du Québec
     avec TOUS les partenaires) et utilisait DE au lieu de TE. Corrigé :
     paramètre état ajouté, flux TE pour les exportations (comme demandé),
     TI pour les importations.
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


def _agreger_vers_codes(df: pd.DataFrame, codes_demandes: list[str] | None) -> pd.DataFrame:
    """Agrège les lignes SH6 au niveau EXACT des codes demandés (2, 4 ou 6
    chiffres) -- PAS toujours SH4. Si l'utilisateur (Sélection
    personnalisée) ou une catégorie fixe demande un code SH2 (ex. '44'
    pour Foresterie), toutes ses lignes SH6 sous-jacentes sont fusionnées
    en UNE SEULE ligne '44' -- pas éclatées en plusieurs lignes SH4 comme
    avant, ce qui faisait apparaître chaque sous-code séparément dans les
    classements/tableaux alors que l'utilisateur avait demandé une
    agrégation au niveau SH2.

    CORRECTIF (22 juillet 2026) -- si aucun code n'est fourni (cas Top25
    preset, qui construit toujours ses propres codes SH4 précis via
    top25_sh4_isq, jamais de sélection utilisateur ici), retombe sur le
    comportement SH4 historique (_agreger_sh6_vers_sh4) -- comportement
    inchangé pour ce chemin."""
    if df.empty:
        return df
    if not codes_demandes:
        return _agreger_sh6_vers_sh4(df)

    df = df.copy()
    # Le code le plus SPÉCIFIQUE (le plus long) d'abord, pour le cas où
    # deux codes demandés seraient l'un préfixe de l'autre (ex. '84' et
    # '8411' en même temps) -- la ligne va au code le plus précis, pas au
    # plus large.
    codes_tries = sorted(set(codes_demandes), key=len, reverse=True)

    def _code_correspondant(hs6: str) -> str:
        for code in codes_tries:
            if hs6.startswith(code):
                return code
        return hs6[:4]  # filet de sécurité -- ne devrait pas arriver si
        # hs6_prefixes (déjà utilisé pour la requête SQL) est cohérent

    df["hs6"] = df["hs6"].astype(str).map(_code_correspondant)
    colonnes_groupe = [c for c in df.columns if c != "valeur"]
    return df.groupby(colonnes_groupe, as_index=False, observed=True)["valeur"].sum()


def _ajouter_province_et_partenaire_cimt(df: pd.DataFrame) -> pd.DataFrame:
    """CIMT : état = côté B (partenaire). DE/TE -> partenaire=destination,
    province=origine. TI -> partenaire=origine, province=destination."""
    if df.empty:
        return df
    df = df.copy()
    est_ti = df["flux"] == "TI"
    df["province"] = df["destination"].where(est_ti, df["origine"])
    df["partenaire"] = df["origine"].where(est_ti, df["destination"])
    return df


def _ajouter_partenaire_census(df: pd.DataFrame) -> pd.DataFrame:
    """Census : état = côté A (domestique) -- CONVENTION INVERSE de CIMT.
    DE/TE -> état=origine. TI -> état=destination."""
    if df.empty:
        return df
    df = df.copy()
    est_ti = df["flux"] == "TI"
    df["partenaire"] = df["destination"].where(est_ti, df["origine"])
    return df


def extraire_provincial(annees: list[int], flux: list[str], etats_us: list[str],
                         codes_sh4: list[str]) -> pd.DataFrame:
    """Ventilation par province canadienne du commerce avec le(s) état(s)
    américain(s) demandé(s) -- remplace ISED, vient de CIMT."""
    df = d.extraire(
        sources=["CIMT"], annees=annees, flux=flux,
        partenaires_b=etats_us, hs6_prefixes=codes_sh4,
    )
    df = _agreger_vers_codes(df, codes_sh4)
    return _ajouter_province_et_partenaire_cimt(df)


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
    df_isq = _agreger_vers_codes(df_isq, codes_sh4)
    df_isq = _ajouter_province_et_partenaire_cimt(df_isq)
    if df_isq.empty:
        return df_provincial

    df_sans_qc = df_provincial[df_provincial.get("province") != "PQC"]
    return pd.concat([df_sans_qc, df_isq], ignore_index=True)


def extraire_pays_pour_etat(annees: list[int], flux: list[str], etats_us: list[str],
                             codes_sh4: list[str]) -> pd.DataFrame:
    """Ventilation par pays étranger (Canada exclu, déjà couvert par le
    détail provincial CIMT) des fournisseurs/clients du ou des état(s)
    demandé(s) -- remplace l'API Census, vient du parquet Census (SH6
    agrégé localement en SH4).

    CORRECTIF (21 juillet 2026, v2) -- Census et CIMT ont des conventions
    côté A/B INVERSÉES (voir _ajouter_partenaire_census vs
    _ajouter_province_et_partenaire_cimt), ce qui inverse aussi la
    correspondance entre leurs labels de flux. Vérifié sur les données
    brutes (colonnes origine/destination/type_ori/type_dest) :
      CIMT  DE -> province=origine, état=destination  (la province EXPORTE
            vers l'état, donc l'état IMPORTE)
      CIMT  TI -> état=origine, province=destination  (l'état EXPORTE vers
            la province, donc la province IMPORTE)
      Census TE -> état=origine, pays=destination     (l'état EXPORTE vers
            le pays -- même sens que CIMT TI, PAS CIMT DE)
      Census TI -> pays=origine, état=destination     (le pays EXPORTE vers
            l'état, donc l'état IMPORTE -- même sens que CIMT DE, PAS TE)
    Autrement dit, la correspondance par NOM (DE~TE, TI~TI) est FAUSSE --
    la bonne correspondance par SENS DE FLUX est DE<->TI(Census) et
    TI<->TE(Census). Une v1 de ce correctif avait mappé DE->TE, ce qui
    comparait à tort le Québec-fournisseur (CIMT DE) avec les pays-clients
    de l'état (Census TE) -- deux rôles opposés. Corrigé : on interroge
    Census avec le flux correspondant au bon SENS, puis on relabellise le
    résultat selon la convention CIMT pour rejoindre la clé de groupe du
    détail provincial."""
    correspondance_cimt_vers_census = {"DE": "TI", "TI": "TE"}
    correspondance_census_vers_cimt = {"TI": "DE", "TE": "TI"}
    flux_census = [correspondance_cimt_vers_census.get(f, f) for f in flux]
    df = d.extraire(
        sources=["CENSUS"], annees=annees, flux=flux_census,
        partenaires_a=etats_us, hs6_prefixes=codes_sh4,
    )
    if df.empty:
        return df
    # Filtre agnostique au sens du flux -- Canada peut apparaître en
    # origine (TE) ou destination (TI) côté Census.
    df = df[(df.get("origine") != CODE_CANADA_CENSUS) & (df.get("destination") != CODE_CANADA_CENSUS)]
    df = _agreger_vers_codes(df, codes_sh4)
    df = _ajouter_partenaire_census(df)
    df["flux"] = df["flux"].map(lambda f: correspondance_census_vers_cimt.get(f, f))
    return df


def calculer_rangs(df_provincial: pd.DataFrame, df_pays: pd.DataFrame) -> pd.DataFrame:
    """Calcule les deux classements sur le détail provincial (déjà
    substitué ISQ), en suivant d'aussi près que possible la logique du
    script original (_classer_census) :
      - Rang_vs_provinces : .rank(method='min') au sein du groupe
        (partenaire état, hs6, année, flux) -- vectorisé, identique à
        l'original.
      - Rang_vs_tous_fournisseurs : dictionnaire de correspondance
        pré-calculé (clé -> liste des valeurs pays), comme pays_lookup
        dans le script original, puis un passage ligne par ligne pour
        combiner avec les autres provinces du même groupe -- même
        structure que l'original, pas une réinvention.
    """
    if df_provincial.empty:
        return df_provincial

    df = df_provincial.copy()
    cle_groupe = ["partenaire", "hs6", "annee", "flux"]

    df["Rang_vs_provinces"] = (
        df.groupby(cle_groupe, observed=True)["valeur"].rank(ascending=False, method="min").astype("Int64")
    )
    df["Nb_provinces"] = df.groupby(cle_groupe, observed=True)["valeur"].transform("count")

    if df_pays is None or df_pays.empty:
        df["Rang_vs_tous_fournisseurs"] = df["Rang_vs_provinces"]
        df["Nb_fournisseurs_total"] = df["Nb_provinces"]
        return df

    # Dictionnaire clé -> liste des valeurs pays, PRÉ-CALCULÉ une seule
    # fois (comme pays_lookup dans _classer_census), pas refiltré à
    # chaque ligne -- plus fidèle à l'original ET plus rapide.
    pays_lookup: dict[tuple, list[float]] = {}
    for cle, sous_df in df_pays.groupby(cle_groupe, observed=True):
        pays_lookup[cle] = sous_df["valeur"].dropna().tolist()

    # Dictionnaire des valeurs des AUTRES provinces par groupe, même
    # principe -- évite de refiltrer df à chaque itération.
    provinces_par_groupe: dict[tuple, list[tuple]] = {}
    for cle, sous_df in df.groupby(cle_groupe, observed=True):
        provinces_par_groupe[cle] = list(zip(sous_df.index, sous_df["valeur"]))

    rangs, nb_total = [], []
    for idx, ligne in df.iterrows():
        cle = (ligne["partenaire"], ligne["hs6"], ligne["annee"], ligne["flux"])
        vals_pays = pays_lookup.get(cle, [])
        vals_autres_prov = [v for i, v in provinces_par_groupe.get(cle, []) if i != idx]
        pool = vals_pays + vals_autres_prov
        rangs.append(sum(1 for v in pool if v > ligne["valeur"]) + 1)
        nb_total.append(len(pool) + 1)

    df["Rang_vs_tous_fournisseurs"] = pd.array(rangs, dtype="Int64")
    df["Nb_fournisseurs_total"] = pd.array(nb_total, dtype="Int64")
    return df


def _candidats_par_groupe(df_qc: pd.DataFrame, df_provincial: pd.DataFrame,
                           df_pays: pd.DataFrame, noms_geo: dict):
    """Générateur interne PARTAGÉ par construire_detail_produit() et
    construire_top10_produit(), pour ne jamais faire diverger la logique de
    fusion provinces+pays entre les deux. Pour chaque ligne Québec (un
    groupe partenaire/hs6/année/flux), produit (cle, ligne_qc, candidats)
    où candidats est la liste COMPLÈTE (Québec + provinces + pays) triée
    par valeur décroissante -- (nom, valeur, est_qc).

    Le TRI utilise 'valeur_usd' (harmonisée) si la colonne est présente,
    PAS 'valeur' (qui peut être en devise "Native (par source)", donc un
    mélange CAD/USD non comparable) -- sinon l'ordre affiché contredirait
    le rang déjà calculé sur une base harmonisée (voir calculer_rangs).
    Si 'valeur_usd' est absente (df plus ancien/appel externe), on retombe
    sur 'valeur' pour rester rétrocompatible."""
    cle_groupe = ["partenaire", "hs6", "annee", "flux"]
    a_valeur_usd_prov = "valeur_usd" in df_provincial.columns
    a_valeur_usd_pays = df_pays is not None and not df_pays.empty and "valeur_usd" in df_pays.columns

    for _, ligne_qc in df_qc.iterrows():
        cle = tuple(ligne_qc[c] for c in cle_groupe)

        val_tri_qc = ligne_qc["valeur_usd"] if a_valeur_usd_prov else ligne_qc["valeur"]
        candidats = [("Québec", ligne_qc["valeur"], True, val_tri_qc)]

        autres = df_provincial[
            (df_provincial["partenaire"] == cle[0]) & (df_provincial["hs6"] == cle[1]) &
            (df_provincial["annee"] == cle[2]) & (df_provincial["flux"] == cle[3]) &
            (df_provincial["province"] != "PQC")
        ]
        for _, r in autres.iterrows():
            val_tri = r["valeur_usd"] if a_valeur_usd_prov else r["valeur"]
            candidats.append((noms_geo.get(r["province"], r["province"]), r["valeur"], False, val_tri))

        if df_pays is not None and not df_pays.empty:
            pays_grp = df_pays[
                (df_pays["partenaire"] == cle[0]) & (df_pays["hs6"] == cle[1]) &
                (df_pays["annee"] == cle[2]) & (df_pays["flux"] == cle[3])
            ]
            # Census : après translation dans extraire_pays_pour_etat, une
            # ligne df_pays de flux 'DE' provient à l'origine d'une ligne
            # Census TI (pays=origine, état=destination -- le pays exporte
            # vers l'état). Une ligne de flux 'TI' provient d'une ligne
            # Census TE (état=origine, pays=destination -- l'état exporte
            # vers le pays). Le nom du pays est donc en 'origine' pour 'DE'
            # et en 'destination' pour 'TI' -- PAS l'inverse par ressemblance
            # de nom DE~TE.
            colonne_pays = "origine" if cle[3] == "DE" else "destination"
            for _, r in pays_grp.iterrows():
                val_tri = r["valeur_usd"] if a_valeur_usd_pays else r["valeur"]
                candidats.append((noms_geo.get(r[colonne_pays], r[colonne_pays]), r["valeur"], False, val_tri))

        candidats.sort(key=lambda c: c[3], reverse=True)
        yield cle, ligne_qc, candidats


def construire_detail_produit(df_provincial: pd.DataFrame, df_pays: pd.DataFrame,
                               noms_geo: dict) -> pd.DataFrame:
    """Une ligne par (partenaire, hs6, année, flux) -- le rang du Québec,
    sa valeur, ET qui est le grand premier (nom + valeur), peu importe
    si c'est une autre province ou un pays étranger. Reproduit la section
    "Détail par produit" de exporter_excel_formate() du script original
    (colonnes Rang, Nb fournisseurs, Flux QC, 1er fournisseur, Valeur #1)."""
    if df_provincial.empty:
        return pd.DataFrame()

    df_qc = df_provincial[df_provincial["province"] == "PQC"].copy()
    if df_qc.empty:
        return pd.DataFrame()

    lignes = []
    for cle, ligne_qc, candidats in _candidats_par_groupe(df_qc, df_provincial, df_pays, noms_geo):
        top_nom, top_valeur, _, _ = candidats[0]
        lignes.append({
            "partenaire": cle[0], "hs6": cle[1], "annee": cle[2], "flux": cle[3],
            "rang_qc": int(ligne_qc["Rang_vs_tous_fournisseurs"]),
            "nb_total": int(ligne_qc["Nb_fournisseurs_total"]),
            "valeur_qc": ligne_qc["valeur"],
            "top_nom": top_nom, "top_valeur": top_valeur,
        })

    return pd.DataFrame(lignes)


def construire_top10_produit(df_provincial: pd.DataFrame, df_pays: pd.DataFrame,
                              noms_geo: dict, top_n: int = 10) -> pd.DataFrame:
    """Une ligne par (partenaire, hs6, année, flux, rang) -- le TOP N complet
    des fournisseurs/clients pour chaque produit (pas seulement le #1 comme
    construire_detail_produit()). 'est_qc' marque la ligne Québec pour la
    mise en évidence dans l'UI, sans dépendre d'une comparaison de nom
    (fiable même si un partenaire s'appelait aussi 'Québec')."""
    if df_provincial.empty:
        return pd.DataFrame()

    df_qc = df_provincial[df_provincial["province"] == "PQC"].copy()
    if df_qc.empty:
        return pd.DataFrame()

    lignes = []
    for cle, _ligne_qc, candidats in _candidats_par_groupe(df_qc, df_provincial, df_pays, noms_geo):
        for rang, (nom, valeur, est_qc, _) in enumerate(candidats[:top_n], start=1):
            lignes.append({
                "partenaire": cle[0], "hs6": cle[1], "annee": cle[2], "flux": cle[3],
                "rang": rang, "nom": nom, "valeur": valeur, "est_qc": est_qc,
            })

    return pd.DataFrame(lignes)


def resume_stats(df_detail_produit: pd.DataFrame) -> dict:
    """Statistiques agrégées reprenant exactement la section RÉSUMÉ de
    exporter_excel_formate() : nombre de produits, flux total, et
    répartition des rangs (#1, ≤2, ≤5, ≤10, rang moyen)."""
    if df_detail_produit.empty:
        return {
            "nb_produits": 0, "total_flux": 0.0, "rang1": 0, "rang2": 0,
            "rang3": 0, "rang5": 0, "rang10": 0, "rang_moyen": None, "nb_total": 0,
        }
    rangs = df_detail_produit["rang_qc"]
    return {
        "nb_produits": int(df_detail_produit["hs6"].nunique()),
        "total_flux": df_detail_produit["valeur_qc"].sum(),
        "rang1": int((rangs == 1).sum()),
        "rang2": int((rangs <= 2).sum()),
        "rang3": int((rangs <= 3).sum()),
        "rang5": int((rangs <= 5).sum()),
        "rang10": int((rangs <= 10).sum()),
        "rang_moyen": round(rangs.mean(), 1),
        "nb_total": len(df_detail_produit),
    }


def top25_sh4_isq(annees: list[int], etat: str) -> dict[str, list[str]]:
    """Détermine, SÉPARÉMENT, les 25 codes SH4 les plus importants pour le
    commerce du Québec avec l'état visé -- un top 25 PAR SENS DE FLUX, pas
    un seul ensemble fusionné.

    CORRECTIF (22 juillet 2026) -- une v1 fusionnait les deux top25 (TE et
    TI) en un seul set() avant de les retourner, ce qui faisait perdre
    l'info "sélectionné pour quel sens". En aval, l'extraction utilisait
    ce set fusionné (jusqu'à 50 codes) pour LES DEUX flux à la fois --
    l'onglet Fournisseur (DE) se retrouvait à analyser tous les codes du
    set fusionné qui avaient du commerce en DE (ex. 44), pas seulement les
    25 retenus via le classement Fournisseur. Corrigé : deux listes
    distinctes, chacune alimentant EXCLUSIVEMENT son propre sens de flux
    en aval (voir pages/rang_commercial.py).

    Le côté Fournisseur sélectionne maintenant sur 'DE' (pas 'TE') --
    cohérent avec le fait que l'analyse elle-même (Rang_vs_provinces /
    Rang_vs_tous_fournisseurs) utilise déjà DE pour ce sens (voir
    extraire_pays_pour_etat) : sélectionner sur TE risquerait de retenir un
    code dominé par des réexportations, presque inexistant une fois qu'on
    bascule sur la vraie base d'analyse (DE).

    Retourne {"DE": [...≤25 codes...], "TI": [...≤25 codes...]}."""
    resultat: dict[str, list[str]] = {}
    for flux in ("DE", "TI"):
        df = d.extraire(sources=["ISQ"], annees=annees, flux=[flux], partenaires_b=[etat])
        if df.empty:
            resultat[flux] = []
            continue
        df = _agreger_sh6_vers_sh4(df)
        totaux = df.groupby("hs6", observed=True)["valeur"].sum().sort_values(ascending=False)
        resultat[flux] = sorted(totaux.head(25).index.tolist())
    return resultat


CATEGORIES_FIXES: dict[str, list[str]] = {
    "Foresterie": ["44", "47", "48"],
    "Automobile": [f"87{i:02d}" for i in range(1, 12)] + ["8714"],
    "Aérospatial": ["401130", "840710", "8411", "8526", "88", "901420", "940110"],
}


def top_produits_isq(annees: list[int], etat: str, flux: str, devise_cible: str,
                      top_n: int = 5) -> pd.DataFrame:
    """Top N produits SH4 (TOUS produits confondus, aucune restriction de
    code) pour le commerce du Québec avec l'état visé, sur UN SEUL sens de
    flux -- utilisé pour le Top 5 de la Vue d'ensemble, indépendamment de
    toute sélection Top25/personnalisée en cours. Colonnes : hs6, valeur
    (déjà dans devise_cible -- ce niveau de ce module compare toujours des
    valeurs ISQ entre elles, une seule source/devise native, donc la
    conversion ne change jamais le TOP N retenu, seulement l'affichage)."""
    df = d.extraire(sources=["ISQ"], annees=annees, flux=[flux], partenaires_b=[etat])
    if df.empty:
        return pd.DataFrame(columns=["hs6", "valeur"])
    df = d.convertir_devise(df, devise_cible)
    df = _agreger_sh6_vers_sh4(df)
    totaux = df.groupby("hs6", observed=True)["valeur"].sum().sort_values(ascending=False)
    return totaux.head(top_n).reset_index()


def extraire_et_classer(annees: list[int], flux_val: str, etats: list[str],
                         codes: list[str], devise_cible: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pipeline complet réutilisable : extraction (CIMT+ISQ+Census) pour UN
    SEUL flux, classement calculé sur une base TOUJOURS harmonisée en USD
    (peu importe devise_cible), puis conversion vers la devise d'affichage
    demandée -- factorise le motif déjà répété dans pages/rang_commercial.py
    (Top25, et maintenant aussi catégories fixes) pour ne jamais oublier
    l'étape d'harmonisation avant classement (voir bug SH4 7601, Illinois
    2025 -- rang faux en comparant du CAD natif à du USD natif).

    Retourne (df_resultat, df_pays) -- df_resultat porte les colonnes de
    rang ET 'valeur_usd' (harmonisée, pour un tri de candidats toujours
    valide en aval, voir _candidats_par_groupe)."""
    df_provincial = extraire_provincial(annees, [flux_val], etats, codes)
    df_provincial = substituer_isq(df_provincial, annees, [flux_val], etats, codes)
    df_pays = extraire_pays_pour_etat(annees, [flux_val], etats, codes)

    df_provincial_usd = d.convertir_devise(df_provincial, "USD")
    df_pays_usd = d.convertir_devise(df_pays, "USD") if not df_pays.empty else df_pays
    df_avec_rangs = calculer_rangs(df_provincial_usd, df_pays_usd)
    colonnes_rang = ["Rang_vs_provinces", "Nb_provinces",
                      "Rang_vs_tous_fournisseurs", "Nb_fournisseurs_total"]

    if devise_cible == "USD":
        df_resultat = df_avec_rangs
        df_resultat["valeur_usd"] = df_avec_rangs["valeur"]
        df_pays_final = df_pays_usd
        if not df_pays_final.empty:
            df_pays_final["valeur_usd"] = df_pays_usd["valeur"]
    else:
        df_resultat = d.convertir_devise(df_provincial, devise_cible)
        if colonnes_rang[0] in df_avec_rangs.columns:
            df_resultat[colonnes_rang] = df_avec_rangs[colonnes_rang]
        df_resultat["valeur_usd"] = df_provincial_usd["valeur"]
        df_pays_final = d.convertir_devise(df_pays, devise_cible) if not df_pays.empty else df_pays
        if not df_pays_final.empty:
            df_pays_final["valeur_usd"] = df_pays_usd["valeur"]

    return df_resultat, df_pays_final


def agreger_categorie(df_provincial: pd.DataFrame, df_pays: pd.DataFrame,
                       nom_categorie: str = "TOTAL") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Traite tous les codes d'une catégorie fixe (déjà filtrés en amont via
    hs6_prefixes) comme UN SEUL pseudo-produit -- somme les valeurs par
    entité (province ou pays), remplace hs6 par un placeholder constant.
    Le résultat se réinjecte tel quel dans calculer_rangs() puis
    construire_detail_produit() -- même logique, aucune duplication."""
    if df_provincial.empty:
        return df_provincial, df_pays

    def _sommer(df: pd.DataFrame) -> pd.DataFrame:
        # Colonnes à exclure de la clé de regroupement : hs6/valeur (objet
        # de l'agrégation), et les colonnes de RANG déjà calculées PAR CODE
        # par un appel antérieur à calculer_rangs()/extraire_et_classer() --
        # elles diffèrent d'un code à l'autre par construction, donc les
        # garder dans la clé empêcherait toute vraie agrégation (chaque
        # ligne resterait son propre groupe). Elles seront de toute façon
        # recalculées sur l'agrégat par le calculer_rangs() appelé ensuite.
        colonnes_rang = ["Rang_vs_provinces", "Nb_provinces",
                          "Rang_vs_tous_fournisseurs", "Nb_fournisseurs_total"]
        exclues = {"hs6", "valeur", "valeur_usd", *colonnes_rang}
        cles = [c for c in df.columns if c not in exclues]
        sommes = {"valeur": "sum"}
        if "valeur_usd" in df.columns:
            sommes["valeur_usd"] = "sum"
        out = df.groupby(cles, observed=True, as_index=False).agg(sommes)
        out["hs6"] = nom_categorie
        return out

    dfp = _sommer(df_provincial)
    dfy = _sommer(df_pays) if df_pays is not None and not df_pays.empty else df_pays
    return dfp, dfy


def classement_commerce_total(annees: list[int], etats_univers: list[str],
                               etat_cible: str, devise_cible: str) -> dict:
    """Classement du Québec dans son commerce TOTAL (tous produits, ISQ)
    avec l'état visé, parmi l'univers complet d'états fourni (54 entités
    ETAT_US décidé -- Porto Rico, Îles Vierges et "Autres États non
    identifiés" INCLUS, pas de retrait à 51). Dénominateur de la part % =
    somme de l'univers fourni (pas le commerce mondial du Québec). Le rang
    et la part % sont invariants à la devise (ratio/comparaison uniforme,
    une seule source ISQ) -- seule la VALEUR affichée (G$) a besoin de la
    conversion, appliquée ici.

    Retourne {"DE": {...}, "TI": {...}, "TOTAL": {...}}, chaque valeur un
    dict {valeur, rang, nb_total, part_pct}."""
    df = d.extraire(sources=["ISQ"], annees=annees, flux=["DE", "TI"], partenaires_b=etats_univers)
    if df.empty:
        vide = {"valeur": 0.0, "rang": None, "nb_total": len(etats_univers), "part_pct": 0.0}
        return {"DE": vide, "TI": vide, "TOTAL": vide}

    df = d.convertir_devise(df, devise_cible)
    df = _ajouter_province_et_partenaire_cimt(df)
    totaux = df.groupby(["partenaire", "flux"], observed=True)["valeur"].sum().reset_index()

    resultat: dict[str, dict] = {}
    for flux_val in ("DE", "TI"):
        sous = totaux[totaux["flux"] == flux_val].set_index("partenaire")["valeur"]
        total_univers = sous.sum()
        valeur_cible = float(sous.get(etat_cible, 0.0))
        rang = int((sous > valeur_cible).sum()) + 1 if len(sous) else None
        resultat[flux_val] = {
            "valeur": valeur_cible, "rang": rang, "nb_total": len(etats_univers),
            "part_pct": (valeur_cible / total_univers * 100) if total_univers else 0.0,
        }

    bilateral = totaux.groupby("partenaire")["valeur"].sum()
    total_univers_bi = bilateral.sum()
    valeur_cible_bi = float(bilateral.get(etat_cible, 0.0))
    rang_bi = int((bilateral > valeur_cible_bi).sum()) + 1 if len(bilateral) else None
    resultat["TOTAL"] = {
        "valeur": valeur_cible_bi, "rang": rang_bi, "nb_total": len(etats_univers),
        "part_pct": (valeur_cible_bi / total_univers_bi * 100) if total_univers_bi else 0.0,
    }
    return resultat