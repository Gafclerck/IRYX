"""Forensic Windows Event Log (EVTX) parser tool with UTC normalization."""

import contextlib
import logging
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import Evtx.Evtx as evtx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from iryx.core.config import get_settings
from iryx.core.exceptions import ValidationException
from iryx.gateway.base import BaseTool, ToolExecutionContext, ToolExecutionResult
from iryx.gateway.models import ToolExecutionStatus

logger = logging.getLogger("iryx.gateway.tools.evtx_parser")

EVTX_MAGIC = b"ElfFile\x00"


def _local_tag(tag: Any) -> str:
    """Return local XML tag name without namespace, ignoring non-string tags."""
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _parse_event_timestamp(
    time_created_str: str | None,
    fallback_dt: datetime | None = None,
) -> datetime | None:
    """Parse an event timestamp string into a timezone-aware UTC datetime."""
    if time_created_str:
        val = time_created_str.strip()
        if val:
            # 1. ISO-8601 parsing (handles Z/z, offsets, fractional seconds)
            with contextlib.suppress(Exception):
                iso_clean = val.replace("Z", "+00:00").replace("z", "+00:00")
                dt = datetime.fromisoformat(iso_clean)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=UTC)
                return dt.astimezone(UTC)

            # 2. RFC 2822 or email date parsing
            with contextlib.suppress(Exception):
                dt = parsedate_to_datetime(val)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=UTC)
                return dt.astimezone(UTC)

    if fallback_dt is not None:
        if fallback_dt.tzinfo is None:
            return fallback_dt.replace(tzinfo=UTC)
        return fallback_dt.astimezone(UTC)

    return None


class EvtxParserParameters(BaseModel):
    """Input parameters schema for EvtxParserTool."""

    evidence_id: uuid.UUID | None = Field(
        default=None,
        description="Identifiant UUID de la preuve scellée à analyser.",
    )
    file_path: str | None = Field(
        default=None,
        description="Chemin local du fichier journal EVTX à analyser.",
    )
    event_ids: list[int] | None = Field(
        default=None,
        description="Liste d'identifiants d'événements (EventID) à filtrer.",
    )
    channels: list[str] | None = Field(
        default=None,
        description="Liste de canaux (Channel) Windows à filtrer (ex: Security, System).",
    )
    start_time: datetime | None = Field(
        default=None,
        description="Date et heure de début UTC pour la fenêtre temporelle.",
    )
    end_time: datetime | None = Field(
        default=None,
        description="Date et heure de fin UTC pour la fenêtre temporelle.",
    )
    max_records: int = Field(
        default=5000,
        ge=1,
        le=50000,
        description="Nombre maximal d'enregistrements à extraire (défaut 5000, max 50000).",
    )
    search_query: str | None = Field(
        default=None,
        description="Chaîne de recherche textuelle insensible à la casse.",
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_sources_and_timestamps(self) -> "EvtxParserParameters":
        """Validate at least one source is supplied and timestamps are UTC-consistent."""
        if not self.evidence_id and not self.file_path:
            raise ValueError(
                "Au moins une source de données doit être fournie: 'evidence_id' ou 'file_path'."
            )

        if self.start_time is not None:
            if self.start_time.tzinfo is None:
                self.start_time = self.start_time.replace(tzinfo=UTC)
            else:
                self.start_time = self.start_time.astimezone(UTC)

        if self.end_time is not None:
            if self.end_time.tzinfo is None:
                self.end_time = self.end_time.replace(tzinfo=UTC)
            else:
                self.end_time = self.end_time.astimezone(UTC)

        if self.start_time and self.end_time and self.start_time > self.end_time:
            raise ValueError("Le paramètre 'start_time' doit être antérieur ou égal à 'end_time'.")

        return self


class EvtxParserTool(BaseTool):
    """Forensic Windows Event Log (EVTX) parser tool with selective filtering."""

    name: str = "parse_evtx"
    version: str = "1.0.0"
    description: str = (
        "Analyseur forensique de journaux d'événements Windows EVTX pur Python "
        "avec filtrage sélectif et normalisation UTC."
    )
    timeout_seconds: int = 180
    parameters_schema: type[BaseModel] = EvtxParserParameters

    def __init__(self) -> None:
        super().__init__(
            name=self.name,
            version=self.version,
            description=self.description,
            timeout_seconds=self.timeout_seconds,
            parameters_schema=self.parameters_schema,
        )

    async def execute(
        self,
        params: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Execute EVTX parsing logic under strict passive boundaries."""
        if not isinstance(params, EvtxParserParameters):
            try:
                params = EvtxParserParameters.model_validate(params)
            except Exception as e:
                raise ValidationException(f"Paramètres invalides pour EvtxParserTool: {e}") from e

        # 1. Resolve source file path and evidence identifier
        target_path, source_id = self._resolve_source(params, context)

        # 2. Strict file integrity and header validation
        self._validate_evtx_header(target_path)

        # 3. Parse EVTX records with fault resilience
        observations: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        total_records_read = 0
        truncated = False

        try:
            evtx_obj = evtx.Evtx(str(target_path))
            with evtx_obj as evtx_file:
                # Check FileHeader magic if available
                fh = evtx_file.get_file_header()
                if not fh.check_magic():
                    raise ValidationException(
                        f"Format EVTX non reconnu ou corrompu dès l'en-tête: '{target_path.name}'."
                    )

                for record, err in self._iter_records(evtx_file):
                    if err is not None:
                        logger.warning("Enregistrement ou chunk EVTX illisible: %s", err)
                        errors.append(
                            {"error": f"Enregistrement EVTX illisible ou corrompu: {err}"}
                        )
                        continue

                    if record is None:
                        continue

                    total_records_read += 1
                    record_offset = 0
                    with contextlib.suppress(Exception):
                        record_offset = int(record.offset())
                    fallback_record_num = None
                    fallback_dt = None

                    with contextlib.suppress(Exception):
                        fallback_record_num = record.record_num()

                    with contextlib.suppress(Exception):
                        fallback_dt = record.timestamp()

                    try:
                        xml_str = record.xml()
                    except (evtx.InvalidRecordException, evtx.ParseException, Exception) as exc:
                        logger.warning(
                            "Erreur de décodage XML de l'enregistrement EVTX "
                            "(record_id=%s, offset=%s): %s",
                            fallback_record_num,
                            record_offset,
                            exc,
                        )
                        errors.append(
                            {
                                "record_id": fallback_record_num,
                                "record_offset": record_offset,
                                "error": f"Erreur lors du décodage XML de l'enregistrement: {exc}",
                            }
                        )
                        continue

                    try:
                        parsed = self._parse_xml_record(
                            xml_str=xml_str,
                            record_offset=record_offset,
                            fallback_record_num=fallback_record_num,
                            fallback_dt=fallback_dt,
                        )
                    except (ET.ParseError, Exception) as exc:
                        logger.warning(
                            "Erreur de structure XML dans l'enregistrement EVTX "
                            "(record_id=%s, offset=%s): %s",
                            fallback_record_num,
                            record_offset,
                            exc,
                        )
                        errors.append(
                            {
                                "record_id": fallback_record_num,
                                "record_offset": record_offset,
                                "error": f"Erreur de structure XML dans l'enregistrement: {exc}",
                            }
                        )
                        continue

                    if self._matches_filters(parsed, params):
                        if len(observations) >= params.max_records:
                            truncated = True
                            break
                        observations.append(
                            {
                                "source_id": source_id,
                                "source_location": parsed["source_location"],
                                "timestamp_utc": parsed["timestamp_utc"],
                                "normalized_content": parsed["normalized_content"],
                            }
                        )
        except ValidationException:
            raise
        except Exception as exc:
            raise ValidationException(
                f"Format EVTX non reconnu ou corrompu dès l'en-tête: {exc}"
            ) from exc

        raw_output = {
            "records_count": len(observations),
            "total_records_read": total_records_read,
            "errors_count": len(errors),
            "events": [
                {
                    "event_id": obs["normalized_content"]["event_id"],
                    "record_id": obs["normalized_content"]["record_id"],
                    "channel": obs["normalized_content"]["channel"],
                    "computer": obs["normalized_content"]["computer"],
                    "provider_name": obs["normalized_content"]["provider_name"],
                    "timestamp_utc": obs["normalized_content"]["time_created_utc"],
                    "data": obs["normalized_content"]["event_data"],
                }
                for obs in observations
            ],
        }

        metadata = {
            "parsed_records_count": len(observations),
            "total_records_read": total_records_read,
            "truncated": truncated,
            "errors": errors,
        }

        return ToolExecutionResult(
            raw_output=raw_output,
            observations=observations,
            metadata=metadata,
            status=ToolExecutionStatus.SUCCESS,
        )

    def _resolve_source(
        self,
        params: EvtxParserParameters,
        context: ToolExecutionContext,
    ) -> tuple[Path, uuid.UUID | None]:
        """Resolve physical EVTX file path and associated evidence_id."""
        source_id = params.evidence_id or context.evidence_id

        if params.file_path is not None:
            path = Path(params.file_path)
            if not path.is_file():
                raise ValidationException(f"Fichier EVTX introuvable: '{params.file_path}'.")
            return path, source_id

        if params.evidence_id is not None:
            settings = get_settings()
            staging_dir = Path(settings.evidence_staging_path)
            storage_dir = Path(settings.evidence_storage_path)

            candidates = [
                staging_dir / f"{params.evidence_id}.bin",
                staging_dir / str(params.evidence_id),
                storage_dir / f"{params.evidence_id}.bin",
                storage_dir / str(params.evidence_id),
            ]
            target_path: Path | None = None
            for candidate in candidates:
                if candidate.is_file():
                    target_path = candidate
                    break

            if target_path is None:
                raise ValidationException(
                    f"Fichier de preuve introuvable pour l'identifiant '{params.evidence_id}'."
                )

            return target_path, source_id

        raise ValidationException(
            "Au moins une source de données doit être fournie: 'evidence_id' ou 'file_path'."
        )

    def _validate_evtx_header(self, path: Path) -> None:
        """Verify binary file header matches EVTX specification (ElfFile\\x00)."""
        try:
            file_size = path.stat().st_size
        except Exception as exc:
            raise ValidationException(
                f"Impossible de vérifier la taille du fichier '{path.name}': {exc}"
            ) from exc

        if file_size < 4096:
            raise ValidationException(
                f"Format EVTX non reconnu ou corrompu dès l'en-tête: '{path.name}'."
            )

        try:
            with open(path, "rb") as f:
                magic = f.read(8)
        except Exception as exc:
            raise ValidationException(
                f"Erreur d'accès en lecture au fichier '{path.name}': {exc}"
            ) from exc

        if len(magic) < 8 or magic != EVTX_MAGIC:
            raise ValidationException(
                f"Format EVTX non reconnu ou corrompu dès l'en-tête: '{path.name}'."
            )

    def _iter_records(self, evtx_file: Any) -> Any:
        """Yield (record, error) tuples with lazy per-chunk and per-record isolation."""
        # Prefer iterating chunks lazily if supported by python-evtx
        if hasattr(evtx_file, "chunks"):
            try:
                chunk_gen = iter(evtx_file.chunks())
            except Exception as exc:
                logger.warning("Erreur lors de l'initialisation des chunks EVTX: %s", exc)
                yield None, exc
                return

            while True:
                try:
                    chunk = next(chunk_gen)
                except StopIteration:
                    break
                except Exception as exc:
                    logger.warning("Chunk EVTX corrompu ignoré: %s", exc)
                    yield None, exc
                    break

                try:
                    records_iter = iter(chunk.records())
                except Exception as exc:
                    logger.warning("Erreur d'accès aux records du chunk EVTX: %s", exc)
                    yield None, exc
                    continue

                while True:
                    try:
                        record = next(records_iter)
                        yield record, None
                    except StopIteration:
                        break
                    except Exception as exc:
                        logger.warning("Enregistrement de chunk EVTX corrompu: %s", exc)
                        yield None, exc
                        break
            return

        # Fallback to direct records generator if chunks() is unavailable (e.g. test mock)
        if hasattr(evtx_file, "records"):
            try:
                for rec in evtx_file.records():
                    yield rec, None
            except Exception as exc:
                logger.warning("Erreur lors du parcours des records EVTX: %s", exc)
                yield None, exc

    def _parse_xml_record(
        self,
        xml_str: str,
        record_offset: int = 0,
        fallback_record_num: int | None = None,
        fallback_dt: datetime | None = None,
    ) -> dict[str, Any]:
        """Parse raw XML string into structured event fields and normalized content."""
        root = ET.fromstring(xml_str)

        event_id: int = 0
        record_id: int | None = fallback_record_num
        channel: str = ""
        computer: str = ""
        provider_name: str = ""
        level: int | None = None
        opcode: int | None = None
        task: int | None = None
        keywords: str | None = None
        process_id: int | None = None
        thread_id: int | None = None
        user_id: str | None = None
        activity_id: str | None = None
        time_created_str: str | None = None
        event_data: dict[str, Any] = {}
        unnamed_counters: dict[str, int] = {}

        for child in root:
            tag = _local_tag(child.tag)
            if tag == "System":
                for sub in child:
                    sub_tag = _local_tag(sub.tag)
                    val_text = (sub.text or "").strip()
                    if sub_tag == "EventID":
                        with contextlib.suppress(ValueError, TypeError):
                            event_id = int(val_text)
                    elif sub_tag == "EventRecordID":
                        with contextlib.suppress(ValueError, TypeError):
                            record_id = int(val_text)
                    elif sub_tag == "TimeCreated":
                        time_created_str = sub.attrib.get("SystemTime") or val_text or None
                    elif sub_tag == "Channel":
                        channel = val_text
                    elif sub_tag == "Computer":
                        computer = val_text
                    elif sub_tag == "Provider":
                        provider_name = sub.attrib.get("Name") or val_text
                    elif sub_tag == "Level":
                        with contextlib.suppress(ValueError, TypeError):
                            level = int(val_text)
                    elif sub_tag == "Opcode":
                        with contextlib.suppress(ValueError, TypeError):
                            opcode = int(val_text)
                    elif sub_tag == "Task":
                        with contextlib.suppress(ValueError, TypeError):
                            task = int(val_text)
                    elif sub_tag == "Keywords":
                        keywords = val_text or None
                    elif sub_tag == "Execution":
                        with contextlib.suppress(ValueError, TypeError):
                            pid_str = sub.attrib.get("ProcessID") or sub.attrib.get("process_id")
                            if pid_str:
                                process_id = int(pid_str)
                        with contextlib.suppress(ValueError, TypeError):
                            tid_str = sub.attrib.get("ThreadID") or sub.attrib.get("thread_id")
                            if tid_str:
                                thread_id = int(tid_str)
                    elif sub_tag == "Security":
                        user_id = (
                            sub.attrib.get("UserID")
                            or sub.attrib.get("user_id")
                            or (sub.text or "").strip()
                            or None
                        )
                    elif sub_tag == "Correlation":
                        activity_id = (
                            sub.attrib.get("ActivityID")
                            or sub.attrib.get("activity_id")
                            or (sub.text or "").strip()
                            or None
                        )
            elif tag in ("EventData", "UserData"):
                for sub in child:
                    sub_tag = _local_tag(sub.tag)
                    sub_children = list(sub)
                    if sub_children:
                        for nested in sub_children:
                            nested_tag = _local_tag(nested.tag)
                            name = nested.attrib.get("Name") or nested_tag
                            event_data[name] = (nested.text or "").strip()
                    else:
                        name = sub.attrib.get("Name")
                        val = (sub.text or "").strip()
                        if name:
                            event_data[name] = val
                        else:
                            count = unnamed_counters.get(sub_tag, 0)
                            unnamed_counters[sub_tag] = count + 1
                            key = sub_tag if count == 0 else f"{sub_tag}_{count}"
                            event_data[key] = val

        dt_utc = _parse_event_timestamp(time_created_str, fallback_dt)

        if record_id is not None:
            source_location = f"record_id:{record_id}"
            effective_record_id = record_id
        else:
            source_location = f"record_offset:{record_offset}"
            effective_record_id = record_offset

        time_created_utc_str = dt_utc.isoformat() if dt_utc else None

        normalized_content = {
            "event_id": event_id,
            "record_id": effective_record_id,
            "channel": channel,
            "computer": computer,
            "provider_name": provider_name,
            "level": level,
            "opcode": opcode,
            "task": task,
            "keywords": keywords,
            "process_id": process_id,
            "thread_id": thread_id,
            "user_id": user_id,
            "activity_id": activity_id,
            "time_created_utc": time_created_utc_str,
            "event_data": event_data,
        }

        return {
            "source_location": source_location,
            "timestamp_utc": dt_utc,
            "normalized_content": normalized_content,
        }

    def _matches_filters(
        self,
        parsed: dict[str, Any],
        params: EvtxParserParameters,
    ) -> bool:
        """Apply upstream filtering on event_ids, channels, temporal window, and search query."""
        content = parsed["normalized_content"]

        # 1. event_ids filter
        if params.event_ids is not None and content["event_id"] not in params.event_ids:
            return False

        # 2. channels filter (case-insensitive)
        if params.channels is not None:
            allowed_channels = {c.strip().lower() for c in params.channels if c}
            if (content["channel"] or "").strip().lower() not in allowed_channels:
                return False

        # 3. temporal window filter
        ts = parsed.get("timestamp_utc")
        if params.start_time is not None and (ts is None or ts < params.start_time):
            return False
        if params.end_time is not None and (ts is None or ts > params.end_time):
            return False

        # 4. search_query filter (case-insensitive search in extracted field values)
        if params.search_query is not None and params.search_query.strip():
            query = params.search_query.strip().lower()
            if query in (content["computer"] or "").lower():
                return True
            if query in (content["channel"] or "").lower():
                return True
            if query in (content["provider_name"] or "").lower():
                return True
            if content.get("user_id") and query in content["user_id"].lower():
                return True
            if content.get("activity_id") and query in content["activity_id"].lower():
                return True
            for k, v in content["event_data"].items():
                if query in str(k).lower() or query in str(v).lower():
                    return True
            return False

        return True
