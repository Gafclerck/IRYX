---
title: "Story 4.3 : Analyseur de journaux d'événements Windows EVTX (python-evtx, FR12)"
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: '55cb8e462fea4deb5d92f7d0f35cb170486b7a64'
baseline_revision: '55cb8e462fea4deb5d92f7d0f35cb170486b7a64'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/docs/02-agents-et-outils.md'
  - '{project-root}/docs/03-modele-de-donnees.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les artefacts forensiques Windows au format binaire EVTX (`.evtx`) constituent la principale source d'investigation des activités système (authentifications, créations de processus, modifications de services), mais leur structure binaire propriétaire et compressée est inexploitable directement sans parseur spécialisé, tout en présentant un risque si des binaires tiers non audités ou dépendant du shell sont invoqués.

**Approach:** Implémenter l'analyseur forensique `EvtxParserTool` sous le nom d'outil enregistré `parse_evtx` en pur Python via la bibliothèque `python-evtx` (D-16), assurant la lecture sécurisée en lecture seule (`rb`), le filtrage sélectif par Event IDs, canaux et plages temporelles UTC, l'extraction structurée des métadonnées système (`System`) et données d'événement (`EventData` / `UserData`), la résilience aux enregistrements corrompus, et la production d'entités `Observation` normalisées prêtes à être persistées par `ToolRunner`.

## Boundaries & Constraints

**Always:**
- Respecter le nom d'outil autorisé `parse_evtx` défini dans `MVP_TOOL_WHITELIST` (`backend/src/iryx/gateway/registry.py`) et hériter de `BaseTool` (`backend/src/iryx/gateway/base.py`).
- Définir les paramètres d'entrée via le schéma Pydantic v2 `EvtxParserParameters` (`evidence_id`, `file_path`, `event_ids`, `channels`, `start_time`, `end_time`, `max_records`, `search_query`).
- Valider la présence d'au moins une source de données (`evidence_id` ou `file_path`) ; si `evidence_id` est fourni, résoudre le fichier physique scellé dans le répertoire d'ingestion (`{evidence_staging_path}/{evidence_id}.bin`) et vérifier son existence.
- Utiliser la bibliothèque pur Python `python-evtx` (`import Evtx.Evtx as evtx`) sans aucune dépendance binaire externe ni sous-processus système (`shell=False` strict).
- Ouvrir et lire les fichiers exclusivement en binaire lecture seule (`rb`), préservant strictement l'intégrité de la preuve source.
- Normaliser systématiquement l'horodatage de l'événement (`System.TimeCreated[@SystemTime]`) en `datetime` UTC (`astimezone(timezone.utc)`).
- Renseigner `Observation.source_location` sous la forme normalisée `record_id:{EventRecordID}` (ou `record_offset:{offset}` si l'ID d'enregistrement n'est pas disponible).
- Extraire dans `Observation.normalized_content` un dictionnaire structuré contenant : `event_id` (int), `record_id` (int), `channel` (str), `computer` (str), `provider_name` (str), `level` (int|None), `opcode` (int|None), `task` (int|None), `keywords` (str|None), `time_created_utc` (str ISO-8601), ainsi qu'un dictionnaire aplati `event_data` (contenant les paires clé/valeur extraites de `<EventData>` ou `<UserData>`).
- Supporter le filtrage en amont : ne conserver que les événements correspondant aux listes `event_ids` (si spécifiée), `channels` (si spécifiée), à la fenêtre temporelle `start_time` <= `timestamp` <= `end_time` (si spécifiée), et contenant `search_query` dans le contenu de l'événement (insensible à la casse, si spécifiée).
- Résilience aux fautes : intercepter les erreurs d'enregistrement corrompu ou illisible (`evtx.ParseException`, `evtx.InvalidRecordException`, `xml.etree.ElementTree.ParseError`) en consignant l'incident dans `metadata.errors` sans faire échouer l'analyse des enregistrements valides suivants.
- Borner l'extraction par défaut à `max_records = 5000` (valeur maximale autorisée : 50000) et positionner le drapeau `metadata["truncated"] = True` si le plafond est atteint.
- Ajouter la dépendance `python-evtx` dans `backend/pyproject.toml`.

**Never:**
- Jamais d'appel à `shell=True`, ni d'invocation de binaire système externe ou d'interpréteur de commandes (tout le parsing est 100% pur Python en mémoire).
- Jamais de modification, suppression ou écriture dans le fichier source analysé (`chmod 0440` en lecture seule préservé).
- Jamais d'interruption globale du traitement pour un enregistrement individuel malformé ou un bloc corrompu au sein d'un fichier EVTX par ailleurs lisible.
- Jamais de fuite d'horodatage local ou non typé : tous les horodatages générés doivent être strictement conscients du fuseau horaire UTC (`tzinfo=timezone.utc`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Journal EVTX nominal Security.evtx | Fichier EVTX valide contenant événements 4624 (Logon) et 4625 (Failed Logon) | Liste d'observations extraites avec `timestamp_utc` valide, `event_id=4624`, `source_location="record_id:..."`, `event_data` contenant `TargetUserName`, `LogonType`, etc. | N/A |
| Filtrage par Event IDs | Paramètre `event_ids=[4625, 4688]` fourni | Seuls les événements dont le champ `EventID` vaut 4625 ou 4688 sont extraits dans `observations` | N/A |
| Filtrage par plage temporelle | Paramètres `start_time` et `end_time` fournis en UTC | Seuls les événements dont `timestamp_utc` est inclus dans l'intervalle sont retenus | N/A |
| Recherche textuelle (`search_query`) | `search_query="powershell.exe"` | Seuls les événements mentionnant "powershell.exe" dans `EventData`, `Computer` ou le XML sont retenus | N/A |
| Enregistrement EVTX corrompu | Fichier contenant 1 bloc corrompu au milieu de 50 enregistrements valides | 49 observations extraites, 1 erreur tracée dans `metadata.errors`, statut global `success` | Tolérance aux fautes sans crash du parseur |
| Fichier EVTX tronqué ou invalide | Fichier d'en-tête non EVTX (octets aléatoires ou fichier texte) | `ValidationException` (422) signalant un format EVTX non reconnu ou corrompu dès l'en-tête | Lève `ValidationException` propre |
| Preuve ou fichier introuvable | `evidence_id` inexistant ou chemin `file_path` introuvable | Aucune exécution, levée de `ValidationException` ou `NotFoundException` (404) | Lève `ValidationException` ou `NotFoundException` |
| Fichier EVTX valide mais vide (0 enregistrement) | Fichier EVTX correctement initialisé sans aucun événement | Résultat avec `observations=[]`, `parsed_records_count=0`, statut `success` | N/A |
| Plafond max_records atteint | Fichier de 10 000 événements avec `max_records=500` | Exactement 500 observations extraites, `metadata.truncated=True`, statut `success` | N/A |

</frozen-after-approval>

## Code Map

- `backend/pyproject.toml` -- Déclaration de la dépendance de production `python-evtx>=0.7.4`
- `backend/src/iryx/gateway/tools/evtx_parser.py` -- Implémentation du parseur `EvtxParserTool`, du schéma `EvtxParserParameters`, du décodage XML et de la normalisation UTC
- `backend/src/iryx/gateway/tools/__init__.py` -- Export des symboles `EvtxParserTool` et `EvtxParserParameters`
- `backend/src/iryx/gateway/registry.py` -- Enregistrement de `EvtxParserTool` dans `default_registry` via `_register_default_tools`
- `backend/src/iryx/gateway/__init__.py` -- Exposition publique de `EvtxParserTool` et `EvtxParserParameters`
- `backend/src/iryx/gateway/base.py` -- Contrats de base `BaseTool`, `ToolExecutionContext` et `ToolExecutionResult` (réutilisation sans modification)
- `backend/src/iryx/gateway/runner.py` -- Moteur d'exécution sécurisé et persistance automatique des entités `Observation` (réutilisation sans modification)
- `backend/tests/unit/test_tool_evtx_parser.py` -- Suite complète de tests unitaires couvrant tous les scénarios de la matrice I/O, la résilience aux corruptions et l'intégration avec `ToolRunner`

## Tasks & Acceptance

**Execution:**
- [x] `backend/pyproject.toml` -- Ajouter `python-evtx>=0.7.4` dans les dépendances du projet et synchroniser l'environnement -- Intégrer la bibliothèque pur Python conforme à la décision D-16
- [x] `backend/src/iryx/gateway/tools/evtx_parser.py` -- Créer le module `evtx_parser.py` avec `EvtxParserParameters`, `EvtxParserTool`, l'extraction des blocs XML, le filtrage et la résilience aux enregistrements corrompus -- Réaliser l'analyseur forensique de journaux Windows
- [x] `backend/src/iryx/gateway/tools/__init__.py` -- Exporter `EvtxParserTool` et `EvtxParserParameters` -- Assurer la disponibilité dans le package des outils
- [x] `backend/src/iryx/gateway/registry.py` -- Enregistrer automatiquement `EvtxParserTool` dans `default_registry` -- Rendre l'outil disponible dans la Gateway
- [x] `backend/src/iryx/gateway/__init__.py` -- Exporter `EvtxParserTool` et `EvtxParserParameters` -- Assurer la visibilité au niveau du package gateway
- [x] `backend/tests/unit/test_tool_evtx_parser.py` -- Créer la suite de tests unitaires complète couvrant le parsing nominal, les filtres (event_ids, temporels, recherche), les fichiers vides, corrompus ou inexistants, et l'intégration avec `ToolRunner` -- Valider la conformité et la robustesse

**Acceptance Criteria:**
- Given un fichier journal Windows EVTX valide scellé dans les preuves, when `EvtxParserTool` est exécuté via `ToolRunner`, then chaque événement correspondant aux critères est analysé, son horodatage `TimeCreated` est converti en UTC dans `Observation.timestamp_utc`, son identifiant d'enregistrement figure dans `Observation.source_location`, et ses métadonnées structurées (`EventID`, `Channel`, `Computer`, `event_data`) sont insérées dans `Observation.normalized_content`.
- Given des paramètres de filtrage `event_ids=[4624, 4688]` ou une plage temporelle `[start_time, end_time]`, when `EvtxParserTool` s'exécute, then seuls les événements concordants sont retournés dans la liste des observations.
- Given un fichier EVTX contenant des enregistrements corrompus ou invalides, when `EvtxParserTool` est exécuté, then les erreurs sont tracées dans `metadata.errors` sans interruption du traitement des autres enregistrements valides.
- Given un accès au fichier de preuve, when `EvtxParserTool` effectue la lecture, then le fichier est ouvert en binaire lecture seule (`rb`) sans modification de la preuve source ni exécution d'aucune commande système (`shell=False`).
- Given un `evidence_id` inexistant ou un chemin non accessible, when l'analyse est lancée, then une `ValidationException` ou `NotFoundException` est levée sans persistance d'état incohérent.

## Implementation Notes

- Ajout de `python-evtx>=0.7.4` (`0.8.1`, dépendance transitive `hexdump`) dans `backend/pyproject.toml` et `uv.lock`, et implémentation de `EvtxParserTool` / `EvtxParserParameters` dans `backend/src/iryx/gateway/tools/evtx_parser.py` (nom `parse_evtx`, `timeout_seconds = 180`), enregistré dans `default_registry` et réexporté par `iryx.gateway` et `iryx.gateway.tools`.
- Lecture binaire lecture seule (`rb`) avec contrôle d'en-tête (`file_size >= 4096` et magic `ElfFile\x00`), sans aucun sous-processus shell (`shell=False`).
- Itération paresseuse sur les chunks et enregistrements (`_iter_records`) avec isolation des erreurs par chunk et par enregistrement dans `metadata.errors` et journalisation `logger.warning`.
- Extraction des métadonnées `System` dont `Execution` (`process_id`, `thread_id`), `Security` (`user_id`) et `Correlation` (`activity_id`), normalisation UTC de `TimeCreated`, et compteur par balise (`unnamed_counters`) pour les `<Data>` sans nom (`Data`, `Data_1`, ...).
- Restriction de `search_query` aux valeurs extraites (sans correspondance sur le balisage XML brut) et correction lors de la revérification d'une boucle infinie dans `_iter_records` (`iter()` + `break` après échec de `next()`) ainsi que sécurisation de `record.offset()`.

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Evidence |
|---|---|---|
| Collision des `<Data>` sans nom (`k.startswith("data_")` sensible à la casse) | medium | Corrigé par un compteur par nom de balise (`unnamed_counters`) ; validé par `test_evtx_unnamed_data_tags_collision_prevention`. |
| Évaluation anticipée `list(evtx_file.chunks())` interrompant le fichier sur un chunk corrompu | medium | Remplacé par une itération paresseuse chunk par chunk ; validé par `test_evtx_lazy_chunk_corruption_resilience`. |
| Contrôle de troncature d'en-tête à 8 octets au lieu de 4096 | low | Seuil porté à 4096 octets dans `_validate_evtx_header` ; validé par `test_evtx_truncated_header_under_4096_bytes`. |
| `_local_tag` plante sur des nœuds XML non-chaîne (commentaires / PI) | low | Garde `isinstance(tag, str)` ajoutée et testée par `test_local_tag_guard`. |
| Champs `<System>` `Execution`, `Security` et `Correlation` absents | medium | Extraction ajoutée pour `process_id`, `thread_id`, `user_id` et `activity_id` dans `normalized_content`. |
| Faux positifs de `search_query` sur le XML brut | medium | Recherche restreinte aux champs extraits (`computer`, `channel`, `provider_name`, `user_id`, `activity_id`, `event_data`). |
| Logger de module défini mais inutilisé | low | Ajout de `logger.warning` sur les chunks, décodages XML et enregistrements corrompus. |
| Incohérence de statut entre `sprint-status.yaml` (`in-progress`) et la spec (`in-review`) | false | La transition vers `review` dans `sprint-status.yaml` est effectuée à l'étape `step-05-present` selon le workflow. |
| Sections `Implementation Notes`, `Spec Change Log` et `Review Triage Log` vides dans la spec | false | Ces sections sont renseignées par le workflow à l'issue de la phase de revue. |
| Absence de fixture EVTX binaire réelle (tout est mocké) | medium | Partiellement corrigé : `test_evtx_empty_file_zero_records` exécute le vrai `python-evtx` sans mock ; l'ajout d'une fixture binaire avec enregistrements 4624/4625 est différé dans `deferred-work.md`. |
| Couverture manquante pour payloads Unicode et borne exacte `max_records` | low | Rejeté : comportement peu susceptible de diverger en usage courant et couvert côté troncature par `test_evtx_max_records_truncation`. |
| Duplication mémoire des observations dans `raw_output["events"]` | low | Rejeté : volume borné par `max_records`, et `raw_output` porte le résultat brut destiné au calcul SHA-256 (troncature LLM traitée en Story 4.7). |
| Exception à l'entrée du context manager `evtx.Evtx` non convertie | medium | Bloc `with evtx_obj as evtx_file:` englobé dans `try/except` et converti en `ValidationException`. |
| Exception ou attribut non appelable sur `record.offset()` | low | Encapsulé via `contextlib.suppress(Exception)` avec repli sur `0`. |
| Suffixe `z` minuscule non normalisé dans `_parse_event_timestamp` | low | Remplacement de `z` et `Z` par `+00:00` ajouté et vérifié par `test_parse_event_timestamp_normalization`. |
| Assertions manquantes sur `level`, `opcode`, `task` et `keywords` | low | Gap pré-vérifié (patch) : assertions ajoutées dans `test_evtx_nominal_parsing`. |
| Repli `record_offset:{offset}` sans `EventRecordID` non testé | low | Gap pré-vérifié (patch) : test `test_evtx_record_offset_fallback_when_no_record_id` ajouté. |
| Mock complet de `Evtx.Evtx` empêchant la vérification réelle de `python-evtx` | medium | Gap pré-vérifié (patch) : mock retiré de `test_evtx_empty_file_zero_records`. |
| Boucle infinie dans `_iter_records` introduite lors des correctifs (itération sur non-itérateur) | high | Corrigé lors de la revérification : `iter()` appliqué sur `chunks()` / `records()` et `break` après échec de `next()`. |

## Design Notes

L'implémentation de `EvtxParserTool` s'appuie sur le moteur `python-evtx` :
1. **Accès au fichier et validation :**
   - Résolution de la source soit via `evidence_id` (`{evidence_staging_path}/{id}.bin`), soit via `file_path`.
   - Vérification de l'existence du fichier et ouverture via `evtx.Evtx(path)`.
   - Vérification de l'en-tête du fichier (magic bytes `ElfFile\x00`) ; en cas de non-concordance, levée d'une `ValidationException`.
2. **Extraction et parsing XML :**
   - Itération sur les enregistrements avec `evtx_file.records()`.
   - Chaque enregistrement fournit une représentation XML via `record.xml()`.
   - Parsing sécurisé du fragment XML via `xml.etree.ElementTree.fromstring()`.
   - Extraction des balises de l'espace de noms Windows Event (`http://schemas.microsoft.com/win/2004/08/events/event`) en gérant l'absence d'espace de noms ou les espaces de noms personnalisés.
3. **Extraction de `System` et `EventData` :**
   - Balise `System` : `EventID`, `TimeCreated[@SystemTime]`, `EventRecordID`, `Computer`, `Channel`, `Provider[@Name]`, `Level`, `Task`, `Opcode`, `Keywords`.
   - Balises `EventData` / `UserData` : extraction de tous les éléments `<Data Name="clé">valeur</Data>` sous forme de dictionnaire clé-valeur.
4. **Normalisation temporelle UTC :**
   - La chaîne `SystemTime` (format ISO-8601 ex: `2026-11-24 16:00:00.123456Z` ou `2026-11-24T16:00:00.123456Z`) est analysée via `datetime.fromisoformat()` ou `parsedate_to_datetime()` et convertie en `UTC`.
5. **Tolérance aux pannes :**
   - Capture de `evtx.InvalidRecordException`, `evtx.ParseException`, `xml.etree.ElementTree.ParseError` par enregistrement individuel avec stockage du numéro de record et message d'erreur dans la liste `errors`.

## Verification

**Commands:**
- `uv run pytest backend/tests/unit/test_tool_evtx_parser.py` -- expected: Tous les tests unitaires de EvtxParserTool passent avec succès
- `uv run pytest backend/tests/unit/test_tool_gateway_runner.py` -- expected: Aucun impact négatif ni régression sur ToolRunner
- `uv run pytest` -- expected: 100% des tests de la suite passent
- `uv run ruff check backend` -- expected: 0 erreur, 0 avertissement
- `uv run ruff format --check backend` -- expected: 0 modification nécessaire
