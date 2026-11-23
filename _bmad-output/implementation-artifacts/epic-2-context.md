# Epic 2 Context: Organisations, dossiers et membres

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Implémenter la gestion multi-organisationnelle, les adhésions (`Membership`) avec attribution des rôles RBAC (`admin`, `analyst`, `investigator`, `viewer`), ainsi que la création, la consultation et la gestion du cycle de vie des dossiers d'investigation (`Case` : `open`, `in_progress`, `review`, `closed`), en imposant un contrôle d'accès strict au niveau route (`verify_case_access`) garantissant une étanchéité absolue (Zero Leak) entre organisations clientes.

## Stories

- Story 2.1: Modèles Organization et Membership, migration Alembic et schémas Pydantic
- Story 2.2: API de gestion des organisations et attribution des rôles RBAC
- Story 2.3: Modèle Case, migration Alembic et gestion du cycle de vie des dossiers
- Story 2.4: Dépendance de sécurité verify_case_access et isolation stricte par dossier

## Requirements & Constraints

- Modélisation relationnelle stricte sous PostgreSQL 16 des entités `Organization`, `Membership` et `Case` avec identifiants UUID et horodatages UTC.
- Rôles RBAC énumérés strictement : `admin`, `analyst`, `investigator`, `viewer`.
- Statuts de dossier (`Case`) énumérés strictement : `open`, `in_progress`, `review`, `closed` avec contrôle des transitions de cycle de vie (rejet des transitions invalides en HTTP 400).
- Contrainte d'unicité composite sur `memberships (organization_id, user_id)` pour empêcher les doublons.
- Suppression en cascade : la suppression d'une organisation révoque en cascade ses adhésions et dossiers associés sans laisser d'orphelins.
- Contrôle d'accès RBAC au niveau route avec dépendance `require_role` (seul `admin` peut inviter ou modifier les rôles de membres).
- Dépendance de sécurité systématique `verify_case_access` pour interdire tout accès trans-organisation (Zero Leak) et retourner HTTP 404 / 403 sans fuite d'existence ou de métadonnées.
- Pagination systématique (`limit` par défaut / max 100, `offset`) sur les listes d'organisations, de membres et de dossiers.
- Schémas Pydantic v2 stricts (`SchemaIn`, `SchemaOut`) interdisant l'exposition directe des modèles ORM SQLAlchemy.
- Migrations de schéma traçables et réversibles via Alembic sans appel à `create_all` en production.
- Conformité stricte : 0 avertissement / 0 erreur Ruff, typage complet et couverture de tests unitaires, d'intégration et de sécurité multi-tenants.

## Technical Decisions

- **D-03** : Framework API REST : FastAPI (>=0.115.0).
- **D-04** : Validation de schémas et configuration : Pydantic v2 (>=2.9.0) et `pydantic-settings` (>=2.5.0).
- **D-05** : Base de données relationnelle : PostgreSQL 16.
- **D-06** : ORM et pilote SQL : SQLAlchemy 2.x (>=2.0.35) avec `psycopg` 3 (>=3.2.0).
- **D-07** : Gestionnaire de migrations : Alembic (>=1.13.0).
- **D-12** : Jetons d'authentification : `PyJWT` (>=2.9.0).
- **D-20** : Tests automatisés : `pytest` (>=8.3.0), `pytest-asyncio` (>=0.24.0), `httpx` (>=0.27.0).
- **D-21** : Linter et formateur de code : `ruff` (>=0.6.0).
- **D-23** : Journalisation : bibliothèque standard `logging` au format JSON structuré sans secrets.

## Cross-Story Dependencies

- E2 dépend d'E1 : l'authentification JWT (`get_current_user`), le modèle `User`, la session DB (`get_db`) et les exceptions de base sont déjà établis.
- Story 2.1 établit les modèles ORM et schémas `Organization` et `Membership`, ainsi que la migration Alembic `002_create_org_and_membership_tables`.
- Story 2.2 s'appuie sur les modèles de 2.1 pour fournir le service, le routeur et le contrôle RBAC sur les organisations et les membres.
- Story 2.3 ajoute le modèle `Case`, sa migration Alembic `003_create_case_table` et son cycle de vie.
- Story 2.4 implémente la dépendance `verify_case_access` protégeant les dossiers et leurs futures sous-ressources (preuves, observations, findings, rapports des épics E3 à E8).
