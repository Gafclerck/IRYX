---
title: 'Story 2.3 : Modèle Case, migration Alembic et gestion du cycle de vie des dossiers (FR3)'
type: 'feature'
created: '2026-11-23'
status: 'done'
baseline_commit: 'bdc120846f5cad12a5979de6dec2e2387bd11a23'
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

**Problem:** La plateforme IRYX ne dispose pas encore de modèle relationnel ni d'API pour créer et administrer les dossiers d'investigation (`Case`). Les enquêteurs et analystes ne peuvent pas délimiter le périmètre d'un incident au sein de leur organisation, ni piloter son avancement opérationnel à travers les différents statuts de cycle de vie.

**Approach:** Implémenter le modèle SQLAlchemy `Case` avec énumération `CaseStatus` (`open`, `in_progress`, `review`, `closed`), la migration Alembic `003_create_case_table`, les schémas Pydantic v2, le service `CaseService` régissant les transitions d'états strictes (`InvalidStatusTransitionException`), les endpoints REST de création, consultation paginée et mise à jour de statut, ainsi que les contrôles RBAC excluant le rôle `viewer` des opérations de mutation.

## Boundaries & Constraints

**Always:**
- Utiliser des identifiants UUID v4 pour la clé primaire `Case.id` et des horodatages UTC (`DateTime(timezone=True)`) pour `created_at` et `updated_at`.
- Établir les clés étrangères avec intégrité référentielle : `organization_id` avec suppression en cascade (`ondelete="CASCADE"`) et `created_by` avec conservation (`ondelete="SET NULL"`, `nullable=True`).
- Appliquer une contrainte d'intégrité SQL `CheckConstraint` garantissant que `status` appartient strictement à `('open', 'in_progress', 'review', 'closed')`.
- Initialiser tout nouveau dossier au statut `open` avec `created_by` lié à l'utilisateur authentifié.
- Valider strictement les transitions d'états : `open` -> `in_progress`, `closed` ; `in_progress` -> `review`, `open`, `closed` ; `review` -> `closed`, `in_progress`.
- Rejeter toute transition depuis l'état terminal `closed` ou toute transition non permise en HTTP 400 Bad Request avec le code `INVALID_STATUS_TRANSITION`.
- Restreindre la création de dossier et la modification de statut aux membres actifs ayant un rôle opérationnel (`admin`, `investigator`, `analyst`) ; rejeter le rôle `viewer` en HTTP 403 Forbidden (`INSUFFICIENT_PERMISSIONS`).
- Permettre la consultation des dossiers (détail unitaire et liste paginée) à tout membre actif de l'organisation détentrice (y compris `viewer`).
- Appliquer une pagination systématique (`limit` entre 1 et 100, `offset` >= 0) avec retour standardisé (`items`, `total`, `limit`, `offset`, `has_more`).
- Valider les données d'entrée via Pydantic : `title` non vide de longueur maximale 255 caractères (rejet HTTP 422 `VALIDATION_ERROR`).

**Never:**
- Jamais de transition de statut autorisée depuis l'état `closed` sans procédure explicite de réouverture.
- Jamais d'exposition directe des modèles ORM SQLAlchemy dans les réponses de l'API REST.
- Jamais d'accès trans-organisation (Zero Leak) : rejeter en HTTP 403 / 404 tout accès par un utilisateur non membre de l'organisation cible.
- Jamais d'appel direct à `Base.metadata.create_all()` pour les migrations en base de données.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Création nominale dossier | `POST /api/v1/organizations/{org_id}/cases` avec `{"title": "Compromission AD", "description": "Activité anormale"}` par membre `admin`/`investigator`/`analyst` | HTTP 201 Created avec `CaseOut` (`id`, `organization_id`, `title`, `description`, `status="open"`, `created_by`, horodatages UTC) | N/A |
| Création par viewer | `POST /api/v1/organizations/{org_id}/cases` par un membre ayant le rôle `viewer` | HTTP 403 Forbidden | Code `INSUFFICIENT_PERMISSIONS` |
| Création par non-membre | `POST /api/v1/organizations/{org_id}/cases` par un utilisateur non membre | HTTP 403 Forbidden | Code `INSUFFICIENT_PERMISSIONS` |
| Création titre invalide | `POST /api/v1/organizations/{org_id}/cases` avec titre vide ou excédant 255 caractères | HTTP 422 Unprocessable Content | Code `VALIDATION_ERROR` |
| Organisation inconnue | `POST /api/v1/organizations/{org_id}/cases` avec `org_id` inexistant | HTTP 404 Not Found | Code `ORGANIZATION_NOT_FOUND` |
| Liste paginée des dossiers | `GET /api/v1/organizations/{org_id}/cases?limit=10&offset=0` par membre actif | HTTP 200 OK avec `CaseListResponse` (`items`, `total`, `limit`, `offset`, `has_more`) | N/A |
| Consultation dossier par ID | `GET /api/v1/cases/{case_id}` par membre de l'organisation du dossier | HTTP 200 OK avec `CaseOut` | N/A |
| Consultation dossier inexistant | `GET /api/v1/cases/{case_id}` avec `case_id` inconnu | HTTP 404 Not Found | Code `CASE_NOT_FOUND` |
| Consultation par non-membre | `GET /api/v1/cases/{case_id}` par membre d'une autre organisation | HTTP 403 Forbidden | Code `INSUFFICIENT_PERMISSIONS` |
| Transition nominale open -> in_progress | `PATCH /api/v1/cases/{case_id}/status` avec `{"status": "in_progress"}` par membre autorisé | HTTP 200 OK avec `CaseOut` ayant `status="in_progress"` | N/A |
| Transition nominale in_progress -> review | `PATCH /api/v1/cases/{case_id}/status` avec `{"status": "review"}` par membre autorisé | HTTP 200 OK avec `CaseOut` ayant `status="review"` | N/A |
| Transition nominale review -> closed | `PATCH /api/v1/cases/{case_id}/status` avec `{"status": "closed"}` par membre autorisé | HTTP 200 OK avec `CaseOut` ayant `status="closed"` | N/A |
| Transition illégale depuis closed | `PATCH /api/v1/cases/{case_id}/status` avec `{"status": "in_progress"}` sur dossier `closed` | HTTP 400 Bad Request | Code `INVALID_STATUS_TRANSITION` |
| Transition de statut par viewer | `PATCH /api/v1/cases/{case_id}/status` par un membre ayant le rôle `viewer` | HTTP 403 Forbidden | Code `INSUFFICIENT_PERMISSIONS` |

</frozen-after-approval>

## Code Map

- `backend/src/iryx/core/exceptions.py` -- Déclaration de `CaseNotFoundException` (HTTP 404, `CASE_NOT_FOUND`) et `InvalidStatusTransitionException` (HTTP 400, `INVALID_STATUS_TRANSITION`).
- `backend/src/iryx/cases/__init__.py` -- Package du domaine dossiers d'investigation.
- `backend/src/iryx/cases/models.py` -- Énumération `CaseStatus` (StrEnum) et modèle SQLAlchemy `Case` avec index, contraintes et relations (`organization`, `creator`).
- `backend/src/iryx/auth/models.py` -- Relation bidirectionnelle `cases` rattachée sur `Organization` (`cascade="all, delete-orphan", passive_deletes=True`).
- `backend/src/iryx/cases/schemas.py` -- Schémas Pydantic v2 `CaseCreate`, `CaseStatusUpdate`, `CaseOut`, `CaseListResponse`.
- `backend/src/iryx/cases/services.py` -- Logique métier `CaseService` : création, consultation, validation des transitions d'états et pagination.
- `backend/src/iryx/cases/router.py` -- Routes REST FastAPI `/api/v1/organizations/{org_id}/cases` et `/api/v1/cases/{case_id}` avec gardes de permissions RBAC.
- `backend/src/iryx/main.py` -- Enregistrement de `cases_router` dans l'application principale FastAPI.
- `backend/migrations/versions/003_create_case_table.py` -- Migration Alembic créant la table `cases` avec contraintes et index.
- `backend/tests/unit/test_case_models.py` -- Tests unitaires du modèle et des énumérations.
- `backend/tests/unit/test_case_service.py` -- Tests unitaires du service et de la matrice de transition d'états.
- `backend/tests/unit/test_case_migration.py` -- Validation de la migration Alembic réversible 003.
- `backend/tests/integration/test_cases_api.py` -- Tests d'intégration API complets couvrant création, consultation, transitions, permissions RBAC et erreurs HTTP.

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/core/exceptions.py` -- Ajouter `CaseNotFoundException` et `InvalidStatusTransitionException` -- Erreurs HTTP standardisées.
- [x] `backend/src/iryx/cases/models.py` -- Définir `CaseStatus` et le modèle SQLAlchemy `Case` -- Persistance relationnelle sous PostgreSQL 16.
- [x] `backend/src/iryx/auth/models.py` -- Ajouter la relation `cases` sur `Organization` -- Navigation ORM et cascade de suppression.
- [x] `backend/migrations/versions/003_create_case_table.py` -- Créer la migration réversible Alembic 003 pour la table `cases` -- Gestion versionnée du schéma SQL.
- [x] `backend/src/iryx/cases/schemas.py` -- Définir les schémas Pydantic `CaseCreate`, `CaseStatusUpdate`, `CaseOut`, `CaseListResponse` -- Contrats de données et validation d'entrée.
- [x] `backend/src/iryx/cases/services.py` -- Implémenter `CaseService` avec logique de cycle de vie et pagination -- Encapsulation des règles métier.
- [x] `backend/src/iryx/cases/router.py` -- Implémenter le routeur FastAPI avec les endpoints `/cases` et gardes de permissions -- Exposition REST conforme.
- [x] `backend/src/iryx/main.py` -- Enregistrer le routeur dans l'application principale -- Activation des routes API.
- [x] `backend/tests/unit/test_case_models.py` -- Écrire les tests unitaires du modèle `Case` -- Vérification des invariants ORM.
- [x] `backend/tests/unit/test_case_service.py` -- Écrire les tests unitaires du service et des transitions interdites -- Robustesse du cycle de vie.
- [x] `backend/tests/unit/test_case_migration.py` -- Tester l'application et le rollback de la migration 003 -- Intégrité de la base de données.
- [x] `backend/tests/integration/test_cases_api.py` -- Rédiger les tests d'intégration API complets -- Validation de bout en bout des critères d'acceptation.

**Acceptance Criteria:**
- Given la migration `003_create_case_table` appliquée et un utilisateur membre actif d'une organisation (`admin`, `investigator` ou `analyst`), when l'utilisateur soumet `POST /api/v1/organizations/{org_id}/cases` avec un titre valide et une description optionnelle, then le système crée le dossier avec le statut `open`, affecte `created_by` à l'utilisateur authentifié et renvoie HTTP 201 Created avec `CaseOut`.
- Given un dossier existant au statut `open`, when un utilisateur habilité soumet successivement `PATCH /api/v1/cases/{case_id}/status` avec `in_progress`, puis `review`, puis `closed`, then le statut évolue avec succès et le serveur renvoie HTTP 200 OK à chaque transition.
- Given un dossier au statut `closed`, when un utilisateur tente de modifier son statut vers `in_progress` ou tout autre statut, then le service lève `InvalidStatusTransitionException` et renvoie HTTP 400 Bad Request avec le code `INVALID_STATUS_TRANSITION`.
- Given un utilisateur ayant le rôle `viewer` dans l'organisation, when il tente d'exécuter `POST /api/v1/organizations/{org_id}/cases` ou `PATCH /api/v1/cases/{case_id}/status`, then le serveur renvoie HTTP 403 Forbidden avec le code `INSUFFICIENT_PERMISSIONS`.
- Given une organisation possédant des dossiers, when un membre effectue `GET /api/v1/organizations/{org_id}/cases`, then le serveur renvoie la collection paginée `CaseListResponse` avec métadonnées de pagination conformes.

## Implementation Notes

- Création du modèle SQLAlchemy `Case` et de l'énumération `CaseStatus` (`open`, `in_progress`, `review`, `closed`) dans `backend/src/iryx/cases/models.py`.
- Migration Alembic 003 réversible (`003_create_case_table.py`) avec index, contraintes de clés étrangères (`CASCADE` sur organisation, `SET NULL` sur créateur) et contrainte SQL `CheckConstraint`.
- Enregistrement de `iryx.cases.models` dans `backend/migrations/env.py`.
- Couche de validation Pydantic v2 `CaseCreate`, `CaseStatusUpdate`, `CaseOut` et `CaseListResponse` dans `backend/src/iryx/cases/schemas.py`.
- Implémentation du service de domaine `CaseService` dans `backend/src/iryx/cases/services.py` encapsulant la matrice des transitions autorisées (`VALID_STATUS_TRANSITIONS`), la pagination ordonnée et l'étanchéité multi-tenants Zero Leak.
- Déclaration des erreurs unifiées `CaseNotFoundException` (HTTP 404, `CASE_NOT_FOUND`) et `InvalidStatusTransitionException` (HTTP 400, `INVALID_STATUS_TRANSITION`) dans `backend/src/iryx/core/exceptions.py`.
- Exposition des routes REST dans `backend/src/iryx/cases/router.py` et rattachement dans `backend/src/iryx/main.py`.
- Suite complète de tests unitaires et d'intégration couvrant la totalité des scénarios de la matrice I/O (44 nouveaux tests, 218 tests réussis au total, Ruff validé).

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Evidence | Route |
|---|---|---|---|
| ECH1 / BH3: Absence de verrouillage ligne sur update_case_status | medium | L'absence de with_for_update() expose à des concurrences sur la transition depuis le statut terminal closed. | patch |
| ECH2: Absence de garde sur limit/offset négatifs dans list_cases | low | list_cases dans la couche service n'effectue pas de validation directe si appelé hors FastAPI. | patch |
| BH1: Nom de CheckConstraint avec double préfixe | low | POSTGRES_NAMING_CONVENTION préfixe déjà ck_%(table_name)s; purement cosmétique sur le nom de contrainte. | rejected |
| BH2: Discrépance 404/403 sur get_case_by_id | false | La matrice I/O et les critères d'acceptation approuvés spécifient explicitement 404 pour ID inconnu et 403 pour non-membre. | rejected |
| BH4: Absence d'index composite (org_id, created_at DESC) | low | L'index simple ix_cases_organization_id est suffisant pour le périmètre MVP. | rejected |
| BH5: Index status et created_by non utilisés par filtres | false | Ces index anticipent les exigences fonctionnelles des prochains récits (E3, E5). | rejected |
| BH6: Absence d'endpoint d'édition titre/description | false | Hors périmètre strict de la Story 2.3 (FR3 : création, listing, cycle de vie des statuts). | rejected |
| BH7: Absence de suppression ou d'archivage de dossier | false | Hors périmètre et contraire à l'immutabilité d'audit d'IRYX. | rejected |
| BH8: Contrôle d'accès dans le service plutôt qu'en dépendance de route | false | La dépendance de sécurité verify_case_access fait l'objet exclusif de la Story 2.4 dédiée. | rejected |
| BH9: Absence de traçabilité fine closed_by / closed_at | false | Le modèle Case est strictement aligné sur docs/03; l'audit complet relève d'AuditEvent (Epic 8). | rejected |
| BH10 / VG4: Surcharge non idiomatique de __init__ dans CaseListResponse | low | L'alignement total_items = total peut être géré de manière idiomatique sans surcharger __init__. | patch |
| BH11: Absence de borne maximale sur description | low | Une limite défensive sur description évite l'envoi de charges utiles démesurées. | patch |
| BH12: Absence de procédure de réouverture de dossier | false | L'invariant stipule que closed est terminal sans réouverture; l'absence de réouverture en Story 2.3 est conforme. | rejected |
| BH13: Relation bidirectionnelle absente sur le modèle User | low | Case.creator résout la relation; l'absence sur User n'a aucun impact opérationnel. | rejected |
| BH14: Absence de vérification d'existence d'organisation dans list_cases | false | La dépendance verify_org_membership vérifie déjà l'existence de l'organisation en amont. | rejected |
| BH15: Utilisation de littéraux bruts au lieu de constantes MembershipRole | low | Préférer MembershipRole.ADMIN.value etc. sécurise le typage. | patch |
| BH16: Absence de test API sur les transitions arrières autorisées | low | Les transitions in_progress -> open et review -> in_progress méritent d'être testées au niveau HTTP. | patch |
| BH17: Statut sprint-status.yaml vs spec | false | Conforme au déroulement nominal du workflow BMAD en cours de revue. | rejected |
| BH18: Contexte de log incomplet sur update_case_status | low | Ajouter old_status dans le contexte JSON enrichit la traçabilité sans complexité. | patch |
| VG1: Isolation multi-tenants non vérifiée dans les tests de listing | medium | Pre-verified gap: test_list_cases_nominal_and_pagination ne crée pas de cas dans other_org pour vérifier l'exclusion. | patch |
| VG2: Ordre de tri non vérifié dans les assertions de test de listing | medium | Pre-verified gap: les tests de pagination ne vérifient pas que le tri renvoie les dossiers les plus récents en premier. | patch |
| VG3: other_org non exploitée dans test_cases_api.py | low | Rattaché à VG1 : utiliser other_org pour prouver l'isolation étanche. | patch |

## Design Notes

- **Matrice des transitions d'état autorisées :**
  ```python
  VALID_STATUS_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
      CaseStatus.OPEN: {CaseStatus.IN_PROGRESS, CaseStatus.CLOSED},
      CaseStatus.IN_PROGRESS: {CaseStatus.REVIEW, CaseStatus.OPEN, CaseStatus.CLOSED},
      CaseStatus.REVIEW: {CaseStatus.CLOSED, CaseStatus.IN_PROGRESS},
      CaseStatus.CLOSED: set(),
  }
  ```
- **Résolution des accès pour `/api/v1/cases/{case_id}` :**
  Pour les routes directes sur un dossier (`GET /api/v1/cases/{case_id}` et `PATCH /api/v1/cases/{case_id}/status`), le service récupère le dossier, vérifie l'existence (`CaseNotFoundException` si absent) et valide l'appartenance de `current_user` à l'organisation détentrice via sa table `memberships`. Pour les modifications de statut, le rôle du membre doit être distinct de `viewer`.

## Verification

**Commands:**
- `uv run ruff check backend/` -- expected: `All checks passed!`
- `uv run pytest backend/tests` -- expected: `All tests passed`
