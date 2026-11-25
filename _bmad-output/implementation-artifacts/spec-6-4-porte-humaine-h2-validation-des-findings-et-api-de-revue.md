---
title: "Story 6.4 : Porte Humaine H2 (Validation des findings) et API de revue"
type: 'feature'
created: '2026-11-25'
status: 'in-progress'
baseline_commit: 'f1d7a8b6c344c803da9343f9acc97fb6bdd0727e'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-6-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les constats formulés par l'Analyst et vérifiés par le Verifier ne doivent pas être intégrés à la chronologie ni aux rapports sans validation humaine qualifiée (principe Human-in-the-loop, FR19). L'analyste doit pouvoir inspecter les findings, ajuster leur qualification, les valider ou rejeter unitairement, et arbitrer la porte H2 de la session d'enquête.

**Approach:** Suspendre automatiquement l'exécution du graphe au nœud `gate_h2` (`status: paused`, `current_phase: waiting_h2`), exposer l'endpoint `POST /api/v1/cases/{case_id}/findings/{finding_id}/review` pour valider/rejeter les constats avec ajustement de sévérité/confiance et enregistrement de `created_by`, et exposer `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h2` acceptant les décisions `proceed` (après vérification que tous les constats sont arbitrés) et `reject` sous contrôle RBAC strict (interdit aux rôles viewer, HTTP 403).

## Boundaries & Constraints

**Always:**
- Respecter le principe Human-in-the-loop (FR19) : la session se suspend systématiquement à la porte H2 (`status: paused`, `current_phase: waiting_h2`) en base et dans l'état LangGraph en l'absence d'arbitrage préalable (`h2_approved`).
- Protéger les endpoints de revue de finding et d'arbitrage H2 par `require_case_role(MembershipRole.ADMIN, MembershipRole.INVESTIGATOR, MembershipRole.ANALYST)` : tout utilisateur `role: viewer` reçoit HTTP 403 Forbidden.
- Valider le payload de revue avec `FindingReview` (`action: "validate"|"reject"`). L'action `validate` passe le statut SQL à `validated`, `reject` à `rejected`. `created_by` prend l'UUID de l'analyste connecté.
- Rejeter tout déblocage `proceed` à la porte H2 si au moins un constat du dossier est encore au statut `proposed` (HTTP 400 Bad Request, code `UNREVIEWED_FINDINGS_EXIST`).
- Utiliser un verrouillage pessimiste SQL (`with_for_update`) lors de l'arbitrage H2 et valider l'état en attente H2 (`paused` et `waiting_h2` ou `gate_h2`), rejetant tout autre état avec HTTP 400 (`INVALID_GATE_STATE`).

**Never:**
- Aucun appel LLM durant l'étape de revue humaine ou d'arbitrage H2.
- Aucune transition vers `gate_h3` / `reporting` tant que la porte H2 n'a pas reçu la décision `proceed`.
- Aucun affaiblissement du cloisonnement multi-tenant : tout finding ou session hors du `case_id` retourne HTTP 404 Not Found.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Validation de constat | `POST .../findings/{id}/review` avec `{"action": "validate", "severity": "high", "confidence": "high"}` par Analyst | HTTP 200 OK, `FindingOut` avec `status: "validated"`, `severity: "high"`, `confidence: "high"`, `created_by: user_id` | N/A |
| Rejet de constat | `POST .../findings/{id}/review` avec `{"action": "reject"}` par Analyst | HTTP 200 OK, `FindingOut` avec `status: "rejected"` | N/A |
| Constat inexistant ou cross-case | `POST .../findings/{fake_id}/review` | HTTP 404 Not Found | `FindingNotFoundException` |
| Rôle Viewer sur revue ou H2 | `POST .../findings/{id}/review` ou `POST .../gates/h2` par viewer | HTTP 403 Forbidden | `require_case_role` |
| Déblocage nominal Porte H2 | `POST .../gates/h2` avec `{"decision": "proceed"}` quand 0 constats `proposed` | HTTP 200 OK, `status: "running"`, `current_phase: "gate_h3"`, `decision: "proceed"` | N/A |
| Déblocage H2 avec constats en attente | `POST .../gates/h2` avec `decision: "proceed"` et >=1 constat `proposed` | HTTP 400 Bad Request (`UNREVIEWED_FINDINGS_EXIST`) | `ValidationException` |
| Rejet de session à la Porte H2 | `POST .../gates/h2` avec `{"decision": "reject"}` | HTTP 200 OK, `status: "completed"`, `current_phase: "gate_h2"`, `decision: "reject"` | N/A |
| Arbitrage sur session non en pause H2 | `POST .../gates/h2` sur un run `status: running` | HTTP 400 Bad Request (`INVALID_GATE_STATE`) | `InvalidGateStateException` |
| Suspension automatique LangGraph | Arrivée au nœud `gate_h2` sans `h2_approved: True` | DB persistée à `paused` / `waiting_h2`, retour `{"current_phase": "waiting_h2", "status": "paused"}`, arrêt à `END` | N/A |

</frozen-after-approval>

## Code Map

- `backend/src/iryx/analytics/services.py` -- Méthode `FindingService.review_finding` pour appliquer la décision de revue humaine et persister le statut `validated` ou `rejected`.
- `backend/src/iryx/analytics/router.py` -- Endpoint `POST /api/v1/cases/{case_id}/findings/{finding_id}/review` protégé par `require_case_role`.
- `backend/src/iryx/orchestrator/models.py` -- Constante `WAITING_H2 = "waiting_h2"` dans `PhaseName`.
- `backend/src/iryx/orchestrator/schemas.py` -- Modèles Pydantic `H2Decision`, `H2DecisionRequest`, `H2DecisionResponse`.
- `backend/src/iryx/orchestrator/services.py` -- Méthodes `pause_at_gate_h2`, `arbitrate_gate_h2` et support de reprise dans `resume_investigation`.
- `backend/src/iryx/orchestrator/graph.py` -- Nœud `gate_h2_node` avec suspension automatique en base et routage conditionnel `route_gate_h2`.
- `backend/src/iryx/orchestrator/router.py` -- Endpoint `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h2`.
- `backend/tests/integration/test_findings_api.py` -- Tests d'intégration pour l'API de revue de findings.
- `backend/tests/unit/test_orchestrator_api.py` -- Tests unitaires pour l'arbitrage de la porte H2.
- `backend/tests/unit/test_orchestrator_graph.py` -- Tests unitaires pour le nœud `gate_h2_node` et sa conditional edge.

## Tasks & Acceptance

**Execution:**
- [ ] `backend/src/iryx/analytics/services.py` -- Implémenter la méthode `review_finding` sur `FindingService` -- Mettre à jour statut (`validated`/`rejected`), sévérité, confiance et `created_by` (FR19).
- [ ] `backend/src/iryx/analytics/router.py` -- Créer l'endpoint `POST /api/v1/cases/{case_id}/findings/{finding_id}/review` -- Exposer la revue unitaire sous contrôle `require_case_role` (FR19, D-04).
- [ ] `backend/src/iryx/orchestrator/models.py` -- Ajouter `WAITING_H2 = "waiting_h2"` dans `PhaseName` -- Normaliser la phase de pause H2 (D-09).
- [ ] `backend/src/iryx/orchestrator/schemas.py` -- Définir `H2Decision`, `H2DecisionRequest`, `H2DecisionResponse` -- Formaliser les schémas d'arbitrage H2 (D-04).
- [ ] `backend/src/iryx/orchestrator/services.py` -- Implémenter `pause_at_gate_h2`, `arbitrate_gate_h2` et gestion de phase H2 dans `resume_investigation` -- Assurer la persistance et l'arbitrage avec verrouillage pessimiste et vérification des constats (FR19).
- [ ] `backend/src/iryx/orchestrator/graph.py` -- Adapter `gate_h2_node`, `route_gate_h2` et `build_investigation_graph` -- Câbler la suspension automatique et la conditional edge vers `gate_h3` ou `END` (D-09).
- [ ] `backend/src/iryx/orchestrator/router.py` -- Ajouter l'endpoint `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h2` -- Permettre le déblocage humain de la session (FR19).
- [ ] `backend/tests/integration/test_findings_api.py` -- Ajouter tests d'intégration de revue de finding (validation, rejet, 403 viewer, 404 not found) -- Garantir l'intégrité de l'API de revue.
- [ ] `backend/tests/unit/test_orchestrator_api.py` -- Ajouter tests d'arbitrage H2 (proceed nominal, 400 constats proposed, reject, 403 viewer, 400 invalid state) -- Garantir le contrôle d'état H2.
- [ ] `backend/tests/unit/test_orchestrator_graph.py` -- Ajouter tests du nœud `gate_h2_node` et conditional edge `route_gate_h2` -- Valider la suspension et la reprise dans LangGraph.

**Acceptance Criteria:**
- Given une session d'enquête atteignant l'état `gate_h2`, when le graphe LangGraph s'exécute, then la session se met en pause avec le statut `waiting_h2` (`InvestigationRun.status = "paused"`).
- Given une liste de constats au statut `proposed`, when l'analyste appelle `POST /api/v1/cases/{case_id}/findings/{finding_id}/review` avec `{"action": "validate", "severity": "high", "confidence": "high"}`, then le constat passe au statut `validated`, ses attributs sont ajustés et l'analyste est enregistré dans `created_by`.
- Given un constat à rejeter, when l'analyste appelle `review` avec `{"action": "reject"}`, then son statut passe à `rejected`.
- Given un utilisateur avec rôle `viewer`, when il tente de revendre/valider un constat ou d'arbitrer la porte H2, then le serveur retourne HTTP 403 Forbidden.
- Given une session en pause à la porte H2 avec tous constats arbitrés, when l'analyste soumet `POST .../gates/h2` avec `{"decision": "proceed"}`, then la porte H2 est débloquée et la session transite vers la phase suivante (`gate_h3`).
- Given une session en pause à la porte H2 avec au moins un constat restant au statut `proposed`, when l'analyste soumet `POST .../gates/h2` avec `{"decision": "proceed"}`, then le serveur rejette la requête avec HTTP 400 Bad Request (`UNREVIEWED_FINDINGS_EXIST`).

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Design Notes

1. **Vérification exhaustive préalable des constats lors de H2** : `arbitrate_gate_h2` vérifie via un `COUNT` qu'aucun constat du dossier n'est au statut `FindingStatus.PROPOSED`. Si des constats proposed subsistent, l'arbitrage `proceed` est rejeté avec `ValidationException` (code `UNREVIEWED_FINDINGS_EXIST`), garantissant l'arbitrage humain préalable de tous les constats.
2. **Alignement d'architecture avec la Porte H1** : La porte H2 (`pause_at_gate_h2`, `arbitrate_gate_h2`, `gate_h2_node`, `route_gate_h2`) applique exactement le même cycle de vie que la porte H1 (Story 5.4), garantissant l'homogénéité du modèle d'état et des transitions.

## Verification

**Commands:**
- `uv run pytest backend/tests/integration/test_findings_api.py -k review` -- expected: Tous les tests d'intégration de l'API de revue de findings passent avec succès.
- `uv run pytest backend/tests/unit/test_orchestrator_api.py -k gate_h2` -- expected: Tous les tests d'arbitrage de la porte H2 passent avec succès.
- `uv run pytest backend/tests/unit/test_orchestrator_graph.py -k gate_h2` -- expected: Tous les tests du nœud et de la conditional edge H2 passent avec succès.
- `uv run ruff check backend/src backend/tests` -- expected: 0 erreur, conformité PEP8 et typage.
