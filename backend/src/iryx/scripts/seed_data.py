"""Idempotent demo data seeding for IRYX (Story 9.3).

Run with::

    uv run python -m iryx.scripts.seed_data

The command creates (or repairs) a demonstration organization, four accounts,
one open ransomware case, and three sealed demo evidences. It is safe to run
multiple times: existing rows are reused and missing or partially sealed data is
repaired without deleting unrelated records.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

# Imported first on purpose: it breaks the existing analytics <-> cases package
# import cycle when this module is the CLI entry point (``python -m ...``).
import iryx.analytics.models  # noqa: F401
from iryx.auth.models import Membership, MembershipRole, Organization, User
from iryx.cases.models import Case, CaseStatus
from iryx.core.config import get_settings
from iryx.core.security import hash_password, verify_password
from iryx.db.session import SessionLocal
from iryx.evidence.models import Evidence, IngestionRun, IngestionStatus
from iryx.evidence.tasks import process_evidence_ingestion
from iryx.scripts.demo_evidence import DemoEvidence, build_demo_evidences

ORGANIZATION_NAME = "Banque Atlantique DFIR"
CASE_TITLE = "Attaque Ransomware Serveur AD"
CASE_DESCRIPTION = (
    "Incident de démonstration : chiffrement ransomware d'un serveur Active Directory, "
    "exécution PowerShell suspecte et collecte de preuves Windows."
)

DEMO_PASSWORD_WARNING = (
    "AVERTISSEMENT : les identifiants ci-dessus sont réservés à la démonstration. "
    "Hors démonstration, utilisez des mots de passe robustes et personnalisés."
)

SEALED_FILE_MODE = 0o440
WRITABLE_FILE_MODE = 0o600


@dataclass(frozen=True, slots=True)
class DemoUserSpec:
    """A demo account with its fixed password and organization role."""

    email: str
    password: str
    role: MembershipRole


DEMO_USERS: tuple[DemoUserSpec, ...] = (
    DemoUserSpec("admin@iryx.local", "Admin12345!", MembershipRole.ADMIN),
    DemoUserSpec("analyst@iryx.local", "Analyst12345!", MembershipRole.ANALYST),
    DemoUserSpec(
        "investigator@iryx.local",
        "Investigator12345!",
        MembershipRole.INVESTIGATOR,
    ),
    DemoUserSpec("auditor@iryx.local", "Auditor12345!", MembershipRole.VIEWER),
)

ADMIN_EMAIL = DEMO_USERS[0].email


class SeedDataError(RuntimeError):
    """Raised when demo data cannot be created, written, or sealed."""


@dataclass(frozen=True, slots=True)
class SeededEvidence:
    """Sealed demo evidence as reported in the final summary."""

    original_name: str
    evidence_id: str
    sha256: str
    detected_type: str
    file_size: int
    staging_path: str


@dataclass(frozen=True, slots=True)
class SeedSummary:
    """Result of a successful demo seeding run."""

    organization_name: str
    case_id: str
    case_title: str
    evidences: tuple[SeededEvidence, ...]


def _ensure_staging_directory(staging_path: str) -> Path:
    """Create and validate the configured evidence staging directory."""
    if not staging_path or not staging_path.strip():
        raise SeedDataError("Le chemin de staging configuré est vide.")
    staging_dir = Path(staging_path)
    try:
        staging_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SeedDataError(
            f"Impossible de créer le répertoire de staging '{staging_dir}': {exc}"
        ) from exc
    if not staging_dir.is_dir():
        raise SeedDataError(f"Le chemin de staging '{staging_dir}' n'est pas un répertoire.")
    return staging_dir.resolve()


def _ensure_organization(db: Session) -> Organization:
    organization = db.scalar(
        select(Organization)
        .where(Organization.name == ORGANIZATION_NAME)
        .order_by(Organization.created_at.asc(), Organization.id.asc())
    )
    if organization is None:
        organization = Organization(name=ORGANIZATION_NAME)
        db.add(organization)
        db.flush()
    return organization


def _ensure_user(db: Session, spec: DemoUserSpec) -> User:
    user = db.scalar(select(User).where(User.email == spec.email))
    if user is None:
        user = User(
            email=spec.email,
            hashed_password=hash_password(spec.password),
            is_active=True,
        )
        db.add(user)
        db.flush()
        return user

    if not user.is_active:
        user.is_active = True
    if not verify_password(spec.password, user.hashed_password):
        user.hashed_password = hash_password(spec.password)
    return user


def _ensure_membership(
    db: Session,
    organization: Organization,
    user: User,
    role: MembershipRole,
) -> Membership:
    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == organization.id,
            Membership.user_id == user.id,
        )
    )
    if membership is None:
        membership = Membership(
            organization_id=organization.id,
            user_id=user.id,
            role=role.value,
        )
        db.add(membership)
        db.flush()
    elif membership.role != role.value:
        membership.role = role.value
    return membership


def _ensure_case(db: Session, organization: Organization, creator: User) -> Case:
    case = db.scalar(
        select(Case)
        .where(
            Case.organization_id == organization.id,
            Case.title == CASE_TITLE,
        )
        .order_by(Case.created_at.asc(), Case.id.asc())
    )
    if case is None:
        case = Case(
            organization_id=organization.id,
            title=CASE_TITLE,
            description=CASE_DESCRIPTION,
            status=CaseStatus.OPEN,
            created_by=creator.id,
        )
        db.add(case)
        db.flush()
        return case

    if case.status != CaseStatus.OPEN:
        case.status = CaseStatus.OPEN
    if not case.description:
        case.description = CASE_DESCRIPTION
    if case.created_by is None:
        case.created_by = creator.id
    return case


def _ensure_evidence(
    db: Session,
    case: Case,
    demo: DemoEvidence,
    importer: User,
    expected_sha256: str,
) -> Evidence:
    evidence = db.scalar(
        select(Evidence)
        .where(
            Evidence.case_id == case.id,
            Evidence.original_name == demo.original_name,
        )
        .order_by(Evidence.created_at.asc(), Evidence.id.asc())
    )
    if evidence is None:
        evidence = Evidence(
            case_id=case.id,
            original_name=demo.original_name,
            file_size=len(demo.content),
            sha256=None,
            detected_type=None,
            imported_by=importer.id,
        )
        db.add(evidence)
        db.flush()
        return evidence

    needs_reseal = (
        evidence.file_size != len(demo.content)
        or evidence.sha256 is None
        or evidence.sha256 != expected_sha256
        or evidence.detected_type is None
    )
    if needs_reseal:
        evidence.file_size = len(demo.content)
        evidence.sha256 = None
        evidence.detected_type = None
    if evidence.imported_by is None:
        evidence.imported_by = importer.id
    return evidence


def _ensure_ingestion_run(db: Session, evidence: Evidence) -> IngestionRun:
    run = db.scalar(
        select(IngestionRun)
        .where(IngestionRun.evidence_id == evidence.id)
        .order_by(IngestionRun.started_at.desc(), IngestionRun.id.desc())
    )
    if run is None:
        run = IngestionRun(
            evidence_id=evidence.id,
            status=IngestionStatus.PENDING,
            progress=0,
        )
        db.add(run)
        db.flush()
        return run

    if run.status == IngestionStatus.FAILED or evidence.sha256 is None or run.progress != 100:
        run.status = IngestionStatus.PENDING
        run.progress = 0
        run.error_message = None
        run.completed_at = None
    return run


def _make_writable(path: Path) -> None:
    with contextlib.suppress(OSError):
        os.chmod(path, WRITABLE_FILE_MODE)


def _prepare_staging_file(path: Path, content: bytes) -> None:
    """Write the deterministic fixture unless an identical file already exists."""
    if path.is_file():
        try:
            same_content = (
                path.stat().st_size == len(content)
                and hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(content).digest()
            )
        except OSError:
            same_content = False
        if same_content:
            return
        _make_writable(path)

    try:
        path.write_bytes(content)
    except OSError as exc:
        raise SeedDataError(
            f"Impossible d'écrire la preuve de démonstration '{path}': {exc}"
        ) from exc


def _apply_sealed_permissions(path: Path) -> None:
    try:
        os.chmod(path, SEALED_FILE_MODE)
    except OSError as exc:
        raise SeedDataError(
            f"Impossible d'appliquer les permissions scellées à '{path}': {exc}"
        ) from exc


def _verify_sealed_evidence(
    evidence_id: uuid.UUID,
    original_name: str,
    staging_path: Path,
    expected_sha256: str,
) -> SeededEvidence:
    db = SessionLocal()
    try:
        evidence = db.get(Evidence, evidence_id)
        if evidence is None:
            raise SeedDataError(f"La preuve '{original_name}' est introuvable après scellement.")
        run = db.scalar(
            select(IngestionRun)
            .where(IngestionRun.evidence_id == evidence_id)
            .order_by(IngestionRun.started_at.desc(), IngestionRun.id.desc())
        )
        if evidence.sha256 != expected_sha256:
            raise SeedDataError(
                f"Le SHA-256 de la preuve '{original_name}' est incohérent après scellement."
            )
        if evidence.detected_type is None:
            raise SeedDataError(
                f"Le type détecté de la preuve '{original_name}' est absent après scellement."
            )
        if run is None or run.status != IngestionStatus.COMPLETED or run.progress != 100:
            raise SeedDataError(
                f"Le run d'ingestion de la preuve '{original_name}' n'est pas terminé."
            )
        return SeededEvidence(
            original_name=original_name,
            evidence_id=str(evidence_id),
            sha256=evidence.sha256,
            detected_type=evidence.detected_type,
            file_size=evidence.file_size,
            staging_path=str(staging_path),
        )
    finally:
        db.close()


def seed_demo_data() -> SeedSummary:
    """Create or repair the demo dataset and return a printable summary.

    Raises:
        SeedDataError: If the staging directory or a sealed evidence cannot be
            prepared. The caller is expected to surface the message and exit
            with a non-zero status.
    """
    settings = get_settings()
    staging_dir = _ensure_staging_directory(settings.evidence_staging_path)
    fixtures = build_demo_evidences()

    db = SessionLocal()
    prepared: list[tuple[DemoEvidence, uuid.UUID, Path, str]] = []
    try:
        organization = _ensure_organization(db)
        users: dict[str, User] = {}
        for spec in DEMO_USERS:
            user = _ensure_user(db, spec)
            _ensure_membership(db, organization, user, spec.role)
            users[spec.email] = user

        admin = users[ADMIN_EMAIL]
        case = _ensure_case(db, organization, admin)
        case_id = case.id

        for demo in fixtures:
            expected_sha256 = hashlib.sha256(demo.content).hexdigest()
            evidence = _ensure_evidence(db, case, demo, admin, expected_sha256)
            _ensure_ingestion_run(db, evidence)
            staging_path = staging_dir / f"{evidence.id}.bin"
            _prepare_staging_file(staging_path, demo.content)
            prepared.append((demo, evidence.id, staging_path, expected_sha256))

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    sealed: list[SeededEvidence] = []
    for demo, evidence_id, staging_path, expected_sha256 in prepared:
        result = process_evidence_ingestion(str(evidence_id), str(staging_path))
        if result.get("status") != "completed":
            raise SeedDataError(
                f"Le scellement de la preuve '{demo.original_name}' a échoué : "
                f"{result.get('error', 'statut inconnu')}"
            )
        _apply_sealed_permissions(staging_path)
        sealed.append(
            _verify_sealed_evidence(
                evidence_id,
                demo.original_name,
                staging_path,
                expected_sha256,
            )
        )

    return SeedSummary(
        organization_name=ORGANIZATION_NAME,
        case_id=str(case_id),
        case_title=CASE_TITLE,
        evidences=tuple(sealed),
    )


def format_summary(summary: SeedSummary) -> str:
    """Render the final human-readable summary, including demo credentials."""
    lines = [
        "=" * 72,
        "IRYX - Données de démonstration prêtes",
        "=" * 72,
        f"Organisation : {summary.organization_name}",
        f"Dossier      : {summary.case_title} ({summary.case_id})",
        "Idempotence  : relance sans doublon, données existantes réutilisées et éléments "
        "manquants réparés.",
        "",
        "Comptes de démonstration :",
    ]
    for spec in DEMO_USERS:
        lines.append(f"  - {spec.email} / {spec.password}  [{spec.role.value}]")
    lines.extend(["", "Preuves scellées :"])
    for evidence in summary.evidences:
        lines.append(
            f"  - {evidence.original_name} | {evidence.file_size} octets | {evidence.detected_type}"
        )
        lines.append(f"    SHA-256 : {evidence.sha256}")
        lines.append(f"    Fichier : {evidence.staging_path}")
    lines.extend(["", DEMO_PASSWORD_WARNING, "=" * 72])
    return "\n".join(lines)


def main() -> int:
    """CLI entry point. Returns a non-zero status on failure."""
    try:
        summary = seed_demo_data()
    except Exception as exc:
        print(f"[ERREUR] Le peuplement de démonstration a échoué : {exc}", file=sys.stderr)
        return 1
    print(format_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
