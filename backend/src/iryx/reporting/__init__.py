"""Paquet IRYX Reporting (Story 8.1 et suivantes).

Expose le service de pseudonymisation déterministe comme point d'entrée stable
utilisé par l'aperçu H3, l'agent rapporteur et les routes de rapport.
"""

from iryx.reporting.pseudonymizer import (
    SUPPORTED_ENTITY_TYPES,
    CasePseudonymStore,
    DeterministicPseudonymizer,
    PseudonymStoreError,
)
from iryx.reporting.schemas import (
    DetectedEntityInfo,
    PseudonymizeRequest,
    PseudonymizeResult,
)

__all__ = [
    "CasePseudonymStore",
    "DetectedEntityInfo",
    "DeterministicPseudonymizer",
    "PseudonymizeRequest",
    "PseudonymizeResult",
    "PseudonymStoreError",
    "SUPPORTED_ENTITY_TYPES",
]
