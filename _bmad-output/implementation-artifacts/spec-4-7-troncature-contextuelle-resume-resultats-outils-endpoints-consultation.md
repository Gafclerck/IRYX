---
title: "Story 4.7 : Troncature contextuelle, résumé des résultats d'outils et endpoints de consultation (FR9, FR10, NFR-PERF-06)"
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: '952fd63db951da59f25f62c651328150bbf14dd4'
baseline_revision: '952fd63db951da59f25f62c651328150bbf14dd4'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/docs/02-agents-et-outils.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les outils forensiques produisent des volumes volumineux (milliers d'événements EVTX, mégaoctets de logs) qui risquent de saturer la fenêtre de contexte des agents LLM, alors que l'analyste doit pouvoir auditer l'intégralité des preuves en base.

**Approach:** Implémenter un module de troncature et résumé pour agents IA (`AgentPayload` borné à 50 observations, 8 Ko et 200 lignes max avec bandeau `[TRUNCATED: X éléments masqués. Consulter Observation pour la totalité]`), intégré dans `ToolExecutionResult` et `ToolRunner`, et exposer les endpoints de consultation paginée `GET /api/v1/cases/{case_id}/tool-executions` et `GET /api/v1/cases/{case_id}/observations` sécurisés par `verify_case_access`.

## Boundaries & Constraints

**Always:**
- Plafonner la charge utile destinée aux agents LLM (NFR-PERF-06) : maximum 50 observations représentatives, résumé textuel borné à 8 Ko (8 192 octets) et 200 lignes max.
- Si le résultat dépasse ces seuils, inclure la mention normalisée : `[TRUNCATED: {X} éléments masqués. Consulter Observation pour la totalité]`, où `{X}` est le nombre d'éléments omis.
- Conserver systématiquement l'intégralité des données brutes en base PostgreSQL dans `ToolExecution` (avec empreinte SHA-256 `result_sha256`) et dans `Observation`.
- Pagination sur toutes les collections (NFR-PERF-07) : paramètres de requête `limit` (défaut 50, min 1, max 100) et `offset` (défaut 0, min 0), avec structure paginée (`items`, `total`, `total_items`, `limit`, `offset`, `has_more`).
- Contrôle d'accès strict via `verify_case_access` sur tous les endpoints de consultation (HTTP 404 si dossier inconnu, HTTP 403 si utilisateur non membre).
- Validation des filtres temporels `start_date` et `end_date` (format ISO-8601 UTC) avec renvoi HTTP 422 standard en cas de format invalide.
- Enregistrer le nouveau routeur dans `backend/src/iryx/main.py`.

**Never:**
- Ne jamais altérer ni tronquer les données persistées en base : la troncature ne s'applique qu'au payload destiné au modèle LLM (`AgentPayload`).
- Ne jamais accepter un paramètre `limit` supérieur à 100 ou inférieur à 1 sans renvoyer une erreur 422.
- Ne jamais contourner le contrôle d'accès `verify_case_access`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Troncature nominale | 1 000 observations produites par un outil | `AgentPayload` avec 50 observations, résumé textuel <= 8 Ko / 200 lignes, bandeau `[TRUNCATED: 950 éléments masqués...]`, `is_truncated=True`, `truncated_count=950` | N/A |
| Sortie courte | 15 observations produites | `AgentPayload` complet (15 obs), pas de bandeau `[TRUNCATED]`, `is_truncated=False`, `truncated_count=0` | N/A |
| Dépassement strict en octets | 30 observations très volumineuses (> 10 Ko) | Résumé textuel tronqué à 8 192 octets max avec avertissement `[TRUNCATED]` | N/A |
| Liste tool-executions paginée | `GET /api/v1/cases/{case_id}/tool-executions?limit=20&offset=0` | HTTP 200, `ToolExecutionListResponse` avec pagination et métadonnées | N/A |
| Filtres tool-executions | `tool_name="parse_evtx"`, `status="success"`, `start_date`, `end_date` | HTTP 200, liste filtrée correspondante | N/A |
| Liste observations paginée | `GET /api/v1/cases/{case_id}/observations?limit=50&offset=0` | HTTP 200, `ObservationListResponse` paginée | N/A |
| Filtres observations | `tool_name="parse_text_logs"`, `source_id=<uuid>` | HTTP 200, observations filtrées | N/A |
| Paramètres pagination invalides | `limit=150` ou `limit=0` ou `offset=-1` | HTTP 422 Unprocessable Entity standardisé | ValidationException / RequestValidationError |
| Date invalide | `start_date="not-a-date"` | HTTP 422 Unprocessable Entity standardisé | RequestValidationError |
| Accès non autorisé au dossier | Utilisateur non membre de l'organisation du dossier | HTTP 403 Forbidden | `InsufficientPermissionsException` |
| Dossier inexistant | `case_id` inconnu | HTTP 404 Not Found | `CaseNotFoundException` |

</frozen-after-approval>

## Code Map

- `backend/src/iryx/gateway/truncation.py` -- Module de troncature : `truncate_for_agent(...)`, `AgentPayload`, constantes `MAX_AGENT_OBSERVATIONS = 50`, `MAX_SUMMARY_BYTES = 8192`, `MAX_SUMMARY_LINES = 200`.
- `backend/src/iryx/gateway/schemas.py` -- Schémas Pydantic v2 `AgentPayload`, `ToolExecutionListResponse`, `ObservationListResponse`.
- `backend/src/iryx/gateway/base.py` & `backend/src/iryx/gateway/runner.py` -- Intégration de la génération du payload agent dans `ToolExecutionResult` et `ToolRunner`.
- `backend/src/iryx/gateway/router.py` -- Routeur FastAPI `router` avec endpoints `tool-executions` et `observations` (listes paginées et consultation par identifiant).
- `backend/src/iryx/gateway/__init__.py` & `backend/src/iryx/main.py` -- Exports publics et enregistrement du routeur.
- `backend/src/iryx/cases/dependencies.py` -- Dépendance `verify_case_access`.
- `backend/tests/unit/test_gateway_truncation.py` -- Tests unitaires de troncature contextuelle.
- `backend/tests/api/test_gateway_routes.py` -- Tests d'intégration API des endpoints de consultation et de sécurité.

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/gateway/truncation.py` -- Implémenter la logique de troncature contextuelle et de résumé pour agents (50 obs, 8 Ko, 200 lignes, bandeau `[TRUNCATED]`).
- [x] `backend/src/iryx/gateway/schemas.py` -- Ajouter `AgentPayload`, `ToolExecutionListResponse`, `ObservationListResponse`.
- [x] `backend/src/iryx/gateway/base.py` & `backend/src/iryx/gateway/runner.py` -- Intégrer `to_agent_payload()` et `agent_payload` dans `ToolExecutionResult`.
- [x] `backend/src/iryx/gateway/router.py` -- Créer les endpoints REST de consultation pour `tool-executions` et `observations` avec filtres et pagination.
- [x] `backend/src/iryx/gateway/__init__.py` & `backend/src/iryx/main.py` -- Exporter les composants et brancher le routeur dans l'app FastAPI.
- [x] `backend/tests/unit/test_gateway_truncation.py` -- Tests unitaires de troncature et génération de résumé.
- [x] `backend/tests/api/test_gateway_routes.py` -- Tests des endpoints REST (pagination, filtres, erreurs 422, contrôle d'accès 403/404).

**Acceptance Criteria:**
- Given une sortie d'outil produisant plus de 50 observations ou plus de 8 Ko / 200 lignes, when la projection pour l'agent est générée, then elle contient au maximum 50 observations et un résumé borné à 8 Ko / 200 lignes arborant l'avertissement `[TRUNCATED: {X} éléments masqués. Consulter Observation pour la totalité]`, tandis que la totalité des données reste persistée en base.
- Given une sortie d'outil de 50 éléments ou moins respectant les limites, when la projection est générée, then l'intégralité est conservée avec `is_truncated=False` et sans avertissement.
- Given un utilisateur autorisé sur un dossier, when il appelle `GET /api/v1/cases/{case_id}/tool-executions` ou `GET /api/v1/cases/{case_id}/observations`, then les résultats sont retournés paginés (`limit`, `offset`, `has_more`, `total`, `total_items`) avec application des filtres.
- Given un utilisateur non membre ou un dossier inexistant, when l'accès est tenté, then la requête est rejetée avec HTTP 403 ou 404.
- Given des filtres ou paramètres invalides (`limit=150`, date invalide), when la requête est reçue, then FastAPI répond avec HTTP 422 standard.

## Implementation Notes

- Implémentation complète du module `backend/src/iryx/gateway/truncation.py` avec la fonction `truncate_for_agent(...)`, les constantes `MAX_AGENT_OBSERVATIONS = 50`, `MAX_SUMMARY_BYTES = 8192`, `MAX_SUMMARY_LINES = 200` et la génération du bandeau `[TRUNCATED: {X} éléments masqués. Consulter Observation pour la totalité]`.
- Ajout des schémas Pydantic v2 `AgentPayload`, `ToolExecutionListResponse`, `ObservationListResponse` dans `backend/src/iryx/gateway/schemas.py`.
- Intégration de `to_agent_payload()` et du champ `agent_payload` dans `ToolExecutionResult` (`base.py`) et automatisation dans `ToolRunner.execute_tool` (`runner.py`).
- Préservation intégrale et non altérée des preuves et observations brutes en base PostgreSQL / SQLAlchemy (`ToolExecution` et `Observation`).
- Implémentation du routeur `backend/src/iryx/gateway/router.py` avec les endpoints de consultation `GET /api/v1/cases/{case_id}/tool-executions`, `GET /api/v1/cases/{case_id}/tool-executions/{execution_id}`, `GET /api/v1/cases/{case_id}/observations`, `GET /api/v1/cases/{case_id}/observations/{observation_id}`, et `GET /api/v1/gateway/tools`.
- Sécurisation stricte de tous les endpoints par la dépendance `verify_case_access` (rejet 403 pour utilisateur non membre, 404 pour dossier inconnu).
- Validation de pagination `limit` (1 à 100, défaut 50) et `offset` (>= 0, défaut 0) avec rejet 422 standard.
- Gestion paresseuse (`__getattr__`) dans `backend/src/iryx/gateway/__init__.py` pour prévenir les dépendances circulaires avec `Case`.
- Enregistrement du routeur `gateway_router` dans `backend/src/iryx/main.py`.
- Validation : 18/18 tests dédiés passants (7 unitaires, 11 API) et 521/521 tests globaux du projet passants. Linting ruff (0 erreur) et formatage ruff (0 modification).

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Evidence |
|---|---|---|
| Absence de décorateur `@model_validator(mode="before")` sur `populate_total_items` dans `ToolExecutionListResponse` et `ObservationListResponse` | medium | Sans décorateur validator, Pydantic v2 n'exécute jamais la méthode et `total_items` vaut 0 par défaut lorsque non renseigné dans le dictionnaire d'entrée. Corrigé par patch. |
| Incohérence du calcul de `truncated_count` et du message du bandeau lorsque seules la taille ou les lignes débordent | low | Si `total_obs <= 50`, aucune observation n'est masquée dans la liste; le bandeau doit refléter la troncature du texte/résumé et `truncated_count` doit valoir `max(total_obs - max_observations, 0)`. Corrigé par patch. |
| Absence de normalisation UTC sur les paramètres de date `start_date` et `end_date` | medium | Les dates offset-naive fournies en requête peuvent échouer en comparaison contre des colonnes PostgreSQL timezone-aware. Normalisation explicite requise. Corrigé par patch. |
| Absence de validation `start_date <= end_date` | low | Si `start_date > end_date`, la requête renvoyait silencieusement une liste vide au lieu d'une erreur 422 de validation. Corrigé par patch. |
| Tri chronologique dans `list_observations` | false | Le tri standard du projet sur les listes paginées se fait par date d'insertion `created_at desc, id desc`, identique aux autres entités du socle. Réfuté. |
| Expression `COALESCE` non indexée | false | Les colonnes `created_at` et `timestamp_utc` sont déjà indexées individuellement; pour le MVP, l'expression ne nécessite pas d'index fonctionnel supplémentaire. Réfuté. |
| Duplication des métadonnées dans le formatage texte de repli des observations | low | Exclusion de `timestamp_utc`, `tool_name` et `source_location` de la charge utile de repli pour éviter la répétition dans la ligne formatée. Corrigé par patch. |
| Génération d'agent payload avant persistance | false | Le runner produit la projection à partir des observations générées par l'outil, ce qui est le comportement nominal pour alimenter le résultat `ToolExecutionResult`. Réfuté. |
| Typage Pydantic du paramètre `status` dans le router | low | Remplacer la chaîne brute et la validation manuelle par `ToolExecutionStatus | None = Query(None, alias="status")` pour bénéficier de la validation et documentation OpenAPI automatique. Corrigé par patch. |
| Dépendance du registre d'outils en dur dans `list_registered_tools` | low | Injection via `Depends(get_tool_registry)` pour faciliter le test unitaire et le remplacement en dépendance. Corrigé par patch. |
| Tronquage textuel en plein milieu d'une ligne ou d'un JSON | low | Tronquer sur la dernière frontière de ligne `\n` avant le seuil d'octets. Corrigé par patch. |
| Couverture de tests manquante pour les filtres temporels, l'ID d'exécution et le rejet 422 sur statut invalide | medium | Gap pré-vérifié par le reviewer de vérification : aucun test n'exécutait de filtre par plage de dates ou par `tool_execution_id`, ni la vérification de rejet 404 cross-case pour observations. Corrigé par patch. |

## Design Notes

La troncature contextuelle protège la fenêtre de contexte des agents (FR10, NFR-PERF-06).
Elle échantillonne les 50 premières observations, compose une synthèse textuelle compacte bornée strictement à 8 192 octets et 200 lignes, et insère l'avertissement explicite `[TRUNCATED: X éléments masqués. Consulter Observation pour la totalité]`.
Les endpoints REST `tool-executions` et `observations` permettent aux analystes et interfaces de naviguer dans l'intégralité des preuves brutes et observations grâce à une pagination systématique `limit`/`offset` (NFR-PERF-07).

## Verification

**Commands:**
- `uv run pytest backend/tests/unit/test_gateway_truncation.py` -- expected: tous les tests de troncature passent
- `uv run pytest backend/tests/api/test_gateway_routes.py` -- expected: tous les tests d'endpoints passent
- `uv run pytest` -- expected: 100% des tests du projet passent
- `uv run ruff check backend` -- expected: 0 erreur
- `uv run ruff format --check backend` -- expected: 0 modification
