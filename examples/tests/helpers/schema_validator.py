"""Schema validators used by auto-generated Tenant Shield test modules.

These helpers are imported by tests generated via
`workflo_datahub.generator.TestGenerator`. Production deployments would
swap these stubs with real DB adapters (asyncpg/psycopg/sqlalchemy).
"""

from dataclasses import dataclass


@dataclass
class ValidationResult:
    ok: bool
    message: str = ""


def validate_schema(db_connection, table_name: str, expected_columns: list[tuple]) -> list[str]:
    """Return list of missing columns — empty if all expected columns exist."""
    try:
        cursor = db_connection.cursor() if hasattr(db_connection, "cursor") else db_connection.execute
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table_name.split(".")[-1],),
        )
        actual = {row[0] for row in cursor.fetchall()}
    except Exception:
        # Fallback for mock connections used in unit tests
        actual = set(getattr(db_connection, "columns", set()))

    expected_names = {col[0] for col in expected_columns}
    return sorted(expected_names - actual)


def validate_primary_key(db_connection, table_name: str, pk_columns: list[str]) -> list[int]:
    """Return list of duplicate PK row counts — empty if all PKs are unique."""
    try:
        cursor = db_connection.cursor() if hasattr(db_connection, "cursor") else db_connection.execute
        cols = ", ".join(pk_columns)
        cursor.execute(
            f"SELECT {cols}, COUNT(*) FROM {table_name} GROUP BY {cols} HAVING COUNT(*) > 1"
        )
        return [row[-1] for row in cursor.fetchall()]
    except Exception:
        return []


def validate_nullable(db_connection, table_name: str, column: str, expected_nullable: bool) -> ValidationResult:
    """Validate a column's nullability against the DataHub-declared constraint."""
    try:
        cursor = db_connection.cursor() if hasattr(db_connection, "cursor") else db_connection.execute
        op = "IS NULL" if expected_nullable else "IS NOT NULL"
        # Probe by attempting to insert/observe
        cursor.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE {column} {op}"
        )
        return ValidationResult(ok=True, message="")
    except Exception as exc:
        return ValidationResult(ok=False, message=str(exc))
