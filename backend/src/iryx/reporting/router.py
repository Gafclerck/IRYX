"""IRYX Reporting API router for sealed report consultation and download (Story 8.4)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from iryx.api.dependencies import get_db
from iryx.auth.dependencies import get_current_user
from iryx.auth.models import User
from iryx.cases.dependencies import verify_case_access
from iryx.cases.models import Case
from iryx.core.exceptions import ReportNotFoundException
from iryx.reporting.schemas import ReportFormat, ReportListResponse
from iryx.reporting.services import ReportService, _safe_uuid

router = APIRouter(tags=["Reports"])

_REPORT_MIME_TYPES: dict[str, str] = {
    ReportFormat.MARKDOWN.value: "text/markdown",
    ReportFormat.JSON.value: "application/json",
}


def _verified_case(
    case_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Case:
    """Parse the raw case UUID, then delegate tenant checks to verify_case_access."""
    return verify_case_access(
        case_id=_safe_uuid(case_id, "case_id"),
        current_user=current_user,
        db=db,
    )


@router.get(
    "/api/v1/cases/{case_id}/reports",
    response_model=ReportListResponse,
    status_code=status.HTTP_200_OK,
    summary="Liste paginée des rapports scellés d'un dossier",
    description=(
        "Retourne les rapports validés du dossier, triés de façon déterministe. "
        "limit par défaut à 50 (max 100) et offset par défaut à 0."
    ),
)
def list_reports(
    case_id: str,
    _case: Annotated[Case, Depends(_verified_case)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    format: Annotated[
        str | None,
        Query(description="Filtre de format scellé : markdown ou json."),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Nombre maximum de rapports par page."),
    ] = 50,
    offset: Annotated[int, Query(ge=0, description="Index de départ de pagination.")] = 0,
) -> ReportListResponse:
    """List only validated sealed reports belonging to the authorized case."""
    parsed_case_id = _safe_uuid(case_id, "case_id")
    service = ReportService(db)
    rows = service.list_reports(
        case_id=parsed_case_id,
        user_id=current_user.id,
        format=format,
        limit=limit,
        offset=offset,
    )
    total = service.count_reports(
        case_id=parsed_case_id,
        user_id=current_user.id,
        format=format,
    )
    return ReportListResponse(
        items=[ReportService.to_out(row) for row in rows],
        total=total,
        total_items=total,
        limit=limit,
        offset=offset,
        has_more=bool(rows) and (offset + len(rows)) < total,
    )


@router.get(
    "/api/v1/cases/{case_id}/reports/{report_id}/download",
    response_class=Response,
    status_code=status.HTTP_200_OK,
    summary="Téléchargement d'un rapport scellé",
    description=(
        "Sert les octets exactement persistés du rapport validé avec l'en-tête "
        "X-Report-SHA256 et un Content-Type conforme au format scellé."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "Contenu scellé du rapport validé.",
            "content": {
                "text/markdown": {"schema": {"type": "string"}},
                "application/json": {"schema": {"type": "string"}},
            },
            "headers": {
                "X-Report-SHA256": {
                    "description": "Empreinte SHA-256 du contenu scellé servi.",
                    "schema": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                }
            },
        }
    },
)
def download_report(
    case_id: str,
    report_id: str,
    _case: Annotated[Case, Depends(_verified_case)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Download a validated report without recompiling or mutating it."""
    parsed_case_id = _safe_uuid(case_id, "case_id")
    parsed_report_id = _safe_uuid(report_id, "report_id")
    report = ReportService(db).get_report(
        case_id=parsed_case_id,
        report_id=parsed_report_id,
        user_id=current_user.id,
    )
    try:
        media_type = _REPORT_MIME_TYPES[ReportFormat(str(report.format)).value]
    except (ValueError, KeyError) as exc:
        raise ReportNotFoundException() from exc

    return Response(
        content=report.content.encode("utf-8"),
        headers={
            "Content-Type": media_type,
            "X-Report-SHA256": report.sha256,
        },
    )
