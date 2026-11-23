# 02 - Agents et Outils : Rôles, Registre et Gateway
 
---
 
## 1. Rôles d'agents
 
L'investigation assistée repose sur six rôles d'agents spécialisés. Chaque rôle est soumis à un contrat d'exécution strict :
 
| Rôle | Ce qu'il fait | Outils autorisés | Ce qu'il ne fait jamais |
|---|---|---|---|
| **Planner** | Analyse la demande initiale du dossier et l'inventaire des preuves disponibles. Propose un plan structuré de 4 à 8 étapes d'outils adaptées aux artefacts présents. | Aucun outil technique direct. Consultation de l'inventaire des preuves uniquement. | Ne lance aucun outil technique. Ne lit jamais le contenu des preuves brutes. Ne prend pas d'initiative hors liste blanche. |
| **Executor** | Reçoit le plan validé par l'humain (porte H1). Invoque séquentiellement chaque outil via la Gateway d'outils. Gère les erreurs techniques et les dépassements de timeout. | Tous les outils déclarés dans le registre MVP via la Gateway. | Ne génère aucun texte libre comme résultat. N'exécute aucune commande système arbitraire. Ne contourne jamais la Gateway. |
| **Analyst** | Interroge la base des `Observation` normalisées. Identifie les corrélations, formule des hypothèses de compromission et propose des `Finding` structurés. | Requêtes de lecture sur les observations et exécutions d'outils du dossier. | N'invente aucun fait. Ne référence aucune preuve absente de la base. Ne modifie pas les preuves ou observations. |
| **Verifier** | Contrôle déterministe (sans aucun modèle probabiliste ou LLM). Valide l'admissibilité de chaque `Finding` en vérifiant la présence effective des identifiants d'observations et d'outils cités. | Module de vérification déterministe interne (SQL / intégrité de graphe). | N'utilise aucun LLM. Ne produit aucune inférence sémantique. Rejette automatiquement tout finding dont une référence est introuvable. |
| **Corrélateur** | Agrège les observations temporelles extraites d'artefacts hétérogènes (EVTX, logs, fichiers, mémoire). Construit une frise chronologique unifiée ordonnée en UTC. | Fonctions d'agrégation et de tri temporel en base de données. | Ne modifie pas les horodatages originaux. Ne déduit pas d'événements sans observation correspondante. |
| **Rapporteur** | Rédige le document de synthèse d'incident (`Report`) à partir des `Finding` validés (porte H2) et des observations certifiées, après autorisation explicite de la porte H3. | Générateur de documents (Markdown / JSON). | Ne lit aucune preuve brute. Ne contacte jamais un LLM externe sans passage préalable par la pseudonymisation (D-19). |
 
---
 
## 2. Registre des outils MVP (Liste blanche stricte)
 
Tout accès aux artefacts forensiques passe impérativement par les analyseurs de la liste blanche. Aucun accès à un interpréteur de commandes (shell bash, powershell, sh) n'est exposé aux agents.
 
### 2.1 Outils inclus dans le MVP
1. **Empreinte cryptographique (`hash_sha256`)** :
   Calcul du hachage SHA-256 d'un fichier brut ou d'une fraction de preuve.
   *Bibliothèque* : `hashlib` (D-14).
2. **Normalisateur de journaux texte et CSV (`parse_text_logs`)** :
   Parsing, extraction regex et conversion standardisée des horodatages vers le format ISO-8601 UTC.
   *Bibliothèque* : `csv`, expressions régulières Python standard.
3. **Analyseur d'événements Windows EVTX (`parse_evtx`)** :
   Extraction structurée des canaux cruciaux : `Security` (connexions, élévations de privilèges), `System` (services), `PowerShell` (scripts exécutés, EventID 4104).
   *Bibliothèque* : `python-evtx` (D-16).
4. **Analyseur de Registre Windows (`parse_registry`)** :
   Extraction des clés de persistance (Run/RunOnce), des profils utilisateurs et des périphériques montés.
   *Bibliothèque* : `regipy` (D-17).
5. **Analyseur d'artefacts d'exécution Windows (`parse_execution`)** :
   Extraction des métadonnées d'exécution récentes (Prefetch).
   *Bibliothèque* : `dissect` (D-18).
6. **Analyseur de mémoire vive Volatility 3 (`analyze_memory`)** :
   Exécution locale hors ligne de Volatility 3 sur dump RAM Windows avec tables de symboles ISF préchargées (D-26).
   *Liste blanche stricte des plugins autorisés au MVP (tout autre plugin est bloqué)* :
   - `windows.info` : Identification du système d'exploitation, architecture, horodatage de capture.
   - `windows.pslist` et `windows.pstree` : Liste arborescente des processus actifs et terminés.
   - `windows.cmdline` : Extraction des lignes de commande des processus.
   - `windows.netscan` : Détection des connexions réseau établies et des ports en écoute.
   - `windows.malware.malfind` : Détection des injections de code et zones mémoire suspectes avec droits RWX.
   Chaque résultat est normalisé en entités `Observation` incluant l'identifiant d'appel, la version de Volatility et l'identifiant de la table de symboles utilisée.
 
### 2.2 Outils optionnels (conditionnés au calendrier)
- Extraction de système de fichiers Sleuth Kit : `pytsk3` (D-25).
- Moteur de signatures de menaces : `yara-python` (D-25).
- Extraction automatique d'indicateurs de compromission : extracteur d'IOC regex.
 
---
 
## 3. Spécifications techniques des outils
 
| Outil | Entrées | Sortie structurée | Timeout | Rôles autorisés | Bibliothèque |
|---|---|---|---|---|---|
| `hash_sha256` | `evidence_id`, `offset`, `length` | `sha256_hash`, `bytes_hashed` | 30 s | Executor | `hashlib` |
| `parse_text_logs` | `evidence_id`, `format_preset` | `records: [{timestamp_utc, raw, parsed_fields}]` | 60 s | Executor | standard / regex |
| `parse_evtx` | `evidence_id`, `event_ids: int[]`, `max_records` | `events: [{event_id, channel, computer, timestamp_utc, data}]` | 180 s | Executor | `python-evtx` |
| `parse_registry` | `evidence_id`, `hive_type`, `key_path` | `values: [{key, name, value_type, data, last_written_utc}]` | 120 s | Executor | `regipy` |
| `parse_execution` | `evidence_id`, `artifact_type` | `executions: [{executable_name, run_count, last_execution_utc}]` | 120 s | Executor | `dissect` |
| `analyze_memory` | `evidence_id`, `plugin_name` (parmi les 5 autorisés), `args` | `findings: [{plugin, pid, process_name, timestamp_utc, details}]` | 300 s | Executor | `volatility3` |
 
---
 
## 4. Règles de la Gateway d'outils
 
La Gateway d'outils est le composant central d'exécution et de médiation sécurisée :
 
1. **Validation des entrées** :
   Chaque paramètre d'entrée est validé par un modèle Pydantic strict avant toute instanciation. Toute tentative de passage de chemin de fichier arbitraire ou d'arguments non documentés déclenche une exception bloquante.
2. **Timeout d'exécution strict** :
   Chaque appel est soumis à une temporisation définie dans sa spécification (30 à 300 secondes). En cas de dépassement, le processus enfant est immédiatement tué et l'échec consigné.
3. **Audit exhaustif (`ToolExecution`)** :
   Pour chaque invocation, la Gateway persiste dans la table `ToolExecution` : l'identifiant unique d'appel, le nom de l'outil, sa version exacte, le rôle de l'agent appelant, les paramètres utiles, l'empreinte SHA-256 de la sortie, la durée d'exécution en millisecondes et le statut (`success`, `error`, `timeout`).
4. **Troncature de contexte pour agents** :
   Pour préserver la fenêtre de contexte des agents LLM et éviter tout déni de service par token, la réponse renvoyée à l'agent est tronquée et résumée (maximum 50 enregistrements représentatifs). La sortie brute exhaustive est quant à elle intégralement stockée en base et associée au dossier.
 
---
 
## 5. Règle de reprise sur interruption
 
L'état de chaque plan d'investigation est persisté dans l'entité `InvestigationRun`. Une enquête peut être mise en pause, interrompue suite à un crash serveur ou annulée manuellement par l'analyste.
 
Lors de la reprise :
- Toutes les étapes déjà terminées avec succès dans `ToolExecution` et leurs `Observation` associées restent valides et ne sont pas réexécutées.
- Le graphe LangGraph reprend directement à l'étape suivante non finalisée.
 
---
 
## 6. Limites opérationnelles chiffrées
 
Pour garantir la stabilité, la sécurité et la maîtrise des coûts de calcul :
- **Nombre maximal d'étapes par plan d'investigation** : 8 étapes.
- **Nombre maximal d'itérations de boucle Planner - Analyst** : 3 itérations.
- **Durée maximale globale d'une exécution d'investigation** : 30 minutes.
 
---
 
Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
