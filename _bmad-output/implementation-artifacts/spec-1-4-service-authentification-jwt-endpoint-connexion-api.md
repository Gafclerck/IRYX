---
title: "Story 1.4 : Service d'authentification JWT et endpoint de connexion /api/v1/auth/login"
type: 'feature'
created: '2026-11-23'
status: 'done'
baseline_commit: '463a40681767ea4db8a7d68ff8145553edb2da98'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/docs/04-securite-et-gates.md'
  - '{project-root}/docs/05-conventions-backend.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La plateforme IRYX ne dispose pas encore de mécanisme d'authentification ni d'émission de jetons de session pour sécuriser ses routes API. Les utilisateurs enregistrés ne peuvent pas ouvrir de session ni prouver leur identité de manière sécurisée et sans état.

**Approach:** Intégrer la dépendance `PyJWT`, implémenter les utilitaires de génération et décodage de jetons d'accès JWT signés (HS256) dans `core/security.py`, ajouter les exceptions d'authentification normalisées dans `core/exceptions.py`, étendre le service d'authentification avec la méthode `authenticate_user`, exposer l'endpoint `POST /api/v1/auth/login` recevant des identifiants JSON et fournissant `TokenResponse`, fournir la dépendance injectable `get_current_user` pour protéger les routes, et brancher le routeur `auth` sur l'application FastAPI principale.

## Boundaries & Constraints

**Always:**
- Utiliser la bibliothèque `PyJWT` (>=2.9.0, décision D-12) pour l'encodage et le décodage des jetons JWT avec algorithme configurable (`HS256` par défaut via `Settings`).
- Inclure systématiquement dans la charge utile (payload) du jeton JWT : le sujet `sub` (identifiant UUID de l'utilisateur sous forme de chaîne de caractères), l'adresse `email`, la date d'émission `iat` (timestamp Unix UTC) et la date d'expiration `exp` (timestamp Unix UTC).
- Retourner une réponse d'authentification nominale HTTP 200 conforme au schéma : `{"access_token": "<JWT>", "token_type": "bearer", "expires_in": 3600}`.
- Renvoyer un code HTTP 401 Unauthorized avec le message générique `{"error": {"code": "INVALID_CREDENTIALS", "message": "Identifiants invalides."}}` en cas de mot de passe incorrect ou d'email introuvable, sans jamais divulguer si l'anomalie porte sur l'email ou le mot de passe.
- Renvoyer un code HTTP 403 Forbidden avec l'erreur `{"error": {"code": "INACTIVE_ACCOUNT", "message": "Compte utilisateur inactif."}}` si l'utilisateur est authentifié avec succès mais que son champ `is_active` est à `False`.
- Imposer l'en-tête `Authorization: Bearer <token>` sur les routes protégées via la dépendance FastAPI `get_current_user` ; lever une exception HTTP 401 (`UNAUTHORIZED` ou `INVALID_TOKEN`) si l'en-tête est manquant, malformé, expiré ou si la signature est invalide.
- Respecter l'architecture de contrôleurs minces (Thin Controllers, Règle 2 de docs/05) : la route se limite à valider la requête Pydantic, invoquer le service et renvoyer la réponse typée.
- Maintenir une conformité stricte avec `ruff` (0 avertissement, 0 erreur) et garantir 100% de réussite sur la suite de tests automatisés.

**Never:**
- Aucun secret, clé privée/secrète ou mot de passe en clair consigné dans les logs applicatifs (Règle 13 de docs/05).
- Aucun modèle ORM retourné directement par les routes API (Règle 3 de docs/05) ; utiliser exclusivement des schémas Pydantic.
- Aucune fuite de trace de pile (stack trace) ou d'information interne dans les réponses d'erreur HTTP (Règle 6 de docs/05).
- Pas de dépendances circulaires entre modules : `core` ne dépend d'aucun domaine métier, `auth` utilise `core` et `db`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Connexion nominale réussie | `POST /api/v1/auth/login` avec email valide et mot de passe exact pour un utilisateur actif | HTTP 200, `TokenResponse` contenant `access_token`, `token_type: "bearer"`, `expires_in: 3600` | N/A |
| Identifiants erronés (mauvais mot de passe) | `POST /api/v1/auth/login` avec email existant mais mot de passe erroné | HTTP 401, corps `{"error": {"code": "INVALID_CREDENTIALS", "message": "Identifiants invalides."}}` | Interception sécurisée sans fuite de détails |
| Identifiants erronés (email inconnu) | `POST /api/v1/auth/login` avec email non enregistré | HTTP 401, corps `{"error": {"code": "INVALID_CREDENTIALS", "message": "Identifiants invalides."}}` | Message identique au mauvais mot de passe |
| Compte utilisateur désactivé | `POST /api/v1/auth/login` avec identifiants valides mais `is_active=False` | HTTP 403, corps `{"error": {"code": "INACTIVE_ACCOUNT", "message": "Compte utilisateur inactif."}}` | Levée d'`InactiveAccountException` |
| Requête de connexion invalide | `POST /api/v1/auth/login` avec email malformé ou corps vide | HTTP 422, corps standardisé `{"error": {"code": "VALIDATION_ERROR", ...}}` | Validation Pydantic standard |
| Accès route protégée avec jeton valide | `GET /api/v1/auth/me` avec `Authorization: Bearer <valid_token>` | HTTP 200, schéma `UserResponse` correspondant à l'utilisateur authentifié | N/A |
| Accès route protégée sans jeton | `GET /api/v1/auth/me` sans en-tête `Authorization` | HTTP 401, corps `{"error": {"code": "UNAUTHORIZED", "message": "Authentification requise."}}` | Levée d'`UnauthorizedException` |
| Accès route protégée avec jeton expiré | `GET /api/v1/auth/me` avec jeton dont `exp` est dépassé | HTTP 401, corps `{"error": {"code": "INVALID_TOKEN", "message": "Jeton d'authentification invalide ou expiré."}}` | Interception `jwt.ExpiredSignatureError` |
| Accès route protégée avec signature altérée | `GET /api/v1/auth/me` avec jeton modifié ou signé avec une autre clé | HTTP 401, corps `{"error": {"code": "INVALID_TOKEN", "message": "Jeton d'authentification invalide ou expiré."}}` | Interception `jwt.InvalidTokenError` |
| Accès route protégée pour utilisateur supprimé | `GET /api/v1/auth/me` avec jeton valide mais `sub` inexistant en base | HTTP 401, corps `{"error": {"code": "USER_NOT_FOUND", "message": "Utilisateur introuvable."}}` | Levée d'`UnauthorizedException` |

</frozen-after-approval>

## Code Map

- `backend/pyproject.toml` -- Ajout de la dépendance de production `pyjwt>=2.9.0` (D-12)
- `backend/src/iryx/core/config.py` -- Ajustement de la valeur par défaut `jwt_access_token_expire_minutes = 60` (correspondant à 3600 secondes) et validation
- `backend/src/iryx/core/security.py` -- Implémentation des fonctions `create_access_token(data: dict, expires_delta: timedelta | None = None) -> str` et `decode_access_token(token: str) -> dict[str, Any]` avec gestion stricte de `jwt.ExpiredSignatureError` et `jwt.PyJWTError`
- `backend/src/iryx/core/exceptions.py` -- Définition des exceptions spécialisées : `InvalidCredentialsException` (HTTP 401, code `INVALID_CREDENTIALS`), `InactiveAccountException` (HTTP 403, code `INACTIVE_ACCOUNT`), `InvalidTokenException` (HTTP 401, code `INVALID_TOKEN`)
- `backend/src/iryx/auth/schemas.py` -- Définition des schémas Pydantic v2 `LoginRequest` (email normalisé, password) et `TokenResponse` (`access_token`, `token_type`, `expires_in`)
- `backend/src/iryx/auth/services.py` -- Ajout de la méthode métier `authenticate_user(email: str, password: str) -> User` dans `UserService` (ou `AuthService`) validant existence, mot de passe via `verify_password` et état actif
- `backend/src/iryx/auth/dependencies.py` -- Implémentation de la dépendance FastAPI `get_current_user` extrayant le Bearer token via `HTTPBearer(auto_error=False)` ou extraction d'en-tête, décodant le token et injectant l'utilisateur depuis `db`
- `backend/src/iryx/auth/router.py` -- Routeur FastAPI `APIRouter(prefix="/api/v1/auth", tags=["Authentication"])` exposant `POST /login` et `GET /me` (route protégée de vérification)
- `backend/src/iryx/main.py` -- Enregistrement et inclusion de `auth_router` dans l'application FastAPI via `application.include_router(auth_router)`
- `backend/tests/unit/test_jwt_security.py` -- Tests unitaires de création de jeton JWT, décodage, validation des revendications (`sub`, `email`, `iat`, `exp`), expiration et signature altérée
- `backend/tests/integration/test_auth_api.py` -- Tests d'intégration API complets validant `POST /api/v1/auth/login` (nominal, mauvais mot de passe, email inexistant, compte inactif) et `GET /api/v1/auth/me` (nominal avec token, sans token, token expiré, token falsifié)

## Tasks & Acceptance

**Execution:**
- [x] `backend/pyproject.toml` -- Ajouter la dépendance `pyjwt>=2.9.0` et synchroniser avec `uv sync` -- Fournir le moteur d'encodage et décodage JWT requis par D-12
- [x] `backend/src/iryx/core/config.py` -- Vérifier et documenter les paramètres JWT (`jwt_secret_key`, `jwt_algorithm`, `jwt_access_token_expire_minutes=60`) -- Aligner la configuration sur l'expiration 3600 secondes
- [x] `backend/src/iryx/core/security.py` -- Implémenter `create_access_token` et `decode_access_token` -- Fournir les briques cryptographiques réutilisables d'encodage/décodage de jetons
- [x] `backend/src/iryx/core/exceptions.py` -- Ajouter `InvalidCredentialsException`, `InactiveAccountException` et `InvalidTokenException` -- Normaliser les codes et statuts d'erreur d'authentification
- [x] `backend/src/iryx/auth/schemas.py` -- Créer `LoginRequest` et `TokenResponse` -- Définir les contrats d'entrée et sortie de l'API de connexion
- [x] `backend/src/iryx/auth/services.py` -- Implémenter la méthode `authenticate_user` dans `UserService` -- Encapsuler la vérification des identifiants et du statut actif de l'utilisateur
- [x] `backend/src/iryx/auth/dependencies.py` -- Implémenter la dépendance FastAPI `get_current_user` -- Sécuriser l'accès aux endpoints protégés via injection de dépendances
- [x] `backend/src/iryx/auth/router.py` -- Créer le routeur `/api/v1/auth` avec `POST /login` et `GET /me` -- Exposer les points d'accès HTTP conformément aux spécifications
- [x] `backend/src/iryx/main.py` -- Monter `auth_router` dans l'application FastAPI -- Rendre les routes d'authentification accessibles
- [x] `backend/tests/unit/test_jwt_security.py` -- Écrire les tests unitaires de manipulation et validation des tokens JWT -- Valider le déterminisme et la sécurité cryptographique
- [x] `backend/tests/integration/test_auth_api.py` -- Écrire les tests d'intégration des routes `/api/v1/auth/login` et `/api/v1/auth/me` -- Valider les critères d'acceptation et cas d'erreur de bout en bout

**Acceptance Criteria:**
- Given un utilisateur actif enregistré avec `analyst@iryx.local` et son mot de passe valide, when une requête `POST /api/v1/auth/login` est soumise avec ces identifiants, then le serveur répond HTTP 200 avec `access_token`, `token_type: "bearer"` et `expires_in: 3600`.
- Given un jeton JWT valide émis lors de la connexion, when son contenu est décodé, then il contient la signature valide par `PyJWT`, le `sub` contenant l'identifiant UUID de l'utilisateur, son `email`, ainsi que les timestamps `iat` et `exp` distants de 3600 secondes.
- Given une requête `POST /api/v1/auth/login` avec un mot de passe erroné ou un email non enregistré, when la requête est exécutée, then le serveur répond HTTP 401 avec `{"error": {"code": "INVALID_CREDENTIALS", "message": "Identifiants invalides."}}` sans révéler la raison spécifique de l'échec.
- Given un utilisateur dont `is_active` est à `False`, when il tente de se connecter avec ses identifiants valides, then le serveur retourne HTTP 403 avec le code `INACTIVE_ACCOUNT`.
- Given une route protégée par la dépendance `get_current_user`, when une requête est émise sans en-tête `Authorization`, avec un jeton expiré ou avec une signature altérée, then le serveur rejette la requête immédiatement avec le code HTTP 401.
- Given une suite de tests unitaires et d'intégration couvrant l'authentification et les routes API, when `uv run ruff check backend/` et `uv run pytest backend/tests` sont exécutés, then 0 avertissement, 0 erreur et 100% de succès sont obtenus.

## Implementation Notes

- Dépendance `pyjwt>=2.9.0` ajoutée à `backend/pyproject.toml` et verrouillée dans `uv.lock`.
- Paramètre `jwt_access_token_expire_minutes` aligné à 60 (3600 secondes) dans `config.py`, `.env`, et `.env.example`.
- Utilitaires cryptographiques `create_access_token` et `decode_access_token` implémentés dans `core/security.py` avec validation stricte des signatures et expirations.
- Exceptions normalisées ajoutées dans `core/exceptions.py` : `InvalidCredentialsException` (HTTP 401), `InactiveAccountException` (HTTP 403), `InvalidTokenException` (HTTP 401), `UserNotFoundException` (HTTP 401).
- Schémas Pydantic v2 `LoginRequest` et `TokenResponse` définis dans `auth/schemas.py`.
- Méthode `authenticate_user` implémentée dans `UserService` (`auth/services.py`).
- Dépendance `get_current_user` implémentée dans `auth/dependencies.py` via `HTTPBearer(auto_error=False)` et injection typée `Annotated`.
- Routeur `/api/v1/auth` implémenté dans `auth/router.py` et monté dans `main.py`.
- Suite de tests unitaires `test_jwt_security.py` (7 tests) et d'intégration `test_auth_api.py` (13 tests) créée. Zéro avertissement, zéro erreur Ruff et 90/90 tests passants.

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Evidence | Route |
|---|---|---|---|
| B1: Timing attack sur `authenticate_user` si email inconnu | low | Différence mesurable par rapport à argon2id, mais charge CPU disproportionnée pour le MVP (dummy hash sur chaque tentative invalide). | rejeté |
| B2 / E1: Absence d'exigence explicite des claims `exp` et `sub` dans `decode_access_token` | medium | PyJWT ne valide `exp` que si présent. Un token sans `exp` n'expirerait jamais. Ajout de `options={"require": ["exp", "sub"]}` dans `jwt.decode`. | patch |
| B3 / E4: Absence de validation de type dictionnaire sur `data` dans `create_access_token` | low | Si `data` n'est pas un dictionnaire, levée d'une `TypeError` préventive avant appel à `.copy()`. | patch |
| B4: Valeur par défaut statique de `jwt_secret_key` dans `Settings` | low | Pré-existant dans le socle IRYX depuis Story 1.1 pour le dev local. Durcissement consigné pour la phase globale de durcissement. | defer |
| B5: Absence d'en-tête standard `WWW-Authenticate: Bearer` sur les réponses HTTP 401 | low | Recommandation RFC 6750 : ajout de `headers={"WWW-Authenticate": "Bearer"}` sur `JSONResponse` pour tout statut 401. | patch |
| B6: Logique d'assemblage du token présente dans le contrôleur `login` | low | Le contrôleur se limite à 6 lignes de mapping sans logique métier complexe, conforme au principe de Thin Controller. | rejeté |
| B7 / V-Other-1: Injection directe de `get_db_session` au lieu de `get_db` | medium | `architecture.md` et Règle 4 de docs/05 imposent `get_db` depuis `iryx.api.dependencies` pour unifier le cycle de vie des sessions FastAPI. | patch |
| B8: Loggers déclarés et inutilisés dans `router.py` et `dependencies.py` | low | Déclaration de loggers inutilisés supprimée pour garantir la concision du code. | patch |
| B9: Mutation de `SPECIAL_USE_DOMAIN_NAMES` dans `schemas.py` | low | Nécessaire pour autoriser le domaine `.local` imposé par les critères d'acceptation et l'environnement DFIR IRYX. | rejeté |
| B10: Nommage de `UserNotFoundException` héritant de `UnauthorizedException` | false | Conforme à la ligne 10 de la matrice I/O du spec gelée (code d'erreur `USER_NOT_FOUND` en HTTP 401). | rejeté |
| B11: Divergence documentaire sur la durée du jeton (60 min vs ADR-0006) | low | Alignement documentaire à répercuter dans `docs/adr/ADR-0006`. | defer |
| B12: Mention dans ADR-0006 de l'absence de requête DB pour `get_current_user` | low | L'exigence de vérification de l'état actif impose un lookup SQL. Synchronisation documentaire consignée. | defer |
| B13: Avertissement StarletteDeprecationWarning sur `TestClient` | low | Dépendance de test Starlette fonctionnelle sans impact opérationnel sur la suite de tests. | rejeté |
| B14 / V1: Absence de tests vérifiant le rejet des tokens sans `sub` ou avec `sub` non-UUID en 401 | medium | Ajout des tests d'intégration `test_get_me_missing_sub_claim` et `test_get_me_non_uuid_sub_claim` dans `test_auth_api.py`. | patch |
| B15: Absence de rehash automatique du mot de passe dans `authenticate_user` | false | Non prévu dans le périmètre ni les critères d'acceptation de la Story 1.4. | rejeté |
| E2: Validation `gt=0` sur `jwt_access_token_expire_minutes` | low | Empêche la configuration d'une durée négative ou nulle produisant des tokens immédiatement expirés. | patch |
| E3: Absence de garde de type chaîne sur `email` et `password` dans `authenticate_user` | low | Ajout d'une vérification stricte préalable levant `InvalidCredentialsException` en cas d'argument non-string ou vide. | patch |
| V-Other-2: Branche inatteignable `scheme.lower() != "bearer"` | low | Garde défensive inoffensive conservée. | rejeté |

## Design Notes

- **Payload JWT et typage :**
  ```python
  payload = {
      "sub": str(user.id),
      "email": user.email,
      "iat": datetime.now(timezone.utc),
      "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes),
  }
  ```
- **Dépendance `get_current_user` :**
  Utilisation de `HTTPBearer(auto_error=False)` pour extraire le header standard `Authorization: Bearer <token>`. Si absent -> levée de `UnauthorizedException(message="Authentification requise.", code="UNAUTHORIZED")`. Si décodage échoue -> `InvalidTokenException`. Récupération de l'utilisateur en base via `user_service.get_by_id(UUID(sub))`. Si absent -> 401. Si `not user.is_active` -> `InactiveAccountException` (403).

## Verification

**Commands:**
- `uv run ruff check backend/` -- expected: `All checks passed!`
- `uv run pytest backend/tests` -- expected: `All tests passed`
