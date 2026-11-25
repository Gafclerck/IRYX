---
title: "Story 5.5 : Agent Executor procédural et dispatch sécurisé vers la Gateway"
type: 'feature'
created: '2026-11-25'
status: 'done'
baseline_revision: 'ad84261c2c5ae04c45894b2b933f30c26947922c'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Une fois le plan d'investigation validé par l'analyste à la porte H1, l'orchestration LangGraph doit déclencher les outils d'analyse forensique de façon rigoureusement déterministe et traçable sans recourir à un LLM probabiliste (FR17, D-08, D-09).

**Approach:** Implémenter l'agent procédural `ExecutorAgent` et le nœud de graphe `executor_node` qui consomment le plan validé, exécutent séquentiellement chaque étape via le service `ToolRunner` de la Gateway avec réapplication stricte des permissions et contrôles sur les preuves ciblées, tracent chaque exécution dans `ToolExecution`, stockent les `Observation` normalisées en base relationnelle, incrémentent `error_count` en cas d'échec technique tout en adaptant la poursuite de l'exécution, et effectuent la transition automatique vers la phase d'analyse (`analyst`).

## Boundaries & Constraints

**Always:**
- Exécuter les outils de manière séquentielle et déterministe pure : ZÉRO appel LLM par l'agent Executor (D-08, D-09).
- Transmettre chaque étape approuvée du plan à la Gateway (`ToolRunner.execute_tool`) en passant un `ToolExecutionContext` typé avec le rôle `Executor`, le `case_id` et l'identifiant de la preuve ciblée (`target_evidence_id`).
- Valider systématiquement que chaque preuve ciblée (`target_evidence_id`) existe en base, est rattachée au dossier courant (`case_id`), et possède une empreinte `sha256` valide scellée ; lever ou consigner une `EvidenceNotFoundInCaseException` ou `ValidationException` le cas échéant.
- Vérifier que chaque outil requis figure dans la liste blanche stricte de `ToolRegistry` (`MVP_TOOL_WHITELIST`).
- Consigner chaque exécution dans la table `tool_executions` (via `ToolRunner`) et persister toutes les `Observation` produites en base relationnelle PostgreSQL.
- Incrémenter `error_count` (à la fois dans l'état de graphe `InvestigationState.error_count` et sur l'entité relationnelle `InvestigationRun.error_count`) et enregistrer le détail de l'erreur dans `InvestigationState.errors` dès qu'une étape échoue (timeout, erreur de validation, erreur interne de l'outil).
- Gérer la résilience d'exécution : par défaut, poursuivre l'exécution des étapes suivantes si une étape non bloquante échoue (`continue_on_error = True`) ; suspendre l'exécution (`status = paused` / `current_phase = executor`) si l'erreur est spécifiée comme bloquante (`is_blocking = True`).
- Clôturer la phase `PhaseName.EXECUTOR` (`status = completed`, `completed_at = now`) et initialiser la phase `PhaseName.ANALYST` (`status = active`, `started_at = now`) en base lorsque toutes les étapes du plan ont été traitées, avec mise à jour de `InvestigationRun.current_phase = PhaseName.ANALYST`.
- Mettre à jour le graphe LangGraph pour router automatiquement de `executor` vers `analyst` lors de la complétion nominale, ou vers `END` si le statut devient `paused` ou `failed`.

**Never:**
- Jamais d'appel LLM émis par le composant Executor (interdiction formelle de solliciter `UnifiedLLMClient` dans `ExecutorAgent` ou `executor_node`).
- Jamais d'exécution d'un outil hors de la liste blanche `ToolRegistry` ou sans passage par `ToolRunner`.
- Jamais d'accès direct au système de fichiers ou à des processus système en dehors du bac à sable géré par `ToolRunner` et la Gateway.
- Jamais d'exécution d'étapes ciblant une preuve d'un autre dossier (cloisonnement strict multi-tenancy / multi-dossiers).
- Jamais d'écrasement ou de perte de l'historique des erreurs d'investigation : `error_count` est cumulatif et strictement croissant.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Exécution nominale plan 1..N étapes | State avec `h1_approved: True` et plan validé (ex. 2 étapes) | Exécution séquentielle des 2 outils via `ToolRunner`, création de 2 `ToolExecution`, persistance des `Observation`, transition vers `analyst` (`status: running`) | N/A |
| Plan absent ou vide | State sans champ `plan` et sans plan en DB | Statut `failed`, message d'erreur consigné dans `errors`, arrêt ou exception appropriée | `PlanNotFoundException` ou consigne dans `errors` |
| Échec technique non bloquant (ex. timeout ou format) | Étape 1 échoue avec timeout ou erreur de validation, `is_blocking: False` | `error_count` incrémenté de 1, erreur enregistrée dans `errors`, Executor enchaîne sur l'étape 2, transition finale vers `analyst` | Consignation `ToolExecutionStatus.ERROR` / `TIMEOUT` |
| Échec technique bloquant | Étape 1 échoue avec `is_blocking: True` | `error_count` incrémenté, `status: paused`, `current_phase: executor`, arrêt de la boucle avant l'étape 2 | `status = paused`, arrêt immédiat |
| Preuve ciblée inexistante ou hors dossier | Étape ciblant un UUID de preuve inconnu ou appartenant à un autre `case_id` | `error_count` incrémenté, `errors` enrichi avec `EVIDENCE_NOT_FOUND_IN_CASE`, étape sautée ou arrêtée selon criticité | `EvidenceNotFoundInCaseException` gérée |
| Preuve ciblée non scellée | Étape ciblant une preuve sans `sha256` | `error_count` incrémenté, erreur de preuve non scellée consignée | `ValidationException` gérée |
| Outil non répertorié dans ToolRegistry | Étape spécifiant un nom d'outil arbitraire (ex: `bash_exploit`) | `error_count` incrémenté, étape rejetée avec `TOOL_NOT_FOUND` ou `PLUGIN_NOT_WHITELISTED` | `ToolNotFoundException` gérée |
| Déroulement complet du graphe LangGraph | Invocation `graph.invoke` ou `graph.stream` après Gate H1 | Traversée ordonnée `triage` -> `planner` -> `gate_h1` -> `executor` -> `analyst` -> `verifier` -> `gate_h2` -> `gate_h3` -> `reporting` | Conforme au flux |

</intent-contract>

## Code Map

- `backend/src/iryx/orchestrator/executor.py` -- Nouvel agent procédural `ExecutorAgent` et modèle de résultat `ExecutorResult` exécutant séquentiellement les étapes d'un `InvestigationPlan` via `ToolRunner` avec vérification des preuves, sans appel LLM.
- `backend/src/iryx/orchestrator/services.py` -- Méthodes de service pour compléter la phase d'exécution (`complete_executor_phase`), initialiser la phase d'analyse, et incrémenter `error_count` sur `InvestigationRun`.
- `backend/src/iryx/orchestrator/graph.py` -- Implémentation complète de `executor_node` et de l'arête conditionnelle `route_executor` liant l'exécution à `analyst` ou à `END` en cas de suspension/échec.
- `backend/src/iryx/orchestrator/schemas.py` -- Enrichissement d'attributs optionnels sur `InvestigationPlanStep` (`is_blocking: bool = False`, `continue_on_error: bool = True`).
- `backend/tests/unit/test_executor_agent.py` -- Tests unitaires dédiés pour `ExecutorAgent` (nominal, étapes séquentielles, gestion d'erreurs non bloquantes, erreurs bloquantes, preuves invalides, zéro appel LLM).
- `backend/tests/unit/test_orchestrator_graph.py` -- Actualisation et ajout de tests de flux de graphe LangGraph pour l'exécution d'outils et la transition vers `analyst`.

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/orchestrator/schemas.py` -- Ajouter les champs de contrôle de tolérance aux pannes (`is_blocking`, `continue_on_error`) dans `InvestigationPlanStep` -- Permettre aux étapes de spécifier leur criticité en cas d'erreur.
- [x] `backend/src/iryx/orchestrator/services.py` -- Ajouter `complete_executor_phase` et la mise à jour transactionnelle des compteurs d'erreurs et des phases -- Assurer la traçabilité en base relationnelle lors du passage d'executor à analyst.
- [x] `backend/src/iryx/orchestrator/executor.py` -- Créer `ExecutorAgent` et `ExecutorResult` avec exécution séquentielle purement déterministe, contrôles de preuve et dispatch vers `ToolRunner` -- Implémenter le cœur procédural de la Story 5.5.
- [x] `backend/src/iryx/orchestrator/graph.py` -- Remplacer le bouchon de `executor_node` par l'appel à `ExecutorAgent` et ajouter la route conditionnelle `route_executor` -- Intégrer l'agent au graphe LangGraph.
- [x] `backend/tests/unit/test_executor_agent.py` -- Écrire une suite complète de tests unitaires pour `ExecutorAgent` -- Valider le cas nominal, les erreurs techniques, le non-usage de LLM et l'isolation des dossiers.
- [x] `backend/tests/unit/test_orchestrator_graph.py` -- Mettre à jour les tests de graphe pour valider le comportement effectif d'`executor_node` et la transition fluide vers `analyst`.

**Acceptance Criteria:**
- Given la porte H1 approuvée avec un plan d'actions validé, when le nœud `executor` s'exécute dans LangGraph, then chaque étape du plan est appelée de manière séquentielle via le service `ToolRunner` de la Gateway.
- Given l'exécution de l'Executor, then aucun appel LLM n'est émis (procédure déterministe pure).
- Given l'exécution d'un outil par l'Executor, then un enregistrement `ToolExecution` est tracé en base et les `Observation` correspondantes sont persistées.
- Given une session où toutes les étapes du plan sont achevées, then la phase en base passe à `analyst` et le graphe LangGraph transitionne automatiquement vers le nœud `analyst`.
- Given une étape du plan échouant techniquement (erreur de format ou timeout d'outil) sans être marquée bloquante, when l'erreur est constatée par l'Executor, then `InvestigationRun.error_count` est incrémenté, l'erreur est enregistrée dans `errors`, et l'Executor passe à l'étape suivante.
- Given une étape du plan marquée bloquante (`is_blocking: True`) échouant techniquement, when l'erreur survient, then l'exécution s'interrompt avec le statut `paused`.
- Given une étape ciblant une preuve n'appartenant pas au dossier ou non scellée, when l'Executor tente de la traiter, then l'erreur est rejetée et comptabilisée sans exécution de l'outil.

## Spec Change Log

## Review Triage Log

### 2026-11-25 — Review pass
- verdicts: 7 findings — high 2, medium 2, low 3, false 0, maybe-false 0
- findings:
  - `[high]` `[patch]` Route conditionnelle `route_executor` dans LangGraph interrompant le flux en cas d'erreur bloquante — Ajouté `route_executor` avec arrêt sur `paused`/`failed` et routage vers `analyst`.
  - `[high]` `[patch]` Contrôle d'accès et d'intégrité réentrant sur les preuves forensiques — Vérification en base de l'appartenance au dossier (`case_id`) et du scellement SHA-256 dans `ExecutorAgent`.
  - `[medium]` `[patch]` Persistance et incrémentation transactionnelle d'`error_count` dans `InvestigationRun` — Implémenté `complete_executor_phase` et `pause_at_executor` dans `InvestigationService`.
  - `[medium]` `[patch]` Pilotage de la criticité des étapes via `is_blocking` et `continue_on_error` — Enrichi `InvestigationPlanStep` dans `schemas.py` et gestion dans `ExecutorAgent`.
  - `[low]` `[patch]` Normalisation de `source_id` en UUID pour la compatibilité des observations — Normalisé `src_id` dans `ToolRunner` pour éviter les erreurs de type string/UUID.
  - `[low]` `[patch]` Fallback de récupération du plan validé depuis `InvestigationRun.validated_plan` — Ajout du chargement DB dans `ExecutorAgent` si le plan est omis dans le state.
  - `[low]` `[patch]` Isolation des paramètres d'étape contre les mutations — Copie défensive de `step.parameters` avant injection d'`evidence_id`.

## Design Notes

- **Déterminisme absolu et zéro LLM :** Contrairement au Planner ou à l'Analyst, l'Executor n'a pas accès à `UnifiedLLMClient`. Il s'agit d'une machine à états procédurale qui boucle de manière synchrone/asynchrone sur les `InvestigationPlanStep`.
- **Validation réentrante des preuves :** Bien que le plan ait été validé par H1, l'Executor réinterroge la base de données au moment de l'exécution pour confirmer que la preuve existe toujours, est rattachée au dossier et que son intégrité SHA-256 est scellée, éliminant tout risque de condition de course.
- **Continuité d'enquête sur erreur technique :** Les analyses forensiques manipulent des artefacts hétérogènes. Si un parseur de journaux texte échoue sur un format non standard, l'analyste a besoin que les étapes suivantes (ex. extraction EVTX ou ruches de registre) continuent de s'exécuter. Le flag `continue_on_error = True` par défaut garantit cette résilience opérationnelle.

## Verification

**Commands:**
- `uv run pytest backend/tests/unit/test_executor_agent.py backend/tests/unit/test_orchestrator_graph.py` -- expected: Tous les tests unitaires de l'agent Executor et du graphe LangGraph réussissent.
- `uv run pytest` -- expected: L'ensemble de la suite de tests globale passe sans régression (627+ tests).

## Auto Run Result

### Résumé de l'implémentation
La Story 5.5 implémente l'agent procédural `Executor` et le dispatch sécurisé vers la Forensic Gateway (FR17) :
- Création de `ExecutorAgent` et du modèle `ExecutorResult` garantissant une exécution séquentielle déterministe pure (Zéro appel LLM).
- Dispatch sécurisé des outils approuvés vers le service `ToolRunner` de la Gateway avec réapplication systématique des permissions sur les preuves ciblées (`case_id` correspondant, empreinte `sha256` scellée requise).
- Traçabilité complète d'exécution forensique : chaque outil exécuté est persisté dans `ToolExecution` et toutes les `Observation` correspondantes sont stockées en base relationnelle PostgreSQL.
- Résilience et gestion d'erreurs techniques : incrémentation de `InvestigationRun.error_count` et poursuite des étapes suivantes par défaut (`continue_on_error: True`), avec possibilité de suspension immédiate (`status: paused`) si l'étape est marquée bloquante (`is_blocking: True`).
- Transition automatique d'état : clôture transactionnelle de la phase `PhaseName.EXECUTOR` et initialisation de la phase `PhaseName.ANALYST` en base de données et dans LangGraph.
- Intégration dans le graphe d'états LangGraph via `executor_node` et la route conditionnelle `route_executor`.

### Fichiers modifiés
- `backend/src/iryx/orchestrator/schemas.py` : Ajout des attributs `is_blocking` et `continue_on_error` sur `InvestigationPlanStep`.
- `backend/src/iryx/orchestrator/executor.py` : Nouvel agent procédural `ExecutorAgent` et modèle `ExecutorResult`.
- `backend/src/iryx/orchestrator/services.py` : Méthodes `complete_executor_phase` et `pause_at_executor` avec verrouillage transactionnel et transition vers la phase Analyst.
- `backend/src/iryx/orchestrator/graph.py` : Implémentation complète de `executor_node`, ajout de `route_executor` et branchement conditionnel vers `analyst` / `END`.
- `backend/src/iryx/orchestrator/__init__.py` : Export de `ExecutorAgent` et `ExecutorResult`.
- `backend/src/iryx/gateway/runner.py` : Normalisation du `source_id` en UUID pour la persistance des observations.
- `backend/tests/unit/test_executor_agent.py` : 13 tests unitaires exhaustifs pour l'ExecutorAgent.
- `backend/tests/unit/test_orchestrator_graph.py` : Tests de route conditionnelle `route_executor` et mise à jour des assertions de graphe.

### Bilan des constats de revue
- **Patches appliqués** : 7 constats (2 high, 2 medium, 3 low) traités et vérifiés.
- **Éléments différés** : 0.
- **Constats rejetés** : 0.
- **Recommandation de revue ultérieure** : `false` (couverture complète, zéro régression).

### Vérifications effectuées
- `uv run ruff check` : 0 avertissement / 0 erreur de linting.
- `uv run pytest backend/tests/unit/test_executor_agent.py backend/tests/unit/test_orchestrator_graph.py` : 30/30 tests passés (100%).
- `uv run pytest` : 641/641 tests passés (100%) sans aucune régression.

### Risques résiduels
- Aucun.
