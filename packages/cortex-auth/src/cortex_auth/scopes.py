"""Product-specific OAuth scope definitions.

Each Cortex product (workflo, astra, nexus) requests product-specific scopes
during the device authorization flow. Execution scopes are strictly separate
from viewer scopes: a CLI never receives ``nexus:execution:execute`` merely
because the user can view a Nexus workspace.
"""

from __future__ import annotations


WORKFLO_SCOPES: list[str] = [
    "openid",
    "profile",
    "offline_access",
    "workflo:runs:create",
    "workflo:runs:read",
    "workflo:receipts:read",
    "workflo:projects:read",
]


ASTRA_SCOPES: list[str] = [
    "openid",
    "profile",
    "offline_access",
    "astra:missions:create",
    "astra:missions:read",
    "astra:runs:create",
    "astra:reports:read",
]


NEXUS_SCOPES: list[str] = [
    "openid",
    "profile",
    "offline_access",
    "nexus:data:read",
    "nexus:simulation:create",
    "nexus:decisions:read",
    "nexus:approvals:write",
]


# Execution scopes are strictly separate and never granted to a CLI by
# default. They require additional vetting and are listed here for reference
# and audit.
NEXUS_EXECUTION_SCOPES: list[str] = [
    "nexus:execution:propose",
    "nexus:execution:approve",
    "nexus:execution:execute",
]


# Product -> default scopes mapping.
PRODUCT_SCOPES: dict[str, list[str]] = {
    "workflo": WORKFLO_SCOPES,
    "astra": ASTRA_SCOPES,
    "nexus": NEXUS_SCOPES,
}


# Product -> default OAuth client id.
PRODUCT_CLIENT_IDS: dict[str, str] = {
    "workflo": "workflo_cli",
    "astra": "astra_cli",
    "nexus": "nexus_cli",
}
