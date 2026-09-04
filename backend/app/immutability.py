from sqlalchemy import text

TABLES = ("documents", "nav_records", "audit_events")


def install_guards(connection):
    """DB-level defence, not WORM storage or protection against DB superusers."""
    if connection.dialect.name == "postgresql":
        connection.execute(
            text(
                "CREATE OR REPLACE FUNCTION reject_evidence_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'append-only evidence cannot be updated or deleted'; END; $$"
            )
        )
        for table in TABLES:
            connection.execute(
                text(
                    f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_evidence_mutation()"
                )
            )
    elif connection.dialect.name == "sqlite":
        for table in TABLES:
            for action in ("UPDATE", "DELETE"):
                connection.execute(
                    text(
                        f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'append-only evidence'); END"
                    )
                )
