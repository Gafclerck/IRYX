"""Static verification of the Docker deployment configuration (Story 9.1)."""

from pathlib import Path
from typing import Any

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
SYMBOLS_GITIGNORE = DOCKER_DIR / "symbols" / ".gitignore"

EXPECTED_SERVICES = {"postgres", "redis", "iryx-api", "iryx-worker"}
EXPECTED_SYMBOLS_SHA256 = "c7e49e8a520bfd68cfa1907cbcf9581c15f9e761dfb61b369527ec50c76251b3"


def load_compose() -> dict[str, Any]:
    """Load the Compose file without requiring a Docker daemon."""
    with COMPOSE_FILE.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    assert isinstance(config, dict)
    return config


def test_compose_defines_exactly_four_services() -> None:
    """The mono-server topology must expose exactly the four D-22 services."""
    compose = load_compose()
    assert set(compose["services"]) == EXPECTED_SERVICES


def test_every_service_has_a_healthcheck() -> None:
    """Each probe must target the real dependency, endpoint or process."""
    compose = load_compose()
    services = compose["services"]
    for name, service in services.items():
        healthcheck = service.get("healthcheck")
        assert isinstance(healthcheck, dict), f"{name} a besoin d'un healthcheck"
        assert healthcheck.get("test"), f"{name} a besoin d'une sonde"

    probes = {name: service["healthcheck"]["test"] for name, service in services.items()}
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
    compose = load_compose()
    services = compose["services"]

    api_deps = services["iryx-api"]["depends_on"]
    assert api_deps["postgres"] == {"condition": "service_healthy"}
    assert api_deps["redis"] == {"condition": "service_healthy"}

    worker_deps = services["iryx-worker"]["depends_on"]
    for dependency in ("postgres", "redis", "iryx-api"):
        assert worker_deps[dependency] == {"condition": "service_healthy"}


def test_only_api_publishes_port_8000() -> None:
    """No database or broker port may be published on the host."""
    compose = load_compose()
    published: list[str] = []
    for service in compose["services"].values():
        published.extend(service.get("ports", []))
    assert published == ["8000:8000"]


def test_no_hardcoded_secret_or_host_path_in_compose() -> None:
    """Secrets come from .env and volumes are named, never host-bound."""
    compose = load_compose()
    for name, service in compose["services"].items():
        if "env_file" in service:
            assert service["env_file"] == ".env", f"{name} doit lire backend/.env"
    # PostgreSQL ne reçoit que ses trois variables : aucun secret applicatif superflu.
    assert "env_file" not in compose["services"]["postgres"]
    for service in compose["services"].values():
        for volume in service.get("volumes", []):
            source = volume.split(":")[0]
            assert not source.startswith((".", "/", "~", "C:")), volume

    text = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD" in text
    assert "POSTGRES_PASSWORD: change" not in text


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
    assert "if [ -z \"$(find /opt/volatility3/symbols -type f -print -quit)\" ]; then" in text
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
    assert not any(
        ".env" in line and not line.endswith(".env.example") for line in negations
    ), negations
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
    ):
        assert fragment in text, f"{fragment} manque dans le README"
