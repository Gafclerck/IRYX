---
title: 'Story 1.3 : Modèle utilisateur User, hachage sécurisé argon2 et migration initiale'
type: 'feature'
created: '2026-11-23'
status: 'done'
baseline_commit: '99fc108b77e7b67f7eb5729e0ee482cb241a5358'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/docs/03-modele-de-donnees.md'
  - '{project-root}/docs/04-securite-et-gates.md'
  - '{project-root}/docs/05-conventions-backend.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La plateforme IRYX ne dispose pas encore de modèle d'utilisateur ni de mécanisme de persistance des comptes et de hachage sécurisé des mots de passe. Il est impératif d'établir une modélisation `User` conforme aux conventions de données, avec un algorithme de hachage de référence (argon2id) et une migration Alembic traçable, sans fuite de mots de passe ni faille d'unicité.

**Approach:** Définir le modèle ORM SQLAlchemy 2.x `User` avec clé primaire UUID et table `users`, implémenter le module de sécurité cryptographique `core/security.py` pour le hachage et la vérification des mots de passe avec `pwdlib[argon2]`, fournir les schémas Pydantic v2 de validation (`UserCreate` imposant >= 12 caractères et `UserResponse` protégeant le mot de passe), concevoir le service de gestion d'utilisateurs convertissant les conflits d'unicité en `UserAlreadyExistsException` (HTTP 409), et générer la migration Alembic réversible `001_create_user_table`.

## Boundaries & Constraints

**Always:**
- Utiliser strictement l'algorithme `argon2id` via `pwdlib[argon2]` (D-13) pour tout hachage de mot de passe, avec vérification du préfixe `$argon2id$`.
- Respecter les conventions de nommage des colonnes et types de `docs/03-modele-de-donnees.md` : `id` (UUIDv4), `email` (String unique et indexé), `hashed_password` (String), `is_active` (Boolean, défaut True), `created_at` (DateTime UTC), `updated_at` (DateTime UTC).
- Ne jamais inclure `hashed_password` dans les schémas de réponse exposés (`UserResponse`).
- Valider la contrainte de complexité minimale du mot de passe dans le schéma Pydantic `UserCreate` (au moins 12 caractères) et renvoyer une erreur de validation HTTP 422 en cas de non-respect.
- Intercepter les violations de contrainte d'unicité sur l'email dans le service utilisateur et lever l'exception métier standardisée `UserAlreadyExistsException` (HTTP 409, code `USER_ALREADY_EXISTS`).
- Générer et versionner la migration via Alembic dans `backend/migrations/versions/` avec méthodes `upgrade()` et `downgrade()` symétriques et testées.
- Maintenir une conformité stricte avec `ruff` (0 avertissement, 0 erreur) et exécuter la suite de tests avec 100% de succès.

**Never:**
- Aucun mot de passe en clair persisté en base de données ou consigné dans les logs applicatifs.
- Aucun contournement des migrations par `Base.metadata.create_all()` en production (règle 9 de docs/05).
- Aucun modèle ORM retourné directement par une route ou un schéma de sortie (règle 3 de docs/05).
- Pas d'exposition de trace de pile (stack trace) ou d'information interne sur les erreurs d'unicité ou de validation.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Hachage valide de mot de passe | Mot de passe en clair (>= 12 caractères) | Chaîne de hachage débutant par `$argon2id$` valide vérifiable par `verify_password` | N/A |
| Vérification de mot de passe erroné | Mot de passe incorrect vs hash existant | `verify_password` retourne `False` sans lever d'exception | N/A |
| Validation schéma UserCreate (mot de passe court) | Mot de passe < 12 caractères | Rejet par Pydantic avec code HTTP 422 standardisé | `VALIDATION_ERROR` standardisé |
| Création d'utilisateur nominale | `UserCreate` avec email unique et mot de passe valide | Utilisateur persisté en base avec UUIDv4, `is_active=True`, timestamps UTC et mot de passe haché | Rollback en cas d'erreur de transaction |
| Email déjà existant (doublon) | Tentative de création avec un email déjà présent en base | Levée de `UserAlreadyExistsException` (HTTP 409, `USER_ALREADY_EXISTS`) | Interception `IntegrityError` et levée d'exception contrôlée |
| Exécution migration Alembic | `uv run alembic upgrade head` puis `downgrade -1` | Table `users` créée puis supprimée proprement sans incohérence de schéma | Rejet de la transaction Alembic en cas d'échec SQL |

</frozen-after-approval>

## Code Map

- `backend/pyproject.toml` -- Ajout des dépendances de production `pwdlib[argon2]>=0.2.0` et `email-validator>=2.2.0`
- `backend/src/iryx/core/security.py` -- Module centralisé de cryptographie : instance `PasswordHash.recommended()` (argon2id), fonctions `hash_password(password: str) -> str` et `verify_password(plain_password: str, hashed_password: str) -> bool`
- `backend/src/iryx/core/exceptions.py` -- Définition de `ConflictException` (HTTP 409) et `UserAlreadyExistsException` (code `USER_ALREADY_EXISTS`, HTTP 409)
- `backend/src/iryx/auth/__init__.py` -- Package du domaine métier d'authentification et gestion des identités
- `backend/src/iryx/auth/models.py` -- Modèle ORM `User` héritant de `Base` (`__tablename__ = "users"`), avec champs `id`, `email`, `hashed_password`, `is_active`, `created_at`, `updated_at`
- `backend/src/iryx/auth/schemas.py` -- Schémas Pydantic v2 `UserCreate` (email valide, mot de passe min 12 caractères) et `UserResponse` (`id`, `email`, `is_active`, `created_at`, `updated_at`, `from_attributes = True`)
- `backend/src/iryx/auth/services.py` -- Service métier `UserService` / fonctions de création d'utilisateur, vérification d'existence, hachage automatique et conversion des erreurs d'unicité en `UserAlreadyExistsException`
- `backend/migrations/versions/001_create_user_table.py` -- Script de migration Alembic initial créant la table `users` avec index unique sur `email`, clé primaire UUID et contraintes PostgreSQL
- `backend/tests/unit/test_security.py` -- Tests unitaires du hachage argon2id, vérification de mot de passe et rejet des faux mots de passe
- `backend/tests/unit/test_user_model.py` -- Tests unitaires du modèle `User`, de la validation des schémas Pydantic (mot de passe < 12 car -> 422) et exclusion du champ `hashed_password` dans `UserResponse`
- `backend/tests/unit/test_user_service.py` -- Tests unitaires du service de persistance et de détection de doublons d'email (`UserAlreadyExistsException`)
- `backend/tests/unit/test_user_migration.py` -- Tests d'intégrité de la migration Alembic `001_create_user_table` (upgrade/downgrade offline et vérification du schéma)

## Tasks & Acceptance

**Execution:**
- [x] `backend/pyproject.toml` -- Ajouter les dépendances `pwdlib[argon2]>=0.2.0` et `email-validator>=2.2.0`, puis exécuter `uv sync` -- Intégrer les composants cryptographiques et de validation d'email requis par D-13 et D-04
- [x] `backend/src/iryx/core/security.py` -- Implémenter les utilitaires de hachage et de vérification des mots de passe avec `pwdlib[argon2]` -- Assurer le hachage sécurisé argon2id sans secrets en clair
- [x] `backend/src/iryx/core/exceptions.py` -- Ajouter `ConflictException` (HTTP 409) et `UserAlreadyExistsException` (code `USER_ALREADY_EXISTS`) -- Permettre la notification standardisée des conflits d'unicité
- [x] `backend/src/iryx/auth/__init__.py` -- Créer le package métier `auth` -- Structurer le module conformément à la règle 1 de `docs/05`
- [x] `backend/src/iryx/auth/models.py` -- Implémenter le modèle ORM SQLAlchemy `User` lié à `Base` -- Persister les utilisateurs conformément aux spécifications de `docs/03`
- [x] `backend/src/iryx/auth/schemas.py` -- Implémenter les schémas Pydantic `UserCreate` (min_length=12) et `UserResponse` (sans hashed_password) -- Garantir l'étanchéité des données et la validation des entrées
- [x] `backend/src/iryx/auth/services.py` -- Développer la logique métier de création d'utilisateurs avec gestion de l'unicité et transaction sécurisée -- Encapsuler la logique métier hors des contrôleurs
- [x] `backend/migrations/versions/001_create_user_table.py` -- Créer la migration Alembic réversible pour la table `users` -- Respecter la règle 9 d'évolution du schéma par Alembic exclusivement
- [x] `backend/tests/unit/test_security.py` -- Écrire les tests unitaires de hachage et vérification argon2id -- Valider la conformité cryptographique NFR-SEC-04
- [x] `backend/tests/unit/test_user_model.py` -- Écrire les tests unitaires de modélisation et validation Pydantic -- Valider les contraintes de champs et le rejet des mots de passe courts
- [x] `backend/tests/unit/test_user_service.py` -- Écrire les tests unitaires du service de persistance et de détection de doublons d'email -- Valider le comportement métier et la levée de `UserAlreadyExistsException`
- [x] `backend/tests/unit/test_user_migration.py` -- Écrire les tests de migration Alembic offline -- Vérifier la validité de l'upgrade et du downgrade de la table `users`

**Acceptance Criteria:**
- Given la bibliothèque `pwdlib[argon2]` configurée, when la fonction `hash_password` est invoquée avec un mot de passe en clair, then la chaîne produite débute impérativement par `$argon2id$` et `verify_password` confirme sa validité.
- Given le modèle ORM `User` et la migration Alembic `001_create_user_table`, when la migration est exécutée, then la table `users` est créée avec une clé primaire `id` de type UUID, un champ `email` unique et indexé, un champ `hashed_password` non nul, `is_active` booléen avec valeur par défaut `True`, et les horodatages UTC `created_at` et `updated_at`.
- Given une tentative de création d'utilisateur avec une adresse email déjà enregistrée dans la base de données, when l'opération est traitée par le service utilisateur, then la contrainte d'unicité SQL est interceptée et l'exception `UserAlreadyExistsException` (HTTP 409, code `USER_ALREADY_EXISTS`) est levée.
- Given une charge utile d'enregistrement soumise avec un mot de passe de moins de 12 caractères, when le schéma Pydantic `UserCreate` valide les données, then une erreur de validation HTTP 422 (`VALIDATION_ERROR`) est déclenchée sans stocker ni exposer de mot de passe.
- Given une instance `User` enregistrée en base, when elle est sérialisée via le schéma `UserResponse`, then aucun champ sensible ou mot de passe haché (`hashed_password`) n'est présent dans le dictionnaire ou payload de sortie.
- Given la suite de tests automatisés et l'analyse statique du code, when `uv run ruff check backend/` et `uv run pytest backend/tests` sont exécutés, then 0 avertissement et 0 erreur ne sont relevés et 100% des tests réussissent.

## Implementation Notes

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Evidence | Route |
|---|---|---|---|
| Absence de borne max_length sur le mot de passe dans `UserCreate` (risque DoS CPU/RAM sur Argon2) | medium | `password: str = Field(..., min_length=12)` n'impose pas de longueur maximale. Un attaquant peut soumettre de très longues chaînes provoquant un épuisement mémoire/CPU lors du hachage Argon2id. | patch |
| Absence de limite max_length=255 et de normalisation Pydantic sur `email` dans `UserCreate` | low | `email: EmailStr` sans max_length explicite aligné sur `String(255)`. L'ajout de `max_length=255` et d'un validator Pydantic normalisant en minuscules/strip renforce l'étanchéité. | patch |
| Interception trop large de `IntegrityError` dans `UserService.create_user` | medium | `except IntegrityError:` convertit toute erreur d'intégrité en `UserAlreadyExistsException` même si la cause n'est pas un doublon d'email. Restreindre à la présence d'un indicateur de doublon d'email. | patch |
| Absence de garde sur type dans `UserService.get_by_email` | low | `get_by_email` sans validation préalable de chaîne pourrait lever `AttributeError` sur `.lower().strip()` si une valeur non-string ou vide est transmise. | patch |
| Fragilité de `backend/migrations/env.py` si l'attribut connection est un `Engine` | low | `config.attributes.get("connection")` passe directement l'objet à `context.configure(connection=connectable)`. Si un `Engine` est fourni, gérer la connexion via context manager. | patch |
| Absence de `server_default` sur la colonne `id` UUID dans `001_create_user_table.py` | false | Choix architectural délibéré (docs/03 et D-05) : IRYX utilise des UUIDv4 générés côté client en Python via `uuid.uuid4()`. L'ajout de `gen_random_uuid()` romprait la compatibilité SQLite en test unitaire. | rejeté |
| Exécution systématique de `commit()` dans `UserService.create_user` | low | L'appel explicite à `self.db.commit()` est standard pour les opérations unitaires. Ajouter un paramètre optionnel `auto_commit: bool = True` pour supporter les transactions composites. | patch |
| Requête non optimale dans `UserService.get_by_id` | low | `self.db.scalars(select(User).where(User.id == user_id)).first()` n'exploite pas l'identity map de la session SQLAlchemy 2.0 contrairement à `self.db.get(User, user_id)`. | patch |
| Absence de `__repr__` explicite sur `User` masquant `hashed_password` | low | L'absence de `__repr__` personnalisé risque d'exposer le hash de mot de passe lors de représentations par défaut en console ou logs (Règle 13 de docs/05). | patch |
| Absence de fonction utilitaire `needs_rehash` dans `core/security.py` | low | `pwdlib` supporte la détection de re-hachage nécessaire (`password_hash.needs_rehash(hashed)`), utile pour les montées de version d'algorithme. | patch |
| Absence de contexte structuré JSON dans le logger de `UserService` | low | L'appel à `logger.warning` ne transmet pas `extra={"context": {"email": normalized_email}}` selon la convention IRYX JSONFormatter. | patch |
| Absence de méthodes métier `authenticate`, `update_password`, `list_users` dans `UserService` | false | Hors périmètre Story 1.3 : l'authentification et l'émission JWT sont spécifiquement l'objet de la Story 1.4, et la gestion avancée des utilisateurs relève des stories ultérieures. | rejeté |
| Redondance déclarative de `unique=True` et `index=True` sur `User.email` | false | Définition conforme aux critères d'acceptation de la story 1.3 ("un champ email unique et indexé") et à la convention SQLAlchemy Declarative. | rejeté |
| Absence de garde contre les chaînes vides dans `hash_password` | low | Si appelée hors Pydantic, la fonction `hash_password` accepte une chaîne vide. Une garde `if not password:` évite le hachage d'entrées vides. | patch |
| Absence de test unitaire pour l'interception de `IntegrityError` lors d'un commit concurrent | medium | `test_create_user_duplicate_email_raises_user_already_exists` s'arrête au check proactif `get_by_email`. Aucun test ne valide le bloc `except IntegrityError:` en cas de commit concurrent avec rollback. | patch |
| Absence de vérification des timestamps et de sérialisation `UserResponse` sur un `User` persisté | medium | Les assertions dans `test_create_user_nominal` ne testent pas `user.created_at`, `user.updated_at` ni `UserResponse.model_validate(user)` sur l'instance persistée et rafraîchie. | patch |
| Nécessité d'une instance PostgreSQL active pour `alembic check` | low | `alembic check` requiert une base en ligne pour comparer le schéma; les tests unitaires valident déjà l'historique et la structure en offline et in-memory. | rejeté |

## Design Notes

- **Hachage de mot de passe :** `PasswordHash.recommended()` de `pwdlib` utilise argon2id avec des paramètres par défaut adaptés aux exigences modernes de sécurité contre les attaques par GPU/ASIC.
- **Modèle ORM `User` :**
  ```python
  class User(Base):
      __tablename__ = "users"

      id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
      email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
      hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
      is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True), server_default=func.now(), nullable=False
      )
      updated_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
      )
  ```
- **Sécurité et étanchéité :** Séparation stricte entre `UserCreate` (qui reçoit le mot de passe en clair pour validation et hachage immédiat) et `UserResponse` (qui ne contient que les métadonnées publiques de l'utilisateur).

## Verification

**Commands:**
- `uv run ruff check backend/` -- expected: `All checks passed!`
- `uv run pytest backend/tests` -- expected: `All tests passed`
- `uv run alembic -c backend/alembic.ini check` -- expected: vérification de conformité de l'historique Alembic
