"""Secure execution engine for forensic tools with timeouts, hashing, and audit persistence."""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from iryx.analytics.models import Observation
from iryx.core.exceptions import (
    PluginNotWhitelistedException,
    ToolExecutionFailedException,
    ToolExecutionTimeoutException,
    ToolNotFoundException,
    ValidationException,
)
from iryx.gateway.base import BaseTool, ToolExecutionContext, ToolExecutionResult
from iryx.gateway.models import ToolExecution, ToolExecutionStatus
from iryx.gateway.registry import ToolRegistry, default_registry

logger = logging.getLogger("iryx.gateway.runner")


def compute_sha256(raw_output: Any) -> str:
    """Compute deterministic SHA-256 hash of raw tool execution output."""
    if raw_output is None:
        return hashlib.sha256(b"").hexdigest()
    if isinstance(raw_output, bytes):
        return hashlib.sha256(raw_output).hexdigest()
    if isinstance(raw_output, str):
        return hashlib.sha256(raw_output.encode("utf-8")).hexdigest()
    if isinstance(raw_output, BaseModel):
        return hashlib.sha256(raw_output.model_dump_json().encode("utf-8")).hexdigest()
    try:
        serialized = json.dumps(
            raw_output,
            sort_keys=True,
            ensure_ascii=True,
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()
    except Exception:
        return hashlib.sha256(str(raw_output).encode("utf-8")).hexdigest()


async def run_command_safely(
    cmd: list[str],
    timeout: float | None = None,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, bytes, bytes]:
    """Execute an external command strictly without shell (shell=False).

    Args:
        cmd: List of command arguments. Must be a list or tuple of strings.
        timeout: Maximum execution duration in seconds.
        cwd: Optional working directory.
        env: Optional environment variables.

    Raises:
        ValidationException: If cmd is not a sequence or is empty.
        ToolExecutionTimeoutException: If execution duration exceeds timeout.
    """
    if isinstance(cmd, str) or not isinstance(cmd, (list, tuple)):
        raise ValidationException("Commands must be provided as a list of arguments, not a string.")
    if not cmd or not str(cmd[0]).strip():
        raise ValidationException("Command list cannot be empty.")

    cmd_args = [str(arg) for arg in cmd]

    # Strictly shell=False via asyncio.create_subprocess_exec (direct OS exec)
    proc = await asyncio.create_subprocess_exec(
        *cmd_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd) if cwd else None,
        env=env,
    )

    try:
        stdout_data, stderr_data = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )
        return (proc.returncode or 0, stdout_data, stderr_data)
    except (TimeoutError, asyncio.CancelledError) as exc:
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise ToolExecutionTimeoutException(
            f"Command execution timed out after {timeout}s: {' '.join(cmd_args)}"
        ) from exc


class ToolRunner:
    """Runner responsible for validating, executing, timing, hashing, and persisting tool calls."""

    def __init__(
        self,
        db: Session | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or default_registry

    async def execute_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any] | BaseModel,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Execute a registered forensic tool within controlled boundaries.

        Args:
            tool_name: Name of the registered tool to execute.
            parameters: Input arguments matching tool's Pydantic schema.
            context: Context containing case_id, agent_role, evidence_id.

        Returns:
            ToolExecutionResult with raw output, duration, and SHA-256 fingerprint.

        Raises:
            ToolNotFoundException: If tool_name is not registered (HTTP 404).
            ValidationException: If parameters do not conform to tool schema (HTTP 422).
            ToolExecutionTimeoutException: If execution exceeds tool's timeout (HTTP 504).
            ToolExecutionFailedException: If tool raises unexpected error (HTTP 500).
        """
        # 1. Lookup tool in registry (raises ToolNotFoundException if missing)
        tool: BaseTool = self.registry.get(tool_name)

        # 2. Validate input parameters against tool schema
        if isinstance(parameters, BaseModel):
            if not isinstance(parameters, tool.parameters_schema):
                try:
                    validated_params = tool.parameters_schema.model_validate(
                        parameters.model_dump(mode="json")
                    )
                except ValidationError as e:
                    raise ValidationException(
                        f"Paramètres non conformes au schéma de l'outil '{tool_name}': {e}"
                    ) from e
            else:
                validated_params = parameters
        elif isinstance(parameters, dict):
            try:
                validated_params = tool.parameters_schema.model_validate(parameters)
            except ValidationError as e:
                raise ValidationException(
                    f"Paramètres non conformes au schéma de l'outil '{tool_name}': {e}"
                ) from e
        else:
            raise ValidationException(
                "Les paramètres d'exécution doivent être un dictionnaire ou un modèle Pydantic."
            )

        params_dict = validated_params.model_dump(mode="json")

        # 3. Execute tool under timeout and measured duration
        start_time = time.perf_counter()
        timeout = tool.timeout_seconds

        try:
            result = await asyncio.wait_for(
                tool.execute(validated_params, context),
                timeout=timeout,
            )
        except (TimeoutError, ToolExecutionTimeoutException) as exc:
            duration_ms = max(int((time.perf_counter() - start_time) * 1000), 0)
            if self.db is not None:
                execution = ToolExecution(
                    case_id=context.case_id,
                    tool_name=tool.name,
                    tool_version=tool.version,
                    agent_role=context.agent_role,
                    parameters=params_dict,
                    result_sha256=None,
                    duration_ms=duration_ms,
                    status=ToolExecutionStatus.TIMEOUT,
                    error_message=f"Dépassement du délai d'expiration ({timeout}s)",
                )
                self.db.add(execution)
                try:
                    self.db.commit()
                    self.db.refresh(execution)
                except Exception:
                    self.db.rollback()
                    raise
            if isinstance(exc, ToolExecutionTimeoutException):
                raise
            raise ToolExecutionTimeoutException(
                f"L'outil '{tool.name}' a dépassé son délai maximal d'exécution ({timeout}s)."
            ) from exc
        except Exception as exc:
            if isinstance(
                exc,
                (
                    ToolExecutionTimeoutException,
                    ToolNotFoundException,
                    ValidationException,
                    PluginNotWhitelistedException,
                ),
            ):
                raise
            duration_ms = max(int((time.perf_counter() - start_time) * 1000), 0)
            error_msg = str(exc) or type(exc).__name__
            if self.db is not None:
                execution = ToolExecution(
                    case_id=context.case_id,
                    tool_name=tool.name,
                    tool_version=tool.version,
                    agent_role=context.agent_role,
                    parameters=params_dict,
                    result_sha256=None,
                    duration_ms=duration_ms,
                    status=ToolExecutionStatus.ERROR,
                    error_message=error_msg,
                )
                self.db.add(execution)
                try:
                    self.db.commit()
                    self.db.refresh(execution)
                except Exception:
                    self.db.rollback()
                    raise
            raise ToolExecutionFailedException(
                f"Erreur interne lors de l'exécution de l'outil '{tool.name}': {error_msg}"
            ) from exc

        # 4. Nominal completion: compute duration, SHA-256 fingerprint, and persist execution
        duration_ms = max(int((time.perf_counter() - start_time) * 1000), 1)
        sha256 = compute_sha256(result.raw_output)
        result.result_sha256 = sha256
        result.duration_ms = duration_ms
        result.status = ToolExecutionStatus.SUCCESS

        if self.db is not None:
            execution = ToolExecution(
                case_id=context.case_id,
                tool_name=tool.name,
                tool_version=tool.version,
                agent_role=context.agent_role,
                parameters=params_dict,
                result_sha256=sha256,
                duration_ms=duration_ms,
                status=ToolExecutionStatus.SUCCESS,
                error_message=None,
            )
            self.db.add(execution)
            self.db.flush()

            created_observations: list[tuple[dict[str, Any], uuid.UUID, uuid.UUID | None]] = []
            if result.observations:
                for obs_data in result.observations:
                    ts = obs_data.get("timestamp_utc")
                    if isinstance(ts, str):
                        try:
                            ts = datetime.fromisoformat(ts)
                        except ValueError:
                            ts = None
                    src_id = obs_data.get("source_id") or context.evidence_id
                    if isinstance(src_id, str):
                        try:
                            src_id = uuid.UUID(src_id)
                        except ValueError:
                            src_id = None
                    raw_norm = obs_data.get("normalized_content")
                    normalized_content = raw_norm if raw_norm is not None else dict(obs_data)
                    obs = Observation(
                        case_id=context.case_id,
                        source_id=src_id,
                        tool_name=tool.name,
                        tool_execution_id=execution.id,
                        normalized_content=normalized_content,
                        timestamp_utc=ts,
                        source_location=obs_data.get("source_location"),
                    )
                    self.db.add(obs)
                    self.db.flush()
                    created_observations.append((obs_data, obs.id, obs.source_id))

            exec_id_str = str(execution.id)
            try:
                self.db.commit()
                self.db.refresh(execution)
            except Exception:
                self.db.rollback()
                raise
            for obs_data, obs_id, obs_source_id in created_observations:
                obs_data["id"] = str(obs_id)
                obs_data["tool_name"] = tool.name
                obs_data["tool_execution_id"] = exec_id_str
                if obs_source_id is not None:
                    obs_data["source_id"] = str(obs_source_id)
            result.tool_execution_id = execution.id
            result.agent_payload = None
            result.agent_payload = result.to_agent_payload()
        else:
            result.agent_payload = result.to_agent_payload()

        return result
