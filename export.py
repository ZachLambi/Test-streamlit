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


def exporter_excel(df: pd.DataFrame, unites_par_source: dict[str, str]) -> bytes:
    """Génère un .xlsx formaté : en-têtes en gras avec fond, colonnes
    ajustées à leur contenu, volets gelés sous l'en-tête, tri par année.
    Retourne les bytes du fichier (prêt pour un bouton de téléchargement).

    Import openpyxl différé (dans la fonction, pas en haut du module) —
    évite un conflit bas niveau observé entre openpyxl et DuckDB quand les
    deux sont chargés dans le même contexte avant tout appel Excel réel."""
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    df_export = df.rename(columns=NOMS_COLONNES_AFFICHAGE)
    if "Année" in df_export.columns:
        df_export = df_export.sort_values("Année")

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_export.to_excel(writer, sheet_name="Extraction", index=False, startrow=1)
        wb = writer.book
        ws = writer.sheets["Extraction"]

        # Ligne de note sur les unités, au-dessus du tableau
        sources_presentes = df["source"].unique().tolist() if "source" in df.columns else []
        note = " | ".join(f"{s} en {unites_par_source.get(s, '?')}" for s in sources_presentes)
        ws.cell(row=1, column=1, value=f"Unités : {note}").font = Font(italic=True, size=9)

        # En-têtes : gras, fond gris clair, alignées au centre
        fond_entete = PatternFill(start_color="E8EAED", end_color="E8EAED", fill_type="solid")
        for col_idx, nom_col in enumerate(df_export.columns, start=1):
            cellule = ws.cell(row=2, column=col_idx)
            cellule.font = Font(bold=True)
            cellule.fill = fond_entete
            cellule.alignment = Alignment(horizontal="center")

        # Largeur de colonne ajustée au contenu (plafonnée à 40 pour éviter
        # qu'une valeur aberrante n'étire toute la colonne)
        for col_idx, nom_col in enumerate(df_export.columns, start=1):
            lettre = get_column_letter(col_idx)
            largeur_contenu = df_export[nom_col].astype(str).str.len().max()
            largeur = max(len(str(nom_col)), int(largeur_contenu) if pd.notna(largeur_contenu) else 10) + 2
            ws.column_dimensions[lettre].width = min(largeur, 40)

        # Gel des volets sous l'en-tête (ligne 3 = première ligne de données)
        ws.freeze_panes = "A3"

    return buffer.getvalue()


def exporter_csv(df: pd.DataFrame) -> bytes:
    """CSV simple pour retraitement ailleurs (pas de mise en forme —
    c'est le point : un CSV formaté n'a pas de sens)."""
    df_export = df.rename(columns=NOMS_COLONNES_AFFICHAGE)
    return df_export.to_csv(index=False).encode("utf-8-sig")  # BOM pour Excel FR
