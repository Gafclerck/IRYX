---
status: awaiting-operator
operator_actions:
  - "Vérifier la prévisualisation anonymisée de la synthèse du dossier via GET /api/v1/cases/{case_id}/investigations/{run_id}/anonymized-preview, et confirmer que la version intégrale transmise à un LLM externe est acceptable."
  - "Soumettre la décision à la porte H3 via POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h3 avec {\"decision\": \"approve\"} pour débloquer l'écriture assistée par un LLM externe, ou {\"decision\": \"reject\"} pour activer le gabarit déterministe local sans appel LLM."
---

# 8-2-porte-humaine-h3-autorisation-d-envoi-llm-externe-et-prévisu

## Définition de l'histoire

**En tant qu'** analyste SOC ou RSSI,
**Je veux** prévisualiser la synthèse d'enquête pseudonymisée à la porte H3 et autoriser ou refuser explicitement son envoi vers un LLM externe pour la rédaction du rapport,
**Afin de** garantir la souveraineté des données d'incident.

Architecture mobilisée : D-03, D-04, D-09, D-19, D-24.

## Critères d'acceptation

- **Nominal :** l'analyste interroge `GET /api/v1/cases/{case_id}/investigations/{run_id}/anonymized-preview` pour vérifier la version intégrale des données pseudonymisées qui seraient transmises ; l'analyste soumet sa décision via `POST /api/v1/cases/{case_id}/investigutions/{run_id}/gates/h3` avec `{"decision": "approve"}` ; le graphe débloque l'étape de rédaction assistée par LLM externe vers le nœud `reporting`.
- **Erreur et validation :** l'analysiste refusant l'envoi (`decision: "reject"` ou mode hors-ligne), le système bascule sur un gabarit déterministe local sans appel LLM pour compiler le rapport.
- **Autorisation et sécurité :** toute tentative d'envoi de données brutes vers une API externe sans validation préalable de H3 : la porte H3 constitue une barrière infranchissable dans le code empêchant tout appel réseau LLM avant approbation formelle.

## Implémenté (agent, Story 8.2)

- `orchestrator/models.py` : ajout du statut de phase `waiting_h3` (PhaseName).
- `orchestrator/state.py` : champ `h3_rejected` ajouté à `InvestigationState`.
- `orchestrator/schemas.py` : `H3Decision`, `H3DecisionRequest`, `H3DecisionResponse`, `AnonymizedPreviewOut`.
- `orchestrator/services.py` : `pause_at_gate_h3` (statut `paused`, `current_phase` `waiting_h3`, phase `gate_h3` active), `arbitrate_gate_h3` (approve → `running` + nœud `reporting` actif ; reject → `running` + nœud `reporting` en mode local), `get_anonymized_preview` (aperçu pseudonymisé via `DeterministicPseudonymizer`, FR25/D-19), mise à jour de `resume_investigation` (injection `h3_approved`/`h3_rejected`).
- `orchestrator/graph.py` : `gate_h3_node` — suspend l'exécution à `waiting_h3` via `pause_at_gate_h3` ; la seule voie vers `reporting` requiert `h3_approved` ; le reject active le gabarit local (`local_report_mode`) sans appel LLM. Barrière structurelle : le graphe ne route vers `reporting` qu'après `h3_approved`.
- `orchestrator/router.py` : `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h3` (roles ADMIN/INVESTIGATOR/ANALYST) et `GET /api/v1/cases/{case_id}/investigations/{run_id}/anonymized-preview`.
- Tests : nouveaux tests d'API pour l'approbation, le refus, le statut `waiting_h3`, les vérifications RBAC (403), l'état invalide (400), le cross-case 404, et le test de lifecycle `pause_at_gate_h3`. Tous les 704 tests unitaires passent.

## Auto Run Result

Status: awaiting-operator
Blocking condition: Aucune — le travail agent a été terminé et commité ; l'histoire est « finie autant que l'agent peut l'emporter ». Le statut doit être confirmé par l'opérateur via les actions listées ci-dessus.
