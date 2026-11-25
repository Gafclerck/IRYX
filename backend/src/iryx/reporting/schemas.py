"""IRYX Reporting Pydantic v2 Schemas.

Structures exchanged by the deterministic pseudonymisation service (Story 8.1).
No schema ever exposes the original sensitive value: only the detected span,
the entity type, the confidence score and the assigned pseudonym are public.
"""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "DetectedEntityInfo",
    "PseudonymizeRequest",
    "PseudonymizeResult",
]


class PseudonymizeRequest(BaseModel):
    """Request to pseudonymize a text within a given investigation case."""

    case_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Identifiant du dossier d'investigation (UUID ou identifiant logique).",
    )
    text: str = Field(
        ...,
        description="Texte brut à pseudonymiser avant tout transfert externe.",
    )
    entities: list[str] | None = Field(
        default=None,
        description=(
            "Liste optionnelle des types d'entités à rechercher "
            "(IP_ADDRESS, HOSTNAME, USER_ACCOUNT, EMAIL_ADDRESS). "
            "Tous les types supportés sont analysés si la valeur est nulle."
        ),
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("case_id", mode="before")
    @classmethod
    def normalize_case_id(cls, value: Any) -> str:
        """Accept UUID instances or strings and normalize them to a stable string."""
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("Le case_id ne peut pas être vide.")
            return cleaned
        raise ValueError("Le case_id doit être un UUID ou une chaîne non vide.")

    @field_validator("entities", mode="after")
    @classmethod
    def normalize_entities(cls, value: list[str] | None) -> list[str] | None:
        """Normalize requested entity types to upper-case and remove duplicates."""
        if value is None:
            return None
        normalized: list[str] = []
        for entity in value:
            if not isinstance(entity, str):
                raise ValueError("Chaque type d'entité doit être une chaîne.")
            cleaned = entity.strip().upper()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized or None


class DetectedEntityInfo(BaseModel):
    """Non-sensitive metadata describing a detected sensitive entity.

    The original value is deliberately absent: exposing it would defeat the
    purpose of pseudonymisation and could leak into logs or external calls.
    """

    entity_type: str = Field(
        ...,
        min_length=1,
        description="Type d'entité Presidio détecté (ex: IP_ADDRESS).",
    )
    start: int = Field(..., ge=0, description="Index de début dans le texte d'origine.")
    end: int = Field(..., ge=0, description="Index de fin (exclu) dans le texte d'origine.")
    score: float = Field(..., ge=0.0, le=1.0, description="Score de confiance Presidio.")
    pseudonym: str = Field(
        ...,
        min_length=1,
        description="Pseudonyme déterministe attribué dans le dossier.",
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_span(self) -> "DetectedEntityInfo":
        """Ensure the detected span is non-empty and properly ordered."""
        if self.end <= self.start:
            raise ValueError("La fin de l'entité doit être strictement supérieure au début.")
        return self


class PseudonymizeResult(BaseModel):
    """Result of a deterministic pseudonymisation operation."""

    case_id: str = Field(
        ...,
        min_length=1,
        description="Identifiant du dossier dans lequel les pseudonymes ont été attribués.",
    )
    pseudonymized_text: str = Field(
        ...,
        description="Texte pseudonymisé, structure syntaxique préservée hors entités.",
    )
    entities: list[DetectedEntityInfo] = Field(
        default_factory=list,
        description="Métadonnées des entités détectées (sans valeur d'origine).",
    )
    entity_count: int = Field(
        default=0,
        ge=0,
        description="Nombre d'entités détectées et pseudonymisées.",
    )
    has_entities: bool = Field(
        default=False,
        description="Indique si au moins une entité sensible a été détectée.",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("case_id", mode="before")
    @classmethod
    def normalize_case_id(cls, value: Any) -> str:
        """Accept UUID instances or strings and normalize them to a stable string."""
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("Le case_id ne peut pas être vide.")
            return cleaned
        raise ValueError("Le case_id doit être un UUID ou une chaîne non vide.")

    @model_validator(mode="before")
    @classmethod
    def sync_counters(cls, data: Any) -> Any:
        """Keep entity_count and has_entities consistent with the entity list."""
        if isinstance(data, dict):
            entities = data.get("entities")
            if isinstance(entities, list):
                data.setdefault("entity_count", len(entities))
                data.setdefault("has_entities", bool(entities))
        return data

    @model_validator(mode="after")
    def validate_entity_count(self) -> "PseudonymizeResult":
        """Reject inconsistent counters supplied by a caller."""
        if self.entity_count != len(self.entities):
            raise ValueError("entity_count doit correspondre au nombre d'entités détectées.")
        if self.has_entities != bool(self.entities):
            raise ValueError("has_entities doit refléter la présence d'entités détectées.")
        return self
