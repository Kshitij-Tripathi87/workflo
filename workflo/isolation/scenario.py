"""Declarative tenant-isolation scenario.

Usage:

    with IsolationScenario(company1_client, company2_client) as scenario:
        scenario.assert_intruder_cannot_read()
        scenario.assert_intruder_cannot_list()
        scenario.assert_intruder_cannot_modify()
        scenario.assert_intruder_cannot_delete()
        scenario.assert_creator_can_access()

The scenario owns resource creation (via the creator client) and teardown, and
accumulates `VerificationRecord`s that downstream reporting can consume.
"""

from typing import Optional

from workflo.isolation import verifier
from workflo.isolation.patterns import IsolationPattern
from workflo.isolation.result import VerificationSummary


class IsolationScenario:
    def __init__(
        self,
        creator_client,
        intruder_client,
        *,
        resource_path="/api/v1/projects",
        list_key="projects",
        project_data=None,
        expected_denial_statuses=verifier.DENIAL_STATUSES,
    ):
        self.creator_client = creator_client
        self.intruder_client = intruder_client
        self.resource_path = resource_path
        self.list_key = list_key
        self.project_data = project_data
        self.expected_denial_statuses = expected_denial_statuses

        self.project_id: Optional[str] = None
        self._created = False
        self.summary: Optional[VerificationSummary] = None

    def __enter__(self):
        creator_tenant = getattr(self.creator_client, "tenant_id", "creator")
        data = self.project_data or _default_project_data(creator_tenant)
        response = self.creator_client.post(self.resource_path, json=data)
        response.raise_for_status()
        self.project_id = response.json()["id"]
        self._created = True

        intruder_tenant = "none"
        if self.intruder_client is not None:
            intruder_tenant = getattr(self.intruder_client, "tenant_id", "intruder")
        self.summary = VerificationSummary(
            creator_tenant=creator_tenant,
            intruder_tenant=intruder_tenant,
            resource_id=self.project_id,
        )
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._created and self.project_id:
            try:
                self.creator_client.delete(f"{self.resource_path}/{self.project_id}")
            except Exception:
                pass
        return False

    def _accumulate(self, record):
        creator_tenant = self.summary.creator_tenant
        intruder_tenant = self.summary.intruder_tenant
        from workflo.isolation.patterns import IsolationPattern
        if record.pattern == IsolationPattern.POSITIVE_CONTROL.value:
            record.tenant_pair = [creator_tenant]
        else:
            record.tenant_pair = [creator_tenant, intruder_tenant]
        self.summary.records.append(record)
        from workflo.isolation import evidence
        try:
            evidence.add_record(record)
        except Exception:
            pass
        return record

    def assert_intruder_cannot_read(self):
        record = verifier.verify_read(
            self.intruder_client, self.resource_path, self.project_id, self.expected_denial_statuses
        )
        self._accumulate(record)
        if not record.passed:
            raise AssertionError(
                f"Cross-tenant READ breach: intruder {self.summary.intruder_tenant} "
                f"got {record.actual_status} for resource {self.project_id}"
            )

    def assert_intruder_cannot_list(self):
        record = verifier.verify_list_excludes(
            self.intruder_client, self.resource_path, self.project_id, self.list_key
        )
        self._accumulate(record)
        if not record.passed:
            raise AssertionError(
                f"Cross-tenant LIST leak: {self.project_id} visible in "
                f"{self.summary.intruder_tenant}'s list"
            )

    def assert_intruder_cannot_modify(self):
        record = verifier.verify_modify_denied(
            self.intruder_client, self.resource_path, self.project_id, expected_statuses=self.expected_denial_statuses
        )
        self._accumulate(record)
        if not record.passed:
            raise AssertionError(
                f"Cross-tenant MODIFY breach: intruder {self.summary.intruder_tenant} "
                f"got {record.actual_status} for resource {self.project_id}"
            )

    def assert_intruder_cannot_delete(self):
        record = verifier.verify_delete_denied(
            self.intruder_client, self.resource_path, self.project_id, self.expected_denial_statuses
        )
        self._accumulate(record)
        if not record.passed:
            raise AssertionError(
                f"Cross-tenant DELETE breach: intruder {self.summary.intruder_tenant} "
                f"got {record.actual_status} for resource {self.project_id}"
            )
        still = self.creator_client.get(f"{self.resource_path}/{self.project_id}")
        assert still.status_code == 200, "Resource disappeared despite denied delete"

    def assert_creator_can_access(self):
        record = verifier.verify_positive_control(
            self.creator_client, self.resource_path, self.project_id
        )
        self._accumulate(record)
        if not record.passed:
            raise AssertionError(
                f"Positive control failed: creator {self.summary.creator_tenant} "
                f"could not read own resource {self.project_id} (got {record.actual_status})"
            )

    def assert_intruder_cannot_write(self):
        self.assert_intruder_cannot_modify()


def _default_project_data(tenant_id):
    from data.factories.project_factory import ProjectFactory
    return ProjectFactory.generate(tenant_id=tenant_id)
