"""IRYX Analytics and Finding Pydantic Schemas."""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from iryx.analytics.models import (
    FindingConfidence,
    FindingSeverity,
    FindingStatus,
    FindingType,
)

__all__ = [
    "FindingBase",
    "FindingConfidence",
    "FindingCreate",
    "FindingListResponse",
    "FindingOut",
    "FindingReview",
    "FindingSeverity",
    "FindingStatus",
    "FindingType",
    "FindingUpdate",
    "TimelineEventOut",
    "TimelineFactBase",
    "TimelineFilterParams",
    "TimelineListResponse",
    "TimelineProjectionResponse",
    "UndatedFactOut",
]


class FindingBase(BaseModel):
    """Base schema for investigation findings."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Intitulé concis du constat d'investigation.",
    )
    severity: FindingSeverity = Field(
        ...,
        description="Niveau de sévérité ('low', 'medium', 'high', 'critical').",
    )
    confidence: FindingConfidence = Field(
        default=FindingConfidence.MEDIUM,
        description="Niveau de confiance ('low', 'medium', 'high').",
    )
    finding_type: FindingType = Field(
        default=FindingType.FACT,
        description="Classification ('fact', 'inference', 'hypothesis').",
    )
    observation_refs: list[uuid.UUID] = Field(
        default_factory=list,
        description="Identifiants d'observations justificatives réelles.",
    )
    tool_execution_refs: list[uuid.UUID] = Field(
        default_factory=list,
        description="Identifiants d'exécutions d'outils associées.",
    )

    @field_validator("title")
    @classmethod
    def validate_title_non_empty(cls, value: str) -> str:
        """Ensure title contains non-whitespace characters and is within bounds."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Le titre du constat ne peut pas être vide.")
        if len(cleaned) > 255:
            raise ValueError("Le titre du constat ne peut pas dépasser 255 caractères.")
        return cleaned


class FindingCreate(FindingBase):
    """Schema for proposing or registering a new finding."""

    pass


class FindingUpdate(BaseModel):
    """Schema for updating an existing technical finding."""

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Nouvel intitulé concis du constat.",
    )
    severity: FindingSeverity | None = Field(
        default=None,
        description="Nouveau niveau de sévérité.",
    )
    confidence: FindingConfidence | None = Field(
        default=None,
        description="Nouveau niveau de confiance.",
    )
    finding_type: FindingType | None = Field(
        default=None,
        description="Nouveau type de constat.",
    )
    status: FindingStatus | None = Field(
        default=None,
        description="Nouveau statut opérationnel ('proposed', 'validated', 'rejected').",
    )
    observation_refs: list[uuid.UUID] | None = Field(
        default=None,
        description="Nouvelle liste d'identifiants d'observations.",
    )
    tool_execution_refs: list[uuid.UUID] | None = Field(
        default=None,
        description="Nouvelle liste d'identifiants d'exécutions d'outils.",
    )

    @field_validator("title")
    @classmethod
    def validate_title_optional(cls, value: str | None) -> str | None:
        """Ensure updated title is non-empty if supplied."""
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Le titre du constat ne peut pas être vide.")
        if len(cleaned) > 255:
            raise ValueError("Le titre du constat ne peut pas dépasser 255 caractères.")
        return cleaned


class FindingReview(BaseModel):
    """Schema for analyst human-in-the-loop review at Gate H2."""

    action: Literal["validate", "reject"] = Field(
        ...,
        description="Décision de revue humaine : 'validate' ou 'reject'.",
    )
    severity: FindingSeverity | None = Field(
        default=None,
        description="Ajustement optionnel du niveau de sévérité.",
    )
    confidence: FindingConfidence | None = Field(
        default=None,
        description="Ajustement optionnel du niveau de confiance.",
    )


class FindingOut(FindingBase):
    """Public representation of an investigation finding."""

    id: uuid.UUID
    case_id: uuid.UUID
    status: FindingStatus
    created_by: uuid.UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FindingListResponse(BaseModel):
    """Paginated collection of investigation findings."""

    items: list[FindingOut]
    total: int = Field(..., ge=0)
    total_items: int = Field(default=0, ge=0)
    limit: int = Field(..., ge=1, le=100)
    offset: int = Field(..., ge=0)
    has_more: bool

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def populate_total_items(cls, data: Any) -> Any:
        """Ensure total_items is populated from total when missing."""
        if isinstance(data, dict) and "total_items" not in data and "total" in data:
            data["total_items"] = data["total"]
        elif (
            hasattr(data, "__dict__")
            and hasattr(data, "total")
            and not getattr(data, "total_items", None)
        ):
            data.total_items = data.total
        return data


class TimelineFactBase(BaseModel):
    """Base schema for timeline technical facts extracted from observations."""

    observation_id: uuid.UUID = Field(
        ...,
        description="Identifiant unique de l'observation source.",
    )
    tool_name: str = Field(
        ...,
        description="Nom de l'outil générateur de l'observation.",
    )
    tool_execution_id: uuid.UUID | None = Field(
        default=None,
        description="Identifiant de l'exécution d'outil source.",
    )
    evidence_id: uuid.UUID | None = Field(
        default=None,
        description="Identifiant de la preuve scellée source.",
    )
    evidence_name: str | None = Field(
        default=None,
        description="Nom original du fichier de preuve scellé.",
    )
    summary: str = Field(
        ...,
        description="Résumé textuel synthétique du fait technique.",
    )
    source_location: str | None = Field(
        default=None,
        description="Emplacement de l'artefact source.",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Contenu technique normalisé intégral (normalized_content).",
    )

    model_config = ConfigDict(from_attributes=True)


class TimelineEventOut(TimelineFactBase):
    """Public representation of a dated timeline event ordered in UTC."""

    timestamp_utc: datetime = Field(
        ...,
        description="Horodatage UTC strict de l'événement.",
    )

    @field_validator("timestamp_utc", mode="after")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        """Ensure datetime has UTC timezone."""
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)


class UndatedFactOut(TimelineFactBase):
    """Public representation of an undated technical fact."""

    timestamp_utc: datetime | None = Field(
        default=None,
        description="Horodatage nul pour les faits non horodatés.",
    )

    @field_validator("timestamp_utc")
    @classmethod
    def validate_timestamp_is_none(cls, v: Any) -> None:
        """Enforce that undated facts must not have a timestamp."""
        if v is not None:
            raise ValueError("UndatedFactOut must have timestamp_utc set to None.")
        return None


class TimelineProjectionResponse(BaseModel):
    """Deterministic timeline projection response partitioned into dated and undated events."""

    case_id: uuid.UUID | None = Field(
        default=None,
        description="Identifiant du dossier d'investigation.",
    )
    events: list[TimelineEventOut] = Field(
        default_factory=list,
        description="Événements techniques horodatés, ordonnés en UTC croissant.",
    )
    undated_events: list[UndatedFactOut] = Field(
        default_factory=list,
        description="Faits techniques sans horodatage extractible.",
    )
    total_events: int = Field(
        default=0,
        ge=0,
        description="Nombre total d'événements horodatés.",
    )
    total_undated: int = Field(
        default=0,
        ge=0,
        description="Nombre total de faits non horodatés.",
    )

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def populate_totals(cls, data: Any) -> Any:
        """Ensure total counters are populated when omitted or None."""
        if isinstance(data, dict):
            if (
                data.get("total_events") is None
                and "events" in data
                and isinstance(data["events"], list)
            ):
                data["total_events"] = len(data["events"])
            if (
                data.get("total_undated") is None
                and "undated_events" in data
                and isinstance(data["undated_events"], list)
            ):
                data["total_undated"] = len(data["undated_events"])
        return data


class TimelineFilterParams(BaseModel):
    """Query parameters schema for timeline filtering and pagination (Story 7.2, NFR-PERF-07)."""

    limit: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Nombre maximum d'événements par page (défaut 50, borné entre 1 et 100).",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Index de départ pour la pagination (>= 0).",
    )
    start_time: datetime | None = Field(
        default=None,
        description="Filtre temporel de début (format ISO-8601 UTC).",
    )
    end_time: datetime | None = Field(
        default=None,
        description="Filtre temporel de fin (format ISO-8601 UTC).",
    )
    tool_name: str | None = Field(
        default=None,
        description="Filtrer par nom de l'outil extracteur.",
    )
    evidence_id: uuid.UUID | None = Field(
        default=None,
        description="Filtrer par identifiant de la preuve source.",
    )

    model_config = ConfigDict(extra="ignore")

    @field_validator("tool_name", mode="before")
    @classmethod
    def sanitize_tool_name(cls, v: Any) -> str | None:
        """Strip empty or whitespace tool_name to None."""
        if v is None:
            return None
        if isinstance(v, str):
            cleaned = v.strip()
            return cleaned if cleaned else None
        return v

    @model_validator(mode="after")
    def validate_time_window(self) -> "TimelineFilterParams":
        """Validate that start_time <= end_time and normalize datetimes to UTC."""
        st: datetime | None = None
        et: datetime | None = None

        if self.start_time is not None:
            st = (
                self.start_time.replace(tzinfo=UTC)
                if self.start_time.tzinfo is None
                else self.start_time.astimezone(UTC)
            )
            self.start_time = st

        if self.end_time is not None:
            et = (
                self.end_time.replace(tzinfo=UTC)
                if self.end_time.tzinfo is None
                else self.end_time.astimezone(UTC)
            )
            self.end_time = et

        if st is not None and et is not None and st > et:
            raise ValueError("start_time must be before end_time")

        return self


class TimelineListResponse(BaseModel):
    """Paginated collection of chronological timeline events (Story 7.2, NFR-PERF-07)."""

    items: list[TimelineEventOut] = Field(
        default_factory=list,
        description="Événements chronologiques de la timeline pour la page courante.",
    )
    events: list[TimelineEventOut] = Field(
        default_factory=list,
        description="Alias d'items pour compatibilité et flexibilité des clients d'API.",
    )
    total: int = Field(
        default=0,
        ge=0,
        description="Nombre total d'événements correspondant aux filtres.",
    )
    total_items: int = Field(
        default=0,
        ge=0,
        description="Alias standardisé de total.",
    )
    limit: int = Field(..., ge=1, le=100, description="Nombre d'éléments par page.")
    offset: int = Field(..., ge=0, description="Décalage pour pagination.")
    has_more: bool = Field(..., description="Vrai si des événements supplémentaires existent.")

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def sync_items_and_totals(cls, data: Any) -> Any:
        """Synchronize items/events and total/total_items symmetrically."""
        if isinstance(data, dict):
            items = data.get("items")
            events = data.get("events")

            if items and not events:
                data["events"] = items
            elif events and not items:
                data["items"] = events
            elif "items" in data and "events" not in data:
                data["events"] = data["items"]
            elif "events" in data and "items" not in data:
                data["items"] = data["events"]

            # Sync total and total_items
            total = data.get("total")
            total_items = data.get("total_items")
            if total is not None and total_items is None:
                data["total_items"] = total
            elif total_items is not None and total is None:
                data["total"] = total_items

        elif hasattr(data, "__dict__"):
            items = getattr(data, "items", None)
            events = getattr(data, "events", None)
            if items and not events:
                data.events = items
            elif events and not items:
                data.items = events
            elif items is not None and events is None:
                data.events = items
            elif events is not None and items is None:
                data.items = events

            total = getattr(data, "total", None)
            total_items = getattr(data, "total_items", None)
            if total is not None and total_items is None:
                data.total_items = total
            elif total_items is not None and total is None:
                data.total = total_items

        return data
