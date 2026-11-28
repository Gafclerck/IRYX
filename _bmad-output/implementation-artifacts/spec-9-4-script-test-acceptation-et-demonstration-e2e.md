---
title: 'Story 9.4 : Script de test d''acceptation et démonstration de bout en bout (Smoke Test E2E)'
type: 'feature'
created: '2026-11-28'
status: 'done'
baseline_commit: 'cbd19a638e809ba997b6960e5b96bb2656eae012'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-9-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Même avec la pile Docker Compose (Stories 9.1–9.2) et le jeu de données de démonstration (Story 9.3), aucune validation automatisée de bout en bout ne prouve encore que tous les modules E1 à E8 et les exigences FR1 à FR27 s'enchaînent sans rupture via l'API REST.

**Approach:** Fournir un module CLI `python -m iryx.scripts.test_e2e_investigation_flow` s'appuyant sur une abstraction légère de transport HTTP (stdlib `urllib` en production sans dépendance `dev`, `TestClient` en tests) qui exécute de façon ordonnée et fail-fast les 12 étapes du cycle d'enquête (JWT, RBAC, upload/polling SHA-256, LangGraph + portes H1/H2/H3 via `/resume`, Gateway, Verifier, timeline UTC, Presidio, rapports Markdown/JSON scellés, audit et Invariant 3), puis affiche `DÉMONSTRATION ET VALIDATION COMPLÈTE DU MVP IRYX RÉUSSIE` avec code de sortie `0`.

## Boundaries & Constraints

**Always:**
- Emplacement : `backend/src/iryx/scripts/test_e2e_investigation_flow.py` (cohérent avec `seed_data.py`), plus tests automatisés dans `backend/tests/unit/test_e2e_investigation_flow.py`.
- Transport HTTP sans dépendance `dev` requise à l'exécution (`urllib.request` / protocole `HttpTransport` injectable pour `TestClient`).
- Chaque requête HTTP protégée porte un `Authorization: Bearer <jwt>` valide ; contrôle explicite des rejets `401`/`403` attendus (dont `viewer` et `analyst` sur `/audit-trail`).
- Polling ingestion conforme au contrat `202` + `Retry-After` jusqu'à `completed` et vérification de concordance SHA-256.
- Aucune porte humaine (`H1`, `H2`, `H3`) n'est contournée ; l'arbitrage passe par les endpoints `/gates/h1`, `/findings/{id}/review`, `/gates/h2`, `/anonymized-preview`, `/gates/h3` et `/resume`.
- Double vérification d'Invariant 3 : refus HTTP (`405`) sur `/audit-trail` + tentative SQL directe (`UPDATE`/`DELETE` sur `audit_events` rejetée par `CANNOT_MODIFY_AUDIT_LOG`, désactivable uniquement via `--skip-db-audit-check` si Postgres n'est pas joignable depuis l'hôte).
- Mode `--mode stack` (défaut, zéro mock dans le backend) + mode `--mode local-demo` (application FastAPI locale isolée avec stubs Celery/LLM injectés uniquement dans le script pour démonstration hors ligne ou CI).
- Arrêt immédiat (exit `!= 0`) identifiant l'étape et l'écart sur toute anomalie ; succès final affichant `DÉMONSTRATION ET VALIDATION COMPLÈTE DU MVP IRYX RÉUSSIE` et exit `0`.

**Decisions:**
- Q1 (Emplacement) : `backend/src/iryx/scripts/test_e2e_investigation_flow.py` + tests sous `backend/tests/unit/test_e2e_investigation_flow.py`.
- Q2 (LLM) : Zéro mock dans `backend/src/iryx/ai/` ; mode `--mode stack` réel par défaut (diagnostique explicitement `503` si aucun LLM compatible OpenAI n'est configuré) + `--mode local-demo` autonome pour exécution hors ligne/CI.
- Q3 (Invariant 3) : Double vérification HTTP (`405`) + SQL directe sur `audit_events` (`CANNOT_MODIFY_AUDIT_LOG`), avec `--skip-db-audit-check` optionnel hors conteneur.

**Never:** Ne pas modifier `backend/src/iryx/ai/`, `orchestrator/`, `reporting/`, `audit/` ou tout autre module métier pour ajouter des contournements/mocks de test ; ne pas casser `uv run pytest` sans Docker actif ; ne pas logger de mots de passe ou jetons JWT.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Parcours E2E nominal (`stack` / `local-demo`) | Pile prête + seed 9.3 + LLM joignable (ou `local-demo`) | 12 étapes validées, MD+JSON SHA-256 vérifiés, audit complet, exit `0` | N/A |
| Échec auth / RBAC | Mauvais identifiants, requête anonyme, ou `viewer`/`analyst` sur route interdite | Rejet `401`/`403` vérifié | Arrêt immédiat si accès indu accordé |
| Polling ingestion incomplet ou hash faux | Timeout polling ou `sha256` != empreinte locale | Écart détecté à l'étape 3 avant enquête | Arrêt immédiat avec nom d'étape et détail |
| LLM indisponible (`503`) en mode `stack` | `OPENAI_API_KEY` factice ou fournisseur injoignable | Échec remonté à l'étape 4/6/11 | Arrêt immédiat avec conseil de config LLM / `--mode local-demo` |
| Porte H1/H2/H3 ou finding non arbitré | Phase/statut inattendu ou finding resté `proposed` | Divergence phase/statut détectée | Arrêt immédiat avec phase attendue vs reçue |
| Mutation audit acceptée (Invariant 3) | Tentative `DELETE`/`PATCH` HTTP ou `UPDATE`/`DELETE` SQL sur `audit_events` | Rejet HTTP `405` et trigger SQL `CANNOT_MODIFY_AUDIT_LOG` | Arrêt immédiat si mutation réussit |

</frozen-after-approval>

## Code Map

- `backend/src/iryx/main.py:56-108` -- `create_app()`, montage des 9 routeurs (`/api/v1/...`) et `GET /health`.
- `backend/docker-compose.yml:30-118` -- services `postgres`, `redis`, `iryx-api` (`8000:8000`), `iryx-worker`, `iryx-analysis` ; ports Postgres/Redis internes.
- `backend/src/iryx/scripts/seed_data.py:38-75,349-413` -- constantes `CASE_TITLE`, `DEMO_USERS` (`admin`, `analyst`, `investigator`, `auditor`), `seed_demo_data()`.
- `backend/src/iryx/scripts/demo_evidence.py:23-26,313-530` -- `generate_security_evtx()` et `generate_powershell_prefetch()`.
- `backend/src/iryx/auth/router.py:21-83` -- `POST /api/v1/auth/login`, `GET /api/v1/auth/me`.
- `backend/src/iryx/cases/router.py:108-167` -- `GET /api/v1/cases`, `GET /api/v1/cases/{case_id}` (émet `CASE_READ`).
- `backend/src/iryx/evidence/router.py:26-143` -- `POST /api/v1/cases/{case_id}/evidences` (`202` + `Location` + `Retry-After`), `GET .../ingestion-status`, `GET .../evidences`.
- `backend/src/iryx/orchestrator/router.py:32-298` -- `POST .../investigations` (`201`, `running`/`triage`), `POST .../resume`, `GET .../plan`, `POST .../gates/h1`, `POST .../gates/h2`, `GET .../anonymized-preview`, `POST .../gates/h3`.
- `backend/src/iryx/gateway/router.py:44-283` -- `GET .../tool-executions`, `GET .../observations`.
- `backend/src/iryx/analytics/router.py:71-303` -- `GET .../findings`, `POST .../findings/{id}/review`, `GET .../timeline`, `GET .../timeline/correlations`.
- `backend/src/iryx/reporting/router.py:38-139` -- `GET .../reports`, `GET .../reports/{id}/download` (`Content-Type`, `X-Report-SHA256`).
- `backend/src/iryx/audit/router.py:19-62` -- `GET .../audit-trail` (`ADMIN`/`INVESTIGATOR` uniquement).
- `backend/src/iryx/audit/triggers.py:6-60` -- `AUDIT_LOG_ERROR_MESSAGE = "CANNOT_MODIFY_AUDIT_LOG"`.
- `backend/src/iryx/ai/client.py:49-307` -- `UnifiedLLMClient` (aucun stub intégré).
- `backend/pyproject.toml:38-59` -- `httpx` en dépendance `dev` uniquement ; `testpaths = ["tests"]`.

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/scripts/test_e2e_investigation_flow.py` -- implémenter le runner E2E séquentiel 12 étapes (`HttpTransport` stdlib `urllib` + CLI `--mode stack|local-demo`, `--base-url`, `--db-url`, `--skip-db-audit-check`, `--timeout`, `--poll-interval`), vérifications RBAC/SHA-256/UTC/audit/Invariant 3 et rapport d'erreur explicite par étape -- cœur Story 9.4.
- [x] `backend/tests/unit/test_e2e_investigation_flow.py` -- couvrir le parcours complet 12 étapes en mode `local-demo`/transport `TestClient` ainsi que les cas d'échec de la matrice (auth/RBAC, mismatch SHA-256, timeout polling, phase porte invalide, finding non arbitré, mutation audit acceptée, CLI exit code) -- validation CI sans dépendance Docker.
- [x] `README.md` -- documenter la commande d'exécution du smoke test E2E (mode Docker Compose `stack` et mode `local-demo`) -- opérabilité.

**Acceptance Criteria:**
- Given la pile active et les données de démonstration initialisées, when `uv run python -m iryx.scripts.test_e2e_investigation_flow` (ou `docker compose exec iryx-api python -m iryx.scripts.test_e2e_investigation_flow`) s'exécute, then il valide les 12 étapes avec un JWT valide sur chaque requête protégée, vérifie les empreintes SHA-256 et le journal d'audit, affiche `DÉMONSTRATION ET VALIDATION COMPLÈTE DU MVP IRYX RÉUSSIE` et termine avec le code `0`.
- Given toute déviation sur une étape (auth, hash, timeout, porte, rapport, audit, Invariant 3), when le runner la détecte, then il s'arrête immédiatement avec un code de sortie non nul et identifie l'étape ainsi que la condition non satisfaite.

## Implementation Notes

- 2026-11-28 — Correctif E4→E6 dans [runner.py](../../backend/src/iryx/gateway/runner.py#L260-L295) : `ToolRunner.execute_tool` persistait les `Observation` en base sans réinjecter `id`, `tool_name`, `tool_execution_id` et `source_id` dans `result.observations`, ce qui empêchait `AnalystAgent` de référencer des UUID valides depuis la sortie d'`ExecutorAgent`.
- 2026-11-28 — `test_e2e_investigation_flow.py` isole le transport HTTP via `HttpTransport` (`UrllibHttpTransport` en stdlib pure pour `--mode stack`, `TestClientHttpTransport` pour `--mode local-demo` et les tests). En `--mode local-demo`, le schéma SQLite est migré via `alembic upgrade head` (jamais `create_all`), peuplé via `seed_demo_data()`, et les stubs Celery/LLM sont injectés uniquement dans le contexte du script sans altérer `iryx/ai/`.

## Spec Change Log

## Review Triage Log

- 2026-11-28 — Revue step-04 (`edge-case-hunter` `57e96826-1650-409d-ad6a-c40a2e308f2e`, `blind-hunter` `ded2df3b-f55f-4478-ae88-27fe6023e2a3`, `verification-gap` `8befb1c7-7890-4098-bb1d-2106608702a0`). Aucun `intent_gap`/`bad_spec`, aucun `defer`. Correctifs `patch` renvoyés au sous-agent d'implémentation `983936bd-359b-4886-ac3c-c67a340371ef`.
- 2026-11-28 — [EC-1] `medium` (`patch`) : `GET /reports?limit=100` non paginé (`test_e2e_investigation_flow.py:1628-1654`) ; le tri ascendant tronque la dernière version au-delà de 50 versions (>100 lignes). Corrigé via pagination complète.
- 2026-11-28 — [EC-2] `medium` (`patch`) : `GET /evidences?limit=100` non paginé (`test_e2e_investigation_flow.py:868-890`) ; le tri descendant pousse les preuves seedées hors page 1 après >97 uploads. Corrigé via pagination complète.
- 2026-11-28 — [EC-3] `medium` (`patch`) : `GET /findings?status=proposed&limit=100` non paginé (`test_e2e_investigation_flow.py:1320-1380`) ; >100 constats bloqueraient H2. Corrigé par boucle de pagination jusqu'à épuisement.
- 2026-11-28 — [EC-4] `medium` (`patch`) : `GET /timeline?limit=100` non paginé (`test_e2e_investigation_flow.py:1442-1485`) ; les événements au-delà de 100 échappaient au contrôle UTC monotone. Corrigé via pagination complète.
- 2026-11-28 — [EC-5] `low` (`patch`) : `--timeout nan` / `--poll-interval nan` contournent `<= 0` (`test_e2e_investigation_flow.py:2177`). Garde `math.isfinite` ajouté.
- 2026-11-28 — [EC-6] `high` (`patch`) : exception SQL brute dans `verify_sql_audit_append_only` (`test_e2e_investigation_flow.py:600-611`) pouvant exposer un mot de passe `--db-url` sur `stderr`. Filtrage via `sanitize_error_message`.
- 2026-11-28 — [EC-7] `medium` (`patch`) : `engine.dispose()` absent en cas d'exception entre `create_engine` et `yield` dans `local_demo_environment` (`test_e2e_investigation_flow.py:2019-2095`). Encadré par `try/finally`.
- 2026-11-28 — [EC-8] `medium` (`patch`) : `gateway/runner.py:283-298` référence `obs_data` comme `normalized_content` si absent et lit `obs.id`/`obs.source_id` après `commit()` (N+1 si `expire_on_commit=True`). Copie du dict + capture avant `commit()` après `flush()`.
- 2026-11-28 — [EC-9] `low` (`patch`) : `_parse_json` accepte un JSON non-objet (`null`/liste/scalaire), provoquant `AttributeError` au lieu de `E2EStepError`. Vérification de type ajoutée.
- 2026-11-28 — [BH-1] `medium` (`patch`) : `result.agent_payload` calculé avant le backfill `obs_data` (`gateway/runner.py:246,293-298`), rendant `agent_payload.summary` obsolète. Déplacé/recalculé après persistence DB + tests ajoutés dans `test_tool_gateway_runner.py`.
- 2026-11-28 — [BH-2] `medium` (`patch`) : `SENSITIVE_DEMO_MARKERS` omettait `"adm_backup"` et Step 10 n'exigeait pas `entity_count >= 1` / `has_entities is True` en mode `local-demo`. Marqueur ajouté et assertions renforcées en `local-demo`.
- 2026-11-28 — [BH-3] `medium` (`patch`) : Step 11 ne vérifiait pas `CANONICAL_SECTION_KEYS`, `case_id`/`run_id` JSON, Markdown non vide, ni l'absence de `SENSITIVE_DEMO_MARKERS` dans les rapports externes. Assertions ajoutées.
- 2026-11-28 — [BH-4] `medium` (`patch`, regroupé avec EC-1..EC-4) : pagination manquante sur `/evidences`, `/tool-executions`, `/observations`, `/findings`, `/timeline`, `/reports`. Corrigé via helper partagé.
- 2026-11-28 — [BH-5] `medium` (`patch`) : Step 6 ne vérifiait pas que les exécutions/observations appartiennent au run courant / à `uploaded_id`. Vérification `created_at >= run_started_at` (et `source_id == uploaded_id` en `local-demo`) ajoutée.
- 2026-11-28 — [BH-6] `low` (`patch`) : Step 3 validait seulement `Retry-After is not None` et testait `deadline` après requête plutôt qu'avant nouvelle attente. Validation numérique `>= 1` et garde `deadline` avant sleep ajoutés.
- 2026-11-28 — [BH-7] `low` (`patch`) : Step 9 vérifiait uniquement `isinstance(groups, list)` sur `/timeline/correlations`. Validation des champs de corrélation (et `>= 1` groupe en `local-demo`) ajoutée.
- 2026-11-28 — [BH-8] `medium` (`patch`) : `verify_sql_audit_append_only` committait `"TAMPERED"` si `UPDATE` réussissait faute de trigger (`tx.rollback()` requis) ; contrôle `len(events) == total` et scan des valeurs secrètes dans `AuditEvent.details` ajoutés.
- 2026-11-28 — [BH-9] `low` (`patch`) : tests manquants dans `test_e2e_investigation_flow.py` (phases H1/H2/H3 inattendues, timeline non monotone, fuite PII Step 10, `PATCH`/action manquante/secret Step 12, `UrllibHttpTransport` erreurs, parité `DEMO_USERS`, param `tmp_path` inutilisé). Couverts par patch.
- 2026-11-28 — [BH-10] `false` : `local_demo_environment()` est un harnais CLI isolé qui sauvegarde et restaure `os.environ` dans `finally:` et réinitialise `get_settings`/`MemorySaver` ; `TestClientHttpTransport` exécute l'app ASGI en mémoire sans socket réseau, donc `timeout` est sans objet sans défaut fonctionnel.
- 2026-11-28 — [BH-11] `low` (`patch` pour `README.md`, `false` pour `sprint-status.yaml`) : `sprint-status.yaml` reste `in-progress` jusqu'à `step-05-present` selon le workflow ; `README.md` Section 8.10 complété avec l'avertissement sur `HTTP 409` en cas de relance `--mode stack` sur une session encore `running`.
- 2026-11-28 — [VG-1] `medium` (`patch`, pré-vérifié) : backfill `obs_data["id"]`, `obs_data["tool_name"]`, `obs_data["tool_execution_id"]`, `obs_data["source_id"]` non testé dans `test_tool_gateway_runner.py`. Tests unitaires ajoutés (y compris surcharge d'un `tool_name` interne).
- 2026-11-28 — [VG-2] `medium` (`patch`, pré-vérifié) : `verify_sql_audit_append_only(..., engine=None, db_url=...)` et cas `UPDATE` bloqué / `DELETE` autorisé non testés. Tests dédiés ajoutés dans `test_e2e_investigation_flow.py`.
- 2026-11-28 — [VG-3] `medium` (`patch`, regroupé avec BH-1) : `result.agent_payload` calculé avant backfill `obs_data` dans `gateway/runner.py:246`. Corrigé en recalculant après persistance DB.

## Verification

**Commands:**
- `cd backend && uv run pytest -q tests/unit/test_e2e_investigation_flow.py` -- expected: tous les tests verts.
- `cd backend && uv run python -m iryx.scripts.test_e2e_investigation_flow --mode local-demo` -- expected: exit `0` et affichage `DÉMONSTRATION ET VALIDATION COMPLÈTE DU MVP IRYX RÉUSSIE`.
- `cd backend && uv run ruff check src/iryx/scripts/test_e2e_investigation_flow.py tests/unit/test_e2e_investigation_flow.py` -- expected: `All checks passed!`.
- `cd backend && uv run ruff format --check src/iryx/scripts/test_e2e_investigation_flow.py tests/unit/test_e2e_investigation_flow.py` -- expected: `2 files already formatted`.

**Results (2026-11-28, après correctifs de revue step-04) :**
- `cd backend && uv run ruff check src/iryx/gateway/runner.py src/iryx/scripts/test_e2e_investigation_flow.py tests/unit/test_e2e_investigation_flow.py tests/unit/test_tool_gateway_runner.py` → `All checks passed!`.
- `cd backend && uv run ruff format --check src/iryx/gateway/runner.py src/iryx/scripts/test_e2e_investigation_flow.py tests/unit/test_e2e_investigation_flow.py tests/unit/test_tool_gateway_runner.py` → `4 files already formatted`.
- `cd backend && uv run python -m iryx.scripts.test_e2e_investigation_flow --mode local-demo` → exit `0`, 12/12 étapes validées, `DÉMONSTRATION ET VALIDATION COMPLÈTE DU MVP IRYX RÉUSSIE`.
- `cd backend && uv run pytest -q` → `1156 passed in 96.24s`.
