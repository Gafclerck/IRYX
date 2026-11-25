"""Analyst Agent formulating structured investigation findings (Story 6.2, FR22).

Conforms to FR22, D-10, D-11, and NFR-SEC-06.
"""

import asyncio
import concurrent.futures
import json
import logging
import re
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from iryx.ai.client import UnifiedLLMClient, get_llm_client
from iryx.ai.prompts import build_system_prompt, wrap_forensic_data
from iryx.ai.schemas import LLMRole
from iryx.analytics.models import (
    FindingConfidence,
    FindingSeverity,
    FindingStatus,
    FindingType,
    Observation,
)
from iryx.analytics.schemas import FindingCreate, FindingOut
from iryx.analytics.services import FindingService

logger = logging.getLogger("iryx.orchestrator.analyst")

MAX_CORRECTION_RETRIES: int = 2

ANALYST_SYSTEM_INSTRUCTIONS: str = (
    "Vous etes l'AnalystAgent d'IRYX. Votre mission est d'analyser rigoureusement "
    "les observations techniques normalisees issues des outils forensiques afin "
    "d'identifier les correlations, de formuler des hypotheses d'investigation et "
    "de proposer des constats structures (findings).\n\n"
    "REGLES STRICTES :\n"
    "1. Chaque constat (finding) doit obligatoirement etre etaye par des faits techniques "
    "reels issus des observations fournies.\n"
    "2. Chaque constat DOIT OBLIGATOIREMENT citer au moins un identifiant d'observation "
    "('observation_refs') et au moins un identifiant d'execution d'outil ('tool_execution_refs') "
    "figurant EXCLUSIVEMENT dans les donnees transmises.\n"
    "3. Il vous est FORMELLEMENT INTERDIT d'inventer des faits, des UUID d'observations "
    "ou des identifiants d'outils inexistants dans le contexte d'analyse.\n"
    "4. Si les observations ne presentent pas d'indices suspects ou de faits probants "
    "suffisants, renvoyez une liste vide de findings avec un summary explicatif.\n"
    "5. Les valeurs d'enumerations autorisees sont STRICTEMENT :\n"
    "   - severity : 'low', 'medium', 'high', 'critical'\n"
    "   - confidence : 'low', 'medium', 'high'\n"
    "   - finding_type : 'fact', 'inference', 'hypothesis'\n"
    "6. Votre reponse doit etre EXCLUSIVEMENT un objet JSON valide conforme au schema suivant :\n"
    "{\n"
    '  "summary": "Synthese concise de l\'analyse forensique",\n'
    '  "findings": [\n'
    "    {\n"
    '      "title": "<intitule_concis_du_constat>",\n'
    '      "severity": "<low|medium|high|critical>",\n'
    '      "confidence": "<low|medium|high>",\n'
    '      "finding_type": "<fact|inference|hypothesis>",\n'
    '      "observation_refs": ["<uuid_observation_existante>"],\n'
    '      "tool_execution_refs": ["<uuid_tool_execution_existant>"]\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "N'ajoutez aucun texte d'introduction ni de conclusion en dehors du JSON."
)


class ProposedFinding(BaseModel):
    """Schema for a single finding proposed by the Analyst agent."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

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
    status: FindingStatus = Field(
        default=FindingStatus.PROPOSED,
        description="Statut opérationnel initial ('proposed').",
    )
    observation_refs: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        description="Identifiants d'observations justificatives réelles (min 1).",
    )
    tool_execution_refs: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        description="Identifiants d'exécutions d'outils associées (min 1).",
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


class AnalystOutput(BaseModel):
    """Structured output expected from LLM inference during analysis."""

    summary: str = Field(
        ...,
        description="Synthèse concise de l'analyse forensique.",
    )
    findings: list[ProposedFinding] = Field(
        default_factory=list,
        description="Liste des constats d'investigation formulés.",
    )


class AnalystResult(BaseModel):
    """Result returned by AnalystAgent execution."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    status: str = "completed"  # "completed" | "failed" | "paused"
    summary: str | None = None
    findings: list[FindingOut | ProposedFinding] = Field(default_factory=list)
    persisted_findings: list[FindingOut] = Field(default_factory=list)
    notification: str | None = None
    errors: list[str] = Field(default_factory=list)
    retries_used: int = 0


_CODE_BLOCK_REGEX = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", flags=re.IGNORECASE)


def _extract_json_payload(raw_content: str) -> str:
    """Extract JSON payload reliably, supporting markdown code blocks and conversational text."""
    stripped = raw_content.strip()
    match = _CODE_BLOCK_REGEX.search(stripped)
    if match:
        return match.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1].strip()
    return stripped


class AnalystAgent:
    """Forensic Analyst Agent interpreting technical observations to formulate findings (FR22)."""

    def __init__(
        self,
        llm_client: UnifiedLLMClient | None = None,
        db: Session | None = None,
    ) -> None:
        self.llm_client = llm_client or get_llm_client(role=LLMRole.ANALYST)
        self.db = db

    def _format_observations(
        self,
        raw_observations: list[Any],
        tool_executions: list[Any] | None = None,
    ) -> tuple[str, set[str], set[str]]:
        """Format raw observations for prompt encapsulation and collect valid UUIDs."""
        lines: list[str] = []
        valid_obs_ids: set[str] = set()
        valid_tool_exec_ids: set[str] = set()

        if tool_executions:
            for te in tool_executions:
                if isinstance(te, dict):
                    te_id = str(te.get("tool_execution_id") or te.get("id") or "")
                else:
                    te_id = str(getattr(te, "tool_execution_id", getattr(te, "id", "")) or "")
                if te_id:
                    valid_tool_exec_ids.add(te_id)

        for idx, obs in enumerate(raw_observations, 1):
            if isinstance(obs, Observation):
                obs_id = str(obs.id)
                tool_name = obs.tool_name
                tool_exec_id = str(obs.tool_execution_id) if obs.tool_execution_id else ""
                ts = obs.timestamp_utc.isoformat() if obs.timestamp_utc else "N/A"
                content = obs.normalized_content or {}
            elif isinstance(obs, dict):
                obs_id = str(obs.get("id") or obs.get("observation_id") or "")
                tool_name = str(obs.get("tool_name") or "unknown")
                tool_exec_id = str(obs.get("tool_execution_id") or "")
                ts_raw = obs.get("timestamp_utc")
                ts = ts_raw.isoformat() if hasattr(ts_raw, "isoformat") else str(ts_raw or "N/A")
                content = obs.get("normalized_content") or obs.get("content") or {}
            else:
                obs_id = str(getattr(obs, "id", ""))
                tool_name = str(getattr(obs, "tool_name", "unknown"))
                tool_exec_id = str(getattr(obs, "tool_execution_id", "") or "")
                ts_attr = getattr(obs, "timestamp_utc", None)
                ts = ts_attr.isoformat() if hasattr(ts_attr, "isoformat") else str(ts_attr or "N/A")
                content = getattr(obs, "normalized_content", {}) or {}

            if obs_id:
                valid_obs_ids.add(obs_id)
            if tool_exec_id:
                valid_tool_exec_ids.add(tool_exec_id)

            try:
                content_str = (
                    json.dumps(content, ensure_ascii=False)
                    if not isinstance(content, str)
                    else content
                )
            except Exception:
                content_str = str(content)

            lines.append(
                f"Observation #{idx} :\n"
                f"- ID: {obs_id}\n"
                f"- Outil: {tool_name}\n"
                f"- Tool Execution ID: {tool_exec_id}\n"
                f"- Horodatage UTC: {ts}\n"
                f"- Contenu normalisé: {content_str}\n"
            )

        return "\n".join(lines), valid_obs_ids, valid_tool_exec_ids

    def _validate_finding_invariants(
        self,
        output: AnalystOutput,
        valid_obs_ids: set[str],
        valid_tool_exec_ids: set[str],
    ) -> None:
        """Validate that all referenced UUIDs exist in the context without invention."""
        for finding in output.findings:
            if not finding.observation_refs:
                raise ValueError(
                    f"Le constat '{finding.title}' doit obligatoirement citer au moins "
                    "une référence d'observation."
                )
            if not finding.tool_execution_refs:
                raise ValueError(
                    f"Le constat '{finding.title}' doit obligatoirement citer au moins "
                    "une référence d'exécution d'outil."
                )

            if valid_obs_ids:
                for ref in finding.observation_refs:
                    if str(ref) not in valid_obs_ids:
                        raise ValueError(
                            f"Référence d'observation inconnue ou fictive '{ref}' "
                            f"dans le constat '{finding.title}'. "
                            f"Observations valides disponibles : {sorted(valid_obs_ids)}"
                        )

            if valid_tool_exec_ids:
                for ref in finding.tool_execution_refs:
                    if str(ref) not in valid_tool_exec_ids:
                        tools_avail = sorted(valid_tool_exec_ids)
                        raise ValueError(
                            f"Référence d'exécution d'outil inconnue ou fictive '{ref}' "
                            f"dans le constat '{finding.title}'. "
                            f"Exécutions d'outils valides disponibles : {tools_avail}"
                        )

    def _parse_and_validate(
        self,
        raw_output: str,
        valid_obs_ids: set[str],
        valid_tool_exec_ids: set[str],
    ) -> AnalystOutput:
        """Deserialize JSON, validate Pydantic schema, and verify domain invariants."""
        cleaned = _extract_json_payload(raw_output)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Sortie LLM non-JSON ou malformée : {exc}") from exc

        if not isinstance(parsed, dict):
            raise ValueError("La sortie doit être un objet JSON avec 'summary' et 'findings'.")

        try:
            output = AnalystOutput.model_validate(parsed)
        except Exception as exc:
            raise ValueError(f"Violation du schéma AnalystOutput : {exc}") from exc

        self._validate_finding_invariants(
            output=output,
            valid_obs_ids=valid_obs_ids,
            valid_tool_exec_ids=valid_tool_exec_ids,
        )
        return output

    async def analyze(
        self,
        observations: list[Any] | None = None,
        tool_executions: list[Any] | None = None,
        case_id: uuid.UUID | str | None = None,
        run_id: uuid.UUID | str | None = None,
        incident_description: str | None = None,
        db: Session | None = None,
    ) -> AnalystResult:
        """Execute forensic analysis of observations to formulate structured findings."""
        session = db or self.db
        raw_observations: list[Any] = []

        if observations is not None:
            raw_observations = list(observations)
        elif case_id is not None and session is not None:
            try:
                case_uuid = uuid.UUID(str(case_id))
                stmt = (
                    select(Observation)
                    .where(Observation.case_id == case_uuid)
                    .order_by(Observation.created_at.asc(), Observation.id.asc())
                )
                raw_observations = list(session.scalars(stmt).all())
            except Exception as exc:
                logger.warning(
                    "Could not query observations from DB for case %s: %s",
                    case_id,
                    exc,
                )

        # 0-token short-circuit when no observations are available
        if not raw_observations:
            notification = (
                "Aucune observation technique probante disponible "
                "pour formuler des constats d'enquête."
            )
            logger.info("Analyst short-circuited (0 tokens): %s", notification)
            return AnalystResult(
                status="completed",
                summary=None,
                findings=[],
                persisted_findings=[],
                notification=notification,
                retries_used=0,
            )

        obs_text, valid_obs_ids, valid_tool_exec_ids = self._format_observations(
            raw_observations=raw_observations,
            tool_executions=tool_executions,
        )

        wrapped_forensic_data = wrap_forensic_data(obs_text)

        system_prompt = build_system_prompt(
            role=LLMRole.ANALYST,
            custom_instructions=ANALYST_SYSTEM_INSTRUCTIONS,
        )

        user_content_parts = []
        if incident_description and incident_description.strip():
            user_content_parts.append(
                f"Demande initiale / Contexte du dossier :\n{incident_description.strip()}"
            )
        user_content_parts.append(
            "Consultez les observations techniques normalisées suivantes :\n"
            f"{wrapped_forensic_data}"
        )
        user_content_parts.append(
            "Analysez ces éléments techniques et formulez vos constats d'investigation (findings) "
            "au format JSON strict, en citant obligatoirement les identifiants d'observations et "
            "d'exécutions d'outils correspondants."
        )
        user_prompt = "\n\n".join(user_content_parts)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        last_error = ""
        for attempt in range(1 + MAX_CORRECTION_RETRIES):
            response = await self.llm_client.complete(messages=messages)
            raw_content = response.content

            try:
                output = self._parse_and_validate(
                    raw_output=raw_content,
                    valid_obs_ids=valid_obs_ids,
                    valid_tool_exec_ids=valid_tool_exec_ids,
                )

                # Persist findings in DB if session and case_id are provided
                persisted: list[FindingOut] = []
                if session is not None and case_id is not None:
                    case_uuid = uuid.UUID(str(case_id))
                    finding_service = FindingService(session)
                    try:
                        for pf in output.findings:
                            payload = FindingCreate(
                                title=pf.title,
                                severity=pf.severity,
                                confidence=pf.confidence,
                                finding_type=pf.finding_type,
                                observation_refs=list(dict.fromkeys(pf.observation_refs)),
                                tool_execution_refs=list(dict.fromkeys(pf.tool_execution_refs)),
                            )
                            created = finding_service.create_finding(
                                case_id=case_uuid,
                                payload=payload,
                            )
                            persisted.append(
                                FindingOut.model_validate(created, from_attributes=True)
                            )
                    except Exception:
                        session.rollback()
                        raise

                logger.info(
                    "Analyst findings generated and validated successfully "
                    "(count: %d, retries: %d)",
                    len(output.findings),
                    attempt,
                )

                return AnalystResult(
                    status="completed",
                    summary=output.summary,
                    findings=persisted if persisted else output.findings,
                    persisted_findings=persisted,
                    notification=None,
                    retries_used=attempt,
                )

            except Exception as exc:
                last_error = str(exc)
                if attempt < MAX_CORRECTION_RETRIES:
                    logger.warning(
                        "Analyst validation failed on attempt %d: %s. Sending correction prompt.",
                        attempt + 1,
                        last_error,
                    )
                    messages.append({"role": "assistant", "content": raw_content})
                    obs_str = ", ".join(sorted(valid_obs_ids))
                    tools_str = ", ".join(sorted(valid_tool_exec_ids))
                    correction_prompt = (
                        "La réponse précédente est invalide pour la raison suivante :\n"
                        f"{last_error}\n\n"
                        "Veuillez corriger le JSON en respectant STRICTEMENT les contraintes :\n"
                        "- Respecter le schéma JSON AnalystOutput avec 'summary' et 'findings'.\n"
                        "- Chaque constat dans 'findings' doit obligatoirement avoir :\n"
                        "  * 'title' (non vide, max 255 caractères)\n"
                        "  * 'severity' ('low', 'medium', 'high', 'critical')\n"
                        "  * 'confidence' ('low', 'medium', 'high')\n"
                        "  * 'finding_type' ('fact', 'inference', 'hypothesis')\n"
                        f"  * 'observation_refs' (au moins un UUID valide parmi : {obs_str})\n"
                        f"  * 'tool_execution_refs' (au moins un UUID valide parmi : {tools_str})\n"
                        "Répondez UNIQUEMENT avec le JSON valide, sans texte explicatif extérieur."
                    )
                    messages.append({"role": "user", "content": correction_prompt})
                else:
                    logger.error(
                        "Analyst failed after %d correction attempts. Last error: %s",
                        MAX_CORRECTION_RETRIES,
                        last_error,
                    )
                    return AnalystResult(
                        status="failed",
                        summary=None,
                        findings=[],
                        persisted_findings=[],
                        errors=[
                            f"Échec de validation des constats après {MAX_CORRECTION_RETRIES} "
                            f"tentatives de correction : {last_error}"
                        ],
                        retries_used=attempt,
                    )

        return AnalystResult(
            status="failed",
            summary=None,
            findings=[],
            persisted_findings=[],
            errors=["Échec inattendu lors de l'analyse des constats."],
            retries_used=MAX_CORRECTION_RETRIES,
        )

    def analyze_sync(
        self,
        observations: list[Any] | None = None,
        tool_executions: list[Any] | None = None,
        case_id: uuid.UUID | str | None = None,
        run_id: uuid.UUID | str | None = None,
        incident_description: str | None = None,
        db: Session | None = None,
    ) -> AnalystResult:
        """Synchronously execute analysis, safely handling active event loops."""
        coro = self.analyze(
            observations=observations,
            tool_executions=tool_executions,
            case_id=case_id,
            run_id=run_id,
            incident_description=incident_description,
            db=db,
        )
        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        except RuntimeError:
            return asyncio.run(coro)
