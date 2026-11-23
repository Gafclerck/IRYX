---
title: 'Story 2.1 : Modèles Organization et Membership, migration Alembic et schémas Pydantic'
type: 'feature'
created: '2026-11-23'
status: 'done'
baseline_commit: '7fdbd90983c3646bd0005390682c85ac3087c5dc'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/docs/03-modele-de-donnees.md'
  - '{project-root}/docs/05-conventions-backend.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La plateforme IRYX ne dispose pas encore des structures relationnelles pour gérer le multi-tenant, les organisations clientes et l'affectation des utilisateurs avec des rôles RBAC distincts. Sans ces entités fondamentales, il est impossible de segmenter les dossiers d'investigation ni d'appliquer le contrôle d'accès strict (Zero Leak).

**Approach:** Définir les modèles SQLAlchemy 2.x `Organization` et `Membership` dans `backend/src/iryx/auth/models.py`, l'énumération `MembershipRole` (`admin`, `analyst`, `investigator`, `viewer`), générer la migration Alembic `002_create_org_and_membership_tables` avec contraintes de clés étrangères en cascade, contrainte CHECK sur les rôles et contrainte d'unicité composite `(organization_id, user_id)`, et fournir les schémas Pydantic v2 correspondants (`OrganizationCreate`, `OrganizationResponse`, `MembershipCreate`, `MembershipResponse`).

## Boundaries & Constraints

**Always:**
- Respecter les noms d'entités, de colonnes et de tables définis dans `docs/03-modele-de-donnees.md` (`organizations`, `memberships`).
- Utiliser `sa.Uuid` avec génération de valeur par défaut `uuid.uuid4` pour toutes les clés primaires.
- Établir les clés étrangères `organization_id` vers `organizations.id` et `user_id` vers `users.id` avec suppression en cascade (`ondelete="CASCADE"` au niveau SQL et `cascade="all, delete-orphan"` au niveau ORM).
- Restreindre les rôles strictement aux 4 valeurs définies dans l'architecture : `admin`, `analyst`, `investigator`, `viewer` via `MembershipRole(StrEnum)` et une contrainte `CHECK` SQL `ck_memberships_role_check`.
- Imposer une contrainte d'unicité composite sur `(organization_id, user_id)` (`uq_memberships_organization_id_user_id` ou `uq_org_user`) pour interdire formellement les adhésions en doublon.
- Utiliser des horodatages UTC gérés automatiquement (`created_at` et `updated_at` avec `server_default=func.now()`).
- Assurer le typage strict Pydantic v2 avec `model_config = ConfigDict(from_attributes=True)`.
- Maintenir 0 erreur et 0 avertissement avec `uv run ruff check backend/`.
- Assurer 100% de réussite de la suite de tests automatisés avec `uv run pytest backend/tests`.

**Never:**
- Ne jamais appeler `Base.metadata.create_all()` en production (Règle 9 de `docs/05-conventions-backend.md`).
- Ne jamais exposer directement les modèles SQLAlchemy ORM en dehors de la couche interne de persistance ; toujours utiliser des schémas Pydantic v2 (Règle 3).
- Ne jamais ajouter de rôles non prévus par l'architecture (comme `superuser`, `owner`, ou `root`).
- Ne jamais permettre d'adhésions orphelines sans utilisateur ou sans organisation associée.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Création valide Organization (ORM & Schema) | `name="CERT Interne"` | Instance persistée avec UUID généré, `created_at` et `updated_at` UTC | `ValidationError` si `name` vide ou absent |
| Création valide Membership (ORM & Schema) | `organization_id=<uuid>`, `user_id=<uuid>`, `role="analyst"` | Adhésion persistée reliée à l'organisation et à l'utilisateur | `ValidationError` si rôle inconnu |
| Rôle invalide dans MembershipCreate | `role="superuser"` ou `role="editor"` | Rejet immédiat par validation Pydantic v2 | Levée de `ValidationError` (HTTP 422) listant les rôles autorisés |
| Rôle invalide au niveau base SQL | Tentative d'insertion SQL avec `role='invalid'` | Rejet par contrainte CHECK PostgreSQL/SQLite | `IntegrityError` de base de données |
| Doublon d'adhésion `(organization_id, user_id)` | Insertion d'un second membership pour le même couple `(org, user)` | Rejet par contrainte d'unicité composite `uq_memberships_organization_id_user_id` | `IntegrityError` levée par SQLAlchemy |
| Suppression d'une organisation en cascade | Suppression de `Organization` ayant 2 `Membership` | L'organisation et ses 2 adhésions sont supprimées sans orphelins | N/A (Cascade deletion opérationnelle) |
| Suppression d'un utilisateur en cascade | Suppression de `User` ayant des adhésions | Les adhésions rattachées à cet utilisateur sont supprimées | N/A (Cascade deletion opérationnelle) |
| Migration Alembic 002 upgrade / downgrade | `alembic upgrade head` puis `alembic downgrade 001` | Tables créées avec index et contraintes, puis supprimées proprement | Erreur si régression de chaîne Alembic |

</frozen-after-approval>

## Code Map

- `backend/src/iryx/auth/models.py` -- Définition des modèles ORM SQLAlchemy `Organization` et `Membership`, enum `MembershipRole`, et mise à jour des relations sur `User`.
- `backend/src/iryx/auth/schemas.py` -- Schémas Pydantic v2 `OrganizationCreate`, `OrganizationResponse`, `MembershipRole`, `MembershipCreate`, `MembershipResponse`.
- `backend/src/iryx/auth/__init__.py` -- Exportation publique des nouveaux modèles, enum et schémas pour le module `auth`.
- `backend/migrations/versions/002_create_org_and_membership_tables.py` -- Migration Alembic réversible créant `organizations` et `memberships` avec clés étrangères cascade, contrainte CHECK et contrainte d'unicité.
- `backend/tests/unit/test_org_membership_models.py` -- Tests unitaires des modèles ORM `Organization`, `Membership`, cascade et contraintes d'intégrité.
- `backend/tests/unit/test_org_membership_schemas.py` -- Tests unitaires des schémas Pydantic (validation des rôles, normalisation, rejets).
- `backend/tests/unit/test_org_migration.py` -- Tests unitaires de la migration Alembic 002 (upgrade, downgrade, intégrité du schéma).

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/auth/models.py` -- Déclarer `MembershipRole(StrEnum)`, `Organization(Base)` et `Membership(Base)` avec clés primaires UUID, horodatages UTC, contrainte CHECK sur rôle, unicité composite et cascade d'intégrité ; lier `User.memberships`.
- [x] `backend/src/iryx/auth/schemas.py` -- Implémenter les schémas Pydantic v2 pour `Organization` (`OrganizationCreate`, `OrganizationResponse`) et `Membership` (`MembershipRole`, `MembershipCreate`, `MembershipResponse`).
- [x] `backend/src/iryx/auth/__init__.py` -- Exporter les nouveaux modèles et schémas dans l'interface publique du module.
- [x] `backend/migrations/versions/002_create_org_and_membership_tables.py` -- Rédiger le script de migration Alembic 002 avec `revision="002"`, `down_revision="001"` définissant les tables `organizations` et `memberships`.
- [x] `backend/tests/unit/test_org_membership_models.py` -- Écrire la suite de tests unitaires pour la persistance, l'unicité `(organization_id, user_id)` et la suppression en cascade.
- [x] `backend/tests/unit/test_org_membership_schemas.py` -- Écrire la suite de tests unitaires pour la validation des schémas Pydantic (rôles valides vs invalides, formats UUID, sérialisation).
- [x] `backend/tests/unit/test_org_migration.py` -- Écrire la suite de tests validant l'application et le rollback de la migration 002.

**Acceptance Criteria:**
- Given la base de données initialisée, when la migration `002_create_org_and_membership_tables` est exécutée, then les tables `organizations` et `memberships` existent avec les colonnes, contraintes et index requis.
- Given une charge utile Pydantic avec un rôle `admin`, `analyst`, `investigator` ou `viewer`, when `MembershipCreate` est validé, then l'objet est accepté avec succès.
- Given une charge utile Pydantic avec un rôle hors liste (ex: `superuser`), when `MembershipCreate` est validé, then Pydantic lève une erreur de validation `ValidationError`.
- Given une organisation avec des membres associés en base, when l'organisation est supprimée, then toutes ses lignes d'adhésion `memberships` sont automatiquement supprimées en cascade sans laisser d'orphelins.
- Given une adhésion existante pour un couple `(organization_id, user_id)`, when une seconde tentative d'adhésion est effectuée pour le même couple, then la contrainte d'unicité `uq_memberships_organization_id_user_id` bloque l'opération.

## Implementation Notes

- Modèles `Organization` et `Membership` et enum `MembershipRole(StrEnum)` créés dans `backend/src/iryx/auth/models.py`.
- Clés primaires `sa.Uuid` avec `default=uuid.uuid4` et horodatages UTC automatiques (`func.now()`).
- Contraintes d'intégrité définies sur `memberships` : `uq_memberships_organization_id_user_id`, `ck_memberships_role_check`, et clés étrangères avec `ondelete="CASCADE"` vers `organizations.id` et `users.id`.
- Relations ORM configurées avec `cascade="all, delete-orphan"` sur `Organization.memberships` et `User.memberships`.
- Schémas Pydantic v2 `OrganizationCreate`, `OrganizationResponse`, `MembershipCreate`, `MembershipResponse` implémentés dans `backend/src/iryx/auth/schemas.py`.
- Migration Alembic `002_create_org_and_membership_tables.py` réversible et testée avec upgrade et downgrade.
- 100% des tests unitaires et vérifications Ruff (`uv run ruff check backend/` et `uv run pytest backend/tests`) au vert (121 tests passés).

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Evidence / Justification | Route |
|---|---|---|---|
| B1: Absence de `passive_deletes=True` sur les relations cascade ORM | low | En présence de `ondelete="CASCADE"` en base, `passive_deletes=True` évite à SQLAlchemy d'émettre des requêtes SELECT/DELETE superflues sur les enfants. | patch |
| B2: Index colonne unique `memberships.organization_id` redondant avec la contrainte unique composite | low | La contrainte unique composite commence par `organization_id`, rendant un index unicolonne séparé techniquement redondant mais inoffensif. | rejeté |
| B3: Absence de contrainte CHECK SQL `length(trim(name)) > 0` sur `organizations.name` | low | Non stipulé dans `docs/03` ; la validation de format et non-vacuité est assurée par le schéma Pydantic `OrganizationCreate` (Règle 3). | rejeté |
| B4: Typage primitif `Mapped[str]` sur `Membership.role` au lieu de `Mapped[MembershipRole]` | low | `Mapped[str]` utilisé avec colonne `String(32)` et CHECK constraint SQL. Typage avec enum envisageable mais non bloquant. | rejeté |
| B5: Utilisation de noms littéraux sans `op.f(...)` sur UniqueConstraint et CheckConstraint dans la migration 002 | low | Harmonisation des conventions de nommage Alembic via `op.f(...)` recommandée pour une stricte cohérence. | patch |
| B6: Littéraux de rôles codés en dur dans `CheckConstraint` du modèle au lieu d'être dérivés de `MembershipRole` | low | Dériver la contrainte CHECK de `MembershipRole` garantit le respect du principe DRY en cas d'évolution. | patch |
| B7: Absence des schémas `MembershipUpdate` et `OrganizationUpdate` | false | Hors périmètre de la Story 2.1 ; les opérations de mise à jour font l'objet de la Story 2.2. | rejeté |
| B8: Absence de schémas de réponse paginée | false | Hors périmètre de la Story 2.1 ; aucun endpoint REST de listing n'est implémenté dans cette story (dévolu à Story 2.2). | rejeté |
| B9: Assertion fragile `heads == ["002"]` dans `test_alembic.py` | low | Remplacer par `len(heads) == 1` et vérification de chaîne évite une rupture lors de l'ajout de migrations futures. | patch |
| B10: Absence de vérification explicite des check constraints dans `test_org_migration.py` | false | La contrainte CHECK SQL est déjà formellement testée et vérifiée dans `test_org_membership_models.py`. | rejeté |
| B11: Absence de colonne `updated_at` sur `Membership` | false | La spécification `docs/03-modele-de-donnees.md` section 1.3 définit explicitement `Membership` sans `updated_at`. L'ajouter violerait le modèle gelé. | rejeté |
| B12: Absence des détails d'identité utilisateur dans `MembershipResponse` | false | `MemberOut` avec email est prévu spécifiquement pour la Story 2.2 (API d'attribution des rôles). | rejeté |
| B13: Défense `setdefault` dans `__init__` du modèle si `id=None` explicite | low | Remplacer par `if kw.get("id") is None: kw["id"] = uuid.uuid4()` pour immuniser contre un passage explicite de `None`. | patch |
| B14: Absence de tests sur les champs manquants dans `MembershipCreate` | low | Ajout de tests unitaires vérifiant le rejet des charges utiles incomplètes dans `test_org_membership_schemas.py`. | patch |

## Design Notes

- **Modèle ORM `Organization` :**
  ```python
  class Organization(Base):
      __tablename__ = "organizations"
      id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
      name: Mapped[str] = mapped_column(String(255), nullable=False)
      created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
      updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
      memberships: Mapped[list["Membership"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
  ```
- **Modèle ORM `Membership` :**
  ```python
  class MembershipRole(StrEnum):
      ADMIN = "admin"
      ANALYST = "analyst"
      INVESTIGATOR = "investigator"
      VIEWER = "viewer"

  class Membership(Base):
      __tablename__ = "memberships"
      id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
      organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
      user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
      role: Mapped[str] = mapped_column(String(32), nullable=False)
      created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
      __table_args__ = (
          UniqueConstraint("organization_id", "user_id", name="uq_memberships_organization_id_user_id"),
          CheckConstraint("role IN ('admin', 'analyst', 'investigator', 'viewer')", name="ck_memberships_role_check"),
      )
  ```

## Verification

**Commands:**
- `uv run ruff check backend/` -- expected: `All checks passed!`
- `uv run pytest backend/tests` -- expected: `All tests passed`
