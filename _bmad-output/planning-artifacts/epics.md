---
status: final
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
  - docs/00-contexte-produit.md
  - docs/01-architecture-technique.md
  - docs/02-agents-et-outils.md
  - docs/03-modele-de-donnees.md
  - docs/04-securite-et-gates.md
  - docs/05-conventions-backend.md
  - docs/06-perimetre-mvp.md
  - docs/07-api-llm-et-dependances.md
  - docs/08-architecture-backend.md
---

# IRYX - Découpage en Épics et Récits Utilisateurs (Epics & Stories)

## Vue d'ensemble

Ce document présente la décomposition exhaustive et détaillée des exigences du Product Requirement Document (PRD) et du Document d'Architecture Technique d'**IRYX (Back-End)** en récits utilisateurs (*user stories*) actionnables, organisés par valeur métier et regroupés selon le découpage imposé de 9 épics (E1 à E9).

Chaque récit utilisateur respecte les principes directeurs suivants :
1. **Format standardisé** : « En tant que [rôle], je veux [action], afin de [bénéfice] ».
2. **Dimensionnement maîtrisé** : chaque story est calibrée pour être réalisée en une journée de développement au maximum par un développeur ou agent développeur.
3. **Critères d'acceptation vérifiables** : spécification systématique des conditions nominales (Given/When/Then), des cas d'erreur avec schémas de réponse HTTP standardisés, et des cas d'autorisation / contrôle d'accès strict.
4. **Traçabilité technique** : rattachement explicite aux exigences fonctionnelles (FR1 à FR27), aux exigences non fonctionnelles (NFR) et aux décisions d'architecture figées (D-01 à D-26).
5. **Respect strict du périmètre MVP** : exclusion formelle de toute technologie, outil ou fonctionnalité reportée hors MVP (exclusion des analyseurs YARA/pytsk3, absence de WebSockets/SSE au profit du polling REST, aucun microservice ni orchestration Kubernetes).

---

## 1. Inventaire des Exigences

### 1.1 Exigences Fonctionnelles (FR1 à FR27)

| Identifiant | Intitulé de l'exigence | Module métier cible |
|---|---|---|
| **FR1** | Authentification et émission de jetons JWT | `auth` |
| **FR2** | Gestion des organisations et adhésions RBAC | `auth` / `organizations` |
| **FR3** | Gestion du cycle de vie des dossiers d'investigation | `cases` |
| **FR4** | Contrôle d'accès strict au niveau dossier | `cases` |
| **FR5** | Ingestion asynchrone des preuves numériques | `evidences` / `ingestion` |
| **FR6** | Scellement cryptographique SHA-256 et identification de type | `evidences` |
| **FR7** | Stockage immuable en lecture seule des preuves | `evidences` |
| **FR8** | Registre et invocation sécurisée des outils forensiques | `gateway` / `tools` |
| **FR9** | Traçabilité et audit d'exécution d'outils | `gateway` / `tools` |
| **FR10** | Troncature et résumé des résultats pour les agents | `gateway` / `tools` |
| **FR11** | Analyseur de logs texte et CSV | `gateway` / `tools` |
| **FR12** | Analyseur d'événements Windows EVTX | `gateway` / `tools` |
| **FR13** | Analyseur de Registre Windows | `gateway` / `tools` |
| **FR14** | Analyseur d'artefacts d'exécution Prefetch | `gateway` / `tools` |
| **FR15** | Analyseur de mémoire vive Volatility 3 (5 plugins, symboles ISF préchargés) | `gateway` / `tools` |
| **FR16** | Orchestration de session d'enquête par machine d'états LangGraph | `orchestrator` |
| **FR17** | Boucle d'agents Planner - Executor | `orchestrator` / `agents` |
| **FR18** | Porte de contrôle humain H1 - Validation du plan d'action | `orchestrator` |
| **FR19** | Porte de contrôle humain H2 - Validation des constats (Findings) | `orchestrator` / `findings` |
| **FR20** | Porte de contrôle humain H3 - Autorisation d'envoi externe | `orchestrator` / `reports` |
| **FR21** | Persistance et reprise sur interruption | `orchestrator` |
| **FR22** | Formulation et structuration des constats d'investigation (Analyst) | `analytics` / `findings` |
| **FR23** | Vérification déterministe formelle des constats (Verifier sans LLM) | `analytics` / `findings` |
| **FR24** | Corrélation temporelle et timeline unifiée UTC | `analytics` / `observations` |
| **FR25** | Pseudonymisation déterministe des données (Microsoft Presidio) | `reporting` |
| **FR26** | Rédaction et scellement du rapport d'incident | `reporting` |
| **FR27** | Journalisation d'audit immuable en ajout seul (`AuditEvent`) | `audit` |

---

### 1.2 Exigences Non Fonctionnelles (NFR)

- **NFR-PERF-01** : Délégation asynchrone des tâches longues (> 500 ms) via Celery et Redis (code HTTP 202).
- **NFR-PERF-02** : Timeouts stricts d'exécution des outils forensiques (logs/EVTX/Registre/Prefetch <= 30s ; Volatility 3 <= 600s).
- **NFR-PERF-03** : Paramètres de résilience et timeout des appels LLM (timeout 60s, 3 retries avec backoff exponentiel Tenacity).
- **NFR-PERF-04** : Durée maximale d'une session d'investigation (timeout global 3600s / 1 heure).
- **NFR-PERF-05** : Limites structurelles du plan et des itérations d'enquête (max 10 étapes par plan, max 5 itérations de boucle).
- **NFR-PERF-06** : Troncature de contexte pour les agents (résumé et extrait borné à 8 Ko / 200 lignes max pour éviter le dépassement de fenêtre de contexte).
- **NFR-PERF-07** : Pagination systématique des listes (`limit` max 100, `offset`).
- **NFR-SEC-01** : Scellement et lecture seule des preuves brutes (`chmod 0440`, montage Docker `ro`).
- **NFR-SEC-02** : Confinement non-root (`uid 10001:gid 10001`), `cap_drop: ALL`, coupure réseau (`network_mode: none`) et exécution sans shell (`shell=False`).
- **NFR-SEC-03** : Immutabilité absolue de la table d'audit (trigger SQL rejetant tout UPDATE et DELETE).
- **NFR-SEC-04** : Hachage fort des mots de passe avec l'algorithme argon2 (`pwdlib[argon2]`).
- **NFR-SEC-05** : Cloisonnement strict multi-utilisateurs et isolation par dossier (Zero Leak).
- **NFR-SEC-06** : Immunisation contre l'injection indirecte de prompts (données forensiques traitées comme passives et délimitées).
- **NFR-SEC-07** : Pseudonymisation intégrale préalable à tout transfert externe (Microsoft Presidio).
- **NFR-SEC-08** : Intégrité et symboles Volatility 3 hors ligne (`windows.zip` pack ISF vérifié par SHA-256).
- **NFR-REL-01** : Déterminisme absolu du composant Verifier (pure validation relationnelle SQL sans LLM).
- **NFR-REL-02** : Journalisation structurée JSON sans secrets (zéro mot de passe, clé d'API ou token dans les logs).
- **NFR-QA-01** : Typage strict Python et conformité Ruff (0 avertissement, 0 erreur).
- **NFR-QA-02** : Couverture de tests automatisés (tests unitaires, tests d'intégration API, tests de sécurité d'isolation).

---

### 1.3 Tableau des Décisions Technologiques Figées (D-01 à D-26)

| ID | Domaine / Composant | Technologie retenue | Rôle dans l'architecture |
|---|---|---|---|
| **D-01** | Langage d'exécution | Python 3.12 | Socle applicatif |
| **D-02** | Gestionnaire de dépendances | `uv` (v0.12.8) | Gestion des packages et lockfile |
| **D-03** | Framework HTTP | FastAPI (>=0.115.0) | API REST asynchrone |
| **D-04** | Schémas et configuration | Pydantic v2 & `pydantic-settings` | Validation de données et config env |
| **D-05** | Base de données | PostgreSQL 16 | Persistance relationnelle ACID |
| **D-06** | Accès base de données | SQLAlchemy 2.x & `psycopg` 3 | ORM et requêtage relationnel |
| **D-07** | Migrations de schéma | Alembic (>=1.13.0) | Gestion tracée des évolutions SQL |
| **D-08** | Tâches d'arrière-plan | Celery (>=5.4.0) & Redis 7 | Exécution asynchrone déportée |
| **D-09** | Orchestration d'agents | LangGraph (>=0.2.20) | Machine d'états d'investigation |
| **D-10** | Client LLM unifié | SDK officiel `openai` (>=1.50.0) | Inférence LLM uniforme par rôle |
| **D-11** | Réessais LLM | `tenacity` (>=9.0.0) | Backoff exponentiel sur appels LLM |
| **D-12** | Authentification | `PyJWT` (>=2.9.0) | Signature et validation de jetons JWT |
| **D-13** | Hachage de mot de passe | `pwdlib[argon2]` (>=0.2.0) | Chiffrement sécurisé argon2 |
| **D-14** | Empreinte cryptographique | `hashlib` (Standard) | Scellement SHA-256 |
| **D-15** | Détection type binaire | `filetype` (>=1.2.0) | Identification MIME par magic numbers |
| **D-16** | Analyseur EVTX | `python-evtx` (>=0.7.4) | Parseur pur Python des journaux Windows |
| **D-17** | Analyseur Registre | `regipy` (>=5.1.0) | Parseur pur Python des ruches Windows |
| **D-18** | Analyseur Prefetch | `dissect` (>=3.8.0) | Parseur d'artefacts d'exécution Windows |
| **D-19** | Pseudonymisation | `presidio-analyzer` & `presidio-anonymizer` | Détection et anonymisation PII |
| **D-20** | Tests automatisés | `pytest`, `pytest-asyncio`, `httpx` | Validation unitaire et intégration |
| **D-21** | Qualité de code | `ruff` (>=0.6.0) | Formatage et analyse statique |
| **D-22** | Déploiement local | Docker Compose (>=v5.3.0) | Topologie conteneurisée mono-serveur |
| **D-23** | Journalisation | Standard library `logging` | JSON structuré sans secrets |
| **D-24** | Suivi temps réel | Polling HTTP REST | Consultations régulières d'état (pas de WS/SSE) |
| **D-25** | Analyseurs différés | Sleuth Kit, YARA | **Exclus formellement du MVP** |
| **D-26** | Analyseur RAM | `volatility3 == 2.7.0` | Extraction mémoire hors-ligne avec symboles ISF |

---

## 2. Matrice de Couverture des Exigences Fonctionnelles (FR Coverage Map)

| Exigence | Intitulé | Épic principal | Story associée | Décisions mobilisées |
|---|---|---|---|---|
| **FR1** | Authentification et émission de jetons JWT | **E1** | Story 1.3, Story 1.4 | D-03, D-04, D-12, D-13 |
| **FR2** | Gestion des organisations et adhésions RBAC | **E2** | Story 2.1, Story 2.2 | D-03, D-04, D-05, D-06, D-07 |
| **FR3** | Gestion du cycle de vie des dossiers d'investigation | **E2** | Story 2.3 | D-03, D-04, D-05, D-06, D-07 |
| **FR4** | Contrôle d'accès strict au niveau dossier | **E2** | Story 2.4 | D-03, D-06, D-12 |
| **FR5** | Ingestion asynchrone des preuves numériques | **E3** | Story 3.1, Story 3.2, Story 3.3 | D-03, D-04, D-08 |
| **FR6** | Scellement cryptographique SHA-256 et détection de type | **E3** | Story 3.3 | D-08, D-14, D-15 |
| **FR7** | Stockage immuable en lecture seule des preuves | **E3** | Story 3.2, Story 3.3 | D-08, D-14 |
| **FR8** | Registre et invocation sécurisée des outils forensiques | **E4** | Story 4.1 | D-04, D-06, D-14 |
| **FR9** | Traçabilité et audit d'exécution d'outils | **E4** | Story 4.1, Story 4.7 | D-03, D-06, D-14 |
| **FR10** | Troncature et résumé des résultats pour les agents | **E4** | Story 4.7 | D-04, D-06 |
| **FR11** | Analyseur de logs texte et CSV | **E4** | Story 4.2 | D-04, D-06 |
| **FR12** | Analyseur d'événements Windows EVTX | **E4** | Story 4.3 | D-04, D-06, D-16 |
| **FR13** | Analyseur de Registre Windows | **E4** | Story 4.4 | D-04, D-06, D-17 |
| **FR14** | Analyseur d'artefacts d'exécution Prefetch | **E4** | Story 4.5 | D-04, D-06, D-18 |
| **FR15** | Analyseur de mémoire vive Volatility 3 | **E4** | Story 4.6 | D-04, D-06, D-26 |
| **FR16** | Orchestration de session d'enquête par LangGraph | **E5** | Story 5.2 | D-04, D-06, D-09 |
| **FR17** | Boucle d'agents Planner - Executor | **E5** | Story 5.3, Story 5.5 | D-08, D-09, D-10, D-11 |
| **FR18** | Porte de contrôle humain H1 (Validation du plan) | **E5** | Story 5.4 | D-03, D-04, D-09, D-24 |
| **FR19** | Porte de contrôle humain H2 (Validation des findings) | **E6** | Story 6.4 | D-03, D-04, D-06, D-09, D-24 |
| **FR20** | Porte de contrôle humain H3 (Autorisation envoi externe) | **E8** | Story 8.2 | D-03, D-04, D-09, D-19 |
| **FR21** | Persistance et reprise sur interruption | **E5** | Story 5.6 | D-05, D-06, D-09 |
| **FR22** | Formulation et structuration des constats (Analyst) | **E6** | Story 6.1, Story 6.2 | D-04, D-06, D-09, D-10 |
| **FR23** | Vérification déterministe formelle (Verifier) | **E6** | Story 6.3 | D-06, D-20 |
| **FR24** | Corrélation temporelle et timeline unifiée UTC | **E7** | Story 7.1, Story 7.2, Story 7.3 | D-03, D-04, D-05, D-06 |
| **FR25** | Pseudonymisation déterministe (Microsoft Presidio) | **E8** | Story 8.1 | D-04, D-19 |
| **FR26** | Rédaction et scellement du rapport d'incident | **E8** | Story 8.3, Story 8.4 | D-03, D-04, D-06, D-10, D-14 |
| **FR27** | Journalisation d'audit immuable en ajout seul | **E8** | Story 8.5 | D-05, D-06, D-07, D-14, D-23 |

---

## 3. Liste des Épics Imposés (E1 à E9)

| Épic | Intitulé / Objet | Modules concernés | Dépendances | Objectif principal |
|---|---|---|---|---|
| **E1** | Socle, configuration, sécurité de base | `core`, `identity` (`auth`) | Aucune | Établir le squelette FastAPI, la configuration typée, la connexion PostgreSQL, Alembic, le logging JSON et l'authentification JWT/argon2. |
| **E2** | Organisations, dossiers et membres | `organizations`, `cases` | E1 | Implémenter le multi-organisation, les rôles RBAC, la gestion du cycle de vie des dossiers et l'isolation stricte par dossier (`verify_case_access`). |
| **E3** | Preuves et ingestion | `evidence`, `ingestion` | E1, E2 | Fournir l'upload de preuves numériques, la délégation asynchrone Celery/Redis, le scellement SHA-256, la détection `filetype` et le stockage en lecture seule. |
| **E4** | Outils et Gateway | `tools`, `gateway` | E1, E2, E3 | Construire le registre d'outils forensiques sécurisé, les parseurs purs Python (logs, EVTX, Registre, Prefetch), l'analyseur Volatility 3, la traçabilité `ToolExecution` et la normalisation en `Observation`. |
| **E5** | Orchestrateur, agents et gates | `orchestrator`, `agents` | E1, E2, E3, E4 | Mettre en œuvre le graphe d'états LangGraph, le client LLM OpenAI unifié, la boucle Planner-Executor, la porte de validation humaine H1 et la persistance/reprise d'état. |
| **E6** | Findings et revue humaine (H2) | `findings`, `analytics` | E1, E2, E3, E4, E5 | Permettre à l'agent Analyst de formuler des constats, faire valider leur intégrité de façon déterministe par le Verifier (sans LLM), et arbitrer les findings à la porte H2. |
| **E7** | Corrélation et chronologie | `findings` (dérivé), `observations` | E1, E2, E3, E4, E6 | Reconstruire la timeline globale unifiée ordonnée en UTC exclusivement dérivée des faits techniques et relier les findings aux événements sources. |
| **E8** | Rapports et journal d'audit | `reports`, `audit`, `reporting` | E1, E2, E3, E4, E5, E6, E7 | Pseudonymiser les données via Presidio, valider la porte H3, rédiger et sceller les rapports Markdown/JSON, et verrouiller le journal d'audit immuable en ajout seul. |
| **E9** | Déploiement et démonstration | `docker`, `déploiement` | E1 à E8 | Orchestrer l'ensemble de la pile via Docker Compose mono-serveur, appliquer les restrictions non-root et réseau coupé, et fournir le scénario de validation de bout en bout. |

---

## 4. Spécification Détaillée des Épics et Récits Utilisateurs

---

### Epic 1 : E1 - Socle, configuration, sécurité de base

- **Modules concernés** : `core`, `identity` (`auth`)
- **Objectif** : Initialiser le socle technique du monolithe modulaire FastAPI, la gestion de configuration centralisée Pydantic Settings, la connexion relationnelle PostgreSQL 16 via SQLAlchemy 2.x et psycopg 3, le versionnement de schéma Alembic, la journalisation structurée JSON sans secrets, et le système d'authentification utilisateur par jetons JWT signés (PyJWT) et hachage fort de mots de passe argon2.
- **FR couvertes** : FR1
- **NFR couvertes** : NFR-SEC-04, NFR-REL-02, NFR-QA-01, NFR-QA-02
- **Dépendances** : Aucune (Socle initial)
- **Critères de fin d'épic (Definition of Done)** :
  1. Le serveur FastAPI démarre sans erreur via `uv run` et répond HTTP 200 sur `/health`.
  2. Toutes les configurations sont typées via `pydantic-settings` et validées au démarrage.
  3. Les migrations Alembic initiales créent la table `User` et gèrent l'historique des versions.
  4. Les logs applicatifs sont sérialisés en JSON structuré et masquent tout secret ou mot de passe.
  5. Un utilisateur peut s'authentifier via `/api/v1/auth/login` et obtenir un JWT signé valide vérifiable par `get_current_user`.
  6. La suite de tests unitaires et d'intégration passe à 100% avec 0 warning Ruff.

#### Story 1.1 : Initialisation du socle applicatif FastAPI, configuration Pydantic Settings et logging JSON
**En tant que** développeur de la plateforme IRYX,  
**Je veux** disposer d'un socle applicatif FastAPI structuré avec configuration centralisée typée, middleware d'erreurs standardisé et journalisation JSON,  
**Afin d'**assurer une base d'exécution robuste, sans fuite d'informations sensibles et conforme aux conventions du projet.

- **Décisions d'architecture mobilisées** : D-01, D-02, D-03, D-04, D-21, D-23.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** les dépendances du projet installées via `uv sync` d'après le lockfile,
    - **When** l'application FastAPI est instanciée et lancée,
    - **Then** une requête `GET /health` renvoie un statut HTTP 200 avec le corps JSON `{"status": "ok", "version": "0.1.0"}`.
    - **And** tous les messages de journalisation émis dans la console sont formatés en JSON structuré contenant les champs `timestamp`, `level`, `logger`, `message` et `context` sans aucune clé API ni secret.
  - **Cas d'erreur et validation :**
    - **Given** une variable d'environnement obligatoire manquante ou invalide dans le fichier `.env`,
    - **When** l'application démarre,
    - **Then** `pydantic-settings` lève une exception explicite et bloque le démarrage avec un message d'erreur clair sans afficher de valeurs sensibles.
    - **And** toute exception non interceptée renvoie un code HTTP 500 avec le schéma JSON standardisé `{"error": {"code": "INTERNAL_SERVER_ERROR", "message": "Une erreur inattendue est survenue."}}` sans trace de pile (stack trace) ni chemin local du système.
  - **Cas d'autorisation et sécurité :**
    - **Given** le middleware de gestion des erreurs actif,
    - **When** une requête malformée contenant des en-têtes ou des corps suspects est soumise,
    - **Then** FastAPI renvoie une réponse HTTP 422 standardisée sans divulguer la structure interne du code serveur.

#### Story 1.2 : Infrastructure de base de données PostgreSQL 16, sessions SQLAlchemy 2.x et initialisation Alembic
**En tant que** développeur back-end,  
**Je veux** configurer la connexion à PostgreSQL 16 avec SQLAlchemy 2.x, le pilote natif psycopg 3 et le gestionnaire de migrations Alembic,  
**Afin d'**assurer la persistance transactionnelle des données et la traçabilité des évolutions de schéma sans utiliser `create_all`.

- **Décisions d'architecture mobilisées** : D-05, D-06, D-07, D-20.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** une instance PostgreSQL 16 active et accessible via les variables de configuration `DATABASE_URL`,
    - **When** l'injection de dépendances FastAPI `get_db` est invoquée dans une route de test,
    - **Then** une session SQLAlchemy 2.x fonctionnelle est fournie et fermée automatiquement à la fin du cycle de vie de la requête.
    - **And** l'exécution de la commande `uv run alembic upgrade head` applique l'historique de migrations et crée la table `alembic_version` sans aucune erreur.
  - **Cas d'erreur et validation :**
    - **Given** une indisponibilité temporaire ou des identifiants PostgreSQL erronés,
    - **When** l'application tente d'établir une connexion,
    - **Then** une erreur de connexion typée est consignée dans les logs JSON avec le niveau `CRITICAL`, sans faire fuiter le mot de passe de connexion.
    - **And** les endpoints dépendants de la base retournent une réponse HTTP 503 Service Unavailable avec le code d'erreur `DATABASE_UNAVAILABLE`.
  - **Cas d'autorisation et sécurité :**
    - **Given** l'application en cours d'exécution,
    - **When** la commande de démarrage est exécutée,
    - **Then** aucune instruction `Base.metadata.create_all()` n'est appelée dans le code source de production (règle 9 de docs/05).

#### Story 1.3 : Modèle utilisateur `User`, hachage sécurisé argon2 et migration initiale
**En tant qu'**administrateur système,  
**Je veux** que les comptes utilisateurs soient modélisés avec persistance en base et mots de passe hachés avec l'algorithme argon2,  
**Afin de** garantir une protection de l'état de l'art contre les attaques par dictionnaire ou force brute.

- **Décisions d'architecture mobilisées** : D-04, D-05, D-06, D-07, D-13.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la migration Alembic `001_create_user_table` appliquée,
    - **When** un utilisateur est inséré avec un mot de passe clair via le service de sécurité `hash_password`,
    - **Then** le champ `hashed_password` dans la table `users` commence par le préfixe argon2 `$argon2id$`, calculé via la bibliothèque `pwdlib[argon2]`.
    - **And** les champs `id` (UUIDv4), `email` (unique et indexé), `is_active` (True par défaut), `created_at` et `updated_at` (UTC) sont persistés conformément à `docs/03`.
  - **Cas d'erreur et validation :**
    - **Given** une tentative d'insertion d'un utilisateur avec une adresse email déjà enregistrée en base,
    - **When** l'opération est validée en base,
    - **Then** une violation de contrainte d'unicité SQL est interceptée par le service et convertie en exception métier `UserAlreadyExistsException`.
  - **Cas d'autorisation et sécurité :**
    - **Given** un mot de passe soumis lors de l'enregistrement de moins de 12 caractères,
    - **When** le schéma Pydantic `UserCreate` valide la charge utile,
    - **Then** la validation échoue avec un code HTTP 422 précisant l'exigence de complexité minimale.

#### Story 1.4 : Service d'authentification JWT et endpoint de connexion `/api/v1/auth/login`
**En tant qu'**analyste SOC ou enquêteur,  
**Je veux** m'authentifier avec mes identifiants (email et mot de passe) sur l'endpoint `/api/v1/auth/login` pour recevoir un jeton d'accès JWT signé,  
**Afin d'**accéder de façon sécurisée aux points d'accès protégés de l'API IRYX.

- **Décisions d'architecture mobilisées** : D-03, D-04, D-06, D-12, D-13, D-20.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** un utilisateur actif enregistré avec l'email `analyst@iryx.local` et son mot de passe valide,
    - **When** une requête `POST /api/v1/auth/login` est émise avec ces identifiants valides,
    - **Then** le serveur répond HTTP 200 avec le corps JSON contenant `access_token`, `token_type: "bearer"` et `expires_in: 3600`.
    - **And** le jeton est signé avec la clé secrète applicative via `PyJWT` (D-12) et contient dans son payload les revendications standard `sub` (User UUID), `email`, `iat` et `exp`.
    - **And** l'injection de dépendances FastAPI `get_current_user` décode le jeton et injecte l'instance `User` correspondante.
  - **Cas d'erreur et validation :**
    - **Given** un mot de passe incorrect ou un email non répertorié en base,
    - **When** la requête `POST /api/v1/auth/login` est soumise,
    - **Then** le serveur retourne un code HTTP 401 Unauthorized avec le message générique `{"error": {"code": "INVALID_CREDENTIALS", "message": "Identifiants invalides."}}` sans préciser si l'erreur provient de l'email ou du mot de passe.
  - **Cas d'autorisation et sécurité :**
    - **Given** un utilisateur dont le champ `is_active` est défini à `False`,
    - **When** il soumet des identifiants valides,
    - **Then** le serveur retourne HTTP 403 Forbidden avec le code `INACTIVE_ACCOUNT`.
    - **And** une requête sur une route protégée sans en-tête `Authorization: Bearer <token>` ou avec un jeton expiré renvoie immédiatement HTTP 401 Unauthorized.

---

### Epic 2 : E2 - Organisations, dossiers et membres

- **Modules concernés** : `organizations`, `cases`, `auth`
- **Objectif** : Implémenter la gestion multi-organisationnelle, les adhésions (`Membership`) avec attribution des rôles RBAC (`admin`, `analyst`, `investigator`, `viewer`), ainsi que la création, la consultation et la gestion du cycle de vie des dossiers d'investigation (`Case` : `open`, `in_progress`, `review`, `closed`), en imposant un contrôle d'accès strict au niveau route (`verify_case_access`).
- **FR couvertes** : FR2, FR3, FR4
- **NFR couvertes** : NFR-SEC-05, NFR-PERF-07, NFR-QA-01, NFR-QA-02
- **Dépendances** : E1
- **Critères de fin d'épic (Definition of Done)** :
  1. Les modèles `Organization`, `Membership` et `Case` sont créés avec leurs tables via Alembic.
  2. Un utilisateur `admin` peut créer une organisation et y inscrire des membres avec un rôle précis.
  3. Un utilisateur habilité peut créer un dossier rattaché à son organisation et faire évoluer son statut selon les transitions autorisées.
  4. La dépendance FastAPI `verify_case_access` est active et prouve en tests de sécurité l'impossibilité absolue pour un membre d'une organisation A d'accéder aux dossiers d'une organisation B (Zero Leak).
  5. Toutes les listes de dossiers et de membres sont paginées selon NFR-PERF-07.

#### Story 2.1 : Modèles `Organization` et `Membership`, migration Alembic et schémas Pydantic
**En tant que** développeur back-end,  
**Je veux** définir les modèles SQLAlchemy et schémas Pydantic pour les organisations et les adhésions avec rôles RBAC,  
**Afin d'**établir les structures de données relationnelles du cloisonnement multi-utilisateurs.

- **Décisions d'architecture mobilisées** : D-04, D-05, D-06, D-07.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la migration Alembic `002_create_org_and_membership_tables` exécutée,
    - **When** les tables `organizations` et `memberships` sont inspectées,
    - **Then** la table `organizations` comporte les colonnes `id` (UUID), `name` (String non nul), `created_at` et `updated_at` (UTC).
    - **And** la table `memberships` comporte les clés étrangères `organization_id` (vers `organizations.id`), `user_id` (vers `users.id`), et la colonne `role` avec contrainte CHECK énumérant strictement `admin`, `analyst`, `investigator`, `viewer`.
    - **And** une contrainte d'unicité composite `uq_org_user (organization_id, user_id)` empêche les adhésions en doublon.
  - **Cas d'erreur et validation :**
    - **Given** une tentative de création de membership avec une valeur de rôle invalide (ex. `superuser`),
    - **When** les schémas Pydantic `MembershipCreate` valident la charge utile,
    - **Then** la validation Pydantic v2 rejette la requête avec un statut HTTP 422 Unprocessable Entity en énumérant les rôles licites.
  - **Cas d'autorisation et sécurité :**
    - **Given** la suppression en cascade d'une organisation,
    - **When** une organisation est supprimée,
    - **Then** toutes les adhésions associées sont révoquées sans orphelins en base.

#### Story 2.2 : API de gestion des organisations et attribution des rôles RBAC (FR2)
**En tant qu'**administrateur d'organisation (`admin`),  
**Je veux** créer une organisation, inviter des membres et leur affecter un rôle RBAC via l'API REST,  
**Afin de** structurer les équipes d'investigation et délimiter les prérogatives d'accès.

- **Décisions d'architecture mobilisées** : D-03, D-04, D-06, D-12.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** un utilisateur authentifié possédant le rôle `admin` dans l'organisation,
    - **When** il émet une requête `POST /api/v1/organizations/{org_id}/members` avec le corps `{"user_id": "<uuid>", "role": "analyst"}`,
    - **Then** le serveur répond HTTP 201 Created avec le schéma `MemberOut` contenant l'identifiant du membre, son email et son rôle.
    - **And** une requête `GET /api/v1/organizations/{org_id}/members?limit=20&offset=0` liste les membres avec pagination.
  - **Cas d'erreur et validation :**
    - **Given** une tentative d'ajout d'un utilisateur dont le `user_id` n'existe pas dans la table `users`,
    - **When** la requête est traitée par le service,
    - **Then** le serveur répond HTTP 404 Not Found avec le code `USER_NOT_FOUND`.
    - **And** si l'utilisateur est déjà membre de l'organisation, le serveur répond HTTP 409 Conflict avec le code `MEMBER_ALREADY_EXISTS`.
  - **Cas d'autorisation et sécurité :**
    - **Given** un utilisateur authentifié ayant le rôle `viewer` ou `analyst`,
    - **When** il tente d'ajouter ou de modifier le rôle d'un membre via `POST` ou `PATCH`,
    - **Then** le serveur intercepte la requête via la dépendance `require_role("admin")` et retourne HTTP 403 Forbidden avec le code `INSUFFICIENT_PERMISSIONS`.

#### Story 2.3 : Modèle `Case`, migration Alembic et gestion du cycle de vie des dossiers (FR3)
**En tant qu'**enquêteur ou analyste SOC,  
**Je veux** créer des dossiers d'investigation (`Case`), consulter leur liste et faire évoluer leur statut (`open` -> `in_progress` -> `review` -> `closed`),  
**Afin de** matérialiser le périmètre d'un incident et suivre sa progression opérationnelle.

- **Décisions d'architecture mobilisées** : D-03, D-04, D-05, D-06, D-07, D-12.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la migration Alembic `003_create_case_table` appliquée et un utilisateur membre actif d'une organisation,
    - **When** l'utilisateur soumet `POST /api/v1/organizations/{org_id}/cases` avec le corps `{"title": "Compromission Contrôleur AD", "description": "Activité anormale détectée"}` ,
    - **Then** le serveur répond HTTP 201 Created avec l'entité `Case` contenant son identifiant unique, le statut initial `open`, `created_by` égal à l'utilisateur courant, et ses horodatages UTC.
    - **And** une requête `PATCH /api/v1/cases/{case_id}/status` permet de faire évoluer le statut vers `in_progress`, puis `review`, puis `closed`.
  - **Cas d'erreur et validation :**
    - **Given** un dossier déjà au statut `closed`,
    - **When** un utilisateur tente de modifier son statut vers `in_progress` sans réouverture explicite autorisée,
    - **Then** le service lève une exception de transition invalide et répond HTTP 400 Bad Request avec le code `INVALID_STATUS_TRANSITION`.
    - **And** si le titre est vide ou dépasse 255 caractères, Pydantic renvoie HTTP 422.
  - **Cas d'autorisation et sécurité :**
    - **Given** un utilisateur ayant le rôle `viewer`,
    - **When** il tente de créer un dossier ou d'en modifier le statut,
    - **Then** le serveur répond HTTP 403 Forbidden.

#### Story 2.4 : Dépendance de sécurité `verify_case_access` et isolation stricte par dossier (FR4, NFR-SEC-05)
**En tant que** responsable de la sécurité du système (CISO),  
**Je veux** que toute route manipulant un dossier d'investigation ou ses sous-ressources valide obligatoirement l'appartenance de l'utilisateur à l'organisation détentrice via `verify_case_access`,  
**Afin d'**empêcher strictement toute fuite d'informations entre organisations clientes (Zero Leak).

- **Décisions d'architecture mobilisées** : D-03, D-04, D-06, D-12, D-20.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** un utilisateur authentifié membre de l'organisation détentrice du dossier `case-alpha`,
    - **When** il soumet une requête `GET /api/v1/cases/{case-alpha-id}`,
    - **Then** la dépendance `verify_case_access` valide son affiliation et renvoie les détails du dossier avec HTTP 200 OK.
    - **And** la requête `GET /api/v1/cases` filtre automatiquement les dossiers retournés pour ne renvoyer que ceux des organisations dont l'utilisateur est membre actif, avec pagination (`limit`, `offset`).
  - **Cas d'erreur et validation :**
    - **Given** un identifiant de dossier inexistant au format UUID valide,
    - **When** une requête est soumise,
    - **Then** le serveur répond HTTP 404 Not Found avec le message standardisé `{"error": {"code": "CASE_NOT_FOUND", "message": "Le dossier demandé n'existe pas."}}`.
  - **Cas d'autorisation et sécurité :**
    - **Given** un utilisateur authentifié appartenant exclusivement à l'organisation B,
    - **When** il tente d'accéder au dossier `case-alpha` appartenant à l'organisation A,
    - **Then** la dépendance `verify_case_access` rejette l'accès et répond HTTP 404 Not Found ou HTTP 403 Forbidden (sans divulguer l'existence ou les métadonnées du dossier).
    - **And** un test d'intégration automatisé (`test_cross_tenant_isolation_fails`) valide ce rejet systématique.

---

### Epic 3 : E3 - Preuves et ingestion

- **Modules concernés** : `evidence`, `ingestion` (worker Celery)
- **Objectif** : Implémenter le téléversement multipart des preuves numériques rattachées à un dossier, le scellement cryptographique par calcul d'empreinte SHA-256 (`hashlib`), la détection du type MIME réel par signatures binaires (`filetype`), le stockage sur disque avec permissions en lecture seule, l'interdiction formelle d'écrasement, et la délégation asynchrone des traitements d'ingestion via Celery et Redis avec consultation par polling REST (HTTP 202).
- **FR couvertes** : FR5, FR6, FR7
- **NFR couvertes** : NFR-PERF-01, NFR-SEC-01, NFR-PERF-07, NFR-QA-01, NFR-QA-02
- **Dépendances** : E1, E2
- **Critères de fin d'épic (Definition of Done)** :
  1. Les modèles `Evidence` et `IngestionRun` sont instanciés en base via Alembic.
  2. L'upload d'un fichier de preuve retourne HTTP 202 avec l'URI de suivi d'ingestion.
  3. Le worker Celery calcule le SHA-256 par flux de streaming mémoire sans saturer la RAM.
  4. Le type de fichier est détecté par signature binaire via `filetype` (D-15).
  5. Le fichier sur disque est verrouillé avec des permissions de lecture seule strictes (`chmod 0440`).
  6. Le polling REST `/api/v1/cases/{case_id}/evidences/{evidence_id}/ingestion-status` reflète fidèlement l'état et la progression (0 à 100%).

#### Story 3.1 : Modèles `Evidence` et `IngestionRun`, migrations Alembic et configuration Celery/Redis
**En tant que** développeur back-end,  
**Je veux** créer les modèles SQLAlchemy pour `Evidence` et `IngestionRun` et configurer le broker Celery avec Redis 7,  
**Afin de** préparer l'infrastructure relationnelle et asynchrone nécessaire à l'ingestion des preuves.

- **Décisions d'architecture mobilisées** : D-04, D-05, D-06, D-07, D-08.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la migration Alembic `004_create_evidence_and_ingestion_tables` appliquée,
    - **When** les tables `evidences` et `ingestion_runs` sont inspectées,
    - **Then** la table `evidences` contient `id` (UUID), `case_id` (FK vers `cases.id`), `original_name`, `file_size` (BigInteger), `sha256` (String 64 nullable avant calcul), `detected_type` (String nullable), `imported_by` (FK vers `users.id`), et `created_at`.
    - **And** la table `ingestion_runs` contient `id` (UUID), `evidence_id` (FK), `status` (`pending`, `processing`, `completed`, `failed`), `progress` (0-100), `error_message`, `started_at` et `completed_at`.
    - **And** l'instance Celery se connecte avec succès au broker Redis 7 (`CELERY_BROKER_URL`).
  - **Cas d'erreur et validation :**
    - **Given** le broker Redis injoignable,
    - **When** le worker Celery démarre,
    - **Then** le worker trace l'erreur de connexion dans les logs JSON et tente des reconnexions avec backoff sans crasher silencieusement.
  - **Cas d'autorisation et sécurité :**
    - **Given** les contraintes d'intégrité référentielle,
    - **When** une preuve est référencée,
    - **Then** la suppression accidentelle d'un `Case` ne peut pas laisser de preuves orphelines.

#### Story 3.2 : Endpoint de téléversement de preuves et protection contre l'écrasement (FR5, FR7)
**En tant qu'**enquêteur numérique ou analyste SOC,  
**Je veux** téléverser un fichier de preuve via une requête HTTP multipart sur un dossier autorisé,  
**Afin d'**initier son traitement asynchrone sans bloquer l'interface et sans risquer d'écraser une preuve préexistante.

- **Décisions d'architecture mobilisées** : D-03, D-04, D-06, D-08, D-12, D-24.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** un analyste authentifié ayant accès au dossier `{case_id}`,
    - **When** il soumet une requête `POST /api/v1/cases/{case_id}/evidences` avec un fichier en multipart (`file`) et son nom d'origine,
    - **Then** le serveur enregistre temporairement le fichier dans un répertoire de staging sous un nom physique basé sur un UUID unique (évitant tout écrasement accidentel).
    - **And** le serveur crée l'enregistrement `Evidence` et l'entité `IngestionRun` avec le statut `pending`.
    - **And** une tâche Celery `process_evidence_ingestion` est publiée dans Redis.
    - **And** le serveur répond HTTP 202 Accepted avec l'en-tête `Location` pointant vers l'URL de statut d'ingestion et un corps JSON contenant `evidence_id` et `ingestion_run_id`.
  - **Cas d'erreur et validation :**
    - **Given** une requête multipart ne comportant aucun fichier ou un fichier vide (taille 0 octet),
    - **When** la route valide le flux entrant,
    - **Then** le serveur répond HTTP 400 Bad Request avec le code `EMPTY_FILE_ERROR`.
  - **Cas d'autorisation et sécurité :**
    - **Given** un fichier téléversé portant exactement le même nom qu'un fichier déjà présent dans le dossier,
    - **When** le fichier est reçu,
    - **Then** le système refuse l'écrasement physique, crée une nouvelle entité `Evidence` distincte avec son propre UUID, et trace un avertissement d'audit (docs/04 section 1.3).
    - **And** si l'utilisateur n'a pas accès au dossier, la dépendance `verify_case_access` renvoie HTTP 404/403 avant toute écriture sur disque.

#### Story 3.3 : Tâche Celery d'ingestion : scellement SHA-256, détection `filetype` et verrouillage lecture seule (FR6, FR7, NFR-SEC-01)
**En tant que** système d'investigation IRYX,  
**Je veux** exécuter en tâche de fond le calcul d'empreinte SHA-256, la détection binaire du format et le verrouillage en lecture seule du fichier sur disque,  
**Afin de** sceller cryptographiquement la preuve et garantir sa recevabilité légale et technique.

- **Décisions d'architecture mobilisées** : D-08, D-14, D-15, D-20.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la tâche Celery `process_evidence_ingestion` déclenchée avec un identifiant de preuve valide,
    - **When** la tâche s'exécute sur le worker,
    - **Then** l'état de `IngestionRun` passe à `processing` avec progression 20%.
    - **And** le hash SHA-256 est calculé via `hashlib.sha256()` par flux de blocs de 64 Ko (D-14) et stocké dans `Evidence.sha256`.
    - **And** le type MIME et l'extension réelle sont détectés par inspection d'en-tête binaire via `filetype` (D-15) et enregistrés dans `Evidence.detected_type`.
    - **And** les permissions du fichier sur le système de fichiers sont modifiées avec `chmod 0440` (lecture seule, interdiction d'écriture pour tous les comptes applicatifs, NFR-SEC-01).
    - **And** l'entité `IngestionRun` passe au statut `completed`, avec `progress = 100` et `completed_at` horodaté en UTC.
  - **Cas d'erreur et validation :**
    - **Given** un fichier corrompu ou illisible sur le disque lors de l'exécution du worker,
    - **When** la tâche Celery rencontre une erreur d'entrée/sortie,
    - **Then** l'entité `IngestionRun` passe au statut `failed`, `error_message` contient le descriptif de l'anomalie, et l'erreur est consignée dans les logs JSON structurés.
  - **Cas d'autorisation et sécurité :**
    - **Given** le fichier scellé sur disque avec permissions `0440`,
    - **When** un processus worker ou applicatif tente d'ouvrir le fichier en mode écriture (`open(path, "wb")`),
    - **Then** le système d'exploitation lève immédiatement une `PermissionError`.

#### Story 3.4 : Consultation de l'état d'ingestion par polling REST et consultation paginée des preuves (D-24, NFR-PERF-07)
**En tant qu'**analyste SOC,  
**Je veux** consulter périodiquement l'état d'avancement de l'ingestion d'une preuve et lister l'ensemble des preuves d'un dossier,  
**Afin de** savoir quand la preuve est scellée et prête à être soumise aux outils d'analyse.

- **Décisions d'architecture mobilisées** : D-03, D-04, D-06, D-24.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** une preuve en cours d'ingestion ou terminée,
    - **When** le client interroge `GET /api/v1/cases/{case_id}/evidences/{evidence_id}/ingestion-status` (polling REST conforme D-24),
    - **Then** le serveur répond HTTP 200 avec l'objet JSON `{"status": "completed", "progress": 100, "error_message": null, "sha256": "...", "detected_type": "application/x-executable"}`.
    - **And** une requête `GET /api/v1/cases/{case_id}/evidences?limit=50&offset=0` retourne la liste paginée des preuves du dossier avec le total count dans les métadonnées de réponse.
  - **Cas d'erreur et validation :**
    - **Given** un `evidence_id` n'appartenant pas au `case_id` spécifié dans l'URL,
    - **When** la requête de statut est soumise,
    - **Then** le serveur répond HTTP 404 Not Found avec le code `EVIDENCE_NOT_FOUND_IN_CASE`.
  - **Cas d'autorisation et sécurité :**
    - **Given** un utilisateur non authentifié ou membre d'une organisation tierce,
    - **When** il sollicite l'endpoint d'état ou la liste des preuves,
    - **Then** la requête est rejetée avec HTTP 401 ou HTTP 404/403 sans fuite d'informations.

---

### Epic 4 : E4 - Outils et Gateway

- **Modules concernés** : `tools`, `gateway`
- **Objectif** : Implémenter le registre d'outils forensiques sécurisé de la Gateway, le modèle `ToolExecution` assurant la traçabilité intégrale, les parseurs spécialisés purs Python (logs texte/CSV, événements Windows EVTX via `python-evtx`, Registre Windows via `regipy`, Prefetch via `dissect`), l'analyseur mémoire Volatility 3 (restreint à 5 plugins whitelistés avec symboles ISF préchargés hors-ligne), l'extraction normalisée des faits techniques dans l'entité `Observation`, et la troncature contextuelle adaptée aux agents IA.
- **FR couvertes** : FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15
- **NFR couvertes** : NFR-PERF-02, NFR-PERF-06, NFR-SEC-02, NFR-SEC-08, NFR-QA-01, NFR-QA-02
- **Dépendances** : E1, E2, E3
- **Critères de fin d'épic (Definition of Done)** :
  1. Le registre de la Gateway expose tous les outils intégrés avec schémas de paramètres validés par Pydantic v2.
  2. Aucun outil n'est exécuté via un shell système (`shell=False`, politique sans shell).
  3. Chaque exécution produit un enregistrement immuable dans `ToolExecution` avec calcul de hash SHA-256 du résultat brut et durée en millisecondes.
  4. Les parseurs logs/CSV, EVTX, Registre, Prefetch et Volatility 3 fonctionnent et extraient des entités `Observation` normalisées avec horodatages UTC.
  5. Volatility 3 opère strictement hors-ligne sur les 5 plugins autorisés avec symboles ISF locaux.
  6. Le mécanisme de troncature contextuelle limite les sorties destinées aux agents à 8 Ko / 200 lignes max (NFR-PERF-06).

#### Story 4.1 : Registre de la Gateway forensique, modèle `ToolExecution` et classe de base d'outils (FR8, FR9)
**En tant que** développeur de la plateforme IRYX,  
**Je veux** implémenter la classe de base `BaseTool`, le registre central des outils et la persistance des exécutions dans `ToolExecution`,  
**Afin d'**offrir une interface unifiée, sécurisée, traçable et sans interpréteur de commande (`shell=False`) pour l'ensemble des analyseurs forensiques.

- **Décisions d'architecture mobilisées** : D-04, D-05, D-06, D-07, D-14.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la migration Alembic `005_create_tool_execution_and_observation_tables` appliquée,
    - **When** un outil dérivé de `BaseTool` est exécuté via la Gateway,
    - **Then** ses paramètres entrants sont validés contre son schéma Pydantic v2 dédié.
    - **And** le résultat brut produit est haché via `hashlib.sha256` et le hash est consigné dans `ToolExecution.result_sha256`.
    - **And** un enregistrement est créé dans `tool_executions` comportant `id` (UUID), `case_id`, `tool_name`, `tool_version`, `agent_role`, `parameters` (JSONB), `duration_ms`, et `status: "success"`.
  - **Cas d'erreur et validation :**
    - **Given** un outil dont l'exécution dépasse le temps alloué défini dans sa configuration (NFR-PERF-02),
    - **When** le délai expire,
    - **Then** la Gateway interrompt immédiatement le sous-processus ou la tâche, met à jour `ToolExecution.status` à `timeout` et lève une exception `ToolExecutionTimeoutException`.
  - **Cas d'autorisation et sécurité :**
    - **Given** toute invocation d'outil par la Gateway,
    - **When** des sous-processus sont créés,
    - **Then** ils sont instanciés avec `shell=False` strict et interdiction absolue de toute injection de commandes système.

#### Story 4.2 : Analyseur de logs texte et CSV avec normalisation des horodatages UTC (FR11)
**En tant qu'**analyste SOC ou enquêteur,  
**Je veux** soumettre des fichiers de logs textuels ou tabulaires (CSV, syslog, web access logs) à l'analyseur de logs de la Gateway,  
**Afin d'**extraire automatiquement les événements structurés et normaliser leurs horodatages en UTC dans des entités `Observation`.

- **Décisions d'architecture mobilisées** : D-04, D-06, D-14.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** une preuve de type journal texte ou CSV importée dans un dossier,
    - **When** l'outil `LogCsvParserTool` est exécuté sur cette preuve via la Gateway,
    - **Then** chaque ligne d'événement significative est parsée et normalisée.
    - **And** les horodatages identifiés sont convertis en UTC et renseignés dans `Observation.timestamp_utc`.
    - **And** le contenu technique structuré (adresses IP sources/destinations, codes HTTP, identifiants, messages) est inséré dans `Observation.normalized_content` (JSONB).
    - **And** `Observation.source_location` référence le numéro de ligne ou offset dans le fichier source.
  - **Cas d'erreur et validation :**
    - **Given** un fichier de logs contenant des lignes corrompues ou des horodatages dans un format inconnu,
    - **When** le parseur traite ces entrées,
    - **Then** les lignes corrompues sont ignorées ou marquées en avertissement sans interrompre le traitement du reste du fichier.
  - **Cas d'autorisation et sécurité :**
    - **Given** un fichier de log contenant des caractères d'échappement ou des tentatives de command injection,
    - **When** l'outil extrait les données,
    - **Then** les données sont traitées comme du texte passif sans aucune interprétation par un shell.

#### Story 4.3 : Analyseur de journaux d'événements Windows EVTX (`python-evtx`, FR12)
**En tant qu'**analyste SOC,  
**Je veux** analyser des fichiers de journaux d'événements Windows (`.evtx`) avec le parseur pur Python `python-evtx`,  
**Afin d'**extraire les événements de sécurité critiques (authentifications, créations de processus, modifications de services) sans dépendances binaires externes.

- **Décisions d'architecture mobilisées** : D-04, D-06, D-16.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** un fichier EVTX (`Security.evtx` ou `System.evtx`) ingéré et scellé,
    - **When** l'outil `EvtxParserTool` est invoqué via la Gateway avec ciblage des Event IDs pertinents (ex. 4624, 4625, 4688, 7045, 4104),
    - **Then** le parseur lit la structure binaire native via la bibliothèque `python-evtx` (D-16).
    - **And** pour chaque événement concordant, une entité `Observation` est créée avec `timestamp_utc` extrait de l'en-tête `TimeCreated`, `tool_name = "python-evtx"`, et `normalized_content` contenant `EventID`, `Computer`, `SubjectUserName`, `TargetUserName`, `CommandLine`, etc.
    - **And** le champ `source_location` contient le `RecordId` de l'événement EVTX.
  - **Cas d'erreur et validation :**
    - **Given** un fichier EVTX endommagé ou tronqué,
    - **When** `python-evtx` rencontre un enregistrement corrompu,
    - **Then** l'erreur est consignée dans les métadonnées d'exécution de `ToolExecution` et le parseur poursuit la lecture des blocs suivants si possible.
  - **Cas d'autorisation et sécurité :**
    - **Given** l'exécution de l'analyseur EVTX,
    - **When** le fichier de preuve est accédé,
    - **Then** il est lu exclusivement en mode binaire lecture seule (`rb`) sans possibilité de modification de la source scellée.

#### Story 4.4 : Analyseur de ruches de Registre Windows (`regipy`, FR13)
**En tant qu'**enquêteur numérique,  
**Je veux** extraire les clés de persistance et de configuration à partir de ruches de Registre Windows (`SYSTEM`, `SOFTWARE`, `NTUSER.DAT`) via `regipy`,  
**Afin d'**identifier les mécanismes d'autorun, les comptes créés et les preuves d'exécution.

- **Décisions d'architecture mobilisées** : D-04, D-06, D-17.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** une ruche de registre Windows téléversée comme preuve,
    - **When** l'outil `RegistryParserTool` est invoqué via `regipy` (D-17) avec des sous-clés cibles (ex. `Run`, `RunOnce`, `Services`, `UserAssist`),
    - **Then** le parseur extrait de manière récursive les valeurs de clés et leur date de dernière modification `last_write_time` convertie en UTC.
    - **And** chaque valeur extraite produit une entité `Observation` avec `normalized_content` structuré (`key_path`, `value_name`, `value_data`, `value_type`).
    - **And** `source_location` consigne le chemin exact de la clé de registre.
  - **Cas d'erreur et validation :**
    - **Given** une ruche de registre verrouillée ou dont l'en-tête est incomplet,
    - **When** `regipy` lève une exception de parsing,
    - **Then** l'exécution se termine avec le statut `error` dans `ToolExecution` et le message d'erreur est capturé proprement sans faire planter le worker.
  - **Cas d'autorisation et sécurité :**
    - **Given** les ruches de registre soumises,
    - **When** l'outil analyse les clés de configuration,
    - **Then** aucune information extraite n'est transmise hors de la base de données locale du dossier.

#### Story 4.5 : Analyseur d'artefacts d'exécution Windows Prefetch (`dissect`, FR14)
**En tant qu'**enquêteur DFIR,  
**Je veux** parser les fichiers Windows Prefetch (`.pf`) via la bibliothèque `dissect`,  
**Afin d'**obtenir les preuves irréfutables d'exécution de programmes, la fréquence d'exécution et les horodatages précis.

- **Décisions d'architecture mobilisées** : D-04, D-06, D-18.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** un ou plusieurs fichiers `.pf` ingérés dans un dossier d'enquête,
    - **When** l'outil `PrefetchParserTool` est invoqué via la bibliothèque `dissect` (D-18),
    - **Then** le parseur extrait pour chaque fichier : le nom du binaire exécuté, le hash de chemin Prefetch, le compteur d'exécutions (`run_count`), et jusqu'à 8 horodatages d'exécution antérieurs convertis en UTC.
    - **And** des entités `Observation` sont créées pour chaque exécution enregistrée avec `timestamp_utc`, `tool_name = "dissect.prefetch"`, et la liste des volumes et fichiers chargés en dépendance.
  - **Cas d'erreur et validation :**
    - **Given** un fichier qui n'est pas un fichier Prefetch valide (signature `MAM` ou `SCCA` absente),
    - **When** l'analyseur l'inspecte,
    - **Then** l'outil renvoie une erreur de format non reconnu et trace l'anomalie dans `ToolExecution`.
  - **Cas d'autorisation et sécurité :**
    - **Given** l'analyse de fichiers Prefetch,
    - **When** les chemins de fichiers référencés sont extraits,
    - **Then** ils sont assainis et encapsulés sans risque de traversée de répertoire.

#### Story 4.6 : Analyseur de mémoire vive Volatility 3 avec symboles ISF hors-ligne (FR15, NFR-SEC-08)
**En tant qu'**analyste DFIR senior,  
**Je veux** exécuter l'analyse de dumps mémoire vive via Volatility 3 restreint à 5 plugins whitelistés avec symboles ISF préchargés en mode air-gapped,  
**Afin d'**identifier les processus malveillants, les lignes de commande injectées et les sockets réseau sans connexion Internet.

- **Décisions d'architecture mobilisées** : D-04, D-06, D-26.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** une image mémoire vive Windows téléversée et la présence du pack officiel de symboles ISF `windows.zip` préchargé localement dans `/opt/volatility3/symbols`,
    - **When** l'outil `Volatility3Tool` est invoqué avec un plugin parmi les 5 autorisés (`windows.info`, `windows.pslist`/`windows.pstree`, `windows.cmdline`, `windows.netscan`, `windows.malware.malfind`),
    - **Then** Volatility 3 (v2.7.0) s'exécute avec les symboles locaux hors ligne (sans tentative de contact réseau, NFR-SEC-02).
    - **And** la sortie structurée du plugin est extraite et convertie en entités `Observation` normalisées (arborescence de processus, PID, PPID, commandes exécutées, connexions IP distantes, zones injectées).
    - **And** l'exécution est tracée dans `ToolExecution` avec statut `success`.
  - **Cas d'erreur et validation :**
    - **Given** une demande d'exécution d'un plugin hors de la liste blanche (ex. `windows.mimikatz` ou `linux.bash`),
    - **When** la Gateway valide la demande,
    - **Then** la Gateway refuse immédiatement l'exécution avec une erreur `PLUGIN_NOT_WHITELISTED`.
    - **And** si l'analyse mémoire dépasse le délai strict de 600 secondes (NFR-PERF-02), l'opération est arrêtée avec le statut `timeout`.
  - **Cas d'autorisation et sécurité :**
    - **Given** l'environnement d'exécution du worker de traitement,
    - **When** Volatility tourne,
    - **Then** aucun accès réseau n'est disponible (`network_mode: none`) et le conteneur tourne sous le compte non-root `uid 10001` (NFR-SEC-02).

#### Story 4.7 : Troncature contextuelle, résumé des résultats d'outils et endpoints de consultation (FR9, FR10, NFR-PERF-06)
**En tant qu'**agent d'orchestration IA ou analyste consultant les résultats,  
**Je veux** que les sorties d'outils volumineuses soient tronquées et résumées pour l'injection dans le contexte des LLM tout en conservant le résultat complet en base,  
**Afin d'**éviter le dépassement de la fenêtre de contexte des agents tout en permettant à l'analyste de consulter l'intégralité des preuves.

- **Décisions d'architecture mobilisées** : D-03, D-04, D-06, D-24.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** un outil produisant une sortie volumineuse (ex. 50 000 lignes d'EVTX ou 5 Mo de logs),
    - **When** la Gateway persiste le résultat et prépare la charge utile pour l'agent,
    - **Then** le résultat complet est conservé ou référencé sous son hash SHA-256 dans `ToolExecution`.
    - **And** la Gateway génère un résumé textuel borné à un maximum strict de 8 Ko ou 200 lignes significatives (NFR-PERF-06) avec un avertissement explicite `[TRUNCATED: X éléments masqués. Consulter Observation pour la totalité]`.
    - **And** les endpoints `GET /api/v1/cases/{case_id}/tool-executions` et `GET /api/v1/cases/{case_id}/observations` permettent à l'analyste d'interroger la totalité des données avec pagination (`limit`, `offset`) et filtres par outil ou période.
  - **Cas d'erreur et validation :**
    - **Given** des paramètres de filtrage invalides (ex. format de date non ISO-8601),
    - **When** l'analyste consulte les observations,
    - **Then** FastAPI renvoie une réponse HTTP 422 standardisée.
  - **Cas d'autorisation et sécurité :**
    - **Given** un utilisateur sans droit d'accès au dossier,
    - **When** il tente d'accéder aux exécutions d'outils ou aux observations,
    - **Then** `verify_case_access` bloque la requête avec HTTP 404/403.

---

### Epic 5 : E5 - Orchestrateur, agents et gates

- **Modules concernés** : `orchestrator`, `agents`
- **Objectif** : Déployer le graphe d'états LangGraph pilotant la session d'enquête (`InvestigationRun`, `Phase`), intégrer le client LLM unifié basé sur le SDK `openai` avec réessais `tenacity`, implémenter l'agent `Planner` générant un plan d'actions borné, interrompre le graphe à la porte de validation humaine H1, permettre à l'agent procédural `Executor` de déclencher les outils de la Gateway après approbation, et assurer la persistance d'état et la reprise sur incident via le checkpointer PostgreSQL.
- **FR couvertes** : FR16, FR17, FR18, FR20, FR21
- **NFR couvertes** : NFR-PERF-03, NFR-PERF-04, NFR-PERF-05, NFR-SEC-06, NFR-QA-01, NFR-QA-02
- **Dépendances** : E1, E2, E3, E4
- **Critères de fin d'épic (Definition of Done)** :
  1. Le graphe d'états LangGraph s'initialise et orchestre les phases de l'enquête.
  2. Le client LLM unifié communique avec le modèle configuré (OpenAI/Gemma) avec gestion de retries Tenacity et prompts délimités contre l'injection de prompts.
  3. L'agent Planner génère un plan d'investigation respectant les limites (max 10 étapes, max 5 itérations).
  4. L'exécution s'interrompt obligatoirement à la porte H1 ; aucun outil ne s'exécute sans validation explicite de l'analyste via l'API.
  5. L'agent Executor dispatch les outils approuvés vers la Gateway.
  6. L'état du graphe est persisté dans PostgreSQL 16 et une session interrompue peut être reprise sans perte d'état.

#### Story 5.1 : Client LLM unifié OpenAI avec réessais Tenacity et prompts système sécurisés (D-10, D-11, NFR-SEC-06)
**En tant que** développeur d'agents IA,  
**Je veux** un composant client LLM unifié configuré par rôle (`base_url`, `model`), encapsulé avec `tenacity` et immunisé contre l'injection de prompt indirecte,  
**Afin d'**exécuter les inférences des agents de manière fiable et résiliente sans risque d'altération des consignes par des preuves hostiles.

- **Décisions d'architecture mobilisées** : D-04, D-10, D-11.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** les variables d'environnement `OPENAI_API_BASE`, `OPENAI_API_KEY` et la configuration du modèle pour un rôle donné,
    - **When** le client LLM unifié invoque l'API de complétion de chat,
    - **Then** la requête transite via le SDK officiel `openai` (>=1.50.0).
    - **And** si une erreur transitoire réseau (503, 429) survient, `tenacity` applique jusqu'à 3 tentatives avec un backoff exponentiel (1s, 2s, 4s) avant d'échouer (NFR-PERF-03).
    - **And** toutes les données de preuves fournies en entrée sont encapsulées dans des balises de données passives `<forensic_data>` avec consigne système interdisant l'interprétation d'instructions textuelles présentes dans les preuves (NFR-SEC-06).
  - **Cas d'erreur et validation :**
    - **Given** une indisponibilité persistante du fournisseur LLM après épuisement des 3 tentatives ou un dépassement du timeout de 60s,
    - **When** l'appel échoue définitivement,
    - **Then** le client lève une exception `LLMServiceUnavailableException` sans faire crasher l'application.
  - **Cas d'autorisation et sécurité :**
    - **Given** les logs d'appels LLM,
    - **When** des requêtes ou réponses sont enregistrées,
    - **Then** aucune clé d'API n'est jamais journalisée.

#### Story 5.2 : Modèles `InvestigationRun` et `Phase`, schémas et initialisation du graphe LangGraph (FR16)
**En tant que** développeur back-end,  
**Je veux** définir les modèles de session d'enquête et construire le graphe d'états LangGraph,  
**Afin d'**orchestrer les phases d'investigation numérique selon un flux rigoureux et auditable.

- **Décisions d'architecture mobilisées** : D-04, D-05, D-06, D-07, D-09.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la migration Alembic `006_create_investigation_and_phase_tables` appliquée,
    - **When** une session d'enquête est initiée via `POST /api/v1/cases/{case_id}/investigations`,
    - **Then** un enregistrement `InvestigationRun` est créé avec statut `running`, `current_phase = "triage"`, `iteration_count = 0`, `error_count = 0`, et `started_at` horodaté en UTC.
    - **And** le graphe d'états LangGraph compile les nœuds de traitement (`triage`, `planner`, `gate_h1`, `executor`, `analyst`, `verifier`, `gate_h2`, `gate_h3`, `reporting`).
    - **And** une entité `Phase` initiale est créée pour matérialiser la phase active.
  - **Cas d'erreur et validation :**
    - **Given** une session d'enquête active déjà en cours d'exécution sur le même dossier,
    - **When** un utilisateur tente d'en lancer une seconde en parallèle,
    - **Then** le serveur refuse l'opération avec HTTP 409 Conflict et le code `INVESTIGATION_ALREADY_RUNNING`.
  - **Cas d'autorisation et sécurité :**
    - **Given** un utilisateur ayant uniquement le rôle `viewer`,
    - **When** il tente d'initier une session d'investigation,
    - **Then** le serveur retourne HTTP 403 Forbidden.

#### Story 5.3 : Agent `Planner` et proposition de plan d'investigation borné (FR17, NFR-PERF-05)
**En tant qu'**analyste SOC,  
**Je veux** que l'agent `Planner` analyse l'inventaire des preuves disponibles et propose un plan d'actions ordonné d'outils forensiques respectant des limites strictes,  
**Afin de** disposer d'une stratégie d'investigation ciblée sans risque d'emballement ou de requêtes infinies.

- **Décisions d'architecture mobilisées** : D-04, D-09, D-10, D-11.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** le graphe LangGraph atteignant le nœud `planner` avec au moins une preuve scellée dans le dossier,
    - **When** l'agent Planner génère sa proposition de plan,
    - **Then** la sortie est validée contre le schéma Pydantic `InvestigationPlan` contenant une liste ordonnée d'étapes (`step_id`, `tool_name`, `target_evidence_id`, `parameters`, `rationale`).
    - **And** le nombre total d'étapes du plan est borné à un maximum de 10 étapes (NFR-PERF-05).
    - **And** le plan proposé est sauvegardé dans `InvestigationRun.validated_plan` (en attente d'approbation) et l'exécution progresse vers le nœud `gate_h1`.
  - **Cas d'erreur et validation :**
    - **Given** un dossier ne comportant aucune preuve scellée,
    - **When** le Planner s'exécute,
    - **Then** l'agent formule une notification indiquant l'absence de matière analysable et le statut de la session passe en attente de preuves sans consommer de tokens d'inférence inutilement.
    - **And** si la sortie de l'agent ne respecte pas le schéma JSON attendu, le validateur Pydantic déclenche jusqu'à 2 corrections avant de lever une erreur typée.
  - **Cas d'autorisation et sécurité :**
    - **Given** les étapes proposées par le Planner,
    - **When** les outils sont inspectés,
    - **Then** tout outil proposé doit obligatoirement exister dans le registre de la Gateway (aucun nom d'outil arbitraire n'est accepté).

#### Story 5.4 : Porte Humaine H1 (Validation du plan d'action) et API d'arbitrage (FR18)
**En tant qu'**analyste SOC ou enquêteur,  
**Je veux** examiner le plan d'investigation proposé par le Planner à la porte H1, l'approuver, le modifier ou le rejeter via l'API,  
**Afin de** garder le contrôle absolu sur les outils qui seront exécutés et garantir la pertinence de l'enquête.

- **Décisions d'architecture mobilisées** : D-03, D-04, D-09, D-24.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la session d'enquête atteignant l'état `gate_h1`,
    - **When** l'exécution se suspend automatiquement,
    - **Then** `InvestigationRun.status` passe à `paused` et signale l'attente de la porte H1 (`waiting_h1`).
    - **And** l'analyste consulte le plan via `GET /api/v1/cases/{case_id}/investigations/{run_id}/plan`.
    - **And** l'analyste approuve le plan via `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h1` avec le corps `{"decision": "approve"}`.
    - **And** le serveur répond HTTP 200 OK, met à jour le statut à `running` et débloque le graphe LangGraph vers le nœud `executor`.
  - **Cas d'erreur et validation :**
    - **Given** l'analyste décidant de modifier le plan à la porte H1 (`decision: "modify"`),
    - **When** il soumet une liste d'étapes modifiée,
    - **Then** le plan modifié est validé par Pydantic et persisté dans `InvestigationRun.validated_plan`.
    - **And** si l'analyste rejette le plan (`decision: "reject"`), la session s'arrête proprement avec le statut `completed` ou retourne au Planner avec les remarques fournies.
  - **Cas d'autorisation et sécurité :**
    - **Given** un utilisateur sans rôle `analyst`, `investigator` ou `admin` sur le dossier,
    - **When** il tente d'émettre une décision sur la porte H1,
    - **Then** la requête est rejetée avec HTTP 403 Forbidden.

#### Story 5.5 : Agent `Executor` procédural et dispatch sécurisé vers la Gateway (FR17)
**En tant que** système d'investigation IRYX,  
**Je veux** que l'agent procédural `Executor` exécute séquentiellement les étapes approuvées du plan d'actions via la Gateway sans faire d'appels LLM,  
**Afin de** garantir une exécution déterministe, traçable et sécurisée des outils forensiques.

- **Décisions d'architecture mobilisées** : D-08, D-09.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la porte H1 approuvée avec un plan d'actions validé,
    - **When** le nœud `executor` s'exécute dans LangGraph,
    - **Then** chaque étape du plan est appelée de manière séquentielle via le service de la Gateway forensique.
    - **And** aucun appel LLM n'est émis par l'Executor (procédure déterministe pure).
    - **And** pour chaque outil exécuté, un `ToolExecution` est tracé et les `Observation` correspondantes sont stockées en base.
    - **And** une fois toutes les étapes achevées, le graphe transitionne automatiquement vers la phase d'analyse (`analyst`).
  - **Cas d'erreur et validation :**
    - **Given** une étape du plan échouant techniquement (erreur de format ou timeout d'outil),
    - **When** l'erreur est constatée par l'Executor,
    - **Then** `InvestigationRun.error_count` est incrémenté, l'erreur est enregistrée, et l'Executor passe à l'étape suivante si le plan l'autorise ou suspend l'exécution si l'erreur est bloquante.
  - **Cas d'autorisation et sécurité :**
    - **Given** les paramètres de chaque étape,
    - **When** l'Executor les transmet à la Gateway,
    - **Then** la Gateway réapplique la validation stricte des paramètres et des permissions d'accès à la preuve ciblée.

#### Story 5.6 : Persistance transactionnelle d'état (Checkpointer PostgreSQL) et reprise après incident (FR21)
**En tant qu'**administrateur ou analyste,  
**Je veux** que l'état d'avancement de l'orchestration LangGraph soit persisté de manière transactionnelle dans PostgreSQL 16 à chaque nœud et porte humaine,  
**Afin de** permettre la reprise d'une enquête sans perte de données après un redémarrage ou une panne du serveur.

- **Décisions d'architecture mobilisées** : D-05, D-06, D-09.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** une session d'enquête en cours ou en pause sur une porte de contrôle (H1, H2, H3),
    - **When** chaque nœud du graphe LangGraph termine son exécution,
    - **Then** l'état complet des canaux du graphe (state snapshot) est sauvegardé dans la table de checkpointing PostgreSQL gérée par le checkpointer LangGraph (D-05, D-09).
    - **And** après redémarrage du processus ou du conteneur API/Worker, une requête `POST /api/v1/cases/{case_id}/investigations/{run_id}/resume` recharge l'état exact et reprend l'exécution là où elle s'était arrêtée.
  - **Cas d'erreur et validation :**
    - **Given** une tentative de reprise d'une session dont le statut est déjà `completed` ou `failed`,
    - **When** la requête de reprise est soumise,
    - **Then** le serveur répond HTTP 400 Bad Request avec le code `CANNOT_RESUME_TERMINATED_SESSION`.
  - **Cas d'autorisation et sécurité :**
    - **Given** la table des checkpoints PostgreSQL,
    - **When** les accès sont effectués,
    - **Then** les enregistrements sont cloisonnés par identifiant de session et protégés contre les altérations manuelles.

---

### Epic 6 : E6 - Findings et revue humaine (H2)

- **Modules concernés** : `findings`, `analytics`, `orchestrator`
- **Objectif** : Permettre à l'agent `Analyst` de formuler des constats d'enquête structurés (`Finding`), faire certifier chaque constat par le composant déterministe `Verifier` (qui valide en SQL pur sans aucun LLM l'existence réelle en base des observations et exécutions d'outils référencées), suspendre l'enquête à la porte de contrôle humain H2, et offrir à l'analyste l'API complète pour valider, rectifier ou rejeter chaque constat.
- **FR couvertes** : FR19, FR22, FR23
- **NFR couvertes** : NFR-REL-01, NFR-SEC-06, Invariant 1 (intégrité référentielle absolue des findings)
- **Dépendances** : E1, E2, E3, E4, E5
- **Critères de fin d'épic (Definition of Done)** :
  1. Le modèle `Finding` est opérationnel en base avec ses contraintes d'intégrité via Alembic.
  2. L'agent Analyst formule des propositions de findings rattachées aux observations.
  3. Le Verifier contrôle en 100% SQL relationnel l'existence de chaque référence et rejette toute hallucination de référence sans faire appel à un LLM (NFR-REL-01).
  4. La porte H2 suspend l'enquête et expose les findings à l'analyste.
  5. L'analyste valide, ajuste ou rejette les constats via `POST /api/v1/cases/{case_id}/findings/{finding_id}/review`.
  6. Seuls les findings validés sont marqués éligibles pour la timeline et le rapport d'incident.

#### Story 6.1 : Modèle `Finding`, schémas Pydantic et migration Alembic
**En tant que** développeur back-end,  
**Je veux** définir le modèle relationnel `Finding` et ses schémas Pydantic v2 associés,  
**Afin de** stocker les conclusions techniques d'enquête avec leurs niveaux de sévérité, de confiance, leur type et leurs références justificatives.

- **Décisions d'architecture mobilisées** : D-04, D-05, D-06, D-07.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la migration Alembic `007_create_finding_table` appliquée,
    - **When** la table `findings` est inspectée,
    - **Then** elle comporte les champs `id` (UUID), `case_id` (FK), `title` (String), `severity` (`low`, `medium`, `high`, `critical`), `confidence` (`low`, `medium`, `high`), `finding_type` (`fact`, `inference`, `hypothesis`), `status` (`proposed`, `validated`, `rejected`), `observation_refs` (ARRAY(UUID)), `tool_execution_refs` (ARRAY(UUID)), `created_by` (UUID), et `created_at` (UTC).
    - **And** les schémas Pydantic `FindingCreate`, `FindingUpdate` et `FindingOut` assurent la validation bidirectionnelle stricte.
  - **Cas d'erreur et validation :**
    - **Given** une charge utile avec un niveau de sévérité ou un type de finding non reconnu,
    - **When** la validation Pydantic s'exécute,
    - **Then** la requête est rejetée avec HTTP 422.
  - **Cas d'autorisation et sécurité :**
    - **Given** la suppression ou modification d'un finding,
    - **When** l'opération est tentée,
    - **Then** les règles de contrôle d'accès au niveau dossier (`verify_case_access`) sont appliquées.

#### Story 6.2 : Agent `Analyst` et formulation structurée des constats d'enquête (FR22)
**En tant qu'**analyste SOC ou enquêteur,  
**Je veux** que l'agent `Analyst` examine les observations extraites par les outils et propose des constats d'investigation structurés (`Finding`),  
**Afin d'**obtenir une première synthèse interprétative étayée par les preuves techniques.

- **Décisions d'architecture mobilisées** : D-04, D-09, D-10.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** le graphe LangGraph atteignant le nœud `analyst` avec des entités `Observation` produites par la phase d'exécution,
    - **When** l'agent Analyst est sollicité via le client LLM unifié (D-10),
    - **Then** l'agent génère des objets findings typés respectant strictement le schéma JSON attendu.
    - **And** chaque finding formulé cite obligatoirement au moins une référence d'observation existante (`observation_refs`) et une référence d'exécution d'outil (`tool_execution_refs`).
    - **And** chaque finding est persisté en base avec le statut initial `proposed`.
  - **Cas d'erreur et validation :**
    - **Given** l'absence d'observations pertinentes dans le dossier,
    - **When** l'agent Analyst analyse le contexte,
    - **Then** il indique qu'aucun constat ne peut être formulé sans éléments probants plutôt que d'inventer des faits.
  - **Cas d'autorisation et sécurité :**
    - **Given** le prompt envoyé à l'Analyst,
    - **When** les observations y sont injectées,
    - **Then** elles sont encapsulées comme données passives (NFR-SEC-06) pour prévenir toute tentative de détournement d'instructions.

#### Story 6.3 : Composant `Verifier` déterministe formel sans appel LLM (FR23, NFR-REL-01)
**En tant que** garant de l'intégrité légale et forensique de la plateforme IRYX,  
**Je veux** que le composant `Verifier` contrôle de façon 100% déterministe en SQL l'existence et l'appartenance de chaque référence de preuve citée dans un finding sans aucun appel LLM,  
**Afin d'**éliminer avec certitude mathématique toute hallucination de l'agent IA et respecter l'Invariant 1 du modèle de données.

- **Décisions d'architecture mobilisées** : D-06, D-20.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** une liste de findings au statut `proposed` soumis au nœud `verifier`,
    - **When** le Verifier s'exécute,
    - **Then** il exécute des requêtes SQL ciblées vérifiant que chaque UUID présent dans `observation_refs` existe bien dans la table `observations` et appartient au même `case_id`.
    - **And** il vérifie que chaque UUID présent dans `tool_execution_refs` existe bien dans `tool_executions` pour ce même dossier.
    - **And** aucun appel à une API ou modèle LLM n'est émis (interdiction formelle NFR-REL-01).
    - **And** si toutes les références sont vérifiées, le finding est marqué comme formellement certifié et éligible à la revue humaine H2.
  - **Cas d'erreur et validation :**
    - **Given** un finding généré par l'Analyst contenant un UUID d'observation inventé ou appartenant à un autre dossier,
    - **When** le Verifier contrôle ce finding,
    - **Then** le finding est immédiatement invalidé, rejeté avec le motif `HALLUCINATED_REFERENCE_DETECTED`, et l'anomalie est consignée dans les logs de sécurité.
  - **Cas d'autorisation et sécurité :**
    - **Given** la règle d'isolation multi-tenant,
    - **When** une référence valide existe dans un autre dossier de la base,
    - **Then** le Verifier la rejette formellement car elle n'appartient pas au `case_id` de la session courante (Invariant 1).

#### Story 6.4 : Porte Humaine H2 (Validation des findings) et API de revue (FR19)
**En tant qu'**analyste SOC ou enquêteur DFIR,  
**Je veux** examiner les findings certifiés à la porte H2, ajuster leur sévérité ou confiance, et valider ou rejeter chaque constat via l'API REST,  
**Afin de** valider humainement la qualification des faits avant leur inclusion dans les corrélations et les rapports.

- **Décisions d'architecture mobilisées** : D-03, D-04, D-06, D-09, D-24.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la session d'enquête atteignant l'état `gate_h2`,
    - **When** le graphe LangGraph se met en pause avec le statut `waiting_h2`,
    - **Then** l'analyste interroge `GET /api/v1/cases/{case_id}/findings?status=proposed` pour inspecter la liste des constats avec leurs observations liées.
    - **And** l'analyste soumet une décision pour un finding via `POST /api/v1/cases/{case_id}/findings/{finding_id}/review` avec `{"action": "validate", "severity": "high", "confidence": "high"}`.
    - **And** le serveur met à jour le statut du finding à `validated` et enregistre l'identifiant de l'analyste dans `created_by`.
    - **And** une fois tous les findings arbitrés, l'analyste débloque la porte H2 via `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h2` avec `{"decision": "proceed"}`.
  - **Cas d'erreur et validation :**
    - **Given** un finding pour lequel l'analyste décide d'un rejet (`action: "reject"`),
    - **When** la requête est traitée,
    - **Then** le statut passe à `rejected` et ce finding est exclu des phases ultérieures de reporting.
  - **Cas d'autorisation et sécurité :**
    - **Given** un utilisateur ayant uniquement le rôle `viewer`,
    - **When** il tente de valider ou rejeter un finding,
    - **Then** le serveur retourne HTTP 403 Forbidden.

---

### Epic 7 : E7 - Corrélation et chronologie

- **Modules concernés** : `findings` (dérivé), `observations`, `analytics`
- **Objectif** : Construire le moteur de corrélation temporelle et générer la chronologie unifiée (timeline) de l'enquête exclusivement dérivée des faits techniques confirmés, garantissant le respect strict de l'Invariant 2 (interdiction de forger des entrées temporelles ex nihilo) et reliant les constats validés aux événements sources.
- **FR couvertes** : FR24
- **NFR couvertes** : NFR-PERF-07, Invariant 2 (chronologie exclusivement dérivée des observations)
- **Dépendances** : E1, E2, E3, E4, E6
- **Critères de fin d'épic (Definition of Done)** :
  1. Le service de timeline projette et ordonne en UTC de façon strictement croissante les horodatages des entités `Observation`.
  2. Aucune entrée de chronologie ne peut être créée sans être directement rattachée à une `Observation` issue d'une `Evidence` scellée (Invariant 2).
  3. L'API expose un endpoint paginé `GET /api/v1/cases/{case_id}/timeline` supportant les filtres par plage horaire, par outil et par preuve source.
  4. Les `Finding` validés lors de H2 sont superposés sur la timeline pour mettre en exergue les moments clés de l'incident.

#### Story 7.1 : Service de reconstruction et de corrélation de la chronologie unifiée UTC (FR24)
**En tant qu'**analyste SOC ou enquêteur,  
**Je veux** que le système reconstruise automatiquement une chronologie unifiée des faits techniques ordonnés en UTC à partir des observations validées,  
**Afin de** retracer l'enchaînement exact des actions de l'attaquant au cours de l'incident.

- **Décisions d'architecture mobilisées** : D-05, D-06.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** un dossier comportant des observations horodatées provenant de plusieurs sources (ex. EVTX, Registre, Prefetch, logs réseau Volatility),
    - **When** le service de timeline est invoqué pour le dossier,
    - **Then** il agrège toutes les entités `Observation` disposant d'un `timestamp_utc` non nul.
    - **And** les entrées sont triées par ordre chronologique strictement croissant en UTC.
    - **And** chaque entrée de timeline contient l'horodatage UTC, l'identifiant de l'observation source, le nom de l'outil générateur, le nom de la preuve scellée d'origine et le résumé du fait technique.
  - **Cas d'erreur et validation :**
    - **Given** des observations sans horodatage extractible (`timestamp_utc` null),
    - **When** la chronologie est générée,
    - **Then** ces observations sont isolées dans une section spécifique « Faits non horodatés » sans fausser l'ordre de la timeline principale.
  - **Cas d'autorisation et sécurité :**
    - **Given** l'Invariant 2 du modèle de données (`docs/03`),
    - **When** le service opère,
    - **Then** il n'existe aucune méthode ni point d'accès permettant d'insérer, d'éditer ou de forger manuellement un événement temporel dans la timeline (la timeline est une projection calculée pure).

#### Story 7.2 : API de consultation paginée et filtrage de la Timeline d'enquête (NFR-PERF-07)
**En tant qu'**enquêteur numérique,  
**Je veux** interroger la timeline du dossier via une API REST paginée avec filtres temporels et par type d'artefact,  
**Afin de** focaliser mon analyse sur une fenêtre d'attaque précise sans saturer la bande passante.

- **Décisions d'architecture mobilisées** : D-03, D-04, D-06.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** une timeline comportant des milliers d'événements techniques pour un dossier donné,
    - **When** l'analyste appelle `GET /api/v1/cases/{case_id}/timeline?start_time=2026-11-23T08:00:00Z&end_time=2026-11-23T12:00:00Z&limit=50&offset=0`,
    - **Then** le serveur répond HTTP 200 OK avec la liste des 50 événements de la plage horaire demandée, ordonnés chronologiquement.
    - **And** les métadonnées de réponse indiquent `total_items`, `limit`, `offset` et s'il existe une page suivante.
    - **And** un filtre `tool_name=python-evtx` restreint les résultats aux seuls événements issus des journaux Windows.
  - **Cas d'erreur et validation :**
    - **Given** un paramètre `start_time` postérieur à `end_time`,
    - **When** la requête est analysée par Pydantic,
    - **Then** le serveur retourne HTTP 422 avec un message explicite `start_time must be before end_time`.
  - **Cas d'autorisation et sécurité :**
    - **Given** un utilisateur sans droit d'accès au dossier,
    - **When** il sollicite la timeline,
    - **Then** la requête est rejetée avec HTTP 404/403 via `verify_case_access`.

#### Story 7.3 : Moteur de corrélation multi-sources et mise en correspondance des Findings
**En tant qu'**analyste SOC,  
**Je veux** que la timeline mette en évidence les corrélations entre sources différentes et superpose les findings validés sur leurs événements sources,  
**Afin de** visualiser immédiatement les preuves matérielles soutenant chaque constatation d'incident.

- **Décisions d'architecture mobilisées** : D-04, D-06.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** un `Finding` validé rattaché à une observation Prefetch et à une observation EVTX survenues à la même minute,
    - **When** la timeline enrichie est générée,
    - **Then** les deux événements sont étiquetés avec un marqueur visuel de corrélation partagé.
    - **And** l'objet de réponse intègre la liste des identifiants et titres des findings validés superposés aux points temporels correspondants.
  - **Cas d'erreur et validation :**
    - **Given** des findings rejetés lors de la porte H2,
    - **When** la timeline de corrélation est calculée,
    - **Then** les findings au statut `rejected` sont strictement exclus de la surimpression sur la timeline.
  - **Cas d'autorisation et sécurité :**
    - **Given** la consultation des corrélations,
    - **When** les données sont renvoyées,
    - **Then** aucune donnée d'un dossier tiers n'est incluse dans le calcul de corrélation.

---

### Epic 8 : E8 - Rapports et journal d'audit

- **Modules concernés** : `reports`, `audit`, `reporting`
- **Objectif** : Implémenter la pseudonymisation déterministe des entités sensibles via Microsoft Presidio (D-19), gérer la porte de contrôle humain H3 (autorisation explicite avant tout transfert vers un LLM externe), rédiger et sceller le rapport d'incident final aux formats Markdown et JSON (avec calcul d'empreinte SHA-256 dans l'entité `Report`), et verrouiller le journal d'audit immuable en ajout seul (`AuditEvent`) traçant l'ensemble des opérations du système.
- **FR couvertes** : FR20, FR25, FR26, FR27
- **NFR couvertes** : NFR-SEC-03, NFR-SEC-07, NFR-REL-02, Invariant 3 (immutabilité stricte du journal d'audit)
- **Dépendances** : E1, E2, E3, E4, E5, E6, E7
- **Critères de fin d'épic (Definition of Done)** :
  1. Le moteur Presidio remplace de manière déterministe toutes les entités sensibles (IP, hôtes, comptes, emails) par des pseudonymes stables par dossier.
  2. L'orchestrateur s'interrompt à la porte H3 ; aucune donnée n'est expédiée à un LLM externe sans accord explicite de l'analyste.
  3. Le rapport final est généré, compilé en formats Markdown et JSON, et son empreinte SHA-256 est scellée dans l'entité `Report`.
  4. La table `AuditEvent` enregistre de façon synchrone toutes les actions sensibles avec calcul d'empreinte du payload.
  5. Un trigger SQL sur `AuditEvent` bloque avec succès toute tentative de modification (`UPDATE`) ou de suppression (`DELETE`).

#### Story 8.1 : Module de pseudonymisation déterministe Microsoft Presidio (FR25, D-19, NFR-SEC-07)
**En tant que** responsable de la conformité et de la sécurité des données,  
**Je veux** que toutes les données sensibles et identifiants techniques (adresses IP, noms de machines, comptes utilisateurs, emails) soient pseudonymisés de façon déterministe via Microsoft Presidio avant toute transmission externe,  
**Afin d'**empêcher formellement la divulgation d'informations confidentielles à des tiers.

- **Décisions d'architecture mobilisées** : D-04, D-19.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** un texte contenant des adresses IP internes (ex. `192.168.1.50`), des noms d'hôtes (ex. `SRV-DC-01`) et des comptes (ex. `admin_ad`),
    - **When** le service de pseudonymisation basé sur `presidio-analyzer` et `presidio-anonymizer` (D-19) est exécuté,
    - **Then** les entités sensibles sont détectées et substituées par des pseudonymes stables au sein du dossier (ex. `IP_INTERNAL_1`, `HOST_SERVER_01`, `USER_ACCOUNT_A`).
    - **And** une table de correspondances locale chiffrée par dossier permet de maintenir la cohérence des pseudonymes sur l'ensemble de la session d'enquête.
  - **Cas d'erreur et validation :**
    - **Given** un texte ne contenant aucune entité sensible détectée,
    - **When** la pseudonymisation est appliquée,
    - **Then** le texte est retourné intact sans altération de sa structure syntaxique.
  - **Cas d'autorisation et sécurité :**
    - **Given** la table de correspondances de pseudonymisation,
    - **When** l'accès est sollicité,
    - **Then** cette table est strictement restreinte au serveur et ne transite jamais dans les appels vers les API LLM externes.

#### Story 8.2 : Porte Humaine H3 (Autorisation d'envoi LLM externe) et prévisualisation sécurisée (FR20)
**En tant qu'**analyste SOC ou RSSI,  
**Je veux** prévisualiser la synthèse d'enquête pseudonymisée à la porte H3 et autoriser ou refuser explicitement son envoi vers un LLM externe pour la rédaction du rapport,  
**Afin de** garantir la souveraineté des données d'incident.

- **Décisions d'architecture mobilisées** : D-03, D-04, D-09, D-19, D-24.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la session d'enquête atteignant l'état `gate_h3`,
    - **When** le graphe LangGraph s'interrompt avec le statut `waiting_h3`,
    - **Then** l'analyste interroge `GET /api/v1/cases/{case_id}/investigations/{run_id}/anonymized-preview` pour vérifier la version intégrale des données pseudonymisées qui seraient transmises.
    - **And** l'analyste soumet sa décision via `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h3` avec `{"decision": "approve"}`.
    - **And** le graphe débloque l'étape de rédaction assistée par LLM externe vers le nœud `reporting`.
  - **Cas d'erreur et validation :**
    - **Given** l'analyste refusant l'envoi externe (`decision: "reject"` ou choix d'un mode hors-ligne),
    - **When** la décision est enregistrée,
    - **Then** le système bascule sur un gabarit déterministe local sans appel LLM pour compiler le rapport d'incident.
  - **Cas d'autorisation et sécurité :**
    - **Given** toute tentative d'envoi de données brutes vers une API externe sans validation préalable de H3,
    - **When** le code d'orchestration s'exécute,
    - **Then** la porte H3 constitue une barrière infranchissable dans le code empêchant tout appel réseau LLM avant approbation formelle.

#### Story 8.3 : Modèle `Report`, agent `Rapporteur`, génération et scellement SHA-256 du rapport (FR26)
**En tant qu'**analyste SOC ou enquêteur,  
**Je veux** que le rapport d'incident final soit rédigé, structuré et scellé avec son empreinte SHA-256 dans l'entité `Report`,  
**Afin de** produire un livrable d'incident irréfutable, exploitable par la direction et les équipes techniques.

- **Décisions d'architecture mobilisées** : D-04, D-05, D-06, D-07, D-10, D-14.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la migration Alembic `008_create_report_and_audit_tables` appliquée et la porte H3 validée,
    - **When** le nœud `reporting` s'exécute,
    - **Then** l'agent Rapporteur compile le rapport intégrant : le contexte du dossier, les preuves examinées, la chronologie des faits techniques et les findings validés avec leurs niveaux de criticité.
    - **And** le document est exporté dans les formats supportés `markdown` et `json` (D-04).
    - **And** le hash SHA-256 du document compilé est calculé via `hashlib.sha256` et persisté dans `Report.sha256`.
    - **And** l'entité `Report` est insérée avec `status = "validated"` et horodatage UTC.
  - **Cas d'erreur et validation :**
    - **Given** un échec lors de la génération du rapport,
    - **When** l'exception est levée,
    - **Then** l'entité `Report` conserve le statut `draft` ou l'erreur est consignée avec le code `REPORT_GENERATION_FAILED`.
  - **Cas d'autorisation et sécurité :**
    - **Given** un rapport validé et scellé,
    - **When** son contenu est stocké,
    - **Then** il ne peut plus être modifié ; toute nouvelle rédaction génère une nouvelle version distincte de `Report`.

#### Story 8.4 : Endpoints de consultation et téléchargement des rapports scellés
**En tant qu'**analyste ou responsable sécurité,  
**Je veux** consulter la liste des rapports d'un dossier et télécharger un rapport scellé avec son empreinte cryptographique en en-tête HTTP,  
**Afin d'**obtenir le livrable officiel et vérifier son intégrité avant transmission aux autorités ou clients.

- **Décisions d'architecture mobilisées** : D-03, D-04, D-06, D-12, D-14.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** un rapport scellé existant pour le dossier `{case_id}`,
    - **When** l'utilisateur soumet `GET /api/v1/cases/{case_id}/reports`,
    - **Then** le serveur retourne HTTP 200 avec la liste des rapports, leurs formats (`markdown`, `json`), statuts et empreintes SHA-256.
    - **And** une requête `GET /api/v1/cases/{case_id}/reports/{report_id}/download` retourne le contenu du document avec l'en-tête HTTP standardisé `X-Report-SHA256: <hash>` et `Content-Type` adapté (`text/markdown` ou `application/json`).
  - **Cas d'erreur et validation :**
    - **Given** un `report_id` n'existant pas dans le dossier spécifié,
    - **When** le téléchargement est sollicité,
    - **Then** le serveur répond HTTP 404 Not Found avec le code `REPORT_NOT_FOUND`.
  - **Cas d'autorisation et sécurité :**
    - **Given** un utilisateur non habilité sur le dossier,
    - **When** il tente de télécharger le rapport,
    - **Then** `verify_case_access` bloque la requête avec HTTP 404/403.

#### Story 8.5 : Service d'audit immuable en ajout seul `AuditEvent` et déclencheur d'intégrité (FR27, NFR-SEC-03)
**En tant que** responsable de la conformité et auditeur de sécurité,  
**Je veux** que chaque action sensible du système soit consignée de manière synchrone dans la table `AuditEvent` et que tout UPDATE ou DELETE soit rendu impossible par la base de données,  
**Afin d'**assurer une traçabilité d'audit infalsifiable et opposable.

- **Décisions d'architecture mobilisées** : D-05, D-06, D-07, D-14, D-23.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la table `audit_events` créée via Alembic et assortie d'un trigger SQL rejetant toute modification ou suppression,
    - **When** une action sensible survient (connexion utilisateur, accès dossier, téléversement de preuve, validation d'une porte H1/H2/H3, export de rapport),
    - **Then** le service d'audit insère de façon synchrone une ligne dans `audit_events` contenant `id` (UUID), `case_id`, `actor_id`, `action` (code normalisé), `target_type`, `target_id`, `payload_hash` (SHA-256 des paramètres d'action), `details` (JSONB exempt de secrets), et `created_at` (UTC).
    - **And** un endpoint `GET /api/v1/cases/{case_id}/audit-trail?limit=100&offset=0` permet aux rôles `admin` et `investigator` de consulter le journal d'audit paginé.
  - **Cas d'erreur et validation :**
    - **Given** la table `audit_events` en base PostgreSQL,
    - **When** un administrateur de base ou un processus tente d'exécuter `UPDATE audit_events SET action = '...'` ou `DELETE FROM audit_events WHERE id = '...'`,
    - **Then** le déclencheur PostgreSQL (trigger) intercepte la commande et lève une exception SQL formelle `CANNOT_MODIFY_AUDIT_LOG`, bloquant l'opération (Invariant 3, NFR-SEC-03).
  - **Cas d'autorisation et sécurité :**
    - **Given** un utilisateur sans rôle `admin` ou `investigator`,
    - **When** il tente d'interroger la piste d'audit via l'API,
    - **Then** le serveur répond HTTP 403 Forbidden.
    - **And** les champs `details` des événements d'audit ne contiennent jamais de mot de passe, de secret JWT ni de clé API (NFR-REL-02).

---

### Epic 9 : E9 - Déploiement et démonstration

- **Modules concernés** : `docker`, `déploiement`, intégration globale
- **Objectif** : Configurer la topologie mono-serveur Docker Compose (PostgreSQL 16, Redis 7, API FastAPI, Worker Celery) avec durcissement de sécurité (confinement utilisateur non-root `uid 10001`, `cap_drop: ALL`, coupure réseau forensique et volumes de preuves en lecture seule), initialiser un jeu de données de démonstration (seed data avec cas réel d'attaque Windows), et fournir un scénario de test d'acceptation de bout en bout validant l'ensemble du cycle de vie de l'incident de FR1 à FR27.
- **FR couvertes** : Validation globale de bout en bout de FR1 à FR27
- **NFR couvertes** : NFR-SEC-01, NFR-SEC-02, NFR-SEC-08, D-22, NFR-QA-01, NFR-QA-02
- **Dépendances** : E1 à E8
- **Critères de fin d'épic (Definition of Done)** :
  1. La commande `docker compose up -d` monte les services (`postgres`, `redis`, `api`, `worker`) avec application automatique des migrations Alembic.
  2. Le conteneur de traitement tourne sous utilisateur non-root (`uid 10001:gid 10001`), sans capacités Linux privilégiées et avec volumes montés en lecture seule (`ro`).
  3. Le script de seed génère une organisation, des comptes de test avec rôles distincts, et un dossier d'incident avec échantillons de preuves (EVTX, Prefetch, dump mémoire).
  4. Le script de démonstration / smoke test E2E exécute le flux complet sans erreur : connexion -> création dossier -> téléversement preuve -> H1 -> exécution outils -> H2 -> timeline -> H3 -> rapport scellé -> vérification audit trail.

#### Story 9.1 : Configuration Dockerfile multi-étapes et Docker Compose mono-serveur (D-22)
**En tant qu'**ingénieur DevOps ou développeur,  
**Je veux** disposer d'un Dockerfile multi-étapes optimisé avec `uv` et d'un fichier `docker-compose.yml` consolidé pour l'API et le Worker,  
**Afin de** démarrer l'ensemble de la plateforme IRYX en une seule commande reproductible.

- **Décisions d'architecture mobilisées** : D-01, D-02, D-05, D-08, D-22, D-26.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** Docker et Docker Compose installés sur l'hôte,
    - **When** la commande `docker compose up -d` est exécutée,
    - **Then** les quatre conteneurs `postgres` (PostgreSQL 16), `redis` (Redis 7), `iryx-api` (FastAPI) et `iryx-worker` (Celery) démarrent et passent au statut `healthy`.
    - **And** le conteneur `iryx-api` applique automatiquement les migrations Alembic (`alembic upgrade head`) au démarrage avant d'ouvrir le port d'écoute HTTP.
    - **And** les tables de symboles ISF Windows (`windows.zip`) pour Volatility 3 sont intégrées dans le conteneur worker à l'emplacement `/opt/volatility3/symbols` (D-26).
  - **Cas d'erreur et validation :**
    - **Given** une indisponibilité temporaire de PostgreSQL lors du démarrage des services,
    - **When** `iryx-api` et `iryx-worker` démarrent,
    - **Then** ils attendent la disponibilité du port PostgreSQL via une sonde d'attente (healthcheck) sans crasher immédiatement.
  - **Cas d'autorisation et sécurité :**
    - **Given** les conteneurs en fonctionnement,
    - **When** la commande `id` est exécutée dans le conteneur API ou Worker,
    - **Then** l'utilisateur actif est non-root (`uid=10001(iryx) gid=10001(iryx)`).

#### Story 9.2 : Durcissement de sécurité du conteneur de traitement et isolation réseau (NFR-SEC-02)
**En tant que** responsable de la sécurité du système (CISO),  
**Je veux** que les conteneurs d'exécution d'outils forensiques soient durcis avec abandon des capacités Linux (`cap_drop: ALL`), isolation réseau et montage en lecture seule,  
**Afin de** prémunir l'hôte contre toute évasion de conteneur ou tentative de communication malveillante initiée par un malware analysé.

- **Décisions d'architecture mobilisées** : D-04, D-22.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la configuration de sécurité spécifiée dans `docker-compose.yml`,
    - **When** les conteneurs de traitement sont inspectés via `docker inspect`,
    - **Then** le paramètre `CapDrop` contient `["ALL"]` et `SecurityOpt` active `no-new-privileges:true`.
    - **And** le répertoire hébergeant les preuves brutes est monté avec le drapeau `:ro` (lecture seule, NFR-SEC-01).
    - **And** le conteneur dédié aux tâches d'analyse forensique tourne avec `network_mode: none` (air-gap absolu) ou règles de filtrage interdisant tout trafic sortant vers Internet.
  - **Cas d'erreur et validation :**
    - **Given** une tentative de requête réseau sortante initiée depuis un sous-processus d'analyse,
    - **When** une connexion TCP externe est tentée,
    - **Then** l'appel réseau échoue immédiatement avec une erreur de réseau inaccessible (`Network is unreachable`).
  - **Cas d'autorisation et sécurité :**
    - **Given** les variables d'environnement des conteneurs,
    - **When** elles sont inspectées,
    - **Then** aucun secret n'est écrit en dur dans le fichier `docker-compose.yml` ; tous sont injectés via le fichier `.env` non versionné (conforme à `.env.example`).

#### Story 9.3 : Script de peuplement de démonstration (Seed Data) d'un incident Windows type
**En tant que** démonstrateur ou formateur IRYX,  
**Je veux** exécuter un script d'initialisation de données (`seed_data.py`) générant une organisation, des utilisateurs avec différents rôles et un dossier d'incident avec preuves réelles,  
**Afin de** préparer instantanément un environnement de démonstration réaliste sans saisie manuelle préalable.

- **Décisions d'architecture mobilisées** : D-04, D-06, D-13, D-14.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la base de données initialisée avec les migrations Alembic,
    - **When** la commande `uv run python -m iryx.scripts.seed_data` est exécutée,
    - **Then** l'organisation « Banque Atlantique DFIR » est créée.
    - **And** 4 utilisateurs sont créés avec mots de passe hachés argon2 : `admin@iryx.local` (admin), `analyst@iryx.local` (analyst), `investigator@iryx.local` (investigator), et `auditor@iryx.local` (viewer).
    - **And** un dossier d'investigation « Attaque Ransomware Serveur AD » est créé au statut `open`.
    - **And** trois échantillons de preuves forensiques réelles de test sont copiés et scellés dans le dossier : un journal `Security.evtx` (avec Event IDs 4624/4688), un fichier Prefetch `POWERSHELL.EXE-*.pf`, et un extrait dump mémoire de test.
  - **Cas d'erreur et validation :**
    - **Given** un script de seed exécuté une seconde fois sur la même base,
    - **When** les vérifications d'unicité s'exécutent,
    - **Then** le script détecte les données existantes, applique une mise à jour idempotente ou ignore sans provoquer d'erreurs de contraintes SQL.
  - **Cas d'autorisation et sécurité :**
    - **Given** les mots de passe de test générés pour la démo,
    - **When** le script affiche la synthèse,
    - **Then** un message rappelle d'utiliser des mots de passe robustes et personnalisés en environnement de production.

#### Story 9.4 : Script de test d'acceptation et démonstration de bout en bout (Smoke Test E2E)
**En tant qu'**équipe projet et évaluateur technique,  
**Je veux** exécuter un script automatisé de test de bout en bout simulant le parcours complet de l'analyste à travers l'API REST,  
**Afin de** valider l'interopérabilité parfaite de l'ensemble des modules (E1 à E9) et la couverture complète des exigences fonctionnelles FR1 à FR27.

- **Décisions d'architecture mobilisées** : D-03, D-10, D-12, D-14, D-19, D-20.
- **Critères d'acceptation** :
  - **Cas nominal :**
    - **Given** la pile Docker Compose active et les données de démonstration initialisées,
    - **When** le script `test_e2e_investigation_flow.py` est lancé,
    - **Then** le script exécute avec succès la séquence ordonnée suivante :
      1. Authentification de l'analyste et récupération du jeton JWT (FR1).
      2. Vérification des droits d'accès sur le dossier (FR2, FR3, FR4).
      3. Téléversement d'une preuve et attente de la complétion du scellement SHA-256 via polling REST (FR5, FR6, FR7).
      4. Démarrage de la session d'enquête LangGraph (FR16).
      5. Réception de la proposition de plan de l'agent Planner et approbation de la porte H1 (FR17, FR18).
      6. Exécution des outils par l'Executor et la Gateway avec traçabilité `ToolExecution` et normalisation en `Observation` (FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15).
      7. Formulation des findings par l'Analyst et certification formelle par le Verifier SQL sans LLM (FR22, FR23).
      8. Validation des findings par l'analyste à la porte H2 (FR19).
      9. Consultation et vérification de la timeline unifiée UTC corrélée (FR24).
      10. Prévisualisation de la pseudonymisation Presidio et approbation de la porte H3 (FR20, FR25).
      11. Rédaction et scellement du rapport final d'incident en Markdown et JSON avec vérification du hash SHA-256 (FR26).
      12. Consultation du journal d'audit et test de tentative avortée de modification de la table d'audit (FR27, Invariant 3).
    - **And** le script s'achève avec le code de sortie 0 et affiche « DÉMONSTRATION ET VALIDATION COMPLÈTE DU MVP IRYX RÉUSSIE ».
  - **Cas d'erreur et validation :**
    - **Given** une étape de la chaîne échouant (ex. validation H1 non fournie ou hash non concordant),
    - **When** le script détecte l'écart,
    - **Then** il s'interrompt immédiatement avec un rapport d'erreur explicite indiquant l'étape et la condition non remplie.
  - **Cas d'autorisation et sécurité :**
    - **Given** l'ensemble des requêtes HTTP émises par le script de test,
    - **When** les en-têtes et les réponses sont inspectés,
    - **Then** chaque requête est signée avec son jeton JWT valide et aucune faille d'accès direct n'est détectée.

---

## 5. Synthèse et Prochaines Étapes BMAD

Le présent document constitue la référence exhaustive de découpage pour le développement du MVP IRYX. Il formalise :
- **9 Épics** directement alignés sur le découpage imposé de `docs/05`.
- **38 Récits Utilisateurs (User Stories)** rigoureusement calibrés pour une durée de réalisation unitaire d'une journée de développement au maximum.
- **100% des Exigences Fonctionnelles (FR1 à FR27)** et **Non Fonctionnelles** couvertes et testables.
- **Strict respect du périmètre MVP** excluant toute technologie reportée (YARA, Sleuth Kit, WebSockets, microservices).

La prochaine étape de la méthode BMAD est le lancement de la planification de sprint (**`bmad-sprint-planning`**), qui procédera à la vérification de l'état de préparation (*Implementation Readiness Gate*) et à la génération du fichier de suivi de sprint (`sprint-status.yaml`).

### Consignation des Validations Humaines (Jalon BMAD 11.1)

| Rôle | Validateur | Décision | Date |
|---|---|---|---|
| **Team Lead** | Abdoul-Gafar AMADOU | **VALIDÉ** | 2026-11-23 |
| **AI / Tech Lead** | Abdoul-Gafar AMADOU | **VALIDÉ** | 2026-11-23 |
| **Product Lead** | Abdoul-Gafar AMADOU | **VALIDÉ** | 2026-11-23 |

