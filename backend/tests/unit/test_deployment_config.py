"""Vérification statique de la configuration Docker (Stories 9.1 et 9.2).

Sans démon Docker, ces tests valident la configuration cible ; ``docker inspect``
et la sonde dans ``iryx-analysis`` restent les contrôles d'exécution.
"""

from __future__ import annotations

import errno
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent
COMPOSE_FILE = BACKEND_ROOT / "docker-compose.yml"
DOCKERIGNORE_FILE = PROJECT_ROOT / ".dockerignore"
ENV_EXAMPLE = BACKEND_ROOT / ".env.example"
README = PROJECT_ROOT / "README.md"
DOCKER_DIR = BACKEND_ROOT / "docker"
DOCKERFILE_API = DOCKER_DIR / "Dockerfile.api"
DOCKERFILE_WORKER = DOCKER_DIR / "Dockerfile.worker"
ENTRYPOINT_API = DOCKER_DIR / "entrypoint-api.sh"
CHECK_AIRGAP = DOCKER_DIR / "check_airgap.py"
EVIDENCE_SERVICE = BACKEND_ROOT / "src/iryx/evidence/services.py"
EVIDENCE_TASKS = BACKEND_ROOT / "src/iryx/evidence/tasks.py"
SYMBOLS_GITIGNORE = DOCKER_DIR / "symbols" / ".gitignore"

EXPECTED_SERVICES = {
    "postgres",
    "redis",
    "iryx-api",
    "iryx-worker",
    "iryx-analysis",
}
DEFAULT_SERVICES = EXPECTED_SERVICES - {"iryx-analysis"}
HARDENED_SERVICES = {"iryx-api", "iryx-worker", "iryx-analysis"}
RAW_MOUNT = "evidence_data:/data/evidence/raw:ro"
STAGING_MOUNT = "evidence_staging_data:/data/evidence/staging"
SYMBOLS_MOUNT = "symbols_data:/opt/volatility3/symbols:ro"
EXPECTED_SYMBOLS_SHA256 = "c7e49e8a520bfd68cfa1907cbcf9581c15f9e761dfb61b369527ec50c76251b3"


def load_compose() -> dict[str, Any]:
    """Load the Compose file without requiring a Docker daemon."""
    with COMPOSE_FILE.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    assert isinstance(config, dict)
    return config


def load_check_airgap() -> ModuleType:
    """Load the probe module without executing its ``__main__`` block."""
    spec = importlib.util.spec_from_file_location("check_airgap", CHECK_AIRGAP)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compose_defines_four_default_services_and_one_profiled() -> None:
    """Only the four D-22 services start by default; analysis is opt-in."""
    services = load_compose()["services"]
    assert set(services) == EXPECTED_SERVICES
    for name in DEFAULT_SERVICES:
        assert "profiles" not in services[name], f"{name} ne doit pas être profilé"
    assert services["iryx-analysis"]["profiles"] == ["analysis"]


def test_default_services_have_healthchecks() -> None:
    """Each default probe must target the real dependency, endpoint or process."""
    services = load_compose()["services"]
    for name in DEFAULT_SERVICES:
        healthcheck = services[name].get("healthcheck")
        assert isinstance(healthcheck, dict), f"{name} a besoin d'un healthcheck"
        assert healthcheck.get("test"), f"{name} a besoin d'une sonde"

    probes = {name: services[name]["healthcheck"]["test"] for name in DEFAULT_SERVICES}
    assert probes["postgres"] == [
        "CMD-SHELL",
        'pg_isready -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}"',
    ]
    assert probes["redis"] == ["CMD", "redis-cli", "ping"]
    assert "http://127.0.0.1:8000/health" in probes["iryx-api"][-1]
    worker_probe = probes["iryx-worker"][-1]
    assert "/proc/[0-9]*/cmdline" in worker_probe
    assert "any(part.endswith('celery') for part in parts)" in worker_probe
    assert "'worker' in parts" in worker_probe


def test_dependencies_wait_for_healthy_services() -> None:
    """API and worker may only start once their dependencies are healthy."""
    services = load_compose()["services"]

    api_deps = services["iryx-api"]["depends_on"]
    assert api_deps["postgres"] == {"condition": "service_healthy"}
    assert api_deps["redis"] == {"condition": "service_healthy"}

    worker_deps = services["iryx-worker"]["depends_on"]
    for dependency in ("postgres", "redis", "iryx-api"):
        assert worker_deps[dependency] == {"condition": "service_healthy"}


def test_only_api_publishes_port_8000() -> None:
    """No database, broker or analysis service may publish a host port."""
    published: list[str] = []
    for service in load_compose()["services"].values():
        published.extend(service.get("ports", []))
    assert published == ["8000:8000"]


def test_no_hardcoded_secret_or_host_path_in_compose() -> None:
    """Secrets come from required interpolation; volumes are named, never bound."""
    compose = load_compose()
    for name, service in compose["services"].items():
        if "env_file" in service:
            assert service["env_file"] == ".env", f"{name} doit lire backend/.env"
        for volume in service.get("volumes", []):
            source = volume.split(":")[0]
            assert not source.startswith((".", "/", "~", "C:")), volume

    assert "env_file" not in compose["services"]["postgres"]
    assert "env_file" not in compose["services"]["iryx-analysis"]

    text = COMPOSE_FILE.read_text(encoding="utf-8")
    for variable in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        assert f"${{{variable}:?" in text, f"{variable} doit être obligatoire"
    assert "POSTGRES_PASSWORD: change" not in text

    analysis_env = compose["services"]["iryx-analysis"].get("environment", {})
    for key in analysis_env:
        assert not any(part in key.upper() for part in ("PASSWORD", "SECRET", "TOKEN"))


def test_build_contexts_point_to_repository_root() -> None:
    """Both images must build from the root lockfile, not backend/uv.lock."""
    compose = load_compose()
    for name in ("iryx-api", "iryx-worker"):
        build = compose["services"][name]["build"]
        assert build["context"] == ".."
        assert build["dockerfile"] in {
            "docker/Dockerfile.api",
            "docker/Dockerfile.worker",
        }


def test_dockerfiles_use_uv_frozen_lock_and_nonroot_identity() -> None:
    """Both images share the same uv/Python 3.12/non-root foundation."""
    for dockerfile in (DOCKERFILE_API, DOCKERFILE_WORKER):
        text = dockerfile.read_text(encoding="utf-8")
        assert "FROM python:3.12-slim" in text
        assert "COPY pyproject.toml uv.lock ./" in text
        assert "uv sync --frozen --no-dev" in text
        assert "groupadd --gid 10001 iryx" in text
        assert "useradd --uid 10001 --gid 10001" in text
        assert "USER iryx:iryx" in text
        assert "/app/backend" in text


def test_api_image_declares_http_healthcheck_and_entrypoint() -> None:
    """The API image itself advertises the thin /health probe."""
    text = DOCKERFILE_API.read_text(encoding="utf-8")
    assert "HEALTHCHECK" in text
    assert "/health" in text
    assert 'ENTRYPOINT ["/usr/local/bin/entrypoint-api.sh"]' in text
    assert "postgresql-client" in text


def test_worker_image_embeds_and_verifies_symbols() -> None:
    """Symbol integrity is checked at build time and the worker runs Celery."""
    text = DOCKERFILE_WORKER.read_text(encoding="utf-8")
    assert EXPECTED_SYMBOLS_SHA256 in text
    assert "sha256sum" in text
    assert 'if [ "$actual" != "$EXPECTED_SYMBOLS_SHA256" ]; then' in text
    assert 'if [ -z "$(find /opt/volatility3/symbols -type f -print -quit)" ]; then' in text
    assert "ERREUR: SHA-256" in text
    assert "backend/docker/symbols/windows.zip" in text
    assert "Aucun téléchargement réseau" in text
    assert "COPY --from=symbols" in text
    assert "/opt/volatility3/symbols" in text
    assert (
        'CMD ["celery", "-A", "iryx.core.celery_app", "worker", '
        '"--loglevel=info", "--pool=threads", "--concurrency=4"]' in text
    )


def test_operator_symbols_archive_is_ignored_by_git() -> None:
    """The target directory is versioned while the provided archive is not."""
    text = SYMBOLS_GITIGNORE.read_text(encoding="utf-8")
    assert "windows.zip" in text


def test_dockerignore_excludes_local_artifacts_and_forensic_data() -> None:
    """Local caches, secrets and evidence must not enter the build context."""
    patterns = [
        ".git/",
        "**/.venv/",
        "**/__pycache__/",
        ".env",
        "**/.env",
        "**/.env.*",
        "/evidence/",
        "/backend/evidence/",
        "_bmad-output/",
        "docs/",
        "mulder_repo/",
        "sources-frontend/",
    ]
    text = DOCKERIGNORE_FILE.read_text(encoding="utf-8")
    for pattern in patterns:
        assert pattern in text, f"{pattern} doit être exclu du contexte"
    negations = [line for line in text.splitlines() if line.startswith("!")]
    assert not any(".env" in line and not line.endswith(".env.example") for line in negations), (
        negations
    )
    assert "backend/src/iryx/evidence/" not in text


def test_entrypoint_waits_migrates_then_execs_uvicorn() -> None:
    """The entrypoint order guarantees no HTTP traffic before migrations."""
    text = ENTRYPOINT_API.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh")
    assert "create_all" not in text

    pg_index = text.index("pg_isready")
    migrate_index = text.index("alembic upgrade head")
    exec_index = text.index("exec uvicorn iryx.main:app --host 0.0.0.0 --port 8000")
    assert pg_index < migrate_index < exec_index
    assert "Timeout : PostgreSQL n'est pas prêt" in text
    assert 'pg_isready -h "$PG_HOST"' in text
    assert 'case "$PG_TIMEOUT" in' in text
    assert "PG_READY_TIMEOUT_SECONDS doit être un entier positif" in text
    assert "if ! alembic upgrade head; then" in text
    assert 'printf \'{"timestamp":"%s"' in text


def test_hardening_applies_to_api_worker_and_analysis() -> None:
    """Every application container drops all capabilities and privileges."""
    services = load_compose()["services"]
    for name in HARDENED_SERVICES:
        service = services[name]
        assert service["cap_drop"] == ["ALL"], f"{name} doit tout supprimer"
        assert service["security_opt"] == ["no-new-privileges:true"], name
        assert service.get("privileged") is not True, name


def test_evidence_raw_is_readonly_and_staging_is_writable() -> None:
    """Sealed storage is immutable while upload staging stays writable."""
    services = load_compose()["services"]
    for name in HARDENED_SERVICES:
        volumes = services[name]["volumes"]
        assert RAW_MOUNT in volumes, f"{name} doit monter le brut en lecture seule"
        assert STAGING_MOUNT in volumes, f"{name} doit monter le staging en écriture"
        assert not any(volume.endswith("/data/evidence/raw") for volume in volumes), (
            f"{name}: le brut ne doit jamais être monté ':rw'"
        )

        environment = services[name]["environment"]
        assert environment["EVIDENCE_STORAGE_PATH"] == "/data/evidence/raw"
        assert environment["EVIDENCE_STAGING_PATH"] == "/data/evidence/staging"

    assert "evidence_data:/data/evidence\n" not in COMPOSE_FILE.read_text(encoding="utf-8")


def test_sealed_evidence_stays_in_writable_staging() -> None:
    """Uploads and sealed files land in staging; raw stays a read-only source."""
    service_text = EVIDENCE_SERVICE.read_text(encoding="utf-8")
    tasks_text = EVIDENCE_TASKS.read_text(encoding="utf-8")
    assert "staging_dir = Path(self.settings.evidence_staging_path)" in service_text
    assert 'staging_file_path = staging_dir / f"{new_evidence_id}.bin"' in service_text
    assert "evidence_storage_path" not in service_text
    assert "allowed_staging_dir = Path(settings.evidence_staging_path).resolve()" in tasks_text
    assert "os.chmod(staging_path, 0o440)" in tasks_text
    assert "evidence_storage_path" not in tasks_text

    services = load_compose()["services"]
    for name in HARDENED_SERVICES:
        volumes = services[name]["volumes"]
        assert RAW_MOUNT in volumes, f"{name}: le brut doit rester ':ro'"
        assert STAGING_MOUNT in volumes, f"{name}: le staging doit rester writable"


def test_forensic_symbols_are_mounted_readonly() -> None:
    """Forensic services read verified symbols from a read-only mount."""
    services = load_compose()["services"]
    for name in ("iryx-worker", "iryx-analysis"):
        assert SYMBOLS_MOUNT in services[name]["volumes"]
        assert (
            services[name]["environment"]["VOLATILITY_SYMBOLS_PATH"] == "/opt/volatility3/symbols"
        )


def test_analysis_service_reuses_worker_image_without_network() -> None:
    """The profiled service is a one-shot air-gapped worker image instance."""
    services = load_compose()["services"]
    analysis = services["iryx-analysis"]
    assert analysis["network_mode"] == "none"
    assert "ports" not in analysis
    assert "networks" not in analysis
    assert "env_file" not in analysis
    assert analysis["build"] == services["iryx-worker"]["build"]
    assert analysis["image"] == services["iryx-worker"]["image"]
    assert "entrypoint" not in analysis
    assert analysis["command"] == [
        "python",
        "/app/backend/docker/check_airgap.py",
    ]


def test_airgap_probe_succeeds_only_on_network_unreachable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A blocked external TCP connection is the expected air-gap outcome."""

    def blocked(address: tuple[str, int], timeout: float) -> Any:
        assert address == ("1.1.1.1", 443)
        assert timeout == 3
        raise OSError(errno.ENETUNREACH, "Réseau inaccessible")

    module = load_check_airgap()
    monkeypatch.setattr(module.socket, "create_connection", blocked)
    assert module.main() == 0
    output = capsys.readouterr()
    assert "OK" in output.out
    assert f"errno {errno.ENETUNREACH}" in output.out
    assert "Réseau inaccessible" in output.out


def test_airgap_probe_rejects_successful_connection(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A reachable network is a failure, never a reason to try another host."""
    module = load_check_airgap()

    class FakeSocket:
        closed = False

        def close(self) -> None:
            self.closed = True

    connection = FakeSocket()
    monkeypatch.setattr(module.socket, "create_connection", lambda *_: connection)
    assert module.main() == 1
    assert "n'est pas effective" in capsys.readouterr().err
    assert connection.closed


def test_airgap_probe_rejects_unexpected_network_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only ENETUNREACH proves isolation; any other error must be explicit."""

    def refused(address: tuple[str, int], timeout: float) -> Any:
        raise OSError(errno.ECONNREFUSED, "Connection refused")

    module = load_check_airgap()
    monkeypatch.setattr(module.socket, "create_connection", refused)
    assert module.main() == 1
    error = capsys.readouterr().err
    assert "Connection refused" in error
    assert f"errno {errno.ENETUNREACH}" in error


def test_env_example_documents_compose_variables() -> None:
    """The template exposes required PostgreSQL variables and internal hosts."""
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for fragment in (
        "POSTGRES_USER=",
        "POSTGRES_PASSWORD=",
        "POSTGRES_DB=",
        "POSTGRES_HOST=postgres",
        "POSTGRES_PORT=5432",
        "PG_READY_TIMEOUT_SECONDS=60",
        "@postgres:5432/",
        "redis://redis:6379/0",
        "/opt/volatility3/symbols",
        "/data/evidence/raw",
        "/data/evidence/staging",
        "docker compose --profile analysis run --rm iryx-analysis",
    ):
        assert fragment in text, f"{fragment} manque dans .env.example"


def test_readme_documents_compose_startup_and_symbols() -> None:
    """Operators can start the platform and satisfy the symbols prerequisite."""
    text = README.read_text(encoding="utf-8")
    for fragment in (
        "docker compose up -d --build",
        "docker compose config --quiet",
        "docker compose ps",
        "windows.zip",
        EXPECTED_SYMBOLS_SHA256,
        "curl -fsS --max-time 5 http://localhost:8000/health",
        "docker compose exec iryx-api alembic current",
        "uid=10001(iryx) gid=10001(iryx)",
        "/data/evidence/raw",
        "/data/evidence/staging",
        "docker compose --profile analysis run --rm iryx-analysis",
        "docker compose --profile analysis build iryx-analysis",
        "docker compose --profile analysis create iryx-analysis",
        "docker compose --profile analysis run --rm iryx-analysis <commande-d'analyse>",
        "cp -a /data/evidence/raw/staging/. /data/evidence/staging/",
        "errno `ENETUNREACH`",
        "Network is unreachable",
        'CapDrop: ["ALL"]',
        'SecurityOpt: ["no-new-privileges:true"]',
    ):
        assert fragment in text, f"{fragment} manque dans le README"
