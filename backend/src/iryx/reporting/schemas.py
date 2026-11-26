"""IRYX Reporting Pydantic v2 Schemas.

Structures exchanged by the deterministic pseudonymisation service (Story 8.1).
No schema ever exposes the original sensitive value: only the detected span,
the entity type, the confidence score and the assigned pseudonym are public.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

__all__ = [
    "CANONICAL_SECTION_KEYS",
    "CANONICAL_SECTION_TITLES",
    "DetectedEntityInfo",
    "PseudonymizeRequest",
    "PseudonymizeResult",
    "ReportContent",
    "ReportFormat",
    "ReportListResponse",
    "ReportOut",
    "ReportSection",
    "ReportStatus",
]


class ReportFormat(StrEnum):
    """Supported sealed report serialization formats."""

    MARKDOWN = "markdown"
    JSON = "json"


class ReportStatus(StrEnum):
    """Lifecycle states of a sealed report row."""

    DRAFT = "draft"
    VALIDATED = "validated"
    EXPORTED = "exported"


CANONICAL_SECTION_TITLES: tuple[str, ...] = (
    "Résumé managérial",
    "Périmètre",
    "Méthodologie",
    "Chaîne des preuves",
    "Observations",
    "Constats validés",
    "Chronologie",
    "Limites",
)

CANONICAL_SECTION_KEYS: tuple[str, ...] = (
    "resume_managerial",
    "perimetre",
    "methodologie",
    "chaine_des_preuves",
    "observations",
    "constats_valides",
    "chronologie",
    "limites",
)

_SECTION_ALIASES: dict[str, tuple[str, str]] = {
    "resume_managerial": ("Résumé managérial", "resume_managerial"),
    "résumé managérial": ("Résumé managérial", "resume_managerial"),
    "résumé": ("Résumé managérial", "resume_managerial"),
    "summary": ("Résumé managérial", "resume_managerial"),
    "perimetre": ("Périmètre", "perimetre"),
    "périmètre": ("Périmètre", "perimetre"),
    "scope": ("Périmètre", "perimetre"),
    "methodologie": ("Méthodologie", "methodologie"),
    "méthodologie": ("Méthodologie", "methodologie"),
    "methodology": ("Méthodologie", "methodologie"),
    "chaine_des_preuves": ("Chaîne des preuves", "chaine_des_preuves"),
    "chaîne des preuves": ("Chaîne des preuves", "chaine_des_preuves"),
    "chaine des preuves": ("Chaîne des preuves", "chaine_des_preuves"),
    "chain_of_custody": ("Chaîne des preuves", "chaine_des_preuves"),
    "observations": ("Observations", "observations"),
    "constats_valides": ("Constats validés", "constats_valides"),
    "constats validés": ("Constats validés", "constats_valides"),
    "findings": ("Constats validés", "constats_valides"),
    "chronologie": ("Chronologie", "chronologie"),
    "timeline": ("Chronologie", "chronologie"),
    "limites": ("Limites", "limites"),
    "limits": ("Limites", "limites"),
}


def _normalize_section_label(value: str) -> str:
    """Normalize a section label for alias matching."""
    return " ".join(value.strip().lower().replace("_", " ").split())


class ReportSection(BaseModel):
    """One canonical section of a sealed incident report."""

    key: str = Field(..., min_length=1, description="Identifiant stable de la section.")
    title: str = Field(..., min_length=1, description="Titre canonique affiché dans le rapport.")
    content: str = Field(default="", description="Corps de la section.")
    order: int = Field(default=0, description="Ordre de rendu déterministe.")

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def normalize_canonical_section(cls, data: Any) -> Any:
        """Resolve known section aliases to the canonical key/title pair."""
        if not isinstance(data, dict):
            return data
        updated = dict(data)
        raw_key = str(updated.get("key") or "").strip()
        raw_title = str(updated.get("title") or "").strip()
        label = raw_title or raw_key
        canonical = _SECTION_ALIASES.get(_normalize_section_label(label))
        key_canonical = _SECTION_ALIASES.get(_normalize_section_label(raw_key)) if raw_key else None
        title_canonical = (
            _SECTION_ALIASES.get(_normalize_section_label(raw_title)) if raw_title else None
        )
        if (
            key_canonical is not None
            and title_canonical is not None
            and key_canonical != title_canonical
        ):
            raise ValueError("Le titre de section ne correspond pas à sa clé canonique.")
        if canonical is not None:
            updated["title"], updated["key"] = canonical
        elif not updated.get("key") and updated.get("title"):
            updated["key"] = _normalize_section_label(raw_title).replace(" ", "_")
        elif not updated.get("title") and updated.get("key"):
            updated["title"] = raw_key.replace("_", " ").capitalize()
        return updated


class ReportContent(BaseModel):
    """Canonical, serializable structure compiled into Markdown and JSON."""

    case_id: uuid.UUID
    sections: list[ReportSection] = Field(..., min_length=8, max_length=8)
    generation_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    version: int = Field(default=1, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("case_id", "generation_id", "run_id", mode="before")
    @classmethod
    def coerce_uuid(cls, value: Any) -> Any:
        """Accept UUID instances or their canonical string representation."""
        if value is None or isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str):
            return uuid.UUID(value)
        return value

    @field_validator("created_at", mode="before")
    @classmethod
    def normalize_created_at(cls, value: Any) -> Any:
        """Normalize naive datetimes to UTC for deterministic serialization."""
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    @model_validator(mode="after")
    def validate_canonical_sections(self) -> "ReportContent":
        """Require each canonical key/title pair exactly once."""
        keys = [section.key for section in self.sections]
        titles = [section.title for section in self.sections]
        if set(keys) != set(CANONICAL_SECTION_KEYS) or len(set(keys)) != 8:
            raise ValueError("Le rapport doit contenir exactement les huit sections canoniques.")
        if len(set(titles)) != 8:
            raise ValueError("Les titres de sections doivent être uniques.")
        expected = set(zip(CANONICAL_SECTION_KEYS, CANONICAL_SECTION_TITLES, strict=True))
        if {(section.key, section.title) for section in self.sections} != expected:
            raise ValueError("Chaque section doit utiliser la paire clé/titre canonique.")
        return self


class ReportOut(BaseModel):
    """Public representation of a persisted report row."""

    id: uuid.UUID
    case_id: uuid.UUID
    generation_id: uuid.UUID
    format: ReportFormat
    version: int
    status: ReportStatus
    sha256: str = Field(..., min_length=64, max_length=64)
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    @field_validator("generation_id", mode="before")
    @classmethod
    def coerce_generation_id(cls, value: Any) -> Any:
        """Accept the canonical string representation stored in the database."""
        if isinstance(value, str):
            return uuid.UUID(value)
        return value

    @field_validator("format", "status", mode="before")
    @classmethod
    def validate_enum_value(cls, value: Any, info: ValidationInfo) -> Any:
        """Reject unknown format or status values explicitly."""
        enum_type = ReportFormat if info.field_name == "format" else ReportStatus
        return enum_type(value)


class ReportListResponse(BaseModel):
    """Paginated collection of sealed reports for one investigation case."""

    items: list[ReportOut]
    total: int = Field(..., ge=0)
    total_items: int = Field(default=0, ge=0)
    limit: int = Field(..., ge=1, le=100)
    offset: int = Field(..., ge=0)
    has_more: bool

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def populate_total_items(cls, data: Any) -> Any:
        """Ensure total_items mirrors total when the caller omits it."""
        if isinstance(data, dict) and data.get("total_items") is None and "total" in data:
            updated = dict(data)
            updated["total_items"] = updated["total"]
            return updated
        return data


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
