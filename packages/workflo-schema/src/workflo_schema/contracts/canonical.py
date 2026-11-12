"""Canonical JSON serialization and digest helpers (ADR-0016).

One profile for every hashed structure in the v1 contracts:

- RFC 8785 (JCS) subset: object keys sorted by code unit, no insignificant
  whitespace, UTF-8 strings without escaping of printable non-ASCII.
- Integers and strings only. Floating point is rejected: durations are
  integer milliseconds, sizes are integer bytes.
- Object keys must be ASCII (eliminates cross-language key-ordering
  ambiguity for supplementary characters).
- ``None`` serializes as ``null`` and is preserved; there is no "absent"
  representation in the canonical form.
- Strings must be valid Unicode (no lone surrogates).

Digests are self-describing: ``sha256:<64 lowercase hex>``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

DIGEST_PREFIX = "sha256:"


class CanonicalizationError(ValueError):
    """Raised when a value cannot be represented in canonical form."""


def _assert_encodable(value: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:  # lone surrogates etc.
        raise CanonicalizationError(f"string is not valid Unicode: {exc}") from exc


def _clean(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise CanonicalizationError(
            "floating point values are forbidden in canonical structures; "
            "use integers (with explicit units) or strings"
        )
    if isinstance(value, str):
        _assert_encodable(value)
        return value
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError("object keys must be strings")
            if not key.isascii():
                raise CanonicalizationError(
                    "object keys must be ASCII in canonical structures"
                )
            _assert_encodable(key)
            cleaned[key] = _clean(item)
        return cleaned
    raise CanonicalizationError(
        f"type {type(value).__name__} cannot be canonicalized"
    )


def canonical_json(value: Any) -> str:
    """Serialize ``value`` to the frozen canonical form."""
    cleaned = _clean(value)
    return json.dumps(
        cleaned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_bytes(value: Any) -> bytes:
    """Canonical UTF-8 bytes of ``value``."""
    return canonical_json(value).encode("utf-8")


def sha256_hex(data: bytes | str) -> str:
    """Bare lowercase hex SHA-256 of ``data``."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha256_digest(data: bytes | str) -> str:
    """Self-describing ``sha256:...`` digest of raw bytes."""
    return f"{DIGEST_PREFIX}{sha256_hex(data)}"


def digest_of(value: Any) -> str:
    """Self-describing digest over the canonical form of ``value``."""
    return sha256_digest(canonical_bytes(value))


def digest_matches(digest: str, value: Any) -> bool:
    """Whether ``digest`` equals the canonical digest of ``value``."""
    return digest == digest_of(value)


def model_canonical_dump(model: Any) -> Any:
    """Canonical-form dump of a Pydantic model (JSON mode, no floats)."""
    dump = model.model_dump(mode="json")
    return _clean(dump)


def model_digest(model: Any) -> str:
    """Self-describing digest over the canonical form of a model."""
    return digest_of(model_canonical_dump(model))
