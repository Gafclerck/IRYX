"""Deterministic Markdown/JSON compiler and SHA-256 sealing (Story 8.3)."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from iryx.reporting.schemas import (
    CANONICAL_SECTION_KEYS,
    ReportContent,
    ReportFormat,
    ReportSection,
)


@dataclass(frozen=True)
class CompiledReport:
    """Exact byte strings persisted for one report generation."""

    content: ReportContent
    documents: dict[ReportFormat, str]
    hashes: dict[ReportFormat, str]

    @property
    def markdown(self) -> str:
        """Return the exact Markdown document bytes as text."""
        return self.documents[ReportFormat.MARKDOWN]

    @property
    def json(self) -> str:
        """Return the exact JSON document bytes as text."""
        return self.documents[ReportFormat.JSON]


def sha256_text(text: str) -> str:
    """Hash the exact UTF-8 bytes that will be persisted."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ordered_sections(content: ReportContent) -> list[ReportSection]:
    """Sort sections deterministically by canonical order, then key."""
    order = {key: index for index, key in enumerate(CANONICAL_SECTION_KEYS)}
    return sorted(content.sections, key=lambda section: (order[section.key], section.key))


def render_markdown(content: ReportContent) -> str:
    """Render the canonical structure as a stable, human-readable Markdown document."""
    lines = [
        "# Rapport d'incident IRYX",
        "",
        f"- Dossier : {content.case_id}",
    ]
    if content.run_id is not None:
        lines.append(f"- Session : {content.run_id}")
    if content.generation_id is not None:
        lines.append(f"- Génération : {content.generation_id}")
    lines.append(f"- Version : {content.version}")
    if content.created_at is not None:
        lines.append(f"- Généré le : {content.created_at.isoformat()}")
    lines.append("")

    for section in _ordered_sections(content):
        lines.extend([f"## {section.title}", "", section.content.rstrip() or "(aucune donnée)", ""])

    return "\n".join(lines).rstrip() + "\n"


def render_json(content: ReportContent) -> str:
    """Serialize the canonical structure with stable keys and separators."""
    payload: dict[str, Any] = {
        "case_id": str(content.case_id),
        "generation_id": str(content.generation_id) if content.generation_id else None,
        "run_id": str(content.run_id) if content.run_id else None,
        "version": content.version,
        "created_at": content.created_at.isoformat() if content.created_at else None,
        "metadata": content.metadata,
        "sections": [
            {
                "key": section.key,
                "title": section.title,
                "content": section.content,
                "order": index,
            }
            for index, section in enumerate(_ordered_sections(content))
        ],
    }
    return json.dumps(
        payload,
        default=str,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def compile_report(content: ReportContent) -> CompiledReport:
    """Compile and seal one report generation in both supported formats."""
    documents = {
        ReportFormat.MARKDOWN: render_markdown(content),
        ReportFormat.JSON: render_json(content),
    }
    hashes = {fmt: sha256_text(document) for fmt, document in documents.items()}
    return CompiledReport(content=content, documents=documents, hashes=hashes)


class ReportCompiler:
    """Object-oriented facade over the deterministic compiler functions."""

    render_markdown = staticmethod(render_markdown)
    render_json = staticmethod(render_json)
    sha256_text = staticmethod(sha256_text)
    compile = staticmethod(compile_report)
