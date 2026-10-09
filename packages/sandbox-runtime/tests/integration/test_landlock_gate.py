"""Landlock integration gate — real kernel enforcement (spec §5, LK-1..8).

Linux-only, runs under the linux/security gate alongside test_linux_gate.
These tests prove the sandbox is structurally incapable of touching
filesystem outside its policy — the rules are enforced BY THE KERNEL
inside the sandboxed process (irreversible, inherited by descendants).

Requires kernel with Landlock (5.13+); tests skip on older kernels —
hardened-mode failure on such kernels is separately covered by
test_compat_and_hardened_modes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from sandbox_runtime.config import BwrapConfig, NetworkMode, WorkloadType
from sandbox_runtime.landlock import probe_abi, rules_for_workload

pytestmark = pytest.mark.linux


def _require_linux():
    import sys
    if sys.platform != "linux":
        pytest.skip("Landlock gate is Linux-only")
    if os.geteuid() != 0:
        pytest.skip("namespace execution requires root on this host")
    if not Path("/opt/workflo/workflo-worker").exists():
        pytest.skip("runtime image missing - run scripts/linux/setup_env.sh")


@pytest.fixture(scope="module")
def landlocked_host():
    _require_linux()
    abi = probe_abi()
    if abi == 0:
        pytest.skip("kernel has no Landlock support (covered by compat tests)")
    return abi


def _config(tmp_path: Path, workload_type=WorkloadType.AGENT,
            mode="hardened", command=()):
    dirs = {}
    for name in ("workspace", "tmp", "home", "artifacts"):
        d = tmp_path / name
        d.mkdir()
        dirs[name] = d
    return BwrapConfig(
        sandbox_id=f"lk-{uuid.uuid4().hex[:8]}",
        workload_type=workload_type,
        readonly_root=Path("/opt/workflo/workflo-worker"),
        workspace_dir=dirs["workspace"],
        evidence_dir=dirs["artifacts"],
        tmp_dir=dirs["tmp"],
        home_dir=dirs["home"],
        network_mode=NetworkMode.NONE,
        landlock_rules=rules_for_workload(workload_type),
        landlock_mode=mode,
        command=list(command),
        env={"PATH": "/usr/bin:/bin", "HOME": "/home/workflo"},
    )


def _run_landlocked(config: BwrapConfig):
    """Spawn the Landlocked sandbox via the REAL spawn path."""
    import asyncio
    from sandbox_runtime.bwrap import run_bwrap

    proc = run_bwrap(config, capture=True)
    try:
        stdout, stderr = proc.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        pytest.fail("landlocked sandbox hung")
    return proc, stdout, stderr


class TestLandlockEnforcement:
    """LK-1..LK-7: hostile filesystem attempts are denied by the kernel."""

    def test_lk1_write_etc_denied(self, landlocked_host, tmp_path):
        config = _config(tmp_path, command=["/bin/sh", "-c",
            "echo hacked >> /etc/passwd && echo WROTE_ETC || echo DENIED_ETC"])
        proc, stdout, _ = _run_landlocked(config)
        assert b"DENIED_ETC" in stdout
        assert b"WROTE_ETC" not in stdout

    def test_lk2_proc_self_root_denied(self, landlocked_host, tmp_path):
        config = _config(tmp_path, command=["/bin/sh", "-c",
            "echo x >> /proc/self/root/etc/passwd 2>/dev/null "
            "&& echo WROTE_PROC_ROOT || echo DENIED_PROC_ROOT"])
        proc, stdout, _ = _run_landlocked(config)
        assert b"DENIED_PROC_ROOT" in stdout
        assert b"WROTE_PROC_ROOT" not in stdout

    def test_lk3_symlink_escape_denied(self, landlocked_host, tmp_path):
        config = _config(tmp_path, command=["/bin/sh", "-c",
            "ln -s /etc/shadow /workspace/link && cat /workspace/link "
            " 2>/dev/null && echo WROTE_LINK || echo DENIED_LINK"])
        proc, stdout, _ = _run_landlocked(config)
        assert b"DENIED_LINK" in stdout

    def test_lk4_mknod_outside_roots_denied(self, landlocked_host, tmp_path):
        config = _config(tmp_path, command=["/bin/sh", "-c",
            "mknod /etc/fake-node c 1 9 2>/dev/null && echo MADE_NODE "
            "|| echo DENIED_MKNOD"])
        proc, stdout, _ = _run_landlocked(config)
        assert b"DENIED_MKNOD" in stdout

    def test_lk5_traversal_denied(self, landlocked_host, tmp_path):
        config = _config(tmp_path, command=["/bin/sh", "-c",
            "cat /workspace/../../etc/hostname 2>/dev/null && echo READ_TRAV "
            "|| true; "
            "touch /workspace/../../evidence-should-not-be-here 2>/dev/null "
            "&& echo WROTE_TRAV || echo DENIED_TRAV"])
        proc, stdout, _ = _run_landlocked(config)
        # Reading /etc (RO) may succeed; WRITING outside roots must not
        assert b"WROTE_TRAV" not in stdout
        assert b"DENIED_TRAV" in stdout

    def test_lk7_ruleset_binds_grandchildren(self, landlocked_host, tmp_path):
        """A daemonizing child inherits the ruleset (Landlock cascade)."""
        config = _config(tmp_path, command=["/bin/sh", "-c",
            "(sleep 1; echo x >> /etc/passwd 2>/dev/null && "
            "echo CHILD_WROTE || echo CHILD_DENIED) & wait; "
            "echo PARENT_OK"])
        proc, stdout, _ = _run_landlocked(config)
        assert b"CHILD_DENIED" in stdout
        assert b"CHILD_WROTE" not in stdout

    def test_lk8_legitimate_writes_still_work(self, landlocked_host, tmp_path):
        """Over-restriction is a defect too: approved RW paths must work."""
        config = _config(tmp_path, workload_type=WorkloadType.AGENT,
                         command=["/bin/sh", "-c",
            "echo ok > /workspace/w.txt && echo ok2 > /tmp/t.txt && "
            "echo a3 > /workflo/artifacts/a.txt && echo OK_ALL || echo BLOCKED"])
        proc, stdout, _ = _run_landlocked(config)
        assert b"OK_ALL" in stdout, stdout

    def test_status_file_written_and_applied(self, landlocked_host, tmp_path):
        config = _config(tmp_path, command=["true"])
        proc, _, _ = _run_landlocked(config)
        status_path = Path(config.evidence_dir) / f"landlock-status-{config.workload_type.value}.json"
        assert status_path.exists(), "no landlock status file produced"
        status = json.loads(status_path.read_text())
        assert status["status"] == "LANDLOCK_APPLIED"
        assert status["abi"] >= 1


def _landlock_status(config: BwrapConfig) -> dict:
    """Read the in-sandbox Landlock status file for this config.

    The filename is derived from the workload tag exactly as bwrap.py derives
    it (``landlock-status-<workload_type.value>.json``). Hardcoding a suffix
    here once produced a path the sandbox never writes, which went unnoticed
    only because the test always skipped.
    """
    tag = config.workload_type.value.lower()
    status_path = Path(config.evidence_dir) / f"landlock-status-{tag}.json"
    assert status_path.exists(), f"no landlock status file at {status_path}"
    return json.loads(status_path.read_text())


class TestCompatAndHardenedModes:
    """Mode behavior across kernel capability (spec §5.3).

    These two tests used to force-skip whenever the host HAD Landlock. Every
    CI runner ships a 5.13+ kernel, so they skipped unconditionally: the Linux
    gate carried two permanent skips on a perfectly healthy environment, and
    the branch that actually applies to production kernels — hardened must
    ENFORCE, compatible must not silently DOWNGRADE — was asserted nowhere on
    real hardware. A skip is indistinguishable from "never verified", so both
    branches are now asserted for real and neither test opts out on capability.

    The only remaining skips are the platform/provisioning ones from
    ``_require_linux()``, which the gate treats as failures.
    """

    def test_hardened_mode_fails_closed_without_landlock(self, tmp_path):
        if sys.platform != "linux":
            pytest.skip("Landlock gate is Linux-only")
        _require_linux()
        abi = probe_abi()
        config = _config(tmp_path, mode="hardened", command=["/bin/sh", "-c",
            "echo WORKLOAD_EXECUTED"])
        proc, stdout, stderr = _run_landlocked(config)

        if abi > 0:
            # Capable kernel: hardened mode must ENFORCE and run the workload.
            # Refusing to exec here would be a self-inflicted outage; running
            # without applying Landlock would be the security defect.
            assert proc.returncode == 0, (
                f"hardened run failed on Landlock ABI {abi}: {stderr!r}")
            assert b"WORKLOAD_EXECUTED" in stdout
            status = _landlock_status(config)
            assert status["status"] == "LANDLOCK_APPLIED"
            assert status["abi"] == abi
            return

        # Incapable kernel: hardened mode must refuse BEFORE the workload execs.
        assert b"WORKLOAD_EXECUTED" not in stdout
        assert proc.returncode == 125

    def test_compatible_mode_records_downgrade(self, tmp_path):
        if sys.platform != "linux":
            pytest.skip("Landlock gate is Linux-only")
        _require_linux()
        abi = probe_abi()
        config = _config(tmp_path, mode="compatible", command=["true"])
        proc, _, stderr = _run_landlocked(config)
        assert proc.returncode == 0, f"compatible run failed: {stderr!r}"
        status = _landlock_status(config)

        if abi > 0:
            # "Compatible" must mean "tolerate older kernels", never "disable
            # enforcement when the kernel does support it".
            assert status["status"] == "LANDLOCK_APPLIED", (
                "compatible mode dropped Landlock on a capable kernel")
            assert status["abi"] == abi
        else:
            assert status["status"] == "UNSUPPORTED_KERNEL"
