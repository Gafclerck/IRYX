"""Forensic Windows Prefetch parser tool via dissect with UTC normalization."""

import contextlib
import io
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from dissect.target.plugins.os.windows.prefetch import Prefetch, c_prefetch
from dissect.util import lzxpress_huffman
from dissect.util.ts import wintimestamp
from pydantic import BaseModel, ConfigDict, Field, model_validator

from iryx.core.config import get_settings
from iryx.core.exceptions import ToolExecutionFailedException, ValidationException
from iryx.gateway.base import (
    BaseTool,
    ToolExecutionContext,
    ToolExecutionResult,
    resolve_confined_evidence_path,
)
from iryx.gateway.models import ToolExecutionStatus

logger = logging.getLogger("iryx.gateway.tools.prefetch_parser")

PREFETCH_SCCA_MAGIC = b"SCCA"
PREFETCH_MAM_MAGIC = b"MAM"
MAX_LOADED_FILES_LIMIT = 1000


class PrefetchParsingError(ToolExecutionFailedException):
    """Raised when a prefetch file is unreadable, corrupted, or has an invalid header."""

    def __init__(self, message: str = "Erreur lors de l'analyse du fichier Prefetch.") -> None:
        super().__init__(message=message, code="PREFETCH_PARSING_ERROR")


def sanitize_path(raw_path: str) -> str:
    """Sanitize paths by removing null bytes, normalizing slashes, and resolving traversal."""
    if not raw_path:
        return ""

    cleaned = raw_path.split("\x00")[0].strip()
    if not cleaned:
        return ""

    cleaned = cleaned.replace("/", "\\")
    is_unc = cleaned.startswith(r"\\")
    has_leading_slash = cleaned.startswith("\\")

    parts = [p.strip() for p in cleaned.split("\\") if p.strip()]
    resolved_parts: list[str] = []

    for part in parts:
        if part == ".":
            continue
        if part == "..":
            if resolved_parts and not (len(resolved_parts) == 1 and ":" in resolved_parts[0]):
                resolved_parts.pop()
        else:
            resolved_parts.append(part)

    result = "\\".join(resolved_parts)
    if is_unc:
        return f"\\\\{result}"
    if has_leading_slash:
        return f"\\{result}"
    return result


def sanitize_loaded_files(raw_files: list[str]) -> tuple[list[str], int, bool]:
    """Sanitize loaded file dependencies, cap at MAX_LOADED_FILES_LIMIT, and report truncation."""
    cleaned_files: list[str] = []
    for f in raw_files:
        sanitized = sanitize_path(f)
        if sanitized:
            cleaned_files.append(sanitized)

    total_count = len(cleaned_files)
    if total_count > MAX_LOADED_FILES_LIMIT:
        return cleaned_files[:MAX_LOADED_FILES_LIMIT], total_count, True
    return cleaned_files, total_count, False


def extract_volumes(scca: Prefetch) -> list[dict[str, Any]]:
    """Extract and sanitize volume information from Prefetch structures."""
    if not scca.fn or not getattr(scca.fn, "number_of_volumes", 0):
        return []

    num_volumes = int(scca.fn.number_of_volumes)
    vol_offset = int(scca.fn.volumes_information_offset)

    vol_struct = (
        c_prefetch.VOLUME_INFORMATION_30
        if scca.version in (26, 30, 31)
        else c_prefetch.VOLUME_INFORMATION_17
    )
    struct_size = len(vol_struct)
    if scca.version not in (26, 30, 31) and num_volumes > 0:
        vol_info_size = getattr(scca.fn, "volumes_information_size", 0)
        if vol_info_size and vol_info_size > 0:
            dyn_stride = int(vol_info_size) // num_volumes
            if dyn_stride > 0:
                struct_size = dyn_stride

    volumes: list[dict[str, Any]] = []

    # Get stream size for bounds checking and restore position in finally
    current_pos = scca.fh.tell()
    try:
        scca.fh.seek(0, io.SEEK_END)
        stream_size = scca.fh.tell()
        scca.fh.seek(current_pos)

        for i in range(num_volumes):
            entry_offset = vol_offset + (i * struct_size)
            if entry_offset + struct_size > stream_size:
                break

            try:
                scca.fh.seek(entry_offset)
                v = vol_struct(scca.fh)
            except Exception as exc:
                logger.debug("Failed reading volume structure at %s: %s", entry_offset, exc)
                break

            # Attempt to read device path string (UTF-16LE)
            num_chars = int(v.device_path_number_of_characters)
            byte_len = num_chars * 2
            dev_path_str = ""

            if num_chars > 0:
                candidates = [
                    entry_offset + v.device_path_offset,
                    vol_offset + v.device_path_offset,
                    v.device_path_offset,
                ]
                for cand_offset in candidates:
                    if cand_offset >= 0 and cand_offset + byte_len <= stream_size:
                        scca.fh.seek(cand_offset)
                        raw_path_bytes = scca.fh.read(byte_len)
                        try:
                            decoded = raw_path_bytes.decode("utf-16-le", errors="ignore")
                            sanitized = sanitize_path(decoded)
                            if sanitized:
                                dev_path_str = sanitized
                                break
                        except Exception:
                            continue

            # Format creation time
            creation_dt = None
            if v.creation_time != 0:
                try:
                    creation_dt = wintimestamp(v.creation_time)
                    if creation_dt.tzinfo is None:
                        creation_dt = creation_dt.replace(tzinfo=UTC)
                    else:
                        creation_dt = creation_dt.astimezone(UTC)
                except Exception:
                    creation_dt = None

            volumes.append(
                {
                    "device_path": dev_path_str,
                    "serial_number": f"{v.serial_number:08X}",
                    "creation_time_utc": creation_dt.isoformat() if creation_dt else None,
                }
            )
    finally:
        with contextlib.suppress(Exception):
            scca.fh.seek(current_pos)

    return volumes


class PrefetchParserParameters(BaseModel):
    """Input parameters schema for PrefetchParserTool."""

    evidence_id: uuid.UUID | None = Field(
        default=None,
        description="Identifiant UUID de la preuve scellée à analyser.",
    )
    file_path: str | None = Field(
        default=None,
        description="Chemin local du fichier ou répertoire Prefetch (.pf) à analyser.",
    )
    artifact_type: Literal["prefetch"] = Field(
        default="prefetch",
        description="Type d'artefact forensique d'exécution (valeur autorisée: 'prefetch').",
    )
    executable_name: str | None = Field(
        default=None,
        description="Filtre optionnel insensible à la casse sur le nom d'exécutable.",
    )
    search_query: str | None = Field(
        default=None,
        description="Filtre textuel insensible à la casse sur exécutable, hash ou dépendances.",
    )
    max_results: int = Field(
        default=5000,
        ge=1,
        le=50000,
        description="Nombre maximal d'observations à extraire (1 à 50000, défaut 5000).",
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_sources(self) -> "PrefetchParserParameters":
        """Validate at least one data source is supplied."""
        if not self.evidence_id and not self.file_path:
            raise ValueError(
                "Au moins une source de données doit être fournie: 'evidence_id' ou 'file_path'."
            )
        return self


class PrefetchParserTool(BaseTool):
    """Forensic Windows Prefetch parser tool via dissect with UTC normalization."""

    name: str = "parse_execution"
    version: str = "1.0.0"
    description: str = (
        "Analyseur forensique d'artefacts d'exécution Windows Prefetch pur Python via dissect "
        "avec normalisation UTC et extraction d'observations."
    )
    timeout_seconds: int = 120
    parameters_schema: type[BaseModel] = PrefetchParserParameters

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
        """Execute prefetch parsing logic under passive forensic boundaries."""
        if not isinstance(params, PrefetchParserParameters):
            try:
                params = PrefetchParserParameters.model_validate(params)
            except Exception as e:
                raise ValidationException(
                    f"Paramètres invalides pour PrefetchParserTool: {e}"
                ) from e

        # 1. Resolve source path and evidence identifier
        target_path, source_id = self._resolve_source(params, context)

        observations: list[dict[str, Any]] = []
        executions: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        files_analyzed = 0
        truncated = False

        if target_path.is_file():
            # For a single file target, any parsing or header error raises immediately
            files_analyzed = 1
            obs_list, exec_list = self._parse_single_file(target_path, source_id, params)
            for obs, exc in zip(obs_list, exec_list, strict=False):
                if len(observations) >= params.max_results:
                    truncated = True
                    break
                observations.append(obs)
                executions.append(exc)
        else:
            # For a directory target, iterate over .pf files and log isolated errors
            pf_files = sorted(
                [
                    p
                    for p in target_path.iterdir()
                    if p.is_file() and p.name.lower().endswith(".pf")
                ],
                key=lambda p: p.name.lower(),
            )
            for pf_path in pf_files:
                if truncated:
                    break
                files_analyzed += 1
                try:
                    confined_pf = resolve_confined_evidence_path(pf_path)
                    obs_list, exec_list = self._parse_single_file(confined_pf, source_id, params)
                    for obs, exc in zip(obs_list, exec_list, strict=False):
                        if len(observations) >= params.max_results:
                            truncated = True
                            break
                        observations.append(obs)
                        executions.append(exc)
                except Exception as exc:
                    logger.warning(
                        "Erreur lors de l'analyse du fichier Prefetch '%s': %s",
                        pf_path.name,
                        exc,
                    )
                    errors.append({"file": pf_path.name, "error": str(exc)})

        raw_output = {
            "artifact_type": "prefetch",
            "files_analyzed": files_analyzed,
            "total_executions": len(observations),
            "executions": executions,
        }

        metadata = {
            "files_analyzed": files_analyzed,
            "total_executions": len(observations),
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
        params: PrefetchParserParameters,
        context: ToolExecutionContext,
    ) -> tuple[Path, uuid.UUID | None]:
        """Resolve physical prefetch file or directory path and associated evidence_id."""
        source_id = params.evidence_id or context.evidence_id

        if params.file_path is not None:
            path = resolve_confined_evidence_path(params.file_path)
            if not path.exists():
                raise ValidationException(
                    f"Fichier ou répertoire Prefetch introuvable: '{params.file_path}'."
                )
            if not (path.is_file() or path.is_dir()):
                raise ValidationException(
                    f"Chemin source invalide (ni fichier ni répertoire): '{params.file_path}'."
                )
            return path, source_id

        if params.evidence_id is not None:
            settings = get_settings()
            staging_dir = Path(settings.evidence_staging_path)
            storage_dir = Path(settings.evidence_storage_path)

            candidates = [
                staging_dir / f"{params.evidence_id}.pf",
                staging_dir / f"{params.evidence_id}.bin",
                staging_dir / str(params.evidence_id),
                storage_dir / f"{params.evidence_id}.pf",
                storage_dir / f"{params.evidence_id}.bin",
                storage_dir / str(params.evidence_id),
            ]
            target_path: Path | None = None
            for candidate in candidates:
                if candidate.exists() and (candidate.is_file() or candidate.is_dir()):
                    target_path = candidate
                    break

            if target_path is None:
                raise ValidationException(
                    f"Preuve introuvable pour l'identifiant '{params.evidence_id}'."
                )

            return target_path, source_id

        raise ValidationException(
            "Au moins une source de données doit être fournie: 'evidence_id' ou 'file_path'."
        )

    def _validate_and_read_prefetch(self, path: Path) -> io.BytesIO:
        """Validate binary header (>=8 bytes, MAM or SCCA) and return an uncompressed stream."""
        try:
            file_size = path.stat().st_size
        except OSError as exc:
            raise PrefetchParsingError(
                f"Impossible de vérifier la taille du fichier '{path.name}': {exc}"
            ) from exc

        if file_size < 8:
            raise PrefetchParsingError(
                f"Fichier Prefetch trop court ou vide ({file_size} octets < 8) : '{path.name}'."
            )

        try:
            with open(path, "rb") as f:
                raw_data = f.read()
        except OSError as exc:
            raise PrefetchParsingError(
                f"Erreur d'accès en lecture au fichier '{path.name}': {exc}"
            ) from exc

        if len(raw_data) < 8:
            raise PrefetchParsingError(
                f"Fichier Prefetch trop court ou vide ({len(raw_data)} octets < 8) : '{path.name}'."
            )

        # Check for MAM compressed signature (bytes 0-2 or 0-3)
        if raw_data[:3] == PREFETCH_MAM_MAGIC:
            declared_size = int.from_bytes(raw_data[4:8], "little")
            if declared_size > 100 * 1024 * 1024:
                raise PrefetchParsingError(
                    f"Taille décompressée MAM excessive ({declared_size} octets > 100 Mo) "
                    f"dans '{path.name}'."
                )
            try:
                decompressed = lzxpress_huffman.decompress(raw_data[8:])
            except Exception as exc:
                raise PrefetchParsingError(
                    f"Échec de décompression MAM LZXpress pour '{path.name}': {exc}"
                ) from exc

            if len(decompressed) < 8 or decompressed[4:8] != PREFETCH_SCCA_MAGIC:
                raise PrefetchParsingError(
                    f"Flux décompressé MAM invalide (signature SCCA absente) dans '{path.name}'."
                )
            return io.BytesIO(decompressed)

        # Check for uncompressed SCCA signature at offset 4
        if raw_data[4:8] == PREFETCH_SCCA_MAGIC:
            return io.BytesIO(raw_data)

        raise PrefetchParsingError(
            f"Format Prefetch non reconnu ou signature invalide : '{path.name}'."
        )

    def _parse_single_file(
        self,
        file_path: Path,
        source_id: uuid.UUID | None,
        params: PrefetchParserParameters,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Parse an individual Prefetch file, applying filters and producing records."""
        stream = self._validate_and_read_prefetch(file_path)

        try:
            scca = Prefetch(stream)
        except Exception as exc:
            raise PrefetchParsingError(
                f"Erreur lors du décodage des structures Prefetch de '{file_path.name}': {exc}"
            ) from exc

        # Extract executable name
        try:
            raw_name = scca.header.name.decode("utf-16-le", errors="ignore")
            executable_name = raw_name.split("\x00")[0].strip()
        except Exception:
            executable_name = ""

        if not executable_name:
            executable_name = file_path.stem.rsplit("-", 1)[0].strip()

        # Check executable_name filter
        if params.executable_name and not self._matches_executable_filter(
            params.executable_name, executable_name
        ):
            return [], []

        # Extract prefetch hash and run count
        prefetch_hash = f"{scca.header.hash:08X}"
        run_count = int(getattr(scca.fn, "run_count", 0))

        # Extract execution timestamps (latest + previous non-null runs)
        valid_timestamps: list[datetime] = []
        if getattr(scca.fn, "last_run_time", 0) != 0:
            try:
                latest_ts = scca.latest_timestamp
                if latest_ts and latest_ts.year > 1601:
                    if latest_ts.tzinfo is None:
                        latest_ts = latest_ts.replace(tzinfo=UTC)
                    else:
                        latest_ts = latest_ts.astimezone(UTC)
                    valid_timestamps.append(latest_ts)
            except Exception:
                pass

        try:
            for prev_ts in scca.previous_timestamps:
                if prev_ts and prev_ts.year > 1601:
                    if prev_ts.tzinfo is None:
                        prev_ts = prev_ts.replace(tzinfo=UTC)
                    else:
                        prev_ts = prev_ts.astimezone(UTC)
                    valid_timestamps.append(prev_ts)
        except Exception:
            pass

        all_timestamps_iso = [ts.isoformat() for ts in valid_timestamps]
        last_execution_utc_str = valid_timestamps[0].isoformat() if valid_timestamps else None

        # Extract volumes and loaded files
        volumes = extract_volumes(scca)
        raw_metrics = getattr(scca, "metrics", None) or []
        loaded_files, loaded_files_count, loaded_files_truncated = sanitize_loaded_files(
            raw_metrics
        )

        # Check search_query filter
        source_loc = str(file_path.name)[:512]
        if params.search_query and not self._matches_search_filter(
            params.search_query,
            executable_name,
            prefetch_hash,
            source_loc,
            volumes,
            loaded_files,
        ):
            return [], []

        file_observations: list[dict[str, Any]] = []
        file_executions: list[dict[str, Any]] = []

        for idx, exec_dt in enumerate(valid_timestamps):
            exec_iso = exec_dt.isoformat()
            normalized_content = {
                "tool_name": "dissect.prefetch",
                "executable_name": executable_name,
                "prefetch_hash": prefetch_hash,
                "run_count": run_count,
                "execution_index": idx,
                "timestamp_utc": exec_iso,
                "all_execution_timestamps_utc": all_timestamps_iso,
                "volumes": volumes,
                "loaded_files_count": loaded_files_count,
                "loaded_files": loaded_files,
                "loaded_files_truncated": loaded_files_truncated,
            }

            obs = {
                "source_id": source_id,
                "source_location": source_loc,
                "timestamp_utc": exec_dt,
                "normalized_content": normalized_content,
            }

            exec_record = {
                "executable_name": executable_name,
                "run_count": run_count,
                "last_execution_utc": last_execution_utc_str,
                "prefetch_hash": prefetch_hash,
                "timestamp_utc": exec_iso,
                "execution_index": idx,
                "source_file": source_loc,
                "volumes": volumes,
                "loaded_files_count": loaded_files_count,
            }

            file_observations.append(obs)
            file_executions.append(exec_record)

        return file_observations, file_executions

    def _matches_executable_filter(self, filter_name: str, executable_name: str) -> bool:
        """Case-insensitive matching between filter and binary name."""
        f = filter_name.strip().lower()
        e = executable_name.strip().lower()
        if f == e:
            return True
        f_name = Path(f).name.lower()
        if f_name == e:
            return True
        return Path(f_name).stem.lower() == Path(e).stem.lower()

    def _matches_search_filter(
        self,
        query: str,
        executable_name: str,
        prefetch_hash: str,
        source_location: str,
        volumes: list[dict[str, Any]],
        loaded_files: list[str],
    ) -> bool:
        """Check if case-insensitive search query matches any prefetch metadata or dependency."""
        q = query.strip().lower()
        if q in executable_name.lower():
            return True
        if q in prefetch_hash.lower():
            return True
        if q in source_location.lower():
            return True
        if any(
            q in v.get("device_path", "").lower()
            or q in v.get("serial_number", "").lower()
            or q in (v.get("creation_time_utc") or "").lower()
            for v in volumes
        ):
            return True
        return any(q in f.lower() for f in loaded_files)
