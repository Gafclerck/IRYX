---
title: 'Story 8.5 : Service d''audit immuable en ajout seul AuditEvent et déclencheur d''intégrité'
type: 'feature'
created: '2026-11-26'
status: 'done'
baseline_commit: '003c2dadea00f88d93ef6e38350ddb57440b450e'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-8-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `audit_events` n'existe qu'à l'état de modèle posé par la Story 8.3 : aucun service n'y écrit, aucun endpoint ne l'expose, et rien au niveau SQL n'empêche un `UPDATE` ou un `DELETE`. Les actions sensibles ne sont donc ni traçables ni opposables.

**Approach:** Finaliser `audit_events` (migration + trigger append-only), ajouter un service d'audit synchrone appelé par les actions sensibles, et exposer `GET /api/v1/cases/{case_id}/audit-trail` paginé, réservé aux rôles `admin` et `investigator`.

## Boundaries & Constraints

**Always:** Écrire l'événement dans la transaction de l'action auditée : si l'audit échoue, l'action échoue (fail-closed). `payload_hash` = SHA-256 hexadécimal minuscule d'un JSON canonique (`sort_keys`, séparateurs compacts) décrivant `action`, `target_type`, `target_id`, `details`. `details` est un JSONB sérialisable expurgé récursivement des clés `password`, `token`, `secret`, `api_key`, `authorization`, `jwt`, `credential` (insensible à la casse) ; une action sans utilisateur porte `actor_id` NULL et `details.actor = "system"`. Le trigger SQL est l'autorité d'immutabilité ; aucune couche applicative ne modifie ni supprime un événement. L'endpoint valide les UUID, cloisonne par dossier et ordonne `created_at ASC, id ASC`.

**Never:** Aucune écriture d'audit sur le téléchargement ou la liste des rapports (contrat figé 8.4). Pas d'audit des exécutions d'outils (déjà tracées par `ToolExecution`). Aucune purge, rotation ou désactivation du trigger. Aucun secret dans `details` ni dans les logs. Aucune nouvelle dépendance.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Connexion réussie | Identifiants valides | 1 ligne `AUTH_LOGIN`, `case_id` NULL, cible `User` | N/A |
| Dossier créé / lu / modifié | `POST /organizations/{org_id}/cases`, `GET /cases/{id}`, `PATCH .../status` | 1 ligne `CASE_CREATE`, `CASE_READ` ou `CASE_STATUS_UPDATE`, même transaction | Rollback si audit échoue |
| Upload de preuve | Upload accepté | 1 ligne `EVIDENCE_UPLOAD`, cible `Evidence` | Rollback preuve + audit |
| Décision de porte | H1, H2, H3, revue de finding | 1 ligne `GATE_H*_DECISION` ou `FINDING_REVIEW`, cible `InvestigationRun`/`Finding` | Rollback si audit échoue |
| Génération de rapport | `generate_report` (avec ou sans utilisateur) | 1 ligne `REPORT_GENERATE`, cible `Report` ; `actor_id` NULL et `details.actor="system"` en interne | Rollback si audit échoue |
| Consultation piste | `admin`/`investigator` | 200, `{items,total,total_items,limit,offset,has_more}` | N/A |
| Rôle non autorisé | `analyst`, `viewer`, non-membre | 403 `INSUFFICIENT_PERMISSIONS` | Avant lecture |
| Dossier inconnu / UUID invalide / bornes | `case_id` absent ou mal formé, `limit=0/101`, `offset=-1` | 404 `CASE_NOT_FOUND`, 422 `VALIDATION_ERROR` | Exception typée ou `Query(ge/le)` |
| Modification SQL | `UPDATE`/`DELETE` sur `audit_events` | Exception `CANNOT_MODIFY_AUDIT_LOG`, ligne intacte | Trigger base |
| Détails sensibles | `details` avec `password`/`token` | Clés supprimées, hash stable | Expurgation |

## Decisions

- `case_id` est nullable (la connexion n'a pas de dossier, conformément à l'architecture) ; `actor_id` est nullable et vaut NULL pour une action système/agent, avec `details.actor = "system"` ; `target_type` et `target_id` sont obligatoires et renseignés pour chaque action.
- L'« export de rapport » de l'AC 8.5 est couvert par `REPORT_GENERATE` dans `generate_report` ; le téléchargement et la liste des rapports restent sans écriture d'audit (contrat figé 8.4).
- L'audit d'accès aux dossiers se limite aux endpoints du dossier : `CASE_CREATE`, `CASE_READ` et `CASE_STATUS_UPDATE`. `verify_case_access` n'écrit rien, afin de ne pas auditer chaque sous-ressource ni les téléchargements.
- La migration 010 recrée `audit_events` : aucun code de production n'y écrivait avant cette story (seuls des tests l'instancient) ; le downgrade restaure la forme 009.
- Le trigger est installé par la migration **et** par un listener DDL `after_create`, en PostgreSQL (`RAISE EXCEPTION`) et SQLite (`RAISE(ABORT)`), pour que `create_all` le fournisse à la suite de tests.

</frozen-after-approval>

## Code Map

- `backend/src/iryx/audit/models.py:22-66` -- `AuditEvent` : renommer `event_type`→`action`, `payload`→`details`, `payload_sha256`→`payload_hash` ; ajouter `target_type`, `target_id` ; `case_id`/`actor_id` nullables ; garder checks et index `(case_id, created_at)`.
- `backend/src/iryx/audit/triggers.py` -- nouveau : DDL PostgreSQL/SQLite idempotent, helper d'installation, listener `after_create` importé par le modèle.
- `backend/src/iryx/audit/services.py`, `schemas.py`, `router.py`, `backend/src/iryx/main.py:11-21,87-94` -- `AuditService.record()` (add + flush), `canonical_payload_hash`, `sanitize_details`, `list_events`/`count_events`, `AuditEventOut`, enveloppe paginée (modèle `reporting/schemas.py:222-243`), endpoint `GET /api/v1/cases/{case_id}/audit-trail` avec `require_case_role(ADMIN, INVESTIGATOR)`, `limit=Query(100, ge=1, le=100)`, `offset=Query(0, ge=0)`, puis enregistrement du router.
- `backend/migrations/versions/010_finalize_audit_events.py` -- drop/recreate + trigger ; downgrade vers 009.
- `backend/src/iryx/auth/router.py:30-60` -- `AUTH_LOGIN` après `authenticate_user`.
- `backend/src/iryx/cases/router.py:36-60,138-142,155-175` -- `CASE_CREATE`, `CASE_READ`, `CASE_STATUS_UPDATE` ; ajouter `db`/`current_user` à `get_case`.
- `backend/src/iryx/evidence/services.py:33-38,128-137` -- `EVIDENCE_UPLOAD` entre `db.add(...)` et `db.commit()`.
- `backend/src/iryx/orchestrator/services.py:333,625,834` -- audit des portes avant les commits `:532`, `:743`, `:961` ; `analytics/services.py:138-173` -- `FINDING_REVIEW` avant `:173`.
- `backend/src/iryx/reporting/services.py:318-334,424-462` -- `REPORT_GENERATE` avant le commit `:441`, avec `user_id` ou `details.actor="system"` ; ne pas toucher `router.py:113` (8.4).
- `backend/src/iryx/core/exceptions.py:19-90` -- réutiliser `ForbiddenException`/`NotFoundException`.
- `backend/tests/conftest.py:35-55` -- `create_all` SQLite : le listener DDL doit installer le trigger.
- `backend/tests/unit/test_report_models.py:203-225`, `test_report_migration.py:57-155` -- aligner sur les nouveaux noms de colonnes et la nouvelle migration.
- `backend/tests/unit/test_report_service.py:257` -- attendre une ligne `REPORT_GENERATE` après génération ; `:1499` et `tests/integration/test_reports_api.py:273` -- les chemins de lecture restent sans audit.

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/audit/triggers.py`, `models.py` -- DDL du trigger, listener `after_create`, forme finale du modèle.
- [x] `backend/src/iryx/audit/services.py`, `schemas.py`, `router.py`, `backend/src/iryx/main.py` -- service, contrats, endpoint et enregistrement.
- [x] `backend/migrations/versions/010_finalize_audit_events.py` -- recréation de la table et trigger ; downgrade complet.
- [x] `backend/src/iryx/auth/router.py`, `cases/router.py`, `evidence/services.py` -- audit connexion, dossier et upload.
- [x] `backend/src/iryx/orchestrator/services.py`, `analytics/services.py` -- audit des portes H1/H2/H3 et des revues de findings.
- [x] `backend/src/iryx/reporting/services.py` -- `REPORT_GENERATE` (utilisateur ou système), sans toucher aux endpoints 8.4.
- [x] `backend/tests/unit/test_audit_service.py` -- hash canonique, expurgation, immutabilité SQLite, rollback.
- [x] `backend/tests/unit/test_audit_migration.py` -- upgrade/downgrade SQLite, DDL hors ligne PostgreSQL, trigger effectif.
- [x] `backend/tests/integration/test_audit_api.py` -- matrice, rôles, pagination, isolation, événements émis.
- [x] `backend/tests/unit/test_report_models.py`, `test_report_migration.py`, `test_report_service.py:257` -- aligner colonnes, migration et attente `REPORT_GENERATE`.

**Acceptance Criteria:**
- Given une action sensible réussie, when elle s'exécute, then exactement une ligne `audit_events` contient `id`, `case_id`, `actor_id`, `action`, `target_type`, `target_id`, `payload_hash`, `details` et `created_at` UTC.
- Given la même action rejouée avec les mêmes paramètres, when l'événement est enregistré, then `payload_hash` est identique.
- Given un `UPDATE` ou `DELETE` SQL, when il est exécuté, then `CANNOT_MODIFY_AUDIT_LOG` est levée et la ligne reste inchangée.
- Given `admin` ou `investigator`, when il consulte la piste, then il reçoit les événements du dossier en ordre déterministe dans l'enveloppe paginée.
- Given `analyst`, `viewer` ou un non-membre, when il appelle l'endpoint, then 403 sans lecture ; given un dossier étranger ou inconnu, then 404 sans fuite.
- Given une génération de rapport avec ou sans utilisateur, when elle réussit, then une ligne `REPORT_GENERATE` est écrite et le téléchargement 8.4 n'en écrit aucune.
- Given des clés secrètes dans `details`, when l'événement est écrit, then elles sont absentes de la ligne et des logs.

## Implementation Notes

## Spec Change Log

## Review Triage Log

### 2026-11-27 - Review pass (blind-hunter, edge-case-hunter, verification-gap)

- verdicts: 31 findings - high 7, medium 8, low 13, false 3, maybe-false 0
- routes: patch 22, defer 4, reject 5

| # | Finding | Verdict | Evidence et route |
|---|---------|---------|-------------------|
| B1 | `cases/services.py:73,242` + `cases/router.py` - `CASE_CREATE`/`CASE_STATUS_UPDATE` commitent avant l'audit, donc l'audit ne peut pas annuler l'action | `[high]` | Confirmé : deux `commit()` précédaient l'écriture d'audit. `create_case`/`update_case_status` acceptent désormais `commit: bool = True`, le router appelle avec `commit=False`, écrit l'audit puis fait un seul `db.commit()` (`cases/router.py:60-71,201-212`). Groupé avec E1/E2. Route `patch`. |
| B2 | `db/session.py:73-100` - `IntegrityError` d'audit non converti et pas de `rollback()` garanti | `[high]` | Confirmé pour le rollback : `get_db_session` ne faisait que `close()`. Le `finally` exécute maintenant `session.rollback()` avant `close()`. `IntegrityError` continue de remonter en 500 plutôt qu'en 503, mais l'action n'est jamais committée (fail-closed) et le contrat figé ne prescrit pas de code HTTP pour ce cas. Route `patch`. |
| B3 | `cases/router.py:63-70` - `details.title` reprend le titre brut de la requête au lieu du titre nettoyé | `[low]` | Confirmé : l'audit utilisait `payload.title`. Il utilise maintenant `case.title`, aligné sur `CaseOut`. Route `patch`. |
| B4 | `audit/services.py:51-60` - l'expurgation par sous-chaîne sur-expurge des clés non secrètes | `[medium]` | Confirmé : `"token_count"`/`"secretary"` étaient supprimés. `_SECRET_KEYS` est comparé par égalité exacte après `lower()`. Route `patch`. |
| B5 | `audit/services.py:51-80` - valeurs non JSON (`UUID`, `datetime`, `bytes`, `Enum`, `NaN`) stockées brutes et hash divergent | `[high]` | Confirmé : `safe_details` n'était pas normalisé avant stockage. `_sanitize` convertit désormais récursivement en structures JSON-safe et `payload_hash` est calculé sur ces détails normalisés. Route `patch`. |
| B6 | `audit/services.py:61-63` - `set` converti en liste dans un ordre non déterministe | `[medium]` | Confirmé : l'ordre d'itération rendait le hash instable. Les sets/frozensets sont triés par leur JSON canonique. Route `patch`. |
| B7 | `audit/services.py:51-80` - les secrets présents dans les valeurs libres ne sont pas retirés | `[low]` | Le contrat figé impose l'expurgation des **clés** listées et la matrice d'edge-cases attend « Clés supprimées » ; scanner les valeurs exigerait une heuristique non spécifiée et risquerait de mutiler `feedback`/`original_name`. Les appelants ne transmettent que des champs contrôlés. Rejeté. |
| B8 | `audit/services.py:140-145` - `count_events` charge toutes les lignes en mémoire | `[medium]` | Confirmé : `len(scalars(...).all())`. Remplacé par `select(func.count()).select_from(AuditEvent)`. Route `patch`. |
| B9 | `audit/schemas.py` - `AuditEventOut.target_id` nullable alors que la colonne et `record()` l'exigent | `[medium]` | Confirmé : le schéma exposait `uuid.UUID \| None`. Il est maintenant `uuid.UUID`. Le `CHECK(length(target_type) > 0)` suggéré n'est pas ajouté : `target_type` n'est alimenté que par des littéraux non vides du service, aucun chemin ne peut le rendre vide. Route `patch`. |
| B10 | `migrations/versions/010_finalize_audit_events.py` - docstring `Revises: 008` alors que `down_revision = "009"` | `[low]` | Confirmé et corrigé en `Revises: 009`. Route `patch`. |
| B11 | `migrations/versions/010_finalize_audit_events.py` - `drop_table` perd d'éventuelles lignes existantes | `[false]` | La décision figée `spec:47` autorise explicitement la recréation : aucun code de production n'écrivait dans `audit_events` avant cette story. Aucune donnée métier ne peut être perdue ; le downgrade restaure la forme 009. Rejeté. |
| B12 | `migrations/versions/010_finalize_audit_events.py` - le downgrade ne supprime pas la fonction PostgreSQL | `[low]` | Confirmé : `DROP TABLE` ne retire pas `prevent_audit_event_mutation()`. Le downgrade exécute `DROP FUNCTION IF EXISTS`. Route `patch`. |
| B13 | `audit/triggers.py` - pas de trigger `BEFORE TRUNCATE` | `[medium]` | Confirmé : `TRUNCATE` purgeait la piste sans erreur. Un trigger `BEFORE TRUNCATE ... FOR EACH STATEMENT` lève `CANNOT_MODIFY_AUDIT_LOG` en PostgreSQL. Route `patch`. |
| B14 | `audit/triggers.py:6` - `AUDIT_LOG_ERROR_MESSAGE` jamais référencé | `[false]` | Vérifié : la constante est interpolée dans les `f"RAISE EXCEPTION '{AUDIT_LOG_ERROR_MESSAGE}'"` des deux dialectes. Aucun code mort. Rejeté. |
| B15 | `audit/triggers.py` + migration 010 - fallback de dialecte incohérent (`postgresql` vs `sqlite`) | `[low]` | Confirmé : deux fallbacks différents. `install_audit_triggers` et la migration retombent désormais sur `postgresql`. Route `patch`. |
| B16 | `audit/triggers.py` - `DROP TRIGGER; CREATE TRIGGER` dans une seule commande, incompatible psycopg3 | `[high]` | Confirmé : les commandes préparées multi-instructions peuvent échouer. Chaque `DROP`/`CREATE` est une entrée séparée de `AUDIT_TRIGGER_STATEMENTS`. Route `patch`. |
| B17 | `backend/pyproject.toml` + `uv.lock` - `fastapi[standard]` ajoute des dépendances | `[low]` | Modification présente avant la story et conservée à la demande explicite de l'utilisateur (entrée déjà consignée dans `deferred-work.md`) ; contraire à « Aucune nouvelle dépendance » mais non causée par 8.5. Groupé avec B18/E4/VG4, route `defer`. |
| B18 | `backend/pyproject.toml` - `httpx` runtime dupliqué via l'extra `standard` | `[low]` | Même cause racine que B17 ; `httpx` est déjà une dépendance `dev` et le changement préexiste à 8.5. Groupé avec B17, route `defer`. |
| B19 | `migrations/versions/010_finalize_audit_events.py` - `_LowercaseHex64Check` dupliqué au lieu de `iryx.core.integrity` | `[low]` | Confirmé : la migration redéfinissait l'expression. Elle importe désormais `LowercaseHex64Check`, source unique ORM/migration. Route `patch`. |
| B20 | `tests/unit/test_report_migration.py:33` - helper `_migration_009` devenu inutilisé | `[low]` | Confirmé : seul `_migration_010()` est appelé. Le helper mort est supprimé. Route `patch`. |
| B21 | `tests/unit/test_timeline_migration.py` - noms `test_migration_008_*` trompeurs | `[false]` | Vérifié : ces tests portent bien sur la migration 008 (métadonnées, SQL offline `008:007`, index `ix_observations_...`) ; l'assertion de head `010` est un garde-fou additif, pas un changement de cible. Rejeté. |
| B22 | `tests/conftest.py` - `drop_all`/`create_all` par test, plus lent | `[low]` | Le trigger SQLite interdit `DELETE` sur `audit_events`, donc le nettoyage ligne à ligne est impossible sans désactiver le trigger (interdit). Le `drop_all` est la seule remise à zéro correcte ; le coût est accepté et le changement demanderait une stratégie de fixtures plus complexe. Rejeté. |
| B23 | `reporting/services.py:36-38` - ligne vide surnuméraire avant `_safe_uuid` | `[low]` | Confirmé et ramené à deux lignes vides. Route `patch`. |
| E1 | `cases/router.py:53-71` - un échec d'audit ne peut pas annuler la création du dossier | `[high]` | Même défaut que B1 : commit précoce du service. Corrigé par `commit=False` + commit unique. Groupé avec B1, route `patch`. |
| E2 | `cases/router.py:193-210` - un échec d'audit ne peut pas annuler le changement de statut | `[high]` | Même défaut que B1 sur `update_case_status`. Corrigé par `commit=False` + commit unique. Groupé avec B1, route `patch`. |
| E3 | `orchestrator/services.py:905-1004` - une décision H3 peut rester dans le checkpointer sans ligne d'audit | `[high]` | Confirmé : `graph.update_state()` précédait l'audit. L'écriture checkpointer est déplacée après `AuditService.record()` et avant `db.commit()`, avec `db.rollback()` si elle échoue ; un test force l'échec d'audit et vérifie que le checkpointer reste sans verdict. Route `patch`. |
| E4 | `backend/pyproject.toml:11-12` - `fastapi[standard]` contredit « Aucune nouvelle dépendance » | `[low]` | Même cause racine que B17, préexistante à 8.5 et déjà consignée. Groupé avec B17, route `defer`. |
| VG1 | Aucun test d'émission `GATE_H1/H2/H3_DECISION` | `[medium]` | Finding pré-vérifié par la couche verification-gap. `tests/unit/test_audit_service_emissions.py` couvre désormais les trois portes (action, cible, dossier, acteur, détails) et le rollback H2/H3 sur échec d'audit. Route `patch`. |
| VG2 | Aucun test d'émission `EVIDENCE_UPLOAD` au point d'appel | `[medium]` | Finding pré-vérifié. Le même fichier teste l'upload accepté (une ligne correctement formée) et l'échec d'audit (aucune ligne `Evidence`/`AuditEvent`, staging nettoyé). Route `patch`. |
| VG3 | Le chemin `REPORT_GENERATE` sans utilisateur n'est pas asserté | `[medium]` | Finding pré-vérifié. `test_report_service.py` vérifie `actor_id is None` + `details["actor"] == "system"` en interne, l'acteur utilisateur quand `user_id` est fourni, et le rollback si l'audit échoue. Route `patch`. |
| VG4 | `backend/pyproject.toml` - aucune vérification que les dépendances sont inchangées | `[low]` | Même cause racine que B17 ; le changement est préexistant et déjà consigné dans `deferred-work.md`. Groupé avec B17, route `defer`. |

## Verification

**Commands:**
- `cd backend && uv run pytest -q` -- expected: suite complète verte.
- `cd backend && uv run ruff check src tests` -- expected: `All checks passed!`.
- `cd backend && uv run pytest -q tests/unit/test_audit_service.py tests/unit/test_audit_migration.py tests/integration/test_audit_api.py` -- expected: ciblé vert.
