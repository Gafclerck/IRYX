# 05 - Conventions Back-End : Normes de Développement et Règles de Revue
 
---
 
## 1. Principes généraux d'architecture logicielle
 
Le back-end IRYX est structuré en **monolithe modulaire** sous Python 3.12 et FastAPI. Chaque module métier forme une unité autonome et découplée.
 
### 1.1 Organisation modulaire du code
Chaque domaine fonctionnel dispose de son propre package sous `backend/src/iryx/` :
- `auth` : Authentification, gestion des utilisateurs et permissions.
- `cases` : Gestion des dossiers d'investigation et adhésion des membres.
- `evidences` : Ingestion, contrôle d'intégrité SHA-256 et stockage en lecture seule.
- `gateway` : Registre et invocation sécurisée des outils forensiques.
- `orchestrator` : Machine d'états LangGraph, exécution des phases et gestion des portes H1/H2/H3.
- `analytics` : Analyse, vérification déterministe des findings et corrélations temporelles.
- `reporting` : Génération, pseudonymisation et export des rapports d'incident.
- `audit` : Journalisation d'audit immuable (`AuditEvent`).
 
Les dépendances circulaires entre modules sont formellement interdites. Les communications inter-modules s'effectuent par interfaces de service explicites.
 
---
 
## 2. Les 14 règles de développement et de revue (Critères bloquants)
 
Toute contribution au code source doit respecter impérativement les quatorze règles suivantes. Le non-respect d'une seule règle entraîne le rejet immédiat en revue de code.
 
1. **Un dossier par module métier** :
   Chaque composant réside dans son module dédié. Les dépendances importées depuis un autre module sont déclarées de manière explicite au niveau du service.
2. **Routes minces (Thin Controllers)** :
   Une route FastAPI ne doit contenir aucune logique métier. Son rôle se limite exclusivement à : valider le schéma de requête entrant, injecter le contexte d'authentification/autorisation, appeler la méthode de service appropriée et renvoyer le schéma de réponse normalisé.
3. **Séparation stricte des schémas et des modèles ORM** :
   Aucun modèle ORM SQLAlchemy ne doit être directement renvoyé en sortie d'une route API ou accepté en entrée. Chaque échange transite par un modèle Pydantic v2 dédié (`SchemaIn`, `SchemaOut`).
4. **Injection de dépendances systématique** :
   L'accès à la session de base de données (`get_db`), l'utilisateur authentifié (`get_current_user`) et la vérification des permissions sont injectés via le mécanisme `Depends` de FastAPI.
5. **Vérification d'accès au dossier sur toute route concernée** :
   Toute route manipulant une ressource rattachée à un `Case` doit impérativement injecter la dépendance de contrôle d'appartenance (`verify_case_access`). L'omission de ce contrôle est une faille de sécurité critique bloquante.
6. **Codes d'erreur HTTP stables et absence de fuites d'informations** :
   Les erreurs retournent des codes HTTP sémantiques (400, 401, 403, 404, 422, 500) avec un schéma d'erreur standardisé (`code`, `message`). Aucune trace d'exception (stack trace) ni aucun chemin absolu de fichier système ne doit fuiter dans les réponses HTTP.
7. **Pagination et filtrage systématiques** :
   Tout point d'accès renvoyant une liste d'entités (preuves, observations, findings, événements d'audit) doit supporter la pagination (`limit`, `offset`) et un filtrage adapté. La valeur maximale de pagination est bornée par configuration (défaut : 100 éléments).
8. **Délégation asynchrone des tâches longues** :
   Toute tâche dont la durée d'exécution dépasse 500 ms (ingestion, hash, parsing EVTX, Volatility, rapport) doit être déléguée à un worker Celery. La route retourne un code HTTP 202 avec un identifiant de tâche consultable par polling.
9. **Évolution du schéma de données exclusivement par Alembic** :
   Aucune modification de structure de base de données n'est effectuée manuellement ou par `create_all` au démarrage. Chaque changement de table fait l'objet d'un script de migration Alembic testé et réversible.
10. **Configuration centralisée par variables d'environnement** :
    Tous les paramètres applicatifs sont définis via une classe dérivée de `pydantic_settings.BaseSettings`. Un fichier `.env.example` documente exhaustivement chaque variable et sa valeur par défaut indicative.
11. **Typage strict et zéro avertissement Ruff** :
    L'intégralité des fonctions publiques, méthodes de service et routes comporte des annotations de type Python conformes. Le linter et formateur `ruff` (D-21) doit s'exécuter sans aucun avertissement ni erreur avant toute validation de branche.
12. **Couverture de tests automatisés obligatoire** :
    Chaque service métier est couvert par des tests unitaires (`pytest`). Les routes sont validées par des tests d'intégration (`pytest-asyncio`, `httpx`). Les règles d'isolation multi-utilisateurs et de prévention des traversées de répertoires font l'objet de tests de sécurité dédiés.
13. **Journalisation structurée JSON sans secrets** :
    La journalisation est opérée via la bibliothèque standard `logging` au format JSON structuré (D-23). Il est formellement interdit de consigner des mots de passe, clés API, jetons JWT ou extraits bruts de preuves dans les logs.
14. **Mise à jour obligatoire de la documentation** :
    Toute modification de comportement technique, de schéma de base de données ou de contrat d'API impose la mise à jour immédiate et synchrone du document correspondant dans le dossier `docs/`.
 
---
 
Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
