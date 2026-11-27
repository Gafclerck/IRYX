---
title: 'Story 9.1 : Configuration Dockerfile multi-étapes et Docker Compose mono-serveur (D-22)'
type: 'feature'
created: '2026-11-27'
status: 'done'
baseline_commit: '9a522f479f4ad4b31d3b9f6a68728177a7ddc77f'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-9-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Aucun Dockerfile, aucun `.dockerignore` et aucun `docker-compose.yml` n'existent : la plateforme ne démarre qu'à la main (uv sync, alembic, uvicorn, celery), avec un lockfile `backend/uv.lock` obsolète et des chemins forensiques non provisionnés. Le déploiement n'est donc ni reproductible ni opérable en une commande.

**Approach:** Construire deux images multi-étapes fondées sur `uv` et le lockfile complet de la racine, un entrypoint API qui attend PostgreSQL puis applique les migrations avant d'écouter, et un `docker-compose.yml` unique montant exactement quatre services (`postgres`, `redis`, `iryx-api`, `iryx-worker`) en utilisateur non-root `10001:10001`, avec symboles Volatility 3 préchargés et vérifiés.

## Boundaries & Constraints

**Always:** Le contexte de build est la **racine du dépôt** (seul `uv.lock` racine contient les 26+ dépendances et `[manifest]`) ; `uv sync --frozen --no-dev` ; base `python:3.12-slim` ; utilisateur `iryx` uid/gid `10001`. L'API attend `pg_isready`, exécute `alembic upgrade head`, puis `exec uvicorn iryx.main:app --host 0.0.0.0 --port 8000` : aucun port HTTP n'est ouvert avant la fin des migrations. Le worker lance `celery -A iryx.core.celery_app worker --loglevel=info --pool=threads --concurrency=4`. Le compose définit exactement quatre services nommés `postgres` (PostgreSQL 16), `redis` (Redis 7), `iryx-api`, `iryx-worker`, avec healthchecks sur les quatre et dépendances en `condition: service_healthy`. Aucun secret en dur dans le compose : `env_file: .env` (non versionné, calqué sur `.env.example`) et interpolation `${POSTGRES_USER}` / `${POSTGRES_PASSWORD}` / `${POSTGRES_DB}` pour construire l'URL interne ; seuls les ports `8000` (API) sont publiés sur l'hôte. Les symboles ISF Windows sont fournis par l'opérateur dans `backend/docker/symbols/windows.zip` (chemin ignoré par git), copiés dans `/opt/volatility3/symbols` et vérifiés par SHA-256 au build ; absence ou écart de hash fait échouer le build et le prérequis est documenté dans le README ; aucun téléchargement réseau, y compris au build. Les répertoires `/data/evidence` et `/data/evidence/staging` sont accessibles en écriture au worker. Logs JSON sur stdout.

**Never:** Aucun `create_all` ni migration manuelle à l'exécution, aucun cinquième service, aucune publication des ports 5432/6379, aucun secret ou chemin hôte visible dans le compose, aucun téléchargement de symboles au runtime, aucune modification du code applicatif `backend/src`, de `backend/uv.lock` ni des migrations. Le durcissement (cap_drop, `network_mode: none`, montage `:ro` des preuves brutes) reste l'objet de la Story 9.2 et n'est pas anticipé ici.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Démarrage nominal | `cd backend && docker compose up -d`, `.env` renseigné | 4 conteneurs `healthy`, API répond `GET /health` 200, migrations au head `010` | N/A |
| PostgreSQL indisponible | Service `postgres` en retard au démarrage | L'entrypoint API boucle sur `pg_isready` sans crasher ; worker attend `service_healthy` | Timeout puis sortie non nulle avec message explicite |
| Migration en échec | Revision Alembic cassée ou DB inaccessible | API ne commence pas à écouter, conteneur `unhealthy` | Logs structurés, `exec` non atteint |
| Symboles absents ou corrompus | Archive fournie avec un SHA-256 différent de `c7e4…51b3` | Build du worker interrompu avant etag final | Message d'erreur explicite naming le chemin et le hash attendu |
| Identité des conteneurs | `docker compose exec iryx-api id` et `docker compose exec iryx-worker id` | `uid=10001(iryx) gid=10001(iryx)` dans les deux | N/A |
| Configuration sans démon | `docker compose config` sur hôte sans daemon Docker | Configuration résolue et valide, secrets lus depuis `backend/.env` | Échec si `.env` manquant, sans valeur par défaut sensible |

</frozen-after-approval>

## Code Map

- `pyproject.toml:1-5`, `uv.lock:1-11` -- workspace uv et lock complet ; à lire, jamais à modifier ; définissent le contexte de build racine.
- `backend/pyproject.toml:10-45` -- Python >=3.12, `volatility3==2.7.0`, psycopg, celery, presidio ; `fastapi[standard]` déjà commité séparément (entrée `deferred-work.md` soldée).
- `backend/uv.lock` -- lock obsolète (26 paquets, sans `[manifest]`) : ne pas l'utiliser comme source de vérité pour l'image.
- `backend/docker/Dockerfile.api`, `backend/docker/Dockerfile.worker` -- nouveaux ; multi-étapes `uv`, utilisateur 10001, symboles pour le worker uniquement.
- `backend/docker/entrypoint-api.sh` -- nouveau ; attente PostgreSQL, `alembic upgrade head`, puis `exec uvicorn`.
- `backend/docker/symbols/` -- emplacement du `windows.zip` fourni par l'opérateur ; ignoré par git via un `.gitignore` local dédié.
- `backend/docker-compose.yml` -- nouveau ; quatre services, healthchecks, `env_file: .env`, volumes nommés, build context `..`.
- `/.dockerignore` -- nouveau ; exclude `.venv`, caches, `.env`, `evidence`, `_bmad-output`, `docs`, `mulder_repo`, `sources-frontend`, `.git`.
- `backend/.env.example:26-51` -- compléter avec `POSTGRES_USER/PASSWORD/DB` et documenter les hôtes internes ; ne jamais y mettre de vrai secret.
- `README.md:236-274` -- remplacer/extendre la procédure manuelle par la commande Compose et les vérifications.
- `backend/src/iryx/core/config.py:30,49,66,98-104` -- `SECRET_KEY` obligatoire dès l'import, chemins `/data/evidence`, `/opt/volatility3/symbols` ; contrat à respecter, pas à modifier.
- `backend/src/iryx/main.py:56-111` -- `iryx.main:app` et `/health` (réponse thin, sans check DB).
- `backend/src/iryx/core/celery_app.py:14-32` -- instance `iryx`, broker/backend Redis, autodiscover `iryx.evidence`.
- `backend/alembic.ini:5-23`, `backend/migrations/env.py:37-39` -- URL lue depuis `get_settings().database_url`, tête `010`.
- `backend/src/iryx/gateway/tools/volatility_analyzer.py:500-518` -- appelle déjà `--offline -s settings.volatility_symbols_path` ; ne pas toucher.

## Tasks & Acceptance

**Execution:**
- [x] `/.dockerignore` -- exclure du contexte de build les artefacts locaux et les données forensiques.
- [x] `backend/docker/Dockerfile.api` -- image multi-étapes uv (lock racine), utilisateur `iryx:10001`, copie de l'entrypoint, healthcheck HTTP.
- [x] `backend/docker/Dockerfile.worker` -- même socle, ajout des symboles ISF et vérification d'intégrité au build, commande Celery par défaut.
- [x] `backend/docker/entrypoint-api.sh` -- sonde `pg_isready`, `alembic upgrade head`, `exec uvicorn`, sans `create_all`.
- [x] `backend/docker/symbols/.gitignore` -- ignorer `windows.zip` fourni localement tout en versionnant le dossier cible du build.
- [x] `backend/docker-compose.yml` -- quatre services, dépendances `service_healthy`, healthchecks, `env_file: .env`, volumes pour preuves et symboles, interpolation des secrets Postgres.
- [x] `backend/.env.example`, `README.md` -- documenter la copie de `.env`, la commande de démarrage, le prérequis symboles et les vérifications.
- [x] `backend/tests/unit/test_deployment_config.py` -- tester statiquement la configuration (quatre services, healthchecks, uid, absence de secrets en dur, hash des symboles, contextes de build).

**Acceptance Criteria:**
- Given un `.env` renseigné et le prérequis symboles satisfait, when `docker compose up -d` est lancé depuis `backend/`, then les quatre services atteignent `healthy` et `GET http://localhost:8000/health` répond 200.
- Given la base vide, when l'API démarre, then `alembic upgrade head` est appliqué jusqu'à `010` avant l'ouverture du port HTTP.
- Given PostgreSQL indisponible, when les conteneurs démarrent, then l'API attend sans crash et le worker attend un service `healthy`.
- Given un conteneur API ou worker en fonctionnement, when `id` y est exécuté, then l'utilisateur est `iryx` avec `uid=10001` et `gid=10001`.
- Given l'image worker construite, when les symboles sont inspectés, then `/opt/volatility3/symbols` est présent et son empreinte correspond au hash figé D-26.
- Given le dépôt cloné sans `.env`, when `docker compose config` est lancé, then la configuration échoue explicitement sans révéler ni inventer de secret.

## Implementation Notes

### 2026-11-27 — implémentation (baseline `9a522f479f4ad4b31d3b9f6a68728177a7ddc77f`)

- Contexte de build racine confirmé : seuls `pyproject.toml` + `uv.lock` racine sont copiés dans l'étape `builder`, avec `uv sync --frozen --no-dev` et `UV_PROJECT_ENVIRONMENT=/opt/venv`. Le lock obsolète `backend/uv.lock` n'est pas utilisé comme source de vérité.
- Symboles : archive `windows.zip` fournie par l'opérateur, vérifiée par `sha256sum` dans l'étape `symbols` avant extraction ; absence, hash divergent ou archive vide => échec du build avec message explicite. Aucun `curl`/`wget` de symboles.
- Entrypoint API : `pg_isready` avec timeout configurable, puis `alembic upgrade head`, puis `exec uvicorn` ; aucun `create_all`.
- Corrections apportées après lecture du diff : synchronisation de `epic-9` en `in-progress` dans `sprint-status.yaml` ; exclusion des `.env` imbriqués (`**/.env`, `**/.env.*`) du contexte de build pour éviter de cuire les secrets locaux dans l'image ; retrait de `env_file: .env` du service `postgres` (lequel ne reçoit que ses trois variables via interpolation) ; suppression d'une variable de boucle inutilisée détectée par ruff.
- `EVIDENCE_STAGING_PATH` est fixé explicitement dans le compose, en cohérence avec le champ `evidence_staging_path` de `Settings` (`core/config.py`).

**Vérifications exécutées :** `uv run pytest -q tests/unit/test_deployment_config.py` (14 passed) ; `uv run pytest -q` (1106 passed) ; `uv run ruff check src tests` (All checks passed) ; `bash -n docker/entrypoint-api.sh` (OK) ; `docker compose --env-file <copie de .env.example> config --quiet` (OK) ; `docker compose config --quiet` avec le `.env` local obsolète (échec explicite sur `POSTGRES_USER`, aucun secret révélé).

**Limites connues :**
- Le démon Docker est absent de l'environnement : les AC nécessitant un démarrage réel (4 services `healthy`, `GET /health` 200, migrations effectives, `id` dans les conteneurs) sont vérifiées structurellement par les tests statiques mais non validées empiriquement.
- `backend/docker/symbols/windows.zip` n'a pas été fourni : la garde d'intégrité est en place, mais l'extraction complète et le hash réel n'ont pas été exercés. Le build worker échouera tant que l'archive conforme n'est pas déposée.
- Le `.env` local préexistant (gitignored, non modifié) ne contient pas `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` : l'opérateur doit le régénérer depuis `.env.example` avant `docker compose up`.
- Le volume nommé `symbols_data` est initialisé depuis l'image à sa première création ; un volume préexistant vide masquerait les symboles embarqués.
- `POSTGRES_PASSWORD` doit rester URL-safe (éviter `@`, `/`, `:`, `#`) car il est interpolé dans `DATABASE_URL` ; contrainte documentée dans `.env.example`.

## Spec Change Log

## Review Triage Log

### 2026-11-27 — revue initiale (3 couches simultanées)

Préfixes : `VG` = verification-gap (finding pré-vérifié par la couche, 4 principaux + 2 « other »), `BH` = blind hunter (N = min(⌊√46,933⌋+1, 10) = 7 ; 13 constats rendus), `EC` = edge-case hunter (14 constats). Chaque verdict a été rendu après lecture du fichier cité et, si nécessaire, des appelants/guards.

- **VG-1** — `backend/tests/unit/test_deployment_config.py:38-44` — `medium` — pré-vérifié : remplacer `/health` par `/healthz` dans la sonde API laisse le test vert et rend l'API `unhealthy` en runtime. Correctif : assérer les commandes/cibles exactes des quatre sondes. → `patch`.
- **VG-2** — `backend/docker/entrypoint-api.sh:17-31` — `medium` — pré-vérifié : retirer `-h "$PG_HOST"` conserve l'ordre des sous-chaînes testé, mais la sonde interroge alors la socket locale et l'entrypoint time-out. Correctif : validation numérique du timeout + assération de `-h "$PG_HOST"`. → `patch`.
- **VG-3** — `backend/docker/Dockerfile.worker:33-37` — `medium` — pré-vérifié : inverser `!=` en `=` conserve tous les fragments assérés et fait rejeter l'archive conforme / accepter une archive falsifiée. Correctif : assérer l'opérateur de comparaison et la garde d'archive vide. → `patch`.
- **VG-4** — `/.dockerignore:11-16` — `medium` — pré-vérifié : ajouter `!backend/.env` après les exclusions laisse les motifs présents et cuit les secrets dans l'image. Correctif : interdire toute négation réintégrant un `.env`. → `patch`.
- **VG-5** (`other`) — `backend/docker-compose.yml:73` — `low` — la copie depuis l'image au premier remplissage du volume nommé fournit bien les symboles ; un volume précréé vide est nécessaire pour masquer l'ISF, scénario sans cas d'usage courant et déjà consigné comme limite connue. Tout correctif (retrait d'un volume prévu au spec, ou entrypoint worker + garde runtime) dépasse une correction directe. → rejeté.
- **VG-6** (`other`) — `/.dockerignore` + `COPY backend ./backend` — `low` — l'archive n'est pas un secret et n'alourdit que l'image API ; l'exclure globalement casserait l'étape `symbols` du worker, donc il faut restructurer le contexte de build. → rejeté.
- **BH-1** — `epic-9-context.md:21` (cité `:186`, fichier de 50 lignes) — `low` — l'exigence « au démarrage » du document de planification est remplacée par le bloc gelé, qui impose une vérification **au build** (décision humaine option B) ; la partie volume partagé avec VG-5 reste `low`. → rejeté.
- **BH-2** — `.dockerignore` / `windows.zip` — `low` — doublon exact de VG-6, même preuve. → rejeté.
- **BH-3** — note de vérification de la spec (`--env-file <copie>`) — `low` — vrai : `env_file: .env` reste résolu depuis `backend/`, donc l'option `--env-file` ne remplace pas le fichier. Son correctif est une édition de la spec elle-même (règle 86) ; la note est corrigée séparément comme housekeeping, sans toucher au code. → rejeté.
- **BH-4** — `docker-compose.yml:34,64` — `medium` — vrai : un mot de passe contenant `@ / : #` casse `DATABASE_URL`. Mais le bloc gelé impose l'interpolation directe de `${POSTGRES_PASSWORD}` dans l'URL et l'intent exclut d'autres schémas ; la contrainte « URL-safe » est documentée dans `.env.example` et le README. → rejeté comme hors-intent (règle 84).
- **BH-5** — `docker-compose.yml:82` (profondeur de la sonde) — `low` — le process-scan ne détecte pas un broker mort après le démarrage, mais le spec exige seulement une sonde par service et `redis` est déjà gate en `service_healthy` ; un `celery inspect ping` ajoute une surface non demandée. → rejeté.
- **BH-6** — `tests/unit/test_deployment_config.py:86-87` — `medium` — vérifié : les assérations `"network_mode: none" not in text` et `"cap_drop" not in text` font échouer la Story 9.2, qui doit précisément ajouter ces durcissements (frozen `Never`). Correctif : supprimer ces deux lignes. → `patch`.
- **BH-7** — sonde API définie deux fois — `low` — les deux définitions sont imposées par le spec (image + compose) et Compose écrase l'image par design ; l'écart n'a pas de dommage démontré et un test de parité ajoute une surface. → rejeté.
- **BH-8** — `entrypoint-api.sh:19,24` — `medium` — vérifié : avec `PG_READY_TIMEOUT_SECONDS=abc`, `[ "$elapsed" -ge "$PG_TIMEOUT" ]` échoue silencieusement dans le `if` (set -e inopérant), donc la boucle ne sort jamais. Correctif : garde numérique explicite avec log JSON + sortie 1, et documentation des trois variables. → `patch`.
- **BH-9** — valeurs placeholders de `.env.example` — `medium` — la validation de production de `SECRET_KEY`/`POSTGRES_PASSWORD` est un comportement préexistant de `core/config.py`, non créé par cette story, et son correctif modifierait `backend/src` que le bloc gelé interdit. → `defer`.
- **BH-10** — logs worker non JSON — `low` — vrai pour Celery, mais la CMD worker et l'interdiction de modifier `backend/src` sont gelées ; les logs restent sur stdout et l'impact est rédactionnel. Correctif hors correction directe. → rejeté.
- **BH-11** — `README.md:290-295` — `low` — vérifié : le `cd backend` de §8.6 est redondant après §8.4 et mène à `backend/backend`. Correctif : suppression directe. → `patch`.
- **BH-12** — tags d'images flottants — `low` — l'intent gèle explicitement `python:3.12-slim`, PostgreSQL 16 et Redis 7 ; épingler par digest contredirait le bloc gelé. → rejeté.
- **BH-13** — `README.md:248-255` — `low` — vérifié : §7 annonce Windows/PowerShell mais §8.3 ne donne que `sha256sum`. Correctif : ajouter l'équivalent `Get-FileHash`. → `patch`.
- **EC-1** — `docker-compose.yml:82` — `high` — vérifié : un script console uv démarre par `#!/opt/venv/bin/python`, donc `/proc/<pid>/cmdline` donne `argv[0]=/opt/venv/bin/python` et le script celery en `argv[1]` ; `parts[0].endswith('celery')` est toujours faux et le worker reste `unhealthy` (AC1 cassé). Correctif : tester n'importe quelle partie de la ligne de commande pour un chemin se terminant par `celery`. → `patch`.
- **EC-2** — `docker-compose.yml:34,64` — `medium` — doublon de BH-4, même preuve et même rejet hors-intent. → rejeté.
- **EC-3** — `docker-compose.yml:73` — `low` — doublon de VG-5, même preuve. → rejeté.
- **EC-4** — `docker-compose.yml:39,72` — `low` — les deux Dockerfiles créent `/data/evidence/staging` dans l'image avant l'attachement du volume, qui est donc copié au premier remplissage ; un volume préexistant sans staging est spéculatif et le correctif ajoute une garde non démontrée. → rejeté.
- **EC-5** — `docker-compose.yml:9` — `medium` — comportement préexistant de l'image PostgreSQL officielle (les identifiants ne sont appliqués qu'à un volume vide), non causé par cette story ; nécessite une procédure opérationnelle de recréation. → `defer`.
- **EC-6** — `entrypoint-api.sh:19,24` — `medium` — doublon de BH-8, même preuve. → `patch`.
- **EC-7** — `entrypoint-api.sh:35` — `medium` — un verrou Alembic peut bloquer indéfiniment ; la matrice gelée couvre l'échec de migration mais pas un timeout, et ajouter `timeout` + `MIGRATION_TIMEOUT_SECONDS` crée une surface nouvelle non démontrée dans cette exécution. → `defer`.
- **EC-8** — `README.md:274` — `low` — `curl -fsS` sans `--max-time` peut attendre indéfiniment si l'API accepte le socket sans répondre. Correctif direct : `--max-time 5` (et mise à jour du fragment dans le test). → `patch`.
- **EC-9** — `.dockerignore` / `windows.zip` — `low` — doublon de VG-6. → rejeté.
- **EC-10** — `docker-compose.yml:82` (race `/proc`) — `low` — une disparition de processus entre `glob` et `open` est transitoire et absorbée par les 12 tentatives ; un `try/except OSError` ajoute une garde pour un état non démontré. → rejeté.
- **EC-11** — `tests/unit/test_deployment_config.py:86-87` — `medium` — doublon de BH-6, même preuve. → `patch`.
- **EC-12** — `entrypoint-api.sh:9-10` — `low` — `PG_HOST`/`PG_PORT` viennent du `.env` interne, pas d'une entrée hostile ; échapper les guillemets ajoute une surface sans cas d'usage. → rejeté.
- **EC-13** — `README.md:297-305` — `medium` — vérifié : après `uv sync`, l'environnement n'est pas activé et `alembic`/`uvicorn`/`celery` ne sont pas sur le PATH ; le mode manuel documenté échoue immédiatement. Correctif direct : préfixer `uv run`. → `patch`.
- **EC-14** — `docker-compose.yml:82` (claim AC1) — `high` — doublon de EC-1, même preuve et même correctif. → `patch`.

**Regroupement et routage des survivants :**

- **P1 (`high`)** — EC-1 + EC-14 : sonde worker invalide due à `argv[0]` Python. → `patch`.
- **P2 (`medium`)** — VG-1 + VG-2 + VG-3 + VG-4 : tests statiques trop faibles pour les sondes, l'entrypoint, la garde SHA-256 et les exclusions `.dockerignore`. → `patch`.
- **P3 (`medium`)** — BH-6 + EC-11 : assérations qui interdisent le durcissement de la Story 9.2. → `patch`.
- **P4 (`medium`)** — BH-8 + EC-6 : timeout non numérique non validé et variables non documentées. → `patch`.
- **P5 (`medium`)** — BH-11 + BH-13 + EC-8 + EC-13 : procédures README erronées (`cd` redondant, commandes sans `uv run`, empreinte Windows absente, `curl` sans borne). → `patch`.
- **D1/D2/D3 (`medium`)** — BH-9, EC-5, EC-7 : limitations opérationnelles préexistantes ou hors surface gelée. → `defer`.

Aucune entrée `intent_gap` ni `bad_spec` : le bloc gelé tranche explicitement chaque point soulevé (vérification des symboles au build, interpolation directe de l'URL, CMD Celery exacte, images de base nommées). Le routage `patch` peut donc procéder sans loopback.

## Verification

**Commands:**
- `cd backend && docker compose config --quiet` -- expected: configuration valide (le démon Docker n'est pas nécessaire). `backend/.env` doit exister (même avec des valeurs factices) car `env_file: .env` est résolu depuis `backend/` ; le régénérer depuis `.env.example` si besoin. L'option `--env-file` ne remplace pas ce fichier.
- `cd backend && uv run pytest -q tests/unit/test_deployment_config.py` -- expected: vert.
- `cd backend && uv run ruff check src tests` -- expected: `All checks passed!`.
- `docker compose up -d && docker compose ps` -- expected: quatre services `healthy` (nécessite un démon Docker actif, absent sur la machine de planification).

**Manual checks (if no CLI):**
- Inspecter `docker-compose.yml` : aucun secret en dur, aucun port 5432/6379 publié, tous les `build.context` pointent vers la racine du dépôt.
