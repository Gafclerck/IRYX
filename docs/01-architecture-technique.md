# 01 - Architecture Technique : IRYX Back-End MVP
 
---
 
## 1. Tableau des décisions technologiques figées (D-01 à D-26)
 
Les choix technologiques suivants constituent les fondations intangibles du back-end IRYX pour le périmètre MVP :
 
| ID | Besoin | Choix retenu | Alternative écartée | Raison |
|---|---|---|---|---|
| D-01 | Langage | Python 3.12 | Node.js | Écosystème forensique et IA le plus riche |
| D-02 | Gestion des dépendances | uv + fichier de verrouillage | pip + requirements.txt | Installation reproductible, rapide |
| D-03 | API HTTP | FastAPI | Flask, Django | Imposé par l'architecture ; validation native |
| D-04 | Validation et schémas | Pydantic v2 + pydantic-settings | marshmallow | Intégré à FastAPI |
| D-05 | Base de données | PostgreSQL 16 | SQLite par dossier (Mulder) | Plusieurs utilisateurs, transactions, FTS natif |
| D-06 | Accès base | SQLAlchemy 2.x + driver psycopg 3 | SQL brut | Standard, sécurisé contre l'injection |
| D-07 | Migrations | Alembic | create_all au démarrage | Évolution du schéma tracée |
| D-08 | Tâches de fond | Celery avec Redis 7 comme broker, PostgreSQL comme source de vérité de l'état | arq | Standard éprouvé, réessais, délais et planification natifs ; évolutif sans changement d'architecture |
| D-09 | Orchestration d'investigation | LangGraph | code de boucle maison | Graphe d'états, reprise et persistance prêtes |
| D-10 | Client LLM | SDK officiel `openai`, base_url et modèle configurables | LiteLLM (proxy ou SDK) | Un seul format ; le même code sert l'API externe puis Gemma auto-hébergé (compatible OpenAI) |
| D-11 | Réessais des appels LLM | tenacity | boucles de retry maison | Standard, testable |
| D-12 | Jetons d'authentification | PyJWT | fastapi-users | Périmètre réduit ; pas de gestion de comptes complexe |
| D-13 | Mots de passe | pwdlib avec argon2 | passlib, bcrypt direct | passlib est peu maintenu |
| D-14 | Empreinte des preuves | hashlib (SHA-256) | aucune bibliothèque tierce | Standard de la bibliothèque standard |
| D-15 | Détection du type de fichier | filetype (signature) | python-magic (dépend de libmagic) | Pur Python, sans dépendance système |
| D-16 | Journaux EVTX | python-evtx | Chainsaw, Hayabusa (binaires Rust) | Pur Python pour le MVP ; binaires plus tard si besoin |
| D-17 | Registre Windows | regipy | RegRipper (Perl) | Pur Python, maintenu |
| D-18 | Autres artefacts Windows | Dissect (à évaluer pour Prefetch) ; sinon libscca | écriture d'analyseurs | Évite de réinventer les parseurs binaires |
| D-19 | Pseudonymisation | Microsoft Presidio + règles pour IP et hôtes | regex seules | Détection d'entités éprouvée ; règles propres pour les identifiants techniques |
| D-20 | Tests | pytest, pytest-asyncio, httpx | unittest | Standard FastAPI |
| D-21 | Qualité de code | ruff (lint et format) | flake8 + black + isort | Un seul outil |
| D-22 | Conteneurs | Docker Compose en local et en ligne | Kubernetes | MVP mono-serveur |
| D-23 | Journalisation | bibliothèque standard `logging` en JSON | structlog | Pas de dépendance supplémentaire |
| D-24 | Mise à jour d'état des investigations | interrogation (polling) | SSE, WebSocket | Suffisant pour le MVP |
| D-25 | Outils optionnels | pytsk3 (Sleuth Kit), yara-python | - | Activés seulement si le temps le permet (plan de la semaine) |
| D-26 | Analyse de mémoire vive (MVP) | Volatility 3 (paquet `volatility3`, version figée), tables de symboles ISF préchargées, exécution hors ligne | Volatility 2 (profils, obsolète) ; téléchargement de symboles à l'exécution (interdit en conteneur isolé) | Image RAM prévue dans le périmètre du canevas phase 2 ; outil de référence du domaine |
 
---
 
## 2. Description des couches logicielles
 
Le système adopte une architecture en couches étanches sous la forme d'un monolithe modulaire :
 
1. **Couche Interface** :
   Consommateur HTTP (interface web frontend ou client de test) communiquant par API REST JSON standard. Les mises à jour de progression d'investigation et d'ingestion s'opèrent par interrogation périodique (polling, D-24).
2. **Couche API et Coordination** :
   Application FastAPI (D-03). Responsable du routage, de la validation des requêtes entrantes via Pydantic v2 (D-04), de l'authentification par jeton PyJWT (D-12) et du contrôle d'autorisation d'accès au dossier (`Case`).
3. **Couche Orchestration** :
   Machine d'états implémentée avec LangGraph (D-09). Contrôle l'enchaînement strict des phases d'investigation : Triage -> Planification -> Validation H1 -> Exécution d'outils -> Analyse -> Vérification -> Validation H2 -> Autorisation H3 -> Reporting. Supporte l'interruption, la reprise et l'abandon sans perte de contexte.
4. **Couche Agents** :
   Agents spécialisés pilotés par prompts structurés :
   - `Planner` : élabore le plan d'outils (4 à 8 étapes).
   - `Executor` : exécute séquentiellement les étapes planifiées via la Gateway.
   - `Analyst` : extrait des synthèses et formule des `Finding` basés sur les observations.
   - `Verifier` : validateur déterministe sans LLM qui contrôle l'existence de chaque référence de preuve.
   - `Corrélateur` : agrège et ordonne chronologiquement les observations UTC.
   - `Rapporteur` : rédige le rapport d'incident final à partir des éléments certifiés.
5. **Couche Outils et Exécution isolée (Gateway)** :
   Point d'accès unique vers les analyseurs techniques forensiques (D-14 à D-18, D-26). Assure le respect strict de la liste blanche d'outils, la validation des paramètres, le timeout d'exécution, la journalisation d'audit dans `ToolExecution`, et l'isolation des processus (conteneur non-root, réseau désactivé, volume de preuve monté en lecture seule).
6. **Couche Données** :
   - PostgreSQL 16 (D-05) : source unique de vérité relationnelle, gérant la persistance de l'état, des dossiers, preuves, observations, findings, rapports et le journal `AuditEvent`.
   - Redis 7 (D-08) : courtier de messages (broker) et backend de transport pour la file de tâches Celery.
7. **Couche IA** :
   Module client unifié basé sur le SDK officiel `openai` (D-10) avec gestion des réessais par `tenacity` (D-11). Paramétré par rôle (`base_url` et `model`), dialoguant avec un service compatible OpenAI en développement ou un modèle Gemma auto-hébergé en production.
8. **Hors périmètre MVP (Passerelles externes)** :
   Aucun composant de microservice, pas de bus de messages Kafka, pas de gestionnaire Kubernetes, pas d'interface Flower pour Celery.
 
---
 
## 3. Règles de la couche données
 
1. **Preuves en lecture seule** :
   Le stockage physique des preuves (`Evidence`) réside sur un volume dédié monté avec l'attribut lecture seule (`read-only`) pour tous les conteneurs d'exécution d'outils.
2. **Empreinte SHA-256 à l'ingestion** :
   Toute preuve reçue est hachée cryptographiquement en SHA-256 (D-14) dès son enregistrement initial. L'écrasement silencieux d'un fichier est impossible : un nouvel upload d'un fichier modifié génère un nouvel identifiant d'entité `Evidence` horodaté.
3. **Observations avec provenance intégrale** :
   Chaque enregistrement `Observation` conserve obligatoirement l'identifiant de la preuve source (`source_id`), l'identifiant de l'exécution d'outil (`tool_execution_id`), l'horodatage UTC normalisé et l'offset ou chemin interne dans la ressource source.
4. **Journal d'audit en ajout seul (Append-only)** :
   La table `AuditEvent` est strictement en ajout seul. Aucune opération SQL `UPDATE` ou `DELETE` n'est permise au niveau applicatif ou fonctionnel. Tout événement critique (accès dossier, téléversement de preuve, appel outil, validation de porte H1/H2/H3, export) est scellé avec son empreinte de contenu.
 
---
 
## 4. Règle d'exécution asynchrone
 
Toute opération dont la durée prévisible dépasse 500 millisecondes (téléversement lourd, calcul de hash SHA-256, ingestion, parsing EVTX, scan mémoire Volatility 3, inférence LLM, compilation de rapport) s'exécute obligatoirement au sein d'un worker Celery (D-08).
 
La route API FastAPI crée immédiatement l'entité de suivi (`IngestionRun`, `ToolExecution` ou `InvestigationRun`), soumet la tâche à Celery et retourne un code HTTP 202 (Accepted) accompagné de l'identifiant de suivi. Le client consulte l'état d'avancement par polling sur une route dédiée.
 
---
 
## 5. Règle de topologie et d'infrastructure
 
Pour l'environnement de développement et la démonstration MVP, la topologie est consolidée sur un hôte unique orchestré via Docker Compose (D-22).
 
L'infrastructure comprend exclusivement :
- Service `postgres` : PostgreSQL 16 officiel.
- Service `redis` : Redis 7 officiel (mode broker Celery).
- Service `api` : Application FastAPI Python 3.12.
- Service `worker` : Exécuteur Celery Python 3.12 partageant le volume de stockage local des preuves.
 
Aucune dépendance externe (SaaS tiers, base managée non locale, service de télémesure non documenté) n'est autorisée.
 
---
 
Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
