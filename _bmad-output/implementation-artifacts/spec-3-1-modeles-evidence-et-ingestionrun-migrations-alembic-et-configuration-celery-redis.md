---
title: 'Story 3.1: Modèles Evidence et IngestionRun, migrations Alembic et configuration Celery/Redis'
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: '29c07b9f058b7dc15887b598e0290449ea2578c1'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La plateforme IRYX ne dispose pas encore de modèles de données pour persister les preuves numériques (`Evidence`) et le suivi asynchrone de leur traitement (`IngestionRun`), ni de l'infrastructure de file de tâches asynchrones Celery/Redis requise pour absorber les traitements longs sans bloquer l'API.

**Approach:** Définir les modèles SQLAlchemy 2.0 `Evidence` et `IngestionRun` avec leurs contraintes relationnelles, créer et valider la migration Alembic `004_create_evidence_and_ingestion_tables`, exposer les schémas Pydantic v2 associés, et initialiser l'instance applicative Celery connectée au courtier Redis 7 avec gestion de reconnexion résiliente et journalisation structurée.

## Boundaries & Constraints

**Always:**
- Utiliser SQLAlchemy 2.0 avec typage strict `Mapped[...]` et `mapped_column(...)`, rattachés à `Base` (`iryx.db.base`).
- Clés primaires en UUIDv4 et horodatages en `DateTime(timezone=True)` avec valeur par défaut UTC.
- Intégrité référentielle stricte : suppression en cascade (`ondelete="CASCADE"`, `cascade="all, delete-orphan"`, `passive_deletes=True`) sur `case_id` (vers `cases.id`) et `evidence_id` (vers `evidences.id`). Pour `imported_by` (vers `users.id`), utiliser `ondelete="SET NULL"`.
- Migration Alembic bidirectionnelle stricte (`upgrade` et `downgrade`) enregistrée sous la révision `004` ayant `003` pour `down_revision`.
- Respecter les décisions d'architecture D-04, D-05, D-06, D-07, D-08.
- Configuration Celery centralisée dans `iryx.core.celery_app` exploitant `get_settings()` (`celery_broker_url`, `celery_result_backend`).
- Tolérance aux pannes : journaliser les échecs de connexion Redis au format JSON structuré et configurer la reconnexion avec backoff (`broker_connection_retry_on_startup=True`).

**Never:**
- Aucun appel à `metadata.create_all()` en dehors des fixtures de tests isolées.
- Aucun écrasement physique ni modification directe de preuve brute (intégrité forensique).
- Aucune logique de calcul SHA-256 ou d'inspection binaire dans cette story (réservée à Story 3.3).
- Aucun endpoint HTTP d'upload de fichier dans cette story (réservé à Story 3.2).
- Aucun composant ou dépendance non standard (pas de Flower, pas de bus Kafka).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Création Evidence nominale | `case_id`, `original_name`, `file_size`, `imported_by` valides | Instance persistée, `sha256` et `detected_type` nuls avant traitement, UUID généré | Rejet si `case_id` invalide ou absent (`IntegrityError`) |
| Création IngestionRun nominal | `evidence_id` valide, `status=pending` | Instance persistée, `progress=0`, `started_at` horodaté UTC, `completed_at=None` | Rejet si `evidence_id` invalide |
| Progression IngestionRun invalide | `progress < 0` ou `progress > 100` | Rejet par contrainte d'intégrité de la table | `IntegrityError` (CheckConstraint `ck_ingestion_runs_progress_range`) |
| Statut IngestionRun invalide | `status='unknown_status'` | Rejet par contrainte de vérification | `IntegrityError` (CheckConstraint `ck_ingestion_runs_status_check`) |
| Suppression en cascade du dossier | Suppression d'un `Case` ayant des preuves et runs | Preuves et IngestionRuns associées supprimées en cascade | Zéro preuve orpheline en base |
| Démarrage Celery avec Redis indisponible | Worker ou vérification de connectivité avec Redis éteint | Journalisation d'erreur JSON avec backoff sans crash silencieux | Trace structurée de l'erreur réseau |

</frozen-after-approval>

## Code Map

- `backend/pyproject.toml` -- Déclarer les dépendances `celery>=5.4.0` et `redis>=5.0.0`
- `backend/src/iryx/evidence/__init__.py` -- Package evidence
- `backend/src/iryx/evidence/models.py` -- Modèles ORM `Evidence` et `IngestionRun`, énumération `IngestionStatus`
- `backend/src/iryx/evidence/schemas.py` -- Schémas Pydantic v2 `EvidenceRead`, `IngestionRunRead`
- `backend/src/iryx/cases/models.py` -- Relation `evidences` bidirectionnelle sur le modèle `Case`
- `backend/src/iryx/core/celery_app.py` -- Configuration et instanciation du client/worker Celery avec résilience de connexion
- `backend/migrations/env.py` -- Import de `iryx.evidence.models` pour l'inspection des métadonnées Alembic
- `backend/migrations/versions/004_create_evidence_and_ingestion_tables.py` -- Migration Alembic pour les tables `evidences` et `ingestion_runs`
- `backend/tests/unit/test_evidence_models.py` -- Tests unitaires des modèles `Evidence` et `IngestionRun`, relations, cascades et contraintes
- `backend/tests/unit/test_evidence_migration.py` -- Tests de migration Alembic 004 (upgrade, downgrade, inspection schéma)
- `backend/tests/unit/test_celery_config.py` -- Tests de configuration Celery, options de résilience et gestion de courtier injoignable

## Tasks & Acceptance

**Execution:**
- [x] `backend/pyproject.toml` -- Ajouter les dépendances `celery>=5.4.0` et `redis>=5.0.0` -- Support de l'orchestration asynchrone D-08
- [x] `backend/src/iryx/evidence/models.py` -- Créer les modèles ORM `Evidence` et `IngestionRun` avec contraintes et index -- Persistance relationnelle des preuves et exécutions
- [x] `backend/src/iryx/cases/models.py` -- Ajouter la relation `evidences` avec cascade `all, delete-orphan` sur `Case` -- Prévention des preuves orphelines
- [x] `backend/src/iryx/evidence/schemas.py` -- Définir les schémas Pydantic v2 `EvidenceRead` et `IngestionRunRead` -- Typage et sérialisation des entités
- [x] `backend/src/iryx/core/celery_app.py` -- Créer l'application Celery avec configuration broker Redis et résilience -- Infrastructure de tâches d'arrière-plan
- [x] `backend/migrations/env.py` -- Importer `iryx.evidence.models` dans le script d'environnement de migration -- Prise en compte dans autogenerate et migrations
- [x] `backend/migrations/versions/004_create_evidence_and_ingestion_tables.py` -- Rédiger la migration Alembic réversible 004 -- Évolution traçable du schéma PostgreSQL
- [x] `backend/tests/unit/test_evidence_models.py` -- Écrire les tests unitaires pour les modèles `Evidence` et `IngestionRun` -- Validation des attributs, enums, cascades et contraintes
- [x] `backend/tests/unit/test_evidence_migration.py` -- Écrire les tests de migration pour la révision 004 -- Validation du cycle de vie DDL Alembic
- [x] `backend/tests/unit/test_celery_config.py` -- Écrire les tests de validation de la configuration Celery et de gestion d'erreur Redis -- Vérification de la conformité D-08

**Acceptance Criteria:**
- Given la migration Alembic `004_create_evidence_and_ingestion_tables` appliquée, when les tables sont inspectées, then `evidences` et `ingestion_runs` contiennent toutes les colonnes, contraintes et index requis.
- Given une instance `Case` supprimée, when la suppression est validée en base, then toutes les entités `Evidence` et `IngestionRun` associées sont supprimées en cascade sans orphelins.
- Given une tentative d'insertion d'un `IngestionRun` avec un `progress` hors intervalle [0, 100] ou un `status` invalide, when la transaction est validée, then une `IntegrityError` est levée.
- Given la configuration de Celery, when `celery_app` est inspectée, then elle utilise `settings.celery_broker_url`, `settings.celery_result_backend` et active `broker_connection_retry_on_startup`.

## Implementation Notes

## Spec Change Log

## Review Triage Log

| Ref | Source | Verdict | Evidence / Justification | Route |
|-----|--------|---------|--------------------------|-------|
| F01 | edge-case-hunter / blind-hunter | high | `configure_mappers()` échoue avec `UnmappedClassError` ou `InvalidRequestError` si `iryx.evidence.models` est importé sans `iryx.cases.models` ou inversement. | patch |
| F02 | edge-case-hunter / blind-hunter | medium | `mask_broker_url` ne masque que `parsed.password`, laissant les tokens passés en username ou requêtes exposés ; utiliser `kombu.utils.url.sanitize_url`. | patch |
| F03 | edge-case-hunter / blind-hunter | medium | L'entité `Evidence` et la migration 004 ne possèdent pas de `CheckConstraint("file_size >= 0")`, autorisant des tailles négatives invalides. | patch |
| F04 | blind-hunter | false | `updated_at` sur `Evidence` : la documentation d'architecture sanctuarise l'immutabilité de l'artefact de preuve (`Evidence` n'a volontairement que `created_at`). | rejet |
| F05 | blind-hunter | low | Contrainte temporelle `completed_at >= started_at` sur `IngestionRun` : cohérence chronologique additionnelle. | patch |
| F06 | blind-hunter | false | `IngestionRun.status` sur `String(32)` : correspond au standard architectural IRYX (StrEnum sur colonne String avec CheckConstraint). | rejet |
| F07 | blind-hunter | medium | Absence de `autodiscover_tasks` sur Celery : les futures tâches des packages d'investigation ne seront pas découvertes par le worker. | patch |
| F08 | blind-hunter | low | Paramètres de worker Celery pour gros artefacts : ajout de `worker_prefetch_multiplier = 1` et `task_acks_late = True`. | patch |
| F09 | blind-hunter | low | Fuite potentielle d'URL dans `logger.error` : s'assurer que les messages d'erreur ne répètent pas l'URL non masquée. | patch |
| F10 | blind-hunter | false | Intégration de `check_broker_connection` dans `/health` : hors périmètre de Story 3.1 (interdiction formelle de toucher aux routes API dans cette story). | rejet |
| F11 | blind-hunter | low | Index sur colonnes temporelles : ajout d'un index sur `created_at` dans `evidences`. | patch |
| F12 | blind-hunter | low | Validation de `EvidenceRead` : ajout de `min_length=1` pour `original_name` et `ge=0` pour `file_size`. | patch |
| F13 | blind-hunter | false | Heartbeat / updated_at sur `IngestionRun` : non présent dans les spécifications relationnelles D-05. | rejet |
| F14 | blind-hunter | false | Schéma `EvidenceRead` sans état d'ingestion : l'ingestion est interrogée via l'endpoint de polling dédié FR5/FR7. | rejet |
| F15 | blind-hunter | low | Check constraint dynamique : utilisation de l'énumération pour construire la contrainte SQL. | patch |
| F16 | blind-hunter | false | Instanciation module-level de Celery : standard officiel Celery. | rejet |

## Design Notes

L'application Celery est instanciée via `celery_app = Celery("iryx", broker=settings.celery_broker_url, backend=settings.celery_result_backend)`.
La configuration inclut :
```python
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
)
```
Une fonction utilitaire `check_broker_connection(timeout: float = 2.0) -> bool` teste la connectivité réseau au broker et consigne un log JSON structuré en cas d'échec pour respecter l'exigence d'alerte sans plantage silencieux.

## Verification

**Commands:**
- `cd backend && uv run pytest tests/unit/test_evidence_models.py tests/unit/test_evidence_migration.py tests/unit/test_celery_config.py` -- expected: Tous les tests unitaires passent avec succès (100% passés)
- `cd backend && uv run ruff check src tests` -- expected: 0 erreur, 0 avertissement
- `cd backend && uv run pytest` -- expected: L'ensemble de la suite de tests (241+ tests) passe sans régression
