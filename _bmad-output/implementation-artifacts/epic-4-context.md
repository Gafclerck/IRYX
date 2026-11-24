# Epic 4 Context: Outils et Gateway forensique

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Implémenter la passerelle sécurisée (Gateway) d'outils forensiques, le registre central des analyseurs, le modèle de traçabilité `ToolExecution` avec calcul d'empreinte SHA-256 et gestion stricte des délais d'attente (`shell=False`), ainsi que les parseurs spécialisés (logs texte/CSV, événements Windows EVTX via `python-evtx`, Registre Windows via `regipy`, artefacts Prefetch via `dissect`), l'analyseur de mémoire Volatility 3 en mode déconnecté (5 plugins autorisés avec symboles ISF locaux), l'extraction normalisée des faits techniques dans l'entité `Observation` avec horodatages UTC, et la troncature contextuelle (8 Ko / 200 lignes max) adaptée aux agents IA.

## Stories

- Story 4.1: Registre de la Gateway forensique, modèle `ToolExecution` et classe de base d'outils (FR8, FR9)
- Story 4.2: Analyseur de logs texte et CSV avec normalisation des horodatages UTC (FR11)
- Story 4.3: Analyseur de journaux d'événements Windows EVTX (`python-evtx`, FR12)
- Story 4.4: Analyseur de ruches de Registre Windows (`regipy`, FR13)
- Story 4.5: Analyseur d'artefacts d'exécution Windows Prefetch (`dissect`, FR14)
- Story 4.6: Analyseur de mémoire vive Volatility 3 avec symboles ISF hors-ligne (FR15, NFR-SEC-08)
- Story 4.7: Troncature contextuelle, résumé des résultats d'outils et endpoints de consultation (FR9, FR10, NFR-PERF-06)

## Requirements & Constraints

- **Exécution contrôlée et sans shell** : Tout sous-processus d'analyse est instancié avec `shell=False` strict. Aucune commande shell arbitraire ni accès à un terminal système n'est autorisé.
- **Environnement d'exécution confiné** : Isolation réseau stricte (`network_mode: none`), exécution sous compte non-root (`uid 10001`), et accès aux fichiers de preuves exclusivement en lecture seule (`chmod 0440`).
- **Auditabilité et traçabilité (`ToolExecution`)** : Chaque exécution d'outil est tracée de façon immuable dans `tool_executions` (`id` UUID, `case_id`, `tool_name`, `tool_version`, `agent_role`, `parameters` JSONB, `result_sha256`, `duration_ms`, et `status`).
- **Normalisation des observations (`Observation`)** : Extraction des faits techniques élémentaires vers l'entité `Observation` (`id` UUID, `case_id`, `source_id`, `tool_name`, `tool_execution_id`, `normalized_content` JSONB, `timestamp_utc`, `source_location`). Tous les horodatages sont convertis et validés en UTC.
- **Troncature contextuelle pour LLM** : Mécanisme bornant les retours d'outils destinés aux agents IA à 8 Ko ou 200 lignes max (50 éléments significatifs) avec mention explicite `[TRUNCATED]`, tandis que le résultat brut intégral est conservé en base.
- **Gestion des délais d'attente (Timeouts)** : Temporisation stricte par outil (de 30 s à 300 s, jusqu'à 600 s pour Volatility). En cas de dépassement, interruption immédiate du processus, marquage `timeout` dans `ToolExecution` et levée d'exception `ToolExecutionTimeoutException`.

## Technical Decisions

- **D-04** : Validation des paramètres d'entrée et sorties via des schémas Pydantic v2 stricts.
- **D-05 & D-06** : Modèles relationnels PostgreSQL 16 avec SQLAlchemy 2.x (`ToolExecution` et `Observation`).
- **D-07** : Migration Alembic dédiée pour la création des tables `tool_executions` et `observations`.
- **D-14** : Calcul d'empreinte SHA-256 standard via `hashlib`.
- **D-16** : Analyse EVTX en pur Python via la bibliothèque `python-evtx`.
- **D-17** : Analyse des ruches de registre Windows via la bibliothèque `regipy`.
- **D-18** : Analyse des fichiers Windows Prefetch via la bibliothèque `dissect`.
- **D-26** : Analyseur mémoire Volatility 3 hors-ligne restreint aux 5 plugins autorisés (`windows.info`, `windows.pslist`/`windows.pstree`, `windows.cmdline`, `windows.netscan`, `windows.malware.malfind`).
- **D-24** : Troncature contextuelle protectrice de la fenêtre de contexte des agents.

## Cross-Story Dependencies

- E4 dépend d'E1, E2 et E3 : Les utilisateurs, dossiers (`Case`), preuves scellées (`Evidence`) et le contrôle d'accès dossier (`verify_case_access`) sont déjà opérationnels.
- Story 4.1 pose les fondations communes : création des tables `tool_executions` et `observations`, classe abstraite `BaseTool`, registre central d'outils `ToolRegistry`, et gestion du cycle d'exécution avec timeouts et empreinte SHA-256.
- Stories 4.2 à 4.6 implémentent les différents analyseurs concrets qui héritent de `BaseTool` et s'enregistrent auprès de `ToolRegistry`.
- Story 4.7 finalise l'épic en exposant la troncature contextuelle et les routes REST de consultation pour les analystes et agents.
