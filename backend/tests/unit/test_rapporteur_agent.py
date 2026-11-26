"""Unit tests for the H3-gated Rapporteur agent (Story 8.3)."""

import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from iryx.ai.schemas import LLMRole
from iryx.core.exceptions import ReportGenerationFailedException
from iryx.reporting.pseudonymizer import DeterministicPseudonymizer
from iryx.reporting.rapporteur_agent import (
    RapporteurAgent,
    _extract_mentioned_titles,
    _prefer_full_title,
)
from iryx.reporting.schemas import CANONICAL_SECTION_KEYS, ReportContent
from iryx.reporting.verdicts import verdict_flag

_CASE_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
_VALID_TITLE = "Connexion suspecte depuis 10.0.0.8"
_INVALID_TITLE = "Constat non validé confidentiel"


class FakeLLMClient:
    """Instrumented LLM double recording every external call."""

    def __init__(
        self,
        response: str,
        role: LLMRole = LLMRole.RAPPORTEUR,
        calls: list[list[dict[str, Any]]] | None = None,
    ) -> None:
        self.role = role
        self.response = response
        self.calls = calls if calls is not None else []
        self.roles_requested: list[LLMRole] = []

    def for_role(self, role: LLMRole) -> "FakeLLMClient":
        """Return a double preserving its configured role for verification."""
        self.roles_requested.append(role)
        return FakeLLMClient(self.response, role=self.role, calls=self.calls)

    async def complete(self, messages: list[dict[str, Any]], temperature: float = 0.0) -> dict:
        """Return a normalized response and record the emitted messages."""
        self.calls.append(messages)
        return {"content": self.response}


def _llm_response(**overrides: str) -> str:
    """Return a JSON LLM response with all eight canonical sections."""
    payload = {key: "Texte factuel." for key in CANONICAL_SECTION_KEYS}
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def _context(**overrides: Any) -> dict[str, Any]:
    """Return a minimal investigation context with one validated fact."""
    values: dict[str, Any] = {
        "case_id": _CASE_ID,
        "case": {"title": "Dossier test", "description": "Incident confirmé"},
        "facts": [{"title": _VALID_TITLE, "severity": "high"}],
        "invalid_finding_titles": [_INVALID_TITLE],
        "evidences": [{"original_name": "auth.log", "sha256": "a" * 64}],
        "observations": [{"tool_name": "log_parser", "summary": "Échecs répétés"}],
        "timeline": [{"timestamp_utc": "2026-11-25T10:00:00+00:00", "summary": "Connexion"}],
    }
    values.update(overrides)
    return values


def test_agent_without_approval_uses_local_template_without_llm() -> None:
    """Verify the default constructor never contacts an external client."""
    client = FakeLLMClient(_llm_response())
    content = RapporteurAgent(llm_client=client).generate_sync(_context())

    assert isinstance(content, ReportContent)
    assert content.metadata["mode"] == "local"
    assert _VALID_TITLE in next(
        section.content for section in content.sections if section.key == "constats_valides"
    )
    assert client.calls == []


def test_external_mode_requires_strict_bool_approval() -> None:
    """Verify only the literal boolean True unlocks external drafting."""
    client = FakeLLMClient(_llm_response())
    agent = RapporteurAgent(llm_client=client, pseudonymizer=DeterministicPseudonymizer())

    local = agent.generate_sync(_context(), h3_approved="true")  # type: ignore[arg-type]
    assert local.metadata["mode"] == "local"
    assert client.calls == []

    external = agent.generate_sync(_context(), h3_approved=True)
    assert external.metadata["mode"] == "external"
    assert len(client.calls) == 1


def test_local_flag_and_rejection_win_over_approval() -> None:
    """Verify a stale local flag or explicit rejection blocks the external client."""
    agent = RapporteurAgent(
        llm_client=FakeLLMClient(_llm_response()),
        pseudonymizer=DeterministicPseudonymizer(),
    )
    for overrides in (
        {"h3_approved": True, "local_report_mode": True},
        {"h3_approved": True, "h3_rejected": True},
    ):
        content = agent.generate_sync(_context(), **overrides)
        assert content.metadata["mode"] == "local"
    assert agent.llm_client.calls == []


def test_external_mode_requires_shared_pseudonymizer() -> None:
    """Verify no fresh pseudonymizer is silently created on the external path."""
    agent = RapporteurAgent(llm_client=FakeLLMClient(_llm_response()))
    with pytest.raises(ReportGenerationFailedException, match="Pseudonymiseur"):
        agent.generate_sync(_context(), h3_approved=True)


def test_external_client_must_be_configured_for_rapporteur_role() -> None:
    """Verify for_role is requested and the resolved client role is checked."""
    wrong = FakeLLMClient(_llm_response(), role=LLMRole.ANALYST)
    agent = RapporteurAgent(llm_client=wrong, pseudonymizer=DeterministicPseudonymizer())
    with pytest.raises(ReportGenerationFailedException, match="Rapporteur"):
        agent.generate_sync(_context(), h3_approved=True)
    assert wrong.roles_requested == [LLMRole.RAPPORTEUR]
    assert wrong.calls == []


def test_already_rapporteur_client_is_used_without_for_role() -> None:
    """Verify an already-scoped client is reused while a wrong-role client is re-resolved."""
    client = FakeLLMClient(_llm_response())
    agent = RapporteurAgent(
        llm_client=client,
        pseudonymizer=DeterministicPseudonymizer(),
    )
    assert agent.generate_sync(_context(), h3_approved=True).metadata["mode"] == "external"
    assert client.roles_requested == []
    assert len(client.calls) == 1

    wrong = FakeLLMClient(_llm_response(), role=LLMRole.ANALYST)
    wrong_agent = RapporteurAgent(
        llm_client=wrong,
        pseudonymizer=DeterministicPseudonymizer(),
    )
    with pytest.raises(ReportGenerationFailedException, match="Rapporteur"):
        wrong_agent.generate_sync(_context(), h3_approved=True)
    assert wrong.roles_requested == [LLMRole.RAPPORTEUR]
    assert wrong.calls == []


@pytest.mark.parametrize(
    "bad_section",
    [
        "observations",
        "resume_managerial",
        "chaine_des_preuves",
        "limites",
    ],
)
def test_unvalidated_title_is_rejected_in_any_section(bad_section: str) -> None:
    """Verify a known unvalidated finding title is rejected wherever it appears."""
    agent = RapporteurAgent(
        llm_client=FakeLLMClient(_llm_response(**{bad_section: f"Voir {_INVALID_TITLE}."})),
        pseudonymizer=DeterministicPseudonymizer(),
    )
    with pytest.raises(ReportGenerationFailedException, match="non validé"):
        agent.generate_sync(_context(), h3_approved=True)


@pytest.mark.parametrize(
    "fragment",
    [
        f"[high] {_INVALID_TITLE}",
        f"Constat n°4 : {_INVALID_TITLE}",
        f"finding: {_INVALID_TITLE}",
        json.dumps({"constats": [{"title": _INVALID_TITLE}]}, ensure_ascii=False),
        "[critical] Titre inventé sans déclaration préalable",
    ],
)
def test_structured_and_unknown_title_mentions_are_rejected(fragment: str) -> None:
    """Verify every defined mention shape must match a validated fact title."""
    agent = RapporteurAgent(
        llm_client=FakeLLMClient(_llm_response(observations=fragment)),
        pseudonymizer=DeterministicPseudonymizer(),
    )
    with pytest.raises(ReportGenerationFailedException):
        agent.generate_sync(_context(), h3_approved=True)


def test_invented_title_nested_in_a_list_is_rejected() -> None:
    """Verify a title hidden in a structured list cannot escape exact matching."""
    response: dict[str, Any] = {key: "Texte factuel." for key in CANONICAL_SECTION_KEYS}
    response["observations"] = {"constats": [{"title": ["Titre inventé"]}]}
    agent = RapporteurAgent(
        llm_client=FakeLLMClient(json.dumps(response, ensure_ascii=False)),
        pseudonymizer=DeterministicPseudonymizer(),
    )
    with pytest.raises(ReportGenerationFailedException, match="non validé"):
        agent.generate_sync(_context(), h3_approved=True)


def test_title_key_with_nested_mapping_value_is_rejected() -> None:
    """Verify a title wrapped in a nested mapping is still treated as a mention."""
    payload = {key: "Texte factuel." for key in CANONICAL_SECTION_KEYS}
    payload["observations"] = {"detail": {"title": {"value": "Titre inventé imbriqué"}}}
    agent = RapporteurAgent(
        llm_client=FakeLLMClient(json.dumps(payload, ensure_ascii=False)),
        pseudonymizer=DeterministicPseudonymizer(),
    )
    with pytest.raises(ReportGenerationFailedException, match="non validé"):
        agent.generate_sync(_context(), h3_approved=True)


def test_invalid_finding_title_used_as_json_key_is_rejected() -> None:
    """Verify an unvalidated title hidden as a JSON key is scanned too."""
    payload = {key: "Texte factuel." for key in CANONICAL_SECTION_KEYS}
    payload[_INVALID_TITLE] = "Texte factuel."
    agent = RapporteurAgent(
        llm_client=FakeLLMClient(json.dumps(payload, ensure_ascii=False)),
        pseudonymizer=DeterministicPseudonymizer(),
    )
    with pytest.raises(ReportGenerationFailedException, match="non validé"):
        agent.generate_sync(_context(), h3_approved=True)


def test_full_title_substitution_requires_unique_prefix_in_line() -> None:
    """Verify a short candidate only expands to a validated title when unambiguous."""
    full = "Constats réunis ce jour"
    prefix = "Constats réunis"
    assert _prefer_full_title(prefix, f'Constat : "{full}".', {full}) == full

    repeated = f'Constat "{prefix}" / "{full}".'
    assert _prefer_full_title(prefix, repeated, {full}) == prefix
    assert _extract_mentioned_titles(repeated, set(), {full}) == [full, prefix]
    assert _prefer_full_title("réunis ce", f'Constat : "réunis ce" {full}', {full}) == "réunis ce"


def test_constats_valides_are_rebuilt_from_facts() -> None:
    """Verify the LLM cannot alter the authoritative validated-facts section."""
    response = _llm_response(
        constats_valides="Section libre non fiable.",
        observations="Aucune référence externe.",
    )
    agent = RapporteurAgent(
        llm_client=FakeLLMClient(response),
        pseudonymizer=DeterministicPseudonymizer(),
    )
    content = agent.generate_sync(_context(), h3_approved=True)
    section = next(s for s in content.sections if s.key == "constats_valides")
    assert _INVALID_TITLE not in section.content
    assert "Connexion suspecte depuis" in section.content
    assert "[high]" in section.content


def test_llm_payload_accepts_code_fences_and_nested_sections() -> None:
    """Verify tolerant JSON parsing still requires all eight canonical sections."""
    payload = {
        "sections": [
            {"key": key, "content": "Texte."}
            for key in CANONICAL_SECTION_KEYS
        ]
    }
    response = f"```json\n{json.dumps(payload)}\n```"
    agent = RapporteurAgent(
        llm_client=FakeLLMClient(response),
        pseudonymizer=DeterministicPseudonymizer(),
    )
    assert agent.generate_sync(_context(), h3_approved=True).metadata["mode"] == "external"


def test_shared_pseudonymizer_keeps_preview_token_continuity() -> None:
    """Verify external drafting uses the injected store, not a fresh one."""
    pseudonymizer = DeterministicPseudonymizer()
    preview = pseudonymizer.pseudonymize(_VALID_TITLE, case_id=str(_CASE_ID))
    token = pseudonymizer.export_token(_CASE_ID)
    pseudonym = preview.pseudonymized_text
    assert pseudonym != _VALID_TITLE

    client = FakeLLMClient(_llm_response())
    agent = RapporteurAgent(
        llm_client=client,
        pseudonymizer=pseudonymizer,
        h3_approved=True,
    )
    agent.generate_sync(_context())
    prompt = client.calls[0][1]["content"]
    assert pseudonym in prompt
    assert _VALID_TITLE not in prompt
    assert _INVALID_TITLE not in prompt
    assert "auth.log" not in prompt
    assert "Incident confirmé" not in prompt
    assert "Échecs répétés" not in prompt
    # Quoted as a JSON value: the pseudonymized validated title legitimately
    # starts with "Connexion", but the raw timeline summary must not survive.
    assert '"Connexion"' not in prompt

    restored = DeterministicPseudonymizer()
    restored.load_store(_CASE_ID, token)
    assert restored.export_token(_CASE_ID) == token


def test_nested_structured_title_with_invented_value_is_rejected() -> None:
    """Verify a title key nested inside a section value is treated as a mention."""
    payload = {key: "Texte factuel." for key in CANONICAL_SECTION_KEYS}
    payload["observations"] = {
        "detail": {"title": "Titre inventé imbriqué", "texte": "Sans validation."}
    }
    agent = RapporteurAgent(
        llm_client=FakeLLMClient(json.dumps(payload, ensure_ascii=False)),
        pseudonymizer=DeterministicPseudonymizer(),
    )
    with pytest.raises(ReportGenerationFailedException, match="non validé"):
        agent.generate_sync(_context(), h3_approved=True)


def test_non_boolean_rejected_verdict_uses_shared_normalization() -> None:
    """Verify string verdicts never turn an approval into a local fallback."""
    client = FakeLLMClient(_llm_response())
    agent = RapporteurAgent(
        llm_client=client,
        pseudonymizer=DeterministicPseudonymizer(),
    )

    external = agent.generate_sync(
        _context(),
        h3_approved=True,
        h3_rejected="false",  # type: ignore[arg-type]
        local_report_mode="false",  # type: ignore[arg-type]
    )
    assert external.metadata["mode"] == "external"
    assert len(client.calls) == 1

    local = agent.generate_sync(
        _context(),
        h3_approved=True,
        h3_rejected="true",  # type: ignore[arg-type]
    )
    assert local.metadata["mode"] == "local"
    assert len(client.calls) == 1


def test_integer_verdict_flag_accepts_only_one() -> None:
    """Verify checkpointed numeric 1 is affirmative while other integers are not."""
    assert verdict_flag(1) is True
    assert verdict_flag(2) is False
    assert verdict_flag(0) is False


def test_client_without_explicit_role_is_rejected() -> None:
    """Verify a missing role attribute can never default to Rapporteur."""

    class _RolelessClient:
        async def complete(self, messages: list[dict[str, Any]], temperature: float = 0.0) -> dict:
            return {"content": _llm_response()}

    agent = RapporteurAgent(
        llm_client=_RolelessClient(),
        pseudonymizer=DeterministicPseudonymizer(),
    )
    with pytest.raises(ReportGenerationFailedException, match="rôle explicite"):
        agent.generate_sync(_context(), h3_approved=True)


def test_malformed_pseudonymizer_result_never_falls_back_to_raw_text() -> None:
    """Verify an invalid pseudonymization payload aborts instead of leaking raw text."""

    class _MalformedPseudonymizer:
        def pseudonymize(self, text: str, case_id: Any = None) -> dict[str, Any]:
            return {"entity_count": 0}

    client = FakeLLMClient(_llm_response())
    agent = RapporteurAgent(
        llm_client=client,
        pseudonymizer=_MalformedPseudonymizer(),
    )
    with pytest.raises(ReportGenerationFailedException, match="pseudonymisation"):
        agent.generate_sync(_context(), h3_approved=True)
    assert client.calls == []


def test_generate_sync_from_a_running_event_loop_uses_a_fresh_coroutine() -> None:
    """Verify an active loop does not resubmit an already-created coroutine."""
    client = FakeLLMClient(_llm_response())
    agent = RapporteurAgent(
        llm_client=client,
        pseudonymizer=DeterministicPseudonymizer(),
    )

    async def _from_running_loop() -> ReportContent:
        return agent.generate_sync(_context(), h3_approved=True)

    content = asyncio.run(_from_running_loop())
    assert content.metadata["mode"] == "external"
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "reserved_key",
    ["case", "findings", "generation_id", "version", "created_at", "unvalidated_finding_titles"],
)
def test_reserved_kwargs_passed_directly_are_refused(reserved_key: str) -> None:
    """Verify reserved context keys cannot be injected through **kwargs."""
    agent = RapporteurAgent(pseudonymizer=DeterministicPseudonymizer())
    with pytest.raises(ReportGenerationFailedException, match="réservés"):
        asyncio.run(agent.generate(_context(), **{reserved_key: "valeur"}))


def test_non_integer_version_is_a_typed_generation_failure() -> None:
    """Verify an unparsable version fails cleanly before any drafting happens."""
    agent = RapporteurAgent(llm_client=FakeLLMClient(_llm_response()))
    with pytest.raises(ReportGenerationFailedException, match="version invalide"):
        agent.generate_sync(_context(version="deux"))
    assert agent.llm_client.calls == []

    assert agent.generate_sync(_context()).version == 1


def test_validated_finding_with_empty_title_is_rejected() -> None:
    """Verify a validated finding is never silently dropped for an empty title."""
    agent = RapporteurAgent(
        llm_client=FakeLLMClient(_llm_response()),
        pseudonymizer=DeterministicPseudonymizer(),
    )
    with pytest.raises(ReportGenerationFailedException, match="sans titre"):
        agent.generate_sync(
            _context(facts=[{"title": "   ", "severity": "high"}]), h3_approved=True
        )


def test_pseudonymized_unvalidated_title_is_excluded_and_echo_fails() -> None:
    """Verify a pseudonymized rejection is never accepted when echoed by the LLM."""
    invalid = "Connexion depuis 198.51.100.27"
    pseudonymizer = DeterministicPseudonymizer()
    pseudonymized = pseudonymizer.pseudonymize(invalid, case_id=str(_CASE_ID)).pseudonymized_text
    client = FakeLLMClient(_llm_response(observations=f"Voir {pseudonymized}."))
    agent = RapporteurAgent(llm_client=client, pseudonymizer=pseudonymizer)
    context = _context(
        facts=[{"title": "Connexion suspecte", "severity": "high"}],
        invalid_finding_titles=[invalid],
    )

    with pytest.raises(ReportGenerationFailedException) as exc_info:
        agent.generate_sync(context, h3_approved=True)
    assert exc_info.value.code == "REPORT_GENERATION_FAILED"
    assert pseudonymized in client.calls[0][1]["content"]


@pytest.mark.parametrize(
    "fragment",
    [f"- [high] {_INVALID_TITLE}", f"1. [critical] {_INVALID_TITLE}"],
)
def test_bracketed_title_after_list_marker_is_rejected(fragment: str) -> None:
    """Verify a list marker before a bracketed severity is normalized."""
    agent = RapporteurAgent(
        llm_client=FakeLLMClient(_llm_response(observations=fragment)),
        pseudonymizer=DeterministicPseudonymizer(),
    )
    with pytest.raises(ReportGenerationFailedException, match="non validé"):
        agent.generate_sync(_context(), h3_approved=True)


def test_validated_title_with_dot_is_accepted() -> None:
    """Verify dots inside a validated title are not treated as sentence breaks."""
    validated = "Connexion 10.0.0.8 validée"
    pseudonymizer = DeterministicPseudonymizer()
    pseudonym = pseudonymizer.pseudonymize(validated, case_id=str(_CASE_ID)).pseudonymized_text
    agent = RapporteurAgent(
        llm_client=FakeLLMClient(
            _llm_response(observations=f"Constat : {pseudonym}. Analyse terminée.")
        ),
        pseudonymizer=pseudonymizer,
    )
    content = agent.generate_sync(
        _context(facts=[{"title": validated, "severity": "high"}]), h3_approved=True
    )
    assert content.metadata["mode"] == "external"


def test_constats_valides_prose_does_not_fail() -> None:
    """Verify ordinary prose is not mistaken for an introduced finding title."""
    agent = RapporteurAgent(
        llm_client=FakeLLMClient(
            _llm_response(observations="Les constats valides sont au nombre de un.")
        ),
        pseudonymizer=DeterministicPseudonymizer(),
    )
    assert agent.generate_sync(_context(), h3_approved=True).metadata["mode"] == "external"


class _SlowRapporteurClient:
    """LLM double that records cancellation of the network call."""

    def __init__(self) -> None:
        self.role = LLMRole.RAPPORTEUR
        self.cancelled = False

    def for_role(self, role: LLMRole) -> "_SlowRapporteurClient":
        """Return itself for the requested rapporteur role."""
        return self

    async def complete(self, messages: list[dict[str, Any]], temperature: float = 0.0) -> dict:
        """Wait long enough for the deadline to fire."""
        try:
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return {"content": _llm_response()}


@pytest.mark.parametrize("active_loop", [False, True])
def test_generate_sync_deadline_is_enforced_in_both_branches(
    monkeypatch: pytest.MonkeyPatch,
    active_loop: bool,
) -> None:
    """Verify the executor deadline applies with and without a running loop."""
    monkeypatch.setattr("iryx.reporting.rapporteur_agent._SYNC_TIMEOUT_SECONDS", 0.02)
    client = _SlowRapporteurClient()
    agent = RapporteurAgent(
        llm_client=client,
        pseudonymizer=DeterministicPseudonymizer(),
    )

    async def _from_running_loop() -> ReportContent:
        return agent.generate_sync(_context(), h3_approved=True)

    with pytest.raises(ReportGenerationFailedException, match="délai"):
        if active_loop:
            asyncio.run(_from_running_loop())
        else:
            agent.generate_sync(_context(), h3_approved=True)
    assert client.cancelled is True


def test_external_network_call_is_cancelled_on_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify wait_for cancels the underlying client coroutine, not just the future."""
    monkeypatch.setattr("iryx.reporting.rapporteur_agent._SYNC_TIMEOUT_SECONDS", 0.02)
    client = _SlowRapporteurClient()
    agent = RapporteurAgent(llm_client=client, pseudonymizer=DeterministicPseudonymizer())

    with pytest.raises(ReportGenerationFailedException, match="délai"):
        asyncio.run(agent.generate(_context(), h3_approved=True))
    assert client.cancelled is True


def test_generate_sync_wraps_unexpected_worker_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify any worker exception leaves through the typed report envelope."""
    agent = RapporteurAgent()

    async def _failing(*args: Any, **kwargs: Any) -> ReportContent:
        raise ValueError("panne interne")

    monkeypatch.setattr(agent, "generate", _failing)
    with pytest.raises(ReportGenerationFailedException) as exc_info:
        agent.generate_sync(_context())

    assert exc_info.value.code == "REPORT_GENERATION_FAILED"
    assert "ValueError" in str(exc_info.value)


def test_generate_sync_wraps_closed_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify a shut-down drafting engine is reported as a generation failure."""
    closed = ThreadPoolExecutor(max_workers=1)
    closed.shutdown(wait=True)
    monkeypatch.setattr("iryx.reporting.rapporteur_agent._SYNC_EXECUTOR", closed)

    agent = RapporteurAgent()
    with pytest.raises(ReportGenerationFailedException) as exc_info:
        agent.generate_sync(_context())

    assert exc_info.value.code == "REPORT_GENERATION_FAILED"
    assert "moteur de rédaction" in str(exc_info.value)

