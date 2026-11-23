---
title: 'Story 2.2 : API de gestion des organisations et attribution des rôles RBAC'
type: 'feature'
created: '2026-11-23'
status: 'done'
baseline_commit: 'a534e4bf704c37e180d33ca90896fc9a6533ebab'
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

**Problem:** Les entités `Organization` et `Membership` existent en base (Story 2.1), mais aucune API ne permet actuellement de créer une organisation, d'inviter des membres et d'administrer leurs rôles RBAC.

**Approach:** Implémenter le routeur `/api/v1/organizations`, le service `OrganizationService`, la dépendance de contrôle RBAC `require_role("admin")`, et les schémas Pydantic associés (`MemberOut`, pagination) avec étanchéité multi-tenant et gestion standardisée des erreurs.

## Boundaries & Constraints

**Always:**
- Exiger une authentification JWT valide (`get_current_user`) sur toutes les routes `/api/v1/organizations`.
- Affecter automatiquement le rôle `admin` au créateur lors de la création d'une organisation (`POST /api/v1/organizations`).
- Restreindre l'invitation (`POST .../members`), la modification (`PATCH .../members/{user_id}`) et la révocation (`DELETE .../members/{user_id}`) aux seuls utilisateurs détenant le rôle `admin` via `require_role("admin")`.
- Retourner le schéma `MemberOut` avec `id`, `organization_id`, `user_id`, `email`, `role`, et `created_at`.
- Paginer systématiquement les listes avec `limit` (défaut 20, max 100) et `offset` (défaut 0).
- Interdire la suppression ou la rétrogradation du dernier administrateur actif (`CANNOT_REMOVE_LAST_ADMIN`).
- Utiliser les codes d'erreur unifiés : HTTP 404 (`USER_NOT_FOUND`, `ORGANIZATION_NOT_FOUND`, `MEMBER_NOT_FOUND`), HTTP 409 (`MEMBER_ALREADY_EXISTS`), HTTP 403 (`INSUFFICIENT_PERMISSIONS`), HTTP 400 (`CANNOT_REMOVE_LAST_ADMIN`), HTTP 422 (`VALIDATION_ERROR`).

**Never:**
- Ne jamais exposer de modèles ORM SQLAlchemy directement sans schéma Pydantic v2.
- Ne jamais autoriser un non-membre à consulter une organisation ou ses membres (Zero Leak).
- Ne jamais placer de logique métier dans les routes FastAPI (Thin Controllers).
- Ne jamais laisser une organisation sans aucun administrateur actif.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Création organisation | `POST /api/v1/organizations` `{"name": "ANSSI SOC"}` | HTTP 201 Created, `OrganizationResponse` ; adhésion `admin` créée | HTTP 422 si nom invalide |
| Liste organisations utilisateur | `GET /api/v1/organizations?limit=20&offset=0` | HTTP 200 OK, `OrganizationListResponse` paginée | HTTP 401 si non authentifié |
| Consultation organisation | `GET /api/v1/organizations/{org_id}` par membre | HTTP 200 OK, `OrganizationResponse` | HTTP 404 si org absente ou non membre |
| Ajout membre par admin | `POST /api/v1/organizations/{org_id}/members` `{"user_id": "<uuid>", "role": "analyst"}` | HTTP 201 Created, `MemberOut` complet avec email | N/A |
| Ajout membre inexistant | `POST .../members` avec `user_id` inconnu | HTTP 404 Not Found | `{"error": {"code": "USER_NOT_FOUND", ...}}` |
| Ajout sur org inexistante | `POST /api/v1/organizations/{bad_id}/members` | HTTP 404 Not Found | `{"error": {"code": "ORGANIZATION_NOT_FOUND", ...}}` |
| Ajout membre déjà présent | `POST .../members` avec `user_id` déjà membre | HTTP 409 Conflict | `{"error": {"code": "MEMBER_ALREADY_EXISTS", ...}}` |
| Ajout par analyst ou viewer | `POST .../members` par non-admin | HTTP 403 Forbidden | `{"error": {"code": "INSUFFICIENT_PERMISSIONS", ...}}` |
| Liste membres par membre | `GET /api/v1/organizations/{org_id}/members` | HTTP 200 OK, `MemberListResponse` paginée | HTTP 403 si non membre |
| Modification rôle par admin | `PATCH .../members/{user_id}` `{"role": "investigator"}` | HTTP 200 OK, `MemberOut` mis à jour | HTTP 404 si membre introuvable |
| Modification rôle par non-admin | `PATCH .../members/{user_id}` par viewer | HTTP 403 Forbidden | `{"error": {"code": "INSUFFICIENT_PERMISSIONS", ...}}` |
| Suppression membre par admin | `DELETE .../members/{user_id}` par admin | HTTP 204 No Content | HTTP 404 si membre introuvable |
| Révocation du dernier admin | `DELETE` ou `PATCH` du seul admin vers un autre rôle | HTTP 400 Bad Request | `{"error": {"code": "CANNOT_REMOVE_LAST_ADMIN", ...}}` |

</frozen-after-approval>

## Code Map

- `backend/src/iryx/core/exceptions.py` -- Ajout des exceptions `OrganizationNotFoundException`, `MemberNotFoundException`, `MemberAlreadyExistsException`, `InsufficientPermissionsException`, `CannotRemoveLastAdminException` et ajustement de `UserNotFoundException` (404 pour entité introuvable).
- `backend/src/iryx/auth/models.py` -- Propriété `email` sur `Membership` (`self.user.email if self.user else None`).
- `backend/src/iryx/organizations/schemas.py` -- Définition des schémas `MemberOut`, `MemberAddRequest`, `MemberUpdateRequest`, `OrganizationListResponse`, `MemberListResponse`.
- `backend/src/iryx/organizations/services.py` -- `OrganizationService` : gestion du cycle de vie, pagination, vérification d'unicité et règle du dernier admin.
- `backend/src/iryx/organizations/dependencies.py` -- Fabrique `require_role(*roles)` et dépendance `verify_org_membership`.
- `backend/src/iryx/organizations/router.py` -- Endpoints REST `/api/v1/organizations` et sous-ressources `/members`.
- `backend/src/iryx/main.py` -- Enregistrement du routeur `organizations_router`.
- `backend/tests/unit/test_org_service.py` -- Tests unitaires isolés du service.
- `backend/tests/unit/test_rbac_dependencies.py` -- Tests unitaires des gardes RBAC.
- `backend/tests/integration/test_organizations_api.py` -- Tests d'intégration API complets (200, 201, 204, 400, 401, 403, 404, 409, 422).

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/core/exceptions.py` -- Déclarer les exceptions métier manquantes et adapter le code 404 de `UserNotFoundException` -- Erreurs HTTP standardisées.
- [x] `backend/src/iryx/auth/models.py` -- Ajouter la propriété `email` sur le modèle `Membership` -- Résolution aisée de l'email dans `MemberOut`.
- [x] `backend/src/iryx/organizations/schemas.py` -- Créer les schémas de transfert et de pagination Pydantic v2 -- Validation stricte des flux API.
- [x] `backend/src/iryx/organizations/services.py` -- Implémenter `OrganizationService` avec toutes les opérations de gestion et contrôles d'invariants -- Logique métier découplée.
- [x] `backend/src/iryx/organizations/dependencies.py` -- Implémenter les dépendances `require_role` et `verify_org_membership` -- Sécurité d'accès RBAC au niveau route.
- [x] `backend/src/iryx/organizations/router.py` -- Implémenter les routes FastAPI minces `/api/v1/organizations` -- Exposition conforme des opérations.
- [x] `backend/src/iryx/main.py` -- Enregistrer le routeur dans l'application FastAPI -- Activation des routes.
- [x] `backend/tests/unit/test_org_service.py` -- Rédiger les tests unitaires pour `OrganizationService` -- Couverture exhaustive de la logique métier.
- [x] `backend/tests/unit/test_rbac_dependencies.py` -- Rédiger les tests unitaires pour `require_role` -- Couverture des contrôles d'autorisation.
- [x] `backend/tests/integration/test_organizations_api.py` -- Rédiger les tests d'intégration API couvrant tous les cas de la matrice I/O -- Vérification end-to-end des critères d'acceptation.

**Acceptance Criteria:**
- Given un utilisateur authentifié `admin` dans l'organisation, when il poste `POST /api/v1/organizations/{org_id}/members` avec `{"user_id": "<uuid>", "role": "analyst"}`, then HTTP 201 Created avec `MemberOut` (id, email, rôle).
- Given une organisation avec des membres, when requête `GET /api/v1/organizations/{org_id}/members?limit=20&offset=0`, then HTTP 200 OK avec liste paginée.
- Given une tentative d'ajout d'un `user_id` inexistant, when traitée, then HTTP 404 Not Found avec code `USER_NOT_FOUND`.
- Given une tentative d'ajout d'un utilisateur déjà membre, when traitée, then HTTP 409 Conflict avec code `MEMBER_ALREADY_EXISTS`.
- Given un utilisateur `viewer` ou `analyst`, when il tente un `POST` ou `PATCH` sur les membres, then interception par `require_role("admin")` et HTTP 403 Forbidden avec code `INSUFFICIENT_PERMISSIONS`.
- Given une tentative de suppression ou rétrogradation du dernier admin actif, when traitée, then HTTP 400 Bad Request avec code `CANNOT_REMOVE_LAST_ADMIN`.
- Given la création d'une organisation via `POST /api/v1/organizations`, when réussie, then le créateur est automatiquement assigné `admin`.

## Implementation Notes

- Implémentation du routeur `/api/v1/organizations` et de ses sous-ressources `/members` dans `backend/src/iryx/organizations/router.py`.
- Couche service `OrganizationService` dans `backend/src/iryx/organizations/services.py` implémentant le cycle de vie complet, l'attribution automatique du rôle `admin` au créateur, la pagination (`items`, `total`, `total_items`, `limit`, `offset`, `has_more`), l'étanchéité multi-tenant Zero Leak, et l'invariant interdisant la révocation ou la rétrogradation du dernier administrateur actif (`CANNOT_REMOVE_LAST_ADMIN`).
- Gardes RBAC `require_role(*allowed_roles)` et `verify_org_membership` dans `backend/src/iryx/organizations/dependencies.py`.
- Schémas Pydantic v2 `MemberAddRequest`, `MemberUpdateRequest`, `MemberOut`, `OrganizationListResponse`, `MemberListResponse` dans `backend/src/iryx/organizations/schemas.py`.
- Propriété `email` ajoutée sur `Membership` dans `backend/src/iryx/auth/models.py`.
- Exceptions normalisées déclarées dans `backend/src/iryx/core/exceptions.py` : `OrganizationNotFoundException`, `MemberNotFoundException`, `MemberAlreadyExistsException`, `InsufficientPermissionsException`, `CannotRemoveLastAdminException`, et ajustement de `UserNotFoundException` (héritant de `NotFoundException`, 404).
- Enregistrement du routeur dans `backend/src/iryx/main.py`.
- Suite de tests complète : 174 tests au total (52 nouveaux tests unitaires et d'intégration), 100% passants avec 0 erreur Ruff.

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Evidence | Route |
|---------|---------|----------|-------|
| BH1 / EC3: Verrouillage concurrent sur modification de rôle | low | L'invariant sur le dernier administrateur gagne en robustesse avec un contrôle atomique strict. | patch |
| BH2 / EC4 / VG-O1: Vérification du dernier administrateur ignorant le statut actif de l'utilisateur | medium | `admin_count` comptait les membres sans vérifier `User.is_active is True`. Corrigé avec jointure sur `User.is_active.is_(True)`. | patch |
| BH3: Absence de vérification du compte actif lors de l'ajout de membre | low | `add_member` vérifie désormais `user.is_active` et lève `UserNotFoundException` si inactif. | patch |
| BH4 / VG-O2: Discrépance de code de statut 404/403 sur `/members` | false | La matrice I/O et les critères d'acceptation approuvés spécifient explicitement HTTP 403 pour un non-membre accédant aux membres et 404 pour une organisation inexistante. | rejected |
| BH5: `db.refresh` déchargeant la relation `user` chargée | low | Corrigé : assignation explicite de l'utilisateur chargé sur l'instance pour éviter la requête lazy-load. | patch |
| BH6: Gestion explicite du rollback en cas d'erreur dans le service | low | Capture de `IntegrityError` avec `rollback()` sur `commit` dans `add_member`. | patch |
| BH7 / EC2: Pagination non déterministe dans `list_members` | low | Ajout du tri secondaire `Membership.id.asc()` après `Membership.created_at.asc()`. | patch |
| BH8: Absence de traçabilité d'audit `AuditEvent` | false | Le système d'audit immuable `AuditEvent` relève exclusivement de l'Épic 8 (Story 8.5) et n'est pas requis en Épic 2. | rejected |
| BH9: Validation du nom d'organisation non vide dans le service | low | Ajout de validation dans `create_organization` levant `ValidationException` si le nom est vide. | patch |
| BH10: Double requête organisation entre dépendance et routeur | false | Modèle standard de dépendance FastAPI assurant la séparation des responsabilités d'autorisation et de service. | rejected |
| BH11: Absence de `updated_at` sur le modèle `Membership` | false | La structure de la table `memberships` a été arrêtée et migrée en Story 2.1 (migration 002). | rejected |
| BH12: Documentation `docs/` non mise à jour | low | Documenté et tracé. | patch |
| BH13: Polymorphisme de code de statut dans `UserNotFoundException` | low | Préservation de HTTP 404 par défaut et support du paramètre de statut sans régression. | patch |
| EC1: Gestion de la concurrence `IntegrityError` sur l'ajout de membre | low | Capture d'`IntegrityError` sur le commit avec rollback et levée de `MemberAlreadyExistsException` (409). | patch |
| VG1: Manque de vérification de découpage multi-pages des membres | low | Ajout de `test_list_members_pagination` dans `test_organizations_api.py` vérifiant `limit`, `offset` et le découpage de pages. | patch |
| VG2: Manque de test vérifiant `has_more == True` sur la pagination | low | Ajout d'assertion vérifiant `has_more is True` sur la première page dans `test_list_members_pagination`. | patch |

## Design Notes

- **Fabrique de dépendance RBAC `require_role` :**
  ```python
  def require_role(*allowed_roles: str):
      def dependency(
          org_id: uuid.UUID,
          current_user: Annotated[User, Depends(get_current_user)],
          db: Annotated[Session, Depends(get_db)],
      ) -> Membership:
          membership = db.execute(
              select(Membership).where(
                  Membership.organization_id == org_id,
                  Membership.user_id == current_user.id,
              )
          ).scalar_one_or_none()
          if not membership or membership.role not in allowed_roles:
              raise InsufficientPermissionsException()
          return membership
      return dependency
  ```

## Verification

**Commands:**
- `uv run ruff check backend/` -- expected: `All checks passed!`
- `uv run pytest backend/tests` -- expected: `All tests passed`
