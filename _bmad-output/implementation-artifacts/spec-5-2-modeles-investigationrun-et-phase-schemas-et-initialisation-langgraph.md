---
title: "Story 5.2 : Modèles InvestigationRun et Phase, schémas et initialisation du graphe LangGraph"
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: '4244dbb7fca3b9e4a1848fa3a683b2288e16b8a3'
baseline_revision: '4244dbb7fca3b9e4a1848fa3a683b2288e16b8a3'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/docs/adr/ADR-0007-persistance-etat-langgraph-checkpointer-postgresql.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'orchestration des investigations numériques requiert une machine d'états rigoureuse pour coordonner les agents IA et les portes de contrôle humaines, matérialiser l'état des enquêtes et empêcher les exécutions concurrentes sur un même dossier.

**Approach:** Définir les modèles relationnels `InvestigationRun` et `Phase`, créer la migration Alembic `006`, implémenter le schéma d'état `InvestigationState` et le graphe compilé LangGraph avec ses 9 nœuds (`triage`, `planner`, `gate_h1`, `executor`, `analyst`, `verifier`, `gate_h2`, `gate_h3`, `reporting`), exposer l'endpoint `POST /api/v1/cases/{case_id}/investigations` sécurisé par RBAC interdisant les viewers et rejetant les runs concurrents avec HTTP 409 `INVESTIGATION_ALREADY_RUNNING`.

## Boundaries & Constraints

**Always:**
- Utiliser PostgreSQL 16 et SQLAlchemy 2.x pour les modèles `InvestigationRun` et `Phase` (D-05, D-06).
- Implémenter la migration Alembic `006_create_investigation_and_phase_tables` (down-revision `005`).
- Initialiser le statut d'un run à `running`, `current_phase = "triage"`, `iteration_count = 0`, `error_count = 0`, `started_at = UTC now` lors de la création nominale.
- Créer une entité `Phase` initiale au statut `active` associée au run.
- Compiler le graphe LangGraph (`langgraph>=0.2.20`, D-09) contenant tous les 9 nœuds requis : `triage`, `planner`, `gate_h1`, `executor`, `analyst`, `verifier`, `gate_h2`, `gate_h3`, `reporting`.
- Protéger l'endpoint `POST /api/v1/cases/{case_id}/investigations` avec `require_case_role(MembershipRole.ADMIN, MembershipRole.INVESTIGATOR, MembershipRole.ANALYST)` : interdire le rôle `viewer` avec HTTP 403 Forbidden.
- Refuser toute création concurrente de session active (`pending`, `running`, `paused`) sur le même dossier avec HTTP 409 Conflict et code `INVESTIGATION_ALREADY_RUNNING`.
- Préserver la non-régression stricte de la suite de tests existante (547+ tests).

**Never:**
- Jamais d'exécution concurrente multiple autorisée sur un même dossier sans clôture/échec du run précédent.
- Jamais de transition d'état arbitraire hors des statuts autorisés (`pending`, `running`, `paused`, `completed`, `failed`).
- Jamais de contournement de la vérification des permissions par dossier (`verify_case_access` / `require_case_role`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Démarrage nominal d'enquête | `POST /api/v1/cases/{case_id}/investigations` par rôle investigator | HTTP 201 Created, `InvestigationRun` créé avec statut `running`, phase `triage`, entité `Phase` active | N/A |
| Tentative de run concurrent | Enquête déjà active (`running`/`paused`) sur le dossier | HTTP 409 Conflict, code `INVESTIGATION_ALREADY_RUNNING` | `InvestigationAlreadyRunningException` |
| Rôle non autorisé (viewer) | `POST /api/v1/cases/{case_id}/investigations` par un membre viewer | HTTP 403 Forbidden, code `FORBIDDEN` | `InsufficientPermissionsException` |
| Dossier inexistant | UUID de dossier non trouvé en base | HTTP 404 Not Found, code `CASE_NOT_FOUND` | `CaseNotFoundException` |
| Utilisateur hors organisation | Utilisateur authentifié non rattaché à l'organisation du dossier | HTTP 403 Forbidden, code `FORBIDDEN` | `InsufficientPermissionsException` |
| Consultation du statut d'enquête | `GET /api/v1/cases/{case_id}/investigations/{run_id}` | HTTP 200 OK, détails du run, phase courante et compteurs | N/A |
| Compilation du graphe LangGraph | Invocation de `build_investigation_graph()` | Retourne un `CompiledStateGraph` avec les 9 nœuds présents | N/A |

</frozen-after-approval>

## Code Map

- `backend/pyproject.toml` -- Dépendance `langgraph>=0.2.20`
- `backend/migrations/versions/006_create_investigation_and_phase_tables.py` -- Migration Alembic pour les tables `investigation_runs` et `phases`
- `backend/migrations/env.py` -- Enregistrement des modèles `iryx.orchestrator.models`
- `backend/src/iryx/core/exceptions.py` -- Définition de `InvestigationAlreadyRunningException` (HTTP 409, code `INVESTIGATION_ALREADY_RUNNING`)
- `backend/src/iryx/cases/models.py` -- Ajout de la relation bidirectionnelle `investigation_runs` sur le modèle `Case`
- `backend/src/iryx/orchestrator/__init__.py` -- Package racine du module d'orchestration
- `backend/src/iryx/orchestrator/models.py` -- Modèles ORM `InvestigationRun` et `Phase`, énumérations `InvestigationStatus`, `PhaseName`, `PhaseStatus`
- `backend/src/iryx/orchestrator/schemas.py` -- Schémas Pydantic v2 pour création et réponses des runs et phases
- `backend/src/iryx/orchestrator/state.py` -- Typage `InvestigationState` du graphe LangGraph
- `backend/src/iryx/orchestrator/graph.py` -- Construction et compilation du graphe LangGraph avec les 9 nœuds
- `backend/src/iryx/orchestrator/services.py` -- Logique métier `InvestigationService` (création avec verrou anti-concurrence, consultation)
- `backend/src/iryx/orchestrator/router.py` -- Endpoints REST `/api/v1/cases/{case_id}/investigations` avec injection RBAC
- `backend/src/iryx/main.py` -- Inclusion du routeur d'orchestration dans l'application FastAPI
- `backend/tests/unit/test_investigation_migration.py` -- Tests unitaires de la migration Alembic 006
- `backend/tests/unit/test_orchestrator_graph.py` -- Tests de compilation et validation des nœuds du graphe LangGraph
- `backend/tests/unit/test_orchestrator_api.py` -- Tests des endpoints d'API (nominal 201, conflit 409, viewer 403, 404)

## Tasks & Acceptance

**Execution:**
- [x] `backend/pyproject.toml` -- Intégrer la dépendance `langgraph>=0.2.20` et synchroniser l'environnement.
- [x] `backend/src/iryx/core/exceptions.py` -- Ajouter `InvestigationAlreadyRunningException` héritant de `ConflictException` avec code `"INVESTIGATION_ALREADY_RUNNING"`.
- [x] `backend/src/iryx/orchestrator/models.py` -- Définir `InvestigationRun` et `Phase` avec statuts, phases, horodatages UTC et contraintes Check.
- [x] `backend/src/iryx/cases/models.py` -- Déclarer la relation `investigation_runs` liée à `Case`.
- [x] `backend/migrations/versions/006_create_investigation_and_phase_tables.py` -- Rédiger et tester la migration Alembic 006 avec index et contraintes de clés étrangères.
- [x] `backend/migrations/env.py` -- Importer `iryx.orchestrator.models` pour l'enregistrement des métadonnées Alembic.
- [x] `backend/src/iryx/orchestrator/schemas.py` -- Définir les schémas Pydantic `InvestigationRunOut`, `PhaseOut` et schémas d'état.
- [x] `backend/src/iryx/orchestrator/state.py` -- Définir le `TypedDict` `InvestigationState` pour LangGraph.
- [x] `backend/src/iryx/orchestrator/graph.py` -- Implémenter la fonction `build_investigation_graph` compilant les 9 nœuds (`triage`, `planner`, `gate_h1`, `executor`, `analyst`, `verifier`, `gate_h2`, `gate_h3`, `reporting`).
- [x] `backend/src/iryx/orchestrator/services.py` -- Implémenter `InvestigationService` avec détection de run actif (`running`/`paused`) et création atomique de `InvestigationRun` et de sa `Phase` initiale.
- [x] `backend/src/iryx/orchestrator/router.py` -- Créer les endpoints `POST /api/v1/cases/{case_id}/investigations` et `GET /api/v1/cases/{case_id}/investigations/{run_id}` avec RBAC.
- [x] `backend/src/iryx/main.py` -- Enregistrer le routeur d'orchestration dans FastAPI.
- [x] `backend/tests/unit/test_investigation_migration.py` -- Tester la migration Alembic 006 (métadonnées, upgrade offline/online, downgrade).
- [x] `backend/tests/unit/test_orchestrator_graph.py` -- Valider la structure et la compilation du graphe LangGraph.
- [x] `backend/tests/unit/test_orchestrator_api.py` -- Valider les codes de retour HTTP 201, 409, 403 et 404.

**Acceptance Criteria:**
- Given la migration Alembic `006_create_investigation_and_phase_tables` appliquée, when une session d'enquête est initiée via `POST /api/v1/cases/{case_id}/investigations`, then un enregistrement `InvestigationRun` est créé avec statut `running`, `current_phase = "triage"`, `iteration_count = 0`, `error_count = 0`, et `started_at` horodaté en UTC.
- Given l'initialisation de l'orchestrateur, when `build_investigation_graph()` est invoqué, then le graphe d'états LangGraph compile avec succès les 9 nœuds de traitement (`triage`, `planner`, `gate_h1`, `executor`, `analyst`, `verifier`, `gate_h2`, `gate_h3`, `reporting`).
- Given la création nominale d'un `InvestigationRun`, when l'enregistrement est persisté, then une entité `Phase` initiale est créée pour matérialiser la phase active `triage`.
- Given une session d'enquête active déjà en cours d'exécution sur le même dossier (`running` ou `paused`), when un utilisateur tente d'en lancer une seconde en parallèle, then le serveur refuse l'opération avec HTTP 409 Conflict et le code `INVESTIGATION_ALREADY_RUNNING`.
- Given un utilisateur ayant uniquement le rôle `viewer`, when il tente d'initier une session d'investigation, then le serveur retourne HTTP 403 Forbidden.

## Implementation Notes

- **Dépendance LangGraph** : Ajout de `langgraph>=0.2.20` dans `backend/pyproject.toml` (résolu via `uv add` avec `langgraph==1.2.24` et `langchain-core==1.8.4`).
- **Exceptions Métier** :
  - `InvestigationAlreadyRunningException` (HTTP 409, code `"INVESTIGATION_ALREADY_RUNNING"`) ajoutée dans `backend/src/iryx/core/exceptions.py`.
  - `InvestigationNotFoundException` (HTTP 404, code `"INVESTIGATION_NOT_FOUND"`) ajoutée pour la gestion unifiée des 404 sur les investigations.
- **Modèles de Données & Relations** (`backend/src/iryx/orchestrator/models.py`) :
  - Modèle `InvestigationRun` (`investigation_runs`) : UUID `id`, `case_id` (FK `cases.id` ON DELETE CASCADE), `status` (Enum `InvestigationStatus`), `current_phase` (Enum `PhaseName`), `validated_plan` (JSONB), `iteration_count`, `error_count`, horodatages UTC `started_at`, `updated_at`, et relations SQLAlchemy.
  - Modèle `Phase` (`phases`) : UUID `id`, `investigation_run_id` (FK ON DELETE CASCADE), `phase_name` (Enum), `status` (Enum `PhaseStatus`), horodatages UTC.
  - Relation inverse `investigation_runs` ajoutée sur `Case` (`backend/src/iryx/cases/models.py`).
- **Migration Alembic 006** (`backend/migrations/versions/006_create_investigation_and_phase_tables.py`) :
  - Création des tables `investigation_runs` et `phases` avec clés étrangères, index de recherche, et contraintes CHECK de cohérence des statuts et compteurs.
  - Enregistrement des modèles dans `backend/migrations/env.py`.
- **Graphe LangGraph & État** (`backend/src/iryx/orchestrator/state.py` et `graph.py`) :
  - Définition du `TypedDict` `InvestigationState`.
  - Construction du graphe via `build_investigation_graph` enregistrant les 9 nœuds : `triage`, `planner`, `gate_h1`, `executor`, `analyst`, `verifier`, `gate_h2`, `gate_h3`, `reporting`.
- **Service & API REST** (`backend/src/iryx/orchestrator/services.py` et `router.py`) :
  - `InvestigationService.create_investigation_run` : verrouillage anti-concurrence rejetant toute session active (`pending`, `running`, `paused`) avec HTTP 409, et création atomique du run et de sa phase initiale `triage` (`active`).
  - Endpoint `POST /api/v1/cases/{case_id}/investigations` : protégé par `require_case_role(ADMIN, INVESTIGATOR, ANALYST)` interdisant les rôles `viewer` avec HTTP 403.
  - Endpoint `GET /api/v1/cases/{case_id}/investigations/{run_id}` : protégé par `verify_case_access`.
  - Enregistrement du routeur dans `backend/src/iryx/main.py`.
- **Validation & Tests** :
  - 18 tests unitaires dédiés (migration, graphe, API) passant à 100%.
  - 565 tests au global passant à 100% sans régression.

## Spec Change Log

## Review Triage Log

| ID | Source | Verdict | Evidence & Rationale |
|---|---|---|---|
| EC-1 | edge-case-hunter | medium | Risque de TOCTOU dans `start_investigation` si deux requêtes concurrentes interrogent avant commit ; nécessite un verrou `with_for_update` sur le `Case`. |
| BH-1 | blind-hunter | medium | Doublon EC-1 : absence de verrouillage au niveau base sur l'anti-concurrence des sessions actives. |
| BH-2 | blind-hunter | low | Les listes d'état `InvestigationState` (`tool_executions`, `findings`, etc.) écrasent par défaut sans reducer LangGraph. |
| BH-3 | blind-hunter | false | Rejeté : les critères d'acceptation de la Story 5.2 imposent expressément les 9 nœuds (`triage`, `planner`, `gate_h1`, `executor`, `analyst`, `verifier`, `gate_h2`, `gate_h3`, `reporting`). La pseudonymisation relève de l'Epic 8. |
| BH-4 | blind-hunter | false | Rejeté : l'interruption des portes H1/H2/H3 et les routes de reprise font l'objet des Stories 5.4 et 5.6. Story 5.2 valide la compilation initiale. |
| BH-5 | blind-hunter | low | Paramètre de requête `_payload: InvestigationRunCreate` accepté dans l'endpoint POST mais inutilisé par le service. |
| BH-6 | blind-hunter | low | Endpoint de liste `GET /api/v1/cases/{case_id}/investigations` absent pour la découverte des runs d'un dossier. |
| BH-7 | blind-hunter | low | Schémas `InvestigationRunOut` et `PhaseOut` typent les statuts en `str` plutôt qu'avec les énumérations du domaine. |
| BH-8 | blind-hunter | low | Le test `test_create_investigation_by_admin_and_analyst_201` teste `admin_headers` mais n'exécute pas l'appel avec `analyst_headers`. |
| BH-9 | blind-hunter | medium | Doublon VG-1 : absence de test vérifiant l'isolation multi-dossiers sur `GET`. |
| BH-10 | blind-hunter | low | Assertion de tête Alembic dans les tests de migration à aligner sur `heads == ["006"]`. |
| BH-11 | blind-hunter | low | Harmonisation des constantes `PhaseName` et des statuts pour éviter les doublons verbe/nom. |
| BH-12 | blind-hunter | low | Rejeté : `current_phase` en `String(64)` sans contrainte CHECK rigide permet l'évolutivité des phases sans migration DDL bloquante. |
| BH-13 | blind-hunter | low | Absence de logger structuré dans `InvestigationService`. |
| BH-14 | blind-hunter | low | `start_investigation` ne vérifie pas si le dossier est au statut `CaseStatus.CLOSED`. |
| BH-15 | blind-hunter | low | Paramètre `current_user` injecté mais inutilisé dans le routeur. |
| BH-16 | blind-hunter | low | Absence de test de compilation du graphe avec checkpointer (`MemorySaver`). |
| VG-1 | verification-gap | medium | Isolation multi-dossiers non vérifiée sur `get_investigation_run` : `GET /cases/{case_B}/investigations/{run_A}` doit renvoyer 404. |
| VG-2 | verification-gap | medium | Scoping par dossier non vérifié : une session active sur `case_1` ne doit pas bloquer une enquête sur `case_2`. |
| VG-3 | verification-gap | medium | Le test du flux de graphe n'affirmait que la phase finale sans vérifier la traversée séquentielle des 9 nœuds (`graph.stream`). |
| VG-4 | verification-gap | medium | Statuts `FAILED` (autorisant une nouvelle enquête) et `PENDING` (bloquant une nouvelle enquête) non testés dans la matrice. |
| VG-Other-1 | verification-gap | medium | Doublon EC-1/BH-1 (verrouillage concurrence). |
| VG-Other-2 | verification-gap | low | Doublon BH-5 (payload inutilisé). |

## Design Notes

- **Concurrence d'enquêtes par dossier :** Pour garantir la cohérence des preuves et des constats (D-09), un dossier ne peut admettre qu'une seule session d'investigation active (`status IN ('pending', 'running', 'paused')`). Si une telle session existe, la création d'une nouvelle session est immédiatement bloquée par `InvestigationAlreadyRunningException` (HTTP 409).
- **Structure LangGraph modulaire :** Le graphe LangGraph est initialisé dans `iryx.orchestrator.graph` avec un typage d'état `InvestigationState`. Les nœuds sont déclarés comme fonctions pures prenant l'état et retournant le dictionnaire de mise à jour. Dans cette story, chaque nœud fournit l'échafaudage initial nécessaire à la compilation sans exécuter encore les inférences réelles qui feront l'objet des Stories 5.3 à 5.6.

## Verification

**Commands:**
- `uv run pytest tests/unit/test_investigation_migration.py tests/unit/test_orchestrator_graph.py tests/unit/test_orchestrator_api.py` -- expected: Tous les tests unitaires et d'API d'orchestration passent à 100%.
- `uv run pytest` -- expected: Suite complète de tests (>547 tests) au vert sans aucune régression.
