# 06 - Périmètre du MVP : Inclusions, Options et Exclusions
 
---
 
## 1. Délimitation du périmètre fonctionnel et technique
 
Pour garantir la livraison d'une version opérationnelle, robuste et vérifiable dans les délais impartis, le périmètre du back-end IRYX est strictement cadré selon la matrice suivante :
 
| Dans le MVP | Optionnel (activé si le temps le permet) | Reporté (hors MVP) |
|---|---|---|
| **Gestion des dossiers et utilisateurs** : Organisations, utilisateurs, rôles, dossiers (`Case`), contrôle d'accès strict par dossier. | **Extraction disque Sleuth Kit** : support des images disque via `pytsk3` (D-25). | **Microservices & Kubernetes** : déploiement distribué, conteneurs orchestrés par k8s ou Helm. |
| **Ingestion et scellement des preuves** : Importation de fichiers, calcul d'empreinte SHA-256 (`hashlib`), détection de type binaire (`filetype`), stockage en lecture seule. | **Moteur de règles YARA** : analyse de fichiers par signatures via `yara-python` (D-25). | **Bus de messages lourd** : Kafka, RabbitMQ, infrastructure d'événements distribuée. |
| **Analyseur de logs texte et CSV** : Normalisation des horodatages UTC, extraction structurée dans `Observation`. | **Extraction d'IOC** : analyseur automatique d'indicateurs de compromission par regex. | **Cache distribué** : Memcached ou Redis Cluster pour le cache applicatif. |
| **Analyseur Windows EVTX** : Traitement des canaux critiques `Security`, `System`, `PowerShell` via `python-evtx`. | | **Application cliente Tauri** : interface de bureau lourde (reportée post-MVP). |
| **Analyseur de Registre et Prefetch** : Extraction des clés de persistance et d'exécution via `regipy` et `dissect`. | | **Multi-tenant strict par infrastructure** : bases de données isolées par client physique. |
| **Analyse de mémoire vive Volatility 3** : Plugins whitelistés stricts (`windows.info`, `windows.pslist`/`pstree`, `windows.cmdline`, `windows.netscan`, `windows.malware.malfind`) avec symboles ISF préchargés (D-26). | | **Moteurs forensiques tiers lourds** : Plaso / log2timeline, Zeek, Suricata. |
| **Orchestration d'enquête LangGraph** : Graphe d'états complet, boucle Planner -> Executor -> Analyst -> Verifier -> Corrélateur -> Rapporteur. | | **Supervision Celery Flower** : interface web de gestion des workers. |
| **Portes de contrôle humain (Gates)** : H1 (validation plan), H2 (validation findings), H3 (autorisation envoi externe). | | **Flux temps réel** : WebSocket ou Server-Sent Events (le polling REST est la norme MVP D-24). |
| **Vérificateur déterministe (Verifier)** : Validation mathématique de l'existence des références de preuves sans aucun appel LLM. | | |
| **Pseudonymisation (Microsoft Presidio)** : Anonymisation des données sensibles avant toute transmission externe (D-19). | | |
| **Journal d'audit immuable** : Traçabilité complète append-only dans `AuditEvent`. | | |
| **API REST FastAPI & Authentification JWT** : Points d'accès sécurisés, validation Pydantic v2, jetons PyJWT, hachage argon2. | | |
| **Topologie Docker Compose** : Déploiement mono-serveur consolidé (Postgres, Redis, API, Worker). | | |
 
---
 
## 2. Règle absolue de cadrage pour BMAD
 
> **Tout ce qui n'apparaît pas dans la colonne « Dans le MVP » ne doit pas figurer dans les épics du MVP.**
 
Cette règle s'impose à l'ensemble des agents et outils du framework BMAD. Aucun document de spécification, aucun fichier d'architecture, aucune story ni backlog généré ne doit intégrer de récits utilisateurs ou de tâches techniques relevant de la colonne « Reporté ».
 
---
 
Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
