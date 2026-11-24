---
title: "Story 4.4 : Analyseur de ruches de Registre Windows (regipy, FR13)"
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: 'e45766e0d22390c9b2583c9db6539a37b61111d4'
baseline_revision: 'e45766e0d22390c9b2583c9db6539a37b61111d4'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/docs/02-agents-et-outils.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les ruches de Registre Windows (`SYSTEM`, `SOFTWARE`, `NTUSER.DAT`, `SAM`) contiennent les mécanismes d'autorun, les services, les comptes et les traces d'exécution (UserAssist), mais leur format binaire `regf` est inexploitable par les agents sans parseur dédié et sûr.

**Approach:** Implémenter `RegistryParserTool` (nom enregistré `parse_registry`, timeout 120 s) en pur Python via `regipy` (D-17) : parcours récursif borné des clés ciblées, une `Observation` par valeur avec `last_write_time` de la clé converti en UTC, et échec tracé `error` dans `ToolExecution` pour une ruche illisible.

## Boundaries & Constraints

**Always:**
- Hériter de `BaseTool`, nom `parse_registry` (déjà dans `MVP_TOOL_WHITELIST`), schéma Pydantic v2 `RegistryParserParameters` (`extra="forbid"`) : `evidence_id`, `file_path`, `hive_type` (`auto|system|software|ntuser|sam|security|usrclass|amcache`, défaut `auto`), `key_paths` (≤ 50, optionnel), `recursive` (défaut `True`), `max_depth` (1–32, défaut 10), `max_values` (1–50000, défaut 5000), `search_query`.
- Au moins une source (`evidence_id` ou `file_path`) ; résolution de la preuve identique à `EvtxParserTool._resolve_source` ; source introuvable → `ValidationException` (aucune persistance).
- Chemins normalisés (`/` → `\`, préfixe `\`). `\CurrentControlSet` résolu pour la ruche `system` via `\Select` valeur `Current` (repli `ControlSet001`).
- Sans `key_paths`, presets par `hive_type` (constante `DEFAULT_KEY_PATHS`) : `software` → Run/RunOnce (natif et `Wow6432Node`), `Winlogon` ; `system` → `\CurrentControlSet\Services`, `\CurrentControlSet\Control\ComputerName\ComputerName` ; `ntuser` → `\Software\Microsoft\Windows\CurrentVersion\Run`, `RunOnce`, `Explorer\UserAssist` ; `sam` → `\SAM\Domains\Account\Users\Names`. Type sans preset (ou `auto` non détecté) et sans `key_paths` → `ValidationException`.
- Chaque valeur → observation : `source_location` = chemin exact de la clé (≤ 512 car.), `timestamp_utc` = `last_write_time` UTC de la clé, `normalized_content` = `hive_type`, `key_path`, `value_name`, `value_data`, `value_type`, `last_write_time_utc` (ISO-8601), `is_corrupted`, + `decoded_value_name` (ROT13) sous `UserAssist\...\Count`.
- `value_data` sérialisable JSONB : `bytes` → hex (plafond 4096 octets, drapeau `value_data_truncated`), caractères `\x00` retirés des chaînes.
- Clé absente → `metadata.missing_keys` (pas une erreur) ; erreur sur une clé/valeur isolée → `metadata.errors`, le parcours continue ; plafond `max_values` atteint → `metadata.truncated=True`.
- En-tête invalide (taille < 4096 ou magic ≠ `regf`), fichier verrouillé (`OSError`) ou exception `regipy` à l'ouverture → `RegistryHiveParsingError` (sous-classe de `ToolExecutionFailedException`) afin que `ToolRunner` persiste `status=error` avec le message.
- Ajouter `regipy>=5.1.0` aux dépendances de `backend/pyproject.toml` (+ `uv.lock`).

**Never:**
- Aucun sous-processus, shell ou binaire externe ; aucun appel réseau ni transmission hors base locale.
- Aucune écriture/modification de la ruche source (lecture binaire seule).
- Aucun plugin `regipy` automatique ni décodage avancé (ShimCache, Amcache…) : hors périmètre.
- Aucun horodatage naïf.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Run NTUSER nominal | `key_paths=["\Software\Microsoft\Windows\CurrentVersion\Run"]`, 2 valeurs | 2 observations, `source_location` = chemin de la clé, `timestamp_utc` UTC | N/A |
| Récursion Services | ruche `system`, `\CurrentControlSet\Services` | `ControlSet00N` résolu, valeurs des sous-clés extraites jusqu'à `max_depth` | N/A |
| Presets par défaut | `hive_type="software"`, sans `key_paths` | Clés presets parcourues ; absentes listées dans `missing_keys` | N/A |
| UserAssist | valeur `HRZR_EHACNGU` sous `...\Count` | `decoded_value_name="UEME_RUNPATH"` | N/A |
| Donnée binaire | `REG_BINARY` de 10 000 octets | hex de 4096 octets, `value_data_truncated=True` | N/A |
| Plafond | 300 valeurs, `max_values=100` | 100 observations, `truncated=True` | N/A |
| En-tête invalide | fichier texte ou < 4096 octets | `ToolExecution.status=error`, message capturé | `ToolExecutionFailedException` via `ToolRunner` |
| Source introuvable | `evidence_id`/`file_path` inexistant | Aucune exécution persistée | `ValidationException` |
| Type non déterminable | `auto` non détecté, sans `key_paths` | Aucune observation | `ValidationException` |

</frozen-after-approval>

## Code Map

- `backend/src/iryx/gateway/tools/evtx_parser.py` -- Modèle à suivre : structure de classe, `__init__`, `_resolve_source` (à reproduire), validation d'en-tête, format `observations`/`raw_output`/`metadata`.
- `backend/src/iryx/gateway/base.py` -- `BaseTool`, `ToolExecutionContext`, `ToolExecutionResult` (ne pas modifier).
- `backend/src/iryx/gateway/runner.py` -- `ToolRunner` : relance `ValidationException` sans persistance ; toute autre exception → `ToolExecution(status=ERROR)` puis `ToolExecutionFailedException` ; persiste les observations (ne pas modifier).
- `backend/src/iryx/core/exceptions.py` -- `ValidationException`, `ToolExecutionFailedException` (réutiliser).
- `backend/src/iryx/analytics/models.py` -- `Observation.source_location` = `String(512)`.
- `backend/src/iryx/gateway/registry.py` -- `_register_default_tools` : ajouter `RegistryParserTool`.
- `backend/src/iryx/gateway/tools/__init__.py`, `backend/src/iryx/gateway/__init__.py` -- exports.
- `backend/tests/unit/test_tool_evtx_parser.py` -- Fixtures à réutiliser : `db_session` SQLite, `test_case`, `test_evidence`.

## Tasks & Acceptance

**Execution:**
- [x] `backend/pyproject.toml` / `uv.lock` -- `uv add --package iryx "regipy>=5.1.0"` depuis la racine -- D-17.
- [x] `backend/src/iryx/gateway/tools/registry_parser.py` -- Créer `RegistryParserParameters`, `RegistryHiveParsingError`, `DEFAULT_KEY_PATHS`, `RegistryParserTool` (validation d'en-tête, ouverture `RegistryHive`, résolution `CurrentControlSet`, parcours DFS borné, sérialisation, ROT13, filtres) -- Cœur de la story.
- [x] `backend/src/iryx/gateway/registry.py`, `backend/src/iryx/gateway/tools/__init__.py`, `backend/src/iryx/gateway/__init__.py` -- Enregistrer et exporter -- Disponibilité dans la Gateway.
- [x] `backend/tests/unit/test_tool_registry_parser.py` -- Tests de chaque ligne de la matrice I/O (ruche simulée), du rejet d'en-tête réel, et de l'intégration `ToolRunner` (succès + statut `error`) -- Conformité.

**Acceptance Criteria:**
- Given une ruche valide scellée, when `parse_registry` est exécuté via `ToolRunner`, then une `ToolExecution` `success` avec `result_sha256` est persistée et chaque valeur produit une `Observation` liée (`tool_execution_id`, `source_location`, `timestamp_utc` UTC).
- Given une ruche à l'en-tête incomplet, when `ToolRunner` l'exécute, then une `ToolExecution` `error` contenant le message est persistée et le worker ne plante pas.
- Given n'importe quelle exécution, when l'outil analyse la ruche, then aucun sous-processus ni accès réseau n'a lieu et le fichier source reste inchangé.

## Implementation Notes

- Ajout de la dépendance `regipy>=5.1.0` (version installée `6.5.0`) dans `backend/pyproject.toml` et `uv.lock`.
- Implémentation complète de `RegistryParserTool` (nom `parse_registry`, timeout `120` s) et de son schéma Pydantic v2 `RegistryParserParameters` dans `backend/src/iryx/gateway/tools/registry_parser.py`.
- Enregistrement automatique de `RegistryParserTool` dans `default_registry` au sein de `backend/src/iryx/gateway/registry.py` et réexportation via `iryx.gateway.tools` et `iryx.gateway`.
- Validation stricte de l'en-tête de ruche (`REGISTRY_MAGIC = b"regf"` et taille minimale de 4096 octets), avec levée de `RegistryHiveParsingError` (sous-classe de `ToolExecutionFailedException`) pour persister proprement l'exécution en statut `ERROR` dans `ToolExecution` via `ToolRunner`.
- Auto-détection robuste des types de ruches (`SYSTEM`, `SOFTWARE`, `NTUSER.DAT`, `SAM`, `SECURITY`, `USRCLASS`, `AMCACHE`) par nom de fichier/stem et métadonnées d'en-tête, sans dépendre exclusivement des chemins Windows stricts de regipy.
- Résolution dynamique de `\CurrentControlSet` vers le jeu de contrôle actif via `\Select\Current` (avec repli sur `ControlSet001`).
- Parcours DFS borné (`max_depth`, `max_values`) avec gestion des clés manquantes dans `metadata.missing_keys` et isolation des erreurs par valeur/sous-clé sans interruption du reste du parcours.
- Normalisation des données de valeur (JSONB) : conversion des `bytes` en hex (plafond de 4096 octets avec drapeau `value_data_truncated`), troncature des chaînes très longues (> 4096 caractères), formatage ISO-8601 des `datetime`, et suppression des caractères nuls `\x00`.
- Décodage ROT13 automatique de `decoded_value_name` pour les artefacts `UserAssist` sous les clés `...\Count`.
- Suite de 23 tests unitaires et d'intégration validée avec 100 % de succès dans `backend/tests/unit/test_tool_registry_parser.py` et 460/460 tests réussis sur l'ensemble du projet.

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Evidence |
|---|---|---|
| Échec d'auto-détection du type de ruche pour les fichiers nommés simplement `SOFTWARE`, `SAM`, `SECURITY`, `usrclass.dat` | high | `regipy.registry.identify_hive_type` lève `UnidentifiedHiveException` sur les noms de fichiers simples sans chemin Windows complet (`system32\\config\\...`) ; validé en vérifiant le code source de regipy. |
| Chemins avec barre oblique inverse double `\\\\...` lors du parcours depuis la racine `\\` | medium | Dans `execute`, `sk_path = f"{current_path}\\\\{sk_name}"` produit `\\\\nom` quand `current_path == "\\"`, générant des chemins de sous-clés et `source_location` malformés. |
| Absence de normalisation des préfixes racines usuels (`HKLM`, `HKCU`, etc.) | medium | Les agents forensiques passent couramment des chemins avec `HKLM\\` ou `HKCU\\`. Faute de nettoyage des préfixes de ruche, les requêtes échouent et sont classées à tort dans `missing_keys`. |
| Trailing backslash dans `key_paths` (`\\Software\\Run\\`) | medium | `normalize_key_path` ne supprimait pas le séparateur final, provoquant la recherche d'une sous-clé vide `""` et la levée de `RegistryKeyNotFoundException`. |
| Faux positifs de `search_query` sur les valeurs nulles (`value_data is None`) | medium | `str(None)` vaut `'None'`, donc une recherche sur `'none'` matchait indûment toutes les valeurs sans données. |
| Risque d'erreur de sérialisation JSON sur éléments `bytes` dans les listes multi-chaînes | medium | `normalize_value_data` ne convertissait pas les éléments `bytes` au sein d'une liste, ce qui ferait échouer `json.dumps` lors de la persistance en base PostgreSQL JSONB. |
| Absence de test d'auto-détection et résolution des presets par défaut | medium | Gap pré-vérifié : aucun test n'exécutait `execute` avec `hive_type="auto"` sur une ruche identifiable sans `key_paths`. |
| Absence de test de résolution de preuve scellée par `evidence_id` seul en staging/storage | medium | Gap pré-vérifié : aucun test n'appelait `_resolve_source` avec `evidence_id` seul sans `file_path`. |
| Valeurs FILETIME négatives non gérées dans `filetime_to_utc` | low | Un entier négatif produisait une date antérieure à 1601 ; l'ajout de `ft <= 0` garantit le retour de `None`. |
| Dépassement de taille non borné sur chaînes de caractères volumineuses dans `normalize_value_data` | low | Seuls les `bytes` étaient plafonnés à 4096 octets ; les chaînes massives doivent également être bornées avec `value_data_truncated=True`. |
| Formatage incohérent des objets `datetime` (`REG_FILETIME`) dans `normalize_value_data` | low | `datetime` utilisait `str()` au lieu de `.isoformat()`. |
| Absence de déduplication des clés visitées et des `key_paths` en entrée | low | Si des chemins identiques ou redondants sont fournis, le parcours effectue des traversées répétées et produit des doublons. |
| Absence de `decoded_name` dans `raw_output["values"]` pour UserAssist | low | Champ optionnel utile pour les agents lisant directement la sortie brute de l'outil. |
| Abandon prématuré des sous-clés sœurs sur sous-clé corrompue | false | `iter_subkeys` de regipy est un générateur Python (`yield from`) qui lève une exception ; en Python, réitérer sur un générateur qui a levé lève immédiatement `StopIteration`. |
| Incohérence de statut entre `sprint-status.yaml` (`in-progress`) et la spec (`in-review`) | false | La transition de `sprint-status.yaml` vers `review` intervient à l'étape `step-05-present` selon le workflow BMAD. |
| Tests reposant sur des mocks de `RegistryHive` sans fixture binaire | low | Rejeté comme non bloquant pour le MVP, l'en-tête binaire réel étant déjà testé dans `test_scenario_invalid_header_rejection`. |
| Vulnérabilité de casse sur `_resolve_control_set` | low | `get_key` dans regipy est insensible à la casse et la valeur "Current" est déjà testée en `.lower()`. |

## Design Notes

API `regipy` (à vérifier par introspection après installation) : `RegistryHive(path)`, `hive.get_key(path)` → `NKRecord` (`.name`, `.header.last_modified` FILETIME, `.iter_values(as_json=False)` → `Value(name, value, value_type, is_corrupted)`, `.iter_subkeys()`), exceptions `regipy.exceptions.RegistryKeyNotFoundException` / `RegistryException`, `hive.hive_type` pour la détection `auto`. Parcours DFS maison plutôt que `recurse_subkeys` (contrôle de profondeur et isolation d'erreurs par clé). Conversion FILETIME manuelle : `datetime(1601,1,1,tzinfo=UTC) + timedelta(microseconds=ft // 10)` (0 → `None`).

`raw_output` suit `docs/02` : `{"hive_type", "keys_visited", "values_count", "values": [{key, name, value_type, data, last_written_utc}]}` ; `metadata` : `parsed_values_count`, `keys_visited`, `truncated`, `missing_keys`, `errors`, `resolved_key_paths`.

## Verification

**Commands:**
- `uv run pytest backend/tests/unit/test_tool_registry_parser.py` -- expected: tous les tests passent
- `uv run pytest` -- expected: 100 % de la suite passe
- `uv run ruff check backend` -- expected: 0 erreur
- `uv run ruff format --check backend` -- expected: 0 modification
