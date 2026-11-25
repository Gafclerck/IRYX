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
    "CorrelationGroupOut",
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
    "TimelineCorrelationsResponse",
    "TimelineEventOut",
    "TimelineFactBase",
    "TimelineFilterParams",
    "TimelineFindingRef",
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


class TimelineFindingRef(BaseModel):
    """Reference summary of a validated finding superimposed onto timeline events."""

    id: uuid.UUID = Field(..., description="Identifiant unique du constat validé.")
    title: str = Field(..., description="Intitulé concis du constat.")
    severity: FindingSeverity = Field(..., description="Niveau de sévérité du constat.")
    confidence: FindingConfidence = Field(
        default=FindingConfidence.MEDIUM,
        description="Niveau de confiance du constat.",
    )
    finding_type: FindingType = Field(
        default=FindingType.FACT,
        description="Type de constat ('fact', 'inference', 'hypothesis').",
    )

    model_config = ConfigDict(from_attributes=True)


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
    findings: list[TimelineFindingRef] = Field(
        default_factory=list,
        description="Findings validés superposés à cet événement source.",
    )
    correlation_marker: str | None = Field(
        default=None,
        description="Marqueur visuel de corrélation partagé (ex: 'corr-{finding_id}').",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Identifiant unique de corrélation (alias de correlation_marker).",
    )
    correlation_markers: list[str] = Field(
        default_factory=list,
        description="Liste de tous les marqueurs visuels de corrélation associés.",
    )
    is_correlated: bool = Field(
        default=False,
        description="Indicateur d'appartenance à un groupe de corrélation multi-sources.",
    )

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def sync_correlation_fields(self) -> "TimelineFactBase":
        """Synchronize correlation_marker, correlation_id, and correlation_markers."""
        if self.correlation_marker and not self.correlation_id:
            self.correlation_id = self.correlation_marker
        elif self.correlation_id and not self.correlation_marker:
            self.correlation_marker = self.correlation_id

        if self.correlation_marker and not self.correlation_markers:
            self.correlation_markers = [self.correlation_marker]
        elif self.correlation_markers and not self.correlation_marker:
            self.correlation_marker = self.correlation_markers[0]
            self.correlation_id = self.correlation_markers[0]

        return self


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
    is_correlated: bool | None = Field(
        default=None,
        description="Filtrer uniquement les événements corrélés (True/False).",
    )
    correlated_only: bool | None = Field(
        default=None,
        description="Alias pour is_correlated=True.",
    )
    correlation_marker: str | None = Field(
        default=None,
        description="Filtrer par marqueur visuel de corrélation (ex: 'corr-{finding_id}').",
    )
    finding_id: uuid.UUID | None = Field(
        default=None,
        description="Filtrer les événements associés à un constat spécifique.",
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
        if self.correlated_only is not None and self.is_correlated is None:
            self.is_correlated = self.correlated_only

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


class CorrelationGroupOut(BaseModel):
    """Group of timeline events correlated across multiple sources or tools.

    Formed by a validated finding linking observations from distinct tools or sources.
    """

    correlation_marker: str = Field(
        ...,
        description="Marqueur visuel de corrélation partagé (ex: 'corr-{finding_id}').",
    )
    correlation_id: str = Field(
        ...,
        description="Identifiant unique de corrélation.",
    )
    finding_id: uuid.UUID = Field(
        ...,
        description="Identifiant unique du constat validé fédérateur.",
    )
    finding_title: str = Field(
        ...,
        description="Intitulé du constat validé.",
    )
    finding: TimelineFindingRef = Field(
        ...,
        description="Référence complète au constat validé.",
    )
    events: list[TimelineEventOut] = Field(
        default_factory=list,
        description="Événements horodatés participant à la corrélation multi-sources.",
    )
    undated_events: list[UndatedFactOut] = Field(
        default_factory=list,
        description="Faits non horodatés associés au constat.",
    )
    tools: list[str] = Field(
        default_factory=list,
        description="Outils forensiques distincts impliqués dans la corrélation.",
    )
    sources: list[uuid.UUID] = Field(
        default_factory=list,
        description="Identifiants des preuves scellées sources distinctes.",
    )
    evidence_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Alias de sources pour compatibilité des clients.",
    )
    total_events: int = Field(
        default=0,
        ge=0,
        description="Nombre total d'événements horodatés corrélés.",
    )
    events_count: int = Field(
        default=0,
        ge=0,
        description="Alias de total_events.",
    )
    total_undated: int = Field(
        default=0,
        ge=0,
        description="Nombre total de faits non horodatés associés au constat.",
    )
    start_time: datetime | None = Field(
        default=None,
        description="Horodatage UTC du premier événement du groupe.",
    )
    end_time: datetime | None = Field(
        default=None,
        description="Horodatage UTC du dernier événement du groupe.",
    )
    time_span_seconds: float = Field(
        default=0.0,
        ge=0.0,
        description="Durée temporelle en secondes couverte par le groupe.",
    )
    is_multi_tool: bool = Field(
        default=False,
        description="Indique si le groupe associe au moins deux outils distincts.",
    )
    is_multi_source: bool = Field(
        default=False,
        description="Indique si le groupe associe au moins deux preuves/sources distinctes.",
    )

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def sync_group_fields(cls, data: Any) -> Any:
        """Synchronize group aliases."""
        if isinstance(data, dict):
            if "total_events" in data and "events_count" not in data:
                data["events_count"] = data["total_events"]
            elif "events_count" in data and "total_events" not in data:
                data["total_events"] = data["events_count"]
            elif "events" in data and "total_events" not in data:
                cnt = len(data["events"])
                data["total_events"] = cnt
                data["events_count"] = cnt

            if (
                "total_undated" not in data
                and "undated_events" in data
                and isinstance(data["undated_events"], list)
            ):
                data["total_undated"] = len(data["undated_events"])

            if "sources" in data and "evidence_ids" not in data:
                data["evidence_ids"] = data["sources"]
            elif "evidence_ids" in data and "sources" not in data:
                data["sources"] = data["evidence_ids"]

            if "correlation_marker" in data and "correlation_id" not in data:
                data["correlation_id"] = data["correlation_marker"]
            elif "correlation_id" in data and "correlation_marker" not in data:
                data["correlation_marker"] = data["correlation_id"]

        elif hasattr(data, "__dict__"):
            tot = getattr(data, "total_events", None)
            cnt = getattr(data, "events_count", None)
            if tot is not None and cnt is None:
                data.events_count = tot
            elif cnt is not None and tot is None:
                data.total_events = cnt

            undated = getattr(data, "undated_events", None)
            if undated is not None and getattr(data, "total_undated", None) is None:
                data.total_undated = len(undated)

            src = getattr(data, "sources", None)
            ev = getattr(data, "evidence_ids", None)
            if src is not None and ev is None:
                data.evidence_ids = src
            elif ev is not None and src is None:
                data.sources = ev

            m = getattr(data, "correlation_marker", None)
            cid = getattr(data, "correlation_id", None)
            if m is not None and cid is None:
                data.correlation_id = m
            elif cid is not None and m is None:
                data.correlation_marker = cid

        return data


class TimelineCorrelationsResponse(BaseModel):
    """Response containing structured multi-source correlation groups for a case."""

    case_id: uuid.UUID = Field(
        ...,
        description="Identifiant du dossier d'investigation.",
    )
    correlations: list[CorrelationGroupOut] = Field(
        default_factory=list,
        description="Liste structurée des groupes de corrélations multi-sources.",
    )
    groups: list[CorrelationGroupOut] = Field(
        default_factory=list,
        description="Alias de correlations pour compatibilité.",
    )
    items: list[CorrelationGroupOut] = Field(
        default_factory=list,
        description="Alias standardisé de collection pour clients API.",
    )
    total: int = Field(
        default=0,
        ge=0,
        description="Nombre total de groupes de corrélation.",
    )
    total_groups: int = Field(
        default=0,
        ge=0,
        description="Alias de total.",
    )

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def sync_correlations_and_totals(cls, data: Any) -> Any:
        """Synchronize list aliases and total counters."""
        if isinstance(data, dict):
            corr = data.get("correlations")
            grp = data.get("groups")
            items = data.get("items")

            target_list = corr if corr is not None else (grp if grp is not None else items)
            if target_list is not None:
                data.setdefault("correlations", target_list)
                data.setdefault("groups", target_list)
                data.setdefault("items", target_list)

            tot = data.get("total")
            tot_grp = data.get("total_groups")
            if tot is not None and tot_grp is None:
                data["total_groups"] = tot
            elif tot_grp is not None and tot is None:
                data["total"] = tot_grp
            elif tot is None and tot_grp is None and target_list is not None:
                data["total"] = len(target_list)
                data["total_groups"] = len(target_list)

        elif hasattr(data, "__dict__"):
            corr = getattr(data, "correlations", None)
            grp = getattr(data, "groups", None)
            items = getattr(data, "items", None)
            target_list = corr if corr is not None else (grp if grp is not None else items)
            if target_list is not None:
                if not hasattr(data, "correlations") or getattr(data, "correlations", None) is None:
                    data.correlations = target_list
                if not hasattr(data, "groups") or getattr(data, "groups", None) is None:
                    data.groups = target_list
                if not hasattr(data, "items") or getattr(data, "items", None) is None:
                    data.items = target_list

            tot = getattr(data, "total", None)
            tot_grp = getattr(data, "total_groups", None)
            if tot is not None and tot_grp is None:
                data.total_groups = tot
            elif tot_grp is not None and tot is None:
                data.total = tot_grp

        return data
