"""Paquet IRYX Reporting (Story 8.1 et suivantes).

Expose la pseudonymisation, le compilateur scellé, l'agent Rapporteur et le
service de génération comme points d'entrée stables pour l'orchestrateur.
"""

from iryx.reporting.compiler import (
    CompiledReport,
    ReportCompiler,
    compile_report,
    render_json,
    render_markdown,
    sha256_text,
)
from iryx.reporting.models import LowercaseHex64Check, Report
from iryx.reporting.pseudonymizer import (
    SUPPORTED_ENTITY_TYPES,
    CasePseudonymStore,
    DeterministicPseudonymizer,
    PseudonymStoreError,
)
from iryx.reporting.rapporteur_agent import RapporteurAgent
from iryx.reporting.schemas import (
    CANONICAL_SECTION_KEYS,
    CANONICAL_SECTION_TITLES,
    DetectedEntityInfo,
    PseudonymizeRequest,
    PseudonymizeResult,
    ReportContent,
    ReportFormat,
    ReportOut,
    ReportSection,
    ReportStatus,
)
from iryx.reporting.services import ReportService

__all__ = [
    "CANONICAL_SECTION_KEYS",
    "CANONICAL_SECTION_TITLES",
    "CasePseudonymStore",
    "CompiledReport",
    "DetectedEntityInfo",
    "DeterministicPseudonymizer",
    "LowercaseHex64Check",
    "PseudonymizeRequest",
    "PseudonymizeResult",
    "PseudonymStoreError",
    "RapporteurAgent",
    "Report",
    "ReportCompiler",
    "ReportContent",
    "ReportFormat",
    "ReportOut",
    "ReportSection",
    "ReportService",
    "ReportStatus",
    "SUPPORTED_ENTITY_TYPES",
    "compile_report",
    "render_json",
    "render_markdown",
    "sha256_text",
]
