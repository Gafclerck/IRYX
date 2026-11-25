"""IRYX Analytics and Finding Business Services."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from iryx.analytics.models import (
    Finding,
    FindingConfidence,
    FindingSeverity,
    FindingStatus,
    FindingType,
)
from iryx.analytics.schemas import FindingCreate, FindingReview, FindingUpdate
from iryx.core.exceptions import FindingNotFoundException, ValidationException


class FindingService:
    """Service encapsulating CRUD and persistence operations for investigation findings."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_finding(
        self,
        case_id: uuid.UUID,
        payload: FindingCreate,
        created_by: uuid.UUID | None = None,
    ) -> Finding:
        """Create and persist a new technical finding with status 'proposed'."""
        finding = Finding(
            case_id=case_id,
            title=payload.title,
            severity=payload.severity,
            confidence=payload.confidence,
            finding_type=payload.finding_type,
            status=FindingStatus.PROPOSED,
            observation_refs=list(payload.observation_refs),
            tool_execution_refs=list(payload.tool_execution_refs),
            created_by=created_by,
        )
        self.db.add(finding)
        self.db.commit()
        self.db.refresh(finding)
        return finding

    def get_finding(self, case_id: uuid.UUID, finding_id: uuid.UUID) -> Finding:
        """Retrieve a single finding by ID scoped to the given case."""
        stmt = select(Finding).where(Finding.id == finding_id, Finding.case_id == case_id)
        finding = self.db.scalar(stmt)
        if finding is None:
            raise FindingNotFoundException()
        return finding

    def list_findings(
        self,
        case_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        status: FindingStatus | None = None,
        severity: FindingSeverity | None = None,
        confidence: FindingConfidence | None = None,
        finding_type: FindingType | None = None,
    ) -> tuple[Sequence[Finding], int]:
        """List paginated findings belonging to a case with deterministic sorting and filtering."""
        stmt = select(Finding).where(Finding.case_id == case_id)
        count_stmt = select(func.count(Finding.id)).where(Finding.case_id == case_id)

        if status is not None:
            stmt = stmt.where(Finding.status == status)
            count_stmt = count_stmt.where(Finding.status == status)

        if severity is not None:
            stmt = stmt.where(Finding.severity == severity)
            count_stmt = count_stmt.where(Finding.severity == severity)

        if confidence is not None:
            stmt = stmt.where(Finding.confidence == confidence)
            count_stmt = count_stmt.where(Finding.confidence == confidence)

        if finding_type is not None:
            stmt = stmt.where(Finding.finding_type == finding_type)
            count_stmt = count_stmt.where(Finding.finding_type == finding_type)

        total = self.db.scalar(count_stmt) or 0
        items = self.db.scalars(
            stmt.order_by(Finding.created_at.desc(), Finding.id.desc()).offset(offset).limit(limit)
        ).all()

        return items, total

    def update_finding(
        self,
        case_id: uuid.UUID,
        finding_id: uuid.UUID,
        payload: FindingUpdate,
    ) -> Finding:
        """Update fields of an existing finding scoped to the given case."""
        finding = self.get_finding(case_id=case_id, finding_id=finding_id)

        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if field in ("observation_refs", "tool_execution_refs") and value is not None:
                setattr(finding, field, list(value))
            elif value is not None:
                setattr(finding, field, value)

        self.db.commit()
        self.db.refresh(finding)
        return finding

    def delete_finding(self, case_id: uuid.UUID, finding_id: uuid.UUID) -> None:
        """Delete an existing finding scoped to the given case."""
        finding = self.get_finding(case_id=case_id, finding_id=finding_id)
        self.db.delete(finding)
        self.db.commit()

    def review_finding(
        self,
        case_id: uuid.UUID,
        finding_id: uuid.UUID,
        payload: FindingReview,
        user_id: uuid.UUID | None = None,
    ) -> Finding:
        """Apply human-in-the-loop review decision to a finding (Story 6.4, FR19)."""
        stmt = (
            select(Finding)
            .where(Finding.id == finding_id, Finding.case_id == case_id)
            .with_for_update()
        )
        finding = self.db.scalar(stmt)
        if finding is None:
            raise FindingNotFoundException()

        if payload.action not in ("validate", "reject"):
            raise ValidationException(
                message=f"Action de revue invalide : '{payload.action}'.",
                code="INVALID_REVIEW_ACTION",
            )

        if payload.action == "validate":
            finding.status = FindingStatus.VALIDATED
            if payload.severity is not None:
                finding.severity = payload.severity
            if payload.confidence is not None:
                finding.confidence = payload.confidence
        elif payload.action == "reject":
            finding.status = FindingStatus.REJECTED

        if user_id is not None:
            finding.created_by = user_id

        self.db.commit()
        self.db.refresh(finding)
        return finding
