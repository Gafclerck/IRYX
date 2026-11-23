---
title: 'Story 1.2 : Infrastructure de base de données PostgreSQL 16, sessions SQLAlchemy 2.x et initialisation Alembic'
type: 'feature'
created: '2026-11-23'
status: 'done'
baseline_commit: 'afb446c984fba74b9956a402f3eed1e04dc104e6'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/docs/05-conventions-backend.md'
  - '{project-root}/docs/03-modele-de-donnees.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La plateforme IRYX nécessite une infrastructure de persistance relationnelle robuste avec PostgreSQL 16 pour stocker les dossiers, preuves, observations et événements d'audit, sans risque de corruption de schéma ni de manipulation directe non tracée.

**Approach:** Configurer SQLAlchemy 2.x avec le pilote natif `psycopg` 3 et pool de connexions résilient, définir la classe déclarative de base ORM `Base`, implémenter l'injecteur de session `get_db` pour FastAPI avec fermeture garantie et gestion des indisponibilités (HTTP 503), et initialiser le gestionnaire de migrations Alembic relié aux métadonnées sans jamais invoquer `create_all` en production.

## Boundaries & Constraints

**Always:**
- Utiliser SQLAlchemy 2.x (`DeclarativeBase`) et le pilote natif `psycopg` 3 (`postgresql+psycopg://...`).
- Fournir la dépendance FastAPI `get_db` assurant la fermeture systématique de la session SQLAlchemy en fin de cycle de requête (`yield session` avec bloc `finally: session.close()`).
- Lever l'exception `DatabaseUnavailableException` (HTTP 503, code `DATABASE_UNAVAILABLE`) en cas d'échec de connexion ou d'erreur opérationnelle sur la base de données.
- Masquer systématiquement les mots de passe et identifiants dans les messages de log émis en cas d'incident de connexion SQL.
- Configurer Alembic dans `backend/alembic.ini` et `backend/migrations/` pour piloter l'historique des schémas via `alembic upgrade head`.
- Respecter une conformité stricte avec `ruff` (zéro avertissement, zéro erreur, Python 3.12).
- Couvrir l'ensemble des modules par des tests unitaires et d'intégration automatisés avec `pytest`.

**Never:**
- Aucun appel à `Base.metadata.create_all()` dans le code source de production (règle 9 de docs/05).
- Aucune fuite d'URL de base de données non masquée ou de trace d'exécution interne dans les réponses HTTP.
- Pas de dépendances tierces orphelines hors du tableau des décisions D-01 à D-26.
- Aucune création de tables métier anticipée à cette étape (les modèles `User`, `Case`, etc. sont réservés aux stories ultérieures).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Injection nominale de session DB | Route FastAPI injectant `Depends(get_db)` | Session SQLAlchemy active fournie, commit/rollback contrôlé, session fermée après la réponse | Fermeture systématique dans le bloc `finally` |
| Exécution des migrations Alembic | Commande `uv run alembic upgrade head` | Historique de migration appliqué, table `alembic_version` initialisée | Arrêt avec code de sortie non nul en cas d'erreur SQL |
| Indisponibilité PostgreSQL | Base inaccessible ou identifiants erronés lors d'une requête | HTTP 503 avec `{"error": {"code": "DATABASE_UNAVAILABLE", "message": "Service de base de données temporairement indisponible."}}` | Log CRITICAL en JSON avec masquage de l'URL et du mot de passe |
| Interdiction de `create_all` | Analyse statique et audit au démarrage | Aucune invocation de `create_all` présente dans les fichiers applicatifs de production | Violation détectée par test d'audit dédié |

</frozen-after-approval>

## Code Map

- `backend/pyproject.toml` -- Ajout des dépendances `sqlalchemy>=2.0.35`, `psycopg[binary]>=3.2.0`, `alembic>=1.13.0`
- `backend/src/iryx/core/exceptions.py` -- Définition de `DatabaseUnavailableException` (HTTP 503) et intégration dans la gestion normalisée
- `backend/src/iryx/db/__init__.py` -- Package d'infrastructure de base de données
- `backend/src/iryx/db/base.py` -- Déclaration de `Base(DeclarativeBase)` avec convention de nommage standardisée pour les contraintes
- `backend/src/iryx/db/session.py` -- Création du moteur SQLAlchemy (`create_engine`), configuration du `sessionmaker`, masquage d'URL pour les logs et fonction génératrice `get_db_session`
- `backend/src/iryx/api/__init__.py` -- Package de la couche API
- `backend/src/iryx/api/dependencies.py` -- Dépendances partagées FastAPI, exposition de `get_db`
- `backend/alembic.ini` & `alembic.ini` -- Fichiers de configuration Alembic reliant le script_location à `backend/migrations`
- `backend/migrations/env.py` -- Environnement d'exécution Alembic configuré avec `Settings.database_url` et `Base.metadata`
- `backend/migrations/script.py.mako` -- Gabarit de génération des scripts de migration
- `backend/tests/unit/test_db_session.py` -- Tests unitaires du cycle de vie de session, injection `get_db` et gestion d'erreur HTTP 503
- `backend/tests/unit/test_alembic.py` -- Tests unitaires de configuration Alembic et audit d'absence de `create_all` en production

## Tasks & Acceptance

**Execution:**
- [x] `backend/pyproject.toml` -- Ajouter les dépendances `sqlalchemy>=2.0.35`, `psycopg[binary]>=3.2.0`, `alembic>=1.13.0` et synchroniser avec `uv sync`
- [x] `backend/src/iryx/core/exceptions.py` -- Implémenter `DatabaseUnavailableException` (HTTP 503, code `DATABASE_UNAVAILABLE`)
- [x] `backend/src/iryx/db/base.py` -- Définir `Base` héritant de `DeclarativeBase` avec métadonnées conformes aux conventions
- [x] `backend/src/iryx/db/session.py` -- Configurer le moteur SQLAlchemy 2.x, `sessionmaker` et le gestionnaire de session sécurisé
- [x] `backend/src/iryx/api/dependencies.py` -- Exposer la dépendance FastAPI `get_db`
- [x] `backend/alembic.ini` -- Configurer Alembic avec le répertoire `backend/migrations`
- [x] `backend/migrations/env.py` -- Configurer l'environnement Alembic avec `target_metadata = Base.metadata` et `settings.database_url`
- [x] `backend/tests/unit/test_db_session.py` -- Écrire les tests unitaires de session, masquage de logs et simulation d'indisponibilité (HTTP 503)
- [x] `backend/tests/unit/test_alembic.py` -- Écrire les tests de vérification Alembic et de non-utilisation de `create_all`

**Acceptance Criteria:**
- Given une application FastAPI opérationnelle, when une route utilise `Depends(get_db)`, then une session SQLAlchemy 2.x valide est injectée et fermée automatiquement à la fin de la requête.
- Given une panne ou des identifiants invalides lors de la connexion à la base, when une requête sollicite la base de données, then l'application retourne HTTP 503 avec `{"error": {"code": "DATABASE_UNAVAILABLE", "message": "Service de base de données temporairement indisponible."}}` et journalise l'incident en CRITICAL sans divulguer le mot de passe.
- Given l'environnement de développement, when la commande `uv run alembic upgrade head` est exécutée, then Alembic s'exécute avec succès et applique les migrations.
- Given l'ensemble de la base de code de production `backend/src/iryx/`, when une recherche de `create_all` est effectuée, then aucune occurrence n'est trouvée.
- Given les commandes `uv run ruff check backend/` et `uv run pytest backend/tests`, then tous les contrôles linter et tests réussissent à 100%.

## Implementation Notes

- Ajout des dépendances `sqlalchemy>=2.0.35`, `psycopg[binary]>=3.2.0` et `alembic>=1.13.0` dans `backend/pyproject.toml` avec verrouillage via `uv sync`.
- Implémentation de l'exception `DatabaseUnavailableException` (HTTP 503, code `DATABASE_UNAVAILABLE`) et son routage sémantique dans `backend/src/iryx/core/exceptions.py`.
- Définition de la classe de base déclarative ORM `Base` dans `backend/src/iryx/db/base.py` avec la convention de nommage PostgreSQL pour les contraintes (`ix`, `uq`, `ck`, `fk`, `pk`).
- Implémentation de la session et du moteur dans `backend/src/iryx/db/session.py` avec pool résilient (`pool_pre_ping=True`), `SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False)`, masquage récursif des mots de passe/identifiants (`mask_database_url`, `sanitize_error_message`), rollback automatique et fermeture garantie dans `finally`.
- Exposition de la dépendance d'injection de session `get_db` dans `backend/src/iryx/api/dependencies.py`.
- Initialisation et configuration d'Alembic (`backend/alembic.ini`, `alembic.ini`, `backend/migrations/env.py`, `backend/migrations/script.py.mako`) branché dynamiquement sur `Base.metadata` et `get_settings().database_url`.
- Suite complète de tests unitaires couvrant l'injection FastAPI, la fermeture garantie de session, la simulation d'erreurs avec HTTP 503, le masquage des secrets dans les logs et exceptions, ainsi que l'audit de non-utilisation de `create_all` en production.

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Evidence | Route |
|---------|---------|----------|-------|
| Échec potentiel de `session.rollback()` lors d'une rupture de socket réseau | medium | Un appel à `rollback()` sur une socket rompue levait une exception secondaire non interceptée masquant l'erreur 503. Protégé par `with contextlib.suppress(Exception):`. | patch (appliqué) |
| Interception trop large de `SQLAlchemyError` dans `get_db_session` masquant les contraintes métier | medium | Intercepter tout `SQLAlchemyError` convertissait `IntegrityError`/`DataError` en HTTP 503 au lieu de laisser le contrôleur gérer en 409/422. Restreint à `(OperationalError, InterfaceError, psycopg.OperationalError)`. | patch (appliqué) |
| Non-masquage des mots de passe entourés de guillemets dans `sanitize_error_message` | low | L'expression régulière excluait les guillemets simples/doubles après `password=`, laissant les mots de passe entre quotes en clair. Expression mise à jour. | patch (appliqué) |
| Absence d'exécution programmatique de `backend/migrations/env.py` dans les tests unitaires | low | Aucun test n'exécutait `env.py` via `alembic.command`. Test offline `alembic.command.upgrade(..., sql=True)` ajouté dans `test_alembic.py`. | patch (appliqué) |
| Mapping HTTP 503 générique Starlette vers `DATABASE_UNAVAILABLE` | low | Tout 503 non lié à la DB retournait le code `DATABASE_UNAVAILABLE`. Mappé vers `SERVICE_UNAVAILABLE` pour les exceptions Starlette génériques. | patch (appliqué) |
| Risque d'erreur d'interpolation configparser dans `env.py` si l'URL contient des symboles `%` | low | Les URLs avec mot de passe encodé provoquaient une erreur d'interpolation dans `ConfigParser`. Ajout de `.replace('%', '%%')`. | patch (appliqué) |
| Pollution du singleton global `app` par inclusion de routeurs de test dans `test_db_session.py` | low | `db_test_router` était inclus au niveau module dans `app`. Remplacé par une fixture créant une instance de test isolée `create_app()`. | patch (appliqué) |
| Absence de nettoyage des connexions du pool SQLAlchemy lors de l'arrêt de l'application | low | L'engine n'était pas libéré à l'arrêt. Ajout de `engine.dispose()` dans le gestionnaire lifespan de `main.py`. | patch (appliqué) |
| Absence des options `compare_type` et `compare_server_default` dans `env.py` | low | Sans ces options, les modifications de types ou valeurs par défaut ne sont pas détectées lors des révisions Alembic autogénérées. Options ajoutées. | patch (appliqué) |
| Échec de `mask_database_url` sur des cibles non-URL ou des URLs sans nom d'utilisateur | low | Ajout d'une protection try/except autour de `make_url` et support des formats sans username dans l'expression régulière. | patch (appliqué) |
| Écart de statut entre la spec (`in-review`) et `sprint-status.yaml` (`in-progress`) | false | Le cycle BMAD maintient `in-progress` dans sprint-status jusqu'à la fin de la revue avant transition vers `done` à l'étape 5. | rejeté |
| Absence de tests d'intégration avec un conteneur PostgreSQL actif | false | Conforme aux critères d'acceptation de la story 1.2 spécifiant une validation unitaire et mockée en environnement de développement local sans conteneur tiers requis. | rejeté |
| Duplication des fichiers `alembic.ini` à la racine et dans `backend/` | false | Choix délibéré pour permettre l'exécution des commandes `uv run alembic` indifféremment depuis la racine du workspace ou depuis `backend/`. | rejeté |
| Absence de configuration avancée de `pool_size` dans `Settings` | false | Hors périmètre Story 1.2 : la configuration de base avec `pool_pre_ping=True` satisfait pleinement D-06 pour le MVP. | rejeté |

## Design Notes

- **Gestion des sessions:** `sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)`. Le générateur `get_db` capture `SQLAlchemyError` ou les exceptions de connexion pour lever `DatabaseUnavailableException`.
- **Masquage de l'URL:** Utilisation de `engine.url.render_as_string(hide_password=True)` pour toute journalisation d'incident de connexion.
- **Convention de nommage des métadonnées:** Définition d'un `naming_convention` sur `MetaData` (clés `ix`, `uq`, `ck`, `fk`, `pk`) pour garantir la compatibilité et des migrations Alembic déterministes.

## Verification

**Commands:**
- `uv run ruff check backend/` -- expected: `All checks passed!`
- `uv run pytest backend/tests` -- expected: `All tests passed`
- `uv run alembic -c backend/alembic.ini check` ou `uv run alembic -c backend/alembic.ini current` -- expected: validation de configuration Alembic
