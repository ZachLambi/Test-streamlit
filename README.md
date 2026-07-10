# Dashboard BDD universelle

Interface Streamlit d'extraction et d'analyse pour les 4 sources de commerce
international (ISQ, CIMT, Census, BACI).

## Statut

🧪 **Phase de test.** L'app tourne actuellement sur des données synthétiques
(`test_data/`) générées par `generer_donnees_test.py` — les vraies données
vivent sur Drive et ne sont pas encore branchées ici. `donnees.py` bascule
automatiquement sur les données de test si les chemins Drive réels ne sont
pas trouvés sur le disque (pas de flag à activer/désactiver à la main).

## Tester dans GitHub Codespaces

1. Sur cette page du repo, cliquer le bouton vert **Code** → onglet
   **Codespaces** → **Create codespace on main**.
2. Une fois l'environnement ouvert (VS Code dans le navigateur), ouvrir un
   terminal (`Terminal` → `New Terminal`) et lancer :
   ```bash
   pip install -r requirements.txt
   streamlit run app.py
   ```
3. Codespaces détecte automatiquement le port 8501 et propose d'ouvrir
   l'app dans un nouvel onglet — cliquer **Open in Browser** dans la
   notification qui apparaît en bas à droite (ou onglet **Ports** →
   icône du globe à côté du port 8501).
4. Le bandeau "🧪 Mode test" en haut de l'app confirme qu'on tourne bien
   sur les données synthétiques.

## Régénérer les données de test

```bash
python generer_donnees_test.py
```

## Fichiers

- `app.py` — interface Streamlit (panneau d'extraction, métriques, export)
- `donnees.py` — couche de données DuckDB (filtrage multi-sources, calculs :
  variation annuelle, CAGR, part de marché, rang)
- `export.py` — génération Excel formaté / CSV
- `generer_donnees_test.py` — données synthétiques pour tester sans Drive

## Prochaine étape (une fois l'accès GCS confirmé)

Remplacer `_CHEMINS_DRIVE` dans `donnees.py` par des URLs `gs://...` —
DuckDB les lit nativement via l'extension `httpfs`, sans changement à la
logique de bascule automatique.
