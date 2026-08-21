"""`workflo init` scaffolding.

Generates a starter `workflo.yaml`, an `adapters.yaml`, and a first
isolation test that exercises the API denial patterns against the user's own
tenant-aware API. Designed so a new user can go from `pip install` to a green
test in minutes.
"""

import argparse
import os
import sys


WORKFLO_YAML = """\
# workflo configuration
suite: tenant-isolation
# API base URL for the system under test
api_base_url: "http://localhost:8000"
# Default tenant under test
tenant_id: "company1"
# Tenant against which isolation is asserted
intruder_tenant_id: "company2"
# Resource path the scenario will create/probe
resource_path: "/api/v1/projects"
# JSON key under which a list response returns items
list_key: "projects"
"""

ADAPTERS_YAML = """\
# Tenant identity + auth adapters
tenant_resolver: "header"
tenant_resolver_config:
  header_name: "X-Tenant-ID"

auth_provider: "bearer"
auth_provider_config:
  token_env_var: "API_AUTH_TOKEN"
"""

SAMPLE_TEST = '''\
"""workflo: generated isolation test (API denial patterns).

Edit the config below to match your API, then run:
    workflo run tests/test_tenant_isolation_generated.py --output-json reports/results.json
    workflo report --results reports/results.json
"""

import os
import pytest
from workflo.api.client import APIClient
from workflo.isolation import IsolationScenario


@pytest.mark.security
def test_cross_tenant_access_is_denied():
    base = os.getenv("API_BASE_URL", "http://localhost:8000")
    creator = APIClient(
        base_url=base,
        tenant_id=os.getenv("TENANT_ID", "company1"),
        auth_token=os.getenv("API_AUTH_TOKEN", "mock-token"),
    )
    intruder = APIClient(
        base_url=base,
        tenant_id=os.getenv("INTRUDER_TENANT_ID", "company2"),
        auth_token=os.getenv("INTRUDER_TOKEN", os.getenv("API_AUTH_TOKEN", "mock-token")),
    )

    with IsolationScenario(creator, intruder) as scenario:
        scenario.assert_intruder_cannot_read()
        scenario.assert_intruder_cannot_list()
        scenario.assert_intruder_cannot_modify()
        scenario.assert_intruder_cannot_delete()
        scenario.assert_creator_can_access()
'''


def init_project(target_dir=".", force=False):
    os.makedirs(target_dir, exist_ok=True)
    written = []
    specs = [
        ("workflo.yaml", TENANT_SHIELD_YAML),
        ("adapters.yaml", ADAPTERS_YAML),
        ("tests/test_tenant_isolation_generated.py", SAMPLE_TEST),
    ]
    for rel, content in specs:
        path = os.path.join(target_dir, rel)
        if os.path.exists(path) and not force:
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(path)
    return written


def from_cli(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(prog="workflo init", description="Scaffold a workflo config and first test.")
    parser.add_argument("--dir", "-d", default=".", help="Target directory (default: current).")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files.")
    args = parser.parse_args(argv)

    written = init_project(args.dir, force=args.force)
    if written:
        print("Created:")
        for p in written:
            print("  " + p)
        print("\nNext:\n  pip install workflo playwright && playwright install chromium")
        print("  workflo run tests/test_tenant_isolation_generated.py --output-json reports/results.json")
        print("  workflo report --results reports/results.json")
    else:
        print("Nothing to write (files exist; use --force to overwrite).")
    return 0


if __name__ == "__main__":
    sys.exit(from_cli())
