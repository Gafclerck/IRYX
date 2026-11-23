# ADR-0002 : PostgreSQL plutôt que SQLite par dossier
 
- **Date** : 2026-11-23
- **Statut** : acceptée
 
---
 
## Contexte
 
La plateforme de référence Mulder utilisait une base de données SQLite distincte par dossier d'enquête (`Case`), stockée aux côtés des artefacts.
 
Dans le cadre d'IRYX, nous devons supporter des accès concurrents multi-utilisateurs (analystes, superviseurs, auditeurs), des recherches textuelles rapides sur des millions d'observations normalisées, et garantir des transactions ACID strictes lors de la mise à jour des états d'investigation et du journal d'audit immuable.
 
---
 
## Décision
 
Nous retenons **PostgreSQL 16** comme base de données relationnelle unique et source centrale de vérité (D-05) :
1. Une seule instance PostgreSQL héberge l'ensemble des dossiers, preuves, observations, exécutions d'outils, findings et événements d'audit.
2. L'accès à la base de données s'effectue exclusivement via SQLAlchemy 2.x et le pilote natif `psycopg` 3 (D-06).
3. Le partitionnement logique par dossier est garanti au niveau applicatif et schéma par clé étrangère stricte (`case_id`) et contrôle d'accès systématique par middleware/dépendance FastAPI.
4. Les évolutions de schéma sont rigoureusement gérées par des migrations Alembic (D-07).
5. L'approche d'un fichier SQLite par dossier est formellement écartée.
 
---
 
## Conséquences
 
### Positives
- **Concurrence multi-utilisateurs native** : Gestion robuste des transactions et des verrous concurrents sans risque de verrouillage de fichier (`database is locked` typique de SQLite sous charge).
- **Recherche plein texte native (FTS)** : Capacités d'indexation GIN et recherche rapide sur le contenu des observations sans dépendance tierce.
- **Sécurité et intégrité référentielle** : Clés étrangères avec cascade contrôlée, contraintes d'unicité et déclencheurs empêchant la modification du journal d'audit (`AuditEvent`).
- **Évolution facilitée** : Gestion outillée des migrations de schéma via Alembic sans manipulation manuelle de multiples fichiers SQLite.
 
### Négatives / Risques
- Nécessite l'exécution d'un conteneur de service PostgreSQL dans Docker Compose (impact mémoire minime et standard).
 
---
 
Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
