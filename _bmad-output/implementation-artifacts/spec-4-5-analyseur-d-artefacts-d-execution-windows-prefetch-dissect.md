---
title: "Story 4.5 : Analyseur d'artefacts d'exécution Windows Prefetch (dissect, FR14)"
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: '8e3257ce536ea3b730574956e8402ee528b68c79'
baseline_revision: '8e3257ce536ea3b730574956e8402ee528b68c79'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/docs/02-agents-et-outils.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les fichiers Prefetch (`.pf`) constituent une preuve d'exécution forensique essentielle sous Windows (nom de binaire, compteur d'exécutions, horodatages précis, fichiers chargés), mais leur compression propriétaire (`MAM`) et structures binaires (`SCCA` v17 à v31) ne peuvent pas être décodées de façon sécurisée sans analyseur dédié.

**Approach:** Implémenter `PrefetchParserTool` (nom enregistré `parse_execution`, timeout 120 s) en pur Python via `dissect` (D-18) pour décompresser et parser les fichiers `.pf`, normaliser chaque exécution horodatée en entité `Observation` UTC liée au dossier et tracer les échecs dans `ToolExecution`.

## Boundaries & Constraints

**Always:**
- Hériter de `BaseTool`, nom `parse_execution` (déjà dans `MVP_TOOL_WHITELIST`), timeout 120 s, schéma Pydantic v2 `PrefetchParserParameters` (`extra="forbid"`) : `evidence_id`, `file_path`, `artifact_type` (valeur autorisée `"prefetch"`), `executable_name` (filtre optionnel insensible à la casse), `search_query` (filtre optionnel insensible à la casse), `max_results` (1 à 50 000, défaut 5000).
- Au moins une source (`evidence_id` ou `file_path`) ; résolution de la source via `_resolve_source` supportant fichier individuel (`.pf`) ou répertoire de fichiers Prefetch ; source introuvable → `ValidationException` (HTTP 422, aucune persistance).
- Validation stricte de l'en-tête binaire : fichier >= 8 octets, signature `b"MAM\x04"` (ou `b"MAM"` sur les 3 premiers octets) pour les fichiers compressés, ou signature `b"SCCA"` à l'offset 4 pour les fichiers non compressés ; en cas d'en-tête invalide ou corrompu, levée de `PrefetchParsingError` (sous-classe de `ToolExecutionFailedException`) afin que `ToolRunner` persiste `status="error"` avec le message détaillé.
- Pour chaque exécution horodatée valide (jusqu'à 8 horodatages d'exécution : `latest_timestamp` + `previous_timestamps` non nuls), création d'une `Observation` : `source_location` = chemin ou nom du fichier `.pf` (<= 512 car.), `timestamp_utc` = horodatage d'exécution converti en UTC aware, `normalized_content` = dictionnaire complet (`tool_name="dissect.prefetch"`, `executable_name`, `prefetch_hash`, `run_count`, `execution_index`, `timestamp_utc`, `all_execution_timestamps_utc`, `volumes`, `loaded_files_count`, `loaded_files`, `loaded_files_truncated`).
- Assainissement strict des chemins de fichiers et volumes : suppression des caractères nuls `\x00`, normalisation anti-traversée de répertoire (`..`), limitation de la liste des fichiers dépendants (plafond à 1000 avec drapeau `loaded_files_truncated=True`).
- Sortie structurée `raw_output` conforme à `docs/02` : `{"artifact_type": "prefetch", "files_analyzed": int, "total_executions": int, "executions": [...]}`.
- Dépendance `dissect>=3.13.0` déclarée dans `backend/pyproject.toml` (+ mise à jour de `uv.lock`).

**Never:**
- Aucun sous-processus shell ni binaire externe (`shell=False` strict, pur Python).
- Aucun accès réseau ni transmission de données hors de l'instance locale.
- Aucune modification ni écriture sur les fichiers de preuves analysés (lecture seule stricte).
- Aucun horodatage naïf non converti en UTC.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Prefetch Win10 nominal | Fichier `.pf` valide Win10 (v30, MAM), 3 exécutions | 3 observations créées, chacune avec son `timestamp_utc` UTC, `run_count=3`, `volumes` et `loaded_files` assainis | N/A |
| Prefetch non compressé SCCA | Fichier `.pf` Win7 (v23, sans MAM, magic SCCA) | Observations créées avec `run_count` et horodatages extraits | N/A |
| Répertoire Prefetch | Répertoire contenant 10 fichiers `.pf` | Analyse itérative de tous les fichiers `.pf`, agrégation des observations | Erreurs sur fichiers isolés consignées dans `metadata.errors` sans faire échouer les autres |
| Filtre executable_name | Fichier `.pf` pour `NOTEPAD.EXE`, filtre `executable_name="calc.exe"` | 0 observation générée, `files_analyzed=1`, `total_executions=0` | N/A |
| Dépendances volumineuses | Prefetch référençant 1 500 DLLs | Liste plafonnée à 1 000 fichiers, `loaded_files_truncated=True` | N/A |
| En-tête invalide / Corrompu | Fichier texte ou binaire sans magic MAM/SCCA | `ToolExecution.status="error"`, message capturé | `ToolExecutionFailedException` via `ToolRunner` |
| Fichier vide (< 8 octets) | Fichier de 0 ou 4 octets | `ToolExecution.status="error"`, message d'erreur clair | `PrefetchParsingError` capturé par `ToolRunner` |
| Source introuvable | `evidence_id` ou `file_path` inexistant | Aucune trace persistée en base | `ValidationException` |

</frozen-after-approval>

## Code Map

- `backend/src/iryx/gateway/tools/prefetch_parser.py` -- Nouveau module : `PrefetchParserParameters`, `PrefetchParsingError`, fonctions d'assainissement de chemins, extraction des volumes et métriques, et classe `PrefetchParserTool`.
- `backend/src/iryx/gateway/tools/registry_parser.py` -- Modèle de référence pour `_resolve_source`, gestion des exceptions `ToolExecutionFailedException` et structure de retour `ToolExecutionResult`.
- `backend/src/iryx/gateway/base.py` -- `BaseTool`, `ToolExecutionContext`, `ToolExecutionResult` (à réutiliser sans modification).
- `backend/src/iryx/gateway/runner.py` -- Moteur d'exécution, calcul d'empreinte SHA-256 et persistance `ToolExecution` / `Observation` (à réutiliser sans modification).
- `backend/src/iryx/gateway/registry.py` -- `MVP_TOOL_WHITELIST` (contient déjà `parse_execution`), enregistrement de `PrefetchParserTool` dans `_register_default_tools`.
- `backend/src/iryx/gateway/tools/__init__.py` et `backend/src/iryx/gateway/__init__.py` -- Exports publics de l'outil et de ses schémas.
- `backend/tests/unit/test_tool_prefetch_parser.py` -- Tests unitaires exhaustifs couvrant la matrice I/O, le rejet d'en-tête invalide et l'intégration `ToolRunner`.

## Tasks & Acceptance

**Execution:**
- [x] `backend/pyproject.toml` / `uv.lock` -- Ajouter `dissect>=3.13.0` aux dépendances du backend via `uv add --package iryx "dissect>=3.13.0"` -- D-18.
- [x] `backend/src/iryx/gateway/tools/prefetch_parser.py` -- Implémenter `PrefetchParserParameters`, `PrefetchParsingError`, fonctions d'assainissement de chemins, extraction des volumes et métriques, et classe `PrefetchParserTool` (nom `parse_execution`, timeout 120 s) -- Cœur de la story.
- [x] `backend/src/iryx/gateway/registry.py`, `backend/src/iryx/gateway/tools/__init__.py`, `backend/src/iryx/gateway/__init__.py` -- Enregistrer `PrefetchParserTool` dans le registre par défaut et exporter les symboles -- Intégration Gateway.
- [x] `backend/tests/unit/test_tool_prefetch_parser.py` -- Créer la suite de tests unitaires couvrant les fichiers MAM et SCCA valides, le parsing de répertoires, les filtres, la troncature de dépendances, le rejet d'en-tête invalide et l'intégration avec `ToolRunner` (succès et statut d'erreur) -- Conformité et non-régression.

**Acceptance Criteria:**
- Given un ou plusieurs fichiers `.pf` valides ingérés dans un dossier d'enquête, when l'outil `parse_execution` est exécuté via `ToolRunner`, then une `ToolExecution` de statut `success` avec `result_sha256` est persistée et chaque exécution antérieure enregistrée génère une entité `Observation` avec son horodatage UTC, le nom de l'exécutable, le hash de chemin, le compteur d'exécutions, ainsi que les volumes et fichiers chargés assainis.
- Given un fichier non valide (signature `MAM` ou `SCCA` absente ou fichier tronqué), when l'outil tente son analyse via `ToolRunner`, then une `ToolExecution` de statut `error` est persistée en base avec le message d'erreur et une exception `ToolExecutionFailedException` est levée sans planter le worker.
- Given n'importe quelle invocation, when l'outil analyse les preuves, then l'exécution s'effectue en pur Python (`shell=False`), sans sous-processus externe ni requête réseau, et les fichiers sources restent intacts.

## Implementation Notes

- Ajout de la dépendance `dissect>=3.13.0` (version installée `3.19.0`) dans `backend/pyproject.toml` et `uv.lock`.
- Implémentation complète de `PrefetchParserTool` (nom `parse_execution`, timeout `120` s) et de son schéma Pydantic v2 `PrefetchParserParameters` dans `backend/src/iryx/gateway/tools/prefetch_parser.py`.
- Enregistrement automatique de `PrefetchParserTool` dans `default_registry` au sein de `backend/src/iryx/gateway/registry.py` et réexportation via `iryx.gateway.tools` et `iryx.gateway`.
- Validation stricte de l'en-tête Prefetch (taille >= 8 octets, signature compressée `b"MAM"` ou non compressée `b"SCCA"` à l'offset 4), avec levée de `PrefetchParsingError` (sous-classe de `ToolExecutionFailedException`) permettant à `ToolRunner` de persister le statut `ERROR` dans `ToolExecution`.
- Décompression automatique transparente des fichiers compressés MAM via `lzxpress_huffman.decompress`.
- Extraction des volumes et des numéros de série selon la version (17 ou 30), et normalisation de chaque exécution horodatée (jusqu'à 8 timestamps) en entités `Observation` complètes avec horodatages UTC.
- Assainissement anti-traversée de répertoire des chemins référencés et limitation de la liste des dépendances à 1 000 entrées (`loaded_files_truncated=True`).
- Support des répertoires de fichiers Prefetch avec isolation des erreurs individuelles dans `metadata.errors`.
- Suite de 18 tests unitaires validée avec 100 % de succès dans `backend/tests/unit/test_tool_prefetch_parser.py` et 478/478 tests réussis sur l'ensemble du projet sans aucune régression.

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Evidence |
|---|---|---|
| Absence de tests de résolution de source par `evidence_id` seul en staging/storage | medium | Gap pré-vérifié par le reviewer de vérification : aucun test n'appelait `execute` ou `ToolRunner` avec `evidence_id` sans `file_path`. Corrigé avec deux tests unitaires dédiés. |
| Absence d'assertions sur `loaded_files`, `loaded_files_count` et `creation_time_utc` dans les observations | low | Gap pré-vérifié par le reviewer de vérification : les champs étaient présents dans `normalized_content` mais omis des assertions de `test_nominal_win10_mam_prefetch`. Corrigé avec assertions explicites. |
| Remplacement global des octets nuls plutôt que terminaison sur premier octet nul | medium | Dans `_parse_single_file`, `.replace("\x00", "")` risquait de concaténer des données résiduelles après le premier octet nul d'une chaîne fixe de 60 octets. Corrigé avec `.split("\x00")[0]`. |
| Fallback du nom d'exécutable tronquant les binaires contenant des tirets (`.split("-")[0]`) | medium | Un binaire tel que `docker-compose.exe-12345678.pf` était tronqué en `"docker"`. Corrigé en utilisant `rsplit("-", 1)[0]`. |
| Filtrage asymétrique du nom d'exécutable avec ou sans extension `.exe` | medium | `_matches_executable_filter` ne gérait pas symétriquement la comparaison par stem quand l'un avait `.exe` et l'autre non. Corrigé avec comparaison symétrique `Path(f_name).stem.lower() == Path(e).stem.lower()`. |
| Absence de validation de la taille décompressée MAM dans l'en-tête (risque de bombe mémoire) | medium | L'en-tête MAM spécifie la taille décompressée à l'offset 4; un contrôle de borne (≤ 100 Mo) a été intégré avant décompression. |
| Position du descripteur de fichier non restaurée après seek dans `extract_volumes` | low | `scca.fh.tell()` était lu mais le pointeur n'était pas restauré dans un bloc `finally`. Corrigé avec restauration systématique du seek initial. |
| Numéros de série de volumes et horodatages omis dans `search_query` | low | `_matches_search_filter` omettait `serial_number` et `creation_time_utc`, limitant les pivots d'investigation. Corrigé en intégrant les champs de volumes. |
| Heuristique de détection de chemin de volume acceptant des octets arbitraires | low | Vérification ajoutée pour s'assurer que les chemins de périphériques décodés respectent les préfixes Windows valides (`\Device\`, `\Volume{`, etc.). |
| Taille fixe de structure de volume pour Windows 7 / Vista Prefetch | low | Calcul dynamique du stride de volume basé sur `volumes_information_size // number_of_volumes` lorsque disponible. |
| Décompte total d'exécutions dans `metadata` | low | Comportement conforme aux analyseurs EVTX et Registre; `truncated=True` indique si le plafond a été atteint. Rejeté comme non bloquant. |
| Fichiers Prefetch avec horodatages nuls omis de la sortie d'exécution | low | Cas exceptionnel d'artefact entièrement corrompu; rejeté car aucune observation horodatée ne peut être générée sans date d'exécution valide. |
| Absence de décompression MAM réelle sans mock | low | Décompression mockée dans les tests unitaires pour simuler des flux SCCA synthétiques. Recommandation consignée dans `deferred-work.md` pour fixture d'intégration. |
| Désynchronisation du statut de sprint dans `sprint-status.yaml` | false | La transition de `sprint-status.yaml` vers `review` s'effectue à l'étape `step-05-present` selon l'architecture séquentielle BMAD. |
| Duplication des dépendances entre observations d'un même fichier | false | Exigence explicite des critères d'acceptation de la story (chaque observation horodatée porte la liste de ses dépendances pour analyse isolée). |

## Design Notes

L'outil exploite `dissect.cstruct` et les structures de `dissect.target.plugins.os.windows.prefetch` (`PREFETCH_HEADER`, `prefetch_version_structs`, `lzxpress_huffman`, `wintimestamp`).
Décompression automatique si présence du magic MAM (`b"MAM\x04"` ou `b"MAM"`).
Extraction du hash Prefetch depuis `header.hash` sous forme hexadécimale formatée (`f"{header.hash:08X}"`).
Extraction des volumes à partir de `VOLUME_INFORMATION_17` ou `VOLUME_INFORMATION_30` selon la version, et normalisation des chemins de dépendance (`metrics`) avec suppression des `\x00` et résolution sécurisée sans traversée de répertoire.

## Verification

**Commands:**
- `uv run pytest backend/tests/unit/test_tool_prefetch_parser.py` -- expected: tous les tests passent
- `uv run pytest` -- expected: 100 % de la suite de tests du projet passe
- `uv run ruff check backend` -- expected: 0 erreur
- `uv run ruff format --check backend` -- expected: 0 modification
