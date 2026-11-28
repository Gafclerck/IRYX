"""End-to-end acceptance test and MVP demonstration script for IRYX (Story 9.4).

Validates the full 12-step investigation lifecycle over the REST API without
bypassing authentication, RBAC, SHA-256 sealing, human gates (H1/H2/H3),
deterministic verification, UTC timeline projection, Presidio pseudonymization,
sealed Markdown/JSON reporting, or the append-only audit trail (Invariant 3).

Usage::

    # Against an active Docker Compose / backend stack (default)
    uv run python -m iryx.scripts.test_e2e_investigation_flow

    # Offline / CI demonstration mode with isolated SQLite DB and local stubs
    uv run python -m iryx.scripts.test_e2e_investigation_flow --mode local-demo
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import re
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, TextIO
from unittest.mock import patch

SUCCESS_BANNER = "DÉMONSTRATION ET VALIDATION COMPLÈTE DU MVP IRYX RÉUSSIE"
CASE_TITLE = "Attaque Ransomware Serveur AD"
AUDIT_LOG_ERROR_MESSAGE = "CANNOT_MODIFY_AUDIT_LOG"

DEMO_EVIDENCE_FILENAME = "e2e_triage.csv"
DEMO_EVIDENCE_CONTENT = (
    b"timestamp,host,user,ip,action,details\n"
    b"2026-11-24T02:14:25Z,SRV-AD01,svc_backup,10.42.17.88,powershell_encoded,"
    b"EncodedCommand execution observed\n"
    b"2026-11-24T02:15:10Z,SRV-AD01,adm_backup,10.42.17.88,smb_lateral_move,"
    b"Lateral movement toward DC01\n"
)
SENSITIVE_DEMO_MARKERS: tuple[str, ...] = (
    "10.42.17.88",
    "svc_backup",
    "adm_backup",
    "SRV-AD01",
)

CANONICAL_SECTION_KEYS: tuple[str, ...] = (
    "resume_managerial",
    "perimetre",
    "methodologie",
    "chaine_des_preuves",
    "observations",
    "constats_valides",
    "chronologie",
    "limites",
)

EXPECTED_SEEDED_EVIDENCES: frozenset[str] = frozenset(
    {
        "Security.evtx",
        "POWERSHELL.EXE-DEMO1234.pf",
        "MEMORY.DMP",
    }
)

EXPECTED_GATEWAY_TOOLS: frozenset[str] = frozenset(
    {
        "parse_text_logs",
        "parse_evtx",
        "parse_execution",
    }
)

EXPECTED_CASE_AUDIT_ACTIONS: frozenset[str] = frozenset(
    {
        "CASE_READ",
        "EVIDENCE_UPLOAD",
        "GATE_H1_DECISION",
        "FINDING_REVIEW",
        "GATE_H2_DECISION",
        "GATE_H3_DECISION",
        "REPORT_GENERATE",
    }
)

FORBIDDEN_AUDIT_DETAIL_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "hashed_password",
        "token",
        "access_token",
        "jwt",
        "secret",
        "secret_key",
        "api_key",
    }
)

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class DemoCredential:
    """Credential tuple matching ``iryx.scripts.seed_data.DEMO_USERS``."""

    email: str
    password: str
    role: str


DEFAULT_DEMO_CREDENTIALS: dict[str, DemoCredential] = {
    "admin": DemoCredential("admin@iryx.local", "Admin12345!", "admin"),
    "analyst": DemoCredential("analyst@iryx.local", "Analyst12345!", "analyst"),
    "investigator": DemoCredential("investigator@iryx.local", "Investigator12345!", "investigator"),
    "viewer": DemoCredential("auditor@iryx.local", "Auditor12345!", "viewer"),
}


class E2EStepError(RuntimeError):
    """Fail-fast error identifying the exact failing step and deviation."""

    def __init__(
        self,
        step_number: int,
        step_name: str,
        message: str,
        *,
        hint: str | None = None,
    ) -> None:
        self.step_number = step_number
        self.step_name = step_name
        self.message = message
        self.hint = hint
        full_msg = f"[Étape {step_number}/12 - {step_name}] {message}"
        if hint:
            full_msg = f"{full_msg} ({hint})"
        super().__init__(full_msg)


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Normalized HTTP response returned by any ``HttpTransport``."""

    status_code: int
    headers: dict[str, str]
    body: bytes

    def get_header(self, name: str) -> str | None:
        """Return a header value using case-insensitive lookup."""
        target = name.lower()
        for key, value in self.headers.items():
            if key.lower() == target:
                return value
        return None

    @property
    def text(self) -> str:
        """Decode body as UTF-8 text."""
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        """Deserialize response body as JSON."""
        return json.loads(self.body.decode("utf-8"))


class HttpTransport(Protocol):
    """Minimal synchronous HTTP transport abstraction."""

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: Any | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
        """Execute an HTTP request and return a normalized ``HttpResponse``."""


class UrllibHttpTransport:
    """Pure Python stdlib HTTP transport requiring zero dev dependencies."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.base_url}{path}"

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: Any | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
        if json_body is not None and files is not None:
            raise ValueError("json_body and files are mutually exclusive.")

        req_headers = dict(headers or {})
        data: bytes | None = None

        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
        elif files is not None:
            boundary = f"----IryxE2EBoundary{uuid.uuid4().hex}"
            parts: list[bytes] = []
            for field_name, (filename, content, content_type) in files.items():
                parts.extend(
                    [
                        f"--{boundary}\r\n".encode("ascii"),
                        (
                            f'Content-Disposition: form-data; name="{field_name}"; '
                            f'filename="{filename}"\r\n'
                        ).encode(),
                        f"Content-Type: {content_type}\r\n\r\n".encode("ascii"),
                        content,
                        b"\r\n",
                    ]
                )
            parts.append(f"--{boundary}--\r\n".encode("ascii"))
            data = b"".join(parts)
            req_headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"

        req = urllib.request.Request(
            url=self._build_url(path),
            data=data,
            headers=req_headers,
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                return HttpResponse(
                    status_code=int(resp.status),
                    headers=resp_headers,
                    body=resp.read(),
                )
        except urllib.error.HTTPError as exc:
            resp_headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
            body = exc.read() if hasattr(exc, "read") else b""
            return HttpResponse(
                status_code=int(exc.code),
                headers=resp_headers,
                body=body,
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ConnectionError(f"Erreur réseau HTTP vers {req.full_url} : {exc}") from exc


class TestClientHttpTransport:
    """Adapter wrapping a Starlette/FastAPI ``TestClient`` into ``HttpTransport``."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: Any | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
        kwargs: dict[str, Any] = {}
        if headers is not None:
            kwargs["headers"] = headers
        if json_body is not None:
            kwargs["json"] = json_body
        if files is not None:
            kwargs["files"] = files
        resp = self._client.request(method.upper(), path, **kwargs)
        return HttpResponse(
            status_code=int(resp.status_code),
            headers={k.lower(): v for k, v in resp.headers.items()},
            body=resp.content,
        )


@dataclass(frozen=True, slots=True)
class E2ERunnerConfig:
    """Runtime configuration for the E2E smoke test runner."""

    mode: Literal["stack", "local-demo"] = "stack"
    base_url: str = "http://127.0.0.1:8000"
    db_url: str | None = None
    skip_db_audit_check: bool = False
    timeout: float = 60.0
    poll_interval: float = 3.0


@dataclass(frozen=True, slots=True)
class E2ERunSummary:
    """Structured summary produced upon successful completion of all 12 steps."""

    case_id: str
    run_id: str
    uploaded_evidence_id: str
    uploaded_sha256: str
    report_ids: dict[str, str] = field(default_factory=dict)
    report_hashes: dict[str, str] = field(default_factory=dict)
    audit_event_count: int = 0
    steps_completed: int = 12


def _parse_iso_utc(raw_ts: str) -> datetime:
    cleaned = raw_ts.strip()
    if cleaned.endswith("Z"):
        cleaned = f"{cleaned[:-1]}+00:00"
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        raise ValueError(f"Horodatage sans fuseau horaire UTC : {raw_ts!r}")
    offset = dt.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError(f"Horodatage non UTC ({offset}) : {raw_ts!r}")
    return dt.astimezone(UTC)


def _parse_iso_any(raw_ts: str) -> datetime:
    cleaned = raw_ts.strip()
    if cleaned.endswith("Z"):
        cleaned = f"{cleaned[:-1]}+00:00"
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _check_dict_has_no_secret_keys(
    data: Any,
    *,
    forbidden_values: tuple[str, ...] = (),
) -> str | None:
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in FORBIDDEN_AUDIT_DETAIL_KEYS:
                return f"clé '{key}'"
            nested = _check_dict_has_no_secret_keys(value, forbidden_values=forbidden_values)
            if nested is not None:
                return nested
    elif isinstance(data, list):
        for item in data:
            nested = _check_dict_has_no_secret_keys(item, forbidden_values=forbidden_values)
            if nested is not None:
                return nested
    elif isinstance(data, str):
        for marker in forbidden_values:
            if marker and marker in data:
                return "valeur sensible dans details"
    return None


def verify_sql_audit_append_only(
    *,
    case_id: str,
    db_url: str | None = None,
    engine: Any | None = None,
) -> None:
    """Verify Invariant 3 directly against SQL ``audit_events`` triggers."""
    from sqlalchemy import create_engine, delete, select, update
    from sqlalchemy.exc import DBAPIError

    from iryx.audit.models import AuditEvent
    from iryx.db.session import sanitize_error_message

    created_engine = False
    target_engine = engine
    if target_engine is None:
        resolved_url = db_url
        if not resolved_url:
            from iryx.core.config import get_settings

            resolved_url = get_settings().database_url
        target_engine = create_engine(resolved_url, pool_pre_ping=True)
        created_engine = True

    try:
        try:
            case_uuid = uuid.UUID(case_id)
            with target_engine.connect() as conn:
                row_id = conn.execute(
                    select(AuditEvent.id).where(AuditEvent.case_id == case_uuid).limit(1)
                ).scalar()
                if row_id is None:
                    raise E2EStepError(
                        12,
                        "Journal d'audit & Invariant 3",
                        "Aucun événement d'audit trouvé en base pour tester l'Invariant 3 SQL.",
                    )
                if conn.in_transaction():
                    conn.rollback()

                for op_name, stmt in (
                    (
                        "UPDATE",
                        update(AuditEvent).where(AuditEvent.id == row_id).values(action="TAMPERED"),
                    ),
                    (
                        "DELETE",
                        delete(AuditEvent).where(AuditEvent.id == row_id),
                    ),
                ):
                    tx = conn.begin()
                    try:
                        conn.execute(stmt)
                    except DBAPIError as exc:
                        tx.rollback()
                        if AUDIT_LOG_ERROR_MESSAGE not in str(exc):
                            raise E2EStepError(
                                12,
                                "Journal d'audit & Invariant 3",
                                f"Rejet SQL inattendu lors du {op_name} sur audit_events : "
                                f"{type(exc).__name__}",
                            ) from exc
                    else:
                        tx.rollback()
                        raise E2EStepError(
                            12,
                            "Journal d'audit & Invariant 3",
                            f"Violation Invariant 3 : l'opération SQL {op_name} sur audit_events "
                            "n'a pas été bloquée par le trigger.",
                        )
        except E2EStepError:
            raise
        except Exception as exc:
            sanitized = sanitize_error_message(f"{type(exc).__name__}: {exc}")
            raise E2EStepError(
                12,
                "Journal d'audit & Invariant 3",
                f"Impossible de vérifier l'Invariant 3 directement sur PostgreSQL : {sanitized}",
                hint=(
                    "Exécutez le script dans le conteneur API (`docker compose exec iryx-api "
                    "python -m iryx.scripts.test_e2e_investigation_flow`), passez `--db-url`, "
                    "ou utilisez `--skip-db-audit-check` si PostgreSQL n'est pas exposé."
                ),
            ) from exc
    finally:
        if created_engine:
            target_engine.dispose()


class InvestigationE2ERunner:
    """Sequential fail-fast 12-step E2E acceptance runner."""

    def __init__(
        self,
        transport: HttpTransport,
        config: E2ERunnerConfig,
        *,
        sql_audit_checker: Callable[[str], None] | None = None,
        credentials: dict[str, DemoCredential] | None = None,
        output: TextIO | None = None,
    ) -> None:
        self.transport = transport
        self.config = config
        self.sql_audit_checker = sql_audit_checker
        self.credentials = credentials or DEFAULT_DEMO_CREDENTIALS
        self.output = output or sys.stdout

    def _log_step(self, step_num: int, step_name: str, detail: str) -> None:
        print(f"[{step_num}/12] {step_name} : {detail}", file=self.output, flush=True)

    def _request(
        self,
        step_num: int,
        step_name: str,
        method: str,
        path: str,
        *,
        token: str | None = None,
        expected_status: int | tuple[int, ...] = 200,
        json_body: Any | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        llm_step: bool = False,
    ) -> HttpResponse:
        headers: dict[str, str] = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"

        try:
            resp = self.transport.request(
                method,
                path,
                headers=headers or None,
                json_body=json_body,
                files=files,
                timeout=self.config.timeout,
            )
        except Exception as exc:
            raise E2EStepError(
                step_num,
                step_name,
                f"Échec de requête {method.upper()} {path} : {exc}",
            ) from exc

        expected = (expected_status,) if isinstance(expected_status, int) else expected_status
        if resp.status_code not in expected:
            hint: str | None = None
            if llm_step and resp.status_code == 503 and self.config.mode == "stack":
                hint = (
                    "Aucun fournisseur LLM compatible OpenAI joignable (HTTP 503). "
                    "Vérifiez OPENAI_API_BASE / OPENAI_API_KEY / *_MODEL dans backend/.env "
                    "ou exécutez avec `--mode local-demo`."
                )
            elif resp.status_code == 409 and "/investigations" in path:
                hint = (
                    "Une session d'investigation est déjà active ('running' ou 'paused') sur ce "
                    "dossier. Terminez-la ou réinitialisez la base avant de relancer le test."
                )
            snippet = resp.text[:300].strip()
            raise E2EStepError(
                step_num,
                step_name,
                f"{method.upper()} {path} a retourné HTTP {resp.status_code} "
                f"(attendu {expected}) : {snippet}",
                hint=hint,
            )
        return resp

    @staticmethod
    def _parse_json(
        step_num: int,
        step_name: str,
        resp: HttpResponse,
        *,
        expected_type: type[Any] | tuple[type[Any], ...] = dict,
    ) -> Any:
        try:
            data = resp.json()
        except Exception as exc:
            raise E2EStepError(
                step_num,
                step_name,
                f"Réponse JSON invalide (HTTP {resp.status_code}) : {exc}",
            ) from exc
        if not isinstance(data, expected_type):
            raise E2EStepError(
                step_num,
                step_name,
                f"Type JSON inattendu (HTTP {resp.status_code}) : {type(data).__name__}.",
            )
        return data

    def _paginate_items(
        self,
        step_num: int,
        step_name: str,
        base_path: str,
        *,
        token: str,
    ) -> tuple[list[dict[str, Any]], int]:
        items: list[dict[str, Any]] = []
        offset = 0
        total = 0
        sep = "&" if "?" in base_path else "?"
        while True:
            page = self._parse_json(
                step_num,
                step_name,
                self._request(
                    step_num,
                    step_name,
                    "GET",
                    f"{base_path}{sep}limit=100&offset={offset}",
                    token=token,
                    expected_status=200,
                ),
            )
            batch = page.get("items") or []
            total = int(page.get("total") if page.get("total") is not None else len(batch))
            items.extend(batch)
            if not page.get("has_more") or not batch:
                break
            offset += len(batch)
        return items, total

    @staticmethod
    def _validate_retry_after(
        step_num: int,
        step_name: str,
        resp: HttpResponse,
        context_label: str,
    ) -> int:
        raw_header = resp.get_header("Retry-After")
        if raw_header is None:
            raise E2EStepError(
                step_num,
                step_name,
                f"En-tête Retry-After manquant ({context_label}).",
            )
        try:
            retry_seconds = int(str(raw_header).strip())
        except ValueError as exc:
            raise E2EStepError(
                step_num,
                step_name,
                f"En-tête Retry-After invalide ({context_label}) : {raw_header!r}.",
            ) from exc
        if retry_seconds < 1:
            raise E2EStepError(
                step_num,
                step_name,
                f"En-tête Retry-After doit être >= 1 ({context_label}) : {retry_seconds}.",
            )
        return retry_seconds

    def run(self) -> E2ERunSummary:
        """Execute all 12 E2E steps sequentially, failing fast on the first deviation."""
        tokens = self._step_1_health_and_auth()
        case_id = self._step_2_case_access_and_rbac(tokens)
        uploaded_id, uploaded_sha = self._step_3_upload_and_poll_evidence(
            tokens["analyst"], case_id
        )
        run_id, run_started_at = self._step_4_start_investigation_and_planner(
            tokens["investigator"], case_id
        )
        self._step_5_gate_h1_and_resume(tokens["analyst"], case_id, run_id)
        self._step_6_gateway_tools_and_observations(
            tokens["analyst"],
            case_id,
            run_started_at=run_started_at,
            uploaded_evidence_id=uploaded_id,
        )
        self._step_7_findings_and_verifier(tokens["analyst"], case_id)
        self._step_8_review_findings_and_gate_h2(
            tokens["analyst"],
            tokens["investigator"],
            case_id,
            run_id,
        )
        self._step_9_timeline_and_correlations(tokens["analyst"], case_id)
        self._step_10_presidio_preview(tokens["investigator"], case_id, run_id)
        report_ids, report_hashes = self._step_11_gate_h3_and_sealed_reports(
            tokens["investigator"],
            case_id,
            run_id,
        )
        audit_count = self._step_12_audit_trail_and_invariant_3(tokens["admin"], case_id)

        return E2ERunSummary(
            case_id=case_id,
            run_id=run_id,
            uploaded_evidence_id=uploaded_id,
            uploaded_sha256=uploaded_sha,
            report_ids=report_ids,
            report_hashes=report_hashes,
            audit_event_count=audit_count,
            steps_completed=12,
        )

    def _step_1_health_and_auth(self) -> dict[str, str]:
        step_num, step_name = 1, "Santé API & Authentification JWT"
        health = self._parse_json(
            step_num,
            step_name,
            self._request(step_num, step_name, "GET", "/health", expected_status=200),
        )
        if health.get("status") != "ok":
            raise E2EStepError(
                step_num,
                step_name,
                f"Statut /health inattendu : {health!r}",
            )

        # Unauthenticated protected access must fail with 401
        self._request(step_num, step_name, "GET", "/api/v1/auth/me", expected_status=401)
        # Invalid credentials must fail with 401
        self._request(
            step_num,
            step_name,
            "POST",
            "/api/v1/auth/login",
            expected_status=401,
            json_body={
                "email": self.credentials["admin"].email,
                "password": "WrongPassword999!",
            },
        )

        tokens: dict[str, str] = {}
        for role_key, cred in self.credentials.items():
            resp = self._request(
                step_num,
                step_name,
                "POST",
                "/api/v1/auth/login",
                expected_status=200,
                json_body={"email": cred.email, "password": cred.password},
            )
            payload = self._parse_json(step_num, step_name, resp)
            access_token = payload.get("access_token")
            if payload.get("token_type") != "bearer" or not access_token:
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Jeton JWT invalide retourné pour {cred.email}.",
                )
            tokens[role_key] = str(access_token)

        me = self._parse_json(
            step_num,
            step_name,
            self._request(
                step_num,
                step_name,
                "GET",
                "/api/v1/auth/me",
                token=tokens["analyst"],
                expected_status=200,
            ),
        )
        if me.get("email") != self.credentials["analyst"].email:
            raise E2EStepError(
                step_num,
                step_name,
                f"/api/v1/auth/me incohérent : {me.get('email')!r}",
            )
        self._log_step(step_num, step_name, "OK (4 comptes authentifiés, 401 vérifiés)")
        return tokens

    def _step_2_case_access_and_rbac(self, tokens: dict[str, str]) -> str:
        step_num, step_name = 2, "Contrôle d'accès dossier & RBAC"
        case_id: str | None = None
        offset = 0
        while True:
            page = self._parse_json(
                step_num,
                step_name,
                self._request(
                    step_num,
                    step_name,
                    "GET",
                    f"/api/v1/cases?limit=100&offset={offset}",
                    token=tokens["analyst"],
                    expected_status=200,
                ),
            )
            items = page.get("items") or []
            for item in items:
                if item.get("title") == CASE_TITLE:
                    case_id = str(item["id"])
                    break
            if case_id is not None or not page.get("has_more"):
                break
            offset += len(items)
            if not items:
                break

        if case_id is None:
            raise E2EStepError(
                step_num,
                step_name,
                f"Dossier de démonstration '{CASE_TITLE}' introuvable.",
                hint="Exécutez d'abord `python -m iryx.scripts.seed_data`.",
            )

        case_detail = self._parse_json(
            step_num,
            step_name,
            self._request(
                step_num,
                step_name,
                "GET",
                f"/api/v1/cases/{case_id}",
                token=tokens["analyst"],
                expected_status=200,
            ),
        )
        if case_detail.get("status") != "open":
            raise E2EStepError(
                step_num,
                step_name,
                f"Le dossier '{CASE_TITLE}' doit être 'open', reçu {case_detail.get('status')!r}.",
            )

        evidence_items, _ = self._paginate_items(
            step_num,
            step_name,
            f"/api/v1/cases/{case_id}/evidences",
            token=tokens["analyst"],
        )
        seeded_by_name = {item.get("original_name"): item for item in evidence_items}
        missing_seeded = sorted(EXPECTED_SEEDED_EVIDENCES - set(seeded_by_name))
        if missing_seeded:
            raise E2EStepError(
                step_num,
                step_name,
                f"Preuves de démonstration manquantes dans le dossier : {missing_seeded}",
            )
        for name in EXPECTED_SEEDED_EVIDENCES:
            sha = str(seeded_by_name[name].get("sha256") or "")
            if not _HEX64_RE.match(sha):
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Preuve seedée '{name}' non scellée (sha256={sha!r}).",
                )

        # RBAC verification: viewer cannot start investigation or read audit trail;
        # analyst cannot read audit trail (restricted to admin & investigator).
        self._request(
            step_num,
            step_name,
            "POST",
            f"/api/v1/cases/{case_id}/investigations",
            token=tokens["viewer"],
            expected_status=403,
        )
        self._request(
            step_num,
            step_name,
            "GET",
            f"/api/v1/cases/{case_id}/audit-trail",
            token=tokens["viewer"],
            expected_status=403,
        )
        self._request(
            step_num,
            step_name,
            "GET",
            f"/api/v1/cases/{case_id}/audit-trail",
            token=tokens["analyst"],
            expected_status=403,
        )

        self._log_step(
            step_num,
            step_name,
            f"OK (dossier {case_id}, 3 preuves seedées scellées, 403 RBAC vérifiés)",
        )
        return case_id

    def _step_3_upload_and_poll_evidence(
        self,
        analyst_token: str,
        case_id: str,
    ) -> tuple[str, str]:
        step_num, step_name = 3, "Téléversement preuve & polling SHA-256"
        expected_sha256 = hashlib.sha256(DEMO_EVIDENCE_CONTENT).hexdigest()

        upload_resp = self._request(
            step_num,
            step_name,
            "POST",
            f"/api/v1/cases/{case_id}/evidences",
            token=analyst_token,
            expected_status=202,
            files={"file": (DEMO_EVIDENCE_FILENAME, DEMO_EVIDENCE_CONTENT, "text/csv")},
        )
        location = upload_resp.get_header("Location")
        if not location:
            raise E2EStepError(
                step_num,
                step_name,
                "En-tête Location manquant dans la réponse HTTP 202.",
            )
        self._validate_retry_after(step_num, step_name, upload_resp, "réponse HTTP 202")

        upload_data = self._parse_json(step_num, step_name, upload_resp)
        evidence_id = str(upload_data.get("evidence_id") or "")
        if not evidence_id:
            raise E2EStepError(step_num, step_name, "evidence_id absent de la réponse 202.")

        deadline = time.monotonic() + self.config.timeout
        status_data: dict[str, Any] | None = None
        last_status: str | None = None
        last_progress: Any = None
        while True:
            if time.monotonic() >= deadline:
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Timeout ({self.config.timeout}s) lors du polling d'ingestion "
                    f"(dernier statut={last_status!r}, progress={last_progress}).",
                )
            poll_resp = self._request(
                step_num,
                step_name,
                "GET",
                location,
                token=analyst_token,
                expected_status=200,
            )
            status_data = self._parse_json(step_num, step_name, poll_resp)
            ing_status = status_data.get("status")
            last_status = str(ing_status) if ing_status is not None else None
            last_progress = status_data.get("progress")
            if ing_status == "completed":
                break
            if ing_status == "failed":
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"L'ingestion de la preuve {evidence_id} a échoué : "
                    f"{status_data.get('error_message')}",
                )
            if ing_status not in ("pending", "processing"):
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Statut d'ingestion inconnu : {ing_status!r}",
                )
            self._validate_retry_after(
                step_num,
                step_name,
                poll_resp,
                f"polling {ing_status}",
            )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Timeout ({self.config.timeout}s) lors du polling d'ingestion "
                    f"(dernier statut={ing_status!r}, progress={last_progress}).",
                )
            sleep_seconds = min(max(self.config.poll_interval, 0.01), remaining)
            time.sleep(sleep_seconds)
            if time.monotonic() >= deadline:
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Timeout ({self.config.timeout}s) lors du polling d'ingestion "
                    f"(dernier statut={ing_status!r}, progress={last_progress}).",
                )

        if status_data.get("progress") != 100:
            raise E2EStepError(
                step_num,
                step_name,
                f"Progression finale attendue à 100, reçu {status_data.get('progress')!r}.",
            )
        remote_sha256 = str(status_data.get("sha256") or "")
        if remote_sha256 != expected_sha256:
            raise E2EStepError(
                step_num,
                step_name,
                f"Discordance SHA-256 : attendu {expected_sha256}, reçu {remote_sha256!r}.",
            )
        if not status_data.get("detected_type"):
            raise E2EStepError(step_num, step_name, "detected_type absent après scellement.")

        evidence_meta = self._parse_json(
            step_num,
            step_name,
            self._request(
                step_num,
                step_name,
                "GET",
                f"/api/v1/cases/{case_id}/evidences/{evidence_id}",
                token=analyst_token,
                expected_status=200,
            ),
        )
        if evidence_meta.get("sha256") != expected_sha256:
            raise E2EStepError(
                step_num,
                step_name,
                "Métadonnées GET /evidences/{id} incohérentes avec le SHA-256 local.",
            )

        self._log_step(
            step_num,
            step_name,
            f"OK (evidence {evidence_id}, SHA-256 {expected_sha256[:12]}...)",
        )
        return evidence_id, expected_sha256

    def _step_4_start_investigation_and_planner(
        self,
        investigator_token: str,
        case_id: str,
    ) -> tuple[str, datetime]:
        step_num, step_name = 4, "Initialisation session & Planification (Planner)"
        created = self._parse_json(
            step_num,
            step_name,
            self._request(
                step_num,
                step_name,
                "POST",
                f"/api/v1/cases/{case_id}/investigations",
                token=investigator_token,
                expected_status=201,
            ),
        )
        run_id = str(created.get("id") or "")
        raw_started_at = created.get("started_at")
        if (
            not run_id
            or not raw_started_at
            or created.get("status") != "running"
            or created.get("current_phase") != "triage"
        ):
            raise E2EStepError(
                step_num,
                step_name,
                f"État initial d'investigation invalide : {created!r}",
            )
        try:
            run_started_at = _parse_iso_any(str(raw_started_at))
        except ValueError as exc:
            raise E2EStepError(
                step_num,
                step_name,
                f"Horodatage started_at invalide : {raw_started_at!r}",
            ) from exc

        resumed = self._parse_json(
            step_num,
            step_name,
            self._request(
                step_num,
                step_name,
                "POST",
                f"/api/v1/cases/{case_id}/investigations/{run_id}/resume",
                token=investigator_token,
                expected_status=200,
                llm_step=True,
            ),
        )
        if resumed.get("status") != "paused" or resumed.get("current_phase") not in (
            "waiting_h1",
            "gate_h1",
        ):
            raise E2EStepError(
                step_num,
                step_name,
                f"Phase/statut attendu (paused, waiting_h1), reçu "
                f"({resumed.get('status')!r}, {resumed.get('current_phase')!r}).",
            )

        plan = self._parse_json(
            step_num,
            step_name,
            self._request(
                step_num,
                step_name,
                "GET",
                f"/api/v1/cases/{case_id}/investigations/{run_id}/plan",
                token=investigator_token,
                expected_status=200,
            ),
        )
        steps = plan.get("steps") or []
        if not (1 <= len(steps) <= 10):
            raise E2EStepError(
                step_num,
                step_name,
                f"Nombre d'étapes du plan hors bornes [1..10] : {len(steps)}.",
            )

        self._log_step(step_num, step_name, f"OK (run {run_id}, plan à {len(steps)} étape(s))")
        return run_id, run_started_at

    def _step_5_gate_h1_and_resume(
        self,
        analyst_token: str,
        case_id: str,
        run_id: str,
    ) -> None:
        step_num, step_name = 5, "Validation Porte H1 & Reprise exécution"
        h1_resp = self._parse_json(
            step_num,
            step_name,
            self._request(
                step_num,
                step_name,
                "POST",
                f"/api/v1/cases/{case_id}/investigations/{run_id}/gates/h1",
                token=analyst_token,
                expected_status=200,
                json_body={
                    "decision": "approve",
                    "feedback": "Plan approuvé lors du smoke test E2E",
                },
            ),
        )
        if h1_resp.get("status") != "running" or h1_resp.get("current_phase") != "executor":
            raise E2EStepError(
                step_num,
                step_name,
                f"État post-H1 attendu (running, executor), reçu "
                f"({h1_resp.get('status')!r}, {h1_resp.get('current_phase')!r}).",
            )

        resumed = self._parse_json(
            step_num,
            step_name,
            self._request(
                step_num,
                step_name,
                "POST",
                f"/api/v1/cases/{case_id}/investigations/{run_id}/resume",
                token=analyst_token,
                expected_status=200,
                llm_step=True,
            ),
        )
        if resumed.get("status") != "paused" or resumed.get("current_phase") not in (
            "waiting_h2",
            "gate_h2",
        ):
            raise E2EStepError(
                step_num,
                step_name,
                f"État attendu en sortie d'analyse/vérification (paused, waiting_h2), reçu "
                f"({resumed.get('status')!r}, {resumed.get('current_phase')!r}).",
            )

        self._log_step(step_num, step_name, "OK (H1 approuvée -> pause à waiting_h2)")

    def _step_6_gateway_tools_and_observations(
        self,
        analyst_token: str,
        case_id: str,
        *,
        run_started_at: datetime,
        uploaded_evidence_id: str,
    ) -> None:
        step_num, step_name = 6, "Exécutions Gateway & Observations normalisées"
        tools = self._parse_json(
            step_num,
            step_name,
            self._request(
                step_num,
                step_name,
                "GET",
                "/api/v1/gateway/tools",
                token=analyst_token,
                expected_status=200,
            ),
            expected_type=list,
        )
        tool_names = {item.get("name") for item in tools if isinstance(item, dict)}
        missing_tools = sorted(EXPECTED_GATEWAY_TOOLS - tool_names)
        if missing_tools:
            raise E2EStepError(
                step_num,
                step_name,
                f"Outils forensiques attendus absents de la Gateway : {missing_tools}",
            )

        exec_items, _ = self._paginate_items(
            step_num,
            step_name,
            f"/api/v1/cases/{case_id}/tool-executions",
            token=analyst_token,
        )
        current_run_execs = [
            item
            for item in exec_items
            if item.get("status") == "success"
            and item.get("created_at")
            and _parse_iso_any(str(item["created_at"])) >= run_started_at
        ]
        if not current_run_execs:
            raise E2EStepError(
                step_num,
                step_name,
                "Aucune exécution d'outil 'success' produite par la session courante.",
            )
        for item in current_run_execs:
            sha = str(item.get("result_sha256") or "")
            if not _HEX64_RE.match(sha):
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Exécution d'outil {item.get('id')} sans empreinte SHA-256 valide.",
                )

        obs_items, obs_total = self._paginate_items(
            step_num,
            step_name,
            f"/api/v1/cases/{case_id}/observations",
            token=analyst_token,
        )
        current_run_obs = [
            item
            for item in obs_items
            if item.get("created_at") and _parse_iso_any(str(item["created_at"])) >= run_started_at
        ]
        if obs_total < 1 or not current_run_obs:
            raise E2EStepError(
                step_num,
                step_name,
                "Aucune observation normalisée persistée pour la session courante.",
            )
        if self.config.mode == "local-demo" and not any(
            str(item.get("source_id") or "") == uploaded_evidence_id for item in current_run_obs
        ):
            raise E2EStepError(
                step_num,
                step_name,
                f"La preuve téléversée {uploaded_evidence_id} n'a produit aucune observation.",
            )

        self._log_step(
            step_num,
            step_name,
            f"OK ({len(current_run_execs)} exécution(s) success, "
            f"{len(current_run_obs)} observation(s) de session)",
        )

    def _step_7_findings_and_verifier(
        self,
        analyst_token: str,
        case_id: str,
    ) -> None:
        step_num, step_name = 7, "Analyse IA & Vérification déterministe (Verifier)"
        items, _ = self._paginate_items(
            step_num,
            step_name,
            f"/api/v1/cases/{case_id}/findings",
            token=analyst_token,
        )
        proposed = [item for item in items if item.get("status") == "proposed"]
        if not proposed:
            raise E2EStepError(
                step_num,
                step_name,
                "Aucun constat au statut 'proposed' formulé par l'Analyst et certifié.",
            )
        for finding in proposed:
            if not finding.get("observation_refs") or not finding.get("tool_execution_refs"):
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Constat {finding.get('id')} dépourvu de références probantes.",
                )

        self._log_step(step_num, step_name, f"OK ({len(proposed)} constat(s) vérifié(s) en revue)")

    def _step_8_review_findings_and_gate_h2(
        self,
        analyst_token: str,
        investigator_token: str,
        case_id: str,
        run_id: str,
    ) -> None:
        step_num, step_name = 8, "Revue des constats & Validation Porte H2"
        proposed_items, _ = self._paginate_items(
            step_num,
            step_name,
            f"/api/v1/cases/{case_id}/findings?status=proposed",
            token=analyst_token,
        )
        if not proposed_items:
            raise E2EStepError(
                step_num,
                step_name,
                "Aucun constat 'proposed' disponible pour arbitrage H2.",
            )

        for finding in proposed_items:
            finding_id = str(finding["id"])
            reviewed = self._parse_json(
                step_num,
                step_name,
                self._request(
                    step_num,
                    step_name,
                    "POST",
                    f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
                    token=analyst_token,
                    expected_status=200,
                    json_body={"action": "validate"},
                ),
            )
            if reviewed.get("status") != "validated":
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Le constat {finding_id} n'est pas passé au statut 'validated' : "
                    f"{reviewed.get('status')!r}",
                )

        remaining_items, remaining_total = self._paginate_items(
            step_num,
            step_name,
            f"/api/v1/cases/{case_id}/findings?status=proposed",
            token=analyst_token,
        )
        if remaining_total != 0 or remaining_items:
            raise E2EStepError(
                step_num,
                step_name,
                "Des constats restent encore au statut 'proposed' avant la porte H2.",
            )

        h2_resp = self._parse_json(
            step_num,
            step_name,
            self._request(
                step_num,
                step_name,
                "POST",
                f"/api/v1/cases/{case_id}/investigations/{run_id}/gates/h2",
                token=investigator_token,
                expected_status=200,
                json_body={
                    "decision": "proceed",
                    "feedback": "Constats validés lors du smoke test E2E",
                },
            ),
        )
        if h2_resp.get("status") != "running" or h2_resp.get("current_phase") != "gate_h3":
            raise E2EStepError(
                step_num,
                step_name,
                f"État post-H2 attendu (running, gate_h3), reçu "
                f"({h2_resp.get('status')!r}, {h2_resp.get('current_phase')!r}).",
            )

        resumed_h3 = self._parse_json(
            step_num,
            step_name,
            self._request(
                step_num,
                step_name,
                "POST",
                f"/api/v1/cases/{case_id}/investigations/{run_id}/resume",
                token=investigator_token,
                expected_status=200,
                llm_step=True,
            ),
        )
        if resumed_h3.get("status") != "paused" or resumed_h3.get("current_phase") not in (
            "waiting_h3",
            "gate_h3",
        ):
            raise E2EStepError(
                step_num,
                step_name,
                f"État attendu à la porte H3 (paused, waiting_h3), reçu "
                f"({resumed_h3.get('status')!r}, {resumed_h3.get('current_phase')!r}).",
            )

        self._log_step(
            step_num,
            step_name,
            f"OK ({len(proposed_items)} constat(s) validé(s), pause à waiting_h3)",
        )

    def _step_9_timeline_and_correlations(
        self,
        analyst_token: str,
        case_id: str,
    ) -> None:
        step_num, step_name = 9, "Timeline UTC & Corrélations multi-sources"
        events, _ = self._paginate_items(
            step_num,
            step_name,
            f"/api/v1/cases/{case_id}/timeline",
            token=analyst_token,
        )
        if not events:
            raise E2EStepError(
                step_num,
                step_name,
                "La timeline UTC du dossier est vide.",
            )

        parsed_timestamps: list[datetime] = []
        for event in events:
            raw_ts = event.get("timestamp_utc")
            if not raw_ts:
                raise E2EStepError(
                    step_num,
                    step_name,
                    "Événement timeline sans timestamp_utc.",
                )
            try:
                parsed_timestamps.append(_parse_iso_utc(str(raw_ts)))
            except ValueError as exc:
                raise E2EStepError(step_num, step_name, str(exc)) from exc

        for idx in range(1, len(parsed_timestamps)):
            if parsed_timestamps[idx] < parsed_timestamps[idx - 1]:
                raise E2EStepError(
                    step_num,
                    step_name,
                    "Ordre chronologique UTC de la timeline non monotone : "
                    f"{parsed_timestamps[idx - 1].isoformat()} > "
                    f"{parsed_timestamps[idx].isoformat()}",
                )

        correlations = self._parse_json(
            step_num,
            step_name,
            self._request(
                step_num,
                step_name,
                "GET",
                f"/api/v1/cases/{case_id}/timeline/correlations",
                token=analyst_token,
                expected_status=200,
            ),
        )
        if str(correlations.get("case_id") or "") != case_id:
            raise E2EStepError(
                step_num,
                step_name,
                f"case_id inattendu dans /timeline/correlations : {correlations.get('case_id')!r}",
            )
        groups = correlations.get("correlations")
        if not isinstance(groups, list):
            raise E2EStepError(
                step_num,
                step_name,
                "Champ 'correlations' absent ou invalide dans /timeline/correlations.",
            )
        if self.config.mode == "local-demo" and not groups:
            raise E2EStepError(
                step_num,
                step_name,
                "Aucun groupe de corrélation multi-sources retourné en mode local-demo.",
            )
        for group in groups:
            if (
                not isinstance(group, dict)
                or not group.get("finding_id")
                or not group.get("correlation_marker")
                or int(group.get("events_count") or 0) < 1
            ):
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Groupe de corrélation invalide dans /timeline/correlations : {group!r}",
                )

        self._log_step(
            step_num,
            step_name,
            f"OK ({len(events)} événement(s) UTC ordonnés, {len(groups)} groupe(s) de corrélation)",
        )

    def _step_10_presidio_preview(
        self,
        investigator_token: str,
        case_id: str,
        run_id: str,
    ) -> None:
        step_num, step_name = 10, "Pseudonymisation Presidio & Aperçu H3"
        preview = self._parse_json(
            step_num,
            step_name,
            self._request(
                step_num,
                step_name,
                "GET",
                f"/api/v1/cases/{case_id}/investigations/{run_id}/anonymized-preview",
                token=investigator_token,
                expected_status=200,
            ),
        )
        anonymized_text = str(preview.get("anonymized_text") or "")
        if not anonymized_text.strip():
            raise E2EStepError(
                step_num,
                step_name,
                "L'aperçu pseudonymisé (/anonymized-preview) est vide.",
            )
        if (
            str(preview.get("case_id") or "") != case_id
            or str(preview.get("run_id") or "") != run_id
        ):
            raise E2EStepError(
                step_num,
                step_name,
                "Identifiants case_id/run_id incohérents dans /anonymized-preview.",
            )
        for sensitive in SENSITIVE_DEMO_MARKERS:
            if sensitive in anonymized_text:
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Fuite PII détectée dans /anonymized-preview : "
                    f"'{sensitive}' non pseudonymisé.",
                )

        entity_count = int(preview.get("entity_count") or 0)
        if entity_count > 0 and not preview.get("has_entities"):
            raise E2EStepError(
                step_num,
                step_name,
                "Incohérence has_entities=False alors que entity_count > 0.",
            )
        if self.config.mode == "local-demo" and (
            entity_count < 1 or preview.get("has_entities") is not True
        ):
            raise E2EStepError(
                step_num,
                step_name,
                f"Pseudonymisation Presidio attendue en mode local-demo "
                f"(entity_count={entity_count}, has_entities={preview.get('has_entities')!r}).",
            )

        self._log_step(
            step_num,
            step_name,
            f"OK ({entity_count} entité(s) pseudonymisée(s) par Presidio)",
        )

    def _step_11_gate_h3_and_sealed_reports(
        self,
        investigator_token: str,
        case_id: str,
        run_id: str,
    ) -> tuple[dict[str, str], dict[str, str]]:
        step_num, step_name = 11, "Validation Porte H3 & Rapports scellés MD/JSON"
        h3_resp = self._parse_json(
            step_num,
            step_name,
            self._request(
                step_num,
                step_name,
                "POST",
                f"/api/v1/cases/{case_id}/investigations/{run_id}/gates/h3",
                token=investigator_token,
                expected_status=200,
                json_body={
                    "decision": "approve",
                    "feedback": "Autorisation rédaction rapport externe E2E",
                },
            ),
        )
        if h3_resp.get("status") != "running" or h3_resp.get("current_phase") != "reporting":
            raise E2EStepError(
                step_num,
                step_name,
                f"État post-H3 attendu (running, reporting), reçu "
                f"({h3_resp.get('status')!r}, {h3_resp.get('current_phase')!r}).",
            )

        resumed = self._parse_json(
            step_num,
            step_name,
            self._request(
                step_num,
                step_name,
                "POST",
                f"/api/v1/cases/{case_id}/investigations/{run_id}/resume",
                token=investigator_token,
                expected_status=200,
                llm_step=True,
            ),
        )
        if resumed.get("current_phase") != "reporting":
            raise E2EStepError(
                step_num,
                step_name,
                "Phase attendue 'reporting' après reprise H3, "
                f"reçu {resumed.get('current_phase')!r}.",
            )

        report_items, _ = self._paginate_items(
            step_num,
            step_name,
            f"/api/v1/cases/{case_id}/reports",
            token=investigator_token,
        )
        if not report_items:
            raise E2EStepError(
                step_num,
                step_name,
                "Aucun rapport scellé retourné par GET /reports.",
            )

        latest_version = max(int(item.get("version") or 0) for item in report_items)
        latest_by_format = {
            str(item.get("format")): item
            for item in report_items
            if int(item.get("version") or 0) == latest_version
        }
        for fmt in ("markdown", "json"):
            entry = latest_by_format.get(fmt)
            if entry is None:
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Rapport au format '{fmt}' manquant pour la version {latest_version}.",
                )
            if entry.get("status") != "validated":
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Rapport {fmt} non validé : {entry.get('status')!r}.",
                )

        report_ids: dict[str, str] = {}
        report_hashes: dict[str, str] = {}
        for fmt, expected_mime in (("markdown", "text/markdown"), ("json", "application/json")):
            entry = latest_by_format[fmt]
            report_id = str(entry["id"])
            expected_sha = str(entry["sha256"])
            dl_resp = self._request(
                step_num,
                step_name,
                "GET",
                f"/api/v1/cases/{case_id}/reports/{report_id}/download",
                token=investigator_token,
                expected_status=200,
            )
            content_type = (dl_resp.get_header("Content-Type") or "").split(";")[0].strip().lower()
            if content_type != expected_mime:
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Content-Type invalide pour rapport {fmt} : "
                    f"attendu {expected_mime!r}, reçu {content_type!r}.",
                )
            header_sha = str(dl_resp.get_header("X-Report-SHA256") or "")
            computed_sha = hashlib.sha256(dl_resp.body).hexdigest()
            if header_sha != expected_sha or computed_sha != expected_sha:
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Empreinte SHA-256 invalide pour rapport {fmt} : "
                    f"attendu={expected_sha}, header={header_sha}, calculé={computed_sha}.",
                )
            report_text = dl_resp.text
            for sensitive in SENSITIVE_DEMO_MARKERS:
                if sensitive in report_text:
                    raise E2EStepError(
                        step_num,
                        step_name,
                        f"Fuite PII détectée dans le rapport {fmt} : '{sensitive}'.",
                    )
            if fmt == "markdown":
                if "# Rapport d'incident IRYX" not in report_text:
                    raise E2EStepError(
                        step_num,
                        step_name,
                        "Le rapport Markdown téléchargé ne contient pas l'en-tête attendu.",
                    )
            else:
                parsed_doc = self._parse_json(step_num, step_name, dl_resp)
                if (
                    str(parsed_doc.get("case_id") or "") != case_id
                    or str(parsed_doc.get("run_id") or "") != run_id
                ):
                    raise E2EStepError(
                        step_num,
                        step_name,
                        "Identifiants case_id/run_id incohérents dans le rapport JSON.",
                    )
                sections = parsed_doc.get("sections") or []
                section_keys = [
                    str(section.get("key") or "")
                    for section in sections
                    if isinstance(section, dict)
                ]
                if len(sections) != 8 or set(section_keys) != set(CANONICAL_SECTION_KEYS):
                    raise E2EStepError(
                        step_num,
                        step_name,
                        "Le rapport JSON doit contenir les 8 sections canoniques, "
                        f"reçu {section_keys!r}.",
                    )

            report_ids[fmt] = report_id
            report_hashes[fmt] = computed_sha

        self._log_step(
            step_num,
            step_name,
            f"OK (v{latest_version} MD+JSON vérifiés, SHA-256 conformes)",
        )
        return report_ids, report_hashes

    def _step_12_audit_trail_and_invariant_3(
        self,
        admin_token: str,
        case_id: str,
    ) -> int:
        step_num, step_name = 12, "Journal d'audit & Invariant 3"
        events, total = self._paginate_items(
            step_num,
            step_name,
            f"/api/v1/cases/{case_id}/audit-trail",
            token=admin_token,
        )

        if not events:
            raise E2EStepError(step_num, step_name, "Journal d'audit vide pour le dossier.")
        if len(events) != total:
            raise E2EStepError(
                step_num,
                step_name,
                f"Incohérence de pagination /audit-trail : "
                f"{len(events)} éléments vs total={total}.",
            )

        recorded_actions = {str(item.get("action") or "") for item in events}
        missing_actions = sorted(EXPECTED_CASE_AUDIT_ACTIONS - recorded_actions)
        if missing_actions:
            raise E2EStepError(
                step_num,
                step_name,
                f"Actions d'audit attendues manquantes : {missing_actions}",
            )

        forbidden_values = tuple(cred.password for cred in self.credentials.values()) + ("eyJ",)
        for item in events:
            payload_hash = str(item.get("payload_hash") or "")
            if not _HEX64_RE.match(payload_hash):
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Événement d'audit {item.get('id')} avec payload_hash invalide.",
                )
            leaked = _check_dict_has_no_secret_keys(
                item.get("details"),
                forbidden_values=forbidden_values,
            )
            if leaked is not None:
                raise E2EStepError(
                    step_num,
                    step_name,
                    f"Donnée sensible ({leaked}) détectée dans AuditEvent.details.",
                )

        # Invariant 3 HTTP check: mutation attempts on /audit-trail must return 405
        self._request(
            step_num,
            step_name,
            "DELETE",
            f"/api/v1/cases/{case_id}/audit-trail",
            token=admin_token,
            expected_status=405,
        )
        self._request(
            step_num,
            step_name,
            "PATCH",
            f"/api/v1/cases/{case_id}/audit-trail",
            token=admin_token,
            expected_status=405,
            json_body={"action": "TAMPERED"},
        )

        sql_status = "SQL ignoré (--skip-db-audit-check)"
        if not self.config.skip_db_audit_check:
            checker = self.sql_audit_checker or (
                lambda cid: verify_sql_audit_append_only(case_id=cid, db_url=self.config.db_url)
            )
            checker(case_id)
            sql_status = "SQL CANNOT_MODIFY_AUDIT_LOG vérifié"

        self._log_step(
            step_num,
            step_name,
            f"OK ({total} événement(s) d'audit, HTTP 405 + {sql_status})",
        )
        return total


class _LocalDemoLLMClient:
    """In-script deterministic LLM stub used exclusively in ``--mode local-demo``."""

    def __init__(self, role: Any) -> None:
        from iryx.ai.schemas import LLMRole

        self._role = role if isinstance(role, LLMRole) else LLMRole(str(role))

    @property
    def role(self) -> Any:
        return self._role

    def for_role(self, role: Any) -> _LocalDemoLLMClient:
        return _LocalDemoLLMClient(role)

    async def complete(
        self,
        messages: list[Any] | None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> Any:
        del temperature, max_tokens, response_format, model
        from iryx.ai.schemas import LLMResponse, LLMRole

        joined = "\n".join(
            str(m.get("content", "") if isinstance(m, dict) else getattr(m, "content", ""))
            for m in (messages or [])
        )

        if self._role == LLMRole.PLANNER:
            content = self._planner_response(joined)
        elif self._role == LLMRole.ANALYST:
            content = self._analyst_response(joined)
        elif self._role == LLMRole.RAPPORTEUR:
            content = self._rapporteur_response()
        else:
            content = "{}"

        return LLMResponse(content=content, role="assistant", model="local-demo-stub")

    @staticmethod
    def _planner_response(prompt: str) -> str:
        evidences = re.findall(
            r"Preuve ID:\s*([0-9a-fA-F-]+)\s*\|\s*Fichier:\s*([^\s|]+)",
            prompt,
        )
        tool_by_ext = (
            (".evtx", "parse_evtx", "Analyse des événements de sécurité Windows (4624/4688)"),
            (".pf", "parse_execution", "Analyse des artefacts d'exécution Prefetch PowerShell"),
            (".csv", "parse_text_logs", "Analyse chronologique du journal de triage CSV"),
            (".log", "parse_text_logs", "Analyse chronologique du journal texte"),
        )
        steps: list[dict[str, Any]] = []
        for ev_id, name in evidences:
            lower = name.lower()
            for ext, tool_name, rationale in tool_by_ext:
                if lower.endswith(ext):
                    steps.append(
                        {
                            "step_id": len(steps) + 1,
                            "tool_name": tool_name,
                            "target_evidence_id": ev_id,
                            "parameters": {},
                            "rationale": rationale,
                            "is_blocking": False,
                            "continue_on_error": True,
                        }
                    )
                    break
        if not steps and evidences:
            steps.append(
                {
                    "step_id": 1,
                    "tool_name": "parse_text_logs",
                    "target_evidence_id": evidences[0][0],
                    "parameters": {},
                    "rationale": "Analyse initiale de la preuve disponible",
                    "is_blocking": False,
                    "continue_on_error": True,
                }
            )
        return json.dumps(
            {
                "summary": "Plan d'investigation multi-artefacts EVTX / Prefetch / Journal CSV.",
                "steps": steps[:10],
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _analyst_response(prompt: str) -> str:
        obs_matches = re.findall(
            r"- ID:\s*([0-9a-fA-F-]+)\s*\n"
            r"- Outil:\s*([^\n]+)\n"
            r"- Tool Execution ID:\s*([0-9a-fA-F-]+)",
            prompt,
        )
        selected_obs: list[str] = []
        selected_execs: list[str] = []
        seen_tools: set[str] = set()
        for obs_id, tool_name, exec_id in obs_matches:
            if tool_name not in seen_tools:
                seen_tools.add(tool_name)
                selected_obs.append(obs_id)
                if exec_id and exec_id not in selected_execs:
                    selected_execs.append(exec_id)
        if not selected_obs and obs_matches:
            selected_obs.append(obs_matches[0][0])
            if obs_matches[0][2]:
                selected_execs.append(obs_matches[0][2])

        return json.dumps(
            {
                "summary": "Activité PowerShell encodée corrélée avec mouvement latéral.",
                "findings": [
                    {
                        "title": (
                            "Exécution PowerShell encodée par svc_backup depuis "
                            "10.42.17.88 sur SRV-AD01"
                        ),
                        "severity": "high",
                        "confidence": "high",
                        "finding_type": "fact",
                        "observation_refs": selected_obs,
                        "tool_execution_refs": selected_execs,
                    }
                ],
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _rapporteur_response() -> str:
        return json.dumps(
            {
                "resume_managerial": (
                    "Synthèse d'incident validée après arbitrage humain H1, H2 et H3 "
                    "sur des artefacts pseudonymisés."
                ),
                "perimetre": "Périmètre scellé couvrant les journaux Windows, Prefetch et CSV.",
                "methodologie": (
                    "Orchestration LangGraph supervisée, exécution gateway confinée "
                    "et vérification déterministe sans LLM."
                ),
                "chaine_des_preuves": "Preuves scellées par SHA-256 en mode lecture seule.",
                "observations": "Observations techniques normalisées et horodatées en UTC.",
                "constats_valides": "Reconstruit exclusivement depuis les constats validés.",
                "chronologie": "Frise chronologique UTC monotone et corrélations multi-sources.",
                "limites": "Synthèse issue du mode démonstration locale autonome.",
            },
            ensure_ascii=False,
        )


@contextmanager
def local_demo_environment() -> Iterator[tuple[HttpTransport, Any]]:
    """Build an isolated FastAPI + SQLite + MemorySaver demo stack for offline runs."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_root:
        tmp_path = Path(tmp_root)
        storage_dir = tmp_path / "raw"
        staging_dir = tmp_path / "staging"
        db_path = tmp_path / "local_demo.db"
        storage_dir.mkdir(parents=True, exist_ok=True)
        staging_dir.mkdir(parents=True, exist_ok=True)

        env_overrides = {
            "SECRET_KEY": "iryx-local-demo-secret-key-min-32-chars",
            "JWT_SECRET_KEY": "iryx-local-demo-jwt-key-min-32-chars",
            "ENVIRONMENT": "test",
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "EVIDENCE_STORAGE_PATH": str(storage_dir),
            "EVIDENCE_STAGING_PATH": str(staging_dir),
            "MAX_EVIDENCE_SIZE_GB": "1",
            "OPENAI_API_KEY": "local-demo-stub-key",
        }
        prev_env = {key: os.environ.get(key) for key in env_overrides}
        os.environ.update(env_overrides)

        try:
            from alembic import command as alembic_command
            from alembic.config import Config as AlembicConfig
            from fastapi.testclient import TestClient
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            import iryx.analytics.models  # noqa: F401
            import iryx.audit.models  # noqa: F401
            import iryx.auth.models  # noqa: F401
            import iryx.cases.models  # noqa: F401
            import iryx.evidence.models  # noqa: F401
            import iryx.gateway.models  # noqa: F401
            import iryx.orchestrator.models  # noqa: F401
            import iryx.reporting.models  # noqa: F401
            from iryx.api.dependencies import get_db
            from iryx.core.config import Settings, get_settings
            from iryx.evidence.tasks import process_evidence_ingestion
            from iryx.main import create_app
            from iryx.orchestrator.checkpointer import reset_memory_saver
            from iryx.orchestrator.graph import set_runtime_context
            from iryx.scripts import seed_data

            get_settings.cache_clear()
            demo_settings = Settings(**{k.lower(): v for k, v in env_overrides.items()})

            engine = create_engine(
                demo_settings.database_url,
                connect_args={"check_same_thread": False},
            )
            try:
                backend_dir = Path(__file__).resolve().parents[3]
                alembic_cfg = AlembicConfig(str(backend_dir / "alembic.ini"))
                alembic_cfg.set_main_option("script_location", str(backend_dir / "migrations"))
                alembic_cfg.attributes["connection"] = engine
                alembic_command.upgrade(alembic_cfg, "head")

                demo_session_factory = sessionmaker(
                    bind=engine,
                    autoflush=False,
                    autocommit=False,
                    expire_on_commit=False,
                )
                reset_memory_saver()
                demo_app = create_app()

                def _override_get_db() -> Iterator[Any]:
                    session = demo_session_factory()
                    try:
                        yield session
                    finally:
                        with contextlib.suppress(Exception):
                            session.rollback()
                        session.close()

                demo_app.dependency_overrides[get_db] = _override_get_db

                def _sync_celery_stub(evidence_id: str, staging_path: str) -> dict[str, Any]:
                    return process_evidence_ingestion(evidence_id, staging_path)

                def _llm_factory(role: Any) -> _LocalDemoLLMClient:
                    return _LocalDemoLLMClient(role)

                with ExitStack() as stack:
                    stack.enter_context(
                        patch(
                            "iryx.scripts.seed_data.SessionLocal",
                            side_effect=demo_session_factory,
                        )
                    )
                    stack.enter_context(
                        patch("iryx.scripts.seed_data.get_settings", return_value=demo_settings)
                    )
                    stack.enter_context(
                        patch(
                            "iryx.evidence.tasks.SessionLocal",
                            side_effect=demo_session_factory,
                        )
                    )
                    stack.enter_context(
                        patch("iryx.evidence.tasks.get_settings", return_value=demo_settings)
                    )
                    stack.enter_context(
                        patch.object(
                            process_evidence_ingestion,
                            "delay",
                            side_effect=_sync_celery_stub,
                        )
                    )
                    stack.enter_context(
                        patch("iryx.orchestrator.planner.get_llm_client", side_effect=_llm_factory)
                    )
                    stack.enter_context(
                        patch("iryx.orchestrator.analyst.get_llm_client", side_effect=_llm_factory)
                    )
                    stack.enter_context(
                        patch("iryx.orchestrator.graph.get_llm_client", side_effect=_llm_factory)
                    )

                    seed_data.seed_demo_data()
                    set_runtime_context({})
                    try:
                        with TestClient(demo_app, raise_server_exceptions=False) as client:
                            yield TestClientHttpTransport(client), engine
                    finally:
                        set_runtime_context({})
                        reset_memory_saver()
                        demo_app.dependency_overrides.clear()
            finally:
                engine.dispose()
        finally:
            for file_path in tmp_path.rglob("*"):
                if file_path.is_file():
                    with contextlib.suppress(OSError):
                        os.chmod(file_path, stat.S_IWRITE | stat.S_IREAD)
            for key, old_val in prev_env.items():
                if old_val is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old_val
            with contextlib.suppress(Exception):
                from iryx.core.config import get_settings

                get_settings.cache_clear()


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m iryx.scripts.test_e2e_investigation_flow",
        description="Smoke test d'acceptation E2E du MVP IRYX (Story 9.4).",
    )
    parser.add_argument(
        "--mode",
        choices=("stack", "local-demo"),
        default="stack",
        help="Mode d'exécution : 'stack' (pile réelle, défaut) ou 'local-demo' (autonome).",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="URL de base de l'API IRYX en mode 'stack' (défaut: http://127.0.0.1:8000).",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="URL PostgreSQL pour la vérification SQL Invariant 3 en mode 'stack'.",
    )
    parser.add_argument(
        "--skip-db-audit-check",
        action="store_true",
        help="Désactive la vérification SQL directe sur audit_events (conserve le test HTTP 405).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Délai maximal (secondes) pour les requêtes HTTP et le polling d'ingestion.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=3.0,
        help="Intervalle de polling (secondes) en attente de scellement SHA-256.",
    )
    return parser


def run_e2e(config: E2ERunnerConfig, *, output: TextIO | None = None) -> E2ERunSummary:
    """Execute the E2E suite according to the supplied ``E2ERunnerConfig``."""
    out = output or sys.stdout
    if config.mode == "local-demo":
        with local_demo_environment() as (transport, demo_engine):
            runner = InvestigationE2ERunner(
                transport=transport,
                config=config,
                sql_audit_checker=lambda cid: verify_sql_audit_append_only(
                    case_id=cid,
                    engine=demo_engine,
                ),
                output=out,
            )
            return runner.run()

    transport = UrllibHttpTransport(config.base_url)
    runner = InvestigationE2ERunner(transport=transport, config=config, output=out)
    return runner.run()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point returning 0 on full 12-step success or 1 on failure."""
    args = build_arg_parser().parse_args(argv)
    if (
        not math.isfinite(args.timeout)
        or args.timeout <= 0
        or not math.isfinite(args.poll_interval)
        or args.poll_interval <= 0
    ):
        print(
            "[ERREUR] --timeout et --poll-interval doivent être finis et strictement positifs.",
            file=sys.stderr,
        )
        return 1

    config = E2ERunnerConfig(
        mode=args.mode,
        base_url=args.base_url,
        db_url=args.db_url,
        skip_db_audit_check=bool(args.skip_db_audit_check),
        timeout=float(args.timeout),
        poll_interval=float(args.poll_interval),
    )
    try:
        run_e2e(config, output=sys.stdout)
    except E2EStepError as exc:
        print(f"[ÉCHEC E2E] {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[ÉCHEC E2E] Erreur inattendue : {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(SUCCESS_BANNER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
