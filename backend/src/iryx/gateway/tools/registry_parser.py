"""Forensic Windows Registry hive parser tool via regipy with UTC normalization."""

import codecs
import contextlib
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from regipy.exceptions import RegistryKeyNotFoundException
from regipy.registry import RegistryHive

from iryx.core.config import get_settings
from iryx.core.exceptions import ToolExecutionFailedException, ValidationException
from iryx.gateway.base import BaseTool, ToolExecutionContext, ToolExecutionResult
from iryx.gateway.models import ToolExecutionStatus

logger = logging.getLogger("iryx.gateway.tools.registry_parser")

REGISTRY_MAGIC = b"regf"

AllowedHiveType = Literal[
    "auto",
    "system",
    "software",
    "ntuser",
    "sam",
    "security",
    "usrclass",
    "amcache",
]

DEFAULT_KEY_PATHS: dict[str, list[str]] = {
    "software": [
        r"\Microsoft\Windows\CurrentVersion\Run",
        r"\Microsoft\Windows\CurrentVersion\RunOnce",
        r"\Wow6432Node\Microsoft\Windows\CurrentVersion\Run",
        r"\Wow6432Node\Microsoft\Windows\CurrentVersion\RunOnce",
        r"\Microsoft\Windows NT\CurrentVersion\Winlogon",
    ],
    "system": [
        r"\CurrentControlSet\Services",
        r"\CurrentControlSet\Control\ComputerName\ComputerName",
    ],
    "ntuser": [
        r"\Software\Microsoft\Windows\CurrentVersion\Run",
        r"\Software\Microsoft\Windows\CurrentVersion\RunOnce",
        r"\Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist",
    ],
    "sam": [
        r"\SAM\Domains\Account\Users\Names",
    ],
}


class RegistryHiveParsingError(ToolExecutionFailedException):
    """Raised when a registry hive is unreadable, corrupted, or has an invalid header."""

    def __init__(self, message: str = "Erreur lors de l'analyse de la ruche de Registre.") -> None:
        super().__init__(message=message, code="REGISTRY_HIVE_PARSING_ERROR")


def filetime_to_utc(ft: int | None) -> datetime | None:
    """Convert Windows 64-bit FILETIME (100-ns intervals) to timezone-aware UTC datetime."""
    if not ft or ft <= 0 or ft == 0x7FFFFFFFFFFFFFFF:
        return None
    try:
        return datetime(1601, 1, 1, tzinfo=UTC) + timedelta(microseconds=ft // 10)
    except (OverflowError, ValueError, OSError):
        return None


def normalize_key_path(path: str) -> str:
    """Normalize registry key path with single leading backslash and strip hive root prefixes."""
    cleaned = path.strip().replace("/", "\\")
    if not cleaned.startswith("\\"):
        cleaned = "\\" + cleaned
    cleaned = re.sub(r"\\+", r"\\", cleaned)
    if len(cleaned) > 1 and cleaned.endswith("\\"):
        cleaned = cleaned.rstrip("\\")

    # Strip redundant standard hive prefixes (e.g. \HKLM\, \HKCU\)
    hive_prefixes = (
        "\\hkey_local_machine\\",
        "\\hkey_current_user\\",
        "\\hkey_users\\",
        "\\hkey_classes_root\\",
        "\\hklm\\",
        "\\hkcu\\",
        "\\hku\\",
        "\\hkcr\\",
    )
    cleaned_lower = cleaned.lower()
    for prefix in hive_prefixes:
        if cleaned_lower.startswith(prefix):
            cleaned = "\\" + cleaned[len(prefix) :]
            break

    return cleaned


def is_user_assist_count(key_path: str) -> bool:
    """Check if key path is under UserAssist\\...\\Count."""
    norm = key_path.lower()
    return "userassist" in norm and (norm.endswith(r"\count") or "\\count\\" in norm)


def normalize_value_data(raw_value: Any) -> tuple[Any, bool]:
    """Normalize registry value data to ensure JSONB serialization and enforce size limits."""
    if raw_value is None:
        return None, False

    if isinstance(raw_value, datetime):
        return raw_value.isoformat(), False

    if isinstance(raw_value, bytes):
        if len(raw_value) > 4096:
            return raw_value[:4096].hex(), True
        return raw_value.hex(), False

    if isinstance(raw_value, str):
        cleaned = raw_value.replace("\x00", "")
        if len(cleaned) > 4096:
            return cleaned[:4096], True
        return cleaned, False

    if isinstance(raw_value, list):
        cleaned_list: list[Any] = []
        truncated = False
        for item in raw_value[:500]:
            if isinstance(item, bytes):
                if len(item) > 4096:
                    cleaned_list.append(item[:4096].hex())
                    truncated = True
                else:
                    cleaned_list.append(item.hex())
            elif isinstance(item, str):
                cleaned_item = item.replace("\x00", "")
                if len(cleaned_item) > 4096:
                    cleaned_list.append(cleaned_item[:4096])
                    truncated = True
                else:
                    cleaned_list.append(cleaned_item)
            elif isinstance(item, datetime):
                cleaned_list.append(item.isoformat())
            else:
                cleaned_list.append(item)
        if len(raw_value) > 500:
            truncated = True
        return cleaned_list, truncated

    if isinstance(raw_value, (int, float, bool)):
        return raw_value, False

    # Fallback for unexpected objects
    val_str = str(raw_value).replace("\x00", "")
    if len(val_str) > 4096:
        return val_str[:4096], True
    return val_str, False


class RegistryParserParameters(BaseModel):
    """Input parameters schema for RegistryParserTool."""

    evidence_id: uuid.UUID | None = Field(
        default=None,
        description="Identifiant UUID de la preuve scellée à analyser.",
    )
    file_path: str | None = Field(
        default=None,
        description="Chemin local du fichier de ruche de Registre à analyser.",
    )
    hive_type: AllowedHiveType = Field(
        default="auto",
        description=(
            "Type de ruche Windows (auto, system, software, ntuser, sam, security, "
            "usrclass, amcache)."
        ),
    )
    key_paths: list[str] | None = Field(
        default=None,
        max_length=50,
        description="Liste de chemins de clés de registre à analyser (max 50).",
    )
    recursive: bool = Field(
        default=True,
        description="Indique s'il faut parcourir récursivement les sous-clés.",
    )
    max_depth: int = Field(
        default=10,
        ge=1,
        le=32,
        description="Profondeur maximale de récursion (1 à 32, défaut 10).",
    )
    max_values: int = Field(
        default=5000,
        ge=1,
        le=50000,
        description="Nombre maximal de valeurs à extraire (1 à 50000, défaut 5000).",
    )
    search_query: str | None = Field(
        default=None,
        description="Filtre textuel insensible à la casse sur les clés, noms ou données.",
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_sources(self) -> "RegistryParserParameters":
        """Validate at least one source is supplied."""
        if not self.evidence_id and not self.file_path:
            raise ValueError(
                "Au moins une source de données doit être fournie: 'evidence_id' ou 'file_path'."
            )
        return self


class RegistryParserTool(BaseTool):
    """Forensic Windows Registry hive parser tool via regipy with UTC normalization."""

    name: str = "parse_registry"
    version: str = "1.0.0"
    description: str = (
        "Analyseur forensique de ruches de Registre Windows pur Python via regipy "
        "avec normalisation UTC et extraction d'observations."
    )
    timeout_seconds: int = 120
    parameters_schema: type[BaseModel] = RegistryParserParameters

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
        """Execute registry hive parsing logic under passive forensic boundaries."""
        if not isinstance(params, RegistryParserParameters):
            try:
                params = RegistryParserParameters.model_validate(params)
            except Exception as e:
                raise ValidationException(
                    f"Paramètres invalides pour RegistryParserTool: {e}"
                ) from e

        # 1. Resolve source file path and evidence identifier
        target_path, source_id = self._resolve_source(params, context)

        # 2. Strict file integrity and header validation (raises RegistryHiveParsingError)
        self._validate_registry_header(target_path)

        # 3. Open hive with regipy
        try:
            hive = RegistryHive(str(target_path))
        except OSError as exc:
            raise RegistryHiveParsingError(
                f"Erreur d'accès ou fichier de ruche verrouillé: {exc}"
            ) from exc
        except Exception as exc:
            raise RegistryHiveParsingError(
                f"Erreur lors de l'ouverture de la ruche de Registre: {exc}"
            ) from exc

        # 4. Determine effective hive type
        effective_hive_type = self._detect_hive_type(hive, target_path, params.hive_type)

        # 5. Resolve target key paths (user supplied or presets)
        target_key_paths: list[str] = []
        if params.key_paths:
            target_key_paths = [normalize_key_path(p) for p in params.key_paths if p and p.strip()]

        if not target_key_paths:
            if effective_hive_type and effective_hive_type in DEFAULT_KEY_PATHS:
                target_key_paths = list(DEFAULT_KEY_PATHS[effective_hive_type])
            else:
                raise ValidationException(
                    f"Type de ruche non déterminable ('{effective_hive_type or 'auto'}') "
                    f"sans presets par défaut et aucun 'key_paths' fourni."
                )

        # Deduplicate target key paths while preserving order
        seen_paths: set[str] = set()
        deduped_paths: list[str] = []
        for kp in target_key_paths:
            normalized_kp = normalize_key_path(kp)
            if normalized_kp.lower() not in seen_paths:
                seen_paths.add(normalized_kp.lower())
                deduped_paths.append(normalized_kp)
        target_key_paths = deduped_paths

        # 6. Resolve CurrentControlSet if hive is system or references CurrentControlSet
        control_set_name = "ControlSet001"
        if effective_hive_type == "system" or any(
            "currentcontrolset" in p.lower() for p in target_key_paths
        ):
            control_set_name = self._resolve_control_set(hive)

        resolved_key_paths: list[str] = []
        for p in target_key_paths:
            norm_p = normalize_key_path(p)
            if norm_p.lower().startswith("\\currentcontrolset\\"):
                norm_p = rf"\{control_set_name}" + norm_p[len(r"\currentcontrolset") :]
            elif norm_p.lower() == r"\currentcontrolset":
                norm_p = rf"\{control_set_name}"
            resolved_key_paths.append(norm_p)

        # 7. Perform DFS traversal on resolved key paths
        observations: list[dict[str, Any]] = []
        missing_keys: list[str] = []
        errors: list[dict[str, Any]] = []
        keys_visited = 0
        truncated = False
        visited_keys: set[str] = set()

        for root_path in resolved_key_paths:
            if truncated:
                break

            try:
                root_node = hive.get_key(root_path)
            except RegistryKeyNotFoundException:
                # Fallback for software hive root prefix variations
                alt_node = None
                if effective_hive_type == "software":
                    if root_path.lower().startswith("\\software\\"):
                        alt_path = root_path[len(r"\software") :]
                        with contextlib.suppress(Exception):
                            alt_node = hive.get_key(alt_path)
                            if alt_node:
                                root_node = alt_node
                                root_path = alt_path
                    elif not root_path.lower().startswith("\\software\\"):
                        alt_path = rf"\Software{root_path}"
                        with contextlib.suppress(Exception):
                            alt_node = hive.get_key(alt_path)
                            if alt_node:
                                root_node = alt_node
                                root_path = alt_path

                if alt_node is None:
                    missing_keys.append(root_path)
                    continue
            except Exception as exc:
                errors.append({"key_path": root_path, "error": str(exc)})
                continue

            # Stack for DFS: (key_node, key_path, current_depth)
            stack: list[tuple[Any, str, int]] = [(root_node, root_path, 0)]
            while stack and not truncated:
                current_node, current_path, current_depth = stack.pop()
                current_path_lower = current_path.lower()
                if current_path_lower in visited_keys:
                    continue
                visited_keys.add(current_path_lower)
                keys_visited += 1

                # Extract last_write_time of the key
                last_modified_ft = getattr(
                    getattr(current_node, "header", None), "last_modified", None
                )
                dt_utc = filetime_to_utc(last_modified_ft)
                time_utc_str = dt_utc.isoformat() if dt_utc else None

                # Extract values from current key
                values_iter = None
                try:
                    values_iter = current_node.iter_values(as_json=False, trim_values=False)
                except Exception as exc:
                    errors.append(
                        {"key_path": current_path, "error": f"Erreur de lecture des valeurs: {exc}"}
                    )

                if values_iter is not None:
                    while True:
                        try:
                            val = next(values_iter)
                        except StopIteration:
                            break
                        except Exception as exc:
                            errors.append(
                                {
                                    "key_path": current_path,
                                    "error": f"Valeur corrompue ou illisible: {exc}",
                                }
                            )
                            continue

                        val_name = str(getattr(val, "name", ""))
                        val_type = str(getattr(val, "value_type", ""))
                        raw_data = getattr(val, "value", None)

                        val_data, val_data_truncated = normalize_value_data(raw_data)

                        if not self._matches_search_query(
                            params.search_query, current_path, val_name, val_data
                        ):
                            continue

                        if len(observations) >= params.max_values:
                            truncated = True
                            break

                        is_user_assist = is_user_assist_count(current_path)

                        normalized_content: dict[str, Any] = {
                            "hive_type": effective_hive_type or "unknown",
                            "key_path": current_path,
                            "value_name": val_name,
                            "value_data": val_data,
                            "value_type": val_type,
                            "last_write_time_utc": time_utc_str,
                            "is_corrupted": bool(getattr(val, "is_corrupted", False)),
                            "value_data_truncated": val_data_truncated,
                        }
                        if is_user_assist:
                            normalized_content["decoded_value_name"] = codecs.decode(
                                val_name, "rot-13"
                            )

                        observations.append(
                            {
                                "source_id": source_id,
                                "source_location": current_path[:512],
                                "timestamp_utc": dt_utc,
                                "normalized_content": normalized_content,
                            }
                        )

                # Expand subkeys if recursive and within max_depth
                if params.recursive and current_depth < params.max_depth and not truncated:
                    try:
                        subkeys_iter = current_node.iter_subkeys()
                    except Exception as exc:
                        errors.append(
                            {
                                "key_path": current_path,
                                "error": f"Erreur de parcours des sous-clés: {exc}",
                            }
                        )
                        subkeys_iter = None

                    if subkeys_iter is not None:
                        subkeys = []
                        while True:
                            try:
                                sk = next(subkeys_iter)
                                subkeys.append(sk)
                            except StopIteration:
                                break
                            except Exception as exc:
                                errors.append(
                                    {
                                        "key_path": current_path,
                                        "error": f"Sous-clé corrompue: {exc}",
                                    }
                                )
                                break

                        for sk in reversed(subkeys):
                            sk_name = getattr(sk, "name", "")
                            sk_path = (
                                f"\\{sk_name}"
                                if current_path == "\\"
                                else f"{current_path}\\{sk_name}"
                            )
                            if sk_path.lower() not in visited_keys:
                                stack.append((sk, sk_path, current_depth + 1))

        raw_output = {
            "hive_type": effective_hive_type or "unknown",
            "keys_visited": keys_visited,
            "values_count": len(observations),
            "values": [
                {
                    "key": obs["normalized_content"]["key_path"],
                    "name": obs["normalized_content"]["value_name"],
                    "value_type": obs["normalized_content"]["value_type"],
                    "data": obs["normalized_content"]["value_data"],
                    "last_written_utc": obs["normalized_content"]["last_write_time_utc"],
                    **(
                        {"decoded_name": obs["normalized_content"]["decoded_value_name"]}
                        if "decoded_value_name" in obs["normalized_content"]
                        else {}
                    ),
                }
                for obs in observations
            ],
        }

        metadata = {
            "parsed_values_count": len(observations),
            "keys_visited": keys_visited,
            "truncated": truncated,
            "missing_keys": missing_keys,
            "errors": errors,
            "resolved_key_paths": resolved_key_paths,
        }

        return ToolExecutionResult(
            raw_output=raw_output,
            observations=observations,
            metadata=metadata,
            status=ToolExecutionStatus.SUCCESS,
        )

    def _resolve_source(
        self,
        params: RegistryParserParameters,
        context: ToolExecutionContext,
    ) -> tuple[Path, uuid.UUID | None]:
        """Resolve physical registry hive file path and associated evidence_id."""
        source_id = params.evidence_id or context.evidence_id

        if params.file_path is not None:
            path = Path(params.file_path)
            if not path.is_file():
                raise ValidationException(f"Fichier de Registre introuvable: '{params.file_path}'.")
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

    def _validate_registry_header(self, path: Path) -> None:
        """Verify binary file header matches registry hive specification (regf, >= 4096 bytes)."""
        try:
            file_size = path.stat().st_size
        except OSError as exc:
            raise RegistryHiveParsingError(
                f"Impossible de vérifier la taille du fichier '{path.name}': {exc}"
            ) from exc

        if file_size < 4096:
            raise RegistryHiveParsingError(
                f"Format de ruche de Registre non reconnu ou corrompu: '{path.name}' "
                f"(taille {file_size} octets < 4096)."
            )

        try:
            with open(path, "rb") as f:
                magic = f.read(4)
        except OSError as exc:
            raise RegistryHiveParsingError(
                f"Erreur d'accès en lecture au fichier '{path.name}': {exc}"
            ) from exc

        if len(magic) < 4 or magic != REGISTRY_MAGIC:
            raise RegistryHiveParsingError(
                f"Format de ruche de Registre non reconnu ou corrompu dès l'en-tête: '{path.name}'."
            )

    def _detect_hive_type(
        self,
        hive: RegistryHive,
        target_path: Path,
        param_hive_type: str,
    ) -> str | None:
        """Detect or confirm the hive type."""
        if param_hive_type != "auto":
            return param_hive_type.lower()

        # Check regipy hive_type
        detected = getattr(hive, "hive_type", None)
        if detected:
            return str(detected).lower()

        # Check direct filename stem / name before calling regipy identify_hive_type
        filename = target_path.name.lower()
        stem = target_path.stem.lower()

        known_hive_names = {
            "system": "system",
            "software": "software",
            "sam": "sam",
            "security": "security",
            "ntuser": "ntuser",
            "ntuser.dat": "ntuser",
            "usrclass": "usrclass",
            "usrclass.dat": "usrclass",
            "amcache": "amcache",
            "amcache.hve": "amcache",
        }

        if filename in known_hive_names:
            return known_hive_names[filename]
        if stem in known_hive_names:
            return known_hive_names[stem]

        # Check internal hive header file_name
        internal_name = getattr(hive, "name", None)
        if internal_name:
            internal_lower = str(internal_name).lower()
            if internal_lower in known_hive_names:
                return known_hive_names[internal_lower]
            with contextlib.suppress(Exception):
                from regipy.registry import identify_hive_type

                return identify_hive_type(str(internal_name)).lower()

        # Fallback to regipy identify_hive_type
        with contextlib.suppress(Exception):
            from regipy.registry import identify_hive_type

            return identify_hive_type(target_path.name).lower()

        return None

    def _resolve_control_set(self, hive: RegistryHive) -> str:
        """Resolve CurrentControlSet name (e.g. ControlSet001) from \\Select hive key."""
        try:
            select_key = hive.get_key(r"\Select")
            if select_key:
                values = select_key.iter_values(as_json=False)
                if values is not None:
                    for val in values:
                        if getattr(val, "name", "").lower() == "current":
                            val_data = getattr(val, "value", None)
                            if isinstance(val_data, int):
                                return f"ControlSet{val_data:03d}"
                            if isinstance(val_data, bytes) and len(val_data) >= 4:
                                num = int.from_bytes(val_data[:4], "little")
                                return f"ControlSet{num:03d}"
                            if str(val_data).isdigit():
                                return f"ControlSet{int(val_data):03d}"
        except Exception:
            pass
        return "ControlSet001"

    def _matches_search_query(
        self,
        search_query: str | None,
        key_path: str,
        value_name: str,
        value_data: Any,
    ) -> bool:
        """Apply case-insensitive search filter across key path, value name, and value data."""
        if search_query is None or not search_query.strip():
            return True

        q = search_query.strip().lower()
        if q in key_path.lower():
            return True
        if q in value_name.lower():
            return True

        if isinstance(value_data, (list, tuple, set)):
            for item in value_data:
                if item is not None and q in str(item).lower():
                    return True
        elif value_data is not None and q in str(value_data).lower():
            return True

        return False
