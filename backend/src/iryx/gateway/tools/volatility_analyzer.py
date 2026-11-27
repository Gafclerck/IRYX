"""Forensic memory analyzer tool using Volatility 3 in air-gapped offline mode."""

import json
import logging
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from iryx.core.config import get_settings
from iryx.core.exceptions import (
    PluginNotWhitelistedException,
    ToolExecutionFailedException,
    ValidationException,
)
from iryx.gateway.base import (
    BaseTool,
    ToolExecutionContext,
    ToolExecutionResult,
    resolve_confined_evidence_path,
)
from iryx.gateway.models import ToolExecutionStatus
from iryx.gateway.runner import run_command_safely

logger = logging.getLogger("iryx.gateway.tools.volatility_analyzer")

VOLATILITY_VERSION = "2.7.0"

# Strict whitelist of 5 authorized plugins (and variants/aliases) per FR15, D-26
AUTHORIZED_PLUGINS: dict[str, str] = {
    "windows.info": "windows.info",
    "windows.pslist": "windows.pslist",
    "windows.pstree": "windows.pstree",
    "windows.cmdline": "windows.cmdline",
    "windows.netscan": "windows.netscan",
    "windows.malfind": "windows.malfind",
    "windows.malware.malfind": "windows.malfind",
}


class VolatilityExecutionError(ToolExecutionFailedException):
    """Raised when Volatility 3 execution fails, dump is corrupted, or output cannot be parsed."""

    def __init__(self, message: str = "Erreur lors de l'exécution de Volatility 3.") -> None:
        super().__init__(message=message, code="VOLATILITY_EXECUTION_ERROR")


def parse_utc_datetime(val: Any) -> datetime | None:
    """Parse date/time value into a timezone-aware UTC datetime."""
    if not val:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=UTC)
        return val.astimezone(UTC)
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str or val_str.lower() in ("n/a", "none", "null", "-", "disabled"):
            return None
        # Replace Z with +00:00 for fromisoformat compatibility
        clean = val_str.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(clean)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except Exception:
            pass
        # Try common strptime fallbacks
        for fmt in (
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S.%f%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y/%m/%d %H:%M:%S",
            "%a %b %d %H:%M:%S %Y",
        ):
            try:
                dt = datetime.strptime(val_str, fmt)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=UTC)
                return dt.astimezone(UTC)
            except Exception:
                continue
    return None


def extract_tree_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recursively extract and flatten nodes from hierarchical structures (e.g., pstree)."""
    flattened: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        flattened.append(node)
        children = node.get("__children")
        if isinstance(children, list) and children:
            flattened.extend(extract_tree_nodes(children))
    return flattened


def normalize_windows_info(
    records: list[dict[str, Any]],
    source_id: uuid.UUID | None,
    source_loc: str,
    symbols_path: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize output of the windows.info plugin into OS observations."""
    info_dict: dict[str, Any] = {}
    for row in records:
        if not isinstance(row, dict):
            continue
        if "Variable" in row and "Value" in row:
            info_dict[str(row["Variable"])] = row["Value"]
        else:
            info_dict.update(row)

    if not info_dict:
        return [], []

    kernel_base = info_dict.get("Kernel Base") or info_dict.get("kernel_base")
    nt_build = info_dict.get("NT Build") or info_dict.get("nt_build")
    system_time_raw = info_dict.get("SystemTime") or info_dict.get("system_time")
    timestamp_utc = parse_utc_datetime(system_time_raw)

    normalized_content = {
        "tool_name": "volatility3",
        "volatility_version": VOLATILITY_VERSION,
        "plugin_name": "windows.info",
        "symbols_path": symbols_path,
        "kernel_base": kernel_base,
        "nt_build": nt_build,
        "system_time": system_time_raw,
        "raw_info": info_dict,
    }

    obs = {
        "source_id": source_id,
        "source_location": source_loc,
        "timestamp_utc": timestamp_utc,
        "normalized_content": normalized_content,
    }

    return [obs], [info_dict]


def normalize_windows_pslist(
    records: list[dict[str, Any]],
    plugin_name: str,
    source_id: uuid.UUID | None,
    source_loc: str,
    symbols_path: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize output of windows.pslist / windows.pstree into process observations."""
    flat_rows = extract_tree_nodes(records)
    observations: list[dict[str, Any]] = []
    parsed_records: list[dict[str, Any]] = []

    for row in flat_rows:
        pid = row.get("PID")
        ppid = row.get("PPID")
        image_name = row.get("ImageFileName") or row.get("Process")
        offset = row.get("Offset(V)") or row.get("Offset(P)") or row.get("Offset")
        threads = row.get("Threads")
        handles = row.get("Handles")
        session_id = row.get("SessionId")
        wow64 = row.get("Wow64")
        create_time_raw = row.get("CreateTime")
        exit_time_raw = row.get("ExitTime")
        cmd = row.get("Cmd")
        path = row.get("Path")
        audit = row.get("Audit")

        create_dt = parse_utc_datetime(create_time_raw)
        exit_dt = parse_utc_datetime(exit_time_raw)

        create_time_iso = (
            create_dt.isoformat()
            if create_dt
            else (str(create_time_raw) if create_time_raw else None)
        )
        exit_time_iso = (
            exit_dt.isoformat() if exit_dt else (str(exit_time_raw) if exit_time_raw else None)
        )

        normalized_content = {
            "tool_name": "volatility3",
            "volatility_version": VOLATILITY_VERSION,
            "plugin_name": plugin_name,
            "symbols_path": symbols_path,
            "pid": pid,
            "ppid": ppid,
            "image_file_name": image_name,
            "offset": offset,
            "threads": threads,
            "handles": handles,
            "session_id": session_id,
            "wow64": wow64,
            "create_time_utc": create_time_iso,
            "exit_time_utc": exit_time_iso,
            "cmd": cmd,
            "path": path,
            "audit": audit,
        }

        obs = {
            "source_id": source_id,
            "source_location": source_loc,
            "timestamp_utc": create_dt,
            "normalized_content": normalized_content,
        }
        observations.append(obs)

        record_entry = {
            "pid": pid,
            "ppid": ppid,
            "image_file_name": image_name,
            "threads": threads,
            "handles": handles,
            "create_time_utc": create_dt.isoformat() if create_dt else None,
            "exit_time_utc": exit_dt.isoformat() if exit_dt else None,
            "cmd": cmd,
            "path": path,
        }
        parsed_records.append(record_entry)

    return observations, parsed_records


def normalize_windows_cmdline(
    records: list[dict[str, Any]],
    source_id: uuid.UUID | None,
    source_loc: str,
    symbols_path: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize output of windows.cmdline into command-line observations."""
    flat_rows = extract_tree_nodes(records)
    observations: list[dict[str, Any]] = []
    parsed_records: list[dict[str, Any]] = []

    for row in flat_rows:
        pid = row.get("PID")
        process = row.get("Process") or row.get("ImageFileName")
        args = row.get("Args") or row.get("CommandLine") or row.get("Cmd")

        normalized_content = {
            "tool_name": "volatility3",
            "volatility_version": VOLATILITY_VERSION,
            "plugin_name": "windows.cmdline",
            "symbols_path": symbols_path,
            "pid": pid,
            "process_name": process,
            "args": args,
        }

        obs = {
            "source_id": source_id,
            "source_location": source_loc,
            "timestamp_utc": None,
            "normalized_content": normalized_content,
        }
        observations.append(obs)

        parsed_records.append(
            {
                "pid": pid,
                "process_name": process,
                "args": args,
            }
        )

    return observations, parsed_records


def normalize_windows_netscan(
    records: list[dict[str, Any]],
    source_id: uuid.UUID | None,
    source_loc: str,
    symbols_path: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize output of windows.netscan into network connection observations."""
    flat_rows = extract_tree_nodes(records)
    observations: list[dict[str, Any]] = []
    parsed_records: list[dict[str, Any]] = []

    for row in flat_rows:
        offset = row.get("Offset")
        proto = row.get("Proto")
        local_addr = row.get("LocalAddr")
        local_port = row.get("LocalPort")
        foreign_addr = row.get("ForeignAddr")
        foreign_port = row.get("ForeignPort")
        state = row.get("State")
        pid = row.get("PID")
        owner = row.get("Owner")
        created_raw = row.get("Created")
        created_dt = parse_utc_datetime(created_raw)

        created_time_iso = (
            created_dt.isoformat() if created_dt else (str(created_raw) if created_raw else None)
        )

        normalized_content = {
            "tool_name": "volatility3",
            "volatility_version": VOLATILITY_VERSION,
            "plugin_name": "windows.netscan",
            "symbols_path": symbols_path,
            "offset": offset,
            "proto": proto,
            "local_addr": local_addr,
            "local_port": local_port,
            "foreign_addr": foreign_addr,
            "foreign_port": foreign_port,
            "state": state,
            "pid": pid,
            "owner": owner,
            "created_utc": created_time_iso,
        }

        obs = {
            "source_id": source_id,
            "source_location": source_loc,
            "timestamp_utc": created_dt,
            "normalized_content": normalized_content,
        }
        observations.append(obs)

        parsed_records.append(
            {
                "pid": pid,
                "owner": owner,
                "proto": proto,
                "local_addr": local_addr,
                "local_port": local_port,
                "foreign_addr": foreign_addr,
                "foreign_port": foreign_port,
                "state": state,
                "created_utc": created_dt.isoformat() if created_dt else None,
            }
        )

    return observations, parsed_records


def normalize_windows_malfind(
    records: list[dict[str, Any]],
    plugin_name: str,
    source_id: uuid.UUID | None,
    source_loc: str,
    symbols_path: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize output of windows.malfind into injected code observations."""
    flat_rows = extract_tree_nodes(records)
    observations: list[dict[str, Any]] = []
    parsed_records: list[dict[str, Any]] = []

    for row in flat_rows:
        pid = row.get("PID")
        process = row.get("Process") or row.get("ImageFileName")
        start_vpn = row.get("Start VPN") or row.get("Start")
        end_vpn = row.get("End VPN") or row.get("End")
        tag = row.get("Tag")
        protection = row.get("Protection")
        commit_charge = row.get("CommitCharge")
        private_memory = row.get("PrivateMemory")
        notes = row.get("Notes")
        hexdump = row.get("Hexdump")
        disasm = row.get("Disasm")

        normalized_content = {
            "tool_name": "volatility3",
            "volatility_version": VOLATILITY_VERSION,
            "plugin_name": plugin_name,
            "symbols_path": symbols_path,
            "pid": pid,
            "process_name": process,
            "start_vpn": start_vpn,
            "end_vpn": end_vpn,
            "tag": tag,
            "protection": protection,
            "commit_charge": commit_charge,
            "private_memory": private_memory,
            "notes": notes,
            "hexdump": hexdump,
            "disasm": disasm,
        }

        obs = {
            "source_id": source_id,
            "source_location": source_loc,
            "timestamp_utc": None,
            "normalized_content": normalized_content,
        }
        observations.append(obs)

        parsed_records.append(
            {
                "pid": pid,
                "process_name": process,
                "start_vpn": start_vpn,
                "end_vpn": end_vpn,
                "tag": tag,
                "protection": protection,
                "commit_charge": commit_charge,
                "private_memory": private_memory,
            }
        )

    return observations, parsed_records


class Volatility3Parameters(BaseModel):
    """Input parameters schema for Volatility3Tool with strict attribute rejection."""

    evidence_id: uuid.UUID | None = Field(
        default=None,
        description="Identifiant UUID de la preuve scellée (image RAM) à analyser.",
    )
    file_path: str | None = Field(
        default=None,
        description="Chemin local du fichier dump de mémoire vive à analyser.",
    )
    plugin_name: str = Field(
        ...,
        description="Nom du plugin Volatility 3 à exécuter (parmi les 5 autorisés).",
    )
    plugin_args: list[str] = Field(
        default_factory=list,
        description="Arguments additionnels passés au plugin Volatility 3.",
    )
    max_results: int = Field(
        default=5000,
        ge=1,
        le=50000,
        description="Nombre maximal d'observations à extraire (1 à 50000, défaut 5000).",
    )
    symbols_path: str | None = Field(
        default=None,
        description="Chemin du répertoire local contenant les tables de symboles ISF.",
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_sources(self) -> "Volatility3Parameters":
        """Validate that at least one data source is supplied."""
        if not self.evidence_id and not self.file_path:
            raise ValueError(
                "Au moins une source de données doit être fournie: 'evidence_id' ou 'file_path'."
            )
        return self


class Volatility3Tool(BaseTool):
    """Forensic memory analyzer tool using Volatility 3 in air-gapped offline mode."""

    name: str = "analyze_memory"
    version: str = "2.7.0"
    description: str = (
        "Analyseur forensique de mémoire vive Volatility 3 hors-ligne avec symboles ISF "
        "et normalisation des observations."
    )
    timeout_seconds: int = 600
    parameters_schema: type[BaseModel] = Volatility3Parameters

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
        """Execute Volatility 3 plugin against a memory image in offline mode."""
        if not isinstance(params, Volatility3Parameters):
            try:
                params = Volatility3Parameters.model_validate(params)
            except Exception as exc:
                raise ValidationException(
                    f"Paramètres non conformes pour Volatility3Tool: {exc}"
                ) from exc

        # 1. Enforce strict plugin whitelist before any disk or process execution
        clean_plugin = params.plugin_name.strip().lower()
        if clean_plugin not in AUTHORIZED_PLUGINS:
            allowed_list = ", ".join(sorted(set(AUTHORIZED_PLUGINS.values())))
            raise PluginNotWhitelistedException(
                f"Le plugin '{params.plugin_name}' n'est pas autorisé par la liste blanche "
                f"de Volatility 3. Plugins autorisés: {allowed_list}."
            )
        actual_plugin = AUTHORIZED_PLUGINS[clean_plugin]

        # 2. Resolve source memory dump file path and evidence identifier
        target_path, source_id = self._resolve_source(params, context)

        # 3. Determine ISF symbols directory
        settings = get_settings()
        symbols_path = params.symbols_path or settings.volatility_symbols_path

        # 4. Construct strictly isolated command without shell (shell=False)
        cmd_runner_code = (
            "import sys, volatility3.cli; "
            "sys.argv = ['volatility'] + sys.argv[1:]; "
            "volatility3.cli.main()"
        )
        cmd = [
            sys.executable,
            "-c",
            cmd_runner_code,
            "-q",
            "--offline",
            "-r",
            "json",
            "-s",
            str(symbols_path),
            "-f",
            str(target_path),
            actual_plugin,
            *params.plugin_args,
        ]

        logger.info(
            "Executing Volatility 3 tool '%s' with plugin '%s' on '%s' (symbols: '%s')",
            self.name,
            actual_plugin,
            target_path.name,
            symbols_path,
        )

        returncode, stdout_bytes, stderr_bytes = await run_command_safely(
            cmd=cmd,
            timeout=float(self.timeout_seconds),
        )

        if returncode != 0:
            err_text = stderr_bytes.decode("utf-8", errors="replace").strip()
            if not err_text:
                err_text = stdout_bytes.decode("utf-8", errors="replace").strip()
            if not err_text:
                err_text = f"Le processus Volatility 3 s'est terminé avec le code {returncode}."
            logger.warning(
                "Volatility 3 execution failed with code %d: %s",
                returncode,
                err_text,
            )
            raise VolatilityExecutionError(
                f"Échec de l'exécution de Volatility 3 (code {returncode}): {err_text}"
            )

        # 5. Parse JSON structured output
        raw_stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        records: list[dict[str, Any]] = []

        if raw_stdout:
            # Robust extraction of JSON payload, skipping any leading log prefixes (e.g. [WARNING])
            parsed = False
            for start_char, end_char, is_list in (("[", "]", True), ("{", "}", False)):
                pos = 0
                while True:
                    start_idx = raw_stdout.find(start_char, pos)
                    if start_idx == -1:
                        break
                    end_idx = raw_stdout.rfind(end_char)
                    if end_idx > start_idx:
                        candidate = raw_stdout[start_idx : end_idx + 1]
                        try:
                            candidate_obj = json.loads(candidate)
                            if is_list and isinstance(candidate_obj, list):
                                records = candidate_obj
                                parsed = True
                                break
                            elif not is_list and isinstance(candidate_obj, dict):
                                records = [candidate_obj]
                                parsed = True
                                break
                        except Exception:
                            pass
                    pos = start_idx + 1
                if parsed:
                    break

            if not parsed:
                raise VolatilityExecutionError(
                    f"Format de sortie Volatility 3 inattendu (JSON attendu): {raw_stdout[:200]}"
                )

        # 6. Normalize observations according to plugin type
        source_loc = str(target_path.name)[:512]

        if actual_plugin == "windows.info":
            observations, parsed_records = normalize_windows_info(
                records, source_id, source_loc, str(symbols_path)
            )
        elif actual_plugin in ("windows.pslist", "windows.pstree"):
            observations, parsed_records = normalize_windows_pslist(
                records, actual_plugin, source_id, source_loc, str(symbols_path)
            )
        elif actual_plugin == "windows.cmdline":
            observations, parsed_records = normalize_windows_cmdline(
                records, source_id, source_loc, str(symbols_path)
            )
        elif actual_plugin == "windows.netscan":
            observations, parsed_records = normalize_windows_netscan(
                records, source_id, source_loc, str(symbols_path)
            )
        elif actual_plugin == "windows.malfind":
            observations, parsed_records = normalize_windows_malfind(
                records, actual_plugin, source_id, source_loc, str(symbols_path)
            )
        else:
            raise PluginNotWhitelistedException(
                f"Plugin non supporté pour la normalisation: '{actual_plugin}'."
            )

        # 7. Contextual truncation according to max_results limit
        total_count = len(observations)
        truncated = False
        if total_count > params.max_results:
            observations = observations[: params.max_results]
            parsed_records = parsed_records[: params.max_results]
            truncated = True

        raw_output = {
            "plugin_name": actual_plugin,
            "volatility_version": VOLATILITY_VERSION,
            "symbols_path": str(symbols_path),
            "total_records": total_count,
            "records": parsed_records,
        }

        metadata = {
            "volatility_version": VOLATILITY_VERSION,
            "plugin_name": actual_plugin,
            "symbols_path": str(symbols_path),
            "total_records": total_count,
            "truncated": truncated,
        }

        return ToolExecutionResult(
            raw_output=raw_output,
            observations=observations,
            metadata=metadata,
            status=ToolExecutionStatus.SUCCESS,
        )

    def _resolve_source(
        self,
        params: Volatility3Parameters,
        context: ToolExecutionContext,
    ) -> tuple[Path, uuid.UUID | None]:
        """Resolve physical memory dump file path and associated evidence identifier."""
        source_id = params.evidence_id or context.evidence_id

        if params.file_path is not None:
            path = resolve_confined_evidence_path(params.file_path)
            if not path.exists():
                raise ValidationException(
                    f"Fichier image mémoire introuvable: '{params.file_path}'."
                )
            if not path.is_file():
                raise ValidationException(
                    f"Chemin source invalide (doit être un fichier régulier): '{params.file_path}'."
                )
            return path, source_id

        if params.evidence_id is not None:
            settings = get_settings()
            staging_dir = Path(settings.evidence_staging_path)
            storage_dir = Path(settings.evidence_storage_path)

            candidates = [
                staging_dir / f"{params.evidence_id}.raw",
                staging_dir / f"{params.evidence_id}.dmp",
                staging_dir / f"{params.evidence_id}.bin",
                staging_dir / str(params.evidence_id),
                storage_dir / f"{params.evidence_id}.raw",
                storage_dir / f"{params.evidence_id}.dmp",
                storage_dir / f"{params.evidence_id}.bin",
                storage_dir / str(params.evidence_id),
            ]
            target_path: Path | None = None
            for candidate in candidates:
                if candidate.exists() and candidate.is_file():
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
