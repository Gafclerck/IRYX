---
title: "Story 4.2 : Analyseur de logs texte et CSV avec normalisation des horodatages UTC"
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: 'fcbd2bd6c4cf19d884dcad3eabbda5a977ec16b9'
baseline_revision: 'fcbd2bd6c4cf19d884dcad3eabbda5a977ec16b9'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/docs/02-agents-et-outils.md'
  - '{project-root}/docs/03-modele-de-donnees.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les preuves numériques collectées lors d'incidents contiennent fréquemment des journaux textuels et tabulaires (fichiers CSV/TSV, journaux système Syslog RFC 3164/5424, journaux de serveurs web Apache/Nginx CLF/Combined, JSON Lines, ou paires clé-valeur) comportant des syntaxes hétérogènes et des horodatages locaux disparates, rendant impossible la corrélation temporelle directe et l'analyse automatisée par les agents IA sans prétraitement déterministe.

**Approach:** Implémenter l'analyseur forensique `LogCsvParserTool` sous le nom d'outil autorisé `parse_text_logs` dérivé de `BaseTool`, assurant la détection automatique du format (ou application d'un préréglage explicite/regex personnalisée), le découpage ligne à ligne robuste sans recours au shell (`shell=False`), la tolérance aux lignes malformées, la normalisation systématique des horodatages vers `datetime` UTC, et la génération de dictionnaires normalisés prêts à être persistés dans les entités `Observation` via `ToolRunner`.

## Boundaries & Constraints

**Always:**
- Respecter le nom d'outil `parse_text_logs` figurant dans `MVP_TOOL_WHITELIST` (`backend/src/iryx/gateway/registry.py`) et hériter de `BaseTool` (`backend/src/iryx/gateway/base.py`).
- Définir les paramètres d'entrée via le schéma Pydantic v2 `LogCsvParserParameters` (`evidence_id`, `file_path`, `content`, `format_preset`, `delimiter`, `custom_regex`, `timestamp_field`, `timestamp_format`, `max_records`, `encoding`).
- Valider la présence d'au moins une source de données (`evidence_id`, `file_path` ou `content`) ; si `evidence_id` est fourni, résoudre le chemin physique scellé dans le répertoire d'ingestion (`{evidence_staging_path}/{evidence_id}.bin`) et vérifier son existence.
- Supporter les préréglages de formats forensiques courants : `auto`, `csv`, `tsv`, `syslog` (RFC 3164 BSD et RFC 5424), `apache_combined` (CLF étendu Nginx/Apache), `clf` (Common Log Format), `json_lines` (ndjson/jsonl), `key_value` (firewall/WAF) et `custom_regex`.
- Convertir tout horodatage identifié en objet `datetime` avec fuseau horaire `UTC` (`datetime.now(UTC)` ou conversion `astimezone(UTC)`). Si l'année est absente (ex: Syslog BSD), inférer l'année courante ou UTC par défaut.
- Traiter les lignes corrompues, tronquées ou inintelligibles avec tolérance : consigner un avertissement structuré dans les métadonnées/erreurs sans interrompre l'analyse des lignes valides suivantes.
- Respecter le principe de sécurité passive : manipuler les données comme du texte inerte sans jamais invoquer de shell système (`shell=False` strict) ni interpréter de caractères d'échappement.
- Pour chaque événement extrait, produire un dictionnaire dans `observations` avec les clés attendues par `ToolRunner` : `timestamp_utc`, `source_location` (ex: `line:{n}`), `source_id` (l'identifiant de la preuve), et `normalized_content` (champs structurés : `ip`, `method`, `status`, `message`, `raw_line`, etc.).
- Borner le traitement par défaut à `max_records = 5000` (bornable jusqu'à 50000) et respecter la temporisation `timeout_seconds = 60`.

**Never:**
- Jamais d'appel à `shell=True`, ni d'exécution de commande externe ou de sous-processus système pour le parsing textuel (pur Python standard `csv`, `re`, `json`, `datetime`).
- Jamais de modification ou d'écriture dans le fichier de preuve source (`chmod 0440` en lecture seule préservé).
- Jamais d'interruption globale du traitement pour une simple ligne malformée ou un horodatage non reconnu.
- Jamais d'appel réseau sortant lors du parsing (`network_mode: none`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Journal CSV nominal | Fichier CSV avec en-têtes (`timestamp,ip,action,status`) | Liste d'observations extraites, `timestamp_utc` converti en UTC, `normalized_content` renseigné | N/A |
| Journal Web Nginx/Apache | Lignes format Combined Log Format (`192.168.1.10 - admin [24/Nov/2026:08:14:53 +0000] "GET /api HTTP/1.1" 200 ...`) | Observations avec `timestamp_utc`, `ip`, `method="GET"`, `path="/api"`, `status_code=200` | Lignes invalides ignorées avec trace d'erreur |
| Journal Syslog RFC 3164 / 5424 | Lignes Syslog (`Nov 24 08:14:53 srv-auth sshd[1234]: Accepted publickey...`) | Observations avec `timestamp_utc` en UTC, `hostname="srv-auth"`, `appname="sshd"`, `pid="1234"` | N/A |
| Journal JSON Lines | Fichier ndjson avec objets contenant `@timestamp` ou `time` | Observations normalisées avec tous les champs JSONB sous `normalized_content` | Lignes JSON non valides consignées dans `errors` |
| Regex personnalisé | Format exotique fourni avec `custom_regex` à groupes nommés `(?P<timestamp>...)(?P<msg>...)` | Extraction conforme aux groupes nommés avec conversion UTC du groupe timestamp | Expression invalide signalée par `ValidationException` (422) |
| Lignes corrompues / syntaxe erronée | Fichier avec 3 lignes corrompues au milieu de 100 lignes valides | 97 observations extraites, 3 erreurs consignées dans `metadata.errors`, statut global `success` | Tolérance aux fautes sans crash |
| Tentative d'injection de commande | Log contenant `; rm -rf /` ou `$(whoami)` | Chaîne traitée littéralement comme donnée texte passive sans exécution shell | N/A |
| Preuve ou fichier introuvable | `evidence_id` inexistant ou chemin `file_path` non accessible | Aucune exécution, exception levée | Lève `ValidationException` ou `NotFoundException` (404) |
| Fichier vide | Contenu de 0 octets | Résultat avec 0 observations, `parsed_records_count = 0`, statut `success` | N/A |

</frozen-after-approval>

## Code Map

- `backend/src/iryx/gateway/tools/__init__.py` -- Package des analyseurs forensiques concrets et exports
- `backend/src/iryx/gateway/tools/log_parser.py` -- Implémentation de `LogCsvParserTool`, schéma Pydantic `LogCsvParserParameters` et parseurs de formats
- `backend/src/iryx/gateway/registry.py` -- Enregistrement de `LogCsvParserTool` dans le registre par défaut `default_registry`
- `backend/src/iryx/gateway/__init__.py` -- Exposition publique de `LogCsvParserTool` et `LogCsvParserParameters`
- `backend/src/iryx/gateway/base.py` -- Réutilisation des contrats `BaseTool`, `ToolExecutionContext` et `ToolExecutionResult` (ne pas modifier)
- `backend/src/iryx/gateway/runner.py` -- Moteur d'exécution sécurisé et persistance automatique des entités `Observation` (ne pas modifier)
- `backend/src/iryx/analytics/models.py` -- Modèle relationnel `Observation` (ne pas modifier)
- `backend/tests/unit/test_tool_log_parser.py` -- Tests unitaires complets de l'analyseur de logs (CSV, Syslog, Web, JSONL, Key-Value, regex, résilience et injection)

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/gateway/tools/__init__.py` -- Créer le package `iryx.gateway.tools` et exporter les analyseurs disponibles -- Structurer l'arborescence des outils
- [x] `backend/src/iryx/gateway/tools/log_parser.py` -- Implémenter `LogCsvParserTool`, les fonctions de détection, les extracteurs de formats (`csv`, `syslog`, `apache`, `jsonl`, `key_value`, `regex`) et la conversion UTC -- Réaliser l'analyseur forensique de logs et CSV
- [x] `backend/src/iryx/gateway/registry.py` -- Enregistrer automatiquement une instance de `LogCsvParserTool` dans `default_registry` -- Mettre l'outil à disposition immédiate de la Gateway
- [x] `backend/src/iryx/gateway/__init__.py` -- Exporter `LogCsvParserTool` et `LogCsvParserParameters` -- Assurer la disponibilité publique dans le module gateway
- [x] `backend/tests/unit/test_tool_log_parser.py` -- Développer la suite de tests unitaires couvrant l'ensemble des scénarios de la matrice I/O et l'intégration avec `ToolRunner` -- Valider la conformité et la robustesse

**Acceptance Criteria:**
- Given un fichier journal CSV ou texte avec horodatages valides, when `LogCsvParserTool` est exécuté via `ToolRunner`, then chaque ligne est analysée, ses horodatages sont convertis en UTC dans `Observation.timestamp_utc`, ses attributs structurés sont insérés dans `Observation.normalized_content`, et sa position de ligne est consignée dans `Observation.source_location`.
- Given un fichier contenant des lignes corrompues ou des horodatages inintelligibles, when `LogCsvParserTool` est exécuté, then les lignes corrompues sont ignorées ou inscrites dans le rapport d'erreurs sans faire échouer l'analyse du reste du document.
- Given une entrée contenant des métacaractères shell ou des tentatives d'injection de code, when `LogCsvParserTool` procède au découpage, then les données sont traitées de façon passive en pur Python sans aucune transmission à un interpréteur système.
- Given une preuve inexistante sur le disque, when l'analyse est lancée avec cet `evidence_id`, then une exception explicite `ValidationException` ou `NotFoundException` est retournée sans état orphelin en base.

## Implementation Notes

- Création du package `backend/src/iryx/gateway/tools/__init__.py` et implémentation de `LogCsvParserTool` et `LogCsvParserParameters` dans `backend/src/iryx/gateway/tools/log_parser.py`.
- Enregistrement systématique de `LogCsvParserTool` dans `default_registry` et exposition publique dans `backend/src/iryx/gateway/__init__.py`.
- Normalisation robuste des dates vers UTC sans dépendance de locale (`ENGLISH_MONTHS` mapping pour formats Syslog BSD et CLF).
- Protection contre l'interprétation d'entiers courts (codes HTTP 200, 404, IDs) ou de booléens comme horodatages epoch 1970.
- Tolérance aux fautes : consignation des lignes corrompues dans `metadata.errors` sans interruption du parsing global.
- Intégration complète avec `ToolRunner` : calcul automatique du SHA-256 du résultat brut et persistance des entités `Observation` dans PostgreSQL / SQLite de test.

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Evidence |
|---|---|---|
| Boolean value parsed as epoch timestamp (1970-01-01) in `parse_timestamp_to_utc` | medium | `isinstance(True, int)` est vrai en Python; ajout d'un garde explicite `isinstance(value, bool): return None`. |
| Short integer strings (HTTP status codes 200/404, IDs) parsed as 1970 Unix epoch | medium | `re.match(r"^\d+(\.\d+)?$")` matchait les petits entiers; restriction de la plage epoch plausible aux années 1980 à 2100. |
| CSV column timestamp inference picking numeric ID as timestamp | medium | Résolu par la restriction de la plage epoch plausible ci-dessus. |
| Fallback candidate timestamp keys skipped when earlier candidate is null in JSON lines | medium | Remplacement du test de présence de clé `cand in normalized` par `normalized.get(cand) is not None and != ""` pour permettre le repli. |
| Time component lost for space-separated datetimes in generic parser | medium | `words = line.split()` séparait date et heure; ajout de `GENERIC_DATETIME_REGEX` pour capturer le motif complet avant découpage. |
| Unverified ToolExecutionResult `raw_output` contract | low | Tests unitaires enrichis avec validation explicite des clés de premier niveau et de la structure de `raw_output["records"]`. |
| Unverified `max_records` truncation and limit enforcement | low | Test unitaire ajouté vérifiant la troncature stricte et la présence du drapeau `metadata["truncated"]`. |
| Unverified custom `timestamp_field` and `timestamp_format` | low | Test unitaire ajouté vérifiant l'extraction avec champ personnalisé et directive strptime spécifique. |
| Unverified `tsv` preset and custom `delimiter` parameter | low | Test unitaire ajouté pour `format_preset="tsv"` et séparateurs point-virgule. |
| Unverified fallback `generic` log parser | low | Test unitaire ajouté vérifiant le comportement sur journaux non structurés avec adresses IP et dates. |
| Unused `test_evidence` fixture and missing `source_id` foreign key check | low | Test d'intégration `ToolRunner` mis à jour pour lier explicitement `test_evidence.id`. |
| Arbitrary host file reading via `file_path` | false | `file_path` est un paramètre technique utilisé par les pipelines et confiné au conteneur non-root (`network_mode: none`, `cap_drop: ALL`). |
| Unbounded memory consumption on large forensic log files | low | Les fichiers de preuves sont bornés à `max_evidence_size_gb` et les observations à `max_records` (5000 par défaut). |
| Locale dependency when parsing English month names (`%b`) in Syslog and CLF | medium | `strptime(%b)` dépend de la locale C du système; implémentation d'une table de correspondance anglaise statique déterministe. |
| Desynchronized CSV line numbers on multiline fields | low | `_parse_csv` gère les lignes tabulaires avec localisation `line:{n}` conforme aux spécifications. |
| Default CSV `field_size_limit` overflow on large fields | low | Risque théorique minime en MVP; les enregistrements textuels standards restent sous la limite de 128 Ko. |
| Single-element limitation and unparsed Structured Data in RFC 5424 | low | La spécification exige l'extraction du message brut et des champs normés dans `Observation.normalized_content`; le bloc standard est préservé. |
| Syslog RFC 3164 field corruption when hostnames are omitted | low | Prise en charge des formats BSD standards; les cas exotiques sans hostname sont orientés vers le parseur générique. |
| Missing Syslog Facility and Severity decoding from PRI | low | Décodage de `facility` (`pri >> 3`) et `severity` (`pri & 7`) ajouté aux champs normalisés. |
| Missing UTF-8 Byte Order Mark (BOM) stripping | low | Ajout du nettoyage `.lstrip("\ufeff")` au chargement du texte brut. |
| Unescaped quotes in Key-Value logs | low | Dé-échappement des guillemets `\"` et `\'` intégré dans `_parse_key_value`. |
| Missing truncation flag in execution metadata | low | Ajout du booléen `truncated` dans les métadonnées de sortie de tous les parseurs. |

## Design Notes

L'architecture du parseur de logs s'articule autour de modules de normalisation légers et purs Python :
1. **Résolution de source** : Accepte soit `content` direct (chaîne mémoire), soit `file_path`, soit `evidence_id` (résolu via `evidence_staging_path/{id}.bin`).
2. **Détection de format** :
   - Inspecte les 10 premières lignes non vides.
   - Si les lignes débutent par `{` et se terminent par `}`, oriente vers `json_lines`.
   - Si les lignes concordent avec les expressions régulières CLF/Combined Log Format, oriente vers `apache_combined`.
   - Si les lignes correspondent au motif Syslog (`Mois JJ HH:MM:SS` ou `<PRI>version`), oriente vers `syslog`.
   - Si un séparateur régulier (virgule, tabulation, point-virgule) est détecté de façon cohérente, oriente vers `csv`.
   - Sinon, applique une extraction générique ligne par ligne avec recherche d'horodatage par expressions régulières standard.
3. **Normalisation temporelle** :
   - Prise en charge des formats ISO-8601, RFC 3339, format CLF (`24/Nov/2026:08:14:53 +0000`), Syslog BSD (`Nov 24 08:14:53`), timestamps Epoch Unix (secondes et millisecondes).
   - Tout objet retourné est converti explicitement en `datetime` UTC via `dt.astimezone(datetime.timezone.utc)`.

## Verification

**Commands:**
- `uv run pytest backend/tests/unit/test_tool_log_parser.py` -- expected: Tous les tests unitaires de LogCsvParserTool passent avec succès
- `uv run pytest backend/tests/unit/test_tool_gateway_runner.py` -- expected: Pas de régression sur ToolRunner
- `uv run pytest` -- expected: 100% des tests de la suite passent
- `uv run ruff check backend` -- expected: 0 erreur, 0 avertissement
- `uv run ruff format --check backend` -- expected: 0 modification nécessaire
