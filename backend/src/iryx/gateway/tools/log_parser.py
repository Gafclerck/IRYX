"""Log and CSV forensic parser tool with UTC timestamp normalization."""

import contextlib
import csv
import io
import json
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from iryx.core.config import get_settings
from iryx.core.exceptions import ValidationException
from iryx.gateway.base import (
    BaseTool,
    ToolExecutionContext,
    ToolExecutionResult,
    resolve_confined_evidence_path,
)
from iryx.gateway.models import ToolExecutionStatus

logger = logging.getLogger("iryx.gateway.tools.log_parser")

SupportedPreset = Literal[
    "auto",
    "csv",
    "tsv",
    "syslog",
    "apache_combined",
    "clf",
    "json_lines",
    "key_value",
    "custom_regex",
]

# Compiled regular expressions for format matching and parsing
APACHE_COMBINED_REGEX = re.compile(
    r"^(?P<ip>\S+)\s+"
    r"(?P<ident>\S+)\s+"
    r"(?P<auth_user>\S+)\s+"
    r"\[(?P<timestamp>[^\]]+)\]\s+"
    r'"(?P<request>(?:\\.|[^"\\])*)"\s+'
    r"(?P<status_code>\d{3})"
    r"(?:\s+(?P<bytes_sent>\S+))?"
    r'(?:\s+"(?P<referrer>(?:\\.|[^"\\])*)"\s+"(?P<user_agent>(?:\\.|[^"\\])*)")?'
)

SYSLOG_RFC5424_REGEX = re.compile(
    r"^(?:<(?P<pri>\d{1,3})>)?"
    r"(?P<version>\d+)?\s*"
    r"(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2}))\s+"
    r"(?P<hostname>\S+)\s+"
    r"(?P<appname>\S+)\s+"
    r"(?P<pid>\S+)\s+"
    r"(?P<msgid>\S+)"
    r"(?:\s+(?P<structured_data>\[.*?\]|-))?"
    r"(?:\s+(?P<message>.*))?$"
)

SYSLOG_RFC3164_REGEX = re.compile(
    r"^(?:<(?P<pri>\d{1,3})>)?"
    r"(?P<timestamp>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<hostname>\S+)\s+"
    r"(?P<appname>[^:\[\s]+)"
    r"(?:\[(?P<pid>\d+)\])?"
    r"(?::\s*|\s+)"
    r"(?P<message>.*)$"
)

KEY_VALUE_REGEX = re.compile(
    r'(\b[\w\.\-]+)=(?:"((?:\\.|[^"\\])*)"|\'((?:\\.|[^\'\\])*)\'|([^\s]+))'
)

ENGLISH_MONTHS: dict[str, int] = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

CLF_TIMESTAMP_REGEX = re.compile(
    r"^(?P<day>\d{1,2})/(?P<month>[A-Za-z]{3})/(?P<year>\d{4}):"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
    r"(?:\s+(?P<tz>[+\-]\d{4}))?$"
)

SYSLOG_BSD_TIMESTAMP_REGEX = re.compile(
    r"^(?P<month>[A-Za-z]{3})\s+(?P<day>\d{1,2})\s+"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})$"
)

GENERIC_DATETIME_REGEX = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+\-]\d{2}:?\d{2})?|"
    r"\d{1,2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}(?:\s+[+\-]\d{4})?|"
    r"[A-Za-z]{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\b"
)

IP_REGEX = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _normalize_epoch_to_utc(ts: float) -> datetime | None:
    """Normalize numeric epoch (s, ms, us, ns) within 1980-2100 range to UTC."""
    if ts > 1e16:
        ts /= 1e9
    elif ts > 1e13:
        ts /= 1e6
    elif ts > 1e10:
        ts /= 1e3

    if 315532800 <= ts <= 4102444800:
        try:
            return datetime.fromtimestamp(ts, tz=UTC)
        except (ValueError, OverflowError, OSError):
            return None
    return None


def parse_timestamp_to_utc(
    value: Any,
    custom_format: str | None = None,
) -> datetime | None:
    """Parse various timestamp representations and convert to timezone-aware UTC datetime."""
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    if isinstance(value, (int, float)):
        return _normalize_epoch_to_utc(float(value))

    if not isinstance(value, str):
        return None

    val = value.strip().strip("'\"")
    if not val:
        return None

    # Epoch unix timestamp as string
    if re.match(r"^\d+(\.\d+)?$", val):
        dt_epoch = _normalize_epoch_to_utc(float(val))
        if dt_epoch is not None:
            return dt_epoch

    # Custom strptime format if provided
    if custom_format:
        try:
            dt = datetime.strptime(val, custom_format)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            pass

    # Locale-independent CLF parsing
    m_clf = CLF_TIMESTAMP_REGEX.match(val)
    if m_clf:
        month_str = m_clf.group("month").lower()
        month_num = ENGLISH_MONTHS.get(month_str)
        if month_num:
            day = int(m_clf.group("day"))
            year = int(m_clf.group("year"))
            hour = int(m_clf.group("hour"))
            minute = int(m_clf.group("minute"))
            second = int(m_clf.group("second"))
            tz_str = m_clf.group("tz")
            if tz_str:
                sign = 1 if tz_str[0] == "+" else -1
                tz_h = int(tz_str[1:3])
                tz_m = int(tz_str[3:5])
                tz_offset = timezone(timedelta(minutes=sign * (tz_h * 60 + tz_m)))
                dt = datetime(year, month_num, day, hour, minute, second, tzinfo=tz_offset)
                return dt.astimezone(UTC)
            return datetime(year, month_num, day, hour, minute, second, tzinfo=UTC)

    # Locale-independent Syslog BSD parsing
    norm_val = re.sub(r"\s+", " ", val)
    m_syslog = SYSLOG_BSD_TIMESTAMP_REGEX.match(norm_val)
    if m_syslog:
        month_str = m_syslog.group("month").lower()
        month_num = ENGLISH_MONTHS.get(month_str)
        if month_num:
            day = int(m_syslog.group("day"))
            hour = int(m_syslog.group("hour"))
            minute = int(m_syslog.group("minute"))
            second = int(m_syslog.group("second"))
            current_year = datetime.now(UTC).year
            return datetime(current_year, month_num, day, hour, minute, second, tzinfo=UTC)

    # ISO-8601 / RFC 3339
    try:
        iso_clean = val.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_clean)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        pass

    # Common standard datetime string patterns
    common_formats = (
        "%Y-%m-%d %H:%M:%S,%f",
        "%Y-%m-%d %H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%d",
    )
    for fmt in common_formats:
        try:
            dt = datetime.strptime(norm_val, fmt)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            pass

    # RFC 2822 format (e.g. email or HTTP Date header)
    try:
        dt = parsedate_to_datetime(val)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        pass

    return None


class LogCsvParserParameters(BaseModel):
    """Input parameters schema for LogCsvParserTool."""

    evidence_id: uuid.UUID | None = Field(
        default=None,
        description="Identifiant UUID de la preuve scellée à analyser.",
    )
    file_path: str | None = Field(
        default=None,
        description="Chemin local du fichier de log à analyser.",
    )
    content: str | None = Field(
        default=None,
        description="Contenu texte brut du journal en mémoire.",
    )
    format_preset: SupportedPreset = Field(
        default="auto",
        description="Préréglage du format de log ou détection automatique ('auto').",
    )
    delimiter: str | None = Field(
        default=None,
        description="Délimiteur personnalisé pour format tabulaire (CSV/TSV).",
    )
    custom_regex: str | None = Field(
        default=None,
        description="Expression régulière personnalisée avec groupes nommés.",
    )
    timestamp_field: str | None = Field(
        default=None,
        description="Nom de la colonne ou du champ contenant l'horodatage.",
    )
    timestamp_format: str | None = Field(
        default=None,
        description="Format strptime personnalisé pour parser l'horodatage.",
    )
    max_records: int = Field(
        default=5000,
        ge=1,
        le=50000,
        description="Nombre maximal d'enregistrements à extraire (défaut 5000, max 50000).",
    )
    encoding: str = Field(
        default="utf-8",
        description="Encodage du fichier texte (défaut utf-8).",
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_sources_and_regex(self) -> "LogCsvParserParameters":
        """Validate at least one source is supplied and custom_regex syntax is valid."""
        if not self.evidence_id and not self.file_path and self.content is None:
            raise ValueError(
                "Au moins une source de données doit être fournie: "
                "'evidence_id', 'file_path' ou 'content'."
            )
        if self.format_preset == "custom_regex" and not self.custom_regex:
            raise ValueError(
                "Le paramètre 'custom_regex' est obligatoire lorsque format_preset='custom_regex'."
            )
        if self.custom_regex:
            try:
                re.compile(self.custom_regex)
            except re.error as e:
                raise ValueError(f"Expression régulière invalide dans 'custom_regex': {e}") from e
        return self


class LogCsvParserTool(BaseTool):
    """Forensic log and CSV parser tool with UTC normalization."""

    name: str = "parse_text_logs"
    version: str = "1.0.0"
    description: str = (
        "Analyseur forensique de journaux texte et CSV avec détection de format "
        "et normalisation systématique des horodatages vers UTC."
    )
    timeout_seconds: int = 60
    parameters_schema: type[BaseModel] = LogCsvParserParameters

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
        """Execute log parsing logic under strict passive security boundaries."""
        if not isinstance(params, LogCsvParserParameters):
            try:
                params = LogCsvParserParameters.model_validate(params)
            except Exception as e:
                raise ValidationException(f"Paramètres invalides pour LogCsvParserTool: {e}") from e

        # 1. Resolve source data and evidence identifier
        raw_text, source_id = self._resolve_source(params, context)
        raw_text = raw_text.lstrip("\ufeff")

        # 2. Check empty content
        if not raw_text.strip():
            return ToolExecutionResult(
                raw_output={
                    "records_count": 0,
                    "total_lines": 0,
                    "errors_count": 0,
                    "format_preset": params.format_preset,
                    "records": [],
                },
                observations=[],
                metadata={
                    "parsed_records_count": 0,
                    "total_lines": 0,
                    "truncated": False,
                    "errors": [],
                    "format_preset": params.format_preset,
                },
                status=ToolExecutionStatus.SUCCESS,
            )

        # 3. Detect or enforce format preset
        lines = raw_text.splitlines()
        total_lines = len(lines)
        effective_preset = self._determine_format(params, lines)

        # 4. Parse according to effective preset
        observations: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        truncated = False

        if effective_preset in ("csv", "tsv"):
            observations, errors, truncated = self._parse_csv(
                params, raw_text, source_id, effective_preset
            )
        elif effective_preset in ("apache_combined", "clf"):
            observations, errors, truncated = self._parse_apache(params, lines, source_id)
        elif effective_preset == "syslog":
            observations, errors, truncated = self._parse_syslog(params, lines, source_id)
        elif effective_preset == "json_lines":
            observations, errors, truncated = self._parse_json_lines(params, lines, source_id)
        elif effective_preset == "key_value":
            observations, errors, truncated = self._parse_key_value(params, lines, source_id)
        elif effective_preset == "custom_regex":
            observations, errors, truncated = self._parse_custom_regex(params, lines, source_id)
        else:
            observations, errors, truncated = self._parse_generic(params, lines, source_id)

        # Truncate observations if exceeding max_records
        if len(observations) > params.max_records:
            observations = observations[: params.max_records]
            truncated = True

        raw_output = {
            "records_count": len(observations),
            "total_lines": total_lines,
            "errors_count": len(errors),
            "format_preset": effective_preset,
            "records": [
                {
                    "timestamp_utc": (
                        obs["timestamp_utc"].isoformat() if obs["timestamp_utc"] else None
                    ),
                    "raw": obs["normalized_content"].get("raw_line", ""),
                    "parsed_fields": obs["normalized_content"],
                }
                for obs in observations
            ],
        }

        metadata = {
            "parsed_records_count": len(observations),
            "total_lines": total_lines,
            "truncated": truncated,
            "errors": errors,
            "format_preset": effective_preset,
        }

        return ToolExecutionResult(
            raw_output=raw_output,
            observations=observations,
            metadata=metadata,
            status=ToolExecutionStatus.SUCCESS,
        )

    def _resolve_source(
        self,
        params: LogCsvParserParameters,
        context: ToolExecutionContext,
    ) -> tuple[str, uuid.UUID | None]:
        """Resolve textual source and associated evidence_id."""
        source_id = params.evidence_id or context.evidence_id

        if params.content is not None:
            return params.content.lstrip("\ufeff"), source_id

        if params.file_path is not None:
            path = resolve_confined_evidence_path(params.file_path)
            if not path.is_file():
                raise ValidationException(f"Fichier journal introuvable: '{params.file_path}'.")
            try:
                content = (
                    path.read_bytes().decode(params.encoding, errors="replace").lstrip("\ufeff")
                )
                return content, source_id
            except Exception as exc:
                raise ValidationException(
                    f"Erreur de lecture du fichier '{params.file_path}': {exc}"
                ) from exc

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

            try:
                content = (
                    target_path.read_bytes()
                    .decode(params.encoding, errors="replace")
                    .lstrip("\ufeff")
                )
                return content, params.evidence_id
            except Exception as exc:
                raise ValidationException(
                    f"Erreur de lecture de la preuve '{params.evidence_id}': {exc}"
                ) from exc

        raise ValidationException(
            "Au moins une source de données doit être fournie: "
            "'evidence_id', 'file_path' ou 'content'."
        )

    def _determine_format(
        self,
        params: LogCsvParserParameters,
        lines: list[str],
    ) -> str:
        """Determine effective log format preset from configuration or auto-detection."""
        if params.format_preset != "auto":
            return params.format_preset

        non_empty = [ln.strip() for ln in lines if ln.strip()][:10]
        if not non_empty:
            return "generic"

        # 1. JSON Lines detection
        json_valid_count = 0
        for ln in non_empty:
            if ln.startswith("{") and ln.endswith("}"):
                try:
                    json.loads(ln)
                    json_valid_count += 1
                except Exception:
                    pass
        if json_valid_count >= max(1, int(len(non_empty) * 0.7)):
            return "json_lines"

        # 2. Apache Combined / CLF detection
        apache_count = sum(1 for ln in non_empty if APACHE_COMBINED_REGEX.match(ln))
        if apache_count >= max(1, int(len(non_empty) * 0.7)):
            return "apache_combined"

        # 3. Syslog detection (RFC 5424 or RFC 3164)
        syslog_count = sum(
            1
            for ln in non_empty
            if SYSLOG_RFC5424_REGEX.match(ln) or SYSLOG_RFC3164_REGEX.match(ln)
        )
        if syslog_count >= max(1, int(len(non_empty) * 0.7)):
            return "syslog"

        # 4. TSV detection
        tsv_counts = [ln.count("\t") for ln in non_empty]
        if all(c > 0 and c == tsv_counts[0] for c in tsv_counts):
            return "tsv"

        # 5. CSV detection (check comma, semicolon, pipe)
        for delim in (",", ";", "|"):
            delim_counts = [ln.count(delim) for ln in non_empty]
            if all(c > 0 and c == delim_counts[0] for c in delim_counts):
                return "csv"

        # 6. Key-Value detection
        kv_counts = [len(KEY_VALUE_REGEX.findall(ln)) for ln in non_empty]
        if sum(kv_counts) / len(kv_counts) >= 2:
            return "key_value"

        return "generic"

    def _parse_csv(
        self,
        params: LogCsvParserParameters,
        raw_text: str,
        source_id: uuid.UUID | None,
        preset: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        """Parse tabular CSV or TSV log streams."""
        observations: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        truncated = False

        delim = params.delimiter
        if not delim:
            if preset == "tsv":
                delim = "\t"
            else:
                # Detect delimiter from comma, semicolon, tab, pipe
                first_lines = [ln for ln in raw_text.splitlines() if ln.strip()][:5]
                best_delim = ","
                best_consistency = -1
                for candidate in (",", ";", "\t", "|"):
                    counts = [ln.count(candidate) for ln in first_lines]
                    if (
                        counts
                        and all(c == counts[0] and c > 0 for c in counts)
                        and counts[0] > best_consistency
                    ):
                        best_consistency = counts[0]
                        best_delim = candidate
                delim = best_delim

        try:
            reader = csv.reader(io.StringIO(raw_text), delimiter=delim)
        except Exception as exc:
            errors.append({"line": 1, "error": f"CSV initialization failed: {exc}", "raw": ""})
            return observations, errors, False

        rows: list[list[str]] = []
        line_num = 0
        while True:
            line_num += 1
            try:
                row = next(reader)
                rows.append(row)
            except StopIteration:
                break
            except Exception as exc:
                errors.append({"line": line_num, "error": f"CSV parse error: {exc}", "raw": ""})

        if not rows:
            return observations, errors, False

        first_row = rows[0]
        # Determine if first row is a header
        is_header = False
        if params.timestamp_field and params.timestamp_field in first_row:
            is_header = True
        else:
            header_keywords = {
                "timestamp",
                "@timestamp",
                "time",
                "date",
                "datetime",
                "ip",
                "action",
                "status",
                "host",
                "user",
                "method",
                "level",
            }
            matches = sum(1 for col in first_row if col.strip().lower() in header_keywords)
            # Check if any cell parses as a date
            date_matches = sum(
                1 for col in first_row if parse_timestamp_to_utc(col.strip()) is not None
            )
            if matches > 0 and date_matches == 0:
                is_header = True

        if is_header:
            headers = [h.strip() for h in first_row]
            data_rows = rows[1:]
            start_line = 2
        else:
            headers = [f"col_{i}" for i in range(len(first_row))]
            data_rows = rows
            start_line = 1

        for idx, row in enumerate(data_rows):
            current_line = start_line + idx
            if len(observations) >= params.max_records:
                truncated = True
                break
            if not row or not any(c.strip() for c in row):
                continue

            if len(row) != len(headers):
                # Tolerance: if slight mismatch, pad or truncate with warning
                if len(row) < len(headers):
                    row = row + [""] * (len(headers) - len(row))
                else:
                    errors.append(
                        {
                            "line": current_line,
                            "error": (
                                f"Row column count ({len(row)}) "
                                f"exceeds header count ({len(headers)})"
                            ),
                            "raw": delim.join(row),
                        }
                    )
                    row = row[: len(headers)]

            row_dict = {k: v.strip() for k, v in zip(headers, row, strict=False)}
            row_dict["raw_line"] = delim.join(row)

            # Find timestamp
            ts_val = None
            if params.timestamp_field and params.timestamp_field in row_dict:
                ts_val = row_dict[params.timestamp_field]
            else:
                for h in headers:
                    if h.lower() in ("timestamp", "@timestamp", "time", "date", "datetime", "ts"):
                        ts_val = row_dict[h]
                        break
                if not ts_val:
                    for h in headers:
                        cand = parse_timestamp_to_utc(row_dict[h], params.timestamp_format)
                        if cand is not None:
                            ts_val = row_dict[h]
                            break

            dt_utc = parse_timestamp_to_utc(ts_val, params.timestamp_format) if ts_val else None

            observations.append(
                {
                    "timestamp_utc": dt_utc,
                    "source_location": f"line:{current_line}",
                    "source_id": source_id,
                    "normalized_content": row_dict,
                }
            )

        return observations, errors, truncated

    def _parse_apache(
        self,
        params: LogCsvParserParameters,
        lines: list[str],
        source_id: uuid.UUID | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        """Parse Apache and Nginx CLF / Combined access logs."""
        observations: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        truncated = False

        for line_idx, line in enumerate(lines, start=1):
            if len(observations) >= params.max_records:
                truncated = True
                break
            if not line.strip():
                continue

            match = APACHE_COMBINED_REGEX.match(line)
            if not match:
                errors.append(
                    {
                        "line": line_idx,
                        "error": "Ligne de log Apache/CLF non conforme",
                        "raw": line,
                    }
                )
                continue

            groups = match.groupdict()
            request = groups.get("request") or ""
            req_parts = request.split()
            method = None
            path = None
            protocol = None
            if len(req_parts) > 0:
                method = req_parts[0]
                if len(req_parts) > 2 and req_parts[-1].startswith("HTTP/"):
                    path = " ".join(req_parts[1:-1])
                    protocol = req_parts[-1]
                elif len(req_parts) > 1:
                    path = " ".join(req_parts[1:])
                else:
                    path = None

            status_code = None
            if groups.get("status_code"):
                with contextlib.suppress(ValueError):
                    status_code = int(groups["status_code"])

            bytes_sent = None
            if groups.get("bytes_sent") and groups["bytes_sent"].isdigit():
                bytes_sent = int(groups["bytes_sent"])

            ts_raw = groups.get("timestamp")
            dt_utc = parse_timestamp_to_utc(ts_raw, params.timestamp_format)

            normalized: dict[str, Any] = {
                "ip": groups.get("ip"),
                "ident": groups.get("ident"),
                "auth_user": groups.get("auth_user"),
                "method": method,
                "path": path,
                "protocol": protocol,
                "status_code": status_code,
                "bytes_sent": bytes_sent,
                "referrer": groups.get("referrer"),
                "user_agent": groups.get("user_agent"),
                "raw_line": line,
            }

            observations.append(
                {
                    "timestamp_utc": dt_utc,
                    "source_location": f"line:{line_idx}",
                    "source_id": source_id,
                    "normalized_content": normalized,
                }
            )

        return observations, errors, truncated

    def _parse_syslog(
        self,
        params: LogCsvParserParameters,
        lines: list[str],
        source_id: uuid.UUID | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        """Parse Syslog messages compliant with RFC 5424 and RFC 3164 (BSD)."""
        observations: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        truncated = False

        for line_idx, line in enumerate(lines, start=1):
            if len(observations) >= params.max_records:
                truncated = True
                break
            if not line.strip():
                continue

            # Try RFC 5424 first
            m5424 = SYSLOG_RFC5424_REGEX.match(line)
            if m5424:
                g = m5424.groupdict()
                dt_utc = parse_timestamp_to_utc(g.get("timestamp"), params.timestamp_format)
                pri_val = int(g["pri"]) if g.get("pri") else None
                facility = pri_val >> 3 if pri_val is not None else None
                severity = pri_val & 7 if pri_val is not None else None
                normalized: dict[str, Any] = {
                    "pri": pri_val,
                    "facility": facility,
                    "severity": severity,
                    "version": g.get("version"),
                    "hostname": g.get("hostname"),
                    "appname": g.get("appname"),
                    "pid": g.get("pid") if g.get("pid") != "-" else None,
                    "msgid": g.get("msgid") if g.get("msgid") != "-" else None,
                    "structured_data": g.get("structured_data"),
                    "message": g.get("message") or "",
                    "raw_line": line,
                }
                observations.append(
                    {
                        "timestamp_utc": dt_utc,
                        "source_location": f"line:{line_idx}",
                        "source_id": source_id,
                        "normalized_content": normalized,
                    }
                )
                continue

            # Fallback to RFC 3164 (BSD)
            m3164 = SYSLOG_RFC3164_REGEX.match(line)
            if m3164:
                g = m3164.groupdict()
                dt_utc = parse_timestamp_to_utc(g.get("timestamp"), params.timestamp_format)
                pri_val = int(g["pri"]) if g.get("pri") else None
                facility = pri_val >> 3 if pri_val is not None else None
                severity = pri_val & 7 if pri_val is not None else None
                normalized = {
                    "pri": pri_val,
                    "facility": facility,
                    "severity": severity,
                    "hostname": g.get("hostname"),
                    "appname": g.get("appname"),
                    "pid": g.get("pid"),
                    "message": g.get("message") or "",
                    "raw_line": line,
                }
                observations.append(
                    {
                        "timestamp_utc": dt_utc,
                        "source_location": f"line:{line_idx}",
                        "source_id": source_id,
                        "normalized_content": normalized,
                    }
                )
                continue

            errors.append(
                {
                    "line": line_idx,
                    "error": "Ligne Syslog non conforme (ni RFC 5424 ni RFC 3164)",
                    "raw": line,
                }
            )

        return observations, errors, truncated

    def _parse_json_lines(
        self,
        params: LogCsvParserParameters,
        lines: list[str],
        source_id: uuid.UUID | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        """Parse JSON Lines (ndjson/jsonl) records."""
        observations: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        truncated = False

        for line_idx, line in enumerate(lines, start=1):
            if len(observations) >= params.max_records:
                truncated = True
                break
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except Exception as exc:
                errors.append(
                    {
                        "line": line_idx,
                        "error": f"Ligne JSON non valide: {exc}",
                        "raw": line,
                    }
                )
                continue

            if not isinstance(record, dict):
                normalized: dict[str, Any] = {"value": record, "raw_line": line}
                dt_utc = None
            else:
                normalized = dict(record)
                if "raw_line" not in normalized:
                    normalized["raw_line"] = line

                # Find timestamp
                ts_val = None
                if params.timestamp_field and normalized.get(params.timestamp_field):
                    ts_val = normalized[params.timestamp_field]
                else:
                    for cand in (
                        "@timestamp",
                        "timestamp",
                        "time",
                        "datetime",
                        "date",
                        "ts",
                        "event_time",
                        "created_at",
                    ):
                        val_cand = normalized.get(cand)
                        if val_cand is not None and val_cand != "":
                            ts_val = val_cand
                            break

                dt_utc = parse_timestamp_to_utc(ts_val, params.timestamp_format)

            observations.append(
                {
                    "timestamp_utc": dt_utc,
                    "source_location": f"line:{line_idx}",
                    "source_id": source_id,
                    "normalized_content": normalized,
                }
            )

        return observations, errors, truncated

    def _parse_key_value(
        self,
        params: LogCsvParserParameters,
        lines: list[str],
        source_id: uuid.UUID | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        """Parse Key-Value structured records (Firewall / WAF logs)."""
        observations: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        truncated = False

        for line_idx, line in enumerate(lines, start=1):
            if len(observations) >= params.max_records:
                truncated = True
                break
            if not line.strip():
                continue

            matches = KEY_VALUE_REGEX.findall(line)
            if not matches:
                errors.append(
                    {
                        "line": line_idx,
                        "error": "Aucune paire clé-valeur détectée",
                        "raw": line,
                    }
                )
                continue

            kv_dict: dict[str, Any] = {}
            for k, v_double, v_single, v_unquoted in matches:
                val = v_double or v_single or v_unquoted or ""
                val = val.replace(r"\"", '"').replace(r"\'", "'")
                kv_dict[k] = val

            # Check combined date + time (common in Fortinet / Cisco logs)
            ts_val = None
            if params.timestamp_field and params.timestamp_field in kv_dict:
                ts_val = kv_dict[params.timestamp_field]
            elif "date" in kv_dict and "time" in kv_dict:
                ts_val = f"{kv_dict['date']} {kv_dict['time']}"
            else:
                for cand in ("timestamp", "time", "@timestamp", "ts", "datetime"):
                    if cand in kv_dict:
                        ts_val = kv_dict[cand]
                        break

            dt_utc = parse_timestamp_to_utc(ts_val, params.timestamp_format)
            kv_dict["raw_line"] = line

            observations.append(
                {
                    "timestamp_utc": dt_utc,
                    "source_location": f"line:{line_idx}",
                    "source_id": source_id,
                    "normalized_content": kv_dict,
                }
            )

        return observations, errors, truncated

    def _parse_custom_regex(
        self,
        params: LogCsvParserParameters,
        lines: list[str],
        source_id: uuid.UUID | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        """Parse logs using custom regular expression with named groups."""
        if not params.custom_regex:
            raise ValidationException(
                "Le paramètre 'custom_regex' est obligatoire pour ce préréglage."
            )

        try:
            pattern = re.compile(params.custom_regex)
        except re.error as exc:
            raise ValidationException(f"Expression régulière invalide: {exc}") from exc

        observations: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        truncated = False

        for line_idx, line in enumerate(lines, start=1):
            if len(observations) >= params.max_records:
                truncated = True
                break
            if not line.strip():
                continue

            match = pattern.search(line)
            if not match:
                errors.append(
                    {
                        "line": line_idx,
                        "error": "Ligne non concordante avec custom_regex",
                        "raw": line,
                    }
                )
                continue

            group_dict = match.groupdict()
            if not group_dict:
                group_dict = {"match": match.group(0), "groups": list(match.groups())}

            # Search for timestamp
            ts_val = None
            if params.timestamp_field and params.timestamp_field in group_dict:
                ts_val = group_dict[params.timestamp_field]
            elif "timestamp" in group_dict:
                ts_val = group_dict["timestamp"]
            elif "time" in group_dict:
                ts_val = group_dict["time"]
            elif "date" in group_dict:
                ts_val = group_dict["date"]
            else:
                for v in group_dict.values():
                    cand = parse_timestamp_to_utc(v, params.timestamp_format)
                    if cand is not None:
                        ts_val = v
                        break

            dt_utc = parse_timestamp_to_utc(ts_val, params.timestamp_format) if ts_val else None
            group_dict["raw_line"] = line

            observations.append(
                {
                    "timestamp_utc": dt_utc,
                    "source_location": f"line:{line_idx}",
                    "source_id": source_id,
                    "normalized_content": group_dict,
                }
            )

        return observations, errors, truncated

    def _parse_generic(
        self,
        params: LogCsvParserParameters,
        lines: list[str],
        source_id: uuid.UUID | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        """Fallback generic line-by-line parser with IP and timestamp heuristics."""
        observations: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        truncated = False

        for line_idx, line in enumerate(lines, start=1):
            if len(observations) >= params.max_records:
                truncated = True
                break
            if not line.strip():
                continue

            ips = IP_REGEX.findall(line)
            # Try to detect any timestamp in line (regex search first, token fallback)
            dt_utc = None
            m_dt = GENERIC_DATETIME_REGEX.search(line)
            if m_dt:
                dt_utc = parse_timestamp_to_utc(m_dt.group(0), params.timestamp_format)

            if dt_utc is None:
                words = line.split()
                for w in words:
                    dt_cand = parse_timestamp_to_utc(w, params.timestamp_format)
                    if dt_cand:
                        dt_utc = dt_cand
                        break

            normalized: dict[str, Any] = {
                "message": line.strip(),
                "raw_line": line,
            }
            if ips:
                normalized["ip"] = ips[0]
                if len(ips) > 1:
                    normalized["all_ips"] = ips

            observations.append(
                {
                    "timestamp_utc": dt_utc,
                    "source_location": f"line:{line_idx}",
                    "source_id": source_id,
                    "normalized_content": normalized,
                }
            )

        return observations, errors, truncated
