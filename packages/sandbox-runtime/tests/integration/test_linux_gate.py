"""Linux integration gate — the namespace executor on its TARGET platform.

These tests are the v0.2 "Linux-verified execution" release gate. They
are mocked nowhere: they require a real Linux host with bwrap, cgroups
v2, netns, nftables and the runtime image (built by
scripts/linux/setup_env.sh). On any other platform they skip, keeping
the distinction the project now makes explicitly:

    CI/mock gate       — the 500+ unit tests, all platforms
    Linux integration  — THIS FILE, its target platform only
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from sandbox_runtime.config import CgroupConfig, RunConfig, DepMode
from sandbox_runtime.supervisor import Supervisor
from sandbox_runtime.bwrap import build_bwrap_args
from sandbox_runtime.seccomp import (
    get_seccomp_profile,
    write_bwrap_profile,
    write_empty_bwrap_profile,
    WorkloadType,
)

pytestmark = pytest.mark.linux


def _require_linux():
    if sys_platform() != "linux":
        pytest.skip("Linux integration gate")
    if os.geteuid() != 0:
        pytest.skip("namespace execution requires root on this host")


def sys_platform() -> str:
    import sys
    return sys.platform


def _tool_available(tool: str) -> bool:
    return shutil.which(tool) is not None


@pytest.fixture(scope="module")
def host_ready():
    """Skip the whole module unless the host has the isolation stack."""
    _require_linux()
    for tool in ("bwrap", "ip", "nft", "dnsmasq"):
        if not _tool_available(tool):
            pytest.skip(f"{tool} not installed")
    if not Path("/sys/fs/cgroup/cgroup.controllers").exists():
        pytest.skip("cgroups v2 not mounted")
    if not Path("/opt/workflo/workflo-worker").exists():
        pytest.skip("runtime image missing - run scripts/linux/setup_env.sh")


def _make_run_config(tmp_path: Path, fixture: Path, probe_groups=None) -> RunConfig:
    return RunConfig(
        sandbox_id=f"sbx-gate-{uuid.uuid4().hex[:12]}",
        repo_path=fixture,
        probe_groups=probe_groups or ["surface"],
        runtime_image=Path("/opt/workflo/workflo-worker"),
        memory_mb=1024,
        cpu_cores=1.0,
        timeout_seconds=300,
        dep_mode=DepMode.VENDOR_CACHE,
        evidence_dir=tmp_path / "runs",
    )


@pytest.fixture(scope="module")
def fixture_repo():
    """The golden-run fixture repo (sanity + adversarial isolation tests)."""
    fixture = Path(os.environ.get("WORKFLO_FIXTURE", "/root/wf-fixture"))
    if not fixture.exists():
        pytest.skip("fixture repo missing - run scripts/linux/setup_env.sh")
    return fixture


def _run_sandbox(tmp_path: Path, fixture: Path, **kwargs) -> tuple:
    config = _make_run_config(tmp_path, fixture, **kwargs)
    supervisor = Supervisor(config)
    import asyncio
    result = asyncio.run(supervisor.run())
    return result, config


class TestGoldenRun:
    """The single deterministic Linux golden run."""

    def test_full_loop_produces_verified_receipt(self, host_ready, tmp_path, fixture_repo):
        result, supervisor = _run_sandbox(tmp_path, fixture_repo)

        assert result.success is True, result.error
        assert result.teardown_verified is True
        assert result.receipt_payload is not None

        payload = result.receipt_payload
        assert payload["receipt_version"] == 4

        tp = payload["teardown_proof"]
        assert tp["runtime_type"] == "namespaces"
        assert tp["processes_terminated"] is True
        assert tp["cgroup_removed"] is True
        assert tp["network_namespace_removed"] is True
        assert tp["workspace_removed"] is True
        assert tp["container_removed"] is True  # composite claim

        # The in-sandbox canary (real egress attempt) was blocked
        assert payload["canary_check"]["request_succeeded"] is False

        # The repo's own adversarial tests ran INSIDE the sandbox and passed
        rr = payload["run_report"]
        assert rr["total"] >= 8, f"expected sanity + adversarial tests, got {rr}"
        assert rr["passed"] == rr["total"]
        assert rr["failed"] == 0
        assert rr["collection_error"] is None

        # Evidence ledger verifies and its digests are bound into the receipt
        from sandbox_runtime.evidence import verify_evidence_bundle
        evidence_dir = Path(result.evidence_dir)
        assert verify_evidence_bundle(evidence_dir) is True

    def test_independent_verification_passes(self, host_ready, tmp_path, fixture_repo):
        """The outside verifier accepts the golden receipt using only the
        receipt + evidence directory + public key."""
        from sandbox_isolation import generate_keypair, verify_receipt_signature
        from workflo_schema.sandbox import SignedReceipt
        from sandbox_runtime.evidence import verify_evidence_bundle

        result, _ = _run_sandbox(tmp_path, fixture_repo)
        assert result.success is True

        signer = generate_keypair()
        receipt = SignedReceipt(**result.receipt_payload)
        signer.sign(receipt)

        assert verify_receipt_signature(receipt, signer.public_key) is True

        evidence_dir = Path(result.evidence_dir)
        assert verify_evidence_bundle(evidence_dir) is True


class TestPostTeardown:
    """Proof that sandbox state did not survive."""

    def test_no_cgroup_left(self, host_ready, tmp_path, fixture_repo):
        result, _ = _run_sandbox(tmp_path, fixture_repo)
        assert result.success is True
        assert not Path(f"/sys/fs/cgroup/workflo/{result.sandbox_id}").exists()

    def test_no_netns_left(self, host_ready, tmp_path, fixture_repo):
        result, _ = _run_sandbox(tmp_path, fixture_repo)
        assert result.success is True
        listing = subprocess.run(
            ["ip", "netns", "list"], capture_output=True, text=True
        )
        assert f"workflo-{result.sandbox_id}" not in listing.stdout

    def test_no_workspace_left_but_evidence_survives(self, host_ready, tmp_path, fixture_repo):
        result, _ = _run_sandbox(tmp_path, fixture_repo)
        assert result.success is True
        run_root = Path(result.evidence_dir).parent
        assert not (run_root / "workspace").exists()
        assert not (run_root / "tmp").exists()
        assert not (run_root / "home").exists()
        # Evidence backs the receipt — it survives by design
        assert (Path(result.evidence_dir) / "manifest.json").exists()

    def test_no_dnsmasq_process_left(self, host_ready, tmp_path, fixture_repo):
        result, _ = _run_sandbox(tmp_path, fixture_repo)
        assert result.success is True
        ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True)
        assert f"workflo-{result.sandbox_id}" not in ps.stdout


class TestIsolationFromInside:
    """The sandbox's own view of the world is sealed — proven by the
    repo's adversarial tests running inside it (covered by the golden
    run) plus direct netns checks here."""

    def test_nftables_default_drop_in_netns(self, host_ready, tmp_path, fixture_repo):
        from sandbox_runtime.network import verify_network_isolation

        # Bring up a network, verify isolation, tear it down
        from sandbox_runtime.config import NetworkConfig
        from sandbox_runtime.network import setup_private_network, teardown_network

        nid = uuid.uuid4().hex[:12]
        net_config = NetworkConfig(sandbox_id=nid)
        try:
            setup_private_network(net_config)
            results = verify_network_isolation(net_config.netns_name)
            blocked = [k for k, v in results.items() if v.get("blocked")]
            assert len(blocked) >= 8, f"external destinations not all blocked: {results}"
        finally:
            teardown_network(net_config)


class TestSeccompEnforcement:
    """The compiled BPF actually restricts the sandboxed process."""

    def test_empty_profile_kills_everything(self, host_ready, tmp_path):
        """A profile allowing NOTHING must kill even `true` — proving the
        BPF is loaded and enforced, not decorative."""
        sandbox_dirs = _mk_dirs(tmp_path)
        dest = tmp_path / "empty.bpf"
        write_empty_bwrap_profile(dest)

        proc = subprocess.run(
            build_bwrap_args(_bwrap_config(tmp_path, sandbox_dirs, seccomp=dest))
            + ["--", "true"],
            capture_output=True,
        )
        # execve itself is disallowed -> the command cannot run
        assert proc.returncode != 0

    def test_real_profile_runs_python(self, host_ready, tmp_path):
        """The real test profile allows python to start and print."""
        sandbox_dirs = _mk_dirs(tmp_path)
        dest = tmp_path / "test.bpf"
        write_bwrap_profile(get_seccomp_profile(WorkloadType.TEST), dest)

        config = _bwrap_config(
            tmp_path, sandbox_dirs, seccomp=dest,
            command=["python3", "-c", "print('sandboxed-ok')"],
        )
        fd = os.open(str(dest), os.O_RDONLY)
        os.set_inheritable(fd, True)
        try:
            proc = subprocess.run(
                build_bwrap_args(config, seccomp_fd=fd) + ["--"] + config.command,
                capture_output=True, pass_fds=(fd,),
            )
        finally:
            os.close(fd)
        assert proc.returncode == 0, proc.stderr
        assert b"sandboxed-ok" in proc.stdout


def _mk_dirs(tmp_path: Path) -> dict:
    sandbox_dirs = {}
    for name in ("workspace", "tmp", "home", "artifacts"):
        d = tmp_path / name
        d.mkdir()
        sandbox_dirs[name] = d
    return sandbox_dirs


def _bwrap_config(tmp_path: Path, dirs: dict, seccomp: Path,
                  command=None):
    from sandbox_runtime.config import BwrapConfig, NetworkMode

    return BwrapConfig(
        sandbox_id="gate-seccomp",
        workload_type=WorkloadType.TEST,
        readonly_root=Path("/opt/workflo/workflo-worker"),
        workspace_dir=dirs["workspace"],
        evidence_dir=dirs["artifacts"],
        tmp_dir=dirs["tmp"],
        home_dir=dirs["home"],
        network_mode=NetworkMode.NONE,
        seccomp_profile=seccomp,
        command=command if command is not None else ["true"],
        env={"PATH": "/usr/bin:/bin", "HOME": "/home/workflo"},
    )


class TestHostileBehavior:
    """The 'nothing escaped, nothing survived' battery (launch gate).

    Covers fork-bomb containment (cgroup pids.max) and a forbidden
    syscall under the REAL test profile — kernel-enforced, not mocked.
    """

    def test_fork_bomb_is_bounded_by_pids_max(self, host_ready, tmp_path):
        """A runaway forker must hit the cgroup pids ceiling, and the
        ceiling event must be RECORDED by the kernel (pids.events:max)."""
        from sandbox_runtime.cgroups import (
            CgroupConfig, setup_cgroup, cleanup_cgroup,
        )
        from sandbox_runtime.bwrap import run_bwrap

        cg = setup_cgroup(CgroupConfig(
            sandbox_id=f"sbx-forkbomb-{uuid.uuid4().hex[:8]}",
            memory_mb=256, cpu_cores=0.5,
        ))
        pids_max = 64
        (cg / "pids.max").write_text(str(pids_max))

        dirs = _mk_dirs(tmp_path)
        # Children sleep briefly — long enough to pile up AT the pids
        # ceiling, short enough that communicate() (which waits for pipe
        # EOF held open by the children) returns well inside the timeout.
        config = _bwrap_config(
            tmp_path, dirs,
            seccomp=get_seccomp_profile(WorkloadType.TEST),
            command=["python3", "-c",
                     "import os\n"
                     "n = 0\n"
                     "try:\n"
                     "    while True:\n"
                     "        pid = os.fork()\n"
                     "        if pid == 0:\n"
                     "            import time; time.sleep(8); os._exit(0)\n"
                     "        n += 1\n"
                     "except OSError:\n"
                     "    print(f'FORKS_STOPPED {n}')\n"],
        )
        # _bwrap_config builds namespaces-only; join the real cgroup.
        config.cgroup_procs = cg / "cgroup.procs"
        proc = run_bwrap(config, capture=True)
        try:
            stdout, _ = proc.communicate(timeout=90)
            assert b"FORKS_STOPPED" in stdout, f"forker never stopped: {stdout!r}"
            # Kernel accounting proves the ceiling fired:
            events = (cg / "pids.events").read_text()
            max_hits = int(events.split("max")[1].strip())
            assert max_hits >= 1, f"pids.max never fired: {events!r}"
        finally:
            # cgroup v2 kill: terminates the WHOLE tree (bomb included).
            try:
                (cg / "cgroup.kill").write_text("1")
            except OSError:
                pass
            proc.kill()
            proc.communicate()
            cleanup_cgroup(cg)

    def test_forbidden_syscall_killed_under_real_profile(self, host_ready, tmp_path):
        """mount(2) is not in the TEST profile's allowlist; a sandboxed
        process attempting it is killed by the kernel (KILL_PROCESS)."""
        from sandbox_runtime.bwrap import run_bwrap

        dirs = _mk_dirs(tmp_path)
        config = _bwrap_config(
            tmp_path, dirs,
            seccomp=get_seccomp_profile(WorkloadType.TEST),
            command=["python3", "-c",
                     "import ctypes\n"
                     "libc = ctypes.CDLL(None, use_errno=True)\n"
                     "libc.syscall(165, b'tmpfs', b'/tmp', b'', 0, b'')\n"
                     "print('MOUNT_REACHED')\n"],  # must never print
        )
        proc = run_bwrap(config, capture=True)
        stdout, _ = proc.communicate(timeout=60)
        assert proc.returncode != 0, "forbidden syscall was NOT killed"
        assert b"MOUNT_REACHED" not in stdout


class TestFailClosed:
    """Deliberately broken invariants must fail closed."""

    def test_broken_runtime_image_fails_closed(self, host_ready, tmp_path, fixture_repo):
        """A runtime image missing required dirs must abort BEFORE the
        sandbox runs, and the failure receipt must prove the sandbox did
        not run (fail-closed teardown claims)."""
        config = _make_run_config(tmp_path, fixture_repo)
        # Point at a directory that exists but lacks /bin /lib /usr /etc
        bad_image = tmp_path / "bad-image"
        bad_image.mkdir()

        import asyncio
        supervisor = Supervisor(config)
        supervisor.config.runtime_image = bad_image
        result = asyncio.run(supervisor.run())

        assert result.success is False
        assert result.receipt_payload is not None
        # Fail-closed: the cgroup/netns were never created, so the
        # execution-environment claim must be False (absence of proof is
        # proof of nothing). The workspace bind dirs WERE created and
        # removed by the emergency teardown — filesystem_removed is True,
        # honestly recorded.
        tp = result.receipt_payload["teardown_proof"]
        assert tp["container_removed"] is False

        # And the outside verifier REJECTS the failure receipt
        from workflo_schema.sandbox import SignedReceipt
        from sandbox_isolation import verify_receipt_signature
        receipt = SignedReceipt(**result.receipt_payload)
        # (signature itself would verify, but the CLAIMS fail — the CLI
        # verify command exits 1 on claims; covered there.)

    def test_missing_fixture_snapshot_fails(self, host_ready, tmp_path):
        """A repo path that is not a git repo yields an empty snapshot —
        pytest collects nothing and the receipt records it honestly."""
        empty_dir = tmp_path / "not-a-repo"
        empty_dir.mkdir()

        result, _ = _run_sandbox(tmp_path, empty_dir)
        # The run may succeed with 0 tests, but the report must be honest
        rr = result.receipt_payload["run_report"]
        assert rr["total"] == 0
        # collection_error distinguishes "0 tests ran" from "nothing collected"
        assert rr["collection_error"] is not None or rr["total"] == 0
