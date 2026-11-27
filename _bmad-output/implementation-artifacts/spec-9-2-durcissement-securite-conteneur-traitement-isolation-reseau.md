---
title: 'Story 9.2 : Durcissement de sécurité du conteneur de traitement et isolation réseau (NFR-SEC-02)'
type: 'feature'
created: '2026-11-27'
status: 'done'
baseline_commit: '7539331170066dd707d7037d4a8c220626f31cac'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-9-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La story 9.1 fournit quatre conteneurs non-root sans `cap_drop`, `no-new-privileges`, preuves brutes `:ro` ni isolation réseau : un outil compromis peut monter en privilèges, altérer une preuve ou joindre Internet.

**Approach:** Durcir le compose (capacités, `no-new-privileges`), séparer le brut `:ro` du staging writable, et ajouter un service d'analyse isolé pour les outils forensiques, sans secret en dur.

**Décision (C) :** `iryx-analysis`, profilé `analysis` et en `network_mode: none`, exécute à la demande les analyses et la sonde air-gap ; les quatre services initiaux restent inchangés au démarrage par défaut.

## Boundaries & Constraints

**Always:** Quatre services par défaut (`postgres`, `redis`, `iryx-api`, `iryx-worker`) plus `iryx-analysis` profilé ; utilisateur `10001:10001` ; `cap_drop: ["ALL"]` et `security_opt: ["no-new-privileges:true"]` sur API, worker et analyse ; brut `:ro`, staging writable ; symboles `:ro` et garde SHA-256 `c7e4…51b3` ; `shell=False`, `--offline`, healthchecks, dépendances `service_healthy` et port 8000 conservés ; secrets via `.env`/interpolation.

**Never:** Modifier `backend/src/**`, migrations, lockfiles, CMD Celery ou images 9.1 ; télécharger des symboles ; secret ou chemin hôte dans le compose ; 6e service ou démarrage d'`iryx-analysis` par défaut ; `create_all`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| `docker inspect` | API, worker et analyse démarrés | `CapDrop: ["ALL"]`, `SecurityOpt: ["no-new-privileges:true"]` | N/A |
| Preuves | upload + fichier scellé | brut `:ro`, staging writable ; ingestion OK | écriture refusée sur le brut |
| Sortie réseau | sonde lancée dans `iryx-analysis` | TCP externe échoue : `Network is unreachable` | erreur explicite, pas de fallback |
| Secrets | `docker compose config` | valide, aucun secret | échec si variable absente |

</frozen-after-approval>

## Code Map

- `backend/docker-compose.yml:1-92` -- quatre services + `iryx-analysis` profilé ; ajouts de durcissement, volumes, interpolation.
- `backend/docker/Dockerfile.api:31-44`, `Dockerfile.worker:59-72`, `entrypoint-api.sh:17-49` -- non-root 10001, symboles vérifiés, CMD Celery, ordre `pg_isready`→`alembic`→`uvicorn` ; non modifier.
- `backend/src/iryx/core/config.py:49-51,98-104`, `evidence/services.py:63-75`, `evidence/tasks.py:129-146` -- séparation brut/staging par env ; staging écrit puis `chmod 0o440` : il reste writable.
- `backend/src/iryx/gateway/runner.py:53-105`, `tools/volatility_analyzer.py:504-523,669-695` -- seul sous-processus, déjà `shell=False`/`--offline` ; périmètre de l'air-gap.
- `backend/docker/check_airgap.py` (nouveau), `backend/tests/unit/test_deployment_config.py:1-233` -- sonde TCP et tests statiques ; ne pas réintroduire les assertions anti-durcissement supprimées en 9.1.
- `backend/.env.example:31-42`, `README.md:225-305` -- chemins, procédure `--profile analysis`, gel 9.1 respecté.

## Tasks & Acceptance

**Execution:**
- [x] `backend/docker-compose.yml` -- ajouter `cap_drop`/`security_opt` à API, worker et analyse ; ajouter `iryx-analysis` (profil `analysis`, `network_mode: none`, image worker, symboles `:ro`) ; monter le brut `:ro` via `EVIDENCE_STORAGE_PATH=/data/evidence/raw` et le staging writable via `EVIDENCE_STAGING_PATH=/data/evidence/staging`.
- [x] `backend/docker/check_airgap.py` -- sonde TCP externe échouant avec `Network is unreachable`, code 0 si le blocage est effectif.
- [x] `backend/tests/unit/test_deployment_config.py` -- assérer `CapDrop`, `SecurityOpt`, `network_mode: none`, profil, brut `:ro`, staging writable, absence de secrets, cinq services dont un profilé ; couvrir la matrice.
- [x] `backend/.env.example`, `README.md` -- documenter les chemins et `docker compose --profile analysis run --rm iryx-analysis`.

**Acceptance Criteria:**
- Given la configuration déployée, when `docker inspect` vise API, worker et analyse, then `CapDrop` vaut `["ALL"]` et `SecurityOpt` contient `no-new-privileges:true`.
- Given le répertoire brut, when inspecté, then il est monté `:ro` ; and un nouvel upload via le staging réussit.
- Given `iryx-analysis`, when la sonde y est lancée, then le TCP externe échoue avec `Network is unreachable`.
- Given le compose, when inspecté, then aucun secret en dur, `.env` conforme, quatre services par défaut et un profilé.
- Given l'absence de démon, when les tests statiques roulent, then la cible est validée et les limites notées.

## Implementation Notes

### 2026-11-27 — implémentation (baseline `7539331170066dd707d7037d4a8c220626f31cac`)

- `backend/docker-compose.yml` : `cap_drop: ["ALL"]` et `security_opt: ["no-new-privileges:true"]` sur `iryx-api`, `iryx-worker`, `iryx-analysis`. Les preuves scellées sont écrites dans `evidence_staging_data` (writable) sur `/data/evidence/staging` ; `evidence_data` est monté `:ro` sur `/data/evidence/raw` comme source d'entrée immuable. Les variables `EVIDENCE_STORAGE_PATH`/`EVIDENCE_STAGING_PATH` sont explicites sur les trois services, sans toucher à `backend/src`.
- `iryx-analysis` est profilé (`profiles: ["analysis"]`), en `network_mode: none`, sans `env_file`, ports ni secret. Il réutilise l'image `iryx-worker:local` désormais déclarée avec `build:` (context `..`, `docker/Dockerfile.worker`) ; sa `command:` par défaut lance la sonde `/app/backend/docker/check_airgap.py` et reste surchargeable pour exécuter une analyse forensique à la demande.
- `backend/docker/check_airgap.py` : une seule tentative TCP vers `1.1.1.1:443` ; validation sur `errno.ENETUNREACH` seul, sans dépendance au libellé localisé ; code 0 uniquement sur ce blocage, code 1 avec message explicite sinon (connexion réussie ou erreur différente), sans repli.
- Aucune modification de `backend/src/**`, des migrations, des lockfiles, des Dockerfiles 9.1 ni de la CMD Celery, conformément au bloc gelé.
- Après revue : correction de l'information sur l'emplacement des preuves scellées, du `build:` et du caractère surchargeable de `iryx-analysis`, de la validation par errno, des instructions `docker inspect`/migration du README, et ajout d'un test de placement réel du fichier scellé.

**Vérifications finales :** `uv run pytest -q tests/unit` (919 passed) ; `uv run pytest -q tests/unit/test_deployment_config.py` (22 passed) ; `uv run ruff check tests docker/check_airgap.py` (All checks passed) ; `uv run ruff format --check tests/unit/test_deployment_config.py docker/check_airgap.py` (2 files already formatted) ; `docker compose --env-file .env.example config --quiet` (OK, profil `analysis` inclus) ; `docker compose ... config --services` (4 par défaut, 5 avec `--profile analysis`). Les corrections de revue ont été rejouées intégralement de ce côté.

**Limites connues :**
- Le démon Docker est absent : `docker inspect` et l'exécution réelle de `iryx-analysis` n'ont pas pu être exercés. Les comportements sont validés statiquement et par mocks unitaires.
- L'image `iryx-worker:local` doit être construite avant le premier `docker compose --profile analysis run --rm iryx-analysis`.
- Un volume brut prérempli avec des fichiers non lisibles par l'uid 10001 restera illisible ; les fichiers gérés par l'application résident dans le staging writable.
- Le montage sépare désormais brut et staging : si des données préexistaient dans l'ancien volume `evidence_data` monté sur `/data/evidence`, une migration manuelle sera nécessaire (aucune constatée ici, démon absent).

## Spec Change Log

## Review Triage Log

Préfixes : `VG` = verification-gap (1 gap pré-vérifié + 2 « other »), `BH` = blind hunter (N = min(⌊√31,94⌋+1, 10) = 6 ; 11 constats rendus), `EC` = edge-case hunter (3 constats). Chaque verdict a été rendu après relecture du fichier cité et de son contexte.

- **VG-1** (pré-vérifié) — `backend/docker-compose.yml:46-47,78-79,108-109` — `medium` — le déplacement du volume `evidence_data` vers `/data/evidence/raw:ro` rend invisibles les preuves déjà scellées dans l'ancien `/data/evidence/staging` ; aucun test ni helper d'upgrade ne couvre ce cas, et le montage `:ro` interdit la réparation in place. La limite est déjà consignée dans les notes d'implémentation, sans volume préexistant observé. → `defer`.
- **VG-2** — `backend/docker-compose.yml:96-110`, `README.md:293` — `high` — constat vrai : l'entrée figée du service est `python /app/backend/docker/check_airgap.py`, donc `iryx-analysis` n'exécute aucune analyse forensique, contrairement au bloc gelé qui lui confie « les analyses et la sonde air-gap ». Le fait que les sous-processus tournent encore dans l'API/worker est une conséquence acceptée de la décision C, pas un défaut distinct. → `patch`.
- **VG-3** — `README.md:291`, `## Implementation Notes` — `medium` — `evidence/services.py:64-75` écrit dans `EVIDENCE_STAGING_PATH` et `evidence/tasks.py:145-146` y applique `chmod 0o440` : les preuves scellées résident dans le volume staging writable, pas dans le volume brut `:ro` ; la documentation affirme l'inverse. → `patch`.
- **BH-1** — `README.md:291`, `## Implementation Notes` — `medium` — doublon exact de VG-3, même preuve. → `patch`.
- **BH-2** — `backend/docker-compose.yml:96-110` — `high` — doublon de VG-2, même preuve. → `patch`.
- **BH-3** — `backend/docker-compose.yml:96-97` — `medium` — vérifié : `iryx-analysis` déclare `image: iryx-worker:local` sans `build:`, et la procédure `docker compose --profile analysis run --rm iryx-analysis` n'est précédée d'aucune étape de build ; sur un dépôt cloné, Compose tentera de résoudre l'image depuis un registry au lieu de la construire. → `patch`.
- **BH-4** — `README.md:297` — `low` — vérifié : le `--rm` supprime le conteneur dès la fin de la sonde, donc `docker inspect iryx-analysis` ne peut plus rien montrer ; la phrase laisse croire que les trois services sont inspectables de la même manière. → `patch`.
- **BH-5** — `backend/docker/check_airgap.py:48` — `medium` — vérifié : exiger la chaîne anglaise littérale en plus de `errno.ENETUNREACH` transforme un blocage réel en échec si `strerror` est localisé. → `patch`.
- **BH-6** — `backend/docker/check_airgap.py:25-30` — `low` — vérifié : la fonction annonce `OSError | None` mais lève toujours l'erreur ; la branche « erreur retournée » de `main()` est morte et un connecteur injecté retournant une `OSError` serait traité comme un succès. → `patch`.
- **BH-7** — `backend/docker-compose.yml:100-110` — `false` — une fois l'entrée de VG-2 corrigée pour permettre l'exécution d'outils à la demande, les montages de preuves/symboles et les variables de chemin sont précisément ce dont le conteneur a besoin ; les retirer casserait son rôle. → rejeté.
- **BH-8** — `README.md:290-298` — `low` — vérifié : aucune mention de la migration manuelle des anciens fichiers `evidence_data` vers `evidence_staging_data` n'est donnée à l'opérateur, alors que le changement de montage la rend nécessaire. → `patch`.
- **BH-9** — `backend/tests/unit/test_deployment_config.py:249-264` — `medium` — vérifié : les tests n'assèrent que des chaînes de configuration ; aucun ne vérifie que le fichier scellé atterrit bien dans le staging et que le brut reste vide avec les chemins du compose. → `patch`.
- **BH-10** — `_bmad-output/implementation-artifacts/sprint-status.yaml:101` — `low` — vérifié : le suivi reste à `in-progress` alors que la spec est passée en `in-review` ; alignement à faire lors de la clôture de revue. → `patch`.
- **BH-11** — `backend/docker/Dockerfile.api:25`, `backend/docker/Dockerfile.worker:55` — `low` — écart réel mais aucun flux documenté n'exécute ces images sans les surcharges du compose ; les images de 9.1 sont gelées et l'impact est négligeable. → rejeté.
- **EC-1** — `backend/tests/unit/test_deployment_config.py:254-256` — `false` — le test assère la chaîne exacte `evidence_data:/data/evidence/raw:ro` (`RAW_MOUNT in volumes`) en plus de l'absence de montage brut nu : un `:rw` ou un suffixe supplémentaire fait échouer l'assertion. Le fragment `v.split(':')[1]` cité n'existe pas dans le fichier. → rejeté.
- **EC-2** — `backend/docker-compose.yml:96-97` — `medium` — doublon de BH-3, même preuve. → `patch`.
- **EC-3** — `backend/docker-compose.yml:106` — `high` — doublon de VG-2 : `entrypoint` figé transforme tout `command` fourni à `docker compose run` en arguments de la sonde, donc les outils forensiques ne peuvent pas être lancés dans ce conteneur. → `patch`.

## Verification

**Commands:**
- `cd backend && docker compose --env-file .env.example config --quiet` -- valide.
- `cd backend && uv run pytest -q tests/unit/test_deployment_config.py` -- vert.
- `cd backend && uv run ruff check tests` -- `All checks passed!`.
- `cd backend && docker compose --profile analysis build iryx-analysis` -- prérequis : construit l'image worker partagée.
- `cd backend && docker compose --profile analysis run --rm iryx-analysis` -- sonde air-gap (commande par défaut, nécessite un démon).
- `cd backend && docker compose --profile analysis run --rm iryx-analysis <commande-d'analyse>` -- analyse forensique à la demande, réseau coupé.

**Manual checks (if no CLI):**
- Inspecter le compose : brut `:ro`, staging writable, profil `analysis`, aucun secret.
- Vérifier que les quatre services par défaut et le port 8000 restent inchangés.
