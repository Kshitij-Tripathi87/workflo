"""Tenant isolation testing primitives.

Public API:
    IsolationPattern, IsolationScenario,
    verify_cross_tenant_access, assert_summary,
    VerificationRecord, VerificationSummary
"""

from workflo.isolation.patterns import IsolationPattern
from workflo.isolation.result import VerificationRecord, VerificationSummary
from workflo.isolation.scenario import IsolationScenario
from workflo.isolation.verifier import (
    assert_summary,
    verify_cross_tenant_access,
    verify_delete_denied,
    verify_list_excludes,
    verify_modify_denied,
    verify_positive_control,
    verify_read,
)

__all__ = [
    "IsolationPattern",
    "IsolationScenario",
    "VerificationRecord",
    "VerificationSummary",
    "verify_cross_tenant_access",
    "verify_read",
    "verify_list_excludes",
    "verify_modify_denied",
    "verify_delete_denied",
    "verify_positive_control",
    "assert_summary",
]
