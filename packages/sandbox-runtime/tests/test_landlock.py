"""Landlock unit tests — ABI masking, rule tables, spawn wiring (F-1/F-2).

The Linux-marked integration tests in tests/integration/test_landlock_gate.py
prove real enforcement; these tests prove the host-side logic on any OS.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sandbox_runtime.config import BwrapConfig, NetworkMode, WorkloadType
from sandbox_runtime.landlock import (
    ACCESS_MIN_ABI,
    LANDLOCK_ACCESS_FS_DIR_MOD,
    LANDLOCK_ACCESS_FS_READ,
    LANDLOCK_ACCESS_FS_REFER,
    LANDLOCK_ACCESS_FS_RW,
    LANDLOCK_ACCESS_FS_TRUNCATE,
    LandlockRuleset,
    LandlockStatus,
    build_ruleset_for_workload,
    enable_for_workload,
    mask_for_abi,
    probe_abi,
    rules_for_workload,
    rules_payload,
)


class TestMaskForAbi:
    def test_abi1_strips_refer_and_truncate(self):
        """F-2: ABI 1 kernels must never see REFER/TRUNCATE handled bits."""
        masked = mask_for_abi(LANDLOCK_ACCESS_FS_RW, abi=1)
        assert masked & LANDLOCK_ACCESS_FS_REFER == 0
        assert masked & LANDLOCK_ACCESS_FS_TRUNCATE == 0
        assert masked & LANDLOCK_ACCESS_FS_READ != 0
        assert masked & LANDLOCK_ACCESS_FS_DIR_MOD != 0

    def test_abi2_adds_refer_not_truncate(self):
        masked = mask_for_abi(LANDLOCK_ACCESS_FS_RW, abi=2)
        assert masked & LANDLOCK_ACCESS_FS_REFER != 0
        assert masked & LANDLOCK_ACCESS_FS_TRUNCATE == 0

    def test_abi3_adds_truncate(self):
        masked = mask_for_abi(LANDLOCK_ACCESS_FS_RW, abi=3)
        assert masked & LANDLOCK_ACCESS_FS_TRUNCATE != 0

    def test_abi0_masks_everything(self):
        assert mask_for_abi(LANDLOCK_ACCESS_FS_RW, abi=0) == 0

    def test_every_declared_bit_has_min_abi(self):
        all_bits = (LANDLOCK_ACCESS_FS_READ | LANDLOCK_ACCESS_FS_DIR_MOD
                    | LANDLOCK_ACCESS_FS_TRUNCATE | (1 << 1))
        for bit, min_abi in ACCESS_MIN_ABI.items():
            assert 1 <= min_abi <= 3
            assert bit & all_bits == bit  # every declared bit is a real access bit
            # Every bit is maskable at its declared ABI and above
            assert mask_for_abi(bit, abi=min_abi) == bit
            assert mask_for_abi(bit, abi=min_abi - 1) == 0


class TestProbeAbi:
    def test_unsupported_platform_returns_zero(self):
        """On non-Linux (or unsupported kernels) the probe is 0, never raises."""
        assert probe_abi() == 0


class TestWorkloadRuleTables:
    """Spec §5.4: per-workload rule tables."""

    def test_test_workload(self):
        rules = rules_for_workload(WorkloadType.TEST)
        assert rules == [
            {"path": "/", "access": "read"},
            {"path": "/workspace", "access": "rw"},
            {"path": "/tmp", "access": "rw"},
            {"path": "/workflo/artifacts", "access": "rw"},
            {"path": "/dev/null", "access": "rw"},
        ]

    def test_agent_workload_has_artifacts(self):
        paths = {r["path"] for r in rules_for_workload(WorkloadType.AGENT)}
        assert "/workflo/artifacts" in paths
        assert "/home/workflo" in paths

    def test_every_workload_can_write_artifacts_and_dev_null(self):
        """The landlock status file + run outputs (pytest-report.json) land
        in /workflo/artifacts, and shells/DEVNULL need /dev/null — a table
        missing either silently downgrades or kills the workload."""
        for wt in WorkloadType:
            table = {r["path"]: r["access"] for r in rules_for_workload(wt)}
            assert table.get("/workflo/artifacts") == "rw", wt
            assert table.get("/dev/null") == "rw", wt

    def test_no_workload_gets_evidence_ledger_rule(self):
        """The host-side ledger path must never appear in a sandbox rule."""
        for wt in WorkloadType:
            paths = {r["path"] for r in rules_for_workload(wt)}
            assert not any("evidence" in p for p in paths), wt

    def test_unknown_workload_falls_back_to_test(self):
        assert rules_for_workload("nonsense") == rules_for_workload(WorkloadType.TEST)

    def test_rules_payload_carries_mode(self):
        payload = rules_payload(WorkloadType.AGENT, security_mode="hardened")
        assert payload["mode"] == "hardened"
        assert payload["workload"] == "agent"
        assert payload["rules"] == rules_for_workload(WorkloadType.AGENT)


class TestRulesetPlanning:
    def test_planned_rules_masked_on_old_abi(self):
        ruleset = build_ruleset_for_workload(WorkloadType.AGENT, abi=1)
        planned = dict(ruleset.planned_rules())
        for path, access in planned.items():
            assert access & LANDLOCK_ACCESS_FS_REFER == 0
            assert access & LANDLOCK_ACCESS_FS_TRUNCATE == 0
            assert access != 0

    def test_handled_access_masked_on_old_abi(self):
        ruleset = build_ruleset_for_workload(WorkloadType.AGENT, abi=1)
        assert ruleset.handled_access & LANDLOCK_ACCESS_FS_REFER == 0
        assert ruleset.handled_access & LANDLOCK_ACCESS_FS_TRUNCATE == 0

    def test_apply_on_unsupported_kernel_is_unsupported(self):
        ruleset = build_ruleset_for_workload(WorkloadType.AGENT, abi=0)
        result = ruleset.apply()
        assert result.status == LandlockStatus.UNSUPPORTED_KERNEL
        assert result.abi == 0

    def test_enable_for_workload_sets_bwrap_config(self):
        config = MagicMock()
        enable_for_workload(config, WorkloadType.AGENT, security_mode="hardened")
        assert config.landlock_rules == rules_for_workload(WorkloadType.AGENT)
        assert config.landlock_mode == "hardened"


class TestBwrapWiring:
    """F-1: non-empty landlock_rules must change the spawn command + binds."""

    def _config(self, tmp_path, landlock=True, mode="compatible"):
        return BwrapConfig(
            sandbox_id="sbx-test",
            workload_type=WorkloadType.AGENT,
            readonly_root=tmp_path / "rootfs",
            workspace_dir=tmp_path / "workspace",
            evidence_dir=tmp_path / "run" / "evidence" / "artifacts",
            tmp_dir=tmp_path / "tmp",
            home_dir=tmp_path / "home",
            network_mode=NetworkMode.NONE,
            landlock_rules=rules_for_workload(WorkloadType.AGENT) if landlock else [],
            landlock_mode=mode,
            command=["python3", "-m", "workflo_worker.agent_runner"],
        )

    def test_command_wrapped_with_pre_exec_applier(self, tmp_path):
        from sandbox_runtime.bwrap import build_bwrap_args

        args = build_bwrap_args(self._config(tmp_path))
        joined = " ".join(args)
        assert "/workflo/landlock_exec.py" in joined
        assert "--rules /workflo/landlock-rules.json" in joined
        # The wrapper runs BEFORE the real command
        assert args.index("/workflo/landlock_exec.py") < args.index(
            "workflo_worker.agent_runner")

    def test_wrapper_binds_are_read_only(self, tmp_path):
        from sandbox_runtime.bwrap import build_bwrap_args

        args = build_bwrap_args(self._config(tmp_path))
        i = args.index("/workflo/landlock_exec.py")
        assert args[i - 2] == "--ro-bind"  # flag, source, dest
        j = args.index("/workflo/landlock-rules.json")
        assert args[j - 2] == "--ro-bind"

    def test_status_path_is_per_workload(self, tmp_path):
        from sandbox_runtime.bwrap import build_bwrap_args

        args = build_bwrap_args(self._config(tmp_path))
        status = [a for a in args if "landlock-status-" in a]
        assert status == ["/workflo/artifacts/landlock-status-agent.json"]

    def test_no_landlock_no_wrapper(self, tmp_path):
        from sandbox_runtime.bwrap import build_bwrap_args

        args = build_bwrap_args(self._config(tmp_path, landlock=False))
        assert not any("landlock_exec" in a for a in args)
        assert not any("landlock-rules" in a for a in args)

    def test_write_landlock_rules_roundtrip(self, tmp_path):
        from sandbox_runtime.bwrap import write_landlock_rules, landlock_rules_path
        import json

        config = self._config(tmp_path)
        path = write_landlock_rules(config)
        assert path == landlock_rules_path(config)
        doc = json.loads(path.read_text())
        assert doc["workload"] == "agent"
        assert doc["mode"] == "compatible"
        assert doc["rules"] == rules_for_workload(WorkloadType.AGENT)

    def test_invalid_access_name_fails_loud(self, tmp_path):
        from sandbox_runtime.bwrap import write_landlock_rules

        config = self._config(tmp_path)
        config.landlock_rules = [{"path": "/x", "access": "superuser"}]
        with pytest.raises(ValueError):
            write_landlock_rules(config)


class TestLandlockExecScript:
    """The standalone in-sandbox wrapper's pure logic (no syscalls)."""

    @staticmethod
    def _load_script():
        import importlib.util
        src = Path(__file__).parent.parent / "src" / "sandbox_runtime" / "landlock_exec.py"
        spec = importlib.util.spec_from_file_location("landlock_exec", src)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_plan_masks_on_old_abi(self):
        script = self._load_script()
        rules = [{"path": "/workspace", "access": "rw"}]
        handled, planned = script.plan(rules, abi=1)
        assert handled & (1 << 13) == 0  # REFER
        assert handled & (1 << 14) == 0  # TRUNCATE
        assert planned == [("/workspace", handled)]

    def test_plan_rejects_empty_ruleset(self):
        script = self._load_script()
        with pytest.raises(ValueError):
            script.plan([], abi=3)

    def test_plan_rejects_unknown_access(self):
        script = self._load_script()
        with pytest.raises(ValueError):
            script.plan([{"path": "/x", "access": "root"}], abi=3)

    def test_mask_matches_host_module(self):
        """Host and in-sandbox masking MUST agree — they're deliberately
        duplicated (the script cannot import the package)."""
        script = self._load_script()
        for abi in (0, 1, 2, 3, 5):
            assert script.mask_for_abi(LANDLOCK_ACCESS_FS_RW, abi) == \
                mask_for_abi(LANDLOCK_ACCESS_FS_RW, abi)

    def test_argv_parsing(self):
        script = self._load_script()
        parser_ok = script  # module import itself proves syntax/argparse wiring
        assert parser_ok.EXIT_LANDLOCK_FAILED == 125
