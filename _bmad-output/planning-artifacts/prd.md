---
title: "Product Requirement Document (PRD) - Back-End IRYX"
version: "1.0.0"
status: "validated"
created: "2026-11-23"
updated: "2026-11-23"
author: "BMad Analyst & Product Lead"
project: "IRYX"
target_scope: "MVP Back-End"
---

# Product Requirement Document (PRD) - Back-End IRYX

---

## 1. Vision

### 1.1 Positionnement produit
**IRYX** est une plateforme d'investigation numérique (DFIR - *Digital Forensics and Incident Response*) et d'analyse de fraudes, orchestrée par des agents d'intelligence artificielle spécialisés et supervisée en continu par l'analyste humain (*Human-in-the-Loop*).

Le système permet aux équipes de réponse à incident d'ingérer des preuves numériques brutes (fichiers journaux Windows EVTX, logs textuels et CSV, ruches de registre Windows, métadonnées Prefetch, images mémoire vive RAM), d'en extraire des faits techniques vérifiables de manière rigoureusement déterministe, et d'orienter le raisonnement d'agents IA pour formuler des hypothèses d'investigation, reconstituer des chronologies d'attaque et générer des rapports d'incident auditables et opposables.

### 1.2 Promesse de valeur
> **IRYX accélère et fiabilise les investigations numériques et l'analyse de fraudes en orchestrant des agents spécialisés guidés par des preuves vérifiables et contrôlés par l'analyste humain.**

### 1.3 Contexte et justification du problème
L'investigation numérique moderne fait face à un point de rupture critique, particulièrement exacerbé dans les contextes opérationnels émergents :
1. **Délai d'identification et de confinement critique** : Selon le rapport mondial *IBM Cost of a Data Breach Report 2023*, le délai moyen pour identifier et contenir une violation de données est de **277 jours** (204 jours pour la détection, 73 jours pour le confinement), avec un coût moyen global par brèche de **4,45 millions de dollars**.
2. **Pression accrue sur les marchés émergents d'Afrique de l'Ouest** : Selon l'*Interpol African Cyberthreat Assessment Report 2023*, les attaques par rançongiciel et les compromissions de messageries professionnelles (BEC / fraude au virement) ont progressé de plus de **30% en un an** en Afrique de l'Ouest. Ce phénomène se heurte à un déficit estimé à plus de **100 000 spécialistes en cybersécurité** sur le continent africain (*World Economic Forum Cybersecurity Skills Gap*).
3. **Explosion volumétrique et saturation cognitive** : D'après le *SANS DFIR Survey 2023*, **74% des praticiens forensiques** déclarent que l'inflation du volume de données brutes combinée à la fragmentation des outils d'analyse non intégrés constitue le goulot d'étranglement majeur provoquant retards d'enquête et erreurs de diagnostic.

### 1.4 Principes directeurs
1. **Evidence-first (Priorité absolue à la preuve)** : Aucune affirmation, inférence ou conclusion ne peut exister dans le système sans lien de traçabilité direct vers une observation matérielle issue d'une preuve brute immuable.
2. **Human-in-the-loop (Supervision humaine obligatoire)** : L'intelligence artificielle assiste l'investigateur mais ne prend aucune décision opérationnelle finale en autonomie. Trois portes de contrôle humain (H1, H2, H3) sanctuarisent le cycle de vie de chaque enquête.
3. **Séparation stricte des responsabilités** : Chaque rôle d'agent accomplit une tâche dédiée et étanche. L'agent qui planifie ne manipule pas les preuves ; l'agent qui exécute ne porte pas de jugement ; le module qui vérifie est strictement déterministe et n'utilise aucun modèle de langage probabiliste (LLM).
4. **Résultats persistés et reproductibles** : Chaque plan, exécution d'outil, observation et validation intermédiaire est persisté en base relationnelle. Une enquête peut être interrompue, reprise ou auditée a posteriori avec un résultat identique.
5. **Exécution contrôlée et sécurisée** : Tout outil technique s'exécute dans un environnement isolé, avec réseau désactivé, compte non-root et accès aux preuves monté exclusivement en lecture seule.
6. **Monolithe modulaire** : Architecture logicielle unifiée, modulaire, facilement déployable sur un serveur unique via Docker Compose, éliminant la complexité de maintenance des microservices pour le MVP.

---

## 2. Utilisateurs

### 2.1 Personas cibles
Le système s'adresse prioritairement aux professionnels de la cybersécurité confrontés à des délais stricts et à une forte charge d'analyse technique :

#### Persona 1 : Analyste SOC (Niveau 1 / Niveau 2)
- **Rôle métier** : Détection, triage initial et qualification des alertes d'incident ou de suspicion de fraude.
- **Besoin principal** : Automatiser la corrélation rapide de volumes massifs d'artefacts hétérogènes sans saturation cognitive, pour décider rapidement du passage en crise forensique.
- **Contraintes** : Délais stricts imposés par les accords de niveau de service (SLA), temps de traitement restreint, expertise inégale sur le parsing bas niveau d'artefacts propriétaires complexes.
- **Rôle dans le système** : `analyst`.

#### Persona 2 : Enquêteur numérique / Spécialiste DFIR
- **Rôle métier** : Conduite d'investigations techniques approfondies post-incident, analyse rétrospective de fraude financière, constitution de dossiers de preuves opposables.
- **Besoin principal** : Rigueur forensique absolue, garantie de la chaîne de possession (*chain of custody*), élimination des hallucinations d'IA par validation déterministe systématique.
- **Contraintes** : Interdiction absolue d'exfiltrer des données sensibles ou des preuves brutes non pseudonymisées vers des services cloud tiers ; obligation de produire des rapports auditables recevables devant des juridictions ou régulateurs.
- **Rôle dans le système** : `investigator`.

#### Persona 3 : Responsable Sécurité (CISO / RSSI - Afrique de l'Ouest)
- **Rôle métier** : Pilotage stratégique de la posture de sécurité, communication de crise auprès de la direction générale, justification réglementaire auprès des autorités de protection des données (ex. CDP au Sénégal, ARTCI en Côte d'Ivoire).
- **Besoin principal** : Visibilité claire, synthétique et chronologique sur les compromissions réelles, limitation des coûts d'investigation externe.
- **Contraintes** : Pénurie aiguë de profils seniors DFIR sur le marché local, budgets contraints, impératif strict de souveraineté opérationnelle et de conformité légale sur les données de paiement et d'identité.
- **Rôles dans le système** : `admin` (gestion d'organisation) ou `viewer` (consultation d'audit et rapports).

### 2.2 Rôles applicatifs (RBAC)
Le modèle d'autorisation applicatif repose sur quatre rôles rattachés à l'adhésion (`Membership`) d'un utilisateur au sein d'une organisation :
- **`admin`** : Gestion de l'organisation, des membres, des dossiers et configuration globale.
- **`investigator`** : Création et gestion complète de dossiers (`Case`), import de preuves, déclenchement et validation des investigations (portes H1, H2, H3), génération et export de rapports.
- **`analyst`** : Consultation des dossiers, participation à l'investigation, proposition de plans et de constats, validation des étapes selon délégations.
- **`viewer`** : Accès en lecture seule aux dossiers, observations, chronologies, findings et rapports finalisés.

---

## 3. Périmètre

Le périmètre du MVP est strictement délimité par la matrice définie dans le document source `docs/06-perimetre-mvp.md`.

> **Règle absolue de cadrage (docs/06)** : Tout ce qui n'apparaît pas dans la colonne « Dans le MVP » ne doit pas figurer dans les spécifications du MVP.

### 3.1 Périmètre inclus (Dans le MVP)
Le back-end IRYX MVP comprend exclusivement les treize domaines fonctionnels et techniques suivants :
1. **Gestion des dossiers et utilisateurs** : Organisations (`Organization`), utilisateurs (`User`), adhésions et rôles (`Membership`), dossiers d'investigation (`Case`), contrôle d'accès strict par dossier via dépendance FastAPI.
2. **Ingestion et scellement des preuves** : Importation de fichiers de preuves, calcul d'empreinte SHA-256 (`hashlib`), détection de type de signature binaire (`filetype`), stockage sur volume monté en lecture seule.
3. **Analyseur de logs texte et CSV** : Parseur de journaux texte et CSV, normalisation des horodatages au format ISO-8601 UTC, extraction structurée dans l'entité `Observation`.
4. **Analyseur Windows EVTX** : Traitement structuré des canaux critiques `Security`, `System` et `PowerShell` via `python-evtx`.
5. **Analyseur de Registre et Prefetch** : Extraction des clés de persistance (Run/RunOnce, profils, périphériques) via `regipy` et des métadonnées d'exécution récentes via `dissect`.
6. **Analyse de mémoire vive Volatility 3** : Exécution hors ligne de Volatility 3 restreinte à une liste blanche stricte de 5 plugins (`windows.info`, `windows.pslist`/`windows.pstree`, `windows.cmdline`, `windows.netscan`, `windows.malware.malfind`) avec tables de symboles ISF Windows préchargées (D-26).
7. **Orchestration d'enquête LangGraph** : Graphe d'états d'investigation complet avec cycle séquentiel : Planner -> Executor -> Analyst -> Verifier -> Corrélateur -> Rapporteur.
8. **Portes de contrôle humain (Gates)** :
   - Porte H1 : Validation humaine obligatoire du plan d'outils proposé.
   - Porte H2 : Validation humaine obligatoire des constats (*Findings*) certifiés.
   - Porte H3 : Autorisation humaine expresse avant transmission d'une synthèse au LLM externe.
9. **Vérificateur déterministe (Verifier)** : Module de validation mathématique et relationnelle (SQL) de l'admissibilité des références de preuves sans aucun appel à un modèle de langage (LLM).
10. **Pseudonymisation (Microsoft Presidio)** : Détection et substitution déterministe des entités sensibles (PII, IP, noms d'hôtes, comptes) avant toute sollicitation d'un LLM externe (D-19).
11. **Journal d'audit immuable** : Traçabilité complète des événements critiques en mode ajout seul (*append-only*) dans la table `AuditEvent`.
12. **API REST FastAPI & Authentification JWT** : Points d'accès sécurisés, validation stricte Pydantic v2, jetons d'accès PyJWT, hachage des mots de passe argon2 via `pwdlib`.
13. **Topologie Docker Compose mono-serveur** : Déploiement consolidé sur hôte unique comprenant 4 services : `postgres` (PostgreSQL 16), `redis` (Redis 7), `api` (FastAPI Python 3.12), `worker` (Celery Python 3.12).

### 3.2 Périmètre exclu (Hors MVP)
Sont formellement exclus du périmètre MVP :
- **Options forensiques différées** : Extraction de disque Sleuth Kit (`pytsk3`), moteur de règles de signature YARA (`yara-python`), extracteur automatique d'IOC par regex (D-25).
- **Architecture distribuée & Microservices** : Déploiement multi-services, conteneurs orchestrés par Kubernetes ou Helm (ADR-0001).
- **Bus de messages lourd** : Kafka, RabbitMQ, ou infrastructure d'événements distribuée (ADR-0001).
- **Cache distribué** : Memcached ou Redis Cluster.
- **Application cliente de bureau** : Client lourd Tauri (reporté post-MVP).
- **Multi-tenant d'infrastructure** : Bases de données physiquement isolées par client (l'isolation est logique par organisation au sein de PostgreSQL 16 - ADR-0002).
- **Moteurs forensiques tiers lourds** : Plaso / log2timeline, Zeek, Suricata.
- **Supervision Celery Flower** : Interface graphique web de gestion des workers.
- **Flux temps réel bidirectionnels** : WebSocket ou Server-Sent Events (SSE) ; le polling REST est la norme unique du MVP (D-24).

---

## 4. Exigences Fonctionnelles (FR)

Chaque exigence fonctionnelle est numérotée de façon unique (`FR1`, `FR2`, ...) et rattachée formellement à l'un des huit modules métier définis dans l'organisation du code (`docs/05-conventions-backend.md`) :
- `auth` : Authentification, gestion des utilisateurs et permissions.
- `cases` : Gestion des dossiers d'investigation et adhésion des membres.
- `evidences` : Ingestion, contrôle d'intégrité SHA-256 et stockage en lecture seule.
- `gateway` : Registre et invocation sécurisée des outils forensiques.
- `orchestrator` : Machine d'états LangGraph, exécution des phases et gestion des portes H1/H2/H3.
- `analytics` : Analyse, vérification déterministe des findings et corrélations temporelles.
- `reporting` : Génération, pseudonymisation et export des rapports d'incident.
- `audit` : Journalisation d'audit immuable (`AuditEvent`).

---

### Module métier : `auth`

#### FR1 : Authentification et émission de jetons JWT
- **Module associé** : `auth`
- **Description** : Le système doit authentifier les utilisateurs enregistrés via leur adresse e-mail et leur mot de passe.
- **Détails techniques** :
  - Vérification du hachage de mot de passe via l'algorithme argon2 (`pwdlib[argon2]`, D-13).
  - Émission d'un jeton d'accès signé selon le standard PyJWT (D-12) en cas de succès.
  - Rejet des identifiants invalides avec un code HTTP 401 standardisé sans divulgation d'information sur l'existence du compte.

#### FR2 : Gestion des organisations et adhésions RBAC
- **Module associé** : `auth`
- **Description** : Le système doit gérer les organisations clientes (`Organization`), les utilisateurs (`User`) et leurs adhésions (`Membership`) associées aux rôles RBAC (`admin`, `analyst`, `investigator`, `viewer`).
- **Détails techniques** :
  - Création et consultation des profils utilisateurs et organisations.
  - Attribution d'un rôle d'adhésion définissant les droits de l'utilisateur au sein de l'organisation.
  - Révocation ou désactivation d'un utilisateur via le champ `is_active`.

---

### Module métier : `cases`

#### FR3 : Gestion du cycle de vie des dossiers d'investigation
- **Module associé** : `cases`
- **Description** : Le système doit permettre la création, la consultation, la mise à jour et la clôture de dossiers d'investigation (`Case`).
- **Détails techniques** :
  - Chaque dossier est rattaché obligatoirement à une organisation (`organization_id`) et un créateur (`created_by`).
  - Suivi d'état selon les valeurs d'énumération : `open`, `in_progress`, `review`, `closed`.
  - Consultation paginée et filtrée des dossiers de l'organisation de l'utilisateur.

#### FR4 : Contrôle d'accès strict au niveau dossier
- **Module associé** : `cases`
- **Description** : Le système doit interdire tout accès ou manipulation d'une ressource (preuve, observation, finding, rapport, session d'investigation) si l'utilisateur demandeur n'appartient pas à l'organisation détentrice du dossier.
- **Détails techniques** :
  - Injection systématique de la dépendance FastAPI `verify_case_access` (Règle 5 de docs/05, docs/04).
  - Rejet immédiat par HTTP 403 Forbidden en cas de défaut d'appartenance.

---

### Module métier : `evidences`

#### FR5 : Ingestion asynchrone des preuves numériques
- **Module associé** : `evidences`
- **Description** : Le système doit permettre le téléversement de fichiers de preuves numériques brutes au sein d'un dossier (`Case`) avec suivi asynchrone de l'opération.
- **Détails techniques** :
  - Création de l'entité `Evidence` et initialisation d'une tâche de fond Celery associée à une entité `IngestionRun` (statuts : `pending`, `processing`, `completed`, `failed`).
  - Retour immédiat par l'API d'un code HTTP 202 Accepted avec identifiant de suivi pour consultation par polling.

#### FR6 : Scellement cryptographique SHA-256 et identification de type
- **Module associé** : `evidences`
- **Description** : Dès réception d'un fichier de preuve, le système doit calculer son empreinte cryptographique SHA-256 et identifier son format par signature binaire.
- **Détails techniques** :
  - Calcul de l'empreinte SHA-256 via la bibliothèque standard `hashlib` (D-14), persisté dans `Evidence.sha256`.
  - Détection du type MIME réel par inspection des signatures d'en-tête via `filetype` (D-15), persisté dans `Evidence.detected_type`.
  - Interdiction de l'écrasement silencieux : soumettre un fichier portant un nom identique génère une nouvelle entité `Evidence` horodatée distincte (docs/04).

#### FR7 : Stockage immuable en lecture seule des preuves
- **Module associé** : `evidences`
- **Description** : Le système doit garantir que les fichiers bruts stockés ne peuvent être modifiés ou supprimés par les processus de traitement ou les outils forensiques.
- **Détails techniques** :
  - Stockage physique sur un volume dédié monté avec l'attribut lecture seule (`ro`) pour l'ensemble des conteneurs de traitement et d'exécution d'outils.

---

### Module métier : `gateway`

#### FR8 : Registre et invocation sécurisée des outils forensiques
- **Module associé** : `gateway`
- **Description** : La Gateway doit servir de point d'accès unique et sécurisé pour l'exécution des outils forensiques de la liste blanche MVP, en bloquant tout accès direct au système d'exploitation.
- **Détails techniques** :
  - Validation stricte des paramètres d'entrée via des modèles Pydantic v2 avant toute instanciation.
  - Exécution en sous-processus sans interpréteur de commande (`shell=False`) sous compte non-root (`uid 10001:gid 10001`) sans réseau (`network_mode: none`).
  - Interruption automatique en cas de dépassement du timeout alloué à l'outil.

#### FR9 : Traçabilité et audit d'exécution d'outils
- **Module associé** : `gateway`
- **Description** : La Gateway doit consigner de manière exhaustive chaque exécution d'outil dans l'entité `ToolExecution`.
- **Détails techniques** :
  - Enregistrement de l'identifiant d'exécution, du nom d'outil, de sa version exacte, du rôle de l'agent appelant, des paramètres validés, de l'empreinte SHA-256 de la sortie brute (`result_sha256`), de la durée d'exécution en millisecondes (`duration_ms`) et du statut final (`success`, `error`, `timeout`).

#### FR10 : Troncature et résumé des résultats pour les agents
- **Module associé** : `gateway`
- **Description** : La Gateway doit tronquer la réponse retournée aux agents LLM pour préserver leur fenêtre de contexte tout en conservant le résultat brut complet en base.
- **Détails techniques** :
  - Troncature à 50 enregistrements représentatifs maximum pour la charge utile transmise à l'agent.
  - Stockage persistant du jeu complet d'observations en base de données.

#### FR11 : Analyseur de logs texte et CSV
- **Module associé** : `gateway`
- **Description** : L'outil `parse_text_logs` doit extraire les événements issus de fichiers journaux textuels ou tabulaires (CSV) et normaliser leurs horodatages.
- **Détails techniques** :
  - Extraction des enregistrements et conversion systématique des horodatages vers le standard ISO-8601 UTC.
  - Génération d'enregistrements `Observation` avec contenu normalisé en JSONB et mention de la localisation source.
  - Timeout d'exécution alloué : 60 secondes.

#### FR12 : Analyseur d'événements Windows EVTX
- **Module associé** : `gateway`
- **Description** : L'outil `parse_evtx` doit parser les fichiers journaux Windows EVTX pour extraire les événements critiques des canaux désignés.
- **Détails techniques** :
  - Utilisation du parseur pur Python `python-evtx` (D-16).
  - Ciblage des canaux critiques : `Security` (connexions, élévations de privilèges), `System` (services), `PowerShell` (scripts exécutés, EventID 4104).
  - Génération d'enregistrements `Observation` typés.
  - Timeout d'exécution alloué : 180 secondes.

#### FR13 : Analyseur de Registre Windows
- **Module associé** : `gateway`
- **Description** : L'outil `parse_registry` doit extraire les clés d'intérêt forensique à partir de ruches de registre Windows.
- **Détails techniques** :
  - Utilisation de la bibliothèque pur Python `regipy` (D-17).
  - Extraction des clés de persistance logicielle (Run, RunOnce), des comptes et profils utilisateurs, ainsi que des périphériques montés.
  - Génération d'enregistrements `Observation` incluant la date de dernière écriture UTC (`last_written_utc`).
  - Timeout d'exécution alloué : 120 secondes.

#### FR14 : Analyseur d'artefacts d'exécution Prefetch
- **Module associé** : `gateway`
- **Description** : L'outil `parse_execution` doit extraire les preuves d'exécution de programmes via l'analyse des fichiers Prefetch Windows.
- **Détails techniques** :
  - Utilisation de la bibliothèque `dissect` (D-18).
  - Extraction des métadonnées d'exécution : nom du binaire exécutable, compteur d'exécutions (`run_count`), horodatages de dernière exécution UTC (`last_execution_utc`).
  - Normalisation en entités `Observation`.
  - Timeout d'exécution alloué : 120 secondes.

#### FR15 : Analyseur de mémoire vive Volatility 3
- **Module associé** : `gateway`
- **Description** : L'outil `analyze_memory` doit exécuter localement et hors ligne le moteur Volatility 3 sur des images mémoire RAM Windows.
- **Détails techniques** :
  - Version figée `volatility3 == 2.7.0` (D-26) avec pack de symboles ISF Windows officiel préchargé localement (`windows.zip`).
  - Exécution strictement restreinte à la liste blanche des 5 plugins autorisés :
    1. `windows.info` (métadonnées système et horodatage de capture).
    2. `windows.pslist` et `windows.pstree` (arborescence des processus).
    3. `windows.cmdline` (lignes de commande des processus).
    4. `windows.netscan` (connexions réseau actives et ports en écoute).
    5. `windows.malware.malfind` (injections de code suspectes et zones RWX).
  - Rejet immédiat de tout autre plugin non listé.
  - Génération d'entités `Observation` normalisées avec mention de la version de Volatility et des symboles utilisés.
  - Timeout d'exécution alloué : 300 secondes.

---

### Module métier : `orchestrator`

#### FR16 : Orchestration de session d'enquête par machine d'états LangGraph
- **Module associé** : `orchestrator`
- **Description** : Le système doit orchestrer le déroulement d'une session d'investigation (`InvestigationRun`) via un graphe d'états LangGraph (D-09).
- **Détails techniques** :
  - Séquencement strict des phases : `triage` -> `planning` -> *Validation H1* -> `execution` -> `analysis` -> `verification` -> *Validation H2* -> `pseudonymisation` -> *Autorisation H3* -> `reporting`.
  - Persistance de l'état d'avancement et suivi par phase dans l'entité `Phase`.

#### FR17 : Boucle d'agents Planner - Executor
- **Module associé** : `orchestrator`
- **Description** : Le système doit exécuter la collaboration entre l'agent `Planner` et l'agent `Executor`.
- **Détails techniques** :
  - L'agent `Planner` consulte l'inventaire des preuves disponibles dans le dossier et propose un plan d'investigation ordonné de 4 à 8 étapes d'outils. Le Planner n'a aucun accès direct aux preuves brutes.
  - L'agent `Executor` prend en charge le plan une fois validé par l'humain et invoque séquentiellement chaque outil via la Gateway.

#### FR18 : Porte de contrôle humain H1 - Validation du plan d'action
- **Module associé** : `orchestrator`
- **Description** : L'orchestrateur doit suspendre l'exécution et attendre une approbation explicite de l'analyste humain avant de déclencher l'exécution des outils.
- **Détails techniques** :
  - Mise en pause du graphe LangGraph à l'état `planning`.
  - L'analyste peut approuver le plan tel quel, le rejeter ou apporter des modifications aux étapes d'outils.
  - Enregistrement du plan validé dans `InvestigationRun.validated_plan` et passage à la phase d'exécution uniquement sur validation.

#### FR19 : Porte de contrôle humain H2 - Validation des constats (Findings)
- **Module associé** : `orchestrator`
- **Description** : L'orchestrateur doit suspendre l'enquête après l'étape de vérification déterministe pour permettre à l'analyste de valider les constats techniques.
- **Détails techniques** :
  - Présentation des `Finding` certifiés par le `Verifier`.
  - L'analyste valide individuellement chaque constat, ajuste sa sévérité (`low`, `medium`, `high`, `critical`) ou son niveau de confiance (`low`, `medium`, `high`), ou le rejette.
  - Seuls les constats ayant le statut `validated` sont transmis aux phases ultérieures.

#### FR20 : Porte de contrôle humain H3 - Autorisation d'envoi externe
- **Module associé** : `orchestrator`
- **Description** : Le système doit interdire toute transmission de données vers un service d'inférence LLM externe sans une confirmation humaine explicite.
- **Détails techniques** :
  - Présentation à l'analyste de la synthèse pseudonymisée préparée pour la rédaction du rapport.
  - L'analyste accorde ou refuse formellement l'envoi externe.
  - Consignation immédiate du choix dans le journal d'audit.

#### FR21 : Persistance et reprise sur interruption
- **Module associé** : `orchestrator`
- **Description** : Le système doit pouvoir reprendre une session d'investigation interrompue (pause, crash système, redémarrage) sans rejouer les étapes d'outils déjà achevées avec succès.
- **Détails techniques** :
  - État complet du graphe LangGraph persisté dans PostgreSQL 16.
  - À la reprise, consultation des enregistrements `ToolExecution` réussis et reprise à l'étape suivante non finalisée.

---

### Module métier : `analytics`

#### FR22 : Formulation et structuration des constats d'investigation (Analyst)
- **Module associé** : `analytics`
- **Description** : L'agent `Analyst` doit interroger les observations normalisées pour identifier des corrélations et formuler des constats techniques structurés (`Finding`).
- **Détails techniques** :
  - Chaque `Finding` est caractérisé par un titre, un type (`fact`, `inference`, `hypothesis`), une sévérité, un niveau de confiance et le statut initial `proposed`.
  - Association obligatoire d'une liste d'identifiants d'observations justificatives (`observation_refs`) et d'exécutions d'outils (`tool_execution_refs`).

#### FR23 : Vérification déterministe formelle des constats (Verifier)
- **Module associé** : `analytics`
- **Description** : Le module `Verifier` doit valider de manière purement algorithmique et déterministe, sans aucun appel LLM, l'existence et la cohérence de chaque référence de preuve citée dans un constat.
- **Détails techniques** :
  - Vérification par requête SQL de l'existence effective de chaque identifiant présent dans `observation_refs` et `tool_execution_refs` au sein du même dossier (`case_id`).
  - Rejet automatique immédiat (`status = 'rejected'`) de tout constat comportant au moins une référence introuvable ou étrangère au dossier.

#### FR24 : Corrélation temporelle et timeline unifiée UTC
- **Module associé** : `analytics`
- **Description** : Le composant `Corrélateur` doit agréger l'ensemble des observations temporelles extraites d'artefacts hétérogènes pour construire une frise chronologique unifiée.
- **Détails techniques** :
  - Agrégation et tri chronologique strict sur le champ `timestamp_utc` des entités `Observation`.
  - Conservation intégrale des horodatages originaux sans extrapolation ou altération.

---

### Module métier : `reporting`

#### FR25 : Pseudonymisation déterministe des données (Microsoft Presidio)
- **Module associé** : `reporting`
- **Description** : Le système doit anonymiser les données techniques et personnelles sensibles avant toute sollicitation d'un LLM externe pour la rédaction assistée.
- **Détails techniques** :
  - Analyse et détection des entités nommées (noms de personnes, organisations, adresses IP, noms d'hôtes, identifiants de comptes) via Microsoft Presidio (D-19).
  - Remplacement par des pseudonymes déterministes et cohérents au sein du dossier (ex. `IP_INTERNAL_1`, `USER_ACCOUNT_A`).
  - Génération d'une version pseudonymisée soumise à l'analyste pour la porte H3.

#### FR26 : Rédaction et scellement du rapport d'incident
- **Module associé** : `reporting`
- **Description** : L'agent `Rapporteur` doit compiler un rapport de synthèse d'incident (`Report`) à partir des constats validés (H2) et certifiés.
- **Détails techniques** :
  - Génération du contenu aux formats Markdown et JSON à partir des faits certifiés.
  - Calcul et persistance de l'empreinte cryptographique SHA-256 du rapport final (`sha256`).
  - Suivi d'état du rapport : `draft`, `validated`, `exported`.

---

### Module métier : `audit`

#### FR27 : Journalisation d'audit immuable en ajout seul
- **Module associé** : `audit`
- **Description** : Le système doit consigner de manière synchrone, inaltérable et sans suppression possible chaque action sensible dans la table `AuditEvent`.
- **Détails techniques** :
  - Événements tracés obligatoirement : connexions/authentifications, accès aux dossiers (`Case`), imports de preuves (`Evidence`), exécutions d'outils, validations/rejets des portes de contrôle (H1, H2, H3), exportations de rapports.
  - Données enregistrées : identifiant de l'acteur (`actor_id`), code d'action, type et identifiant de la cible, horodatage UTC, métadonnées de sécurité (IP, session) et empreinte cryptographique de la charge utile (`payload_hash`).
  - Fonctionnement strictement append-only : interdiction des requêtes SQL `UPDATE` et `DELETE`.

---

## 5. Exigences Non Fonctionnelles (NFR)

Toutes les exigences non fonctionnelles ci-dessous sont **strictement mesurables** par une valeur numérique explicite ou par un critère de vérification objectif et vérifiable.

### 5.1 Performance et Dimensionnement

#### NFR-PERF-01 : Délégation asynchrone des tâches longues (> 500 ms)
- **Valeur mesurable** : Tout traitement métier dont l'exécution dépasse 500 millisecondes (ingestion, hash SHA-256, parsing EVTX, scan mémoire Volatility 3, rédaction LLM) doit être exécuté de manière asynchrone par un worker Celery.
- **Critère de vérification** : La route API FastAPI correspondante doit retourner un code HTTP 202 Accepted avec identifiant de tâche en moins de 500 ms (mesuré au 95e percentile).

#### NFR-PERF-02 : Timeouts stricts d'exécution des outils forensiques
- **Valeur mesurable** : Chaque outil invoqué via la Gateway est borné par un timeout strict :
  - `hash_sha256` : 30 secondes.
  - `parse_text_logs` : 60 secondes.
  - `parse_registry` : 120 secondes.
  - `parse_execution` : 120 secondes.
  - `parse_evtx` : 180 secondes.
  - `analyze_memory` : 300 secondes.
- **Critère de vérification** : Un test automatisé simulant un outil bloqué vérifie que le sous-processus est tué par le système à `t = timeout + 1 seconde` maximum, et que la ligne correspondante dans `ToolExecution` reçoit le statut `timeout`.

#### NFR-PERF-03 : Paramètres de résilience et timeout des appels LLM
- **Valeur mesurable** : Le délai d'attente d'une réponse LLM est borné par la variable `LLM_TIMEOUT_SECONDS = 60`. Le nombre de réessais automatiques avec backoff exponentiel géré par `tenacity` est borné par `LLM_MAX_RETRIES = 3`.
- **Critère de vérification** : En cas de coupure réseau ou d'indisponibilité du service LLM, le client doit effectuer exactement 3 tentatives avant de lever une exception et de suspendre la phase en échec après 180 secondes cumulées maximum.

#### NFR-PERF-04 : Durée maximale d'une session d'investigation
- **Valeur mesurable** : La durée globale d'une session d'investigation (`InvestigationRun`) ne doit pas dépasser 30 minutes (1 800 secondes).
- **Critère de vérification** : Si une session dépasse 30 minutes, l'orchestrateur bascule automatiquement son statut à `failed` avec consignation d'un événement d'audit d'expiration.

#### NFR-PERF-05 : Limites structurelles du plan et des itérations d'enquête
- **Valeur mesurable** :
  - Le plan d'outils produit par l'agent `Planner` doit contenir entre 4 et 8 étapes (inclus).
  - La boucle de réitération Planner - Analyst est bornée à 3 itérations maximum (`iteration_count <= 3`).
- **Critère de vérification** : Rejet par validation Pydantic si le plan contient moins de 4 ou plus de 8 étapes ; arrêt automatique de la boucle à la 3e itération si aucun nouveau finding n'est qualifié.

#### NFR-PERF-06 : Troncature de contexte pour les agents
- **Valeur mesurable** : Le flux d'observations renvoyé dans le contexte d'un agent LLM par la Gateway est plafonné à 50 enregistrements maximum.
- **Critère de vérification** : Test unitaire vérifiant que pour une sortie brute contenant 10 000 événements EVTX, le schéma transmis au modèle contient exactement `<=` 50 éléments résumés.

#### NFR-PERF-07 : Pagination systématique des listes
- **Valeur mesurable** : Tous les endpoints retournant des collections (preuves, observations, findings, événements d'audit) doivent accepter les paramètres `limit` et `offset`, avec une valeur par défaut de 50 et un plafond strict de 100 éléments par page.
- **Critère de vérification** : Toute requête demandant `limit=150` est ramenée à 100 ou rejetée avec une erreur 422 de validation Pydantic.

---

### 5.2 Sécurité et Isolation

#### NFR-SEC-01 : Scellement et lecture seule des preuves brutes
- **Valeur mesurable** : Les volumes de stockage des preuves sont montés avec le drapeau `ro` (read-only) sur l'ensemble des conteneurs applicatifs et workers.
- **Critère de vérification** : Toute tentative d'écriture filesystem sur un fichier de preuve déclenche une erreur système `EROFS` (Read-only file system). Tout nouvel upload d'un fichier existant génère un nouvel UUID sans écraser le précédent.

#### NFR-SEC-02 : Confinement non-root et coupure réseau des outils forensiques
- **Valeur mesurable** : Les conteneurs ou environnements d'exécution des outils forensiques s'exécutent avec :
  - Compte non-root : UID `10001`, GID `10001`.
  - Suppression de l'ensemble des capacités Linux : `cap_drop: ALL`.
  - Mode réseau désactivé : `network_mode: none`.
  - Absence de shell : `shell=False` dans les appels de sous-processus.
- **Critère de vérification** : Une commande de tentative d'ouverture de socket externe (ex. requête HTTP sortante) ou d'exécution d'un binaire shell échoue immédiatement avec un code de retour différent de 0.

#### NFR-SEC-03 : Immutabilité absolue de la table d'audit
- **Valeur mesurable** : 0 opération de modification (`UPDATE`) ou de suppression (`DELETE`) autorisée sur la table `AuditEvent`.
- **Critère de vérification** : L'exécution d'une requête SQL `DELETE FROM audit_events` ou `UPDATE audit_events SET action = ...` déclenche une exception SQL bloquante au niveau de la base de données PostgreSQL.

#### NFR-SEC-04 : Hachage fort des mots de passe
- **Valeur mesurable** : 100% des mots de passe utilisateurs sont hachés via argon2 via la bibliothèque `pwdlib[argon2]`.
- **Critère de vérification** : Aucune chaîne de mot de passe en clair ou hachée avec un algorithme non sécurisé (MD5, SHA-1, SHA-256 simple) n'est présente dans la colonne `hashed_password` de la table `User`.

#### NFR-SEC-05 : Cloisonnement strict multi-utilisateurs (Zero Leak)
- **Valeur mesurable** : 100% des routes manipulant un `Case` ou une sous-ressource liée doivent exécuter la dépendance `verify_case_access`.
- **Critère de vérification** : Un test d'intégration automatisé simulant un utilisateur du compte A tentant d'accéder à l'identifiant d'un dossier du compte B reçoit obligatoirement une réponse HTTP 403 Forbidden. Aucune trace de pile (*stack trace*) ni chemin système absolu ne doit figurer dans les réponses d'erreur HTTP.

#### NFR-SEC-06 : Immunisation contre l'injection indirecte de prompts
- **Valeur mesurable** : 0 fragment brut d'artefact forensique (texte EVTX, ligne Prefetch, clé de registre) n'est injecté dans le `system prompt` d'un agent.
- **Critère de vérification** : 100% des données forensiques analysées sont injectées dans des conteneurs de données passifs délimités (balises XML ou champs JSON) avec consigne explicite d'interdiction d'interprétation d'instructions.

#### NFR-SEC-07 : Pseudonymisation intégrale préalable à tout transfert externe
- **Valeur mesurable** : 100% des requêtes sortantes vers un LLM externe doivent comporter 0 entité sensible identifiée par Microsoft Presidio (adresses IP, noms de domaine/hôtes, comptes d'utilisateurs, noms de personnes).
- **Critère de vérification** : Un test unitaire validant le flux de rapport démontre que les identifiants techniques sont systématiquement substitués par leurs pseudonymes déterministes (ex. `IP_INTERNAL_1`).

#### NFR-SEC-08 : Intégrité et symboles Volatility 3 hors ligne
- **Valeur mesurable** : L'archive de symboles Windows officielle `windows.zip` préchargée dans `/opt/volatility3/symbols` doit avoir l'empreinte SHA-256 exacte : `c7e49e8a520bfd68cfa1907cbcf9581c15f9e761dfb61b369527ec50c76251b3`.
- **Critère de vérification** : Au démarrage du worker, un script de vérification contrôle l'empreinte ; en cas de non-concordance ou de tentative de téléchargement dynamique de symboles via le réseau, le service refuse de démarrer.

---

### 5.3 Fiabilité et Déterminisme

#### NFR-REL-01 : Déterminisme absolu du composant Verifier
- **Valeur mesurable** : 0 appel à un modèle de langage (LLM) effectué par le composant `Verifier`.
- **Critère de vérification** : Revue de code et test unitaire démontrant que le `Verifier` opère exclusivement par requêtes SQL et logique ensembliste. Tout `Finding` dont un identifiant dans `observation_refs` ou `tool_execution_refs` n'existe pas en base est rejeté à 100%.

#### NFR-REL-02 : Journalisation structurée JSON sans secrets
- **Valeur mesurable** : 100% des logs applicatifs émis via la bibliothèque standard `logging` sont sérialisés au format JSON structuré (D-23).
- **Critère de vérification** : Vérification automatisée qu'aucun mot de passe, clé API, jeton JWT ou extrait brut de preuve n'est consigné dans les flux de logs.

---

### 5.4 Qualité logicielle et Maintenabilité

#### NFR-QA-01 : Typage strict et conformité Ruff
- **Valeur mesurable** :
  - 100% des fonctions publiques, méthodes de service et routes comportent des annotations de types Python 3.12 conformes.
  - 0 erreur et 0 avertissement émis par le linter et formateur `ruff` (D-21).
- **Critère de vérification** : Exécution de `ruff check .` et `ruff format --check .` avec code de retour 0 dans le pipeline d'intégration continue.

#### NFR-QA-02 : Couverture de tests automatisés
- **Valeur mesurable** :
  - Couverture unitaire de chaque service métier via `pytest`.
  - Couverture d'intégration des routes API via `httpx` et `pytest-asyncio`.
  - Présence de tests de sécurité dédiés pour l'isolation multi-utilisateurs et la prévention des traversées de répertoires (*path traversal*).
- **Critère de vérification** : La commande `pytest` doit s'exécuter avec 100% de tests réussis sans échec.

---

## 6. Contraintes

### 6.1 Contraintes technologiques figées (D-01 à D-26)
Le développement du back-end doit impérativement respecter les décisions technologiques actées dans `docs/01-architecture-technique.md` et `docs/07-api-llm-et-dependances.md` :
- **Langage** : Python 3.12 (D-01).
- **Gestionnaire de dépendances** : `uv` (v0.12.8) avec fichier de verrouillage (D-02).
- **Framework API HTTP** : FastAPI (>=0.115.0) (D-03).
- **Validation et configuration** : Pydantic v2 (>=2.9.0) et `pydantic-settings` (>=2.5.0) (D-04).
- **Base de données relationnelle** : PostgreSQL 16 (D-05, ADR-0002).
- **Accès base de données** : SQLAlchemy 2.x (>=2.0.35) avec driver natif `psycopg` 3 (>=3.2.0) (D-06).
- **Migrations de schéma** : Alembic (>=1.13.0) (D-07) ; interdiction de `create_all` au démarrage.
- **Tâches asynchrones** : Celery (>=5.4.0) avec Redis 7 (>=7.0.0) comme broker (D-08, ADR-0001).
- **Orchestration d'enquête** : LangGraph (>=0.2.20) (D-09).
- **Client LLM** : Client unique basé sur le SDK officiel `openai` (>=1.50.0) configuré par rôle (`base_url`, `model`) (D-10, ADR-0003).
- **Gestion des réessais** : `tenacity` (>=9.0.0) avec backoff exponentiel (D-11).
- **Sécurité et jetons** : `PyJWT` (>=2.9.0) pour les jetons JWT (D-12) et `pwdlib[argon2]` (>=0.2.0) pour les mots de passe (D-13).
- **Outils forensiques purs Python** : `hashlib` pour SHA-256 (D-14), `filetype` (>=1.2.0) pour les signatures (D-15), `python-evtx` (>=0.7.4) pour EVTX (D-16), `regipy` (>=5.1.0) pour le Registre (D-17), `dissect` (>=3.8.0) pour Prefetch/exécution (D-18).
- **Pseudonymisation** : Microsoft Presidio (`presidio-analyzer`, `presidio-anonymizer` >=2.2.35) (D-19).
- **Analyse mémoire vive** : `volatility3 == 2.7.0` avec symboles ISF préchargés (D-26).
- **Mise à jour d'état** : Polling HTTP REST uniquement (D-24). Pas de WebSocket ni SSE au MVP.

### 6.2 Contraintes d'architecture logicielle et règles de revue (docs/05)
Le code source doit respecter sans exception les 14 règles de conventions back-end :
1. Un package dédié par module métier sous `backend/src/iryx/` (`auth`, `cases`, `evidences`, `gateway`, `orchestrator`, `analytics`, `reporting`, `audit`). Zéro dépendance circulaire.
2. Contrôleurs minces (*Thin Controllers*) dans les routes FastAPI : validation, injection de contexte, appel de service, retour schématisé.
3. Séparation stricte entre schémas Pydantic (`SchemaIn`, `SchemaOut`) et modèles ORM SQLAlchemy.
4. Injection systématique des dépendances (`Depends` de FastAPI).
5. Vérification d'accès au dossier (`verify_case_access`) sur 100% des routes manipulant un `Case`.
6. Codes d'erreur HTTP sémantiques normalisés sans fuite de stack trace ou de chemin absolu.
7. Pagination et filtrage systématiques avec limite bornée (défaut : 50, max : 100).
8. Délégation asynchrone systématique à Celery pour toute tâche > 500 ms avec retour HTTP 202.
9. Évolution du schéma PostgreSQL exclusivement par scripts de migration Alembic testés et réversibles.
10. Configuration centralisée par variables d'environnement via `pydantic-settings`.
11. Typage statique strict et zéro avertissement Ruff.
12. Couverture de tests unitaires et d'intégration obligatoire.
13. Journalisation JSON structurée sans secrets.
14. Mise à jour synchrone obligatoire de la documentation dans `docs/` en cas de modification.

### 6.3 Contraintes d'infrastructure et de déploiement
- Déploiement mono-serveur orchestré exclusivement par `docker-compose.yml` (D-22, ADR-0001).
- Quatre services consolidés : `postgres`, `redis`, `api`, `worker`.
- Absence de services tiers managés en mode SaaS ou de dépendances réseau externes non documentées.

---

## 7. Hypothèses

Les hypothèses suivantes fondent la conception du back-end IRYX dans son périmètre MVP, conformément aux documents d'entrée :
1. **Nature et intégrité des artefacts sources** : Les artefacts forensiques soumis par les utilisateurs correspondent aux types supportés par les analyseurs inclus au MVP (fichiers logs texte/CSV, fichiers EVTX Windows, ruches de registre, fichiers Prefetch, images mémoire brutes Windows).
2. **Capacité matérielle de l'hôte de déploiement** : L'hôte physique ou la machine virtuelle exécutant Docker Compose dispose des ressources processeur, mémoire vive (RAM) et disque suffisantes pour exécuter PostgreSQL 16, Redis 7, l'API FastAPI et les workers Celery, notamment lors du parsing d'images mémoire RAM de plusieurs gigaoctets via Volatility 3.
3. **Disponibilité des points d'accès LLM** :
   - En environnement de développement, une connexion sortante autorisée vers une API compatible OpenAI (ex. Groq ou RodiumAi) est disponible avec des clés valides renseignées dans `.env`.
   - En environnement de production souveraine, un serveur d'inférence local compatible OpenAI (ex. Ollama ou vLLM servant Gemma) est opérationnel sur le réseau interne.
4. **Comportement du client HTTP** : Le client (application web front-end ou script de test) est conçu pour gérer le mode asynchrone par polling HTTP périodique (consultation répétée des routes de statut suite à la réception d'un code HTTP 202).
5. **Disponibilité de l'analyste pour les portes de contrôle** : L'analyste humain est présent et disponible pour examiner et valider les plans d'investigation (porte H1), les constats (porte H2) et les demandes d'autorisation d'envoi externe pseudonymisé (porte H3).

---

## 8. Questions ouvertes arbitrées et résolues

L'ensemble des points identifiés ont été formellement arbitrés et résolus par les décisions d'architecture acceptées (ADR-0004 à ADR-0010) :

1. **Moteur technique de génération des rapports PDF** :
   - *Résolution (ADR-0004)* : Les formats générés et scellés côté back-end sont restreints à `markdown` et `json` pour le MVP. L'export PDF direct compilé est différé en post-MVP, l'impression pouvant s'effectuer côté client.

2. **Politique détaillée de gestion des comptes et sécurité des mots de passe** :
   - *Résolution (ADR-0006)* : Jeton d'accès JWT unique d'une durée de validité de 8 heures, modèle sans état (*stateless*), et politique de mot de passe à 12 caractères minimum avec complexité (majuscule, minuscule, chiffre, symbole).

3. **Intervalle et en-têtes de polling pour les tâches asynchrones** :
   - *Résolution (ADR-0008)* : Normalisation systématique de l'en-tête standard `Retry-After: 3` sur toutes les réponses HTTP 202, avec cadence de polling recommandée de 3 à 5 secondes côté client.

4. **Taille maximale des téléversements de preuves et quotas de stockage** :
   - *Résolution (ADR-0005)* : Streaming asynchrone par morceaux de 64 Ko, scellement SHA-256 au fil de l'eau, et plafond configurable fixé à 16 Go (`MAX_EVIDENCE_SIZE_GB`).

5. **Modalités d'alerte de l'analyste pour les portes de contrôle H1, H2 et H3** :
   - *Résolution (ADR-0008 / Architecture)* : L'analyste prend connaissance des demandes de validation via l'état de l'`InvestigationRun` exposé sur l'API et rafraîchi par polling REST standard, sans WebSockets ni SSE.

6. **Procédure de prise en charge des symboles Volatility 3 pour versions Windows non répertoriées** :
   - *Résolution (ADR-0009)* : Répertoire `/opt/volatility3/custom_symbols` monté en volume lecture seule pour l'injection hors-ligne de tables ISF validées par empreinte SHA-256 sans jamais lever l'isolation réseau (`network_mode: none`).

7. **Règles de rétention et politique de purge des preuves et dossiers archivés** :
   - *Résolution (ADR-0010)* : Conservation locale indéfinie sur volume persistant scellé pour le MVP afin de sanctuariser la chaîne de traçabilité des preuves, avec surveillance de l'espace disque sur l'endpoint `/health`.

---

## 9. Validations et Sign-offs Formels (Jalon BMAD 11.1)

Le présent Product Requirement Document (PRD) du back-end IRYX a été formellement examiné, validé et approuvé par les trois rôles de gouvernance projet :

| Rôle | Validateur | Décision | Date |
|---|---|---|---|
| **Team Lead** | Abdoul-Gafar AMADOU | **VALIDÉ** | 2026-11-23 |
| **AI / Tech Lead** | Abdoul-Gafar AMADOU | **VALIDÉ** | 2026-11-23 |
| **Product Lead** | Abdoul-Gafar AMADOU | **VALIDÉ** | 2026-11-23 |

