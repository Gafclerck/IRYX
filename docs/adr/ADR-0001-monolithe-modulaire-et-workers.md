# ADR-0001 : Monolithe modulaire et workers pour le MVP (Rejet des microservices)
 
- **Date** : 2026-11-23
- **Statut** : acceptée
 
---
 
## Contexte
 
Pour le développement et le déploiement du MVP de la plateforme IRYX, la question s'est posée d'adopter soit une architecture distribuée en microservices (avec déploiement conteneurisé sur cluster Kubernetes, service mesh et communication gRPC), soit une architecture unifiée en monolithe modulaire avec séparation asynchrone des tâches lourdes via Celery et Redis.
 
Le projet cible une démonstration technique robuste et un déploiement simplifié en environnement local ou mono-serveur pour les équipes de sécurité d'Afrique de l'Ouest.
 
---
 
## Décision
 
Nous adoptons une architecture en **monolithe modulaire** complétée par un pool de **workers Celery** :
1. L'API HTTP FastAPI et les services métier résident dans une même base de code organisée en modules étanches (D-03).
2. Toutes les opérations forensiques longues (ingestion de preuves, calcul de hachage SHA-256, extraction d'artefacts EVTX/Registre, scan de dump mémoire Volatility 3, inférence LLM) sont déportées de manière asynchrone vers des workers Celery via Redis 7 (D-08).
3. L'ensemble de la topologie est décrit et orchestré par un unique fichier `docker-compose.yml` (D-22).
4. L'option d'une architecture en microservices et l'orchestration Kubernetes sont formellement rejetées pour le MVP.
 
---
 
## Conséquences
 
### Positives
- **Simplicité opérationnelle** : Déploiement trivial en une commande (`docker compose up`), éliminant la charge cognitive et d'infrastructure liée à Kubernetes.
- **Performances et latence** : Les échanges entre composants métier s'opèrent par appels de fonctions Python typés en mémoire sans surcoût de sérialisation réseau inter-services.
- **Facilité de débogage et de tests** : Suite de tests automatisés unifiée (`pytest`) exécutable localement en quelques secondes.
- **Maîtrise des coûts** : Empreinte mémoire et processeur minimale, adaptée aux serveurs modestes des centres d'opérations de sécurité cibles.
 
### Négatives / Risques
- **Scalabilité unitaire limitée** : L'API et les modules partagent le même cycle de vie de déploiement (compromis pleinement acceptable pour un périmètre MVP mono-serveur).
- **Discipline requise** : Nécessite une rigueur stricte en revue de code pour interdire les dépendances cycliques entre modules métier.
 
---
 
Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
