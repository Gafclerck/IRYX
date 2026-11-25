---
title: "Story 6.1 : Modèle Finding, schémas Pydantic et migration Alembic"
type: 'feature'
created: '2026-11-25'
status: 'done'
baseline_commit: 'c8393a3732aa6dbb8a60ba225b3b28452101a816'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-6-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le système ne dispose pas encore de la structure relationnelle ni des contrats de données Pydantic nécessaires pour stocker, valider et manipuler les constats techniques d'investigation (`Finding`), préalables indispensables aux agents `Analyst`, `Verifier` et à la porte de contrôle humain H2.

**Approach:** Définir les énumérations métier et le modèle ORM SQLAlchemy `Finding` dans le module `analytics`, concevoir les schémas Pydantic v2 associés (`FindingCreate`, `FindingUpdate`, `FindingOut`, `FindingListResponse`), générer la migration Alembic `007_create_finding_table.py` compatible PostgreSQL et SQLite, exposer les routes d'API REST protégées par `verify_case_access`, et valider l'ensemble par des tests unitaires et d'intégration stricts.

## Boundaries & Constraints

**Always:**
- Respecter scrupuleusement les énumérations architecturales : sévérité (`low`, `medium`, `high`, `critical`), confiance (`low`, `medium`, `high`), type (`fact`, `inference`, `hypothesis`), statut (`proposed`, `validated`, `rejected`).
- Assurer la stricte isolation multi-tenant et la protection de chaque accès par la dépendance `verify_case_access`.
- Garantir la compatibilité double de la migration et du modèle pour PostgreSQL (via `postgresql.ARRAY(postgresql.UUID)`) et SQLite (via `TypeDecorator` JSON transparent pour la suite de tests).
- Conserver `status` initialement à `proposed` par défaut pour tout nouveau finding.
- Rejeter toute donnée non conforme avec une réponse HTTP 422 Standard FastAPI/Pydantic.

**Never:**
- Ne pas introduire d'appel LLM ou de logique d'inférence dans ce socle de données (Story 6.1 est strictement dédiée aux modèles, schémas, migrations et API de base).
- Ne jamais contourner `Base.metadata.create_all()` en code de production (interdiction absolue Rule 9).
- Ne pas autoriser la manipulation d'un finding appartenant à un autre dossier ou à une organisation non autorisée.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Création valide d'un finding | Payload `FindingCreate` valide avec `case_id` valide et utilisateur membre | `FindingOut` retourné avec code 201, UUID généré, statut `proposed`, horodatage UTC | Erreur 400 si incohérence |
| Sévérité ou type de finding invalide | Payload avec `severity: "extreme"` ou `finding_type: "guess"` | Rejet immédiat par validation Pydantic | HTTP 422 Unprocessable Entity avec détail du champ |
| Références d'observation et d'outils vides | Payload valide avec listes `observation_refs: []`, `tool_execution_refs: []` | Accepté en base avec listes vides par défaut | N/A |
| Accès dossier non autorisé | Utilisateur authentifié n'appartenant pas à l'organisation du dossier | Accès bloqué par `verify_case_access` | HTTP 403 Forbidden |
| Dossier inexistant | `case_id` inexistant lors d'une opération sur les findings | Opération interceptée | HTTP 404 Not Found |
| Migration Alembic 007 | Exécution `upgrade` vers `head` puis `downgrade` vers `006` | Tables et contraintes créées puis supprimées proprement | Échec immédiat si régression DDL |

</frozen-after-approval>

## Code Map

- `backend/src/iryx/analytics/models.py` -- Ajout du modèle ORM `Finding` avec colonnes `id`, `case_id`, `title`, `severity`, `confidence`, `finding_type`, `status`, `observation_refs`, `tool_execution_refs`, `created_by`, `created_at` et type decorator compatible SQLite/PostgreSQL.
- `backend/src/iryx/analytics/schemas.py` -- Création des schémas Pydantic v2 : `FindingBase`, `FindingCreate`, `FindingUpdate`, `FindingOut`, `FindingListResponse`, et enums associés.
- `backend/src/iryx/analytics/services.py` -- Logique de persistance et de requêtage pour les findings (`create_finding`, `get_finding`, `list_findings`, `update_finding`, `delete_finding`).
- `backend/src/iryx/analytics/router.py` -- Contrôleur FastAPI sous `/api/v1/cases/{case_id}/findings` sécurisé par `verify_case_access`.
- `backend/src/iryx/analytics/__init__.py` -- Export des modèles et composants publics du module analytics.
- `backend/src/iryx/cases/models.py` -- Ajout de la relation bidirectionnelle `findings` dans le modèle `Case`.
- `backend/src/iryx/main.py` -- Enregistrement du routeur `analytics_router` dans l'application FastAPI.
- `backend/migrations/versions/007_create_finding_table.py` -- Script de migration Alembic pour la table `findings` et ses index/contraintes.
- `backend/tests/unit/test_finding_migration.py` -- Tests unitaires de la migration 007 (offline upgrade/downgrade, inspection SQLite live).
- `backend/tests/unit/test_finding_models_and_schemas.py` -- Tests unitaires des schémas Pydantic v2 et des validations de types.
- `backend/tests/integration/test_findings_api.py` -- Tests d'intégration API couvrant création, consultation, modification, suppression, HTTP 422 et contrôle d'accès multi-tenant (403/404).

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/analytics/models.py` -- Implémenter le modèle ORM `Finding`, les énumérations (`FindingSeverity`, `FindingConfidence`, `FindingType`, `FindingStatus`) et le `UUIDList` TypeDecorator -- Assurer la persistance relationnelle conforme à D-05 et D-06.
- [x] `backend/src/iryx/analytics/schemas.py` -- Définir les schémas Pydantic v2 de validation stricte -- Garantir la validation bidirectionnelle des charges utiles API (D-04).
- [x] `backend/src/iryx/analytics/services.py` -- Implémenter les opérations de service CRUD pour les findings -- Isoler la logique de base de données du contrôleur HTTP.
- [x] `backend/src/iryx/analytics/router.py` -- Créer les routes REST `/api/v1/cases/{case_id}/findings` avec injection de `verify_case_access` -- Exposer les endpoints de consultation et de gestion sécurisés.
- [x] `backend/src/iryx/cases/models.py` -- Raccorder la relation `findings` sur le modèle `Case` avec suppression en cascade -- Maintenir l'intégrité du graphe d'objets ORM.
- [x] `backend/src/iryx/main.py` -- Enregistrer le routeur `analytics` dans l'application FastAPI principale -- Rendre les endpoints accessibles.
- [x] `backend/migrations/versions/007_create_finding_table.py` -- Développer la migration Alembic 007 avec clé étrangère vers `cases.id` et `users.id`, contraintes CHECK et index -- Permettre le déploiement reproductible du schéma (D-07).
- [x] `backend/tests/unit/test_finding_migration.py` -- Développer la suite de tests pour la migration 007 -- Valider le cycle upgrade/downgrade et l'intégrité DDL.
- [x] `backend/tests/unit/test_finding_models_and_schemas.py` -- Développer la suite de tests unitaires sur les schémas Pydantic -- Valider les rejets 422 sur données invalides et la sérialisation.
- [x] `backend/tests/integration/test_findings_api.py` -- Écrire les tests d'intégration des routes findings avec contrôle d'accès RBAC et isolation tenant -- Valider le respect strict des critères d'acceptation.

**Acceptance Criteria:**
- Given la migration Alembic 007 appliquée, when la table `findings` est inspectée, then elle comporte les colonnes `id`, `case_id`, `title`, `severity`, `confidence`, `finding_type`, `status`, `observation_refs`, `tool_execution_refs`, `created_by`, `created_at` avec contraintes d'intégrité et clés étrangères.
- Given une charge utile contenant une sévérité ou un type de constat non reconnu, when la validation s'exécute, then une erreur HTTP 422 Unprocessable Entity est renvoyée.
- Given une requête de modification ou suppression d'un finding sur un dossier étranger, when l'utilisateur tente l'opération, then la dépendance `verify_case_access` bloque la requête avec une erreur HTTP 403 Forbidden.

## Implementation Notes

## Spec Change Log

## Review Triage Log

| ID | Couche | Fichier / Emplacement | Description du constat | Verdict | Justification / Preuve | Action |
|---|---|---|---|---|---|---|
| E1 | Edge Case Hunter | `backend/src/iryx/analytics/services.py:1036` | Tri instable en pagination offset/limit sur `created_at` identique | `medium` | En cas de créations simultanées, l'absence de clé secondaire (`id.desc()`) peut dupliquer ou sauter des éléments entre pages. | patch |
| E2 | Edge Case Hunter | `backend/src/iryx/analytics/schemas.py:951-952` | Affectation in-place sur objet immuable dans `populate_total_items` | `low` | `setattr` sur objet sans `__dict__` ou avec slots restreints peut lever une `AttributeError`. | patch |
| E3 | Edge Case Hunter | `backend/src/iryx/analytics/models.py:486-489` | Passage d'un scalaire non-séquence à `UUIDList.process_bind_param` | `low` | Une chaîne passée directement provoquerait une itération caractère par caractère. Normaliser en liste sécurise le type. | patch |
| B1 | Blind Hunter | `backend/src/iryx/analytics/schemas.py` | Absence du schéma `FindingReview` prévu dans D-04 / contexte Epic 6 | `low` | Anticipation utile pour Story 6.4 (Porte H2), ajout direct du schéma Pydantic sans impact régressif. | patch |
| B2 | Blind Hunter | `backend/src/iryx/analytics/router.py` | Autorisation basée uniquement sur l'accès dossier sans restriction de rôle pour les écritures | `medium` | Les rôles en lecture seule (`VIEWER`) pouvaient modifier des findings ; `require_case_role` doit restreindre `POST/PATCH/DELETE` aux rôles `ADMIN`, `INVESTIGATOR`, `ANALYST`. | patch |
| B3 | Blind Hunter | `backend/src/iryx/analytics/models.py:571` | Index manquant sur `created_at` dans le modèle ORM `Finding` | `low` | L'index `ix_findings_created_at` existe en migration mais manquait dans la déclaration `mapped_column(index=True)`. | patch |
| B4 | Blind Hunter | `backend/src/iryx/analytics/models.py:557-565` | `server_default` manquant sur les colonnes de références du modèle ORM | `low` | Présent en migration 007 mais non spécifié côté ORM, risquant de créer une dérive de schéma sur les outils de détection. | patch |
| B5 | Blind Hunter | `backend/src/iryx/analytics/models.py:468` | Suivi de mutation in-place manquant sur `UUIDList` | `low` | `MutableList.as_mutable(UUIDList)` garantit la détection des mutations in-place sans réaffectation explicite. | patch |
| B6 | Blind Hunter | `backend/src/iryx/analytics/services.py:1036` | Tri secondaire déterministe manquant en pagination | `medium` | Doublon avec E1 : ajout du tie-breaker `Finding.id.desc()`. | patch |
| B7 | Blind Hunter | `backend/src/iryx/analytics/router.py` | Filtres de requête manquants pour `confidence` et `finding_type` | `low` | Ajout des paramètres optionnels de filtrage dans le service et le routeur HTTP. | patch |
| B8 | Blind Hunter | `backend/src/iryx/analytics/services.py` | Absence de verrou de vérification Verifier lors du passage à `validated` | `false` | La certification par le Verifier (FR23) et la porte H2 font l'objet des stories 6.3 et 6.4 ; la story 6.1 pose uniquement le socle CRUD de base. | rejeté |
| B9 | Blind Hunter | `backend/src/iryx/analytics/__init__.py` | Exportation redondante des enums sous alias `SchemaFinding*` | `low` | Nettoyage des ré-exportations superflues pour un contrat d'importation unifié. | patch |
| B10 | Blind Hunter | `backend/src/iryx/analytics/models.py:606` | Initialisation incomplète des valeurs par défaut dans `Finding.__init__` | `low` | Garantir que les instances non persistées ont des énumérations initialisées par défaut dès leur création Python. | patch |
| B11 | Blind Hunter | `backend/migrations/versions/007_create_finding_table.py` | Résolution de dialecte hors-ligne fragile dans la migration 007 | `false` | Les tests hors-ligne (`test_migration_007_offline_upgrade_sql`) s'exécutent avec succès et génèrent un SQL valide. | rejeté |
| B12 | Blind Hunter | `backend/tests/integration/test_findings_api.py` | Couverture de test manquante pour GET/DELETE inter-tenant et rejet du rôle VIEWER | `medium` | Renforcement des tests d'intégration pour GET unitaire, DELETE et vérification du refus 403 pour `VIEWER`. | patch |
| B13 | Blind Hunter | `backend/tests/unit/test_investigation_migration.py:37` | Assertion sur les heads supprimée plutôt qu'adaptée | `low` | Rétablissement d'une assertion explicite vérifiant la présence des révisions et des têtes dans `test_investigation_migration.py`. | patch |
| B14 | Blind Hunter | `_bmad-output/implementation-artifacts/spec-6-1-...md` | Sections de journalisation vides dans la spec | `false` | Rejeté en vertu de la règle 86 (un constat ne peut pas avoir pour correctif l'édition de la spec de ce build en cours). | rejeté |
| V1 | Verification Gap | `backend/src/iryx/analytics/services.py:47-53` | Absence de test vérifiant le cloisonnement inter-dossiers dans `get_finding` | `medium` | Pré-vérifié : un finding du dossier A accédé via l'URL du dossier B doit retourner HTTP 404. | patch |
| V2 | Verification Gap | `backend/src/iryx/analytics/services.py:93-94` | Mise à jour des listes de références via PATCH non testée | `medium` | Pré-vérifié : ajouter un cas de test vérifiant la modification effective d'`observation_refs` et `tool_execution_refs` en base. | patch |
| V3 | Verification Gap | `backend/src/iryx/analytics/services.py:64-65` | Absence de test vérifiant l'exclusion des findings d'autres dossiers dans `list_findings` | `medium` | Pré-vérifié : insérer des constats dans un autre dossier et s'assurer qu'ils ne polluent pas le listing du dossier cible. | patch |
| V4 | Verification Gap | `backend/src/iryx/analytics/router.py` | Contrôle de rôle RBAC manquant pour les utilisateurs VIEWER sur les routes de mutation | `medium` | Pré-vérifié (aligné avec B2) : bloquer les requêtes de mutation des utilisateurs VIEWER par `require_case_role`. | patch |

## Design Notes

Pour réconcilier l'exigence de type `ARRAY(UUID)` en environnement PostgreSQL de production et la compatibilité avec la base SQLite en mémoire utilisée pour les tests rapides (D-20), un `TypeDecorator` SQLAlchemy (`UUIDList`) est utilisé dans le modèle ORM. Il se résout en `postgresql.ARRAY(postgresql.UUID(as_uuid=True))` sur PostgreSQL et en `sa.JSON` sur SQLite, sérialisant automatiquement les listes d'objets `uuid.UUID`.

## Verification

**Commands:**
- `uv run pytest backend/tests/unit/test_finding_migration.py` -- expected: Tous les tests de migration 007 réussissent (upgrade/downgrade, schéma live).
- `uv run pytest backend/tests/unit/test_finding_models_and_schemas.py` -- expected: Toutes les validations Pydantic v2 et instanciations de modèles sont conformes.
- `uv run pytest backend/tests/integration/test_findings_api.py` -- expected: Toutes les routes findings passent avec succès (CRUD, 422 sur mauvais enums, 403 sur violation de tenant).
- `uv run pytest backend/tests/` -- expected: La suite complète des tests du backend demeure à 100% au vert sans régression.
- `uv run ruff check backend` -- expected: Zéro avertissement de linting.
- `uv run ruff format --check backend` -- expected: Code parfaitement formaté.
