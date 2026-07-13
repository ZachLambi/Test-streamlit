"""
export.py — Génération de fichiers d'export prêts à l'emploi
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Objectif : que l'export SOIT la version finale (en-têtes clairs, colonnes
ajustées, gel des volets, tri déjà fait) — pas un point de départ à
remanier dans Excel avant de pouvoir l'utiliser.
"""

from io import BytesIO
import pandas as pd

NOMS_COLONNES_AFFICHAGE = {
    "annee": "Année", "source": "Source", "flux": "Flux",
    "origine": "Origine", "type_ori": "Type origine",
    "destination": "Destination", "type_dest": "Type destination",
    "hs6": "Code HS6", "valeur": "Valeur",
    "variation_pct": "Variation ann. (%)",
    "cagr_5ans_pct": "CAGR (%)", "n_annees_reel": "Années (CAGR)",
    "part_marche_pct": "Part de marché (%)", "rang": "Rang",
}

# Libellés des métriques qui varient PAR ANNÉE (pivotées, une colonne par
# année) — à distinguer des métriques PAR SÉRIE (CAGR, n_annees_reel) qui
# restent en une seule colonne puisqu'elles ont déjà la même valeur peu
# importe l'année dans le résultat d'origine.
_LIBELLES_METRIQUES_ANNEE = {
    "valeur": "Valeur", "variation_pct": "Variation (%)",
    "part_marche_pct": "Part marché (%)", "rang": "Rang",
}
_ORDRE_METRIQUES_ANNEE = ["valeur", "variation_pct", "part_marche_pct", "rang"]

_COLONNES_A_MASQUER = {"type_ori", "type_dest", "source"}
_CLES_IDENTITE = ["flux", "origine", "destination", "hs6"]


def mettre_en_forme_large(df: pd.DataFrame, noms_geo: dict[str, str]) -> pd.DataFrame:
    """
    Transforme le résultat long (une ligne par année) en tableau large
    (une colonne par année) prêt à être affiché ou exporté — appelée une
    seule fois, réutilisée à l'identique pour l'écran ET l'export, pour
    qu'ils ne puissent jamais diverger.

      - codes origine/destination -> noms (référentiel géo, repli sur le
        code si le référentiel n'a pas d'entrée pour ce code)
      - colonnes type_ori / type_dest / source retirées (redondantes une
        fois qu'on est dans un seul onglet d'une seule source)
      - une colonne PAR ANNÉE pour la valeur, et — si les métriques
        correspondantes ont été cochées — pour variation annuelle, part de
        marché et rang, chacune accolée juste à côté de la valeur de son
        année (pas dans un bloc séparé) pour rester facile à lire
      - CAGR et son nombre d'années réel restent en une seule colonne à la
        toute fin (valeur par SÉRIE, pas par année)
    """
    if df.empty:
        return df

    df = df.copy()
    df["origine"] = df["origine"].map(lambda c: noms_geo.get(c, c))
    df["destination"] = df["destination"].map(lambda c: noms_geo.get(c, c))

    cles = [c for c in _CLES_IDENTITE if c in df.columns]
    colonnes_annee = [c for c in _ORDRE_METRIQUES_ANNEE if c in df.columns]
    colonne_cagr = next((c for c in df.columns if c.startswith("cagr_") and c.endswith("ans_pct")), None)
    colonnes_serie = ([colonne_cagr] if colonne_cagr else []) + (
        ["n_annees_reel"] if "n_annees_reel" in df.columns else []
    )

    annees = sorted(df["annee"].dropna().unique())

    base = df[cles].drop_duplicates(subset=cles).reset_index(drop=True)

    for annee in annees:
        sous_annee = df[df["annee"] == annee]
        for col in colonnes_annee:
            libelle_metrique = _LIBELLES_METRIQUES_ANNEE[col]
            nom_colonne = str(annee) if (len(colonnes_annee) == 1 and col == "valeur") \
                else f"{annee} · {libelle_metrique}"
            serie = sous_annee.set_index(cles)[col].rename(nom_colonne)
            base = base.merge(serie, on=cles, how="left")

    # Métriques PAR SÉRIE (CAGR, n_annees_reel) ajoutées en tout dernier —
    # une seule valeur par groupe, pas par année, donc pas pivotées.
    if colonnes_serie:
        serie_valeurs = df[cles + colonnes_serie].drop_duplicates(subset=cles)
        base = base.merge(serie_valeurs, on=cles, how="left")

    base = base.rename(columns=NOMS_COLONNES_AFFICHAGE)
    return base


def exporter_excel(df_large: pd.DataFrame, note_unite: str) -> bytes:
    """Génère un .xlsx formaté à partir d'un tableau DÉJÀ mis en forme par
    mettre_en_forme_large() (large, colonnes renommées, codes déjà
    convertis en noms) — en-têtes en gras avec fond, colonnes ajustées à
    leur contenu, volets gelés sous l'en-tête. Retourne les bytes du
    fichier (prêt pour un bouton de téléchargement).

    Import openpyxl différé (dans la fonction, pas en haut du module) —
    évite un conflit bas niveau observé entre openpyxl et DuckDB quand les
    deux sont chargés dans le même contexte avant tout appel Excel réel."""
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_large.to_excel(writer, sheet_name="Extraction", index=False, startrow=1)
        wb = writer.book
        ws = writer.sheets["Extraction"]

        # Ligne de note sur les unités, au-dessus du tableau
        ws.cell(row=1, column=1, value=f"Unités : {note_unite}").font = Font(italic=True, size=9)

        # En-têtes : gras, fond gris clair, alignées au centre
        fond_entete = PatternFill(start_color="E8EAED", end_color="E8EAED", fill_type="solid")
        for col_idx, nom_col in enumerate(df_large.columns, start=1):
            cellule = ws.cell(row=2, column=col_idx)
            cellule.font = Font(bold=True)
            cellule.fill = fond_entete
            cellule.alignment = Alignment(horizontal="center")

        # Largeur de colonne ajustée au contenu (plafonnée à 40 pour éviter
        # qu'une valeur aberrante n'étire toute la colonne)
        for col_idx, nom_col in enumerate(df_large.columns, start=1):
            lettre = get_column_letter(col_idx)
            largeur_contenu = df_large[nom_col].astype(str).str.len().max()
            largeur = max(len(str(nom_col)), int(largeur_contenu) if pd.notna(largeur_contenu) else 10) + 2
            ws.column_dimensions[lettre].width = min(largeur, 40)

        # Gel des volets sous l'en-tête (ligne 3 = première ligne de données)
        ws.freeze_panes = "A3"

    return buffer.getvalue()


def exporter_csv(df_large: pd.DataFrame) -> bytes:
    """CSV simple pour retraitement ailleurs, à partir d'un tableau DÉJÀ
    mis en forme par mettre_en_forme_large() (pas de mise en forme
    supplémentaire ici — c'est le point : un CSV formaté n'a pas de sens)."""
    return df_large.to_csv(index=False).encode("utf-8-sig")  # BOM pour Excel FR