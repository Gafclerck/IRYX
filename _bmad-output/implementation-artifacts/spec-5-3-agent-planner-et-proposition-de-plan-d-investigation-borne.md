---
title: "Story 5.3 : Agent Planner et proposition de plan d'investigation borné"
type: 'feature'
created: '2026-11-25'
status: 'done'
baseline_commit: '2af1ae17f536f7e712b0764fc28b1f558ed57e6f'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'investigation forensique numérique requiert une sélection ciblée et ordonnée d'outils d'analyse sur les preuves scellées, sans risquer d'emballement d'inférence, de boucles infinies ou d'exécution d'outils non autorisés.

**Approach:** Implémenter l'agent `PlannerAgent` générant un plan d'investigation structuré (`InvestigationPlan`), strictement borné à 10 étapes et vérifiant l'appartenance des outils au registre `ToolRegistry`. Intégrer un mécanisme d'auto-correction (jusqu'à 2 réessais) en cas de JSON/schéma invalide, et une détection immédiate sans appel LLM si le dossier ne comporte aucune preuve scellée.

## Boundaries & Constraints

**Always:**
- Utiliser le schéma Pydantic `InvestigationPlan` composé d'au maximum 10 `InvestigationPlanStep` ordonnées (`step_id`, `tool_name`, `target_evidence_id`, `parameters`, `rationale`) (FR17, NFR-PERF-05).
- Valider que chaque `tool_name` proposé appartient strictement aux outils enregistrés dans `ToolRegistry` (liste blanche MVP) et que chaque `target_evidence_id` correspond à une preuve existante dans le dossier.
- Utiliser `UnifiedLLMClient(role=LLMRole.PLANNER)` configuré avec `build_system_prompt` et encapsuler systématiquement l'inventaire des preuves dans les balises `<forensic_data>` pour immunisation contre l'injection indirecte (NFR-SEC-06).
- En cas d'absence de preuve scellée (`sha256` non nul), interrompre immédiatement l'agent sans consommer de tokens d'inférence, formuler une notification et marquer la session en attente de preuves (`status: paused`).
- Si la sortie brute du LLM échoue à la désérialisation JSON ou à la validation du schéma Pydantic, exécuter jusqu'à 2 corrections avec rappel des erreurs avant de lever `InvalidPlanException`.
- Sauvegarder le plan validé dans `InvestigationRun.validated_plan` et avancer la phase d'exécution vers `gate_h1` dans l'état du graphe LangGraph.

**Never:**
- Jamais plus de 10 étapes dans le plan d'investigation généré (NFR-PERF-05).
- Jamais d'appel LLM si aucune preuve scellée n'est présente dans le dossier.
- Jamais d'acceptation d'un outil inconnu ou non enregistré dans `ToolRegistry`.
- Jamais d'injection de métadonnées de preuves non assainies sans balisage `<forensic_data>`.
- Jamais d'exécution directe d'outils forensiques à ce stade (réservée à l'agent `Executor` après validation H1).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Planification nominale | Dossier avec preuves scellées (sha256 calculé), appel Planner | Plan valide (<= 10 étapes), `InvestigationRun.validated_plan` alimenté, transition vers `gate_h1` | N/A |
| Absence de preuve scellée | Dossier avec 0 preuve ou preuves sans sha256 | 0 appel LLM, notification formulée dans l'état, statut `paused` en attente de preuves | N/A |
| Sortie LLM JSON non valide | Réponse initiale malformée (non-JSON ou tronqué) | Prompt de correction avec erreur JSON envoyé au LLM (max 2 retries), validation du plan si corrigé | Si >2 échecs, levée de `InvalidPlanException` |
| Schéma Pydantic invalide | Champs manquants ou types incorrects | Prompt de réessai contenant les erreurs de validation Pydantic (max 2 retries) | Si >2 échecs, levée de `InvalidPlanException` |
| Dépassement limite 10 étapes | Le LLM génère un plan de 11 étapes ou plus | Validation Pydantic échoue (`len(steps) <= 10`), tentative de correction avec consigne stricte | Si persistance, levée de `InvalidPlanException` |
| Outil non autorisé | Outil non présent dans `ToolRegistry` (ex: `bash_eval`) | Validation rejetée, correction demandée au LLM | Si persistance, levée de `InvalidPlanException` |
| Preuve inconnue | `target_evidence_id` inexistant dans le dossier | Validation rejetée, étape non valide | Correction demandée ou levée de `InvalidPlanException` |

</frozen-after-approval>

## Code Map

- `backend/src/iryx/core/exceptions.py` -- Définition de `InvalidPlanException` héritant de `ValidationException` avec code `"INVALID_PLAN"`
- `backend/src/iryx/orchestrator/schemas.py` -- Schémas Pydantic `InvestigationPlanStep` et `InvestigationPlan` avec validation stricte du nombre d'étapes (<=10)
- `backend/src/iryx/orchestrator/planner.py` -- Module de l'agent `PlannerAgent` intégrant `UnifiedLLMClient`, `build_system_prompt`, `wrap_forensic_data`, validation des outils via `ToolRegistry`, boucle d'auto-correction (jusqu'à 2 retries) et court-circuit sans appel LLM si aucune preuve scellée
- `backend/src/iryx/orchestrator/graph.py` -- Intégration de l'agent Planner dans le nœud `planner_node` du graphe d'états LangGraph
- `backend/src/iryx/orchestrator/services.py` -- Mise à jour de `InvestigationRun.validated_plan` lors de la génération réussie d'un plan
- `backend/tests/unit/test_planner_agent.py` -- Tests unitaires complets de l'agent Planner (cas nominal, limites 10 étapes, auto-correction, 0 preuves, outils non autorisés, injection de prompt)
- `backend/tests/unit/test_orchestrator_graph.py` -- Vérification de la transition et de la complétion du nœud `planner` dans le graphe LangGraph

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/core/exceptions.py` -- Ajouter `InvalidPlanException` avec code `"INVALID_PLAN"` et statut HTTP 422.
- [x] `backend/src/iryx/orchestrator/schemas.py` -- Implémenter les schémas Pydantic `InvestigationPlanStep` (`step_id`, `tool_name`, `target_evidence_id`, `parameters`, `rationale`) et `InvestigationPlan` (`steps`, `summary`, validateur max 10 étapes).
- [x] `backend/src/iryx/orchestrator/planner.py` -- Créer `PlannerAgent` avec gestion des preuves scellées, prompt sécurisé `<forensic_data>`, validation contre le registre d'outils, et boucle d'auto-correction (max 2 réessais).
- [x] `backend/src/iryx/orchestrator/graph.py` -- Mettre à jour `planner_node` pour appeler la logique du Planner, mettre à jour l'état LangGraph (`plan`, `current_phase`) et gérer le passage à `gate_h1` ou la suspension en attente de preuves.
- [x] `backend/src/iryx/orchestrator/services.py` -- Ajouter une méthode de persistance du plan validé sur `InvestigationRun`.
- [x] `backend/tests/unit/test_planner_agent.py` -- Implémenter les tests unitaires couvrant l'ensemble de la matrice I/O (cas nominal, court-circuit sans preuves, correction d'erreurs, rejet des outils inconnus, NFR-SEC-06).
- [x] `backend/tests/unit/test_orchestrator_graph.py` -- Actualiser et compléter les tests du graphe LangGraph pour valider l'exécution du nœud `planner`.

**Acceptance Criteria:**
- Given le graphe LangGraph atteignant le nœud `planner` avec au moins une preuve scellée dans le dossier, when l'agent Planner génère sa proposition de plan, then la sortie est validée contre le schéma Pydantic `InvestigationPlan` contenant une liste ordonnée d'étapes (`step_id`, `tool_name`, `target_evidence_id`, `parameters`, `rationale`).
- Given une proposition de plan d'investigation, then le nombre total d'étapes est borné à un maximum de 10 étapes (NFR-PERF-05).
- Given un plan d'investigation validé, then il est sauvegardé dans `InvestigationRun.validated_plan` (en attente d'approbation) et l'exécution progresse vers le nœud `gate_h1`.
- Given un dossier ne comportant aucune preuve scellée, when le Planner s'exécute, then l'agent formule une notification indiquant l'absence de matière analysable et le statut de la session passe en attente de preuves sans consommer de tokens d'inférence.
- Given une sortie brute de l'agent ne respectant pas le schéma JSON attendu ou les contraintes Pydantic, when l'erreur est détectée, then le validateur déclenche jusqu'à 2 corrections avant de lever `InvalidPlanException`.
- Given les étapes proposées par le Planner, when les outils sont inspectés, then tout outil proposé existe obligatoirement dans le registre `ToolRegistry`.

## Implementation Notes

- Implémentation du modèle d'exception `InvalidPlanException` (HTTP 422, code `"INVALID_PLAN"`).
- Création des schémas Pydantic v2 `InvestigationPlanStep` et `InvestigationPlan` avec validation stricte du nombre d'étapes (1 <= steps <= 10, NFR-PERF-05) et `step_id > 0`.
- Développement de `PlannerAgent` dans `iryx.orchestrator.planner` avec :
  - Court-circuit 0-token immédiat et suspension de session en l'absence de preuves scellées (`sha256` non nul).
  - Immunisation contre l'injection de prompts (NFR-SEC-06) via `wrap_forensic_data` et `build_system_prompt`.
  - Extraction robuste du JSON via expressions régulières pour gérer les préambules/postambles conversationnels.
  - Validation stricte des outils contre `ToolRegistry` (`MVP_TOOL_WHITELIST`) et des UUIDs de preuves du dossier.
  - Boucle d'auto-correction bornée à 2 tentatives en cas d'erreur de schéma ou JSON.
  - Persistance du plan validé dans `InvestigationRun.validated_plan` et suspension via `InvestigationService`.
  - Prise en charge des modes asynchrone (`plan`/`generate_plan`) et synchrone (`plan_sync`/`generate_plan_sync`).
- Intégration dans le graphe LangGraph via `planner_node` avec validation préventive des plans pré-existants et edge conditionnel `route_planner` routant `paused` et `failed` vers `END`.
- Suite complète de 30 tests unitaires dédiée (`test_planner_agent.py` et `test_orchestrator_graph.py`) couvrant 100% de la matrice I/O et des cas limites.

## Spec Change Log

## Review Triage Log

| ID | Source | Verdict | Evidence & Rationale |
|---|---|---|---|
| VG-1 | verification-gap | medium | `InvestigationService.pause_investigation` manquait de test unitaire dédié ; corrigé par `test_investigation_service_pause_investigation`. |
| VG-2 | verification-gap | medium | Persistance en base dans `PlannerAgent.plan` (save et pause) manquait de test d'intégration ; corrigé par tests dédiés dans `test_planner_agent.py`. |
| VG-3 | verification-gap | medium | Résolution des preuves via requête ORM `Evidence` (`evidences=None`) manquait de test ; corrigé par test unitaire mocké. |
| VG-4 | verification-gap | low | `save_validated_plan` levait `ValidationException` au lieu de `InvalidPlanException` ; corrigé. |
| VG-5 | verification-gap | medium | `InvestigationPlan.steps` manquait de la contrainte `min_length=1` ; corrigée dans le schéma Pydantic. |
| EC-1 | edge-case-hunter | low | Gestion de `RuntimeError` dans `plan_sync` lors de la réutilisation de coroutine dans un pool ; coroutine exécutée proprement. |
| EC-2 | edge-case-hunter | medium | Risque de `TypeError` si `file_size` vaut explicitement `None` (`int(None)`) ; corrigé par `int(item.get("file_size") or 0)`. |
| EC-3 | edge-case-hunter | low | Normalisation défensive des UUIDs de preuves ; format canonique validé. |
| EC-4 | edge-case-hunter | medium | Doublon VG-4 : validation de dictionnaire dans `save_validated_plan` levant ValidationError non typée ; corrigé en `InvalidPlanException`. |
| EC-5 | edge-case-hunter | medium | `pause_investigation` appelé sur une session `completed` ou `failed` violait le cycle de vie ; garde ajoutée avec HTTP 422 `INVALID_STATUS_TRANSITION`. |
| EC-6 | edge-case-hunter | medium | `planner_node` acceptait un plan pré-existant sans validation Pydantic ; validation intégrée avec transition en `failed` si invalide. |
| EC-7 | edge-case-hunter | low | Doublon BH-6 : absence de contrainte `step_id > 0` ; ajout de `gt=0` dans `InvestigationPlanStep`. |
| BH-1 | blind-hunter | medium | Extraction naïve de code fence échouant si préambule texte LLM ; ajout d'expression régulière et recherche des accolades externes. |
| BH-2 | blind-hunter | medium | Doublon EC-2 : risque de `TypeError` sur `file_size=None` ; corrigé. |
| BH-3 | blind-hunter | low | Doublon EC-1 : isolation de session SQLAlchemy entre threads dans `plan_sync` ; documenté et sécurisé. |
| BH-4 | blind-hunter | false | Rejeté : la persistance par `PlannerAgent` respecte l'exigence du brief et délègue à `InvestigationService`. |
| BH-5 | blind-hunter | low | Accès à `_whitelist` du registre ; encapsulation vérifiée. |
| BH-6 | blind-hunter | low | Doublon EC-7 : absence de contrainte `step_id > 0` ; ajout de `gt=0`. |
| BH-7 | blind-hunter | medium | Doublon VG-5 : absence de `min_length=1` sur `InvestigationPlan.steps` ; corrigé. |
| BH-8 | blind-hunter | low | Surcharge de `__getattr__` sur `PlannerResult` ; accès direct aux propriétés du plan maintenu sans impact Pydantic. |
| BH-9 | blind-hunter | medium | `InvalidPlanException` non intercepté dans `planner_node` menaçait de crasher LangGraph ; try/except intégré avec statut `failed`. |
| BH-10 | blind-hunter | medium | Doublon EC-6 : validation préventive du plan pré-existant dans `state["plan"]` ; corrigé. |
| BH-11 | blind-hunter | medium | `route_planner` ne routait pas l'état `failed` vers `END` ; corrigé. |
| BH-12 | blind-hunter | low | Propagation du contexte d'incident `incident_description` dans `planner_node` ; intégré. |
| BH-13 | blind-hunter | low | Notification de pause opérationnelle polluant `state["errors"]` ; séparée dans `context["notification"]`. |
| BH-14 | blind-hunter | low | Mise à jour de `current_phase` en base lors de `save_validated_plan` ; documenté. |
| BH-15 | blind-hunter | medium | Doublon VG-3 / BH-1 : tests manquants pour préambules LLM et requêtes ORM DB ; ajoutés. |

## Design Notes

- **Court-circuit 0-token en l'absence de preuve :** Si un dossier est vierge ou ne comporte que des preuves en cours d'ingestion (sans hash `sha256`), l'agent évite tout appel réseau à l'API LLM. L'état d'investigation enregistre une alerte explicite et la session est suspendue au statut `paused` avec mention `"attente de preuves scellées"`.
- **Boucle d'auto-correction bornée :** Lorsque le LLM renvoie un JSON malformé ou viole le schéma `InvestigationPlan`, une invite de correction enrichie des erreurs de parsing (`pydantic.ValidationError`) est soumise au modèle. Cette boucle est bornée à 2 tentatives pour respecter NFR-PERF-05 et éviter tout surcoût.

## Verification

**Commands:**
- `uv run pytest backend/tests/unit/test_planner_agent.py backend/tests/unit/test_orchestrator_graph.py` -- expected: Tous les tests unitaires du Planner et du graphe LangGraph passent à 100%.
- `uv run pytest` -- expected: Suite complète (>571 tests) sans aucune régression.
