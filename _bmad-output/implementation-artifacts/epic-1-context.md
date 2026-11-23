# Epic 1 Context: Socle, configuration, sécurité de base

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Initialiser le socle technique du monolithe modulaire FastAPI pour la plateforme IRYX : configuration centralisée typée (Pydantic Settings), connexion relationnelle PostgreSQL 16 (SQLAlchemy 2.x, psycopg 3), gestion des migrations de schéma Alembic, journalisation structurée JSON sans secrets, et authentification utilisateur par jetons JWT signés (PyJWT) avec hachage fort de mots de passe argon2 (pwdlib).

## Stories

- Story 1.1: Initialisation du socle applicatif FastAPI, configuration Pydantic Settings et logging JSON
- Story 1.2: Infrastructure de base de données PostgreSQL 16, sessions SQLAlchemy 2.x et initialisation Alembic
- Story 1.3: Modèle utilisateur User, hachage sécurisé argon2 et migration initiale
- Story 1.4: Service d'authentification JWT et endpoint de connexion API

## Requirements & Constraints

- Initialiser l'application FastAPI sous Python 3.12 gérée avec `uv`.
- Endpoint de santé opérationnel : `GET /health` retournant `{"status": "ok", "version": "0.1.0"}` en HTTP 200.
- Configuration centralisée typée et immuable dérivée de `pydantic_settings.BaseSettings` avec lecture des variables d'environnement (`.env`) et `.env.example` documenté.
- Journalisation structurée en JSON via la bibliothèque standard `logging`, incluant `timestamp`, `level`, `logger`, `message`, `context`, avec interdiction formelle d'émettre des secrets, clés API ou mots de passe.
- Middleware global de gestion des erreurs retournant un format JSON standardisé `{"error": {"code": "...", "message": "..."}}` et masquant toute stack trace ou chemin local.
- Infrastructure de persistance PostgreSQL 16 via SQLAlchemy 2.x et pilote `psycopg` 3 avec gestionnaire de sessions `get_db` injectable via FastAPI `Depends`.
- Migrations de schéma tracées exclusivement via Alembic (`uv run alembic upgrade head`), avec interdiction formelle de `Base.metadata.create_all()` en production.
- Modèle `User` avec identifiant UUID clé primaire, email unique indexé, mot de passe haché par `argon2` via `pwdlib[argon2]`.
- Service d'authentification émettant des jetons d'accès JWT signés avec `PyJWT` (durée de validité 30 minutes, champ `sub` contenant l'ID utilisateur, `exp`, `iat`) et route `/api/v1/auth/login`.
- Dépendance de sécurité `get_current_user` validant le Bearer token JWT sur les routes protégées.
- Conformité stricte : 0 erreur / 0 avertissement `ruff`, typage strict des signatures et fonctions publiques.
- Suite de tests unitaires et d'intégration avec `pytest`, `pytest-asyncio` et `httpx`.

## Technical Decisions

- **D-01** : Python 3.12 (ou 3.13) comme environnement d'exécution.
- **D-02** : Gestionnaire de paquets et lockfile : `uv` (v0.12.8).
- **D-03** : Framework API REST : FastAPI (>=0.115.0).
- **D-04** : Validation de schémas et configuration : Pydantic v2 (>=2.9.0) et `pydantic-settings` (>=2.5.0).
- **D-05** : Base de données relationnelle : PostgreSQL 16.
- **D-06** : ORM et pilote SQL : SQLAlchemy 2.x (>=2.0.35) avec `psycopg` 3 (>=3.2.0).
- **D-07** : Gestionnaire de migrations : Alembic (>=1.13.0).
- **D-12** : Jetons d'authentification : `PyJWT` (>=2.9.0).
- **D-13** : Hachage de mot de passe : `pwdlib[argon2]` (>=0.2.0).
- **D-20** : Tests automatisés : `pytest` (>=8.3.0), `pytest-asyncio` (>=0.24.0), `httpx` (>=0.27.0).
- **D-21** : Linter et formateur de code : `ruff` (>=0.6.0).
- **D-23** : Journalisation : bibliothèque standard `logging` au format JSON structuré.

## Cross-Story Dependencies

- Story 1.1 établit le socle (`core/config.py`, `core/logging.py`, `core/exceptions.py`, `main.py`).
- Story 1.2 s'appuie sur la configuration de 1.1 pour initialiser le moteur SQLAlchemy, `db/session.py`, `db/base.py` et Alembic.
- Story 1.3 s'appuie sur le modèle de base et Alembic de 1.2 pour créer la table `User` et implémenter le hachage `argon2` dans `core/security.py`.
- Story 1.4 s'appuie sur le modèle `User` de 1.3 et la sécurité JWT pour fournir le service d'authentification et les routes `/api/v1/auth`.
- Les Épics E2 à E9 dépendent tous de l'achèvement d'Epic 1.
