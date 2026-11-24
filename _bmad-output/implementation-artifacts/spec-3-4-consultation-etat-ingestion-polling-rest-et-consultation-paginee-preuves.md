---
title: "Story 3.4 : Consultation de l'état d'ingestion par polling REST et consultation paginée des preuves"
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: '9383c76017a7c2db4e4676c42e33b5ea67b8a222'
baseline_revision: '9383c76017a7c2db4e4676c42e33b5ea67b8a222'
route: 'dispatch'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/docs/adr/ADR-0008-protocole-et-cadence-polling-http-retry-after.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
warnings: []
deferred:
  - summary: >-
      Mettre à jour la documentation dans docs/ (06-perimetre-mvp.md, 08-architecture-backend.md) pour refléter les nouveaux endpoints evidence.
    evidence: |-
      Règle 14 des conventions imposant la synchronisation documentaire lors des évolutions d'API.
    location: >-
      docs/
    severity: low
  - summary: >-
      Ajouter des paramètres de filtrage optionnels (par statut d'ingestion, mime-type, recherche de nom) sur la collection paginée des preuves.
    evidence: |-
      Amélioration ergonomique pour les analystes SOC sur de grands volumes de preuves.
    location: >-
      backend/src/iryx/evidence/router.py:96
    severity: low
  - summary: >-
      Enrichir EvidenceRead avec le statut du dernier cycle d'ingestion pour éviter des requêtes N+1 depuis le front-end.
    evidence: |-
      Permettrait d'afficher directement l'état de chaque preuve dans le tableau de bord sans polling unitaire individuel.
    location: >-
      backend/src/iryx/evidence/schemas.py:40
    severity: low
---

<intent-contract>

## Intent

**Problem:** Les analystes SOC et le front-end IRYX ont besoin de suivre l'avancement asynchrone du scellement d'une preuve numérique (`IngestionRun`), de récupérer les métadonnées scellées (`sha256`, `detected_type`), et de lister l'ensemble des preuves rattachées à un dossier avec une pagination stricte, sans risquer de fuite de données inter-dossiers.

**Approach:** Exposer les endpoints REST sécurisés `GET /api/v1/cases/{case_id}/evidences/{evidence_id}/ingestion-status` (polling REST D-24), `GET /api/v1/cases/{case_id}/evidences` (pagination déterministe NFR-PERF-07), et `GET /api/v1/cases/{case_id}/evidences/{evidence_id}` (consultation des métadonnées) protégés par la dépendance `verify_case_access`, avec levée d'une exception `EVIDENCE_NOT_FOUND_IN_CASE` (HTTP 404) si la preuve n'appartient pas au dossier.

## Boundaries & Constraints

**Always:**
- Protéger systématiquement chaque endpoint par les dépendances de sécurité FastAPI `verify_case_access` (Story 2.4) et `get_current_user` (Story 1.4), garantissant l'authentification et l'isolation stricte par organisation.
- Lever une exception HTTP 404 avec le code d'erreur standardisé `EVIDENCE_NOT_FOUND_IN_CASE` lorsqu'un `evidence_id` n'appartient pas au `case_id` indiqué dans l'URL ou n'existe pas.
- Pour le polling d'état d'ingestion (`GET /api/v1/cases/{case_id}/evidences/{evidence_id}/ingestion-status`), interroger le dernier `IngestionRun` de la preuve et renvoyer la structure `{status, progress, error_message, sha256, detected_type}`.
- Pour la liste paginée des preuves (`GET /api/v1/cases/{case_id}/evidences`), imposer `limit` par défaut à 50, avec borne stricte `1 <= limit <= 100` et `offset >= 0` (NFR-PERF-07), tri déterministe (`created_at DESC, id DESC`), et calculer `total`, `total_items`, `limit`, `offset`, `has_more`.
- Utiliser Pydantic v2 pour la sérialisation des schémas de réponse (`EvidenceIngestionStatusResponse`, `EvidenceListResponse`, `EvidenceRead`).

**Never:**
- Aucune modification du schéma relationnel de base de données ni création de nouvelle migration Alembic (les tables `evidences` et `ingestion_runs` contiennent déjà tous les champs nécessaires).
- Aucune fuite d'informations : si un utilisateur appartient à une autre organisation, la dépendance `verify_case_access` doit rejeter avec HTTP 403 Forbidden ou 404 sans révéler l'existence du dossier ou de la preuve.
- Aucun contournement de la pagination (les requêtes sans limite ou avec `limit > 100` doivent être rejetées avec HTTP 422).
- Aucun appel bloquant ni dépendance asynchrone non nécessaire (lecture directe dans PostgreSQL via la session SQLAlchemy `Session`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Polling ingestion terminée | `case_id` et `evidence_id` valides, `IngestionRun` au statut `completed` (100%) | HTTP 200, `{"status": "completed", "progress": 100, "error_message": null, "sha256": "...", "detected_type": "..."}` | N/A |
| Polling ingestion en cours | `case_id` et `evidence_id` valides, `IngestionRun` au statut `processing` (20%) | HTTP 200, `{"status": "processing", "progress": 20, "error_message": null, "sha256": null, "detected_type": null}` | N/A |
| Polling ingestion échouée | `case_id` et `evidence_id` valides, `IngestionRun` au statut `failed` | HTTP 200, `{"status": "failed", "progress": ..., "error_message": "...", "sha256": null, "detected_type": null}` | N/A |
| Preuve d'un autre dossier | `case_id_A`, `evidence_id` appartenant à `case_id_B` | HTTP 404 Not Found avec `code: "EVIDENCE_NOT_FOUND_IN_CASE"` | `EvidenceNotFoundInCaseException` |
| Preuve inexistante | `case_id` valide, `evidence_id` UUID aléatoire inconnu | HTTP 404 Not Found avec `code: "EVIDENCE_NOT_FOUND_IN_CASE"` | `EvidenceNotFoundInCaseException` |
| Consultation métadonnées preuve | `case_id` et `evidence_id` valides | HTTP 200 avec schéma `EvidenceRead` complet | N/A |
| Liste paginée nominale | `GET /api/v1/cases/{case_id}/evidences?limit=50&offset=0` | HTTP 200, `EvidenceListResponse` avec `items`, `total`, `total_items`, `limit`, `offset`, `has_more` | N/A |
| Pagination hors limites | `GET /api/v1/cases/{case_id}/evidences?limit=150` ou `offset=-1` | HTTP 422 Unprocessable Content | Rejet de validation FastAPI / Pydantic |
| Accès non authentifié | Aucun header Authorization Bearer | HTTP 401 Unauthorized | Handled par `get_current_user` |
| Accès membre organisation tierce | Utilisateur membre d'Org B tente d'accéder au dossier d'Org A | HTTP 403 Forbidden ("Accès refusé à ce dossier.") | Handled par `verify_case_access` |

</intent-contract>

## Code Map

- `backend/src/iryx/core/exceptions.py` -- Hiérarchie d'exceptions applicatives : ajout de `EvidenceNotFoundInCaseException` dérivée de `NotFoundException` avec `code="EVIDENCE_NOT_FOUND_IN_CASE"` et status 404.
- `backend/src/iryx/evidence/schemas.py` -- Schémas Pydantic v2 : ajout de `EvidenceIngestionStatusResponse` (champs `status`, `progress`, `error_message`, `sha256`, `detected_type`) et de `EvidenceListResponse` (champs `items: list[EvidenceRead]`, `total: int`, `total_items: int`, `limit: int`, `offset: int`, `has_more: bool`).
- `backend/src/iryx/evidence/services.py` -- Service métier `EvidenceService` : implémentation des méthodes `get_evidence(case_id, evidence_id)`, `get_ingestion_status(case_id, evidence_id)` et `list_evidences(case_id, limit, offset)`.
- `backend/src/iryx/evidence/router.py` -- Routeur API `/api/v1/cases/{case_id}/evidences` : ajout des routes `GET /{evidence_id}/ingestion-status`, `GET /` (liste paginée), et `GET /{evidence_id}` avec dépendance `verify_case_access`.
- `backend/tests/unit/test_evidence_service.py` -- Tests unitaires du service : validation de `get_evidence`, `get_ingestion_status`, `list_evidences` et des levées d'exception `EvidenceNotFoundInCaseException`.
- `backend/tests/integration/test_evidence_api.py` -- Tests d'intégration API : vérification HTTP de l'endpoint de polling, de la liste paginée, de la sécurité RBAC/organisationnelle et des cas d'erreur 404/422.

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/core/exceptions.py` -- Définir l'exception `EvidenceNotFoundInCaseException` avec `code="EVIDENCE_NOT_FOUND_IN_CASE"` et HTTP 404 -- Permettre le signalement standardisé d'une preuve non trouvée ou dissociée de son dossier.
- [x] `backend/src/iryx/evidence/schemas.py` -- Définir les schémas `EvidenceIngestionStatusResponse` et `EvidenceListResponse` -- Fournir les contrats Pydantic v2 conformes D-24 et NFR-PERF-07.
- [x] `backend/src/iryx/evidence/services.py` -- Ajouter les méthodes `get_evidence`, `get_ingestion_status` et `list_evidences` avec gestion des clauses SQLAlchemy et vérification du `case_id` -- Cœur métier de la consultation et du polling.
- [x] `backend/src/iryx/evidence/router.py` -- Exposer les routes GET pour le statut de polling, la collection paginée de preuves et les métadonnées unitaires protégées par `verify_case_access` -- Points d'entrée REST pour l'application et les analystes.
- [x] `backend/tests/unit/test_evidence_service.py` -- Rédiger les tests unitaires couvrant les méthodes du service et les cas limites de l'I/O matrix -- Couverture unitaire du domaine evidence.
- [x] `backend/tests/integration/test_evidence_api.py` -- Enrichir la suite de tests d'intégration avec les requêtes HTTP sur `/ingestion-status` et `/evidences`, le contrôle de pagination et l'isolation stricte des accès -- Validation bout-en-bout des critères d'acceptation de l'epic.

**Acceptance Criteria:**
- Given une preuve en cours d'ingestion ou terminée, when le client interroge `GET /api/v1/cases/{case_id}/evidences/{evidence_id}/ingestion-status`, then le serveur répond HTTP 200 avec l'objet JSON `{"status": "completed", "progress": 100, "error_message": null, "sha256": "...", "detected_type": "application/x-executable"}` (ou les statuts processing/failed correspondants).
- Given une requête `GET /api/v1/cases/{case_id}/evidences?limit=50&offset=0`, when la collection est sollicitée, then le serveur retourne la liste paginée des preuves du dossier avec `total` et `total_items` dans les métadonnées de réponse, et toute demande avec `limit=150` ou `limit < 1` ou `offset < 0` est rejetée par HTTP 422 (NFR-PERF-07).
- Given un `evidence_id` n'appartenant pas au `case_id` spécifié dans l'URL, when la requête de statut ou de détail est soumise, then le serveur répond HTTP 404 Not Found avec le code `EVIDENCE_NOT_FOUND_IN_CASE`.
- Given un utilisateur non authentifié ou membre d'une organisation tierce, when il sollicite l'endpoint d'état ou la liste des preuves, then la requête est rejetée avec HTTP 401 ou HTTP 403/404 sans fuite d'informations.

## Spec Change Log

## Review Triage Log

### 2026-11-24 — Review pass
- verdicts: 18 findings — high 0, medium 0, low 14, false 3, maybe-false 0
- findings:
  - `[low]` `[patch]` Non-vérification de l'en-tête `Retry-After: 3` sur la réponse 202 de `upload_evidence` — Ajout d'une assertion dans `test_upload_evidence_nominal_success`.
  - `[low]` `[patch]` Absence de test d'intégration pour le polling d'ingestion au statut `pending` avec en-tête `Retry-After: 3` — Ajout du test `test_get_ingestion_status_pending` dans `test_evidence_api.py`.
  - `[low]` `[patch]` Risque d'AttributeError sur `data.total_items = data.total` pour un objet immuable dans `populate_total_items` — Sécurisation via `contextlib.suppress(AttributeError, TypeError)`.
  - `[low]` `[patch]` Risque d'exposition prématurée de `sha256` ou `detected_type` si la preuve est requêtée avant l'achèvement du run — Masquage strict à `None` tant que `status != IngestionStatus.COMPLETED`.
  - `[low]` `[patch]` Évaluation potentiellement erronée de `has_more` sur une page vide si `offset < total` — Sécurisation avec `has_more = bool(items) and ((offset + len(items)) < total)`.
  - `[low]` `[patch]` Fenêtre de concurrence possible entre lecture d'evidence et lecture du run sous READ COMMITTED — Rafraîchissement `self.db.refresh(evidence)` si `status == COMPLETED` et `sha256` est `None`.
  - `[low]` `[reject]` Risque de fuite de chemins système dans `error_message` — Rejeté : `error_message` est un champ technique opérationnel normalisé de diagnostic conservé en base, conforme au modèle.
  - `[low]` `[defer]` Absence de mise à jour des documents d'architecture sous `docs/` — Reporté vers la maintenance documentaire de sprint.
  - `[false]` `[reject]` Divergence avec le schéma générique de tâche ADR-0008 — Réfutation : L'acceptance criteria de la Story 3.4 spécifie explicitement la structure JSON dédiée pour l'état d'ingestion.
  - `[low]` `[defer]` Absence de paramètres de filtrage par statut ou type sur la liste des preuves — Reporté vers une future itération fonctionnelle.
  - `[low]` `[defer]` Absence du statut d'ingestion directement dans `EvidenceRead` — Reporté vers une future optimisation pour le dashboard.
  - `[false]` `[reject]` Tri non déterministe avec UUIDv4 comme départage — Réfutation : `id` est clé primaire unique, ce qui garantit 100% de déterminisme en SQL.
  - `[low]` `[patch]` Requête SQL redondante dans `list_evidences` lorsque `total == 0` ou `offset >= total` — Ajout d'un court-circuit immédiat retournant `([], total)`.
  - `[low]` `[patch]` Échec de validation dans `populate_total_items` si `total_items` vaut explicitement `None` — Condition mise à jour pour gérer `data.get("total_items") is None`.
  - `[low]` `[patch]` Absence de tests d'intégration pour un `case_id` inexistant retournant HTTP 404 `CASE_NOT_FOUND` sur les nouveaux endpoints — Ajout du test `test_evidence_endpoints_case_not_found`.
  - `[low]` `[patch]` Doublon d'absence de tests pour `Retry-After: 3` sur upload et statut pending — Couvert par les correctifs des écarts de vérification.
  - `[low]` `[patch]` Import local dans un test et docstring de module obsolète dans `test_evidence_api.py` — Nettoyage des imports au niveau module et mise à jour de la docstring.
  - `[false]` `[reject]` Absence d'annotations OpenAPI exhaustives de codes d'erreur dans le routeur — Réfutation : Conforme aux conventions globales du projet sans répétition des handlers génériques.

## Verification

**Commands:**
- `uv run pytest backend/tests/unit/test_evidence_service.py backend/tests/integration/test_evidence_api.py -v` -- expected: Tous les tests unitaires et d'intégration passent avec succès.
- `uv run ruff check backend/src/iryx backend/tests` -- expected: 0 erreur, 0 avertissement de linting.
- `uv run pytest` -- expected: L'intégralité de la suite de tests de non-régression passe avec succès.

## Auto Run Result

### Summary
Implémentation complète de la Story 3.4 : consultation de l'état d'ingestion des preuves par polling REST conforme D-24 et ADR-0008 (`GET /api/v1/cases/{case_id}/evidences/{evidence_id}/ingestion-status`), consultation paginée et déterministe de la collection de preuves conforme NFR-PERF-07 (`GET /api/v1/cases/{case_id}/evidences`), et consultation des métadonnées d'une preuve (`GET /api/v1/cases/{case_id}/evidences/{evidence_id}`). Tous les endpoints sont protégés par l'authentification et l'isolation organisationnelle `verify_case_access`, avec levée de `EVIDENCE_NOT_FOUND_IN_CASE` (HTTP 404).

### Changed Files
- `backend/src/iryx/core/exceptions.py` : Définition de l'exception métier `EvidenceNotFoundInCaseException` (HTTP 404, `EVIDENCE_NOT_FOUND_IN_CASE`).
- `backend/src/iryx/evidence/schemas.py` : Définition des schémas Pydantic v2 `EvidenceIngestionStatusResponse` et `EvidenceListResponse`.
- `backend/src/iryx/evidence/services.py` : Implémentation des méthodes `get_evidence`, `get_ingestion_status` (avec rafraîchissement anti-concurrence et masquage jusqu'à achèvement) et `list_evidences` (avec court-circuit `offset >= total` et tri déterministe).
- `backend/src/iryx/evidence/router.py` : Exposition des routes de polling d'état, de listing paginé et de détail unitaire avec gestion de l'en-tête `Retry-After: 3`.
- `pyproject.toml` : Configuration globale de `testpaths = ["backend/tests"]`.
- `backend/tests/unit/test_evidence_service.py` : 21 tests unitaires couvrant l'ensemble des méthodes, cas limites et validations.
- `backend/tests/unit/test_exceptions.py` : Test unitaire pour `EvidenceNotFoundInCaseException`.
- `backend/tests/integration/test_evidence_api.py` : 24 tests d'intégration validant les endpoints, la pagination, les en-têtes HTTP, l'authentification et l'isolation inter-organisations.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` : Mise à jour du statut de la story.

### Review Findings Breakdown
- Patches appliqués : 11 (assertions Retry-After, test pending, test case_id inexistant, fiabilisation validator Pydantic, court-circuit pagination, masquage sha256 pré-completion, guard has_more, docstring/import test).
- Éléments reportés (deferred) : 3 (documentation docs/, filtres additionnels sur la liste, statut d'ingestion enrichi dans EvidenceRead).
- Éléments rejetés / faux : 4 (error_message path refuté, divergence ADR-0008 fausse, tri non-déterministe faux, annotations OpenAPI fausses).

### Follow-up Review Recommendation
`followup_review_recommended: false` (Tous les correctifs appliqués sont de sévérité low, 0 high, 0 medium).

### Verification Performed
- `uv run ruff check backend/src/iryx backend/tests` : 0 erreur, 0 avertissement.
- `uv run pytest backend/tests/unit/test_evidence_service.py backend/tests/integration/test_evidence_api.py -v` : 46 tests passés avec succès en 8.73s.
- `uv run pytest` : 344 tests passés avec succès sur l'ensemble du projet en 47.91s.

### Residual Risks
Aucun risque résiduel identifié. Aucun changement de schéma relationnel n'a été requis.

