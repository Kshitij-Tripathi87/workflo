"""Tests for the workflo probe engine — config-driven testing for any repo."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from probe_engine import (
    ProbeConfig,
    ProbeGenerator,
    ProbeResult,
    ProbeRunner,
    ProbeSpec,
    PROBE_GROUPS,
)


def _make_config(**overrides) -> ProbeConfig:
    defaults = {
        "name": "test-config",
        "probes": [
            ProbeSpec(
                name="read_denied",
                pattern="api_read",
                path="/api/v1/projects",
                method="GET",
                expected_status=[403, 404],
                soc2_controls=["CC6.1", "CC6.6"],
            ),
            ProbeSpec(
                name="list_excluded",
                pattern="api_list",
                path="/api/v1/projects",
                method="GET",
                list_key="projects",
                expect_resource_absent=True,
                expected_status=200,
                soc2_controls=["CC6.1"],
            ),
            ProbeSpec(
                name="positive",
                pattern="positive_control",
                path="/api/v1/projects",
                method="GET",
                expected_status=200,
                soc2_controls=["CC6.1"],
            ),
        ],
    }
    defaults.update(overrides)
    return ProbeConfig(**defaults)


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


class TestProbeConfig:
    def test_from_yaml_str(self):
        yaml_str = """
name: test
version: "1.0"
probes:
  - name: read_test
    pattern: api_read
    path: /api/v1/items
    method: GET
    expected_status: [403, 404]
    soc2_controls: [CC6.1]
"""
        config = ProbeConfig.from_yaml_str(yaml_str)
        assert config.name == "test"
        assert len(config.probes) == 1
        assert config.probes[0].name == "read_test"
        assert config.probes[0].pattern == "api_read"

    def test_expected_status_can_be_int_or_list(self):
        config = ProbeConfig(probes=[
            ProbeSpec(name="a", pattern="api_read", path="/x", expected_status=403),
            ProbeSpec(name="b", pattern="api_read", path="/x", expected_status=[403, 404]),
        ])
        assert config.probes[0].expected_status == 403
        assert config.probes[1].expected_status == [403, 404]


class TestProbeRunner:
    def test_run_all_success(self):
        """All probes pass when responses match expected statuses."""
        config = _make_config()
        runner = ProbeRunner(config)

        creator = MagicMock()
        intruder = MagicMock()

        creator.get.return_value = _mock_response(200, {"id": "proj-1"})

        def intruder_get(side_url):
            if side_url.endswith("proj-1"):
                return _mock_response(403)
            return _mock_response(200, {"projects": []})

        intruder.get.side_effect = intruder_get
        intruder.put.return_value = _mock_response(403)
        intruder.delete.return_value = _mock_response(403)

        summary = runner.run_all(creator, intruder, "proj-1")

        assert summary.total == 3
        assert summary.passed == 3
        assert summary.failed == 0

    def test_run_all_failed(self):
        """When a probe gets unexpected status, it fails."""
        config = _make_config()
        runner = ProbeRunner(config)

        creator = MagicMock()
        creator.get.return_value = _mock_response(200, {"id": "proj-1"})

        intruder = MagicMock()
        intruder.get.return_value = _mock_response(200, {"projects": []})

        summary = runner.run_all(creator, intruder, "proj-1")

        assert summary.total == 3
        assert summary.failed >= 1

    def test_run_all_collects_soc2_controls(self):
        config = _make_config()
        runner = ProbeRunner(config)

        creator = MagicMock()
        intruder = MagicMock()
        creator.get.return_value = _mock_response(200)
        intruder.get.return_value = _mock_response(403)
        intruder.put.return_value = _mock_response(403)
        intruder.delete.return_value = _mock_response(403)

        summary = runner.run_all(creator, intruder, "proj-1")

        assert "CC6.1" in summary.soc2_controls_covered
        assert "CC6.6" in summary.soc2_controls_covered

    def test_to_run_report_dict(self):
        config = _make_config()
        runner = ProbeRunner(config)
        summary = runner.run_all(
            MagicMock(), MagicMock(), "proj-1"
        )
        report = runner.to_run_report_dict(summary, sandbox_id="sandbox-1")
        assert report["sandbox_id"] == "sandbox-1"
        assert report["total"] == 3
        assert "CC6.1" in report["soc2_controls_covered"]


class TestProbeGenerator:
    def test_default_config_has_five_security_probes(self):
        config = ProbeGenerator.default_config("https://github.com/example/repo.git", groups=["security"])
        assert len(config.probes) == 5
        assert config.metadata["repo_url"] == "https://github.com/example/repo.git"
        names = [p.name for p in config.probes]
        assert "cross_tenant_read_denied" in names
        assert "positive_control_same_tenant" in names

    def test_surface_probes(self):
        config = ProbeGenerator.default_config(groups=["surface"])
        assert len(config.probes) == 3
        names = [p.name for p in config.probes]
        assert "native_pytest_suite" in names
        assert "import_smoke_test" in names
        assert "basic_api_reachability" in names

    def test_deep_probes_includes_surface(self):
        config = ProbeGenerator.default_config(groups=["deep"])
        # deep includes surface + 2 more
        assert len(config.probes) == 5
        names = [p.name for p in config.probes]
        assert "native_pytest_suite" in names
        assert "generated_contract_tests" in names
        assert "generated_edge_cases" in names

    def test_aggressive_probes_includes_deep(self):
        config = ProbeGenerator.default_config(groups=["aggressive"])
        # aggressive includes deep + 2 more = 7 total
        assert len(config.probes) == 7
        names = [p.name for p in config.probes]
        assert "fuzz_testing" in names
        assert "chaos_testing" in names

    def test_composable_groups(self):
        """Multiple groups produce union of all probes."""
        config = ProbeGenerator.default_config(groups=["surface", "security"])
        assert len(config.probes) == 8  # 3 surface + 5 security
        assert config.metadata["groups"] == "surface,security"

    def test_composable_deep_and_security(self):
        config = ProbeGenerator.default_config(groups=["deep", "security"])
        assert len(config.probes) == 10  # 5 deep + 5 security
        names = [p.name for p in config.probes]
        assert "cross_tenant_read_denied" in names
        assert "generated_contract_tests" in names

    def test_roundtrip_yaml(self):
        config = ProbeGenerator.default_config("https://example.com/repo.git", groups=["deep", "security"])
        yaml_str = ProbeGenerator.to_yaml_str(config)
        restored = ProbeGenerator.from_yaml_str(yaml_str)
        assert restored.name == config.name
        assert len(restored.probes) == len(config.probes)

    def test_generate_pytest_file_is_valid_python(self):
        config = ProbeGenerator.default_config(groups=["surface", "security"])
        test_file = ProbeGenerator.generate_pytest_file(config)
        assert "import pytest" in test_file
        assert "def test_" in test_file
        assert "ProbeRunner" in test_file
        assert "WORKFLO_API_BASE_URL" in test_file
        assert "workflo" not in test_file
        compile(test_file, "<generated>", "exec")

    def test_generated_pytest_has_one_test_per_probe(self):
        config = ProbeGenerator.default_config(groups=["surface", "security"])
        test_file = ProbeGenerator.generate_pytest_file(config)
        for probe in config.probes:
            assert f"def test_{probe.name}" in test_file

    def test_generated_pytest_uses_run_one_not_assert_true_stubs(self):
        config = ProbeGenerator.default_config(groups=["security"])
        test_file = ProbeGenerator.generate_pytest_file(config)
        assert "runner.run_one(" in test_file
        assert "assert True" not in test_file
        assert "pytest.skip(" in test_file

    def test_probe_groups_constant(self):
        """PROBE_GROUPS dict contains all expected groups."""
        assert "surface" in PROBE_GROUPS
        assert "deep" in PROBE_GROUPS
        assert "aggressive" in PROBE_GROUPS
        assert "security" in PROBE_GROUPS
        assert len(PROBE_GROUPS["surface"]) == 3
        assert len(PROBE_GROUPS["deep"]) == 5
        assert len(PROBE_GROUPS["aggressive"]) == 7
        assert len(PROBE_GROUPS["security"]) == 5

    def test_default_surface_probes_constant(self):
        assert len(ProbeGenerator.DEFAULT_SURFACE_PROBES) == 3
        names = [p.name for p in ProbeGenerator.DEFAULT_SURFACE_PROBES]
        assert "native_pytest_suite" in names
        assert "import_smoke_test" in names
        assert "basic_api_reachability" in names

    def test_default_deep_probes_constant(self):
        assert len(ProbeGenerator.DEFAULT_DEEP_PROBES) == 5

    def test_default_aggressive_probes_constant(self):
        assert len(ProbeGenerator.DEFAULT_AGGRESSIVE_PROBES) == 7

    def test_default_security_probes_constant(self):
        assert len(ProbeGenerator.DEFAULT_SECURITY_PROBES) == 5
        names = [p.name for p in ProbeGenerator.DEFAULT_SECURITY_PROBES]
        assert "cross_tenant_read_denied" in names
        assert "positive_control_same_tenant" in names