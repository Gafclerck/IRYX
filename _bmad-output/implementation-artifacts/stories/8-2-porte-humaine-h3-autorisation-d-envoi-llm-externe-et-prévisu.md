---
status: done
---

# 8-2-porte-humaine-h3-autorisation-d-envoi-llm-externe-et-prévisu

## Définition de l'histoire

**En tant qu'** analyste SOC ou RSSI,
**Je veux** prévisualiser la synthèse d'enquête pseudonymisée à la porte H3 et autoriser ou refuser explicitement son envoi vers un LLM externe pour la rédaction du rapport,
**Afin de** garantir la souveraineté des données d'incident.

Architecture mobilisée : D-03, D-04, D-09, D-19, D-24.

## Critères d'acceptation

- **Nominal :** l'analyste interroge `GET /api/v1/cases/{case_id}/investigations/{run_id}/anonymized-preview` pour vérifier la version pseudonymisée de la synthèse, puis soumet `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h3` avec `{"decision": "approve"}` ; le graphe débloque la rédaction assistée par LLM externe vers le nœud `reporting`.
- **Erreur et validation :** un refus (`{"decision": "reject"}`) active le gabarit déterministe local (`local_report_mode`) sans appel LLM ; aucune reprise ne peut réapprouver implicitement un envoi externe.
- **Autorisation et sécurité :** sans décision H3 enregistrée dans le checkpointer, `gate_h3_node` suspend le run en `waiting_h3` et `reporting_node` renvoie également vers cet état : la barrière est infranchissable, y compris par le chemin direct `gate_h3 → reporting`.

## Implémenté (Story 8.2)

- `orchestrator/models.py` : ajout de `PhaseName.WAITING_H3`.
- `orchestrator/state.py` : champs `h3_approved` et `h3_rejected` dans `InvestigationState`.
- `orchestrator/schemas.py` : `H3Decision`, `H3DecisionRequest`, `H3DecisionResponse`, `AnonymizedPreviewOut`.
- `orchestrator/services.py` :
  - `pause_at_gate_h3()` : passe le run en `paused` / `waiting_h3` avec une phase `gate_h3` active ;
  - `arbitrate_gate_h3()` : verrou pessimiste sur le run, persistance de la décision **dans le checkpointer** (`h3_approved`, `h3_rejected`, `h3_feedback`, `local_report_mode`) avant l'avancement DB, puis transition vers `reporting` ;
  - `get_anonymized_preview()` : aperçu pseudonymisé via `DeterministicPseudonymizer` (FR25 / D-19) ;
  - `resume_investigation()` : ne réinjecte plus `h3_approved=True` ; la décision est relue depuis le snapshot et un run sans verdict repasse par la porte.
- `orchestrator/graph.py` : `gate_h3_node()` suspend sans décision, `reporting_node()` refuse tout accès sans `h3_approved` ou `h3_rejected`/`local_report_mode`.
- `orchestrator/router.py` : `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h3` (ADMIN / INVESTIGATOR / ANALYST) et `GET …/anonymized-preview` (contrôle d'accès au dossier).

## Vérification

- Tests ciblés : `uv run pytest -q tests/unit/test_orchestrator_api.py tests/unit/test_orchestrator_graph.py tests/unit/test_checkpointer_and_resume.py`.
- Couverture ajoutée : approve 200, reject 200, viewer 403, état invalide 400, cross-case 404, aperçu 200/404, cycle de vie `pause_at_gate_h3`, persistance du rejet dans le checkpointer, reprise sans verdict bloquée à la porte, garde-fou `reporting_node`.
- Qualité : `uv run ruff check src tests` → `All checks passed!`.
- Suite complète backend : `uv run pytest -q` → **871 passed**.

## Traçabilité

La décision et le feedback sont conservés dans le checkpointer (`context.h3_feedback`) et dans les logs applicatifs. L'écriture dans la table immuable `AuditEvent` reste au périmètre de la Story 8.5, conformément à la séparation des responsabilités de l'epic 8.

## Auto Run Result

Status: done. Le travail initialement préservé sur `attempt-preserve/20261125-130311-031b-a503d4e2` a été récupéré, corrigé et intégré ; aucune action opérateur bloquante ne subsiste.
