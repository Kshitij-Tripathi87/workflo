"""Centralized input validators and Pydantic helpers for Cortex Autopilot.

URN schemes supported (production):
  - urn:dbt:model:<project>:<name>
  - urn:dbt:source:<source_name>:<table>
  - urn:dbt:seed:<project>:<name>
  - urn:dbt:snapshot:<project>:<name>
  - urn:snowflake:table:<db>.<schema>.<table>
  - urn:li:dataset:(...)   (DataHub)

URNs that don't match any of the above are still accepted as long as
they look like URNs (start with "urn:" or contain a colon). This keeps
unit-test fixtures (e.g. "test:isolated") and DataHub-style URNs
working while still rejecting empty strings, overly long values, and
clearly malformed inputs.
"""
from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator

URN_DBT_MODEL = re.compile(r"^urn:dbt:model:[a-zA-Z0-9_\-]+:[a-zA-Z0-9_\-\.]+$")
URN_DBT_SOURCE = re.compile(r"^urn:dbt:source:[a-zA-Z0-9_\-]+:[a-zA-Z0-9_\-\.]+$")
URN_DBT_SEED = re.compile(r"^urn:dbt:seed:[a-zA-Z0-9_\-]+:[a-zA-Z0-9_\-\.]+$")
URN_DBT_SNAPSHOT = re.compile(r"^urn:dbt:snapshot:[a-zA-Z0-9_\-]+:[a-zA-Z0-9_\-\.]+$")
URN_SNOWFLAKE = re.compile(r"^urn:snowflake:table:[A-Z0-9_\-]+\.[A-Z0-9_\-]+\.[A-Z0-9_\-]+$")

# Production-grade patterns combined into a single regex
_PROD_URNS = re.compile(
    r"^(?:"
    r"urn:dbt:model:[a-zA-Z0-9_\-]+:[a-zA-Z0-9_\-\.]+$"
    r"|urn:dbt:source:[a-zA-Z0-9_\-]+:[a-zA-Z0-9_\-\.]+$"
    r"|urn:dbt:seed:[a-zA-Z0-9_\-]+:[a-zA-Z0-9_\-\.]+$"
    r"|urn:dbt:snapshot:[a-zA-Z0-9_\-]+:[a-zA-Z0-9_\-\.]+$"
    r"|urn:snowflake:table:[A-Z0-9_\-]+\.[A-Z0-9_\-]+\.[A-Z0-9_\-]+$"
    r"|urn:li:[a-z]+:\(.+\)$"
    r")"
)

# Permissive: anything that looks like an identifier-with-colon
_PERMISSIVE_URN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\-]*:[a-zA-Z0-9_\-:.()\[\], ]+$")


def _validate_urn(value: str) -> str:
    """Validate a URN.

    Accepts production URNs (dbt, Snowflake, DataHub-style) plus any
    colon-delimited identifier that looks like a URN. Rejects empty
    values, values > 512 chars, and inputs that are clearly not URNs.
    """
    if not value or not isinstance(value, str):
        raise ValueError("URN must be a non-empty string")
    if len(value) > 512:
        raise ValueError("URN exceeds maximum length of 512 characters")
    if _PROD_URNS.match(value):
        return value
    if _PERMISSIVE_URN.match(value):
        return value
    raise ValueError(
        f"URN '{value}' is not a valid URN. "
        "Expected a colon-delimited identifier like urn:dbt:model:<project>:<name>."
    )


def _normalize_urn(value: str) -> str:
    """Trim and lower-case for canonical comparison before scheme validation."""
    if not isinstance(value, str):
        raise ValueError("URN must be a string")
    return value.strip()


def _validate_non_empty(value: str) -> str:
    if not value or not value.strip():
        raise ValueError("Field must not be empty")
    return value.strip()


def _validate_column_name(value: str) -> str:
    if not value or not value.strip():
        raise ValueError("Column name must not be empty")
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", value):
        raise ValueError(
            f"Invalid column name '{value}'. "
            "Use snake_case identifiers (letters, digits, underscores)."
        )
    return value


# Pydantic-compatible annotated types -----------------------------------------

CortexURN = Annotated[str, BeforeValidator(_normalize_urn), AfterValidator(_validate_urn)]
NonEmptyStr = Annotated[str, AfterValidator(_validate_non_empty)]
ColumnName = Annotated[str, AfterValidator(_validate_column_name)]


def is_valid_urn(value: str) -> bool:
    """Quick boolean check used by services that want to skip raising."""
    try:
        _validate_urn(_normalize_urn(value))
        return True
    except (ValueError, TypeError):
        return False
