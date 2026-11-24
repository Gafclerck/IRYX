"""Contextual truncation and summarization module for AI LLM agents (FR9, FR10, NFR-PERF-06).

Caps tool outputs to avoid saturating LLM context windows while preserving 100% of raw
evidence and normalized observations in the database.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from iryx.gateway.schemas import AgentPayload

MAX_AGENT_OBSERVATIONS: int = 50
MAX_SUMMARY_BYTES: int = 8192
MAX_SUMMARY_LINES: int = 200


def _obs_to_dict(obs: Any) -> dict[str, Any]:
    """Convert an observation (dict or ORM model) into a clean dictionary."""
    if isinstance(obs, dict):
        return obs
    if hasattr(obs, "normalized_content"):
        return {
            "id": getattr(obs, "id", None),
            "case_id": getattr(obs, "case_id", None),
            "source_id": getattr(obs, "source_id", None),
            "tool_name": getattr(obs, "tool_name", ""),
            "tool_execution_id": getattr(obs, "tool_execution_id", None),
            "normalized_content": getattr(obs, "normalized_content", None) or {},
            "timestamp_utc": getattr(obs, "timestamp_utc", None),
            "source_location": getattr(obs, "source_location", None),
        }
    return {"content": str(obs)}


def _format_obs_line(obs: Any) -> str:
    """Format a single observation as a compact readable text line."""
    if isinstance(obs, dict):
        ts = obs.get("timestamp_utc")
        loc = obs.get("source_location")
        tool = obs.get("tool_name")
        content = obs.get("normalized_content")
        if content is None:
            content = {
                k: v
                for k, v in obs.items()
                if k
                not in (
                    "id",
                    "case_id",
                    "source_id",
                    "tool_execution_id",
                    "created_at",
                    "timestamp_utc",
                    "tool_name",
                    "source_location",
                    "normalized_content",
                )
            }
        elif isinstance(content, dict):
            content = content or {}
        parts: list[str] = []
        if ts:
            parts.append(f"[{ts}]")
        if tool:
            parts.append(f"<{tool}>")
        if loc:
            parts.append(f"({loc})")
        if isinstance(content, dict):
            parts.append(json.dumps(content, ensure_ascii=False, default=str))
        else:
            parts.append(str(content))
        return " ".join(parts) if parts else str(obs)

    if hasattr(obs, "normalized_content"):
        ts = getattr(obs, "timestamp_utc", None)
        loc = getattr(obs, "source_location", None)
        tool = getattr(obs, "tool_name", None)
        content = getattr(obs, "normalized_content", None) or {}
        parts = []
        if ts:
            parts.append(f"[{ts}]")
        if tool:
            parts.append(f"<{tool}>")
        if loc:
            parts.append(f"({loc})")
        if isinstance(content, dict):
            parts.append(json.dumps(content, ensure_ascii=False, default=str))
        else:
            parts.append(str(content))
        return " ".join(parts) if parts else str(obs)

    return str(obs)


def truncate_for_agent(
    observations: Sequence[Any] | Any | None = None,
    raw_output: Any = None,
    *,
    summary: str | None = None,
    max_observations: int = MAX_AGENT_OBSERVATIONS,
    max_bytes: int = MAX_SUMMARY_BYTES,
    max_lines: int = MAX_SUMMARY_LINES,
) -> AgentPayload:
    """Project tool execution results to a context-bounded payload for LLM agents.

    Enforces NFR-PERF-06 boundaries:
    - Maximum `max_observations` (default 50) observations in the payload.
    - Summary bounded strictly to `max_bytes` (8 192 bytes) and `max_lines` (200 lines).
    - If truncated, prepends the standardized banner:
      `[TRUNCATED: {X} éléments masqués. Consulter Observation pour la totalité]`
    - Preserves is_truncated=False and truncated_count=0 when within boundaries.

    Args:
        observations: List of observations or a ToolExecutionResult instance.
        raw_output: Optional raw output to summarize if observations are sparse.
        summary: Optional pre-computed summary string to bound.
        max_observations: Maximum observations to keep in projection (default 50).
        max_bytes: Maximum size of summary in UTF-8 bytes (default 8192).
        max_lines: Maximum number of lines in summary (default 200).

    Returns:
        AgentPayload containing bounded observations, bounded summary, and truncation flags.
    """
    # Support passing a ToolExecutionResult directly as first argument
    if hasattr(observations, "observations") and hasattr(observations, "raw_output"):
        result_obj = observations
        observations = result_obj.observations
        if raw_output is None:
            raw_output = result_obj.raw_output

    obs_list: list[Any] = list(observations) if observations is not None else []
    total_obs = len(obs_list)

    is_obs_truncated = total_obs > max_observations
    if is_obs_truncated:
        truncated_count = total_obs - max_observations
        kept_obs = obs_list[:max_observations]
    else:
        truncated_count = 0
        kept_obs = obs_list

    # Compose base body
    if summary is not None:
        base_body = summary
    elif kept_obs:
        base_body = "\n".join(_format_obs_line(o) for o in kept_obs)
    elif raw_output is not None:
        if isinstance(raw_output, str):
            base_body = raw_output
        elif isinstance(raw_output, (dict, list)):
            base_body = json.dumps(raw_output, indent=2, ensure_ascii=False, default=str)
        else:
            base_body = str(raw_output)
    else:
        base_body = ""

    body_lines = base_body.splitlines() if base_body else []
    body_bytes_len = len(base_body.encode("utf-8"))

    needs_truncation = (
        is_obs_truncated or (len(body_lines) > max_lines) or (body_bytes_len > max_bytes)
    )

    if not needs_truncation:
        return AgentPayload(
            observations=[_obs_to_dict(o) for o in kept_obs],
            summary=base_body,
            is_truncated=False,
            truncated_count=0,
        )

    # When truncation is needed, determine banner and element count omitted
    truncated_count = max(total_obs - max_observations, 0)
    if truncated_count > 0:
        banner = (
            f"[TRUNCATED: {truncated_count} éléments masqués. "
            "Consulter Observation pour la totalité]"
        )
    else:
        banner = "[TRUNCATED: Résumé textuel tronqué. Consulter Observation pour la totalité]"

    # Calculate budgets for the body accounting for the banner
    banner_bytes_len = len(banner.encode("utf-8")) + 1  # newline
    max_body_bytes = max(max_bytes - banner_bytes_len, 0)
    banner_lines_count = len(banner.splitlines()) + 1  # newline
    max_body_lines = max(max_lines - banner_lines_count, 0)

    # Truncate lines first
    if len(body_lines) > max_body_lines:
        body_lines = body_lines[:max_body_lines]
        body = "\n".join(body_lines)
    else:
        body = base_body

    # Truncate bytes safely on line and UTF-8 boundaries
    body_bytes = body.encode("utf-8")
    if len(body_bytes) > max_body_bytes:
        decoded = body_bytes[:max_body_bytes].decode("utf-8", errors="ignore")
        body = decoded.rsplit("\n", 1)[0] if "\n" in decoded else decoded

    final_summary = f"{banner}\n{body}".strip() if body else banner

    # Double-check final invariants
    final_bytes = final_summary.encode("utf-8")
    if len(final_bytes) > max_bytes:
        final_summary = final_bytes[:max_bytes].decode("utf-8", errors="ignore")

    final_lines = final_summary.splitlines()
    if len(final_lines) > max_lines:
        final_summary = "\n".join(final_lines[:max_lines])

    return AgentPayload(
        observations=[_obs_to_dict(o) for o in kept_obs],
        summary=final_summary,
        is_truncated=True,
        truncated_count=truncated_count,
    )
