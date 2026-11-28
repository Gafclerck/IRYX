"""Unit tests for the 12-step E2E acceptance and demonstration script (Story 9.4)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import uuid
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text

from iryx.scripts import test_e2e_investigation_flow as e2e
from iryx.scripts.test_e2e_investigation_flow import (
    E2ERunnerConfig,
    E2EStepError,
    HttpResponse,
    HttpTransport,
    InvestigationE2ERunner,
    UrllibHttpTransport,
    local_demo_environment,
    main,
    run_e2e,
    verify_sql_audit_append_only,
)


class _InterceptingTransport:
    """Delegate requests to an inner transport with optional per-request overrides."""

    def __init__(
        self,
        inner: HttpTransport,
        interceptor: Callable[[str, str, HttpResponse], HttpResponse] | None = None,
    ) -> None:
        self._inner = inner
        self._interceptor = interceptor

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
        resp = self._inner.request(
            method,
            path,
            headers=headers,
            json_body=json_body,
            files=files,
            timeout=timeout,
        )
        if self._interceptor is not None:
            return self._interceptor(method.upper(), path, resp)
        return resp


def _make_json_response(
    status_code: int,
    payload: Any,
    headers: dict[str, str] | None = None,
) -> HttpResponse:
    resolved_headers = headers or {"content-type": "application/json"}
    return HttpResponse(
        status_code=status_code,
        headers={k.lower(): v for k, v in resolved_headers.items()},
        body=json.dumps(payload).encode("utf-8"),
    )


def test_full_e2e_flow_local_demo_succeeds() -> None:
    """Verify all 12 E2E steps pass end-to-end in isolated local-demo mode."""
    summary = run_e2e(E2ERunnerConfig(mode="local-demo", poll_interval=0.01))

    assert summary.steps_completed == 12
    assert summary.case_id
    assert summary.run_id
    assert summary.uploaded_evidence_id
    assert summary.uploaded_sha256 == hashlib.sha256(e2e.DEMO_EVIDENCE_CONTENT).hexdigest()
    assert set(summary.report_ids) == {"markdown", "json"}
    assert set(summary.report_hashes) == {"markdown", "json"}
    assert summary.audit_event_count >= 7


def test_cli_main_local_demo_prints_banner_and_masks_secrets(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify CLI main returns 0, prints the required French banner, and leaks no secrets."""
    exit_code = main(["--mode", "local-demo", "--poll-interval", "0.01"])
    captured = capsys.readouterr()

    assert exit_code == 0, captured.err
    assert e2e.SUCCESS_BANNER in captured.out
    assert "[12/12]" in captured.out
    for cred in e2e.DEFAULT_DEMO_CREDENTIALS.values():
        assert cred.password not in captured.out
        assert cred.password not in captured.err
    assert "eyJ" not in captured.out
    assert "eyJ" not in captured.err


def test_cli_subprocess_runs_without_env_or_secret_key() -> None:
    """Verify module CLI executes cleanly in a fresh subprocess without .env."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"SECRET_KEY", "JWT_SECRET_KEY", "DATABASE_URL"}
    }
    env["PYTHONIOENCODING"] = "utf-8"

    backend_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "iryx.scripts.test_e2e_investigation_flow",
            "--mode",
            "local-demo",
            "--poll-interval",
            "0.01",
        ],
        cwd=str(backend_root),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert e2e.SUCCESS_BANNER in completed.stdout


def test_urllib_transport_handles_json_multipart_and_http_errors() -> None:
    """Verify stdlib UrllibHttpTransport handles JSON, multipart upload, and 4xx errors."""

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            ctype = self.headers.get("Content-Type") or ""
            if self.path == "/upload":
                self.send_response(202)
                self.send_header("Content-Type", "application/json")
                self.send_header("Location", "/status")
                self.send_header("Retry-After", "3")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {
                            "ctype": ctype,
                            "contains_bytes": b"hello-evidence" in raw,
                        }
                    ).encode("utf-8")
                )
                return
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"code":"FORBIDDEN"}}')

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        transport = UrllibHttpTransport(base_url)

        get_resp = transport.request("GET", "/health")
        assert get_resp.status_code == 200
        assert get_resp.json() == {"status": "ok"}

        upload_resp = transport.request(
            "POST",
            "/upload",
            files={"file": ("sample.csv", b"hello-evidence", "text/csv")},
        )
        assert upload_resp.status_code == 202
        assert upload_resp.get_header("Location") == "/status"
        assert upload_resp.get_header("Retry-After") == "3"
        assert upload_resp.json()["contains_bytes"] is True

        err_resp = transport.request("POST", "/forbidden", json_body={"a": 1})
        assert err_resp.status_code == 403
        assert err_resp.json()["error"]["code"] == "FORBIDDEN"
    finally:
        server.shutdown()
        server.server_close()


def test_runner_fails_fast_on_auth_bypass() -> None:
    """Verify Step 1 fails fast if unauthenticated /auth/me does not return 401."""
    with local_demo_environment() as (transport, _engine):

        def _intercept(method: str, path: str, resp: HttpResponse) -> HttpResponse:
            if method == "GET" and path == "/api/v1/auth/me" and resp.status_code == 401:
                return _make_json_response(200, {"email": "bypass@iryx.local"})
            return resp

        runner = InvestigationE2ERunner(
            _InterceptingTransport(transport, _intercept),
            E2ERunnerConfig(mode="local-demo", poll_interval=0.01, skip_db_audit_check=True),
        )
        with pytest.raises(E2EStepError) as exc_info:
            runner.run()
        assert exc_info.value.step_number == 1


def test_runner_fails_fast_on_rbac_bypass_on_audit_trail() -> None:
    """Verify Step 2 fails fast if analyst or viewer is allowed on /audit-trail."""
    with local_demo_environment() as (transport, _engine):

        def _intercept(method: str, path: str, resp: HttpResponse) -> HttpResponse:
            if method == "GET" and path.endswith("/audit-trail") and resp.status_code == 403:
                return _make_json_response(200, {"items": [], "total": 0})
            return resp

        runner = InvestigationE2ERunner(
            _InterceptingTransport(transport, _intercept),
            E2ERunnerConfig(mode="local-demo", poll_interval=0.01, skip_db_audit_check=True),
        )
        with pytest.raises(E2EStepError) as exc_info:
            runner.run()
        assert exc_info.value.step_number == 2


def test_runner_fails_fast_on_ingestion_sha256_mismatch() -> None:
    """Verify Step 3 fails fast when polled SHA-256 differs from local digest."""
    with local_demo_environment() as (transport, _engine):

        def _intercept(method: str, path: str, resp: HttpResponse) -> HttpResponse:
            if method == "GET" and path.endswith("/ingestion-status"):
                data = resp.json()
                data["sha256"] = "0" * 64
                return _make_json_response(200, data)
            return resp

        runner = InvestigationE2ERunner(
            _InterceptingTransport(transport, _intercept),
            E2ERunnerConfig(mode="local-demo", poll_interval=0.01, skip_db_audit_check=True),
        )
        with pytest.raises(E2EStepError) as exc_info:
            runner.run()
        assert exc_info.value.step_number == 3
        assert "SHA-256" in str(exc_info.value)


def test_runner_fails_fast_on_ingestion_polling_timeout() -> None:
    """Verify Step 3 fails fast when ingestion polling stays pending past timeout."""
    with local_demo_environment() as (transport, _engine):

        def _intercept(method: str, path: str, resp: HttpResponse) -> HttpResponse:
            if method == "GET" and path.endswith("/ingestion-status"):
                return _make_json_response(
                    200,
                    {"status": "pending", "progress": 10},
                    headers={"content-type": "application/json", "retry-after": "3"},
                )
            return resp

        runner = InvestigationE2ERunner(
            _InterceptingTransport(transport, _intercept),
            E2ERunnerConfig(
                mode="local-demo",
                timeout=0.05,
                poll_interval=0.01,
                skip_db_audit_check=True,
            ),
        )
        with pytest.raises(E2EStepError) as exc_info:
            runner.run()
        assert exc_info.value.step_number == 3
        assert "Timeout" in str(exc_info.value)


def test_runner_reports_llm_503_diagnostic_in_stack_mode() -> None:
    """Verify Step 4 surfaces explicit LLM/local-demo hint on 503 in stack mode."""
    with local_demo_environment() as (transport, _engine):

        def _intercept(method: str, path: str, resp: HttpResponse) -> HttpResponse:
            if method == "POST" and path.endswith("/resume"):
                return _make_json_response(
                    503,
                    {"error": {"code": "LLM_SERVICE_UNAVAILABLE", "message": "LLM down"}},
                )
            return resp

        runner = InvestigationE2ERunner(
            _InterceptingTransport(transport, _intercept),
            E2ERunnerConfig(mode="stack", poll_interval=0.01, skip_db_audit_check=True),
        )
        with pytest.raises(E2EStepError) as exc_info:
            runner.run()
        assert exc_info.value.step_number == 4
        assert "--mode local-demo" in str(exc_info.value)


def test_runner_fails_fast_on_unexpected_gate_phase() -> None:
    """Verify Step 4/5 fails fast when /resume returns an unexpected phase instead of waiting_h1."""
    with local_demo_environment() as (transport, _engine):

        def _intercept(method: str, path: str, resp: HttpResponse) -> HttpResponse:
            if method == "POST" and path.endswith("/resume") and resp.status_code == 200:
                data = resp.json()
                data["current_phase"] = "reporting"
                return _make_json_response(200, data)
            return resp

        runner = InvestigationE2ERunner(
            _InterceptingTransport(transport, _intercept),
            E2ERunnerConfig(mode="local-demo", poll_interval=0.01, skip_db_audit_check=True),
        )
        with pytest.raises(E2EStepError) as exc_info:
            runner.run()
        assert exc_info.value.step_number == 4
        assert "waiting_h1" in str(exc_info.value)


def test_runner_fails_fast_when_findings_stay_proposed_before_h2() -> None:
    """Verify Step 8 fails fast if proposed findings remain unreviewed before H2."""
    with local_demo_environment() as (transport, _engine):

        def _intercept(method: str, path: str, resp: HttpResponse) -> HttpResponse:
            if method == "GET" and "findings?status=proposed" in path:
                data = resp.json()
                if data.get("total") == 0:
                    data["total"] = 1
                    return _make_json_response(200, data)
            return resp

        runner = InvestigationE2ERunner(
            _InterceptingTransport(transport, _intercept),
            E2ERunnerConfig(mode="local-demo", poll_interval=0.01, skip_db_audit_check=True),
        )
        with pytest.raises(E2EStepError) as exc_info:
            runner.run()
        assert exc_info.value.step_number == 8


def test_runner_fails_fast_on_report_sha256_mismatch() -> None:
    """Verify Step 11 fails fast when downloaded report SHA-256 header mismatches body."""
    with local_demo_environment() as (transport, _engine):

        def _intercept(method: str, path: str, resp: HttpResponse) -> HttpResponse:
            if method == "GET" and path.endswith("/download"):
                headers = dict(resp.headers)
                headers["x-report-sha256"] = "f" * 64
                return HttpResponse(status_code=200, headers=headers, body=resp.body)
            return resp

        runner = InvestigationE2ERunner(
            _InterceptingTransport(transport, _intercept),
            E2ERunnerConfig(mode="local-demo", poll_interval=0.01, skip_db_audit_check=True),
        )
        with pytest.raises(E2EStepError) as exc_info:
            runner.run()
        assert exc_info.value.step_number == 11
        assert "SHA-256" in str(exc_info.value)


def test_runner_fails_fast_when_http_audit_delete_is_accepted() -> None:
    """Verify Step 12 fails fast if DELETE /audit-trail does not return HTTP 405."""
    with local_demo_environment() as (transport, _engine):

        def _intercept(method: str, path: str, resp: HttpResponse) -> HttpResponse:
            if method == "DELETE" and path.endswith("/audit-trail"):
                return _make_json_response(200, {"deleted": True})
            return resp

        runner = InvestigationE2ERunner(
            _InterceptingTransport(transport, _intercept),
            E2ERunnerConfig(mode="local-demo", poll_interval=0.01, skip_db_audit_check=True),
        )
        with pytest.raises(E2EStepError) as exc_info:
            runner.run()
        assert exc_info.value.step_number == 12
        assert "405" in str(exc_info.value)


def test_verify_sql_audit_append_only_detects_missing_trigger(tmp_path: Path) -> None:
    """Verify SQL Invariant 3 checker detects missing triggers, rolls back, and supports db_url."""
    db_file = tmp_path / "audit_check.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    case_id = uuid.uuid4()
    row_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE audit_events (id TEXT PRIMARY KEY, case_id TEXT, action TEXT)")
        )
        conn.execute(
            text("INSERT INTO audit_events (id, case_id, action) VALUES (:id, :cid, 'CASE_READ')"),
            {"id": row_id.hex, "cid": case_id.hex},
        )
    engine.dispose()

    with pytest.raises(E2EStepError) as exc_info:
        verify_sql_audit_append_only(case_id=str(case_id), db_url=db_url)
    assert exc_info.value.step_number == 12
    assert "Invariant 3" in str(exc_info.value)

    # Confirm the attempted UPDATE('TAMPERED') was rolled back cleanly
    verify_engine = create_engine(db_url, connect_args={"check_same_thread": False})
    try:
        with verify_engine.connect() as conn:
            action = conn.execute(
                text("SELECT action FROM audit_events WHERE id = :id"),
                {"id": row_id.hex},
            ).scalar()
            assert action == "CASE_READ"

        # Now install only UPDATE trigger and verify DELETE-allowed gap is still caught
        with verify_engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TRIGGER trg_no_upd BEFORE UPDATE ON audit_events "
                    "FOR EACH ROW BEGIN SELECT RAISE(ABORT, 'CANNOT_MODIFY_AUDIT_LOG'); END;"
                )
            )
        with pytest.raises(E2EStepError) as del_exc:
            verify_sql_audit_append_only(case_id=str(case_id), engine=verify_engine)
        assert del_exc.value.step_number == 12
        assert "DELETE" in str(del_exc.value)
        with verify_engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM audit_events")).scalar()
            assert count == 1
    finally:
        verify_engine.dispose()


def test_default_demo_credentials_match_seed_data() -> None:
    """Verify E2E demo credentials stay in sync with seed_data.DEMO_USERS."""
    from iryx.scripts import seed_data

    expected = {spec.role.value: (spec.email, spec.password) for spec in seed_data.DEMO_USERS}
    actual = {
        key: (cred.email, cred.password) for key, cred in e2e.DEFAULT_DEMO_CREDENTIALS.items()
    }
    assert actual == expected
    assert e2e.CASE_TITLE == seed_data.CASE_TITLE


def test_urllib_transport_connection_error_and_invalid_arguments() -> None:
    """Verify UrllibHttpTransport raises ConnectionError on closed port and ValueError."""
    transport = UrllibHttpTransport("http://127.0.0.1:1")
    with pytest.raises(ValueError, match="mutually exclusive"):
        transport.request(
            "POST",
            "/test",
            json_body={"a": 1},
            files={"file": ("a.txt", b"x", "text/plain")},
        )
    with pytest.raises(ConnectionError):
        transport.request("GET", "/health", timeout=0.2)


@pytest.mark.parametrize(
    ("gate_suffix", "expected_step"),
    [
        ("/gates/h1", 5),
        ("/gates/h2", 8),
        ("/gates/h3", 11),
    ],
)
def test_runner_fails_fast_on_unexpected_gate_arbitration_phase(
    gate_suffix: str,
    expected_step: int,
) -> None:
    """Verify Steps 5, 8, and 11 fail fast if gate arbitration returns an invalid phase."""
    with local_demo_environment() as (transport, _engine):

        def _intercept(method: str, path: str, resp: HttpResponse) -> HttpResponse:
            if method == "POST" and path.endswith(gate_suffix) and resp.status_code == 200:
                data = resp.json()
                data["current_phase"] = "triage"
                return _make_json_response(200, data)
            return resp

        runner = InvestigationE2ERunner(
            _InterceptingTransport(transport, _intercept),
            E2ERunnerConfig(mode="local-demo", poll_interval=0.01, skip_db_audit_check=True),
        )
        with pytest.raises(E2EStepError) as exc_info:
            runner.run()
        assert exc_info.value.step_number == expected_step


def test_runner_fails_fast_on_non_monotonic_timeline_utc() -> None:
    """Verify Step 9 fails fast when timeline events are not monotonically ordered in UTC."""
    with local_demo_environment() as (transport, _engine):

        def _intercept(method: str, path: str, resp: HttpResponse) -> HttpResponse:
            if method == "GET" and "/timeline?" in path and resp.status_code == 200:
                data = resp.json()
                items = list(data.get("items") or [])
                if len(items) >= 2:
                    items[0]["timestamp_utc"] = "2099-01-01T00:00:00+00:00"
                    data["items"] = items
                return _make_json_response(200, data)
            return resp

        runner = InvestigationE2ERunner(
            _InterceptingTransport(transport, _intercept),
            E2ERunnerConfig(mode="local-demo", poll_interval=0.01, skip_db_audit_check=True),
        )
        with pytest.raises(E2EStepError) as exc_info:
            runner.run()
        assert exc_info.value.step_number == 9
        assert "monotone" in str(exc_info.value)


def test_runner_fails_fast_on_step_10_pii_leak() -> None:
    """Verify Step 10 fails fast if unmasked PII appears in /anonymized-preview."""
    with local_demo_environment() as (transport, _engine):

        def _intercept(method: str, path: str, resp: HttpResponse) -> HttpResponse:
            if method == "GET" and path.endswith("/anonymized-preview") and resp.status_code == 200:
                data = resp.json()
                data["anonymized_text"] = "Leak: adm_backup from 10.42.17.88"
                return _make_json_response(200, data)
            return resp

        runner = InvestigationE2ERunner(
            _InterceptingTransport(transport, _intercept),
            E2ERunnerConfig(mode="local-demo", poll_interval=0.01, skip_db_audit_check=True),
        )
        with pytest.raises(E2EStepError) as exc_info:
            runner.run()
        assert exc_info.value.step_number == 10
        assert "PII" in str(exc_info.value)


@pytest.mark.parametrize("failure_mode", ["patch_200", "missing_action", "secret_leak"])
def test_runner_fails_fast_on_step_12_audit_anomalies(failure_mode: str) -> None:
    """Verify Step 12 catches PATCH non-405, missing audit action, and secret leakage."""
    with local_demo_environment() as (transport, _engine):

        def _intercept(method: str, path: str, resp: HttpResponse) -> HttpResponse:
            if failure_mode == "patch_200" and method == "PATCH" and path.endswith("/audit-trail"):
                return _make_json_response(200, {"patched": True})
            if method == "GET" and "/audit-trail?" in path and resp.status_code == 200:
                data = resp.json()
                items = list(data.get("items") or [])
                if failure_mode == "missing_action":
                    filtered = [item for item in items if item.get("action") != "REPORT_GENERATE"]
                    data["items"] = filtered
                    data["total"] = len(filtered)
                elif failure_mode == "secret_leak" and items:
                    admin_pw = e2e.DEFAULT_DEMO_CREDENTIALS["admin"].password
                    items[0]["details"] = {"leaked_note": admin_pw}
                    data["items"] = items
                return _make_json_response(200, data)
            return resp

        runner = InvestigationE2ERunner(
            _InterceptingTransport(transport, _intercept),
            E2ERunnerConfig(mode="local-demo", poll_interval=0.01, skip_db_audit_check=True),
        )
        with pytest.raises(E2EStepError) as exc_info:
            runner.run()
        assert exc_info.value.step_number == 12


def test_cli_main_returns_nonzero_on_invalid_arguments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify CLI main returns non-zero on invalid args or runner failure."""
    for bad_args in (["--timeout", "0"], ["--timeout", "nan"], ["--poll-interval", "inf"]):
        assert main(bad_args) == 1
        assert "[ERREUR]" in capsys.readouterr().err

    assert main(["--mode", "stack", "--base-url", "http://127.0.0.1:1", "--timeout", "0.2"]) == 1
    assert "[ÉCHEC E2E]" in capsys.readouterr().err
