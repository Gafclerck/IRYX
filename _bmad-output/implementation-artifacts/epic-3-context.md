# Epic 3 Context: Preuves et ingestion

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Implémenter le téléversement multipart des preuves numériques rattachées à un dossier d'investigation, leur scellement cryptographique par calcul d'empreinte SHA-256 (`hashlib`), la détection du type MIME réel par signatures binaires (`filetype`), le stockage sécurisé sur disque avec permissions en lecture seule strictes (`chmod 0440`), l'interdiction formelle d'écrasement physique, et la délégation asynchrone des traitements d'ingestion via Celery et Redis avec consultation d'avancement par polling REST (HTTP 202).

## Stories

- Story 3.1: Modèles `Evidence` et `IngestionRun`, migrations Alembic et configuration Celery/Redis
- Story 3.2: Endpoint de téléversement de preuves et protection contre l'écrasement (FR5, FR7)
- Story 3.3: Tâche Celery d'ingestion : scellement SHA-256, détection `filetype` et verrouillage lecture seule (FR6, FR7, NFR-SEC-01)
- Story 3.4: Consultation de l'état d'ingestion par polling REST et consultation des métadonnées (FR5, FR7)

## Requirements & Constraints

- **Modélisation relationnelle** : Tables `evidences` et `ingestion_runs` sous PostgreSQL 16 avec identifiants UUID et horodatages UTC.
- **Intégrité référentielle** : `case_id` pointe vers `cases.id` (avec suppression en cascade interdisant les preuves orphelines) et `imported_by` pointe vers `users.id`. `evidence_id` dans `ingestion_runs` pointe vers `evidences.id` (en cascade).
- **Statuts d'ingestion** : `pending`, `processing`, `completed`, `failed` avec progression de 0 à 100%.
- **Architecture asynchrone** : Worker Celery (>=5.4.0) connecté au broker Redis 7 (`CELERY_BROKER_URL`). En cas de Redis indisponible, journalisation JSON de l'erreur avec politique de reconnexion et backoff.
- **Intégrité et scellement (FR6, FR7, NFR-SEC-01)** : Calcul de l'empreinte SHA-256 par flux de blocs de 64 Ko (`hashlib.sha256()`) pour ne pas saturer la RAM, détection du format par signature binaire via `filetype` (D-15), verrouillage physique en lecture seule (`chmod 0440`) interdisant toute modification ou écrasement.
- **Sécurité et isolation (Zero Leak)** : Toute action sur une preuve est protégée par la dépendance `verify_case_access` (Story 2.4).
- **Qualité et conformité** : Ruff 0 warning / 0 erreur, typage strict, tests unitaires et d'intégration avec mocks pour Celery/Redis si nécessaire.

## Technical Decisions

- **D-03** : Framework API REST : FastAPI (>=0.115.0).
- **D-04** : Validation de schémas et configuration : Pydantic v2 (>=2.9.0) et `pydantic-settings` (>=2.5.0).
- **D-05** : Base de données relationnelle : PostgreSQL 16.
- **D-06** : ORM et pilote SQL : SQLAlchemy 2.x (>=2.0.35) avec `psycopg` 3 (>=3.2.0).
- **D-07** : Gestionnaire de migrations : Alembic (>=1.13.0) pour toute modification de schéma.
- **D-08** : Tâches de fond asynchrones : Celery (>=5.4.0) avec Redis 7 (>=7.0.0) comme courtier de messages (broker).
- **D-14** : Empreinte cryptographique : `hashlib` (SHA-256) standard Python.
- **D-15** : Détection du type de fichier : `filetype` (>=1.2.0) par signatures binaires sans dépendance système.
- **D-20** : Tests automatisés : `pytest` (>=8.3.0), `pytest-asyncio` (>=0.24.0), `httpx` (>=0.27.0).
- **D-23** : Journalisation : JSON structuré standard sans secrets.

## Cross-Story Dependencies

- E3 dépend d'E1 et E2 : L'authentification utilisateur (`get_current_user`), les dossiers (`Case`) et la dépendance `verify_case_access` sont déjà en place.
- Story 3.1 prépare les fondations relationnelles (`Evidence`, `IngestionRun`, migration Alembic 004) et la configuration Celery/Redis (`core/celery_app.py`).
- Story 3.2 s'appuie sur les modèles de 3.1 pour implémenter l'endpoint de téléversement multipart et l'envoi de la tâche Celery.
- Story 3.3 implémente la tâche Celery réelle de traitement (SHA-256, `filetype`, permissions lecture seule).
- Story 3.4 expose les endpoints de polling REST et de consultation des preuves.
