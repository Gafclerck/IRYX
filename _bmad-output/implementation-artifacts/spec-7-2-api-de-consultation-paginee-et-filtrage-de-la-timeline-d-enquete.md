---
title: "Story 7.2 : API de consultation paginée et filtrage de la Timeline d'enquête (NFR-PERF-07)"
type: 'feature'
created: '2026-11-25'
status: 'done'
baseline_revision: 'c92c5cf02280b3361db096830da6fd4ea39b6092'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-7-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Les investigations numériques génèrent des milliers d'événements techniques hétérogènes, rendant inopérante et risquée une restitution intégrale non paginée de la timeline sans capacités de filtrage temporel et technique ciblé.

**Approach:** Exposer un endpoint REST `GET /api/v1/cases/{case_id}/timeline` paginé avec filtres stricts (`start_time`, `end_time`, `tool_name`, `evidence_id`), adossé à un index composite relationnel `(case_id, timestamp_utc)` et protégé par `verify_case_access`, garantissant le respect absolu de l'Invariant 2 (projection purement calculée).

## Boundaries & Constraints

**Always:**
- Respect absolu de l'Invariant 2 : la timeline est une projection dynamique en lecture seule ; aucune méthode ni route ne permet d'ajouter, modifier ou supprimer des événements temporels manuellement.
- Cloisonnement strict multi-tenant : toute requête est soumise à la dépendance `verify_case_access` vérifiant l'appartenance de l'utilisateur à l'organisation du dossier (HTTP 401/403/404).
- Pagination conforme aux standards du projet : paramètres `limit` (défaut 50, borné entre 1 et 100), `offset` (>= 0), et métadonnées retournées `total`, `total_items`, `limit`, `offset`, `has_more`.
- Tri déterministe en temps universel : les événements sont strictement ordonnés par `timestamp_utc ASC, id ASC`.
- Validation stricte des fenêtres temporelles : si `start_time` et `end_time` sont fournis et que `start_time > end_time`, renvoyer une erreur HTTP 422 avec le message explicite `start_time must be before end_time`.
- Indexation SQL optimisée : migration Alembic créant un index composite `(case_id, timestamp_utc)` sur la table `observations` pour honorer NFR-PERF-07.

**Never:**
- Ne jamais permettre l'injection, la création ou la modification d'événements temporels arbitraires dans la timeline.
- Ne jamais charger l'intégralité non bornée des observations en mémoire lors d'une requête API paginée (le filtrage, le comptage et la pagination `LIMIT/OFFSET` doivent être exécutés au niveau SQL).
- Ne jamais exposer de données appartenant à un autre dossier ou à une autre organisation.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Consultation paginée nominale | `case_id` valide, `limit=50, offset=0` | HTTP 200 OK avec liste des 50 premiers événements ordonnés UTC, `total_items`, `limit=50`, `offset=0`, `has_more=true/false` | Aucun |
| Filtrage temporel valide | `start_time=2026-11-23T08:00:00Z`, `end_time=2026-11-23T12:00:00Z` | HTTP 200 OK avec uniquement les événements dont l'horodatage est compris dans l'intervalle `[start_time, end_time]` | Aucun |
| Inversion temporelle `start_time > end_time` | `start_time=2026-11-23T14:00:00Z`, `end_time=2026-11-23T10:00:00Z` | HTTP 422 Unprocessable Entity avec message `start_time must be before end_time` | ValidationException / HTTP 422 |
| Filtrage par outil | `tool_name=python-evtx` | HTTP 200 OK restreint aux observations issues de l'outil demandé | Aucun |
| Filtrage par preuve source | `evidence_id=<UUID>` | HTTP 200 OK restreint aux observations rattachées à cette preuve | Aucun |
| Pagination invalide | `limit=0` ou `limit=101` ou `offset=-1` | HTTP 422 Unprocessable Entity | ValidationException / HTTP 422 |
| Dossier inexistant | `case_id` inconnu dans la base | HTTP 404 Not Found via `verify_case_access` | CaseNotFoundException |
| Utilisateur non autorisé | Utilisateur d'une autre organisation | HTTP 403 Forbidden via `verify_case_access` | InsufficientPermissionsException |
| Requête non authentifiée | Pas de jeton JWT Bearer | HTTP 401 Unauthorized | UnauthorizedException |

</intent-contract>

## Code Map

- `backend/src/iryx/analytics/models.py` -- Ajout de l'index composite relationnel `ix_observations_case_id_timestamp_utc` sur la classe ORM `Observation`.
- `backend/migrations/versions/008_create_observations_case_id_timestamp_utc_index.py` -- Migration Alembic créant l'index composite sur `(case_id, timestamp_utc)`.
- `backend/src/iryx/analytics/schemas.py` -- Définition des schémas Pydantic `TimelineFilterParams` et `TimelineListResponse`.
- `backend/src/iryx/analytics/services.py` -- Implémentation de la méthode `get_paginated_timeline` au sein de `TimelineService`.
- `backend/src/iryx/analytics/router.py` -- Exposition de la route `GET /api/v1/cases/{case_id}/timeline` avec validation et dépendances de sécurité.
- `backend/src/iryx/analytics/__init__.py` -- Export des nouveaux schémas `TimelineFilterParams` et `TimelineListResponse`.
- `backend/src/iryx/core/exceptions.py` -- Prise en compte explicite du message d'erreur pour les inversions temporelles dans le gestionnaire de validation.
- `backend/tests/api/test_timeline_routes.py` -- Tests d'intégration API validant les statuts 200, 422, 401, 403, 404, la pagination et les filtres.

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/analytics/models.py` -- Déclarer l'index composite `ix_observations_case_id_timestamp_utc` dans `__table_args__` du modèle `Observation` -- Optimisation des requêtes ordonnées par dossier et date.
- [x] `backend/migrations/versions/008_create_observations_case_id_timestamp_utc_index.py` -- Rédiger la migration Alembic 008 ajoutant l'index `ix_observations_case_id_timestamp_utc` sur `observations` -- Persistance et schéma relationnel PostgreSQL.
- [x] `backend/src/iryx/analytics/schemas.py` -- Définir `TimelineFilterParams` et `TimelineListResponse` avec synchronisation `items`/`events` et `total`/`total_items` -- Contrats d'échange Pydantic v2 typés.
- [x] `backend/src/iryx/analytics/services.py` -- Implémenter la méthode `get_paginated_timeline` dans `TimelineService` avec filtres SQL, calcul de `has_more` et ordonnancement `timestamp_utc ASC, id ASC` -- Résolution performante et isolée des événements.
- [x] `backend/src/iryx/analytics/router.py` -- Déclarer la route `GET /api/v1/cases/{case_id}/timeline` protégée par `verify_case_access` -- Point d'accès REST public.
- [x] `backend/src/iryx/analytics/__init__.py` -- Exporter `TimelineFilterParams` et `TimelineListResponse` -- Interface publique du module analytics.
- [x] `backend/src/iryx/core/exceptions.py` -- Ajuster la capture de message pour `RequestValidationError` afin de restituer `start_time must be before end_time` lors des erreurs Pydantic -- Conformité aux critères d'acceptation.
- [x] `backend/tests/api/test_timeline_routes.py` -- Créer la suite de tests d'intégration API pour le endpoint de timeline -- Couverture complète des critères d'acceptation et cas limites.

**Acceptance Criteria:**
- Given une timeline comportant des milliers d'événements techniques pour un dossier donné, when l'analyste appelle `GET /api/v1/cases/{case_id}/timeline?start_time=2026-11-23T08:00:00Z&end_time=2026-11-23T12:00:00Z&limit=50&offset=0`, then le serveur répond HTTP 200 OK avec la liste des 50 événements de la plage horaire demandée ordonnés chronologiquement, avec les métadonnées `total_items`, `limit`, `offset` et `has_more`.
- Given le paramètre de requête `tool_name=python-evtx`, when l'appel est effectué, then les résultats retournés sont restreints aux seuls événements issus des journaux Windows.
- Given un paramètre `start_time` postérieur à `end_time`, when la requête est transmise, then le serveur retourne HTTP 422 avec le message explicite `start_time must be before end_time`.
- Given un utilisateur non autorisé ou sans accès au dossier, when il sollicite la timeline, then la requête est rejetée avec HTTP 401, 403 ou 404 via `verify_case_access`.
- Given l'Invariant 2, when l'API de consultation paginée est interrogée, then aucune opération de persistance ou d'altération de la timeline n'est permise ou exécutée.

## Spec Change Log

## Review Triage Log

### 2026-11-25 — Review pass
- verdicts: 23 findings — high 0, medium 7, low 14, false 2, maybe-false 0
- findings:
  - `[medium]` `[patch]` Calling get_paginated_timeline with positional arguments for limit or offset in _PaginatedTimelineDispatcher silently ignored them — Action : Support complet de tous les arguments positionnels (case_id, limit, offset, start_time, end_time, tool_name, evidence_id) sur classe et instance.
  - `[medium]` `[patch]` Passing non-UTC timezone-aware datetime to start_time or end_time filters in services.py was not converted to UTC with .astimezone(UTC) — Action : Normalisation systématique via .astimezone(UTC) pour les datetimes avec fuseau horaire.
  - `[low]` `[patch]` Passing empty string as tool_name filter parameter in services.py filtered for empty string — Action : Nettoyage et conversion des chaînes vides ou d'espaces en None.
  - `[low]` `[patch]` Global exception handler validation_exception_handler hardcoded domain message check — Action : Découplage généralisé pour extraire les messages d'erreur personnalisés de Pydantic (suppression du préfixe "Value error, ").
  - `[low]` `[patch]` Linter failures and line-length violations introduced by diff (Ruff E501 and B007) — Action : Correction des longueurs de ligne et renommage des variables de boucle inutilisées.
  - `[medium]` `[patch]` Missing dedicated Alembic migration test for migration 008 — Action : Création de backend/tests/unit/test_timeline_migration.py testant les métadonnées, le SQL offline upgrade/downgrade et l'inspection de schéma de l'index composite.
  - `[low]` `[patch]` Weakened single head assertions in existing migration tests (assert "008" in script_dir.get_heads()) — Action : Rétablissement de l'assertion stricte assert script_dir.get_heads() == ["008"].
  - `[medium]` `[patch]` Silent argument loss in _PaginatedTimelineDispatcher when passing positional parameters — Action : Traité avec le premier finding (support positionnel unifié).
  - `[false]` `[reject]` Payload duplication across items and events in TimelineListResponse doubles network bandwidth — Réfutation : Conforme aux Design Notes de la spécification pour offrir une flexibilité maximale et une rétrocompatibilité complète aux consommateurs d'API.
  - `[medium]` `[patch]` Asymmetric list synchronization bug in TimelineListResponse.sync_items_and_totals — Action : Correction de la logique de synchronisation pour propager les événements non vides vers les listes vides dans les deux sens.
  - `[false]` `[reject]` Dead validation code in TimelineService._execute_paginated_timeline — Réfutation : Défense en profondeur intentionnelle pour les invocations directes du service hors framework FastAPI.
  - `[medium]` `[patch]` Missing unit tests for TimelineService.get_paginated_timeline — Action : Ajout d'une suite de tests unitaires dédiée dans test_timeline_service.py couvrant l'ensemble des branches du service.
  - `[low]` `[patch]` Redundant database query when total == 0 or offset >= total — Action : Ajout d'un retour anticipé de page vide sans requête SQL superflue.
  - `[medium]` `[patch]` Incomplete timezone normalization in service query filtering — Action : Traité avec le second finding (conversion UTC universelle).
  - `[low]` `[patch]` Duplicated event projection mapping logic in TimelineService — Action : Extraction d'une méthode helper réutilisable _map_observation_to_event.
  - `[low]` `[patch]` Missing update to deferred-work.md for resolved Story 7.1 items — Action : Suppression des deux éléments différés résolus par la Story 7.2.
  - `[low]` `[patch]` OpenAPI tagging mismatch on timeline route (defaulted to Findings) — Action : Ajout explicite de tags=["Timeline"] sur le décorateur de route.
  - `[low]` `[patch]` Unchecked empty string handling for tool_name filter in schemas.py — Action : Ajout d'un validateur Pydantic convertissant les chaînes vides en None.
  - `[low]` `[patch]` Missing test coverage for edge cases in test_timeline_routes.py — Action : Ajout de cas de tests pour start_time == end_time, requêtes semi-bornées, filtres combinés et rôle VIEWER.
  - `[medium]` `[patch]` Deterministic tie-breaking order id ASC unverified for timeline events with identical timestamps — Action : Ajout de tests avec horodatages strictement identiques validant l'ordonnancement par id ASC.
  - `[medium]` `[patch]` Alembic migration 008 index creation and rollback unverified against database schema — Action : Traité avec la création de test_timeline_migration.py.
  - `[medium]` `[patch]` _PaginatedTimelineDispatcher discards positional arguments beyond case_id — Action : Traité avec le premier finding.
  - `[low]` `[patch]` validation_exception_handler couples core error handler to specific query parameter message — Action : Traité avec le quatrième finding.

## Design Notes

La requête SQL principale dans `TimelineService.get_paginated_timeline` utilise l'index composite `(case_id, timestamp_utc)` :
```python
stmt = (
    select(Observation, Evidence.original_name)
    .outerjoin(Evidence, Observation.source_id == Evidence.id)
    .where(
        Observation.case_id == case_id,
        Observation.timestamp_utc.is_not(None),
    )
)
if start_time:
    stmt = stmt.where(Observation.timestamp_utc >= start_time)
if end_time:
    stmt = stmt.where(Observation.timestamp_utc <= end_time)
if tool_name:
    stmt = stmt.where(Observation.tool_name == tool_name)
if evidence_id:
    stmt = stmt.where(Observation.source_id == evidence_id)

count_stmt = select(func.count(Observation.id)).where(...)
total = db.scalar(count_stmt) or 0

stmt = stmt.order_by(Observation.timestamp_utc.asc(), Observation.id.asc()).limit(limit).offset(offset)
```
Le modèle `TimelineListResponse` accepte à la fois `items` et `events` pour une flexibilité maximale des clients d'API.

## Verification

**Commands:**
- `uv run --project backend pytest backend/tests/api/test_timeline_routes.py` -- expected: Tous les tests d'intégration API de la timeline passent avec succès.
- `uv run --project backend pytest backend/tests/unit/test_alembic.py` -- expected: La migration Alembic 008 est valide avec un unique HEAD.
- `uv run --project backend pytest` -- expected: La suite de tests globale passe intégralement sans régression.

## Auto Run Result

### Résumé de l'implémentation
Conception et implémentation de l'API de consultation paginée et de filtrage de la Timeline d'investigation (`GET /api/v1/cases/{case_id}/timeline`). Le endpoint permet d'interroger la chronologie unifiée en respectant strictement l'Invariant 2 (projection en lecture pure exclusivement calculée à partir des observations techniques scellées). La pagination et les filtres (`start_time`, `end_time`, `tool_name`, `evidence_id`) sont exécutés au niveau SQL, adossés au nouvel index composite `(case_id, timestamp_utc)` créé par la migration Alembic 008.

### Fichiers modifiés
- `backend/src/iryx/analytics/models.py` : Déclaration de l'index composite relationnel `ix_observations_case_id_timestamp_utc` sur la classe `Observation`.
- `backend/migrations/versions/008_create_observations_case_id_timestamp_utc_index.py` : Migration Alembic 008 pour la création de l'index composite sur `observations(case_id, timestamp_utc)`.
- `backend/src/iryx/analytics/schemas.py` : Définition des schémas Pydantic `TimelineFilterParams` (avec validation d'intervalle et normalisation UTC) et `TimelineListResponse` (avec synchronisation `items`/`events` et métadonnées de pagination).
- `backend/src/iryx/analytics/services.py` : Méthode `get_paginated_timeline` dans `TimelineService` avec support des arguments positionnels et par mot-clé, ordonnancement strict UTC, exclusion des faits non datés, et évitement des requêtes SQL superflues.
- `backend/src/iryx/analytics/router.py` : Route REST `GET /api/v1/cases/{case_id}/timeline` protégée par `verify_case_access` avec tag `Timeline`.
- `backend/src/iryx/analytics/__init__.py` : Exportation publique des nouveaux schémas.
- `backend/src/iryx/core/exceptions.py` : Généralisation de `validation_exception_handler` pour extraire les messages d'erreurs Pydantic personnalisés.
- `backend/tests/api/test_timeline_routes.py` : Suite de 19 tests d'intégration API validant pagination, filtres, inversions temporelles, Invariant 2, et contrôle d'accès RBAC.
- `backend/tests/unit/test_timeline_migration.py` : Tests unitaires de la révision Alembic 008 (upgrade, downgrade, inspection de schéma).
- `backend/tests/unit/test_timeline_service.py` : Tests unitaires approfondis pour `TimelineService.get_paginated_timeline`.
- `backend/tests/unit/test_finding_migration.py` & `backend/tests/unit/test_investigation_migration.py` : Mise à jour de l'assertion de HEAD unique `008`.
- `_bmad-output/implementation-artifacts/deferred-work.md` : Résolution des deux éléments différés de la Story 7.1.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` : Mise à jour du statut de la story.

### Bilan de la revue
- **Correctifs appliqués (patch)** : 21 constats (7 medium, 14 low) traités avec succès (support positionnel, normalisation UTC, découplage des exceptions, linting/formatage, tests de migration et unitaires, tests de cas limites).
- **Éléments différés (defer)** : 0.
- **Constats rejetés (false)** :
  - Duplication `items`/`events` : Rejeté, comportement intentionnel documenté dans les Design Notes pour compatibilité et flexibilité des clients API.
  - Validation double dans le service : Rejeté, défense en profondeur intentionnelle pour les invocations directes en Python.

### Recommandation de revue de suivi
- **followup_review_recommended** : `true` (5 groupes de constats `medium` corrigés lors de la première passe).
- **Risque résiduel identifié** : Vérification en conditions de production de l'impact de l'index composite sous forte charge concurrente et volumétrie extrême (> 100 000 observations).

### Vérifications effectuées
- `uv run --project backend ruff check backend/src/iryx/analytics backend/src/iryx/core/exceptions.py backend/tests/api/test_timeline_routes.py backend/tests/unit/test_timeline_migration.py backend/tests/unit/test_timeline_service.py` : Succès (0 violation).
- `uv run --project backend pytest backend/tests/api/test_timeline_routes.py backend/tests/unit/test_timeline_migration.py backend/tests/unit/test_timeline_service.py backend/tests/unit/test_alembic.py` : 61 tests passés en 3.11s.
- `uv run --project backend pytest` : 812 tests passés en 59.02s (suite complète sans régression).
