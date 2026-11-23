# 07 - API LLM et Dépendances : Configurations, Versions et Outils
 
---
 
## 1. Configuration des fournisseurs LLM par rôle
 
L'architecture d'IA d'IRYX repose sur un client unifié basé sur le SDK officiel `openai` (D-10) et la gestion des réessais avec `tenacity` (D-11). Les rôles reçoivent deux paramètres de configuration : l'URL de base (`base_url`) et le modèle (`model`).
 
| Rôle | Usage fonctionnel | Fournisseur en développement | Configuration en production |
|---|---|---|---|
| **Planner** | Élabore la proposition initiale de plan d'étapes d'outils. | API externe compatible OpenAI (RodiumAi ou Groq). | Modèle open-source Gemma auto-hébergé via vLLM / Ollama. |
| **Analyst** | Interprète les observations techniques et formule les findings. | API externe compatible OpenAI (RodiumAi ou Groq). | Modèle open-source Gemma auto-hébergé via vLLM / Ollama. |
| **Rapporteur** | Rédige le rapport de synthèse d'incident. | API externe compatible OpenAI, activée exclusivement après accord H3 sur synthèse pseudonymisée. | Modèle auto-hébergé ou API externe sous contrôle H3. |
| **Executor** | Exécute les outils et traite les codes d'erreur. | **Aucun appel LLM par défaut.** Logique procédurale déterministe. | Aucun appel LLM. |
| **Verifier** | Contrôle l'existence et la validité des références de preuves. | **Aucun LLM (Interdiction formelle).** Algorithme SQL déterministe. | Aucun LLM. |
 
- **Date de vérification de l'interopérabilité** : 2026-11-23.
- **Source de la documentation** : Spécification d'API OpenAI v1 (Chat Completions compatible endpoints).
- **Règle de sécurité des données** : Aucune donnée brute de preuve n'est transmise à une API LLM externe. Tout envoi vers un LLM externe requiert obligatoirement le passage par le module de pseudonymisation (D-19) et l'autorisation explicite de la porte humaine H3.
 
---
 
## 2. Variables d'environnement LLM (Noms sans secrets)
 
Les variables d'environnement suivantes sont déclarées dans `.env.example` et chargées par l'application :
- `OPENAI_API_BASE` : Point d'accès HTTP du service LLM (ex. `https://api.groq.com/openai/v1` ou `http://localhost:11434/v1`).
- `OPENAI_API_KEY` : Clé d'authentification du fournisseur LLM (omise ou valeur dummy si auto-hébergé).
- `PLANNER_MODEL` : Identifiant du modèle affecté au rôle Planner (ex. `llama-3.3-70b-versatile` ou `gemma2:27b`).
- `ANALYST_MODEL` : Identifiant du modèle affecté au rôle Analyst.
- `RAPPORTEUR_MODEL` : Identifiant du modèle affecté au rôle Rapporteur.
- `LLM_TIMEOUT_SECONDS` : Délai maximal d'attente d'une inférence (défaut : 60 secondes).
- `LLM_MAX_RETRIES` : Nombre maximal de tentatives en cas d'erreur de transport (défaut : 3).
 
---
 
## 3. Liste des dépendances principales (D-01 à D-26)
 
Les versions exactes retenues pour l'installation et le verrouillage du projet sont les suivantes :
 
| ID | Nom du composant / Bibliothèque | Version retenue | Rôle dans IRYX |
|---|---|---|---|
| D-01 | Python | 3.12 (ou 3.13) | Environnement d'exécution principal |
| D-02 | uv | 0.12.8 | Gestionnaire de dépendances et d'environnements virtuels |
| D-03 | fastapi | >=0.115.0 | Framework d'API HTTP asynchrone |
| D-04 | pydantic / pydantic-settings | >=2.9.0 / >=2.5.0 | Validation des schémas et chargement de configuration |
| D-05 | PostgreSQL | 16.x | Moteur de base de données relationnelle |
| D-06 | sqlalchemy / psycopg | >=2.0.35 / >=3.2.0 | ORM et pilote natif PostgreSQL |
| D-07 | alembic | >=1.13.0 | Gestionnaire des migrations de schéma SQL |
| D-08 | celery / redis | >=5.4.0 / >=7.0.0 | Orchestrateur de tâches asynchrones et broker mémoire |
| D-09 | langgraph | >=0.2.20 | Moteur de graphe d'états d'investigation |
| D-10 | openai | >=1.50.0 | SDK client unifié compatible OpenAI |
| D-11 | tenacity | >=9.0.0 | Gestionnaire de réessais avec backoff exponentiel |
| D-12 | pyjwt | >=2.9.0 | Génération et vérification des jetons d'accès JWT |
| D-13 | pwdlib[argon2] | >=0.2.0 | Hachage sécurisé des mots de passe utilisateurs |
| D-14 | hashlib | Standard Python | Calcul d'empreintes cryptographiques SHA-256 |
| D-15 | filetype | >=1.2.0 | Détection du type de preuve par signature binaire |
| D-16 | python-evtx | >=0.7.4 | Parseur pur Python des journaux d'événements Windows |
| D-17 | regipy | >=5.1.0 | Parseur pur Python des ruches de registre Windows |
| D-18 | dissect | >=3.8.0 | Parseur d'artefacts d'exécution et formats Windows |
| D-19 | presidio-analyzer / presidio-anonymizer | >=2.2.35 | Moteur de détection et pseudonymisation des PII |
| D-20 | pytest / pytest-asyncio / httpx | >=8.3.0 / >=0.24.0 / >=0.27.0 | Suite de tests automatisés et client HTTP |
| D-21 | ruff | >=0.6.0 | Linter et formateur de code haute performance |
| D-22 | Docker Compose | >=v5.3.0 | Définition et lancement des conteneurs locaux |
| D-23 | logging | Standard Python | Journalisation structurée en JSON natif |
| D-24 | REST polling | Spécification interne | Mécanisme de consultation périodique de statut |
| D-25 | pytsk3 / yara-python | Optionnels | Analyse disque Sleuth Kit et détection de règles |
| D-26 | volatility3 | 2.7.0 | Analyseur forensique de mémoire vive RAM |
 
### 3.1 Spécifications particulières pour Volatility 3 (D-26)
- **Version exacte du paquet** : `volatility3 == 2.7.0`.
- **Emplacement des tables de symboles ISF** : `/opt/volatility3/symbols` (montage pré-packagé dans l'image de worker).
- **Politique réseau** : Téléchargement dynamique de symboles strictement interdit lors de l'exécution (`offline mode`).
- **Empreinte SHA-256 des symboles Windows officiels préchargés** : `c7e49e8a520bfd68cfa1907cbcf9581c15f9e761dfb61b369527ec50c76251b3` (`windows.zip` pack ISF).
 
---
 
## 4. Règle de gouvernance et de mise à jour des versions
 
Toute montée de version majeure ou mineure impactant une dépendance de la liste D-01 à D-26 requiert la création et la validation préalable d'une décision d'architecture formelle (ADR) dans le dossier `docs/adr/`.
 
---
 
## 5. Outillage BMAD installé
 
- **Version de BMAD installée** : **BMad Method v6.12.4**.
- **Module actif** : BMM (BMad Method - Software Development).
- **Langue de communication** : French (Français).
- **Langue de sortie des documents** : French (Français).
- **Dossier des livrables** : `_bmad-output/`.
- **Identifiants réels des workflows utilisés pour la planification** :
  - `bmad-workflow-init` / `bmad-help` : Initialisation et diagnostic du projet.
  - `bmad-prd` : Élaboration et validation du Product Requirement Document.
  - `bmad-architecture` : Conception et validation de l'architecture technique détaillée.
  - `bmad-create-epics-and-stories` : Découpage fonctionnel en épics et récits utilisateurs.
  - `bmad-sprint-planning` : Contrôle de préparation (Readiness Gate) et génération du plan de sprint (`sprint-status.yaml`).
 
---
 
Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
