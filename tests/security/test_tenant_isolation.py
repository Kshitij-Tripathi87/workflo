"""
Security Tests: Tenant Isolation

These tests verify that data belonging to one tenant cannot be
accessed by another tenant. This is a critical security boundary
for any B2B SaaS platform.

Each test asserts exactly one IsolationPattern so the SOC 2 evidence
report can show one row per control. Resource setup and teardown are
owned by IsolationScenario.
"""

import os
import pytest
from workflo.api.client import APIClient
from workflo.isolation import IsolationScenario


@pytest.fixture(scope="function")
def company1_client(env_config):
    return APIClient(
        base_url=env_config.api_url,
        tenant_id="company1",
        auth_token=os.getenv("COMPANY1_TOKEN", "mock-token"),
    )


@pytest.fixture(scope="function")
def company2_client(env_config):
    return APIClient(
        base_url=env_config.api_url,
        tenant_id="company2",
        auth_token=os.getenv("COMPANY2_TOKEN", "mock-token"),
    )


@pytest.mark.security
class TestTenantIsolation:

    def test_company_cannot_access_other_company_project(
        self, company1_client, company2_client
    ):
        """Company1 creates a project; Company2 must not be able to read it."""
        with IsolationScenario(company1_client, company2_client) as scenario:
            scenario.assert_intruder_cannot_read()

    def test_company_cannot_list_other_company_projects(
        self, company1_client, company2_client
    ):
        """Company1 creates a project; Company2's list must not include it."""
        with IsolationScenario(company1_client, company2_client) as scenario:
            scenario.assert_intruder_cannot_list()

    def test_company_cannot_modify_other_company_project(
        self, company1_client, company2_client
    ):
        """Company2 must not be able to update Company1's project."""
        with IsolationScenario(company1_client, company2_client) as scenario:
            scenario.assert_intruder_cannot_modify()

    def test_company_cannot_delete_other_company_project(
        self, company1_client, company2_client
    ):
        """Company2 must not be able to delete Company1's project."""
        with IsolationScenario(company1_client, company2_client) as scenario:
            scenario.assert_intruder_cannot_delete()

    def test_same_company_can_access_own_project(self, company1_client):
        """Positive control: Same tenant must be able to access own data."""
        with IsolationScenario(company1_client, intruder_client=None) as scenario:
            scenario.assert_creator_can_access()
