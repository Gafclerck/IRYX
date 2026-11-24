---
title: "Story 4.6 : Analyseur de mémoire vive Volatility 3 avec symboles ISF hors-ligne (FR15, NFR-SEC-08)"
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: 'd992059d48e1e56f9196e53b451065f4c79fe7e9'
baseline_revision: 'd992059d48e1e56f9196e53b451065f4c79fe7e9'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/docs/02-agents-et-outils.md'
  - '{project-root}/docs/07-api-llm-et-dependances.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les images de mémoire vive (RAM) constituent une source forensique critique mais particulièrement sensible pour déceler les processus cachés, les sockets réseau actives, les commandes injectées et les zones RWX suspectes ; toutefois, leur analyse doit s'effectuer sans connexion réseau (mode air-gapped) et en confinant strictement les commandes exécutables à des plugins audités et validés.

**Approach:** Implémenter l'analyseur `Volatility3Tool` (nom de registre `analyze_memory`, timeout 600 s) encapsulant Volatility 3 (v2.7.0) avec isolation hors ligne (`--offline`), utilisation des symboles ISF locaux (`/opt/volatility3/symbols`), restriction stricte aux 5 plugins autorisés, extraction et normalisation des observations techniques avec horodatages UTC dans `Observation`, et audit immuable dans `ToolExecution`.

## Boundaries & Constraints

**Always:**
- Nom d'outil enregistré `analyze_memory` (déjà présent dans `MVP_TOOL_WHITELIST`), version `2.7.0` (métadonnées `volatility_version: 2.7.0`), timeout par défaut de 600 secondes (`NFR-PERF-02`).
- Hériter de `BaseTool` et valider les paramètres via le schéma Pydantic v2 strict `Volatility3Parameters` (`extra="forbid"`) : `evidence_id`, `file_path`, `plugin_name`, `plugin_args` (liste d'arguments passés au plugin), `max_results` (1 à 50 000, défaut 5000), `symbols_path` (chemin optionnel des symboles ISF).
- Validation stricte de la liste blanche des 5 plugins autorisés : `windows.info`, `windows.pslist` (et son variant `windows.pstree`), `windows.cmdline`, `windows.netscan`, `windows.malfind` (et alias `windows.malware.malfind`). Tout autre plugin (ex. `windows.mimikatz`, `linux.bash`) est immédiatement rejeté avec levée de `PluginNotWhitelistedException` (code `PLUGIN_NOT_WHITELISTED`, HTTP 403) avant toute tentative d'exécution.
- Exécution confinée sans shell (`shell=False`) via `run_command_safely` (invoquant l'interpréteur Python avec le point d'entrée Volatility 3 `volatility3.cli:main` en sous-processus isolé), avec drapeau `--offline` obligatoire interdisant toute requête réseau (NFR-SEC-02).
- Utilisation du répertoire de symboles ISF configuré (`settings.volatility_symbols_path` par défaut `/opt/volatility3/symbols`, ou paramètre `symbols_path` fourni).
- Sortie structurée JSON (`-r json`) analysée et convertie en entités `Observation` normalisées : horodatages convertis en UTC (`timestamp_utc`), localisation d'origine (`source_location`), contenu structuré normalisé (`normalized_content`) intégrant `plugin_name`, les identifiants techniques (PID, PPID, adresses IP/ports, chemins, hashes, protection mémoire) et métadonnées d'exécution.
- Enregistrement systématique de `Volatility3Tool` dans `default_registry` au sein de `backend/src/iryx/gateway/registry.py` et exportation dans `iryx.gateway.tools` et `iryx.gateway`.
- Dépendance `volatility3==2.7.0` déclarée dans `backend/pyproject.toml` (avec `pefile`).

**Never:**
- Aucun appel shell arbitraire ni accès à un terminal système (`shell=False` strict).
- Aucun téléchargement dynamique de symboles ni tentative de contact réseau (`--offline` systématique).
- Aucune exécution de plugin non whitelisté au MVP.
- Aucune écriture ni altération sur les fichiers dumps mémoire analysés (lecture seule stricte).
- Aucun crash non intercepté : les erreurs de parsing mémoire ou d'images corrompues sont capturées en `VolatilityExecutionError` (sous-classe de `ToolExecutionFailedException`), permettant à `ToolRunner` de persister le statut `error` sans faire planter l'application.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Plugin windows.info nominal | Image RAM Windows valide, plugin `windows.info` | Sortie OS extraite (Kernel Base, NT Build, SystemTime), 1 observation générée avec `timestamp_utc` SystemTime et contenu structuré | N/A |
| Plugin windows.pslist / pstree nominal | Image RAM Windows valide, plugin `windows.pslist` | Liste des processus extraite (PID, PPID, nom d'image, threads, handles), 1 observation par processus horodatée avec `CreateTime` UTC | N/A |
| Plugin windows.cmdline nominal | Image RAM Windows valide, plugin `windows.cmdline` | Lignes de commande des processus extraites, 1 observation par processus | N/A |
| Plugin windows.netscan nominal | Image RAM Windows valide, plugin `windows.netscan` | Connexions réseau et ports d'écoute extraits, 1 observation par socket avec IP/port source/dest et horodatage UTC | N/A |
| Plugin windows.malfind nominal | Image RAM Windows valide avec injection de code, plugin `windows.malfind` | Régions mémoire suspectes RWX extraites avec aperçu hexdump/disasm, 1 observation par zone injectée | N/A |
| Plugin hors liste blanche | Plugin `windows.mimikatz` ou `linux.bash` | Refus immédiat avant exécution, aucune persistance `ToolExecution` | `PluginNotWhitelistedException` (code `PLUGIN_NOT_WHITELISTED`, HTTP 403) |
| Timeout d'exécution (> 600 s) | Commande Volatility dépassant 600 s | Processus sous-jacent tué, `ToolExecution.status="timeout"` persisté en base | `ToolExecutionTimeoutException` via `ToolRunner` |
| Image mémoire corrompue / invalide | Fichier tronqué ou corrompu ne correspondant à aucun format mémoire reconnu | `ToolExecution.status="error"`, message capturé | `VolatilityExecutionError` (sous-classe `ToolExecutionFailedException`) |
| Source introuvable | `evidence_id` ou `file_path` inexistant | Aucune trace persistée en base | `ValidationException` |

</frozen-after-approval>

## Code Map

- `backend/src/iryx/gateway/tools/volatility_analyzer.py` -- Nouveau module : `Volatility3Parameters`, `VolatilityExecutionError`, dictionnaire des plugins autorisés `AUTHORIZED_PLUGINS`, fonctions de normalisation des observations par plugin, et classe `Volatility3Tool`.
- `backend/src/iryx/gateway/runner.py` -- `run_command_safely` (exécution de sous-processus sans shell avec timeout) et `ToolRunner` (calcul SHA-256, gestion d'erreurs, persistance `ToolExecution` et `Observation`).
- `backend/src/iryx/gateway/registry.py` -- `MVP_TOOL_WHITELIST` (contient déjà `analyze_memory`), enregistrement de `Volatility3Tool` dans `_register_default_tools`.
- `backend/src/iryx/gateway/tools/__init__.py` et `backend/src/iryx/gateway/__init__.py` -- Exports publics de l'outil et de ses schémas.
- `backend/src/iryx/core/config.py` -- Paramètre `volatility_symbols_path` déjà présent.
- `backend/src/iryx/core/exceptions.py` -- `PluginNotWhitelistedException`, `ToolExecutionTimeoutException`, `ToolExecutionFailedException`.
- `backend/tests/unit/test_tool_volatility_analyzer.py` -- Tests unitaires complets couvrant l'ensemble de la matrice I/O, le rejet des plugins hors whitelist, le respect du mode offline et l'intégration `ToolRunner`.

## Tasks & Acceptance

**Execution:**
- [x] `backend/pyproject.toml` / `uv.lock` -- Déclarer `volatility3==2.7.0` dans les dépendances du backend.
- [x] `backend/src/iryx/gateway/tools/volatility_analyzer.py` -- Implémenter `Volatility3Parameters`, `VolatilityExecutionError`, la table des plugins whitelistés, les fonctions d'extraction/normalisation des observations (`windows.info`, `pslist`/`pstree`, `cmdline`, `netscan`, `malfind`) et la classe `Volatility3Tool` (nom `analyze_memory`, timeout 600 s) -- Cœur de la story.
- [x] `backend/src/iryx/gateway/registry.py`, `backend/src/iryx/gateway/tools/__init__.py`, `backend/src/iryx/gateway/__init__.py` -- Enregistrer `Volatility3Tool` dans `default_registry` et exporter les symboles publics.
- [x] `backend/tests/unit/test_tool_volatility_analyzer.py` -- Développer la suite de tests unitaires couvrant les 5 plugins autorisés, le rejet de plugins hors whitelist, la gestion des timeouts, les dumps corrompus et l'intégration `ToolRunner`.

**Acceptance Criteria:**
- Given un dump mémoire vive Windows et la présence de symboles ISF, when l'outil `analyze_memory` est invoqué avec un des 5 plugins autorisés (`windows.info`, `windows.pslist`/`pstree`, `windows.cmdline`, `windows.netscan`, `windows.malfind`), then Volatility 3 s'exécute en mode hors ligne (`--offline`), la sortie est convertie en entités `Observation` normalisées avec horodatages UTC, et l'exécution est tracée dans `ToolExecution` avec statut `success`.
- Given une tentative d'exécution d'un plugin hors de la liste blanche (ex. `windows.mimikatz` ou `linux.bash`), when la Gateway valide la requête, then l'exécution est immédiatement refusée avec levée de `PluginNotWhitelistedException` portant le code `PLUGIN_NOT_WHITELISTED`.
- Given une exécution d'analyse mémoire dépassant 600 secondes, when le timeout survient, then le processus sous-jacent est interrompu, `ToolExecutionTimeoutException` est levée et la trace `ToolExecution` enregistre le statut `timeout`.

## Implementation Notes

- Déclaration de `volatility3==2.7.0` et `pefile>=2023.2.7` dans `backend/pyproject.toml` et régénération de `uv.lock`.
- Implémentation du module `backend/src/iryx/gateway/tools/volatility_analyzer.py` avec le schéma strict `Volatility3Parameters` (Pydantic v2 `extra="forbid"`), la classe d'erreur `VolatilityExecutionError` (code `VOLATILITY_EXECUTION_ERROR`), le registre `AUTHORIZED_PLUGINS` restreint aux 5 plugins MVP (`windows.info`, `windows.pslist`/`pstree`, `windows.cmdline`, `windows.netscan`, `windows.malfind`/`windows.malware.malfind`) et l'outil `Volatility3Tool` (`name="analyze_memory"`, `version="2.7.0"`, `timeout_seconds=600`).
- Exécution de Volatility 3 en sous-processus isolé sans shell (`shell=False`) via `run_command_safely` avec isolation réseau stricte `--offline` et passage du chemin de symboles ISF configuré (`settings.volatility_symbols_path` / `/opt/volatility3/symbols`).
- Fonctions de normalisation des sorties JSON pour chaque plugin en entités `Observation` horodatées en UTC (`timestamp_utc`) et liées au dossier / preuve.
- Enregistrement automatique de `Volatility3Tool` dans `default_registry` au sein de `backend/src/iryx/gateway/registry.py` et exportation publique des symboles dans `iryx.gateway.tools` et `iryx.gateway`.
- 19 tests unitaires dédiés créés dans `backend/tests/unit/test_tool_volatility_analyzer.py` validant tous les scénarios nominaux et d'erreur ainsi que l'intégration avec `ToolRunner`.
- Suite complète de 500 tests exécutée avec 100 % de succès (`500 passed`) et linters `ruff check` / `ruff format` validés à 100 %.

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Evidence |
|---|---|---|
| Absence de tests de résolution par `evidence_id` et liaison `source_id` pour `analyze_memory` | medium | Gap pré-vérifié par le reviewer de vérification : aucun test n'exécutait `analyze_memory` avec `evidence_id` en staging/storage. Corrigé avec deux tests unitaires dédiés (`test_source_resolution_by_evidence_id_in_staging` et `test_missing_evidence_id_raises_validation_exception`). |
| Absence d'assertion sur le fallback vers `settings.volatility_symbols_path` par défaut | low | Gap pré-vérifié par le reviewer de vérification : les tests nominaux omettaient de vérifier que `-s` recevait la valeur par défaut configurée. Corrigé avec assertion explicite dans `test_execute_windows_info_nominal`. |
| Robustesse de l'extraction JSON en cas de logs préfixés entre crochets (ex. `[WARNING]`) | medium | `raw_stdout.find("[")` pouvait matcher une balise de log avant le tableau JSON; corrigé dans `volatility_analyzer.py` avec extraction itérative d'un payload JSON valide et test dédié `test_json_with_prefix_warning_log`. |

## Design Notes

L'outil exécute Volatility 3 sous forme de sous-processus isolé sans shell (`shell=False`) via `run_command_safely`, garantissant l'absence de saturation mémoire ou de crash fatal sur le processus backend principal.
La ligne de commande invoque l'interpréteur Python avec le point d'entrée CLI officiel de Volatility (`volatility3.cli:main`), en passant obligatoirement les drapeaux `-q`, `--offline`, `-r json`, `-s <symbols_path>` et `-f <memory_file>`.
Le parseur JSON traite le format arborescent ou tabulaire produit par le JsonRenderer de Volatility 3 et génère les entités `Observation` avec les attributs forensiques clés et horodatages normalisés en UTC (`SystemTime`, `CreateTime`, dates de connexions réseau).

## Verification

**Commands:**
- `uv run pytest backend/tests/unit/test_tool_volatility_analyzer.py` -- expected: tous les tests passent
- `uv run pytest` -- expected: 100% des tests du projet passent
- `uv run ruff check backend` -- expected: 0 erreur
- `uv run ruff format --check backend` -- expected: 0 modification
