"""Programmatic tenant-isolation verification.

`verify_cross_tenant_access` performs read/list/modify/delete probes from an
intruder client against a resource that belongs to the creator tenant, plus a
positive control on the creator side. It returns a `VerificationSummary` with
one `VerificationRecord` per assertion so callers can assert, log, or feed the
records into an evidence report.
"""

from typing import Iterable, Optional, Sequence, Tuple

from workflo.isolation.patterns import IsolationPattern
from workflo.isolation.result import VerificationRecord, VerificationSummary


DENIAL_STATUSES = (403, 404)


def _push(record):
    from workflo.isolation import evidence
    try:
        evidence.add_record(record)
    except Exception:
        pass


def _tenants_of(creator_client, intruder_client) -> Tuple[str, str]:
    c = getattr(creator_client, "tenant_id", None) or "creator"
    i = getattr(intruder_client, "tenant_id", None) or "intruder"
    return c, i


def verify_read(intruder_client, resource_path, resource_id, expected_statuses=DENIAL_STATUSES):
    response = intruder_client.get(f"{resource_path}/{resource_id}")
    passed = response.status_code in expected_statuses
    record = VerificationRecord(
        pattern=IsolationPattern.API_READ.value,
        assertion=f"GET {resource_path}/{resource_id} -> {expected_statuses}",
        expected=list(expected_statuses),
        actual_status=response.status_code,
        passed=passed,
        tenant_pair=[_tenants_of(None, intruder_client)[1]],
        resource_id=resource_id,
        evidence={"soc2_controls": IsolationPattern.API_READ.soc2_controls},
    )
    return record


def verify_list_excludes(intruder_client, resource_path, resource_id, list_key="projects", expected_statuses=(200,)):
    response = intruder_client.get(resource_path)
    items = response.json().get(list_key, []) if response.status_code in expected_statuses and response.json() else []
    ids = [item.get("id") for item in items] if isinstance(items, list) else []
    leaked = resource_id in ids
    passed = not leaked
    record = VerificationRecord(
        pattern=IsolationPattern.API_LIST.value,
        assertion=f"GET {resource_path} excludes resource {resource_id} from {list_key}",
        expected=f"{resource_id} absent",
        actual_status=response.status_code,
        passed=passed,
        tenant_pair=[_tenants_of(None, intruder_client)[1]],
        resource_id=resource_id,
        evidence={"soc2_controls": IsolationPattern.API_LIST.soc2_controls, "leaked": leaked},
    )
    return record


def verify_modify_denied(intruder_client, resource_path, resource_id, payload=None, expected_statuses=DENIAL_STATUSES):
    response = intruder_client.put(
        f"{resource_path}/{resource_id}",
        json=payload or {"name": "SHOULD NOT PERSIST"},
    )
    passed = response.status_code in expected_statuses
    record = VerificationRecord(
        pattern=IsolationPattern.API_MODIFY.value,
        assertion=f"PUT {resource_path}/{resource_id} -> {expected_statuses}",
        expected=list(expected_statuses),
        actual_status=response.status_code,
        passed=passed,
        tenant_pair=[_tenants_of(None, intruder_client)[1]],
        resource_id=resource_id,
        evidence={"soc2_controls": IsolationPattern.API_MODIFY.soc2_controls},
    )
    return record


def verify_delete_denied(intruder_client, resource_path, resource_id, expected_statuses=DENIAL_STATUSES):
    response = intruder_client.delete(f"{resource_path}/{resource_id}")
    passed = response.status_code in expected_statuses
    record = VerificationRecord(
        pattern=IsolationPattern.API_DELETE.value,
        assertion=f"DELETE {resource_path}/{resource_id} -> {expected_statuses}",
        expected=list(expected_statuses),
        actual_status=response.status_code,
        passed=passed,
        tenant_pair=[_tenants_of(None, intruder_client)[1]],
        resource_id=resource_id,
        evidence={"soc2_controls": IsolationPattern.API_DELETE.soc2_controls},
    )
    return record


def verify_positive_control(creator_client, resource_path, resource_id, expected_status=200):
    response = creator_client.get(f"{resource_path}/{resource_id}")
    passed = response.status_code == expected_status
    record = VerificationRecord(
        pattern=IsolationPattern.POSITIVE_CONTROL.value,
        assertion=f"GET {resource_path}/{resource_id} -> {expected_status} (same-tenant)",
        expected=expected_status,
        actual_status=response.status_code,
        passed=passed,
        tenant_pair=[_tenants_of(creator_client, None)[0]],
        resource_id=resource_id,
        evidence={"soc2_controls": IsolationPattern.POSITIVE_CONTROL.soc2_controls},
    )
    return record


def verify_cross_tenant_access(
    creator_client,
    intruder_client,
    resource_id,
    *,
    resource_path="/api/v1/projects",
    list_key="projects",
    include: Optional[Iterable[str]] = None,
    expected_denial_statuses=DENIAL_STATUSES,
) -> VerificationSummary:
    """Probe all four cross-tenant access patterns plus a positive control.

    `include` optionally limits which patterns run (subset of:
    "read", "list", "modify", "delete", "positive").
    """
    creators = {"read", "list", "modify", "delete", "positive"}
    selected = set(include) & creators if include else creators

    c_tenant, i_tenant = _tenants_of(creator_client, intruder_client)
    summary = VerificationSummary(
        creator_tenant=c_tenant,
        intruder_tenant=i_tenant,
        resource_id=resource_id,
    )

    if "read" in selected:
        summary.records.append(verify_read(intruder_client, resource_path, resource_id, expected_denial_statuses))
    if "list" in selected:
        summary.records.append(verify_list_excludes(intruder_client, resource_path, resource_id, list_key))
    if "modify" in selected:
        summary.records.append(verify_modify_denied(intruder_client, resource_path, resource_id, expected_statuses=expected_denial_statuses))
    if "delete" in selected:
        summary.records.append(verify_delete_denied(intruder_client, resource_path, resource_id, expected_denial_statuses))
    if "positive" in selected:
        summary.records.append(verify_positive_control(creator_client, resource_path, resource_id))

    for r in summary.records:
        r.tenant_pair = [c_tenant, i_tenant]
        _push(r)

    return summary


def assert_summary(summary: VerificationSummary):
    """Raise AssertionError with a consolidated message if any record failed."""
    failures = [r for r in summary.records if not r.passed]
    if failures:
        lines = [f"  - {r.pattern}: {r.assertion} (got {r.actual_status})" for r in failures]
        raise AssertionError(
            f"Tenant isolation violated for resource {summary.resource_id} "
            f"({summary.creator_tenant} vs {summary.intruder_tenant}):\n" + "\n".join(lines)
        )
