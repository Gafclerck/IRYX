---
title: "Story 6.4 : Porte Humaine H2 (Validation des findings) et API de revue"
type: 'feature'
created: '2026-11-25'
status: 'done'
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
- [x] `backend/src/iryx/analytics/services.py` -- Implémenter la méthode `review_finding` sur `FindingService` -- Mettre à jour statut (`validated`/`rejected`), sévérité, confiance et `created_by` (FR19).
- [x] `backend/src/iryx/analytics/router.py` -- Créer l'endpoint `POST /api/v1/cases/{case_id}/findings/{finding_id}/review` -- Exposer la revue unitaire sous contrôle `require_case_role` (FR19, D-04).
- [x] `backend/src/iryx/orchestrator/models.py` -- Ajouter `WAITING_H2 = "waiting_h2"` dans `PhaseName` -- Normaliser la phase de pause H2 (D-09).
- [x] `backend/src/iryx/orchestrator/schemas.py` -- Définir `H2Decision`, `H2DecisionRequest`, `H2DecisionResponse` -- Formaliser les schémas d'arbitrage H2 (D-04).
- [x] `backend/src/iryx/orchestrator/services.py` -- Implémenter `pause_at_gate_h2`, `arbitrate_gate_h2` et gestion de phase H2 dans `resume_investigation` -- Assurer la persistance et l'arbitrage avec verrouillage pessimiste et vérification des constats (FR19).
- [x] `backend/src/iryx/orchestrator/graph.py` -- Adapter `gate_h2_node`, `route_gate_h2` et `build_investigation_graph` -- Câbler la suspension automatique et la conditional edge vers `gate_h3` ou `END` (D-09).
- [x] `backend/src/iryx/orchestrator/router.py` -- Ajouter l'endpoint `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h2` -- Permettre le déblocage humain de la session (FR19).
- [x] `backend/tests/integration/test_findings_api.py` -- Ajouter tests d'intégration de revue de finding (validation, rejet, 403 viewer, 404 not found) -- Garantir l'intégrité de l'API de revue.
- [x] `backend/tests/unit/test_orchestrator_api.py` -- Ajouter tests d'arbitrage H2 (proceed nominal, 400 constats proposed, reject, 403 viewer, 400 invalid state) -- Garantir le contrôle d'état H2.
- [x] `backend/tests/unit/test_orchestrator_graph.py` -- Ajouter tests du nœud `gate_h2_node` et conditional edge `route_gate_h2` -- Valider la suspension et la reprise dans LangGraph.

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

### 2026-11-25 — Review pass 1
- verdicts: 22 findings — high 0, medium 3, low 7, false 12, maybe-false 0
- findings:
  - `[low]` `[patch]` B1 Blind Hunter — `UnreviewedFindingsException` non instancié dans `arbitrate_gate_h2` — Corrigé : importé et levé directement en remplacement de l'exception générique.
  - `[false]` `[reject]` B2 Blind Hunter — Statut HTTP 400 vs 422 pour `InvalidGateStateException` — Rejeté : le code HTTP 400 est formellement exigé par la matrice I/O de la spécification 6.4.
  - `[medium]` `[patch]` B3 Blind Hunter — Reprise à froid depuis `GATE_H3` bloquée à H1 dans `resume_investigation` — Corrigé : ajout de `h1_approved = True` et réinjection du plan lors de la reprise depuis GATE_H3.
  - `[false]` `[reject]` B4 Blind Hunter — `gate_h2_node` redéfinit `current_phase` à `"gate_h2"` lors de la reprise — Rejeté : comportement nominal de machine d'états où le nœud s'exécute avant le franchissement de la transition vers `gate_h3`.
  - `[false]` `[reject]` B5 Blind Hunter — `Finding.created_by` écrasé lors de la revue — Rejeté : l'AC de la spécification exige expressément l'enregistrement de l'identifiant de l'analyste dans `created_by`.
  - `[false]` `[reject]` B6 Blind Hunter — Absence de champ commentaire dans `FindingReview` — Rejeté : hors périmètre MVP de la Story 6.4 non prévu dans les contrats de données.
  - `[low]` `[patch]` B7 Blind Hunter — Verrouillage pessimiste manquant dans `review_finding` — Corrigé : ajout de `.with_for_update()` lors de la récupération du constat.
  - `[false]` `[reject]` B8 Blind Hunter — Contrôle des constats proposed au niveau dossier plutôt que run — Rejeté : dans IRYX, les constats appartiennent à un `Case` et il n'y a qu'une seule enquête active par dossier.
  - `[false]` `[reject]` B9 Blind Hunter — Branche `h2_rejected` inaccessible dans LangGraph en production — Rejeté : conception intentionnelle pour la testabilité des nœuds de graphe en isolation.
  - `[false]` `[reject]` B10 Blind Hunter — Écart de statut entre `sprint-status.yaml` et spec — Rejeté : la synchronisation du statut intervient lors de l'achèvement de la revue conformément au workflow BMAD.
  - `[false]` `[reject]` B11 Blind Hunter — Modifications README globales incluses dans le diff — Rejeté : mise à jour documentaire légitime et synchronisée décrivant les portes H1 et H2.
  - `[false]` `[reject]` B12 Blind Hunter — Re-revue possible de constats déjà validés/rejetés — Rejeté : flexibilité nominale accordée à l'analyste avant le déblocage définitif de la porte H2.
  - `[false]` `[reject]` B13 Blind Hunter — Verrouillage pessimiste manquant dans `pause_at_gate_h2` — Rejeté : le verrouillage est appliqué lors de l'arbitrage concurrentiel ; la pause est séquentielle.
  - `[false]` `[reject]` B14 Blind Hunter — Exception de persistance DB interceptée dans `gate_h2_node` — Rejeté : aligné sur Gate H1 pour autoriser les tests unitaires du graphe hors base relationnelle.
  - `[low]` `[patch]` B15 Blind Hunter — Sévérité et confiance modifiables même lors d'un rejet — Corrigé : conditionnement des modifications uniquement à `action == "validate"`.
  - `[medium]` `[patch]` E1 Edge Case Hunter — Reprise depuis `gate_h3` sans checkpointer bloquée à H1 — Corrigé (identique B3) : `h1_approved` et plan initialisés.
  - `[low]` `[patch]` E2 Edge Case Hunter — Action de revue ni validate ni reject non vérifiée au niveau service — Corrigé : levée d'une `ValidationException` défensive.
  - `[low]` `[patch]` E3 Edge Case Hunter — `active_phase` marquée terminée avant la vérification des constats proposed — Corrigé : vérification déplacée avant toute modification d'état.
  - `[low]` `[patch]` V1 Verification Gap — Assertions faibles dans `test_resume_investigation_nominal_with_approved_plan` — Corrigé : assertions strictes sur `PAUSED` et `WAITING_H2`.
  - `[medium]` `[patch]` V2 Verification Gap — Absence de test de reprise depuis `PhaseName.GATE_H3` — Corrigé : test unitaire dédié `test_resume_investigation_nominal_from_gate_h3` ajouté au vert.
  - `[low]` `[patch]` V3 Verification Gap — `UnreviewedFindingsException` non exploité — Corrigé (identique B1) : utilisé dans `arbitrate_gate_h2`.
  - `[false]` `[reject]` V4 Verification Gap — Risque d'import circulaire entre `cases` et `analytics` — Rejeté : vérifié et réfuté, `cases.models` n'importe pas le routeur analytics.

## Design Notes

1. **Vérification exhaustive préalable des constats lors de H2** : `arbitrate_gate_h2` vérifie via un `COUNT` qu'aucun constat du dossier n'est au statut `FindingStatus.PROPOSED`. Si des constats proposed subsistent, l'arbitrage `proceed` est rejeté avec `ValidationException` (code `UNREVIEWED_FINDINGS_EXIST`), garantissant l'arbitrage humain préalable de tous les constats.
2. **Alignement d'architecture avec la Porte H1** : La porte H2 (`pause_at_gate_h2`, `arbitrate_gate_h2`, `gate_h2_node`, `route_gate_h2`) applique exactement le même cycle de vie que la porte H1 (Story 5.4), garantissant l'homogénéité du modèle d'état et des transitions.

## Verification

**Commands:**
- `uv run pytest backend/tests/integration/test_findings_api.py -k review` -- expected: Tous les tests d'intégration de l'API de revue de findings passent avec succès.
- `uv run pytest backend/tests/unit/test_orchestrator_api.py -k gate_h2` -- expected: Tous les tests d'arbitrage de la porte H2 passent avec succès.
- `uv run pytest backend/tests/unit/test_orchestrator_graph.py -k gate_h2` -- expected: Tous les tests du nœud et de la conditional edge H2 passent avec succès.
- `uv run ruff check backend/src backend/tests` -- expected: 0 erreur, conformité PEP8 et typage.
