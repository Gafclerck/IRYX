---
title: 'Story 2.4 : Dépendance de sécurité verify_case_access et isolation stricte par dossier (FR4, NFR-SEC-05)'
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_revision: '4fdd140975c2fa85dbf7d62d9b952666528f7a04'
baseline_commit: '4fdd140975c2fa85dbf7d62d9b952666528f7a04'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/docs/03-modele-de-donnees.md'
  - '{project-root}/docs/04-securite-et-gates.md'
  - '{project-root}/docs/05-conventions-backend.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** La plateforme IRYX ne dispose pas encore de la dépendance FastAPI `verify_case_access` pour valider l'appartenance de l'utilisateur à l'organisation détentrice d'un dossier au niveau route, ni d'un point d'accès unifié `GET /api/v1/cases` filtrant automatiquement les dossiers de toutes les organisations dont l'utilisateur est membre actif, créant un risque de fuite d'informations inter-organisations (Zero Leak) et limitant l'expérience utilisateur.

**Approach:** Implémenter la dépendance de sécurité `verify_case_access` et la dépendance de rôle `require_case_role` dans `backend/src/iryx/cases/dependencies.py`, enrichir `CaseService` avec la méthode `list_user_cases` effectuant une jointure sécurisée avec `Membership`, exposer la route `GET /api/v1/cases` avec pagination déterministe, et brancher la dépendance `verify_case_access` sur les routes de consultation unitaire dans `backend/src/iryx/cases/router.py`.

## Boundaries & Constraints

**Always:**
- Injecter systématiquement `verify_case_access` sur toute route manipulant un dossier existant (`/api/v1/cases/{case_id}`) ou ses sous-ressources.
- Renvoyer HTTP 404 Not Found avec le code `CASE_NOT_FOUND` si le dossier n'existe pas en base de données.
- Renvoyer HTTP 403 Forbidden avec le code `INSUFFICIENT_PERMISSIONS` sans aucune fuite de métadonnées ni d'existence du dossier si l'utilisateur authentifié n'est pas membre actif de l'organisation détentrice.
- La route `GET /api/v1/cases` doit obligatoirement filtrer les dossiers via une jointure SQL avec la table `memberships` sur `user_id == current_user.id` pour garantir l'isolation stricte multi-tenants.
- Appliquer un ordre de tri antéchronologique déterministe (`Case.created_at.desc(), Case.id.desc()`) et valider les paramètres de pagination (`limit` entre 1 et 100, `offset >= 0`).
- Conserver 100% de passage des 219 tests existants et respecter l'exigence zéro avertissement / zéro erreur Ruff.

**Never:**
- Jamais d'accès trans-organisation autorisé (principe Zero Leak absolu).
- Jamais de contournement de la vérification d'organisation au niveau de la route.
- Jamais d'exposition de champs internes ou modèles ORM sans passer par les schémas Pydantic v2 `CaseOut` et `CaseListResponse`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Consultation nominale dossier | `GET /api/v1/cases/{case_id}` par membre de l'org détentrice | HTTP 200 OK avec schéma `CaseOut` | N/A |
| Accès dossier inexistant | `GET /api/v1/cases/{fake_uuid}` par utilisateur authentifié | HTTP 404 Not Found avec code `CASE_NOT_FOUND` | `{"error": {"code": "CASE_NOT_FOUND", "message": "Le dossier demandé n'existe pas."}}` |
| Accès cross-tenant (Zero Leak) | `GET /api/v1/cases/{case_id_org_a}` par membre exclusif de l'org B | HTTP 403 Forbidden avec code `INSUFFICIENT_PERMISSIONS` | `{"error": {"code": "INSUFFICIENT_PERMISSIONS", "message": "Accès refusé à ce dossier."}}` |
| Listing global des dossiers | `GET /api/v1/cases?limit=20&offset=0` par membre des orgs A et B | HTTP 200 OK avec `CaseListResponse` contenant uniquement les dossiers de A et B | N/A |
| Listing global utilisateur sans org | `GET /api/v1/cases` par utilisateur sans aucune appartenance | HTTP 200 OK avec `items: []`, `total: 0`, `has_more: false` | N/A |
| Listing global pagination invalide | `GET /api/v1/cases?limit=0` ou `limit=101` ou `offset=-1` | HTTP 422 Unprocessable Content | Code `VALIDATION_ERROR` |

</intent-contract>

## Code Map

- `backend/src/iryx/cases/dependencies.py` -- Nouvelles dépendances FastAPI de sécurité `verify_case_access` et `require_case_role` validant l'affiliation et les rôles.
- `backend/src/iryx/cases/services.py` -- Ajout de `list_user_cases(user_id, limit, offset)` avec jointure SQL sécurisée sur `Membership`.
- `backend/src/iryx/cases/router.py` -- Branchement de `verify_case_access` sur `GET /api/v1/cases/{case_id}` et ajout du endpoint `GET /api/v1/cases`.
- `backend/src/iryx/cases/__init__.py` -- Export des dépendances publiques `verify_case_access` et `require_case_role`.
- `backend/tests/unit/test_case_dependencies.py` -- Tests unitaires isolés pour les dépendances `verify_case_access` et `require_case_role`.
- `backend/tests/unit/test_case_service.py` -- Tests unitaires de `list_user_cases` (isolation, multi-org, pagination, ordering).
- `backend/tests/integration/test_cases_api.py` -- Tests d'intégration API incluant `test_cross_tenant_isolation_fails` et le test de l'endpoint `GET /api/v1/cases`.

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/cases/dependencies.py` -- Créer le module de dépendances avec `verify_case_access` et `require_case_role` -- Contrôle d'accès au niveau route et Zero Leak (FR4, NFR-SEC-05).
- [x] `backend/src/iryx/cases/__init__.py` -- Exporter `verify_case_access` et `require_case_role` -- Interface publique du package cases.
- [x] `backend/src/iryx/cases/services.py` -- Implémenter `list_user_cases` dans `CaseService` -- Requête paginée filtrant par les organisations de l'utilisateur.
- [x] `backend/src/iryx/cases/router.py` -- Ajouter `GET /api/v1/cases` et utiliser `verify_case_access` dans `get_case` -- Exposition REST conforme et protection des routes.
- [x] `backend/tests/unit/test_case_dependencies.py` -- Rédiger les tests unitaires des dépendances de sécurité -- Validation unitaire des gardes d'accès.
- [x] `backend/tests/unit/test_case_service.py` -- Ajouter les tests unitaires de `list_user_cases` -- Couverture de la logique métier de listing multi-tenants.
- [x] `backend/tests/integration/test_cases_api.py` -- Ajouter `test_cross_tenant_isolation_fails` et les scénarios de test pour `GET /api/v1/cases` -- Validation de bout en bout des critères d'acceptation.

**Acceptance Criteria:**
- Given un utilisateur authentifié membre de l'organisation détentrice du dossier `case-alpha`, when il soumet une requête `GET /api/v1/cases/{case-alpha-id}`, then la dépendance `verify_case_access` valide son affiliation et renvoie les détails du dossier avec HTTP 200 OK.
- Given un utilisateur authentifié appartenant à une ou plusieurs organisations, when il soumet `GET /api/v1/cases?limit=20&offset=0`, then le serveur renvoie la collection paginée `CaseListResponse` restreinte exclusivement aux dossiers de ses organisations.
- Given un identifiant de dossier inexistant au format UUID valide, when une requête `GET /api/v1/cases/{fake_uuid}` est soumise, then le serveur répond HTTP 404 Not Found avec `CASE_NOT_FOUND`.
- Given un utilisateur authentifié appartenant exclusivement à l'organisation B, when il tente d'accéder au dossier `case-alpha` appartenant à l'organisation A, then la dépendance `verify_case_access` rejette l'accès et répond HTTP 403 Forbidden sans divulguer l'existence ou les métadonnées du dossier, et le test d'intégration `test_cross_tenant_isolation_fails` valide ce rejet.

## Implementation Notes

- Création du module `backend/src/iryx/cases/dependencies.py` implémentant les dépendances FastAPI de sécurité `verify_case_access` et `require_case_role` (Zero Leak multi-tenant, 404 CASE_NOT_FOUND si dossier inexistant, 403 INSUFFICIENT_PERMISSIONS sans fuite de métadonnées).
- Export de `verify_case_access` et `require_case_role` dans `backend/src/iryx/cases/__init__.py`.
- Ajout de la méthode `list_user_cases(user_id, limit, offset)` dans `CaseService` (`backend/src/iryx/cases/services.py`) avec jointure SQL sécurisée sur `Membership`, validation défensive de la pagination (1 <= limit <= 100, offset >= 0) et tri déterministe antéchronologique (`Case.created_at.desc(), Case.id.desc()`).
- Branchement de `verify_case_access` sur `GET /api/v1/cases/{case_id}` et `PATCH /api/v1/cases/{case_id}/status`, et exposition de la route globale `GET /api/v1/cases` dans `backend/src/iryx/cases/router.py`.
- Harmonisation du message de `CaseNotFoundException` dans `backend/src/iryx/core/exceptions.py` vers `"Le dossier demandé n'existe pas."`.
- Couverture complète par des tests unitaires (`backend/tests/unit/test_case_dependencies.py`, `backend/tests/unit/test_case_service.py`) et d'intégration (`backend/tests/integration/test_cases_api.py`), incluant le test d'étanchéité multi-tenants `test_cross_tenant_isolation_fails` (238 tests passants au total, 0 erreur/avertissement Ruff).

## Spec Change Log

## Review Triage Log

### 2026-11-24 — Review pass
- verdicts: 15 findings — high 0, medium 1, low 9, false 5, maybe-false 0
- findings:
  - `[false]` `[reject]` BH1: Case existence enumeration oracle in verify_case_access — Le contrat d'acceptation et la matrice I/O approuvés spécifient explicitement HTTP 404 pour ID inexistant et HTTP 403 pour défaut d'appartenance; aucune métadonnée n'est divulguée en 403 et les UUID v4 sont non devinables.
  - `[low]` `[patch]` BH2 / VG2: require_case_role non exploité dans les routeurs applicatifs — Action: Injecté require_case_role(MembershipRole.ADMIN, MembershipRole.INVESTIGATOR, MembershipRole.ANALYST) sur PATCH /api/v1/cases/{case_id}/status.
  - `[low]` `[reject]` BH3 / VG3: Double requête de verrouillage et vérification dans update_case_status — Double vérification défensive mineure lors d'une transition de statut, sans impact utilisateur ni complexité justifiable pour démanteler la sécurité en profondeur.
  - `[false]` `[reject]` BH4: get_case sérialise directement le Case issu de la dépendance — Conforme au principe Thin Controller; ré-interroger la couche service pour la même entité provoquerait une requête SQL inutile.
  - `[low]` `[patch]` BH5: Incohérence des bornes de validation limit entre list_cases et list_user_cases — Action: Ajout de la validation limit > 100 dans CaseService.list_cases.
  - `[false]` `[reject]` BH6: Absence de filtrage étendu par statut/recherche sur GET /api/v1/cases — Hors périmètre strict de la Story 2.4 (FR4 / NFR-SEC-05), prévu dans les récits ultérieurs (E7).
  - `[low]` `[patch]` BH7: Normalisation insensible à la casse des rôles dans require_case_role — Action: Ajout de .lower() sur toutes les chaînes et valeurs d'énumérations dans require_case_role.
  - `[false]` `[reject]` BH8: Message d'erreur spécifique dans verify_case_access — Le message "Accès refusé à ce dossier." est explicitement prescrit et vérifié par les critères d'acceptation.
  - `[low]` `[patch]` BH9: Référence obsolète à verify_case_membership dans la documentation — Action: Mise à jour de docs/04-securite-et-gates.md vers verify_case_access.
  - `[low]` `[reject]` BH10: Délais time.sleep dans les tests d'intégration — Délais courts (0.005s) déjà en place en Story 2.3 et stabilisés par un tri secondaire déterministe sur id DESC.
  - `[false]` `[reject]` BH11: Absence de test d'isolation sur les mutations cross-tenant — test_patch_case_status_by_outsider_forbidden existe déjà et valide le rejet HTTP 403 sur PATCH.
  - `[low]` `[patch]` BH12: require_case_role non testé au niveau FastAPI Depends — Action: Intégré sur PATCH /api/v1/cases/{case_id}/status et validé via test_patch_case_status_by_viewer_forbidden et test_patch_case_status_by_outsider_forbidden.
  - `[medium]` `[patch]` VG1: Absence de test de pagination multi-pages et has_more sur GET /api/v1/cases — Action: Ajout de test_list_user_cases_pagination_multi_page dans test_cases_api.py (vérifiant has_more True sur page 1, puis False sur page 2).

### 2026-11-24 — Review pass 2
- verdicts: 12 findings — high 0, medium 0, low 2, false 10, maybe-false 0
- findings:
  - `[false]` `[reject]` BH1: carried — Case existence enumeration oracle (404 vs 403) conforme au contrat I/O et entropie UUIDv4.
  - `[false]` `[reject]` BH2: require_case_role est bien injecté sur PATCH /api/v1/cases/{case_id}/status dans router.py.
  - `[false]` `[reject]` BH3: require_case_role sans argument validant l'adhésion est le comportement voulu et testé unitairement.
  - `[false]` `[reject]` BH4: Normalisation .lower() déjà en place pour les rôles passés en chaînes ou enums.
  - `[low]` `[reject]` BH5: carried — Double verrouillage défensif dans update_case_status.
  - `[false]` `[reject]` BH6: Pas de divergence fonctionnelle, requêtes ORM isolées et lisibles.
  - `[low]` `[patch]` BH7: carried — Validation limit > 100 dans list_cases déjà appliquée.
  - `[false]` `[reject]` BH8: Requête SQL déterministe sans anomalie fonctionnelle.
  - `[false]` `[reject]` BH9: carried — Message HTTP conforme à la matrice d'acceptation.
  - `[false]` `[reject]` BH10: carried — Filtrage additionnel hors périmètre Story 2.4.
  - `[false]` `[reject]` BH11: Schéma CaseOut conforme au modèle de données canonique.
  - `[low]` `[patch]` BH12: Ajout de test_list_user_cases_unauthenticated_returns_401 validant le rejet HTTP 401 en l'absence de JWT.

## Design Notes

- **Signature de `verify_case_access` :**
  ```python
  def verify_case_access(
      case_id: uuid.UUID,
      current_user: Annotated[User, Depends(get_current_user)],
      db: Annotated[Session, Depends(get_db)],
  ) -> Case:
      case = db.get(Case, case_id)
      if case is None:
          raise CaseNotFoundException()
      membership = db.scalar(
          select(Membership).where(
              Membership.organization_id == case.organization_id,
              Membership.user_id == current_user.id,
          )
      )
      if membership is None:
          raise InsufficientPermissionsException(message="Accès refusé à ce dossier.")
      return case
  ```
- **Requête multi-tenants dans `list_user_cases` :**
  ```python
  stmt = (
      select(Case)
      .join(Membership, Case.organization_id == Membership.organization_id)
      .where(Membership.user_id == user_id)
      .order_by(Case.created_at.desc(), Case.id.desc())
      .limit(limit)
      .offset(offset)
  )
  ```

## Verification

**Commands:**
- `uv run ruff check backend/` -- expected: `All checks passed!`
- `uv run pytest backend/tests` -- expected: `All tests passed`

## Auto Run Result

### Résumé des modifications implémentées
- Implémentation des dépendances de sécurité FastAPI `verify_case_access` et `require_case_role` dans `backend/src/iryx/cases/dependencies.py` assurant le respect strict du principe Zero Leak (rejet HTTP 403 sans divulgation de métadonnées pour les utilisateurs non membres, HTTP 404 pour les identifiants inexistants).
- Ajout de la méthode `list_user_cases` dans `CaseService` avec jointure `INNER JOIN Membership` garantissant l'étanchéité multi-tenants et pagination déterministe antéchronologique.
- Exposition du endpoint global `GET /api/v1/cases` permettant aux utilisateurs de consulter l'ensemble des dossiers de leurs organisations.
- Protection des routes `/api/v1/cases/{case_id}` via `verify_case_access` pour la consultation unitaire (`GET`) et `require_case_role` pour les transitions de statut opérationnelles (`PATCH`).
- Harmonisation du message de `CaseNotFoundException` vers `"Le dossier demandé n'existe pas."`.
- Mise à jour de la documentation d'architecture dans `docs/04-securite-et-gates.md`.

### Fichiers modifiés
- `backend/src/iryx/cases/dependencies.py` : Dépendances FastAPI `verify_case_access` et `require_case_role` avec normalisation des rôles.
- `backend/src/iryx/cases/__init__.py` : Export des dépendances de sécurité dans l'interface publique du package.
- `backend/src/iryx/cases/services.py` : Méthode `list_user_cases` et harmonisation de la borne de validation `limit <= 100` sur `list_cases`.
- `backend/src/iryx/cases/router.py` : Route `GET /api/v1/cases` et injection des dépendances de sécurité sur les routes de dossiers.
- `backend/src/iryx/core/exceptions.py` : Message par défaut normalisé de `CaseNotFoundException`.
- `docs/04-securite-et-gates.md` : Synchronisation de la référence à `verify_case_access`.
- `backend/tests/unit/test_case_dependencies.py` : 11 tests unitaires exhaustifs pour `verify_case_access` et `require_case_role`.
- `backend/tests/unit/test_case_service.py` : 5 tests unitaires pour `list_user_cases` et la validation des bornes de pagination.
- `backend/tests/integration/test_cases_api.py` : Tests d'intégration incluant `test_cross_tenant_isolation_fails`, listing global multi-orgs et pagination multi-pages.

### Bilan de la revue de code
- Correctifs appliqués (5) :
  - `VG1` (medium) : Test de pagination multi-pages (`has_more`) sur `GET /api/v1/cases`.
  - `BH2 / BH12 / VG2` (low) : Utilisation et test de `require_case_role` sur la route `PATCH /api/v1/cases/{case_id}/status`.
  - `BH5` (low) : Harmonisation de `limit <= 100` sur `CaseService.list_cases`.
  - `BH7` (low) : Normalisation `.lower()` des rôles dans `require_case_role`.
  - `BH9` (low) : Mise à jour de `docs/04-securite-et-gates.md`.
- Éléments rejetés (7) :
  - `BH1` (false) : Contrat d'acceptation et matrice I/O stipulant expressément 404 pour inexistant et 403 pour non-membre.
  - `BH3 / VG3` (low) : Double vérification défensive sans surcoût perceptible pour une transition de statut.
  - `BH4` (false) : Thin Controller pur sans logique métier, évitant une requête SQL redondante.
  - `BH6` (false) : Filtrage étendu hors périmètre Story 2.4.
  - `BH8` (false) : Message d'erreur spécifique prescrit par les critères d'acceptation.
  - `BH10` (low) : Délais courts en tests stabilisés par un tri déterministe sur `id DESC`.
  - `BH11` (false) : Test de mutation cross-tenant déjà présent dans la suite.
- Recommandation de revue de suivi : `false` (0 finding high, 1 medium patché sur première passe).

### Vérifications effectuées
- `uv run ruff check backend/` : Validé (All checks passed!, 0 erreur, 0 avertissement).
- `uv run pytest backend/tests` : 240 tests passés avec succès (0 échec).

### Risques résiduels
- Aucun risque résiduel identifié. L'étanchéité multi-tenants Zero Leak et le contrôle d'accès au niveau route sont rigoureusement vérifiés.
