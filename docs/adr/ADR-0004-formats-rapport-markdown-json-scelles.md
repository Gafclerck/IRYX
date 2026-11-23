# ADR-0004 : Formats de rapport d'incident : Markdown et JSON scellés pour le MVP (Report de l'export PDF direct)

- **Date** : 2026-11-23
- **Statut** : acceptée

---

## Contexte

L'entité `Report` du modèle de données (`docs/03-modele-de-donnees.md`) définit une énumération `format` comprenant les valeurs `markdown`, `pdf` et `json`.

Cependant, la liste des décisions intangibles de dépendances (D-01 à D-26 dans `docs/01` et `docs/07`) n'inclut aucune bibliothèque de rendu de documents PDF (telle que `weasyprint`, `reportlab` ou `xhtml2pdf`), et exclut formellement les dépendances système Linux C lourdes (comme cairo, pango, libgdk-pixbuf) afin de préserver un environnement conteneurisé pur Python et léger (D-15, D-16).

---

## Décision

Nous retenons l'**Option A** :
1. Pour le périmètre strict du MVP, la génération et le scellement cryptographique des rapports d'incident côté back-end sont limités aux formats natifs `markdown` et `json`.
2. L'export direct au format binaire compilé PDF est formellement différé à une phase post-MVP et fera l'objet d'un ADR dédié lors de l'intégration d'un composant de rendu spécifique.
3. Les utilisateurs finaux peuvent imprimer ou exporter le rapport Markdown ou HTML rendu directement via la boîte de dialogue d'impression du navigateur client.

---

## Conséquences

### Positives
- **Zéro dépendance additionnelle** : Respect rigoureux de la liste D-01 à D-26 sans surcharge de paquets Python ou C.
- **Légèreté des images Docker** : Pas d'installation de bibliothèques système Linux C complexes dans les conteneurs API et Celery Worker.
- **Interopérabilité** : Formats Markdown et JSON immédiatement exploitables par l'analyste, les SIEM et les outils de ticketing.

### Négatives / Risques
- L'export direct en un clic d'un fichier binaire `.pdf` n'est pas fourni nativement par l'API back-end dans le MVP.

---

Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & AI/Tech Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
