"""Shared constrained types for the frozen v1 contracts.

Conventions fixed by ADR-0016:

- Timestamps are canonical strings: ISO-8601 UTC, millisecond precision,
  ``YYYY-MM-DDTHH:MM:SS.mmmZ``. They are stored as strings so that the
  canonical serialization is unambiguous across languages.
- Digests are self-describing: ``sha256:<64 lowercase hex>``.
- Identifiers are opaque strings (max 128 chars) matching a conservative
  charset; existing UUIDs and ``run_...``-style ids are both valid.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import Field

SCHEMA_VERSION: str = "1"

TIMESTAMP_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
SHA256_HEX_PATTERN = r"^[0-9a-f]{64}$"
RELATIVE_PATH_PATTERN = r"^[A-Za-z0-9._/-]{1,512}$"
MEDIA_TYPE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,63}/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,63}$"

CanonicalTimestamp = Annotated[str, Field(pattern=TIMESTAMP_PATTERN)]
IdString = Annotated[str, Field(pattern=ID_PATTERN)]
DigestString = Annotated[str, Field(pattern=DIGEST_PATTERN)]
Sha256Hex = Annotated[str, Field(pattern=SHA256_HEX_PATTERN)]


def format_utc_ms(dt: datetime) -> str:
    """Format an aware datetime as the canonical millisecond UTC string."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("timestamp must be timezone-aware")
    dt = dt.astimezone(timezone.utc)
    return (
        f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"
        f"T{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"
        f".{dt.microsecond // 1000:03d}Z"
    )


def utc_now_ms() -> str:
    """Current time as the canonical millisecond UTC string."""
    return format_utc_ms(datetime.now(timezone.utc))
