"""Signing-key directory client — receipt provenance revocation checks.

A receipt that verifies cryptographically can still be worthless for
provenance if its signing key has been REVOKED (device lost, employee
departed, key compromised). The control plane's key directory
(``GET /v1/auth/keys/{key_id}``) publishes key status; this module lets a
verifier check it without trusting anything but the directory response.

Stdlib only — the verifier must stay dependency-light so it runs anywhere.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class KeyStatus:
    """Result of a key-directory lookup."""

    status: str  # "active" | "revoked" | "not_found" | "unreachable"
    detail: str = ""

    @property
    def is_revoked(self) -> bool:
        return self.status == "revoked"

    @property
    def is_usable(self) -> bool:
        return self.status == "active"


def check_key_status(
    directory_base_url: str,
    key_id: str,
    timeout: float = 5.0,
) -> KeyStatus:
    """Fetch the key's status from the provisioning directory.

    Non-200/404 network outcomes are reported, never raised: a verifier
    classifies "unreachable" differently from "revoked" (proof obligation
    unmet vs. proof of compromise).
    """
    base = directory_base_url.rstrip("/")
    url = f"{base}/v1/auth/keys/{key_id}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            payload = json.loads(resp.read(16 * 1024).decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return KeyStatus("not_found", f"key {key_id} is not registered")
        return KeyStatus("unreachable", f"directory returned HTTP {e.code}")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        return KeyStatus("unreachable", f"key directory unreachable: {type(e).__name__}")

    status = str(payload.get("status", "")).lower()
    if status == "active":
        return KeyStatus("active", "key is provisioned and active")
    if status == "revoked":
        return KeyStatus(
            "revoked",
            f"key revoked at {payload.get('revoked_at', 'unknown time')}",
        )
    return KeyStatus("unreachable", f"unrecognized directory status: {status!r}")
