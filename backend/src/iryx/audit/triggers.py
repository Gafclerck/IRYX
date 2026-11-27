"""Database-level append-only enforcement for the audit trail (Story 8.5)."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

AUDIT_LOG_ERROR_MESSAGE = "CANNOT_MODIFY_AUDIT_LOG"

# Mutation guard applied on both supported dialects. Individual statements are
# kept separate so psycopg3 prepared-statement clients can execute each one.
AUDIT_TRIGGER_STATEMENTS: dict[str, tuple[str, ...]] = {
    "postgresql": (
        (
            "CREATE OR REPLACE FUNCTION prevent_audit_event_mutation() "
            "RETURNS trigger AS $$ BEGIN "
            f"RAISE EXCEPTION '{AUDIT_LOG_ERROR_MESSAGE}'; "
            "END; "
            "$$ LANGUAGE plpgsql;"
        ),
        "DROP TRIGGER IF EXISTS trg_audit_events_append_only ON audit_events;",
        (
            "CREATE TRIGGER trg_audit_events_append_only "
            "BEFORE UPDATE OR DELETE ON audit_events "
            "FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation();"
        ),
        (
            "DROP TRIGGER IF EXISTS trg_audit_events_append_only_truncate ON audit_events;"
        ),
        (
            "CREATE TRIGGER trg_audit_events_append_only_truncate "
            "BEFORE TRUNCATE ON audit_events "
            "FOR EACH STATEMENT EXECUTE FUNCTION prevent_audit_event_mutation();"
        ),
    ),
    "sqlite": (
        (
            "CREATE TRIGGER IF NOT EXISTS trg_audit_events_no_update "
            "BEFORE UPDATE ON audit_events "
            "FOR EACH ROW BEGIN "
            f"SELECT RAISE(ABORT, '{AUDIT_LOG_ERROR_MESSAGE}'); "
            "END;"
        ),
        (
            "CREATE TRIGGER IF NOT EXISTS trg_audit_events_no_delete "
            "BEFORE DELETE ON audit_events "
            "FOR EACH ROW BEGIN "
            f"SELECT RAISE(ABORT, '{AUDIT_LOG_ERROR_MESSAGE}'); "
            "END;"
        ),
    ),
}


def install_audit_triggers(connection: Connection) -> None:
    """Install the append-only triggers on ``audit_events`` for the current dialect."""
    statements = AUDIT_TRIGGER_STATEMENTS.get(
        connection.dialect.name,
        AUDIT_TRIGGER_STATEMENTS["postgresql"],
    )
    for statement in statements:
        connection.execute(text(statement))
