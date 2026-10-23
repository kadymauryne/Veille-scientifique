# Veille-scientifique
il s'agit de faire une veille sur les études et découvertes scientifiques couvrant l'afrique et la diaspora.

## Deux rythmes

- **Hebdomadaire** (`veille.py`, chaque vendredi) : tout ce qui sort, pour choisir l'étude du Jeudi Scientifique. Rapport : `reports/latest.md`.
- **Mensuel** (`mensuel.py`, le 1er du mois) : sélection courte pour la newsletter, construite à partir des CSV hebdomadaires du mois — aucune requête API en plus, aucun doublon. Rapport : `reports/mensuel/latest.md`.

Le mensuel commence par un bilan de couverture : une semaine manquante ou dégradée y est signalée.
Si une source principale tombe pendant l'hebdo, le run GitHub passe en rouge et vous recevez un e-mail.
Lancer un mois à la main : onglet Actions → « Sélection mensuelle newsletter » → Run workflow → `AAAA-MM`.
