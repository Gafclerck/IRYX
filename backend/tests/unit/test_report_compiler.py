"""Unit tests for the deterministic report compiler and SHA-256 sealing (Story 8.3)."""

import hashlib
import json
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from iryx.reporting.compiler import (
    CompiledReport,
    ReportCompiler,
    compile_report,
    render_json,
    render_markdown,
    sha256_text,
)
from iryx.reporting.schemas import (
    CANONICAL_SECTION_KEYS,
    CANONICAL_SECTION_TITLES,
    ReportContent,
    ReportFormat,
    ReportOut,
    ReportSection,
)

_CASE_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
_GENERATION_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
_RUN_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
_CREATED_AT = datetime(2026, 11, 25, 10, 30, tzinfo=UTC)


def _content(**overrides: object) -> ReportContent:
    """Build canonical report content with eight unique sections."""
    sections = [
        ReportSection(
            key=key,
            title=title,
            content=f"Contenu de {key}",
            order=index,
        )
        for index, (key, title) in enumerate(
            zip(CANONICAL_SECTION_KEYS, CANONICAL_SECTION_TITLES, strict=True)
        )
    ]
    values: dict[str, object] = {
        "case_id": _CASE_ID,
        "generation_id": _GENERATION_ID,
        "run_id": _RUN_ID,
        "version": 1,
        "created_at": _CREATED_AT,
        "metadata": {"mode": "local"},
        "sections": sections,
    }
    values.update(overrides)
    return ReportContent.model_validate(values)


def test_report_content_rejects_mismatched_key_title_pair() -> None:
    """Verify a canonical key cannot carry another section's canonical title."""
    sections = [
        ReportSection(
            key=key,
            title=title,
            content=f"Contenu de {key}",
            order=index,
        )
        for index, (key, title) in enumerate(
            zip(CANONICAL_SECTION_KEYS, CANONICAL_SECTION_TITLES, strict=True)
        )
    ]
    # Permute two canonical keys while keeping all eight titles unique, so only
    # the (key, title) pair validation can detect the inconsistency.
    sections[4] = ReportSection.model_construct(
        key=CANONICAL_SECTION_KEYS[5],
        title=CANONICAL_SECTION_TITLES[4],
        content="Observations",
        order=4,
    )
    sections[5] = ReportSection.model_construct(
        key=CANONICAL_SECTION_KEYS[4],
        title=CANONICAL_SECTION_TITLES[5],
        content="Constats",
        order=5,
    )
    with pytest.raises(ValidationError, match="canonique"):
        ReportContent(case_id=_CASE_ID, sections=sections)


def test_report_out_rejects_unknown_format_and_status() -> None:
    """Verify public report output validates enum values explicitly."""
    values = {
        "id": _CASE_ID,
        "case_id": _CASE_ID,
        "generation_id": _GENERATION_ID,
        "format": "markdown",
        "version": 1,
        "status": "draft",
        "sha256": "a" * 64,
        "content": "contenu",
        "created_at": _CREATED_AT,
    }
    assert ReportOut.model_validate(values).format is ReportFormat.MARKDOWN
    with pytest.raises(ValidationError):
        ReportOut.model_validate({**values, "format": "pdf"})
    with pytest.raises(ValidationError):
        ReportOut.model_validate({**values, "status": "inconnu"})


def test_render_json_serializes_non_json_metadata() -> None:
    """Verify custom metadata values are stringified instead of raising TypeError."""

    class _CustomValue:
        def __str__(self) -> str:
            return "valeur-custom"

    content = _content(metadata={"objet": _CustomValue()})
    payload = json.loads(render_json(content))
    assert payload["metadata"]["objet"] == "valeur-custom"


def test_report_content_requires_exactly_eight_canonical_sections() -> None:
    """Verify Pydantic rejects missing or duplicated canonical sections."""
    with pytest.raises(ValidationError):
        ReportContent.model_validate(
            {
                "case_id": _CASE_ID,
                "sections": [
                    ReportSection(key=key, title=title, content="x")
                    for key, title in zip(
                        CANONICAL_SECTION_KEYS[:7],
                        CANONICAL_SECTION_TITLES[:7],
                        strict=True,
                    )
                ],
            }
        )
    sections = [
        ReportSection(key=key, title=title, content="x")
        for key, title in zip(
            CANONICAL_SECTION_KEYS, CANONICAL_SECTION_TITLES, strict=True
        )
    ]
    sections[-1] = ReportSection(key=CANONICAL_SECTION_KEYS[0], title="Résumé managérial")
    with pytest.raises(ValidationError):
        ReportContent.model_validate({"case_id": _CASE_ID, "sections": sections})


def test_section_aliases_resolve_to_canonical_pair() -> None:
    """Verify known aliases normalize to the canonical key and title."""
    section = ReportSection(key="findings", title="findings", content="constats")
    assert section.key == "constats_valides"
    assert section.title == "Constats validés"


def test_markdown_contains_all_sections_and_metadata() -> None:
    """Verify the rendered Markdown exposes every canonical section and traceability."""
    markdown = render_markdown(_content())
    for title in CANONICAL_SECTION_TITLES:
        assert f"## {title}" in markdown
    assert str(_CASE_ID) in markdown
    assert str(_GENERATION_ID) in markdown
    assert str(_RUN_ID) in markdown
    assert "Version : 1" in markdown
    assert markdown.endswith("\n")


def test_json_is_deterministic_and_stable() -> None:
    """Verify JSON uses stable keys, compact separators and canonical ordering."""
    first = _content()
    second = _content()
    second.metadata = {"mode": "local"}
    assert render_json(first) == render_json(second)

    payload = json.loads(render_json(first))
    assert [section["key"] for section in payload["sections"]] == list(CANONICAL_SECTION_KEYS)
    assert [section["order"] for section in payload["sections"]] == list(range(8))
    assert payload["case_id"] == str(_CASE_ID)
    assert payload["generation_id"] == str(_GENERATION_ID)
    assert ": " not in render_json(first)


def test_hash_is_computed_on_exact_persisted_bytes() -> None:
    """Verify both hashes are SHA-256 of the exact UTF-8 strings that are stored."""
    compiled = compile_report(_content())
    assert isinstance(compiled, CompiledReport)
    for fmt in (ReportFormat.MARKDOWN, ReportFormat.JSON):
        document = compiled.documents[fmt]
        assert compiled.hashes[fmt] == hashlib.sha256(document.encode("utf-8")).hexdigest()
        assert compiled.hashes[fmt] == sha256_text(document)
        assert len(compiled.hashes[fmt]) == 64
        assert compiled.hashes[fmt].islower()
    assert compiled.markdown == compiled.documents[ReportFormat.MARKDOWN]
    assert compiled.json == compiled.documents[ReportFormat.JSON]


def test_compile_report_canonicalizes_permuted_sections() -> None:
    """Verify permuted input sections compile in canonical order and seal both bytes."""
    content = _content(sections=list(reversed(_content().sections)))
    compiled = compile_report(content)

    json_document = compiled.documents[ReportFormat.JSON]
    markdown_document = compiled.documents[ReportFormat.MARKDOWN]
    payload = json.loads(json_document)
    assert [section["key"] for section in payload["sections"]] == list(CANONICAL_SECTION_KEYS)
    assert [section["order"] for section in payload["sections"]] == list(range(8))
    headings = [line[3:] for line in markdown_document.splitlines() if line.startswith("## ")]
    assert headings == list(CANONICAL_SECTION_TITLES)

    assert compiled.hashes[ReportFormat.JSON] == sha256_text(json_document)
    assert compiled.hashes[ReportFormat.MARKDOWN] == sha256_text(markdown_document)


def test_hash_changes_when_content_changes() -> None:
    """Verify a single byte change produces a different digest."""
    first = sha256_text("contenu A")
    second = sha256_text("contenu B")
    assert first != second


def test_unicode_and_blank_sections_are_rendered_deterministically() -> None:
    """Verify accented section content is preserved and empty sections are explicit."""
    sections = [
        ReportSection(key=key, title=title, content="Évidence — café ✓" if index == 0 else "")
        for index, (key, title) in enumerate(
            zip(CANONICAL_SECTION_KEYS, CANONICAL_SECTION_TITLES, strict=True)
        )
    ]
    content = ReportContent(case_id=_CASE_ID, sections=sections)
    markdown = render_markdown(content)
    assert "Évidence — café ✓" in markdown
    assert "(aucune donnée)" in markdown
    assert "café" in render_json(content)
    assert compile_report(content).hashes[ReportFormat.MARKDOWN] == sha256_text(markdown)


def test_report_compiler_facade_matches_module_functions() -> None:
    """Verify the object facade delegates to the same deterministic functions."""
    content = _content()
    assert ReportCompiler.render_markdown(content) == render_markdown(content)
    assert ReportCompiler.render_json(content) == render_json(content)
    assert ReportCompiler.compile(content).hashes == compile_report(content).hashes
