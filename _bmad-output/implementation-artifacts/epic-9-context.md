# Epic 9 Context: E9 - Déploiement et démonstration

<!-- Compilé à partir des artefacts de planification. Modifiable librement. Régénérer avec compile-epic-context si les documents de planification changent. -->

## Goal

Rendre la plateforme IRYX réellement exécutable et démontrable : figer une topologie Docker Compose mono-serveur reproductible (PostgreSQL 16, Redis 7, API FastAPI, worker Celery) qui démarre en une seule commande, applique automatiquement les migrations et durcit l'exécution des outils forensiques (non-root, capacités supprimées, réseau coupé, preuves en lecture seule). L'épic fournit également un jeu de données de démonstration réaliste (incident Windows type) et un scénario de validation de bout en bout couvrant tout le cycle d'enquête, de l'authentification au rapport scellé et au journal d'audit. Il matérialise la preuve que les épics E1 à E8 s'intègrent et satisfont FR1 à FR27.

## Stories

- Story 9.1: Configuration Dockerfile multi-étapes et Docker Compose mono-serveur
- Story 9.2: Durcissement de sécurité du conteneur de traitement et isolation réseau
- Story 9.3: Script de peuplement de démonstration (Seed Data) d'un incident Windows type
- Story 9.4: Script de test d'acceptation et démonstration de bout en bout (Smoke Test E2E)

## Requirements & Constraints

- **Démarrage en une commande** : `docker compose up -d` doit amener les quatre services (`postgres`, `redis`, `iryx-api`, `iryx-worker`) à l'état `healthy`. L'API applique `alembic upgrade head` avant d'ouvrir le port HTTP ; les services attendent la disponibilité de PostgreSQL via une sonde sans crasher.
- **Durcissement** : conteneurs sous `uid:gid 10001:10001`, `cap_drop: ["ALL"]`, `no-new-privileges:true` ; le conteneur (ou processus) dédié aux analyses forensiques tourne en `network_mode: none` et toute connexion sortante doit échouer immédiatement ; volume des preuves monté `:ro` ; appels d'outils en `shell=False`, aucun shell exposé.
- **Secrets** : aucun secret en dur dans `docker-compose.yml` ; injection via un fichier `.env` non versionné, documenté par `.env.example`.
- **Volatility 3 hors ligne** : symboles ISF Windows préchargés dans `/opt/volatility3/symbols` ; empreinte SHA-256 vérifiée au démarrage (`c7e49e8a520bfd68cfa1907cbcf9581c15f9e761dfb61b369527ec50c76251b3`) ; refus de démarrer en cas d'écart ou de tentative de téléchargement réseau.
- **Seed idempotent** : une organisation, quatre utilisateurs aux rôles distincts (admin, analyst, investigator, viewer) avec mots de passe hachés argon2, un dossier d'investigation au statut `open`, et trois preuves scellées (EVTX contenant les Event IDs 4624/4688, Prefetch, extrait de dump mémoire). Une seconde exécution ne doit provoquer aucune erreur de contrainte SQL et doit rappeler d'utiliser des mots de passe robustes hors démonstration.
- **Smoke test E2E** : séquence complète authentification → contrôle d'accès dossier → téléversement et scellement SHA-256 → H1 → exécution des outils → H2 → timeline UTC → H3 → rapport Markdown/JSON scellé → vérification du journal d'audit. Sortie avec code 0 et message de réussite ; arrêt immédiat avec identification de l'étape fautive en cas d'écart ; chaque requête porte un JWT valide.
- **Qualité** : typage strict, `ruff check` et `ruff format --check` sans erreur, `pytest` entièrement vert.

## Technical Decisions

- **D-01 / D-02** : Python 3.12, dépendances gérées par `uv` avec fichier de verrouillage ; builds reproductibles.
- **D-03 / D-04** : API FastAPI, validation Pydantic v2 et configuration centralisée par variables d'environnement via `pydantic-settings`.
- **D-05 / D-07** : PostgreSQL 16 comme source unique de vérité ; évolution du schéma exclusivement par migrations Alembic, jamais `create_all`.
- **D-08** : Celery avec Redis 7 comme broker, PostgreSQL conservant l'état ; tout traitement supérieur à 500 ms est déporté en asynchrone avec retour HTTP 202.
- **D-22** : Docker Compose mono-serveur, sans Kubernetes ni microservices ; images API et worker distinctes, toutes deux non-root.
- **D-26** : worker embarquant `volatility3 == 2.7.0` et les symboles ISF préchargés, exécution strictement hors ligne.
- **D-12 / D-13 / D-14** : PyJWT pour les jetons, argon2 via `pwdlib` pour les mots de passe, `hashlib` pour les empreintes SHA-256.
- **D-19 / D-20** : pseudonymisation Presidio avant tout appel LLM externe ; tests via `pytest`, `pytest-asyncio` et `httpx`.
- **Formats de rapport** : Markdown et JSON uniquement ; l'export PDF est hors périmètre.
- **Rétention MVP** : preuves conservées localement sans purge automatique ; l'endpoint `/health` expose l'espace disque disponible.
- **Audit** : la table `AuditEvent` est append-only ; le test E2E doit constater le refus d'une tentative de modification ou de suppression.

## UX & Interaction Patterns

Le client, et donc le script E2E, suit un contrat de polling REST : les traitements longs renvoient HTTP 202 avec identifiant de suivi, en-tête `Retry-After: 3` et cadence conseillée de 3 à 5 secondes. Les portes H1, H2 et H3 exigent une validation humaine explicite avant de poursuivre ; aucune étape ne doit être contournée par le script. Les erreurs HTTP restent sémantiques, sans stack trace ni chemin absolu, et les listes sont paginées (défaut 50, maximum 100).

## Cross-Story Dependencies

- **Story 9.1** fournit le socle (images, compose, migrations au démarrage) utilisé par les stories 9.2, 9.3 et 9.4.
- **Story 9.2** durcit la configuration introduite par Story 9.1 (capacités, réseau, montages, secrets).
- **Story 9.3** doit être exécutée avant Story 9.4, qui consomme ses comptes, son dossier et ses preuves.
- **Story 9.4** valide l'intégration de E1 (authentification, migrations), E2 (dossiers, `verify_case_access`), E3 (ingestion et scellement), E4 (gateway, Volatility), E5/E6 (orchestration, H1, Verifier, H2), E7 (timeline) et E8 (Presidio, H3, rapport scellé, audit).
- Les chemins de stockage des preuves, l'emplacement des symboles et les variables d'environnement doivent rester cohérents entre les images, le compose et le script de seed.
