"""Planner Agent proposing bounded digital forensics investigation plans (Story 5.3).

Conforms to FR17, NFR-PERF-05, and NFR-SEC-06.
"""

import asyncio
import concurrent.futures
import json
import logging
import re
import uuid
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from iryx.ai.client import UnifiedLLMClient, get_llm_client
from iryx.ai.prompts import build_system_prompt, wrap_forensic_data
from iryx.ai.schemas import LLMRole
from iryx.core.exceptions import InvalidPlanException
from iryx.evidence.models import Evidence
from iryx.gateway.registry import ToolRegistry, get_tool_registry
from iryx.orchestrator.schemas import InvestigationPlan

logger = logging.getLogger("iryx.orchestrator.planner")

MAX_PLAN_STEPS: int = 10
MAX_CORRECTION_RETRIES: int = 2

PLANNER_SYSTEM_INSTRUCTIONS: str = (
    "Vous etes le PlannerAgent d'IRYX. Votre mission est de proposer un plan d'investigation "
    "forensique structure, rationnel et rigoureusement borne pour assister l'investigateur.\n\n"
    "REGLES STRICTES :\n"
    "1. Le plan doit comporter AU MAXIMUM 10 etapes ordonnees (steps).\n"
    "2. Chaque etape doit cibler une preuve scellee valide identifiee par son UUID.\n"
    "3. Chaque outil specifie (tool_name) doit obligatoirement appartenir a la liste "
    "des outils autorises.\n"
    "4. Ne proposez aucun outil non repertorie (pas de scripts bash, pas de commandes shell).\n"
    "5. Votre reponse doit etre EXCLUSIVEMENT un objet JSON valide conforme au schema "
    "InvestigationPlan suivant :\n"
    "{\n"
    '  "summary": "Synthese concise de la strategie d\'investigation",\n'
    '  "steps": [\n'
    "    {\n"
    '      "step_id": 1,\n'
    '      "tool_name": "<nom_outil_autorise>",\n'
    '      "target_evidence_id": "<uuid_preuve>",\n'
    '      "parameters": {},\n'
    '      "rationale": "<justification forensique du choix>"\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "N'ajoutez aucun texte d'introduction ni de conclusion en dehors du JSON."
)


class PlannerResult(BaseModel):
    """Result returned by PlannerAgent execution."""

    plan: InvestigationPlan | None = None
    status: str = "running"
    notification: str | None = None
    retries_used: int = 0

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to inner plan if available."""
        if self.plan is not None and hasattr(self.plan, name):
            return getattr(self.plan, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


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


class PlannerAgent:
    """Forensic Planner Agent generating bounded investigation plans via UnifiedLLMClient."""

    def __init__(
        self,
        llm_client: UnifiedLLMClient | None = None,
        tool_registry: ToolRegistry | None = None,
        db: Session | None = None,
    ) -> None:
        self.llm_client = llm_client or get_llm_client(role=LLMRole.PLANNER)
        self.tool_registry = tool_registry or get_tool_registry()
        self.db = db

    def _resolve_authorized_tools(self) -> set[str]:
        """Collect authorized tool names from registry registered tools and whitelist."""
        registered = set(self.tool_registry.list_tool_names())
        whitelist = set(getattr(self.tool_registry, "_whitelist", set()))
        return registered | whitelist

    def _filter_sealed_evidences(
        self,
        evidences: list[Any] | None,
        case_id: uuid.UUID | str | None = None,
        db: Session | None = None,
    ) -> list[dict[str, Any]]:
        """Collect sealed evidences (sha256 present and non-empty) from inputs or database."""
        raw_items: list[Any] = []
        if evidences is not None:
            raw_items = list(evidences)
        elif case_id is not None:
            session = db or self.db
            if session is not None:
                try:
                    case_uuid = uuid.UUID(str(case_id))
                    stmt = select(Evidence).where(Evidence.case_id == case_uuid)
                    raw_items = list(session.scalars(stmt).all())
                except Exception as exc:
                    logger.warning(
                        "Could not query evidences from DB for case %s: %s",
                        case_id,
                        exc,
                    )

        sealed: list[dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, Evidence):
                sha = item.sha256
                if sha and sha.strip():
                    sealed.append(
                        {
                            "id": str(item.id),
                            "original_name": item.original_name,
                            "file_size": int(getattr(item, "file_size", None) or 0),
                            "detected_type": item.detected_type or "unknown",
                            "sha256": sha.strip(),
                        }
                    )
            elif isinstance(item, dict):
                sha = item.get("sha256")
                if sha and str(sha).strip():
                    sealed.append(
                        {
                            "id": str(item.get("id")),
                            "original_name": str(item.get("original_name", "evidence")),
                            "file_size": int(item.get("file_size") or 0),
                            "detected_type": str(item.get("detected_type", "unknown")),
                            "sha256": str(sha).strip(),
                        }
                    )
            elif hasattr(item, "sha256"):
                sha = item.sha256
                if sha and str(sha).strip():
                    sealed.append(
                        {
                            "id": str(getattr(item, "id", "")),
                            "original_name": str(getattr(item, "original_name", "evidence")),
                            "file_size": int(getattr(item, "file_size", None) or 0),
                            "detected_type": str(getattr(item, "detected_type", "unknown")),
                            "sha256": str(sha).strip(),
                        }
                    )
        return sealed

    def _validate_plan_invariants(
        self,
        plan: InvestigationPlan,
        authorized_tools: set[str],
        valid_evidence_ids: set[str],
    ) -> None:
        """Validate tool whitelist and target evidence existence invariants."""
        if len(plan.steps) == 0:
            raise ValueError("Le plan d'investigation doit comporter au moins 1 étape.")

        if len(plan.steps) > MAX_PLAN_STEPS:
            raise ValueError(
                f"Le plan comporte {len(plan.steps)} étapes, dépassant la limite "
                f"stricte de {MAX_PLAN_STEPS} étapes."
            )

        for step in plan.steps:
            if step.tool_name not in authorized_tools:
                raise ValueError(
                    f"Outil non autorisé ou inconnu '{step.tool_name}'. "
                    f"Outils autorisés : {sorted(authorized_tools)}"
                )

            if str(step.target_evidence_id) not in valid_evidence_ids:
                raise ValueError(
                    f"Preuve cible '{step.target_evidence_id}' inexistante dans le dossier. "
                    f"Preuves scellées disponibles : {sorted(valid_evidence_ids)}"
                )

    def _parse_and_validate(
        self,
        raw_output: str,
        authorized_tools: set[str],
        valid_evidence_ids: set[str],
    ) -> InvestigationPlan:
        """Deserialize JSON, validate Pydantic schema, and check domain invariants."""
        cleaned = _extract_json_payload(raw_output)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Sortie LLM non-JSON ou malformée : {exc}") from exc

        if not isinstance(parsed, dict):
            raise ValueError("La sortie doit être un objet JSON avec 'steps' et 'summary'.")

        try:
            plan = InvestigationPlan.model_validate(parsed)
        except Exception as exc:
            raise ValueError(f"Violation du schéma InvestigationPlan : {exc}") from exc

        self._validate_plan_invariants(
            plan=plan,
            authorized_tools=authorized_tools,
            valid_evidence_ids=valid_evidence_ids,
        )
        return plan

    async def plan(
        self,
        evidences: list[Any] | None = None,
        case_id: uuid.UUID | str | None = None,
        run_id: uuid.UUID | str | None = None,
        incident_description: str | None = None,
        db: Session | None = None,
    ) -> PlannerResult:
        """Generate a validated investigation plan or pause if no sealed evidence is present."""
        session = db or self.db
        sealed_evidences = self._filter_sealed_evidences(
            evidences=evidences,
            case_id=case_id,
            db=session,
        )

        # 0-token short-circuit when no sealed evidence is available
        if not sealed_evidences:
            notification = (
                "Aucune preuve scellée disponible pour l'investigation. "
                "Session suspendue en attente de preuves scellées (sha256 non nul)."
            )
            logger.info("Planner short-circuited (0 tokens): %s", notification)

            # Mark session as paused in DB if session and run_id are available
            if session is not None and case_id is not None and run_id is not None:
                try:
                    from iryx.orchestrator.services import InvestigationService

                    case_uuid = uuid.UUID(str(case_id))
                    run_uuid = uuid.UUID(str(run_id))
                    InvestigationService(session).pause_investigation(
                        case_id=case_uuid,
                        run_id=run_uuid,
                        reason="attente de preuves scellées",
                    )
                except Exception as exc:
                    logger.warning("Could not persist paused state in DB: %s", exc)

            return PlannerResult(
                plan=None,
                status="paused",
                notification=notification,
                retries_used=0,
            )

        authorized_tools = self._resolve_authorized_tools()
        valid_evidence_ids = {ev["id"] for ev in sealed_evidences}

        # Build secure prompt with NFR-SEC-06 immunization
        system_prompt = build_system_prompt(
            role=LLMRole.PLANNER,
            custom_instructions=PLANNER_SYSTEM_INSTRUCTIONS,
        )

        inventory_lines = ["Inventaire des preuves numériques scellées disponibles :"]
        for ev in sealed_evidences:
            inventory_lines.append(
                f"- Preuve ID: {ev['id']} | Fichier: {ev['original_name']} | "
                f"Taille: {ev['file_size']} octets | Type détecté: {ev['detected_type']} | "
                f"SHA-256: {ev['sha256']}"
            )
        inventory_text = "\n".join(inventory_lines)
        wrapped_forensic_data = wrap_forensic_data(inventory_text)

        user_content_parts = []
        if incident_description and incident_description.strip():
            user_content_parts.append(
                f"Demande initiale / Contexte du dossier :\n{incident_description.strip()}"
            )
        user_content_parts.append(
            f"Consultez les preuves matérielles scellées suivantes :\n{wrapped_forensic_data}"
        )
        user_content_parts.append(
            f"Outils forensiques autorisés (ToolRegistry) : "
            f"{', '.join(sorted(authorized_tools))}\n"
            f"Veuillez proposer un plan d'investigation adapté (maximum {MAX_PLAN_STEPS} étapes) "
            "au format JSON."
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
                plan = self._parse_and_validate(
                    raw_output=raw_content,
                    authorized_tools=authorized_tools,
                    valid_evidence_ids=valid_evidence_ids,
                )

                # Persist validated plan in DB if session and run_id are available
                if session is not None and case_id is not None and run_id is not None:
                    try:
                        from iryx.orchestrator.services import InvestigationService

                        case_uuid = uuid.UUID(str(case_id))
                        run_uuid = uuid.UUID(str(run_id))
                        InvestigationService(session).save_validated_plan(
                            case_id=case_uuid,
                            run_id=run_uuid,
                            plan=plan,
                        )
                    except Exception as exc:
                        logger.warning("Could not persist validated plan in DB: %s", exc)

                logger.info(
                    "Investigation plan generated and validated successfully (retries: %d)",
                    attempt,
                )
                return PlannerResult(
                    plan=plan,
                    status="running",
                    notification=None,
                    retries_used=attempt,
                )

            except Exception as exc:
                last_error = str(exc)
                if attempt < MAX_CORRECTION_RETRIES:
                    logger.warning(
                        "Planner validation failed on attempt %d: %s. Sending correction prompt.",
                        attempt + 1,
                        last_error,
                    )
                    messages.append({"role": "assistant", "content": raw_content})
                    tools_str = ", ".join(sorted(authorized_tools))
                    evidences_str = ", ".join(sorted(valid_evidence_ids))
                    correction_prompt = (
                        "Le plan précédent est invalide pour la raison suivante :\n"
                        f"{last_error}\n\n"
                        "Veuillez corriger le JSON en respectant STRICTEMENT les contraintes :\n"
                        f"- Respecter le schéma JSON InvestigationPlan avec 'summary' et 'steps'.\n"
                        f"- Maximum {MAX_PLAN_STEPS} étapes au total dans la liste 'steps'.\n"
                        f"- Outils autorisés exclusivement parmi : {tools_str}.\n"
                        f"- Preuves cibles exclusivement parmi : {evidences_str}.\n"
                        "Répondez UNIQUEMENT avec le JSON valide, sans texte explicatif extérieur."
                    )
                    messages.append({"role": "user", "content": correction_prompt})
                else:
                    logger.error(
                        "Planner failed after %d correction attempts. Last error: %s",
                        MAX_CORRECTION_RETRIES,
                        last_error,
                    )
                    raise InvalidPlanException(
                        f"Échec de validation du plan d'investigation après "
                        f"{MAX_CORRECTION_RETRIES} tentatives de correction : {last_error}"
                    ) from exc

        raise InvalidPlanException("Échec inattendu lors de la génération du plan.")

    async def generate_plan(
        self,
        evidences: list[Any] | None = None,
        case_id: uuid.UUID | str | None = None,
        run_id: uuid.UUID | str | None = None,
        incident_description: str | None = None,
        db: Session | None = None,
    ) -> PlannerResult:
        """Alias for plan method."""
        return await self.plan(
            evidences=evidences,
            case_id=case_id,
            run_id=run_id,
            incident_description=incident_description,
            db=db,
        )

    def plan_sync(
        self,
        evidences: list[Any] | None = None,
        case_id: uuid.UUID | str | None = None,
        run_id: uuid.UUID | str | None = None,
        incident_description: str | None = None,
        db: Session | None = None,
    ) -> PlannerResult:
        """Synchronously execute plan generation, safely handling active event loops."""
        coro = self.plan(
            evidences=evidences,
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

    def generate_plan_sync(
        self,
        evidences: list[Any] | None = None,
        case_id: uuid.UUID | str | None = None,
        run_id: uuid.UUID | str | None = None,
        incident_description: str | None = None,
        db: Session | None = None,
    ) -> PlannerResult:
        """Alias for plan_sync method."""
        return self.plan_sync(
            evidences=evidences,
            case_id=case_id,
            run_id=run_id,
            incident_description=incident_description,
            db=db,
        )
