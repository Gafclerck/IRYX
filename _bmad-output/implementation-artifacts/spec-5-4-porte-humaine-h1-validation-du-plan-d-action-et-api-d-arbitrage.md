---
title: "Story 5.4 : Porte Humaine H1 (Validation du plan d'action) et API d'arbitrage"
type: 'feature'
created: '2026-11-25'
status: 'done'
baseline_revision: '88e0bac13b62b06da057acdb898f5baeb2fb2149'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
---

<intent-contract>

## Intent

**Problem:** L'investigation forensique numérique autonome ne doit pas exécuter d'actions techniques intrusives sans validation et contrôle humain préalable (principe Human-in-the-loop, FR18). Le plan d'investigation généré par l'agent Planner à l'issue du triage doit être soumis à l'arbitrage formel d'un analyste qualifié, sans risque de passage non autorisé à l'étape d'exécution.

**Approach:** Mettre en œuvre la porte de contrôle humain H1 en suspendant automatiquement l'exécution du graphe LangGraph au nœud `gate_h1` (`status: paused`, `current_phase: gate_h1` / `waiting_h1`), exposer l'endpoint de consultation du plan `GET /api/v1/cases/{case_id}/investigations/{run_id}/plan` et l'endpoint d'arbitrage `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h1` acceptant les décisions d'approbation (`approve`), de modification (`modify` avec validation Pydantic v2 du plan altéré et vérification des outils) ou de rejet (`reject` avec arrêt ou rebouclage vers le Planner), avec contrôle d'accès RBAC strict (interdit aux VIEWERS, HTTP 403) et traçabilité d'audit.

## Boundaries & Constraints

**Always:**
- Respecter le principe Human-in-the-loop (FR18) : l'orchestrateur suspend systématiquement l'exécution à la porte H1, mettant à jour `InvestigationRun.status = paused` et signalant l'attente de décision (`current_phase = gate_h1` ou `waiting_h1`).
- Exposer `GET /api/v1/cases/{case_id}/investigations/{run_id}/plan` protégé par `verify_case_access` renvoyant le plan d'actions au format `InvestigationPlan` (ou HTTP 404 `PLAN_NOT_FOUND` si aucun plan n'est encore associé).
- Exposer `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h1` protégé par `require_case_role(MembershipRole.ADMIN, MembershipRole.INVESTIGATOR, MembershipRole.ANALYST)`, rejetant formellement les utilisateurs sans permissions adéquates avec HTTP 403 Forbidden.
- Valider le corps de requête d'arbitrage `H1DecisionRequest` avec décision stricte dans `['approve', 'modify', 'reject']`.
- En cas de décision `modify`, valider obligatoirement la présence et la conformité du plan modifié (`modified_plan`) via `InvestigationPlan` (1 à 10 étapes, outils dans `ToolRegistry`, preuves rattachées au dossier) avant d'écraser `InvestigationRun.validated_plan` et de faire progresser la session.
- En cas de décision `approve`, mettre à jour `InvestigationRun.status = running`, passer la phase active à `PhaseStatus.COMPLETED` et activer la phase suivante (`PhaseName.EXECUTOR`), débloquant le graphe LangGraph (`h1_approved = True`).
- En cas de décision `reject`, si `return_to_planner` est faux, terminer proprement la session avec le statut `completed` ; si `return_to_planner` est vrai, repositionner la phase sur `PhaseName.PLANNER` pour regénération.
- Si la session d'enquête n'est pas dans l'état d'attente requis (ex. session déjà achevée, échouée ou active sans attente de la porte H1), rejeter l'arbitrage avec HTTP 422 Unprocessable Content (`INVALID_GATE_STATE`).
- Tracer chaque décision d'arbitrage H1 de façon synchrone dans les journaux structurés avec identifiant du dossier, du run, de l'utilisateur et de la décision (FR27).

**Never:**
- Jamais d'exécution d'outils forensiques (`executor`) avant la validation explicite (`approve` ou `modify`) de la porte H1.
- Jamais d'autorisation accordée au rôle `viewer` ou aux membres externes à l'organisation pour soumettre une décision H1 (HTTP 403).
- Jamais d'acceptation d'un plan modifié contenant des outils hors liste blanche `ToolRegistry` ou plus de 10 étapes (NFR-PERF-05).
- Jamais de transition d'état incohérente si le `run_id` ne correspond pas au `case_id` fourni (isolation stricte, HTTP 404).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Consultation nominale du plan | Run en attente H1 avec plan validé | HTTP 200 OK avec le schéma `InvestigationPlan` (`steps`, `summary`) | N/A |
| Consultation plan inexistant | Run créé sans plan généré | HTTP 404 Not Found avec code `PLAN_NOT_FOUND` | `PlanNotFoundException` |
| Approbation nominale H1 | POST `gates/h1` avec `{"decision": "approve"}` sur run pausé H1 | HTTP 200 OK, `status: running`, `current_phase: executor`, déblocage graphe | N/A |
| Modification nominale H1 | POST `gates/h1` avec `{"decision": "modify", "modified_plan": {...}}` valide | HTTP 200 OK, `validated_plan` mis à jour, `status: running`, transition vers `executor` | N/A |
| Modification sans plan | POST `gates/h1` avec `{"decision": "modify"}` sans `modified_plan` | HTTP 422 Unprocessable Content (`MISSING_MODIFIED_PLAN`) | `ValidationException` |
| Modification avec plan invalide | POST `gates/h1` avec `modified_plan` ayant >10 étapes ou outil inconnu | HTTP 422 Unprocessable Content (`INVALID_PLAN`) | `InvalidPlanException` |
| Rejet nominal avec arrêt | POST `gates/h1` avec `{"decision": "reject", "return_to_planner": false}` | HTTP 200 OK, `status: completed`, fin de la session | N/A |
| Rejet avec demande de replanification | POST `gates/h1` avec `{"decision": "reject", "return_to_planner": true, "feedback": "..."}` | HTTP 200 OK, `current_phase: planner`, `status: running`, rebouclage graphe | N/A |
| Arbitrage sur session non en pause H1 | POST `gates/h1` sur run `status: running` ou `completed` | HTTP 422 Unprocessable Content (`INVALID_GATE_STATE`) | `ValidationException` |
| Arbitrage par un Viewer | POST `gates/h1` par un utilisateur avec rôle `viewer` | HTTP 403 Forbidden (`FORBIDDEN`) | `require_case_role` |
| Arbitrage sur dossier inexistant / mauvais dossier | POST `gates/h1` avec `run_id` d'un autre dossier ou inconnu | HTTP 404 Not Found (`INVESTIGATION_NOT_FOUND`) | `InvestigationNotFoundException` |
| Requête non authentifiée | GET plan ou POST `gates/h1` sans en-tête Authorization | HTTP 401 Unauthorized (`UNAUTHORIZED`) | Dépendance d'auth |

</intent-contract>

## Code Map

- `backend/src/iryx/core/exceptions.py` -- Définition de `PlanNotFoundException` (HTTP 404, code `"PLAN_NOT_FOUND"`) et `InvalidGateStateException` (HTTP 422, code `"INVALID_GATE_STATE"`)
- `backend/src/iryx/orchestrator/models.py` -- Ajout éventuel de constantes/membres de phases (`WAITING_H1 = "waiting_h1"`) dans `PhaseName`
- `backend/src/iryx/orchestrator/schemas.py` -- Schémas Pydantic `H1Decision` (Enum: `approve`, `modify`, `reject`), `H1DecisionRequest` (`decision`, `modified_plan`, `feedback`, `return_to_planner`), et `H1DecisionResponse`
- `backend/src/iryx/orchestrator/state.py` -- Déclaration de `h1_rejected` et `return_to_planner` dans `InvestigationState`
- `backend/src/iryx/orchestrator/services.py` -- Méthodes métier `get_investigation_plan`, `pause_at_gate_h1`, et `arbitrate_gate_h1` orchestrant la transition de phase, la mise à jour de `validated_plan`, la persistance en base relationnelle et la journalisation
- `backend/src/iryx/orchestrator/graph.py` -- Mise à jour de `gate_h1_node` et des routes conditionnelles pour suspendre automatiquement le graphe à `gate_h1` et réagir aux décisions (`h1_approved`, rebouclage planner ou fin)
- `backend/src/iryx/orchestrator/router.py` -- Endpoints FastAPI `GET /api/v1/cases/{case_id}/investigations/{run_id}/plan` et `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h1`
- `backend/tests/unit/test_orchestrator_api.py` -- Tests unitaires exhaustifs pour l'arbitrage H1, la consultation du plan, le contrôle RBAC, et l'isolation des dossiers
- `backend/tests/unit/test_orchestrator_graph.py` -- Tests unitaires du graphe LangGraph validant la suspension automatique à `gate_h1`, le déblocage vers `executor`, et les rebouclages

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/core/exceptions.py` -- Ajouter `PlanNotFoundException` et `InvalidGateStateException` -- Fournir les exceptions typées pour les erreurs de consultation et d'arbitrage.
- [x] `backend/src/iryx/orchestrator/models.py` -- Enrichir `PhaseName` si nécessaire pour la porte H1 -- Assurer la compatibilité des noms de phases (`WAITING_H1`).
- [x] `backend/src/iryx/orchestrator/schemas.py` -- Définir `H1Decision`, `H1DecisionRequest`, et `H1DecisionResponse` -- Spécifier les contrats d'entrée et de sortie pour l'arbitrage H1.
- [x] `backend/src/iryx/orchestrator/state.py` -- Déclarer `h1_rejected` et `return_to_planner` dans `InvestigationState`.
- [x] `backend/src/iryx/orchestrator/services.py` -- Implémenter `get_investigation_plan`, `pause_at_gate_h1`, et `arbitrate_gate_h1` avec validation d'outils et gestion de cycle de vie -- Gérer les transitions de phase et la persistance de l'arbitrage.
- [x] `backend/src/iryx/orchestrator/graph.py` -- Ajuster `gate_h1_node` et les transitions conditionnelles pour la suspension et reprise H1 -- Respecter le comportement LangGraph attendu.
- [x] `backend/src/iryx/orchestrator/router.py` -- Ajouter les endpoints de consultation du plan et d'arbitrage de la porte H1 -- Exposer les routes REST conformes aux spécifications.
- [x] `backend/tests/unit/test_orchestrator_api.py` -- Ajouter la suite de tests complète pour les routes de plan et de porte H1 -- Valider les codes de statut HTTP, RBAC et cas d'erreur.
- [x] `backend/tests/unit/test_orchestrator_graph.py` -- Actualiser et compléter les tests de graphe pour le comportement de `gate_h1` -- Valider la suspension et la reprise d'exécution.

**Acceptance Criteria:**
- Given la session d'enquête atteignant l'état `gate_h1`, when l'exécution se suspend automatiquement, then `InvestigationRun.status` passe à `paused` et signale l'attente de la porte H1 (`waiting_h1`).
- Given une session d'enquête avec un plan généré, when un utilisateur autorisé consulte `GET /api/v1/cases/{case_id}/investigations/{run_id}/plan`, then le serveur répond HTTP 200 OK avec le schéma `InvestigationPlan`.
- Given une session d'enquête sans plan, when un utilisateur consulte le plan, then le serveur répond HTTP 404 Not Found avec le code `PLAN_NOT_FOUND`.
- Given une session d'enquête en pause sur la porte H1, when l'analyste approuve le plan via `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h1` avec `{"decision": "approve"}`, then le serveur répond HTTP 200 OK, met à jour le statut à `running` et débloque le graphe vers le nœud `executor`.
- Given l'analyste soumettant une modification du plan avec `decision: "modify"` et un `modified_plan` valide (<= 10 étapes, outils dans `ToolRegistry`), then le plan modifié est validé et persisté dans `InvestigationRun.validated_plan`, et la session reprend vers `executor`.
- Given une tentative de modification avec `modified_plan` invalide (> 10 étapes ou outil inconnu) ou absent, then le serveur répond HTTP 422 Unprocessable Content.
- Given une décision `decision: "reject"`, then si `return_to_planner` est faux la session se termine avec le statut `completed`, et si `return_to_planner` est vrai la session retourne au Planner.
- Given un utilisateur avec le rôle `viewer` ou n'appartenant pas à l'organisation, when il tente de soumettre un arbitrage sur la porte H1, then la requête est rejetée avec HTTP 403 Forbidden.

## Spec Change Log

## Review Triage Log

### 2026-11-25 — Review pass
- verdicts: 23 findings — high 4, medium 8, low 10, false 1, maybe-false 0
- findings:
  - `[high]` `[patch]` Déclaration manquante de `h1_rejected` et `return_to_planner` dans `InvestigationState` TypedDict — Déclaré dans `backend/src/iryx/orchestrator/state.py`.
  - `[high]` `[patch]` Rebouclage vers le Planner bloqué par le cache de plan pré-existant dans LangGraph — Nettoyé `plan: None` et réinitialisé `h1_rejected: False` dans `gate_h1_node` et propagation du feedback.
  - `[high]` `[patch]` Flags d'arbitrage résiduels causant des boucles de replanification infinies — Réinitialisés `h1_rejected: False` et `return_to_planner: False` lors du rebouclage.
  - `[high]` `[patch]` Broken verification du rebouclage LangGraph avec `graph.stream` — Test unitaire `test_graph_rebouclage_planner_when_rejected_with_replan` mis à jour pour vérifier la traversée complète.
  - `[medium]` `[patch]` Verrouillage pessimiste manquant (`with_for_update`) dans `arbitrate_gate_h1` — Ajouté `with_for_update()` sur la sélection de l'investigation.
  - `[medium]` `[patch]` Rejet terminal laissant `run.current_phase` à `waiting_h1` au lieu de `gate_h1` — Corrigé `run.current_phase = PhaseName.GATE_H1` lors d'un rejet avec arrêt.
  - `[medium]` `[patch]` Perte du `feedback` analyste lors de la replanification — Persisté dans les logs d'audit et injecté dans `context["replan_feedback"]` pour le Planner.
  - `[medium]` `[patch]` Borne maximale d'itérations (`iteration_count < 5`) non contrôlée sur replan — Validation ajoutée levant HTTP 422 `MAX_ITERATIONS_REACHED` au-delà de 5 itérations.
  - `[medium]` `[patch]` Absence de vérification du scellement SHA-256 des preuves ciblées dans `modify` — Validation ajoutée requérant `Evidence.sha256` non vide.
  - `[medium]` `[patch]` Manque de test unitaire pour `InvestigationService.pause_at_gate_h1` — Test unitaire complet ajouté dans `test_orchestrator_api.py`.
  - `[medium]` `[patch]` Manque de test unitaire pour l'approbation d'une session sans plan généré — Test unitaire `test_arbitrate_h1_approve_no_plan_404` ajouté.
  - `[medium]` `[patch]` Plan rejeté restant mémorisé dans `run.validated_plan` — Réinitialisé à `None` lors d'un rejet avec demande de replanification.
  - `[low]` `[patch]` Absence de contrôle d'unicité et de séquence 1..N des `step_id` dans `InvestigationPlan` — Validateur ajouté dans `InvestigationPlan`.
  - `[low]` `[patch]` Entrée de texte `feedback` non bornée dans `H1DecisionRequest` — Ajout de `max_length=2000`.
  - `[low]` `[patch]` Constructeur `PlanNotFoundException` avec affectation redondante de `status_code` — Nettoyé pour déléguer à `NotFoundException`.
  - `[low]` `[patch]` Manque de test d'isolation inter-dossiers pour `GET /plan` — Test `test_get_investigation_plan_cross_case_isolation_404` ajouté.
  - `[low]` `[patch]` Manque de test d'autorisation utilisateur externe pour `GET /plan` — Test `test_get_investigation_plan_outside_user_forbidden_403` ajouté.
  - `[low]` `[patch]` Log silencieux lors de l'omission de `db` dans le contexte LangGraph — Message debug ajouté dans `gate_h1_node`.
  - `[low]` `[patch]` Test d'intégration de `gate_h1_node` avec session DB manquante — Test `test_gate_h1_node_persists_pause_when_db_in_context` ajouté.
  - `[low]` `[patch]` Gestion d'erreur interne si `validated_plan` sérialisé est corrompu en base — Modèle Pydantic sécurisé.
  - `[low]` `[patch]` Tests ciblés sur les permissions RBAC d'arbitrage — Couverture validée.
  - `[low]` `[patch]` Format des horodatages UTC lors des transitions de phase — Validé conforme.
  - `[false]` `[reject]` Divergence d'alignement d'intention sur l'exécution asynchrone autonome — Rejeté : l'intention 5.4 couvre l'API d'arbitrage et le scaffold de graphe ; la reprise asynchrone complète par checkpointer PostgreSQL fait l'objet de la Story 5.6.

## Design Notes

- **Suspension et signalement d'attente H1 :** Lorsque l'enquête arrive sur la porte H1, la phase active de l'investigation est marquée comme `gate_h1` (ou `waiting_h1`), et le statut global devient `paused`. Cela permet à l'interface analyste de détecter via polling l'attente d'arbitrage.
- **Cycle de vie transactionnel des phases :** L'approbation ou la modification clôture la phase `gate_h1` (`completed_at = now`) et initialise immédiatement la phase `executor` en base relationnelle avec le statut `active`.
- **Validation réutilisée des outils et preuves :** Lors d'une décision `modify`, le `modified_plan` est scanné pour s'assurer que chaque `tool_name` existe dans la liste blanche `ToolRegistry` et que chaque `target_evidence_id` appartient bien aux preuves du dossier concerné, évitant toute injection d'actions arbitraires.

## Verification

**Commands:**
- `uv run pytest backend/tests/unit/test_orchestrator_api.py backend/tests/unit/test_orchestrator_graph.py` -- expected: Tous les tests unitaires des routes d'arbitrage H1 et du graphe passent avec succès.
- `uv run pytest` -- expected: L'ensemble de la suite de tests (>596 tests) passe sans régression.

## Auto Run Result

### Résumé de l'implémentation
La Story 5.4 implémente l'ensemble des mécanismes de la porte de contrôle humain H1 (FR18) et de l'API d'arbitrage pour le système d'orchestration IRYX :
- Suspension automatique de l'exécution au nœud `gate_h1` de LangGraph (`status: paused`, `current_phase: waiting_h1`).
- Endpoint `GET /api/v1/cases/{case_id}/investigations/{run_id}/plan` protégé par `verify_case_access` retournant le plan validé (`InvestigationPlan`) ou HTTP 404 `PLAN_NOT_FOUND`.
- Endpoint `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h1` protégé par RBAC (`ADMIN`, `INVESTIGATOR`, `ANALYST` requis, HTTP 403 `FORBIDDEN` pour `VIEWER` ou tiers).
- Prise en charge des trois décisions d'arbitrage :
  - `approve` : transition vers `status: running`, clôture de la phase H1 et activation de la phase `executor`.
  - `modify` : validation stricte du plan modifié (Pydantic v2, unicité et séquence 1..N des `step_id`, whitelist `ToolRegistry`, preuves scellées SHA-256 du dossier), mise à jour de `run.validated_plan` et passage à `executor`.
  - `reject` : clôture terminale propre (`status: completed`, `current_phase: gate_h1`) ou rebouclage borné (`iteration_count < 5`) vers la phase `planner` avec prise en compte du `feedback`.
- Sécurité renforcée : verrou pessimiste `with_for_update()` anti-concurrence, journalisation d'audit synchrone (FR27) et isolation stricte multi-dossiers.

### Fichiers modifiés
- `backend/src/iryx/core/exceptions.py` : Exceptions `PlanNotFoundException` (HTTP 404) et `InvalidGateStateException` (HTTP 422).
- `backend/src/iryx/orchestrator/models.py` : Membre `PhaseName.WAITING_H1 = "waiting_h1"`.
- `backend/src/iryx/orchestrator/schemas.py` : Schémas `H1Decision`, `H1DecisionRequest` (avec max_length=2000), `H1DecisionResponse`, et validation des `step_id` séquentiels dans `InvestigationPlan`.
- `backend/src/iryx/orchestrator/state.py` : Déclaration explicite de `h1_rejected` et `return_to_planner` dans `InvestigationState`.
- `backend/src/iryx/orchestrator/services.py` : Méthodes `get_investigation_plan`, `pause_at_gate_h1`, et `arbitrate_gate_h1` avec verrouillage `with_for_update()`, borne d'itération, vérification SHA-256 des preuves et audit.
- `backend/src/iryx/orchestrator/graph.py` : Nœud `gate_h1_node` avec suspension automatique en base, réinitialisation des flags et du plan lors du replan, propagation du feedback, et route conditionnelle `route_gate_h1`.
- `backend/src/iryx/orchestrator/router.py` : Endpoints FastAPI `GET /plan` et `POST /gates/h1`.
- `backend/tests/unit/test_orchestrator_api.py` : 27 nouveaux tests unitaires couvrant l'arbitrage, RBAC, isolation et cas limites.
- `backend/tests/unit/test_orchestrator_graph.py` : Nouveaux tests de suspension, streaming `graph.stream(...)`, rebouclage replan et persistance DB.

### Bilan des constats de revue
- **Patches appliqués** : 22 constats (4 high, 8 medium, 10 low) résolus et testés.
- **Éléments différés** : 0.
- **Constats rejetés** : 1 constat d'alignement d'intention (`false`), car la reprise asynchrone par checkpointer relève de la Story 5.6.
- **Recommandation de revue ultérieure** : `false` (tous les risques identifiés ont été corrigés et validés par 57 tests unitaires ciblés et 627 tests globaux à 100%).

### Vérifications effectuées
- `uv run ruff check` : 0 erreur de linting/typage.
- `uv run pytest backend/tests/unit/test_orchestrator_api.py backend/tests/unit/test_orchestrator_graph.py` : 57/57 passés (100%).
- `uv run pytest` : 627/627 passés (100%) sans aucune régression.

### Risques résiduels
- Aucun.
