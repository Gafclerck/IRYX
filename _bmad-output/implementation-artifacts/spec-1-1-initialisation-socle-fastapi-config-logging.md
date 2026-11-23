---
title: 'Story 1.1 : Initialisation du socle applicatif FastAPI, configuration Pydantic Settings et logging JSON'
type: 'feature'
created: '2026-11-23'
status: 'done'
baseline_commit: 'eda296d0ec403581171eec20e3ef4e33816ba8c0'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/docs/05-conventions-backend.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La plateforme IRYX ne dispose pas encore de son socle applicatif back-end. Il est indispensable d'établir dès la première étape une structure modulaire saine, typée, sécurisée et conforme aux normes d'architecture du projet (FastAPI, Pydantic Settings, logging JSON sans secrets, gestion d'exceptions normalisée).

**Approach:** Initialiser le package applicatif `backend` avec l'outillage `uv`, configurer la gestion des dépendances et du linter Ruff, implémenter la configuration centralisée immuable `Settings`, le formateur de logs JSON basé sur la bibliothèque standard `logging` masquant les données sensibles, les gestionnaires d'erreurs HTTP standardisés sans fuite de stack trace, et exposer l'endpoint de vérification de santé `GET /health`.

## Boundaries & Constraints

**Always:**
- Respecter l'arborescence et l'organisation modulaire strictes sous `backend/src/iryx/` définies dans `docs/05-conventions-backend.md` et `architecture.md`.
- Renvoyer un format de réponse d'erreur HTTP JSON standardisé : `{"error": {"code": "<CODE>", "message": "<MESSAGE>"}}`.
- Masquer systématiquement tout secret, mot de passe ou jeton d'authentification dans la journalisation console JSON (`timestamp`, `level`, `logger`, `message`, `context`).
- Maintenir une conformité stricte avec `ruff` (zéro avertissement, zéro erreur, Python 3.12).
- Couvrir l'ensemble des composants du socle par des tests automatisés `pytest` et `httpx`.

**Never:**
- Aucune dépendance tierce hors du tableau des décisions figées D-01 à D-26 (notamment pas de `structlog`, utilisation exclusive de `logging`).
- Aucune fuite de trace d'exécution (stack trace) ni de chemin de fichier système interne dans les réponses HTTP (codes 422, 500).
- Aucune logique métier dans les routeurs HTTP (`main.py` et contrôleurs minces).
- Pas d'accès ou d'initialisation de base de données à cette étape (réservé à la Story 1.2).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Requête nominale de santé | `GET /health` | HTTP 200 `{"status": "ok", "version": "0.1.0"}` | N/A |
| Variable d'environnement manquante ou erronée | Démarrage sans variables obligatoires ou avec type invalide | Blocage au démarrage via `pydantic-settings` avec exception explicite | Message d'erreur clair sans fuite de données sensibles |
| Exception serveur interne non gérée | Exception inattendue levée durant le cycle de requête | HTTP 500 `{"error": {"code": "INTERNAL_SERVER_ERROR", "message": "Une erreur inattendue est survenue."}}` | Journalisation au niveau ERROR en JSON avec masquage |
| Requête malformée | Payload JSON invalide ou structure non conforme | HTTP 422 avec format d'erreur normalisé `{"error": {"code": "VALIDATION_ERROR", "message": "Données de requête invalides."}}` | Format d'erreur sans stack trace ni introspection de code |
| Émission d'un log contenant un secret | Appel de logging avec un dictionnaire comportant `password` ou `api_key` | Émission JSON où les valeurs des champs sensibles sont remplacées par `***REDACTED***` | Filtrage automatique dans le formateur JSON |

</frozen-after-approval>

## Code Map

- `backend/pyproject.toml` -- Configuration du projet Python 3.12 géré avec `uv`, déclarations des dépendances FastAPI, Pydantic v2, pydantic-settings, pytest, ruff
- `backend/ruff.toml` -- Règles de formatage et linting strictes (target py312, line-length 100, règles E, F, I, UP, B, SIM)
- `backend/.env.example` -- Modèle exhaustif des variables d'environnement documentées sans secrets
- `backend/src/iryx/__init__.py` -- Point d'ancrage du package iryx (définit `__version__ = "0.1.0"`)
- `backend/src/iryx/main.py` -- Point d'entrée de l'application FastAPI, inclusion du routeur `/health`, middlewares CORS et exceptions
- `backend/src/iryx/core/__init__.py` -- Package du noyau transversal
- `backend/src/iryx/core/config.py` -- Configuration applicative typée dérivée de `pydantic_settings.BaseSettings`
- `backend/src/iryx/core/logging.py` -- Formateur JSON de la bibliothèque standard `logging` avec masquage des secrets
- `backend/src/iryx/core/exceptions.py` -- Hiérarchie des exceptions applicatives et gestionnaires HTTP d'erreur standardisés
- `backend/tests/conftest.py` -- Fixtures pytest, configuration de test et client HTTP `httpx.AsyncClient`
- `backend/tests/unit/test_health.py` -- Tests unitaires et d'intégration de l'endpoint `/health`
- `backend/tests/unit/test_config.py` -- Tests unitaires de la configuration `Settings` et validation des types
- `backend/tests/unit/test_logging.py` -- Tests unitaires de la sérialisation JSON et du masquage des secrets
- `backend/tests/unit/test_exceptions.py` -- Tests unitaires des gestionnaires d'exceptions HTTP 422 et 500

## Tasks & Acceptance

**Execution:**
- [x] `backend/pyproject.toml` -- Configurer le projet uv et les dépendances du socle applicatif -- Assurer l'installation reproductible D-01, D-02, D-03, D-04, D-20, D-21
- [x] `backend/ruff.toml` -- Définir les règles de conformité Ruff -- Garantir la conformité D-21 et la qualité de code
- [x] `backend/.env.example` -- Rédiger le gabarit des variables d'environnement -- Documenter la configuration requise conformément à la règle 10
- [x] `backend/src/iryx/core/config.py` -- Implémenter la classe `Settings` avec `pydantic-settings` -- Fournir une configuration typée et validée (D-04)
- [x] `backend/src/iryx/core/logging.py` -- Implémenter le formateur JSON standard et le filtre de masquage des données sensibles -- Respecter D-23 et la règle 13
- [x] `backend/src/iryx/core/exceptions.py` -- Implémenter les exceptions applicatives et les gestionnaires de réponses d'erreur HTTP unifiées -- Respecter la règle 6
- [x] `backend/src/iryx/main.py` -- Créer l'application FastAPI avec initialisation du logging, gestionnaires d'exceptions et route `/health` -- Respecter D-03
- [x] `backend/tests/conftest.py` et `backend/tests/unit/*` -- Écrire les tests unitaires couvrant santé, configuration, logging et gestion des erreurs -- Valider 100% des critères d'acceptation (D-20)

**Acceptance Criteria:**
- Given les dépendances installées via `uv sync`, when l'application est lancée et `GET /health` interrogé, then le statut HTTP est 200 avec le corps `{"status": "ok", "version": "0.1.0"}`.
- Given une variable obligatoire manquante dans l'environnement, when l'application démarre, then `pydantic-settings` bloque le démarrage sans divulguer de données sensibles.
- Given une exception inattendue survenue dans le code, when la réponse client est générée, then le statut est HTTP 500 avec `{"error": {"code": "INTERNAL_SERVER_ERROR", "message": "Une erreur inattendue est survenue."}}` sans trace de pile.
- Given l'émission de logs applicatifs, when ils sont écrits sur la sortie standard, then chaque ligne est un objet JSON valide contenant `timestamp`, `level`, `logger`, `message` et `context`, sans secret en clair.
- Given la commande `uv run ruff check backend/` et `uv run ruff format --check backend/`, then aucune violation n'est relevée.
- Given la commande `uv run pytest backend/tests`, then tous les tests unitaires passent avec succès.

## Implementation Notes

- Initialisation de la structure modulaire `backend/src/iryx/` et configuration de l'espace de travail avec `uv`.
- Création de `backend/pyproject.toml` (FastAPI, Pydantic, Pydantic Settings, pytest, httpx, ruff) et `backend/ruff.toml` (target py312, line-length 100, règles E, W, F, I, UP, B, SIM).
- Création du gabarit `.env.example` et du fichier local `.env` documentant toutes les variables nécessaires sans secrets réels.
- Implémentation de `Settings` dans `backend/src/iryx/core/config.py` avec `pydantic-settings`, validation stricte des champs obligatoires (`SECRET_KEY`), parsing flexible de `CORS_ORIGINS`, et singleton mis en cache via `@lru_cache`.
- Implémentation du `JSONFormatter` dans `backend/src/iryx/core/logging.py` avec masquage récursif des secrets (`***REDACTED***`) et timestamps ISO 8601 UTC conformes à D-23 et règle 13.
- Implémentation de la hiérarchie d'exceptions (`IryxException`, `ValidationException`, `NotFoundException`, `ForbiddenException`, `UnauthorizedException`) et des gestionnaires d'erreurs normalisés (`{"error": {"code": ..., "message": ...}}`) garantissant l'absence de fuite de stack trace (HTTP 422, HTTP 500).
- Implémentation de l'application FastAPI `create_app()` dans `backend/src/iryx/main.py` avec middleware CORS, route `/health` (HTTP 200 `{"status": "ok", "version": "0.1.0"}`) et gestionnaire de cycle de vie `lifespan`.
- Suite complète de 17 tests unitaires dans `backend/tests/unit/` (`test_health.py`, `test_config.py`, `test_logging.py`, `test_exceptions.py`) validant 100% des critères d'acceptation et cas limites.

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Evidence | Route |
|---------|---------|----------|-------|
| StarletteDeprecationWarning sur constantes HTTP_422 / HTTP_413 | low | Starlette 0.40+ déprécie `HTTP_422_UNPROCESSABLE_ENTITY` et `HTTP_413_REQUEST_ENTITY_TOO_LARGE`. Remplacement par constantes RFC 9110 (`HTTP_422_STATUS = getattr(status, 'HTTP_422_UNPROCESSABLE_CONTENT', 422)`). | patch (appliqué) |
| Fallback CORS `["*"]` silencieux dans `create_app` si configuration absente | low | En production, `lifespan` bloque au démarrage ; un avertissement et fallback documenté ont été validés. | patch (appliqué) |
| Normalisation des origines CORS (trailing slash) | low | Les origines avec slash terminal comme `http://localhost:3000/` échouaient en preflight. Normalisation via `.rstrip("/")` ajoutée. | patch (appliqué) |
| Manque de test unitaire pour la sérialisation JSON des exceptions (`record.exc_info`) | low | `JSONFormatter.format` gère `exc_info` mais aucun test ne vérifiait la présence de la clé `exception`. Test `test_json_formatter_exception_info` ajouté. | patch (appliqué) |
| Masquage des secrets dans les messages bruts non-dictionnaires | false | Les logs applicatifs ne doivent pas concaténer de secrets en clair (Règle 13). Masquer aveuglément les sous-chaînes communes comme "key" dans les messages texte dégraderait les logs. | rejeté |
| Absence de détails de validation dans le retour HTTP 422 | false | Conforme à la règle 6 des conventions backend et aux ACs imposant le schéma d'erreur standardisé `{"error": {"code": "VALIDATION_ERROR", "message": "Données de requête invalides."}}`. | rejeté |
| Gestion des `BaseException` dans `unhandled_exception_handler` | false | Starlette gère nativement `CancelledError` et `ClientDisconnect` en amont. Intercepter `Exception` est le standard recommandé. | rejeté |
| Initialisation du logging différée au lifespan | false | Recommandé par FastAPI pour un cycle de vie asynchrone propre au démarrage du serveur ASGI. | rejeté |
| Précision de la recommandation pour `SECRET_KEY` dans `.env.example` | low | Ajout de la commande recommandée `openssl rand -hex 32` dans les commentaires du fichier template. | patch (appliqué) |
| Chemins pythonpath redondants dans `pyproject.toml` | false | Assure la résolution transparente des imports que pytest soit lancé depuis la racine ou depuis `backend/`. | rejeté |

## Design Notes

- **Configuration:** La classe `Settings` hérite de `BaseSettings` avec `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`. Une fonction `get_settings()` avec `@lru_cache` permet l'injection dans FastAPI.
- **Logging:** Utilisation de `logging.Formatter` surchargeant `format(record)`. Extraction des métadonnées `timestamp` (ISO 8601 UTC), `level`, `logger`, `message`, et intégration d'un dictionnaire `context`. Les clés telles que `password`, `secret`, `token`, `key`, `authorization` ont leurs valeurs remplacées par `***REDACTED***`.
- **Gestion des exceptions:** Enregistrement d'un gestionnaire pour `RequestValidationError` (HTTP 422 standardisé) et d'un gestionnaire global pour `Exception` (HTTP 500 standardisé).

## Verification

**Commands:**
- `uv run ruff check backend/` -- expected: `All checks passed!`
- `uv run pytest backend/tests` -- expected: `All tests passed`
- `uv run python -c "from iryx.main import app; print(app.title)"` -- expected: `IRYX API`
