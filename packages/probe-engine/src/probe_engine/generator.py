"""Probe generator — produces default configs and pytest files from configs.

The generator is what makes workflo work on "any Python repo, not just
one hardcoded example" (Claim #1). Given a repo URL, it produces a default
probe config tuned for a B2B SaaS API. The user can then tweak the YAML
without writing Python.
"""

from __future__ import annotations

from probe_engine.models import ProbeConfig, ProbeSpec


def _safe_test_name(name: str) -> str:
    """Turn a ProbeSpec.name into a valid pytest function name."""
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
    if safe and not safe[0].isalpha():
        safe = "probe_" + safe
    if not safe:
        safe = "probe_unnamed"
    if not safe.startswith("test_"):
        safe = "test_" + safe
    return safe


class ProbeGenerator:
    """Generate default probe configs and pytest test files."""

    # ============================================================
    # SECURITY PROBES (renamed from DEFAULT_API_PROBES)
    # ============================================================
    DEFAULT_SECURITY_PROBES = [
        ProbeSpec(
            name="cross_tenant_read_denied",
            pattern="api_read",
            path="/api/v1/projects",
            method="GET",
            expected_status=[403, 404],
            soc2_controls=["CC6.1", "CC6.6"],
            description="Cross-tenant resource read is denied",
        ),
        ProbeSpec(
            name="cross_tenant_list_excluded",
            pattern="api_list",
            path="/api/v1/projects",
            method="GET",
            list_key="projects",
            expect_resource_absent=True,
            expected_status=200,
            soc2_controls=["CC6.1", "CC6.6"],
            description="Cross-tenant resources excluded from list responses",
        ),
        ProbeSpec(
            name="cross_tenant_modify_denied",
            pattern="api_modify",
            path="/api/v1/projects",
            method="PUT",
            expected_status=[403, 404],
            soc2_controls=["CC6.1", "CC6.6"],
            description="Cross-tenant resource modification is denied",
        ),
        ProbeSpec(
            name="cross_tenant_delete_denied",
            pattern="api_delete",
            path="/api/v1/projects",
            method="DELETE",
            expected_status=[403, 404],
            soc2_controls=["CC6.1", "CC6.6"],
            description="Cross-tenant resource deletion is denied",
        ),
        ProbeSpec(
            name="positive_control_same_tenant",
            pattern="positive_control",
            path="/api/v1/projects",
            method="GET",
            expected_status=200,
            soc2_controls=["CC6.1"],
            description="Same-tenant access succeeds (validates the test itself)",
        ),
    ]

    # ============================================================
    # FUNCTIONAL PROBE GROUPS
    # ============================================================
    DEFAULT_SURFACE_PROBES = [
        ProbeSpec(
            name="native_pytest_suite",
            pattern="pytest_execution",
            path="/", method="EXEC",
            expected_status=0,
            soc2_controls=[],
            description="Execute repository's native pytest suite",
        ),
        ProbeSpec(
            name="import_smoke_test",
            pattern="import_check",
            path="/", method="EXEC",
            expected_status=0,
            soc2_controls=[],
            description="Verify package imports without errors",
        ),
        ProbeSpec(
            name="basic_api_reachability",
            pattern="api_reachability",
            path="/health", method="GET",
            expected_status=200,
            soc2_controls=[],
            description="Basic API endpoint reachability",
        ),
    ]

    DEFAULT_DEEP_PROBES = [
        *DEFAULT_SURFACE_PROBES,
        ProbeSpec(
            name="generated_contract_tests",
            pattern="contract_test",
            path="/api/v1", method="EXEC",
            expected_status=0,
            soc2_controls=[],
            description="LLM-generated OpenAPI contract tests (Phase 2+)",
        ),
        ProbeSpec(
            name="generated_edge_cases",
            pattern="edge_case",
            path="/", method="EXEC",
            expected_status=0,
            soc2_controls=[],
            description="LLM-generated edge case tests (Phase 2+)",
        ),
    ]

    DEFAULT_AGGRESSIVE_PROBES = [
        *DEFAULT_DEEP_PROBES,
        ProbeSpec(
            name="fuzz_testing",
            pattern="fuzz",
            path="/", method="EXEC",
            expected_status=0,
            soc2_controls=[],
            description="Property-based/fuzz testing (Phase 2+)",
        ),
        ProbeSpec(
            name="chaos_testing",
            pattern="chaos",
            path="/", method="EXEC",
            expected_status=0,
            soc2_controls=[],
            description="Chaos engineering probes (Phase 2+)",
        ),
    ]

    # Map probe group name -> list of ProbeSpec
    PROBE_GROUPS = {
        "surface": DEFAULT_SURFACE_PROBES,
        "deep": DEFAULT_DEEP_PROBES,
        "aggressive": DEFAULT_AGGRESSIVE_PROBES,
        "security": DEFAULT_SECURITY_PROBES,
    }

    @classmethod
    def default_config(cls, repo_url: str = "", groups: list[str] = None) -> ProbeConfig:
        """Generate a default probe config for an unknown repo.

        Args:
            repo_url: Git repository URL
            groups: List of probe group names. Valid: "surface", "deep",
                    "aggressive", "security". Default: ["surface", "security"].

        Returns:
            ProbeConfig with union of all probes from specified groups.
        """
        groups = groups or ["surface", "security"]
        all_probes = []
        for group in groups:
            all_probes.extend(cls.PROBE_GROUPS.get(group, []))
        return ProbeConfig(
            name="workflo-probes",
            version="1.0",
            probes=all_probes,
            metadata={"repo_url": repo_url, "groups": ",".join(groups)},
        )

    @classmethod
    def to_yaml_str(cls, config: ProbeConfig) -> str:
        """Serialize a ProbeConfig to YAML."""
        import yaml
        return yaml.dump(
            config.model_dump(mode="json"),
            sort_keys=False,
            default_flow_style=False,
        )

    @classmethod
    def from_yaml_str(cls, yaml_str: str) -> ProbeConfig:
        """Parse YAML into a ProbeConfig."""
        return ProbeConfig.from_yaml_str(yaml_str)

    @classmethod
    def generate_pytest_file(cls, config: ProbeConfig) -> str:
        """Generate a pytest file that drives ProbeRunner against a live API.

        Target base URL comes from WORKFLO_API_BASE_URL (set by the worker
        after booting the app-under-test via start_app_under_test). The
        generated file depends only on probe_engine + requests — both are
        already in the worker image — not the legacy workflo package.

        Without a reachable API, each probe test skips (fail-loud via skip
        reason), never silently passes. That is intentional: stub
        assert-True probes made the seeded-bug acceptance test meaningless.
        """
        probe_literals = ",\n".join(
            f"        {p.model_dump(mode='json')!r}" for p in config.probes
        )

        lines = [
            '"""Auto-generated by workflo probe engine — do not edit by hand.',
            "",
            f"Config: {config.name} (v{config.version})",
            'Source: ProbeGenerator.generate_pytest_file → ProbeRunner',
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "import os",
            "",
            "import pytest",
            "import requests",
            "",
            "from probe_engine import ProbeConfig, ProbeRunner, ProbeSpec",
            "",
            "",
            "class _ProbeHttpClient:",
            '    """Minimal client matching ProbeRunner\'s get/post/put/delete surface."""',
            "",
            "    def __init__(self, base_url: str, tenant_id: str, auth_token: str = \"mock-token\"):",
            "        self.base_url = base_url.rstrip(\"/\")",
            "        self.tenant_id = tenant_id",
            "        self.auth_token = auth_token",
            "",
            "    def _headers(self) -> dict:",
            "        return {",
            '            "X-Tenant-ID": self.tenant_id,',
            '            "Authorization": f"Bearer {self.auth_token}",',
            '            "Content-Type": "application/json",',
            "        }",
            "",
            "    def get(self, path: str):",
            '        return requests.get(f"{self.base_url}{path}", headers=self._headers(), timeout=10)',
            "",
            "    def post(self, path: str, json=None):",
            '        return requests.post(f"{self.base_url}{path}", json=json, headers=self._headers(), timeout=10)',
            "",
            "    def put(self, path: str, json=None):",
            '        return requests.put(f"{self.base_url}{path}", json=json, headers=self._headers(), timeout=10)',
            "",
            "    def delete(self, path: str):",
            '        return requests.delete(f"{self.base_url}{path}", headers=self._headers(), timeout=10)',
            "",
            "",
            "@pytest.fixture(scope=\"module\")",
            "def api_base_url():",
            '    url = os.environ.get("WORKFLO_API_BASE_URL", "").strip()',
            "    if not url:",
            "        pytest.skip(",
            '            "WORKFLO_API_BASE_URL unset — no app-under-test booted for ProbeRunner. "',
            '            "Reuse start_app_under_test (same primitive as --web) before expecting "',
            '            "probes to execute."',
            "        )",
            "    return url.rstrip(\"/\")",
            "",
            "",
            "@pytest.fixture",
            "def probe_config():",
            "    return ProbeConfig(",
            f"        name={config.name!r},",
            f"        version={config.version!r},",
            "        probes=[",
            f"{probe_literals}",
            "        ],",
            "    )",
            "",
            "",
            "@pytest.fixture",
            "def creator_client(api_base_url):",
            '    return _ProbeHttpClient(api_base_url, tenant_id="company1")',
            "",
            "",
            "@pytest.fixture",
            "def intruder_client(api_base_url):",
            '    return _ProbeHttpClient(api_base_url, tenant_id="company2")',
            "",
        ]

        for probe in config.probes:
            fn = _safe_test_name(probe.name)
            lines.extend([
                "",
                f"def {fn}(probe_config, creator_client, intruder_client):",
                f'    """{probe.description or probe.name}"""',
                "    runner = ProbeRunner(probe_config)",
                '    response = creator_client.post("/api/v1/projects", json={"name": "workflo-probe-resource"})',
                "    if response.status_code not in (200, 201):",
                "        pytest.skip(",
                '            f"Cannot create resource for probing "',
                '            f"(HTTP {response.status_code}) — app-under-test not probe-ready"',
                "        )",
                '    resource_id = response.json().get("id")',
                "    if not resource_id:",
                '        pytest.skip("Create response missing id — app-under-test not probe-ready")',
                "    try:",
                f"        result = runner.run_one({probe.name!r}, creator_client, intruder_client, resource_id)",
                "        assert result.passed, (",
                f'            f"Probe {probe.name!r} failed: status={{result.actual_status}} "',
                '            f"detail={{result.detail}} error={{result.error}}"',
                "        )",
                "    finally:",
                '        creator_client.delete(f"/api/v1/projects/{resource_id}")',
                "",
            ])

        return "\n".join(lines)
