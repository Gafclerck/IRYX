"""FastAPI REST router for Forensic Gateway tool executions and observations consultation."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from iryx.analytics.models import Observation
from iryx.api.dependencies import get_db
from iryx.auth.dependencies import get_current_user
from iryx.auth.models import User
from iryx.cases.dependencies import verify_case_access
from iryx.cases.models import Case
from iryx.core.exceptions import (
    ObservationNotFoundException,
    ToolExecutionNotFoundException,
    ValidationException,
)
from iryx.gateway.models import ToolExecution, ToolExecutionStatus
from iryx.gateway.registry import ToolRegistry, get_tool_registry
from iryx.gateway.schemas import (
    ObservationListResponse,
    ObservationRead,
    ToolExecutionListResponse,
    ToolExecutionRead,
    ToolMetadataResponse,
)

router = APIRouter(tags=["Forensic Gateway"])


def _normalize_utc(dt: datetime | None) -> datetime | None:
    """Normalize datetime to UTC, converting naive datetime assuming UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


@router.get(
    "/api/v1/cases/{case_id}/tool-executions",
    response_model=ToolExecutionListResponse,
    status_code=status.HTTP_200_OK,
    summary="Consultation paginée des exécutions d'outils d'un dossier",
    description=(
        "Retourne les traces d'audit immuables des exécutions d'outils associées à un dossier."
    ),
)
def list_tool_executions(
    case_id: uuid.UUID,
    _case: Annotated[Case, Depends(verify_case_access)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Nombre maximum d'éléments par page (défaut 50, min 1, max 100).",
        ),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Décalage pour pagination (défaut 0)."),
    ] = 0,
    tool_name: Annotated[
        str | None,
        Query(description="Filtrer par nom de l'outil forensique."),
    ] = None,
    status: Annotated[
        ToolExecutionStatus | None,
        Query(
            alias="status",
            description="Filtrer par statut ('success', 'error', 'timeout').",
        ),
    ] = None,
    start_date: Annotated[
        datetime | None,
        Query(description="Filtre temporel de début (format ISO-8601 UTC)."),
    ] = None,
    end_date: Annotated[
        datetime | None,
        Query(description="Filtre temporel de fin (format ISO-8601 UTC)."),
    ] = None,
) -> ToolExecutionListResponse:
    """Retrieve paginated and filtered list of tool executions for a specific case."""
    if limit < 1 or limit > 100 or offset < 0:
        raise ValidationException(
            "Paramètres de pagination invalides (1 <= limit <= 100, offset >= 0)."
        )

    start_date_utc = _normalize_utc(start_date)
    end_date_utc = _normalize_utc(end_date)
    if start_date_utc is not None and end_date_utc is not None and start_date_utc > end_date_utc:
        raise ValidationException(
            "La date de début (start_date) doit être antérieure "
            "ou égale à la date de fin (end_date)."
        )

    stmt = select(ToolExecution).where(ToolExecution.case_id == case_id)
    count_stmt = select(func.count(ToolExecution.id)).where(ToolExecution.case_id == case_id)

    if tool_name:
        stmt = stmt.where(ToolExecution.tool_name == tool_name)
        count_stmt = count_stmt.where(ToolExecution.tool_name == tool_name)
    if status is not None:
        stmt = stmt.where(ToolExecution.status == status.value)
        count_stmt = count_stmt.where(ToolExecution.status == status.value)
    if start_date_utc:
        stmt = stmt.where(ToolExecution.created_at >= start_date_utc)
        count_stmt = count_stmt.where(ToolExecution.created_at >= start_date_utc)
    if end_date_utc:
        stmt = stmt.where(ToolExecution.created_at <= end_date_utc)
        count_stmt = count_stmt.where(ToolExecution.created_at <= end_date_utc)

    total = db.scalar(count_stmt) or 0
    stmt = (
        stmt.order_by(ToolExecution.created_at.desc(), ToolExecution.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(db.scalars(stmt).all())
    has_more = (offset + len(items)) < total

    return ToolExecutionListResponse(
        items=[ToolExecutionRead.model_validate(e) for e in items],
        total=total,
        total_items=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.get(
    "/api/v1/cases/{case_id}/tool-executions/{execution_id}",
    response_model=ToolExecutionRead,
    status_code=status.HTTP_200_OK,
    summary="Consultation détaillée d'une exécution d'outil",
    description="Retourne les détails et l'empreinte SHA-256 d'une exécution d'outil d'un dossier.",
)
def get_tool_execution(
    case_id: uuid.UUID,
    execution_id: uuid.UUID,
    _case: Annotated[Case, Depends(verify_case_access)],
    db: Annotated[Session, Depends(get_db)],
) -> ToolExecutionRead:
    """Retrieve a single tool execution record by ID."""
    execution = db.scalar(
        select(ToolExecution).where(
            ToolExecution.id == execution_id,
            ToolExecution.case_id == case_id,
        )
    )
    if execution is None:
        raise ToolExecutionNotFoundException()
    return ToolExecutionRead.model_validate(execution)


@router.get(
    "/api/v1/cases/{case_id}/observations",
    response_model=ObservationListResponse,
    status_code=status.HTTP_200_OK,
    summary="Consultation paginée des observations normalisées d'un dossier",
    description="Permet de naviguer dans l'intégralité des faits techniques extraits des preuves.",
)
def list_observations(
    case_id: uuid.UUID,
    _case: Annotated[Case, Depends(verify_case_access)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Nombre maximum d'éléments par page (défaut 50, min 1, max 100).",
        ),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Décalage pour pagination (défaut 0)."),
    ] = 0,
    tool_name: Annotated[
        str | None,
        Query(description="Filtrer par nom de l'outil extracteur."),
    ] = None,
    source_id: Annotated[
        uuid.UUID | None,
        Query(description="Filtrer par identifiant de la preuve source."),
    ] = None,
    tool_execution_id: Annotated[
        uuid.UUID | None,
        Query(description="Filtrer par exécution d'outil source."),
    ] = None,
    start_date: Annotated[
        datetime | None,
        Query(description="Filtre temporel de début (format ISO-8601 UTC)."),
    ] = None,
    end_date: Annotated[
        datetime | None,
        Query(description="Filtre temporel de fin (format ISO-8601 UTC)."),
    ] = None,
) -> ObservationListResponse:
    """Retrieve paginated and filtered list of observations for a specific case."""
    if limit < 1 or limit > 100 or offset < 0:
        raise ValidationException(
            "Paramètres de pagination invalides (1 <= limit <= 100, offset >= 0)."
        )

    start_date_utc = _normalize_utc(start_date)
    end_date_utc = _normalize_utc(end_date)
    if start_date_utc is not None and end_date_utc is not None and start_date_utc > end_date_utc:
        raise ValidationException(
            "La date de début (start_date) doit être antérieure "
            "ou égale à la date de fin (end_date)."
        )

    stmt = select(Observation).where(Observation.case_id == case_id)
    count_stmt = select(func.count(Observation.id)).where(Observation.case_id == case_id)

    if tool_name:
        stmt = stmt.where(Observation.tool_name == tool_name)
        count_stmt = count_stmt.where(Observation.tool_name == tool_name)
    if source_id:
        stmt = stmt.where(Observation.source_id == source_id)
        count_stmt = count_stmt.where(Observation.source_id == source_id)
    if tool_execution_id:
        stmt = stmt.where(Observation.tool_execution_id == tool_execution_id)
        count_stmt = count_stmt.where(Observation.tool_execution_id == tool_execution_id)
    if start_date_utc:
        date_col = func.coalesce(Observation.timestamp_utc, Observation.created_at)
        stmt = stmt.where(date_col >= start_date_utc)
        count_stmt = count_stmt.where(date_col >= start_date_utc)
    if end_date_utc:
        date_col = func.coalesce(Observation.timestamp_utc, Observation.created_at)
        stmt = stmt.where(date_col <= end_date_utc)
        count_stmt = count_stmt.where(date_col <= end_date_utc)

    total = db.scalar(count_stmt) or 0
    stmt = (
        stmt.order_by(Observation.created_at.desc(), Observation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(db.scalars(stmt).all())
    has_more = (offset + len(items)) < total

    return ObservationListResponse(
        items=[ObservationRead.model_validate(o) for o in items],
        total=total,
        total_items=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.get(
    "/api/v1/cases/{case_id}/observations/{observation_id}",
    response_model=ObservationRead,
    status_code=status.HTTP_200_OK,
    summary="Consultation détaillée d'une observation",
    description="Retourne les détails et le contenu normalisé d'une observation spécifique.",
)
def get_observation(
    case_id: uuid.UUID,
    observation_id: uuid.UUID,
    _case: Annotated[Case, Depends(verify_case_access)],
    db: Annotated[Session, Depends(get_db)],
) -> ObservationRead:
    """Retrieve a single observation by ID."""
    obs = db.scalar(
        select(Observation).where(
            Observation.id == observation_id,
            Observation.case_id == case_id,
        )
    )
    if obs is None:
        raise ObservationNotFoundException()
    return ObservationRead.model_validate(obs)


@router.get(
    "/api/v1/gateway/tools",
    response_model=list[ToolMetadataResponse],
    status_code=status.HTTP_200_OK,
    summary="Liste des outils forensiques enregistrés",
    description="Retourne les métadonnées et schémas des outils disponibles dans la Gateway.",
)
def list_registered_tools(
    _current_user: Annotated[User, Depends(get_current_user)],
    registry: Annotated[ToolRegistry, Depends(get_tool_registry)],
) -> list[ToolMetadataResponse]:
    """List metadata for all currently registered forensic tools."""
    tools = registry.list_tools()
    return [
        ToolMetadataResponse(
            name=t.name,
            version=t.version,
            description=t.description,
            timeout_seconds=t.timeout_seconds,
            parameters_schema=t.parameters_schema.model_json_schema()
            if t.parameters_schema
            else {},
        )
        for t in tools
    ]
