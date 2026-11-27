"""Tests de non-régression pour le confinement des chemins (Path Traversal / CWE-22)."""

import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from iryx.core.config import get_settings
from iryx.core.exceptions import ValidationException
from iryx.gateway.base import BaseTool, ToolExecutionContext
from iryx.gateway.tools.evtx_parser import EvtxParserParameters, EvtxParserTool
from iryx.gateway.tools.log_parser import LogCsvParserParameters, LogCsvParserTool
from iryx.gateway.tools.prefetch_parser import PrefetchParserParameters, PrefetchParserTool
from iryx.gateway.tools.registry_parser import RegistryParserParameters, RegistryParserTool
from iryx.gateway.tools.volatility_analyzer import Volatility3Parameters, Volatility3Tool

TOOL_CASES: list[tuple[str, Callable[[], BaseTool], Callable[[str], Any]]] = [
    ("log_parser", LogCsvParserTool, lambda fp: LogCsvParserParameters(file_path=fp)),
    ("evtx_parser", EvtxParserTool, lambda fp: EvtxParserParameters(file_path=fp)),
    ("prefetch_parser", PrefetchParserTool, lambda fp: PrefetchParserParameters(file_path=fp)),
    ("registry_parser", RegistryParserTool, lambda fp: RegistryParserParameters(file_path=fp)),
    (
        "volatility_analyzer",
        Volatility3Tool,
        lambda fp: Volatility3Parameters(file_path=fp, plugin_name="windows.pslist"),
    ),
]


@pytest.fixture
def confined_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Configure isolated evidence storage and staging directories under tmp_path."""
    storage_dir = tmp_path / "evidence_storage"
    staging_dir = tmp_path / "evidence_staging"
    storage_dir.mkdir(parents=True)
    staging_dir.mkdir(parents=True)

    settings = get_settings()
    monkeypatch.setattr(settings, "evidence_storage_path", str(storage_dir))
    monkeypatch.setattr(settings, "evidence_staging_path", str(staging_dir))
    return storage_dir, staging_dir


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool_name", "tool_cls", "params_factory"), TOOL_CASES)
async def test_tools_reject_file_path_outside_evidence_storage(
    tmp_path: Path,
    confined_dirs: tuple[Path, Path],
    tool_name: str,
    tool_cls: Callable[[], BaseTool],
    params_factory: Callable[[str], Any],
) -> None:
    """Un fichier hors du stockage de preuves ne doit jamais être lu via file_path."""
    outside_file = tmp_path / f"hors_perimetre_{tool_name}.bin"
    outside_file.write_text("donnee_factice_hors_perimetre\n", encoding="utf-8")

    tool = tool_cls()
    params = params_factory(str(outside_file))
    ctx = ToolExecutionContext(case_id=uuid.uuid4())

    with pytest.raises(ValidationException, match="hors périmètre"):
        await tool.execute(params, ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool_name", "tool_cls", "params_factory"), TOOL_CASES)
async def test_tools_reject_path_traversal_sequence(
    tmp_path: Path,
    confined_dirs: tuple[Path, Path],
    tool_name: str,
    tool_cls: Callable[[], BaseTool],
    params_factory: Callable[[str], Any],
) -> None:
    """Une séquence de traversée '../' sortant du périmètre doit être rejetée."""
    storage_dir, _ = confined_dirs
    nested_dir = storage_dir / "case_sub"
    nested_dir.mkdir(parents=True)
    outside_file = tmp_path / f"secret_{tool_name}.bin"
    outside_file.write_text("acces_non_autorise\n", encoding="utf-8")

    traversal_path = str(nested_dir / ".." / ".." / outside_file.name)

    tool = tool_cls()
    params = params_factory(traversal_path)
    ctx = ToolExecutionContext(case_id=uuid.uuid4())

    with pytest.raises(ValidationException, match="hors périmètre"):
        await tool.execute(params, ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool_name", "tool_cls", "params_factory"), TOOL_CASES)
async def test_tools_reject_symlink_escaping_perimeter(
    tmp_path: Path,
    confined_dirs: tuple[Path, Path],
    tool_name: str,
    tool_cls: Callable[[], BaseTool],
    params_factory: Callable[[str], Any],
) -> None:
    """Un lien symbolique dans le périmètre pointant à l'extérieur doit être rejeté."""
    storage_dir, _ = confined_dirs
    outside_file = tmp_path / f"target_secret_{tool_name}.bin"
    outside_file.write_text("secret_externe\n", encoding="utf-8")

    symlink_path = storage_dir / f"lien_malveillant_{tool_name}.bin"
    symlink_path.symlink_to(outside_file)

    tool = tool_cls()
    params = params_factory(str(symlink_path))
    ctx = ToolExecutionContext(case_id=uuid.uuid4())

    with pytest.raises(ValidationException, match="hors périmètre"):
        await tool.execute(params, ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool_name", "tool_cls", "params_factory"), TOOL_CASES)
async def test_tools_reject_empty_file_path(
    confined_dirs: tuple[Path, Path],
    tool_name: str,
    tool_cls: Callable[[], BaseTool],
    params_factory: Callable[[str], Any],
) -> None:
    """Un file_path vide ou composé uniquement d'espaces doit être rejeté."""
    tool = tool_cls()
    params = params_factory("   ")
    ctx = ToolExecutionContext(case_id=uuid.uuid4())

    with pytest.raises(ValidationException, match="hors périmètre"):
        await tool.execute(params, ctx)


@pytest.mark.asyncio
async def test_prefetch_directory_rejects_symlink_escaping_perimeter(
    tmp_path: Path,
    confined_dirs: tuple[Path, Path],
) -> None:
    """En mode répertoire, PrefetchParserTool doit bloquer un .pf symlink pointant hors périmètre."""
    storage_dir, _ = confined_dirs
    pf_dir = storage_dir / "prefetch_dir"
    pf_dir.mkdir()

    outside_file = tmp_path / "secret_prefetch.pf"
    outside_file.write_bytes(b"MAM\x04\x00\x00\x00\x00" + b"\x00" * 32)
    (pf_dir / "evil.pf").symlink_to(outside_file)

    tool = PrefetchParserTool()
    params = PrefetchParserParameters(file_path=str(pf_dir))
    ctx = ToolExecutionContext(case_id=uuid.uuid4())

    result = await tool.execute(params, ctx)
    assert result.metadata["files_analyzed"] == 1
    assert result.metadata["total_executions"] == 0
    assert len(result.metadata["errors"]) == 1
    assert "hors périmètre" in result.metadata["errors"][0]["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool_name", "tool_cls", "params_factory"), TOOL_CASES)
async def test_tools_accept_legitimate_confined_paths(
    confined_dirs: tuple[Path, Path],
    tool_name: str,
    tool_cls: Callable[[], BaseTool],
    params_factory: Callable[[str], Any],
) -> None:
    """Un chemin légitime dans storage ou staging est accepté par _resolve_source."""
    storage_dir, staging_dir = confined_dirs
    for idx, base_dir in enumerate((storage_dir, staging_dir)):
        valid_file = base_dir / f"preuve_valide_{tool_name}_{idx}.log"
        valid_file.write_text(
            "2026-01-01T00:00:00Z INFO evenement_legitime\n",
            encoding="utf-8",
        )

        tool = tool_cls()
        params = params_factory(str(valid_file))
        ctx = ToolExecutionContext(case_id=uuid.uuid4())

        if isinstance(tool, LogCsvParserTool):
            result = await tool.execute(params, ctx)
            assert result.status.value == "success"
            assert len(result.observations) == 1
        else:
            resolved_path, _ = tool._resolve_source(params, ctx)  # type: ignore[attr-defined]
            assert resolved_path == valid_file.resolve()
