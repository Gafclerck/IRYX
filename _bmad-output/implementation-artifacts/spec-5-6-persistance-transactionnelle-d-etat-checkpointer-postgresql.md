---
title: "Story 5.6 : Persistance transactionnelle d'état (Checkpointer PostgreSQL) et reprise après incident (FR21)"
type: 'feature'
created: '2026-11-25'
status: 'done'
baseline_revision: '7db55a1c71abcbf47cc8b9fcd0bea0d93820cb50'
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

**Problem:** En cas de redémarrage de conteneur, d'interruption réseau ou de suspension sur une porte de contrôle humain (H1, H2, H3), l'état complet du graphe LangGraph doit être persisté de manière transactionnelle dans PostgreSQL 16 afin de garantir la reprise exacte d'une session d'investigation sans perte de données ni recalcul (FR21, NFR-REL-01, D-05, D-06, D-09, ADR-0007).

**Approach:** Intégrer le checkpointer officiel LangGraph PostgreSQL (`PostgresSaver`) avec factory adaptative pour les environnements de test (`MemorySaver`), enregistrer l'état de chaque nœud sous un `thread_id` cloisonné par session (`run_id`), et exposer l'endpoint REST sécurisé `POST /api/v1/cases/{case_id}/investigations/{run_id}/resume` permettant de recharger l'état exact et de reprendre l'orchestration tout en rejetant rigoureusement les sessions déjà terminées (HTTP 400 `CANNOT_RESUME_TERMINATED_SESSION`).

## Boundaries & Constraints

**Always:**
- Persister l'état complet des canaux du graphe LangGraph (state snapshot) dans PostgreSQL 16 via le checkpointer à chaque nœud et porte humaine (D-05, D-06, D-09, ADR-0007).
- Cloisonner strictement les enregistrements de checkpoints par identifiant de session unique (`thread_id = str(run_id)`), garantissant l'étanchéité multi-tenancy et inter-dossiers.
- Exposer l'endpoint `POST /api/v1/cases/{case_id}/investigations/{run_id}/resume` protégé par RBAC (autorisé pour `ADMIN`, `INVESTIGATOR`, `ANALYST` ; interdit avec HTTP 403 pour `VIEWER`) et par le contrôle d'accès au dossier (`verify_case_access`).
- Rejeter toute tentative de reprise d'une session déjà achevée ou échouée (`completed` ou `failed`) avec une réponse HTTP 400 Bad Request et le code machine strict `CANNOT_RESUME_TERMINATED_SESSION`.
- Mettre à jour de manière transactionnelle le statut (`InvestigationRun.status`), la phase courante (`InvestigationRun.current_phase`), le compteur d'erreurs (`error_count`) et les phases associées (`Phase`) lors de la reprise.
- Assurer la rétrocompatibilité des tests unitaires et d'intégration en fournissant une factory de checkpointer transparente basculant sur un `MemorySaver` sous SQLite / environnement de test.
- Gérer le cycle de vie des tables de checkpointing PostgreSQL via les utilitaires officiels du checkpointer (`PostgresSaver.setup()`) conformément à ADR-0007 et DP-04.

**Never:**
- Jamais de reprise d'une session dont le statut est `completed` ou `failed` (violation de l'Invariant 1).
- Jamais de partage ou de collision d'états de checkpoints entre deux sessions d'investigation distinctes (violation du cloisonnement strict).
- Jamais d'accès direct non autorisé à la table des checkpoints ou d'altération manuelle hors du protocole de checkpointing LangGraph.
- Jamais d'utilisation de `Base.metadata.create_all` dans le code de production (Règle 9 & Alembic strict).
- Jamais d'exposition de secrets ou d'informations d'authentification dans les logs lors de l'accès au checkpointer.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Reprise nominale après suspension sur porte H1 | Session avec statut `paused` / `current_phase: waiting_h1` | Endpoint `POST .../resume` recharge l'état exact, réévalue les conditions ou reprend le graphe, met à jour `InvestigationRun` et retourne `InvestigationRunOut` | Pas d'erreur attendue |
| Reprise après interruption en cours d'exécution | Session avec statut `running` ou `paused` après crash/restart | Le checkpointer restaure le dernier état validé et le graphe reprend à partir du nœud interrompu | Pas d'erreur attendue |
| Tentative de reprise sur session `completed` | Session existante avec `status == completed` | Rejet immédiat avec HTTP 400 Bad Request et code `CANNOT_RESUME_TERMINATED_SESSION` | `CannotResumeTerminatedSessionException` (HTTP 400) |
| Tentative de reprise sur session `failed` | Session existante avec `status == failed` | Rejet immédiat avec HTTP 400 Bad Request et code `CANNOT_RESUME_TERMINATED_SESSION` | `CannotResumeTerminatedSessionException` (HTTP 400) |
| Reprise sur session inexistante ou mauvais dossier | `run_id` inconnu ou rattaché à un autre `case_id` | Rejet avec HTTP 404 Not Found et code `INVESTIGATION_NOT_FOUND` | `InvestigationNotFoundException` (HTTP 404) |
| Tentative de reprise par un utilisateur VIEWER | Utilisateur avec rôle `VIEWER` sur le dossier | Rejet avec HTTP 403 Forbidden et code `INSUFFICIENT_PERMISSIONS` | `InsufficientPermissionsException` (HTTP 403) |
| État de checkpoint absent pour une session active | `run_id` valide en base mais aucun snapshot dans le checkpointer | Initialisation de secours de l'état LangGraph depuis l'entité `InvestigationRun` en base et reprise | Fallback contrôlé |

</intent-contract>

## Code Map

- `backend/src/iryx/core/exceptions.py` -- Définition de l'exception métier typée `CannotResumeTerminatedSessionException` (HTTP 400 Bad Request, code `CANNOT_RESUME_TERMINATED_SESSION`).
- `backend/src/iryx/orchestrator/checkpointer.py` -- Module factory du checkpointer IRYX (`get_checkpointer`, `get_memory_saver`, `reset_memory_saver`, `normalize_postgres_url`, `get_checkpointer_dependency`) supportant `PostgresSaver` pour PostgreSQL et `MemorySaver` pour SQLite/tests.
- `backend/src/iryx/orchestrator/services.py` -- Implémentation de `InvestigationService.resume_investigation(case_id, run_id)` assurant le verrouillage transactionnel, la validation des statuts terminaux, le chargement du snapshot LangGraph et la synchronisation des phases.
- `backend/src/iryx/orchestrator/router.py` -- Exposition de l'endpoint `POST /api/v1/cases/{case_id}/investigations/{run_id}/resume` avec dépendances `require_case_role` et `verify_case_access`.
- `backend/src/iryx/orchestrator/graph.py` -- Intégration du checkpointer dans `build_investigation_graph`, gestion du contexte runtime non sérialisable via `ContextVar` (`set_runtime_context`), et persistance automatique à chaque exécution de nœud.
- `backend/src/iryx/orchestrator/__init__.py` -- Exportation des nouvelles classes et méthodes (`get_checkpointer`, `CannotResumeTerminatedSessionException`).
- `backend/tests/unit/test_checkpointer_and_resume.py` -- Suite de tests unitaires et d'API dédiée à la persistance, la reprise d'investigation, les cas d'erreur (400, 403, 404) et le cloisonnement par session.

## Tasks & Acceptance

**Execution:**
- `backend/src/iryx/core/exceptions.py` -- Ajouter `CannotResumeTerminatedSessionException` avec HTTP 400 et code machine `CANNOT_RESUME_TERMINATED_SESSION` -- Fournir l'exception métier requise par les critères d'acceptation de la Story 5.6.
- `backend/src/iryx/orchestrator/checkpointer.py` -- Créer la factory et les utilitaires de checkpointer LangGraph supportant PostgreSQL (`PostgresSaver`) et SQLite/test (`MemorySaver`) -- Garantir la persistance transactionnelle d'état en base et la testabilité sans dépendance PostgreSQL externe.
- `backend/src/iryx/orchestrator/services.py` -- Implémenter la méthode `resume_investigation` avec verrouillage pessimiste, contrôle de statut terminal et reprise LangGraph -- Fournir le service métier de restauration d'état et de synchronisation des phases.
- `backend/src/iryx/orchestrator/router.py` -- Ajouter l'endpoint `POST /api/v1/cases/{case_id}/investigations/{run_id}/resume` protégé par RBAC -- Exposer l'opération de reprise aux analystes et administrateurs.
- `backend/src/iryx/orchestrator/graph.py` -- Enrichir `build_investigation_graph` pour utiliser le checkpointer configuré et fiabiliser la persistance continue -- Permettre la sauvegarde de l'état après chaque exécution de nœud.
- `backend/tests/unit/test_checkpointer_and_resume.py` -- Écrire les tests unitaires et d'intégration validant la persistance, la reprise, le rejet des sessions terminées et les contrôles RBAC -- Confirmer la conformité intégrale avec les critères d'acceptation de la Story 5.6.

**Acceptance Criteria:**
- Given une session d'enquête en cours ou en pause sur une porte de contrôle (H1, H2, H3), when chaque nœud du graphe LangGraph termine son exécution, then l'état complet des canaux du graphe (state snapshot) est sauvegardé dans le checkpointer (D-05, D-09).
- Given une session d'investigation interrompue ou en pause, when une requête `POST /api/v1/cases/{case_id}/investigations/{run_id}/resume` est soumise par un utilisateur autorisé (ADMIN, INVESTIGATOR, ANALYST), then le serveur recharge l'état exact depuis le checkpointer et reprend l'exécution là où elle s'était arrêtée.
- Given une tentative de reprise d'une session dont le statut est déjà `completed` ou `failed`, when la requête `POST .../resume` est soumise, then le serveur répond HTTP 400 Bad Request avec le code `CANNOT_RESUME_TERMINATED_SESSION`.
- Given une tentative de reprise par un utilisateur ayant le rôle `VIEWER`, when la requête `POST .../resume` est soumise, then le serveur répond HTTP 403 Forbidden avec le code `INSUFFICIENT_PERMISSIONS`.
- Given les enregistrements de checkpoints dans la table de persistance, when les accès sont effectués, then les enregistrements sont cloisonnés par identifiant de session unique (`thread_id = str(run_id)`) et protégés contre les altérations manuelles.

## Spec Change Log

- 2026-11-25 : Initialisation de la spécification de la Story 5.6 suite à `/bmad-build-auto 5.6`.
- 2026-11-25 : Implémentation terminée, passage du statut à `done`.

## Review Triage Log

- 2026-11-25 - Review pass auto:
  - Finding 1: Sérialisation MsgPack LangGraph Checkpointer (`TypeError: Type is not msgpack serializable: Session`).
    - Fix: Injection des dépendances d'exécution volatiles (`db`, `tool_runner`, `tool_registry`) via `contextvars.ContextVar` (`set_runtime_context` / `get_runtime_context`) au lieu d'altérer `InvestigationState["context"]` sérialisé dans le checkpointer. Nettoyage systématique dans un bloc `finally`.
  - Finding 2: Isolation des contextes de test vs contexte runtime global.
    - Fix: Priorité donnée au contexte local passé explicitement (`context.get("db")` avant `get_runtime_context().get("db")`) pour prévenir toute pollution croisée lors des exécutions pytest.
  - Finding 3: Validation Pydantic du plan d'investigation (`step_id` et `rationale`).
    - Fix: Conformité stricte des fixtures de test avec `InvestigationPlan` et `InvestigationStep` pour éviter les erreurs de parsing lors de la reprise.
  - Finding 4: Rejet strict des sessions achevées/échouées.
    - Fix: `CannotResumeTerminatedSessionException` (HTTP 400 Bad Request, code `CANNOT_RESUME_TERMINATED_SESSION`) systématiquement levée dès que `run.status in (InvestigationStatus.COMPLETED, InvestigationStatus.FAILED)`.
  - Finding 5: Cloisonnement strict multi-tenant par `thread_id`.
    - Fix: Chaque exécution et reprise est isolée par `thread_id = str(run_id)`. Test de non-collision validé avec 2 sessions distinctes.
  - Finding 6: Contrôle d'accès RBAC et isolation dossier.
    - Fix: Endpoint `POST /api/v1/cases/{case_id}/investigations/{run_id}/resume` protégé par `require_case_role([Role.ADMIN, Role.INVESTIGATOR, Role.ANALYST])` et `verify_case_access`. Les utilisateurs `VIEWER` reçoivent HTTP 403.
  - Finding 7: Gestion des tables de checkpoints (PostgresSaver vs Alembic).
    - Fix: Conformité avec ADR-0007 et DP-04 où `PostgresSaver.setup()` gère ses tables internes PostgreSQL, préservant la tête de migration Alembic actuelle (`006`) sans conflit avec les tests de migration existants.

## Design Notes

- **Cloisonnement multi-tenancy par `thread_id` :** LangGraph utilise la clé `thread_id` dans le dictionnaire de configuration `{"configurable": {"thread_id": str(run_id)}}`. En fixant `thread_id` à la chaîne de l'UUID de `InvestigationRun`, chaque session possède une ligne de vie strictement indépendante et étanche dans les tables `checkpoints`, `checkpoint_blobs` et `checkpoint_writes`.
- **Factory adaptative PostgreSQL / MemorySaver :** En production, IRYX utilise PostgreSQL 16 via `psycopg` et `langgraph-checkpoint-postgres.PostgresSaver`. En environnement de test automatisé (Pytest utilisant un moteur SQLite en mémoire vive), la factory instancie un `MemorySaver` persistant pour le thread, garantissant des tests ultra-rapides, hermétiques et sans dépendance d'un service PostgreSQL actif.
- **Verrouillage transactionnel à la reprise :** L'appel à `resume_investigation` acquiert un verrou ligne `with_for_update()` sur l'entité `InvestigationRun` pour prévenir toute double exécution concurrente de la même session d'investigation (TOCTOU).

## Verification

**Commands:**
- `uv run pytest backend/tests/unit/test_checkpointer_and_resume.py` -- expected: Tous les tests de persistance, reprise, permissions RBAC et cas d'erreur 400/403/404 réussissent.
- `uv run pytest backend/tests/unit/test_alembic.py` -- expected: Les tests de migration Alembic passent avec la suite existante.
- `uv run pytest` -- expected: L'ensemble de la suite de tests globale passe sans aucune régression.

## Auto Run Result

- **Statut final :** Succès complet (`done`).
- **Fichiers modifiés / créés :**
  - `backend/pyproject.toml` & `uv.lock` : Ajout de `langgraph-checkpoint-postgres>=3.2.1` et `psycopg-pool>=3.3.3`.
  - `backend/src/iryx/core/exceptions.py` : Ajout de `CannotResumeTerminatedSessionException` (HTTP 400 Bad Request, code `CANNOT_RESUME_TERMINATED_SESSION`).
  - `backend/src/iryx/orchestrator/checkpointer.py` : Factory adaptative (`get_checkpointer`, `get_memory_saver`, `reset_memory_saver`, `normalize_postgres_url`, `get_checkpointer_dependency`).
  - `backend/src/iryx/orchestrator/graph.py` : Intégration du checkpointer dans `build_investigation_graph` et gestion du contexte runtime non-sérialisable via `ContextVar`.
  - `backend/src/iryx/orchestrator/services.py` : Implémentation de `InvestigationService.resume_investigation(case_id, run_id)` avec verrouillage transactionnel `with_for_update()`, contrôle de statut terminal, restauration du snapshot LangGraph et synchronisation des phases.
  - `backend/src/iryx/orchestrator/router.py` : Exposition de l'endpoint `POST /api/v1/cases/{case_id}/investigations/{run_id}/resume` sécurisé par RBAC et `verify_case_access`.
  - `backend/src/iryx/orchestrator/__init__.py` : Export des composants de checkpointing.
  - `backend/tests/unit/test_checkpointer_and_resume.py` : Suite de 19 tests unitaires et d'intégration validant la persistance, la reprise, le cloisonnement et la gestion d'erreurs (400, 403, 404).
- **Vérifications exécutées :**
  - `uv run ruff check backend` : 0 erreur.
  - `uv run ruff format backend` : code formaté.
  - `uv run pytest backend/tests/unit/test_checkpointer_and_resume.py backend/tests/unit/test_alembic.py` : 25/25 passés.
  - `uv run pytest` : 660/660 passés (100%).
- **Risques résiduels :** Aucun.
