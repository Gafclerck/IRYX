---
title: "Story 4.1 : Registre de la Gateway forensique, modèle ToolExecution et classe de base d'outils"
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: 'ade1b0b790b944d04ceaf67553507a35518400ef'
baseline_revision: 'ade1b0b790b944d04ceaf67553507a35518400ef'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/docs/02-agents-et-outils.md'
  - '{project-root}/docs/03-modele-de-donnees.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les analyseurs forensiques d'IRYX nécessitent un cadre d'exécution sécurisé, auditable et sans interpréteur de commandes (`shell=False`), assurant la traçabilité intégrale de chaque appel, la validation des paramètres par schémas Pydantic v2, l'application stricte des délais d'expiration (timeouts) et la persistance immuable des métadonnées d'exécution.

**Approach:** Créer les modèles relationnels `ToolExecution` et `Observation` via la migration Alembic 005, définir la classe abstraite `BaseTool`, le registre centralisé `ToolRegistry` avec contrôle par liste blanche, et le moteur d'exécution `ToolRunner` garantissant le hachage SHA-256 des résultats bruts, le calcul de durée en millisecondes et l'interruption sécurisée lors des dépassements de temporisation.

## Boundaries & Constraints

**Always:**
- Créer la migration réversible `005_create_tool_execution_and_observation_tables.py` pour les tables `tool_executions` et `observations` avec clés primaires UUID, clés étrangères en cascade vers `cases.id` / `evidences.id`, index et contraintes de vérification (statuts `success`/`error`/`timeout`, `duration_ms >= 0`).
- Définir le modèle ORM `ToolExecution` dans `backend/src/iryx/gateway/models.py` (`id`, `case_id`, `tool_name`, `tool_version`, `agent_role`, `parameters` JSONB, `result_sha256`, `duration_ms`, `status`, `error_message`, `created_at`).
- Définir le modèle ORM `Observation` dans `backend/src/iryx/analytics/models.py` (réexporté dans `gateway/models.py`) avec `timestamp_utc`, `normalized_content` JSONB, `source_location`, et clés étrangères vers `Case`, `Evidence`, `ToolExecution`.
- Définir `BaseTool` (`backend/src/iryx/gateway/base.py`) avec `name`, `version`, `description`, `timeout_seconds`, `parameters_schema` (Pydantic v2), et `async def execute(self, params: BaseModel, context: ToolExecutionContext) -> ToolExecutionResult`.
- Implémenter le registre d'outils `ToolRegistry` (`backend/src/iryx/gateway/registry.py`) appliquant une liste blanche stricte et interdisant les doublons.
- Implémenter `ToolRunner` (`backend/src/iryx/gateway/runner.py`) validant les paramètres d'entrée, chronométrant l'exécution, calculant l'empreinte `hashlib.sha256` du résultat brut et persistant `ToolExecution`.
- Confinement strict sans shell : tout sous-processus est instancié avec `shell=False` strict.
- En cas de dépassement du délai de l'outil, interrompre immédiatement le traitement, enregistrer le statut `"timeout"` dans `ToolExecution` et lever `ToolExecutionTimeoutException` (HTTP 504).
- Si l'outil est inconnu, lever `ToolNotFoundException` (HTTP 404). Si les paramètres sont non conformes au schéma Pydantic, lever `ValidationException` (HTTP 422). En cas d'erreur inattendue de l'outil, consigner le statut `"error"` et lever `ToolExecutionFailedException` (HTTP 500).
- Exposer les nouvelles exceptions dans `backend/src/iryx/core/exceptions.py`.

**Never:**
- Jamais d'utilisation de `shell=True` ou passage par un interpréteur de commandes système (`sh`, `bash`, `cmd`, `powershell`).
- Jamais d'exécution directe d'un analyseur en contournant le moteur `ToolRunner`.
- Aucun appel réseau sortant autorisé depuis les outils d'analyse (`network_mode: none`).
- Aucune régression sur les migrations antérieures (001 à 004) ou les tests existants.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Exécution nominale | Outil enregistré, paramètres valides | Statut `success`, `duration_ms` > 0, `result_sha256` calculé, `ToolExecution` persisté | N/A |
| Expiration du délai (timeout) | Traitement dépassant `timeout_seconds` | Interruption immédiate, `ToolExecution.status = "timeout"` persisté | Lève `ToolExecutionTimeoutException` (504) |
| Outil non enregistré | Nom d'outil absent de `ToolRegistry` | Aucun sous-processus lancé, aucun enregistrement orphelin | Lève `ToolNotFoundException` (404) |
| Paramètres invalides | Données d'appel ne respectant pas `parameters_schema` | Exécution bloquée avant lancement de l'outil | Lève `ValidationException` (422) |
| Erreur interne d'outil | Exception levée pendant l'exécution | `ToolExecution.status = "error"` persisté avec détails d'erreur | Lève `ToolExecutionFailedException` (500) |
| Injection de métacaractères | Arguments contenant `&&`, `;`, `\|` | Données traitées comme arguments littéraux (`shell=False`) sans interprétation | N/A |

</frozen-after-approval>

## Code Map

- `backend/migrations/versions/005_create_tool_execution_and_observation_tables.py` -- Migration Alembic pour tables `tool_executions` et `observations`
- `backend/migrations/env.py` -- Enregistrement de `iryx.gateway.models` et `iryx.analytics.models` dans target_metadata
- `backend/src/iryx/gateway/__init__.py` -- Package gateway forensique et exports principaux
- `backend/src/iryx/gateway/models.py` -- Modèle ORM `ToolExecution` et enum `ToolExecutionStatus`
- `backend/src/iryx/gateway/base.py` -- Classe abstraite `BaseTool`, `ToolExecutionContext` et `ToolExecutionResult`
- `backend/src/iryx/gateway/registry.py` -- Registre centralisé `ToolRegistry` (liste blanche d'outils)
- `backend/src/iryx/gateway/runner.py` -- Moteur d'exécution sécurisé `ToolRunner` (timeouts, hachage SHA-256, audit)
- `backend/src/iryx/gateway/schemas.py` -- Schémas Pydantic v2 pour métadonnées et résultats d'outils
- `backend/src/iryx/analytics/__init__.py` -- Package analytics et exports
- `backend/src/iryx/analytics/models.py` -- Modèle ORM `Observation`
- `backend/src/iryx/cases/models.py` -- Relations `tool_executions` et `observations` sur `Case`
- `backend/src/iryx/evidence/models.py` -- Relation `observations` sur `Evidence`
- `backend/src/iryx/core/exceptions.py` -- Exceptions Gateway (`ToolExecutionTimeoutException`, `ToolNotFoundException`, etc.)
- `backend/tests/unit/test_gateway_migration.py` -- Tests d'upgrade/downgrade Alembic pour la révision 005
- `backend/tests/unit/test_tool_execution_models.py` -- Tests unitaires ORM, contraintes et relations
- `backend/tests/unit/test_tool_gateway_registry.py` -- Tests unitaires du registre et de `BaseTool`
- `backend/tests/unit/test_tool_gateway_runner.py` -- Tests unitaires de `ToolRunner` (timeouts, hachage, shell=False)

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/core/exceptions.py` -- Ajouter `ToolExecutionTimeoutException`, `ToolNotFoundException`, `ToolExecutionFailedException`, `PluginNotWhitelistedException` -- Standardiser les erreurs de la Gateway
- [x] `backend/src/iryx/gateway/models.py` -- Définir le modèle ORM `ToolExecution` et l'enum `ToolExecutionStatus` -- Modéliser la persistance auditable des exécutions
- [x] `backend/src/iryx/analytics/models.py` -- Définir le modèle ORM `Observation` -- Modéliser la persistance des faits techniques normalisés
- [x] `backend/src/iryx/cases/models.py` -- Ajouter les relations `tool_executions` et `observations` sur `Case` -- Assurer la navigation et suppression en cascade
- [x] `backend/src/iryx/evidence/models.py` -- Ajouter la relation `observations` sur `Evidence` -- Assurer la traçabilité des faits par preuve
- [x] `backend/migrations/versions/005_create_tool_execution_and_observation_tables.py` -- Écrire la migration Alembic 005 réversible -- Créer les tables `tool_executions` et `observations`
- [x] `backend/migrations/env.py` -- Importer `iryx.gateway.models` et `iryx.analytics.models` -- Intégrer les métadonnées dans le contexte Alembic
- [x] `backend/src/iryx/gateway/schemas.py` -- Définir les schémas Pydantic v2 d'entrées/sorties et métadonnées -- Valider les données d'outils
- [x] `backend/src/iryx/gateway/base.py` -- Implémenter `BaseTool`, `ToolExecutionContext` et `ToolExecutionResult` -- Définir le contrat d'interface des analyseurs
- [x] `backend/src/iryx/gateway/registry.py` -- Implémenter `ToolRegistry` avec méthodes d'enregistrement et consultation -- Gérer la liste blanche stricte
- [x] `backend/src/iryx/gateway/runner.py` -- Implémenter `ToolRunner` avec timeouts, calcul SHA-256 et politique sans shell -- Orchestrer les invocations sécurisées
- [x] `backend/tests/unit/test_gateway_migration.py` -- Créer les tests de migration 005 upgrade/downgrade -- Valider le schéma SQL réversible
- [x] `backend/tests/unit/test_tool_execution_models.py` -- Créer les tests unitaires des modèles `ToolExecution` et `Observation` -- Valider relations et contraintes
- [x] `backend/tests/unit/test_tool_gateway_registry.py` -- Créer les tests du registre et de la classe de base -- Valider enregistrement et liste blanche
- [x] `backend/tests/unit/test_tool_gateway_runner.py` -- Créer les tests d'exécution, timeouts, calcul d'empreinte SHA-256 et gestion d'erreurs -- Valider le comportement du moteur

**Acceptance Criteria:**
- Given la migration Alembic 005 appliquée sur la base de données, when inspectée par Alembic ou SQLAlchemy, then les tables `tool_executions` et `observations` existent avec toutes leurs colonnes, clés étrangères, index et contraintes.
- Given un outil dérivé de `BaseTool` enregistré dans `ToolRegistry`, when invoqué via `ToolRunner.execute_tool`, then ses paramètres sont validés par Pydantic v2, son résultat brut est haché via SHA-256, sa durée est mesurée en ms, et un enregistrement `ToolExecution` avec statut `"success"` est persisté en base.
- Given un outil dont le traitement dépasse son délai d'expiration configuré (`timeout_seconds`), when exécuté via `ToolRunner`, then le traitement est immédiatement interrompu, un enregistrement `ToolExecution` avec statut `"timeout"` est persisté, et l'exception `ToolExecutionTimeoutException` (HTTP 504) est levée.
- Given une demande d'exécution d'un outil non présent dans `ToolRegistry`, when soumise à `ToolRunner`, then aucune exécution n'a lieu et `ToolNotFoundException` (HTTP 404) est levée.
- Given des paramètres non conformes au schéma Pydantic de l'outil, when soumis à `ToolRunner`, then l'exécution est bloquée avant lancement et une `ValidationException` (HTTP 422) est levée.

## Implementation Notes

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Evidence |
|---|---|---|
| Subprocess orphan on cancellation in `run_command_safely` | medium | `asyncio.CancelledError` not handled during `wait_for` communicate(), child process could remain running |
| Inner `ToolExecutionTimeoutException` not audited in `execute_tool` | medium | Inner timeout was re-raised without persisting `ToolExecution(status=TIMEOUT)` |
| Parameter validation bypass on arbitrary `BaseModel` | false | Code already validates `parameters.model_dump()` against `tool.parameters_schema` when not an instance |
| Missing string-to-datetime parsing for `Observation.timestamp_utc` | low | Forensic parsers often emit ISO strings; parsing ISO strings avoids Postgres type mismatch |
| Observation extraction fallback | low | Standard dictionary format is expected from tools |
| Unhandled DB session state on execution failures | medium | Session commit failure should rollback to avoid poisoned transactions |
| Inconsistent string literal syntax in migration 005 | low | Using `server_default=sa.text("'success'")` avoids dialect ambiguity |
| Lack of network isolation in subprocess execution | false | Network isolation is enforced at container level (`network_mode: none`) |
| Non-deterministic SHA-256 for unordered collections | false | `sort_keys=True` is already enabled in `compute_sha256` |
| Absence of immutability triggers on tool_executions | false | Audit immutability is assigned to Story 8.5 |
| Missing validation between evidence_id and case_id | false | Validated at API boundary via `verify_case_access` |
| Non-standard `__init__` override on `ToolExecutionResult` | low | `@model_validator(mode="before")` is preferred in Pydantic v2 |
| Missing check constraints on observations table | false | Not null constraints already exist |
| Hardcoded whitelist lacks configuration integration | false | Whitelist is an architectural invariant per ADR-0001 / D-14..D-18 |
| `ToolExecutionResult` status overwritten to SUCCESS | low | Preserving existing non-SUCCESS status in result |
| Non-JSON primitives in dict parameters | low | `params_dict = validated_params.model_dump(mode="json")` ensures proper JSONB serialization |
| `normalized_content` None mapping | low | Handle None value fallback safely |
| `PluginNotWhitelistedException` masked as HTTP 500 | medium | Re-raise directly instead of converting to ToolExecutionFailedException |

## Verification

**Commands:**
- `uv run pytest backend/tests/unit/test_gateway_migration.py` -- expected: Tests de migration 005 validés avec upgrade et downgrade
- `uv run pytest backend/tests/unit/test_tool_execution_models.py` -- expected: Tests des modèles ORM ToolExecution et Observation validés
- `uv run pytest backend/tests/unit/test_tool_gateway_registry.py` -- expected: Tests du registre d'outils et BaseTool validés
- `uv run pytest backend/tests/unit/test_tool_gateway_runner.py` -- expected: Tests d'exécution, timeouts, hachage SHA-256 et shell=False validés
- `uv run pytest` -- expected: 100% des tests passants (suite complète sans régression)
- `uv run ruff check backend` -- expected: 0 erreur, 0 avertissement
- `uv run ruff format --check backend` -- expected: 0 modification nécessaire
