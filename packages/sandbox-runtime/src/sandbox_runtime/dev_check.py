"""Sealed, one-shot namespace supervisor for the local development profile.

Uses the existing bwrap, seccomp, Landlock, cgroup and teardown primitives.
Unlike the legacy supervisor, this path creates no named network, serves no
app, installs no dependencies, and never mounts retained evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp
from uuid import uuid4

from workflo_schema.contracts import (
    ExecutionPolicyBundleV1,
    PolicyComponentId,
    ProducerComponent,
    ProducerIdentityV1,
    RunCreatorV1,
    RunSpecV1,
    SourceProvider,
    SourceSpecV1,
    TrustVerificationStatus,
    utc_now_ms,
)
from workflo_schema.contracts.canonical import canonical_bytes, sha256_digest
from workflo_schema.contracts.receipt import (
    NamespaceTeardownCheckId,
    NamespaceTeardownCheckV1,
    NamespaceTeardownVerificationV1,
)
from workflo_schema.dev_check import (
    CAPABILITIES,
    MAX_REPORT_BYTES,
    PROFILE_ID,
    RETENTION,
    CheckObservation,
    LocalCheckReport,
    LocalSnapshot,
    build_local_policy,
    pytest_argv,
    validate_revision,
)

from sandbox_runtime.bwrap import run_bwrap
from sandbox_runtime.cgroups import WORKFLO_CGROUP_ROOT, setup_cgroup
from sandbox_runtime.config import (
    BwrapConfig,
    CgroupConfig,
    NetworkMode,
    RootfsConfig,
    WorkloadType,
)
from sandbox_runtime.landlock import probe_abi
from sandbox_runtime.pinned_source import SourceRejected, materialize_pinned_source
from sandbox_runtime.rootfs import prepare_rootfs
from sandbox_runtime.seccomp import get_seccomp_profile
from sandbox_runtime.teardown import teardown_and_verify


class DevInfrastructureError(RuntimeError):
    """No complete deterministic check result was produced."""


class DevTeardownError(RuntimeError):
    """The host could not verify removal of a provisioned resource."""


@dataclass(frozen=True)
class LocalDevResult:
    spec: RunSpecV1
    policy: ExecutionPolicyBundleV1
    snapshot: LocalSnapshot
    report: LocalCheckReport
    teardown: NamespaceTeardownVerificationV1
    snapshot_at: str
    checks_at: str


def measure_runtime(image: Path) -> str:
    """Bind the contents and modes of the trusted host-owned runtime tree."""
    if not (image / "workflo/landlock_exec.py").is_file():
        raise DevInfrastructureError("build the Workflo runtime image before running this profile")
    digest = hashlib.sha256(b"workflo:runtime-tree:v1\n")
    for root, dirs, files in os.walk(image, onerror=_raise_os_error, followlinks=False):
        dirs.sort()
        for name in sorted(dirs + files):
            path = Path(root) / name
            mode = path.lstat().st_mode
            entry = {"path": path.relative_to(image).as_posix(), "mode": mode}
            if stat.S_ISLNK(mode):
                entry["link"] = os.readlink(path)
            elif stat.S_ISREG(mode):
                with path.open("rb") as file:
                    entry["sha256"] = hashlib.file_digest(file, "sha256").hexdigest()
            elif not stat.S_ISDIR(mode):
                raise DevInfrastructureError("unexpected special file in runtime image")
            digest.update(canonical_bytes(entry) + b"\n")
    return f"sha256:{digest.hexdigest()}"


def _raise_os_error(error: OSError) -> None:
    raise error


def _read_guest_json(path: Path) -> dict:
    # Only read after the cgroup is gone. Never follow guest symlinks or open
    # blocking special files; bound the read even if the file size is false.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as file:
        info = os.fstat(file.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_REPORT_BYTES:
            raise ValueError("invalid guest report file")
        raw = file.read(MAX_REPORT_BYTES + 1)
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError("guest report exceeded its size limit")
    doc = json.loads(raw)
    if not isinstance(doc, dict):
        raise ValueError("report must be an object")
    return doc


def normalize_pytest_report(data: dict, returncode: int, test_file: str) -> LocalCheckReport:
    """Promote only completed test calls; collection/setup/cleanup errors aren't findings."""
    try:
        if (
            returncode not in (0, 1)
            or type(data["exitcode"]) is not int
            or data["exitcode"] != returncode
        ):
            raise ValueError("pytest exit status does not describe completed checks")
        checks = []
        for item in data["tests"]:
            check = CheckObservation(node_id=item["nodeid"], outcome=item["outcome"])
            if (
                not check.node_id.startswith(f"{test_file}::")
                or item["setup"]["outcome"] != "passed"
                or item["teardown"]["outcome"] != "passed"
                or item["call"]["outcome"] != check.outcome
            ):
                raise ValueError("test scope or phase mismatch")
            checks.append(check)
        report = LocalCheckReport(
            returncode=returncode, checks=tuple(sorted(checks, key=lambda c: c.node_id))
        )
        summary = {"total": len(checks), "collected": len(checks)}
        for check in checks:
            summary[check.outcome] = summary.get(check.outcome, 0) + 1
        actual = data["summary"]
        if (
            not isinstance(actual, dict)
            or any(type(n) is not int for n in actual.values())
            or actual != summary
        ):
            raise ValueError("pytest summary does not describe all collected checks")
        return report
    except (KeyError, ValueError, TypeError) as exc:
        raise DevInfrastructureError(
            "pytest did not produce a complete pass/fail report for the admitted test file"
        ) from exc


def run_local_check(
    repo: Path, commit: str, test_file: str, image: Path, output: Path
) -> LocalDevResult:
    """Admit a fixed policy, execute in namespaces, return host observations (no signing key)."""
    validate_revision(commit)
    pytest_argv(test_file)  # reject invalid test selectors before host checks
    if sys.platform != "linux" or not shutil.which("bwrap") or probe_abi() <= 0:
        raise DevInfrastructureError(
            "this profile requires Linux, bubblewrap, cgroups v2 and Landlock"
        )
    image = image.resolve(strict=True)
    repo = repo.resolve(strict=True)
    if output.exists() or output.is_symlink():
        raise SourceRejected("choose a new proof directory; existing paths are never reused")
    output = output.resolve()
    if output.is_relative_to(image) or output.is_relative_to(repo):
        raise SourceRejected("place the proof directory outside the runtime and source repository")
    runtime_digest = measure_runtime(image)
    seccomp_data = get_seccomp_profile(WorkloadType.TEST).read_bytes()
    created_at = utc_now_ms()
    token = uuid4().hex
    creator = RunCreatorV1(user_id="local-operator", organization_id="local-dev")
    policy = build_local_policy(
        creator, created_at, runtime_digest, sha256_digest(seccomp_data), test_file
    )
    components = {component.component: component.payload for component in policy.components}
    resource = components[PolicyComponentId.RESOURCE]
    command = components[PolicyComponentId.COMMAND]
    filesystem = components[PolicyComponentId.FILESYSTEM]
    spec = RunSpecV1(
        organization_id=creator.organization_id,
        project_id="local-project",
        run_id=f"run-{token}",
        idempotency_key=token,
        source=SourceSpecV1(provider=SourceProvider.GENERIC_GIT, ref=commit, commit=commit),
        profile_id=PROFILE_ID,
        policy_digest=policy.digest(),
        runtime_image_digest=runtime_digest,
        resource_profile=PROFILE_ID,
        capabilities=CAPABILITIES,
        retention=RETENTION,
        created_by=creator,
        created_at=created_at,
    )
    sandbox_id = f"sbx-{token}"
    cgroup_path = WORKFLO_CGROUP_ROOT / sandbox_id
    if cgroup_path.exists():
        raise DevInfrastructureError("run cgroup already exists; refusing to reuse it")
    output.mkdir(mode=0o700, exist_ok=False)
    # The launcher must traverse its bind sources in its user namespace.
    # Keep these separate from the caller-chosen proof path and never mount it.
    scratch = Path(mkdtemp(prefix=f"workflo-{sandbox_id}-", dir="/tmp"))
    workspace = scratch / "workspace"
    artifacts = scratch / "guest" / "artifacts"
    tmp, home = scratch / "tmp", scratch / "home"
    proc = None
    try:
        snapshot = materialize_pinned_source(repo, spec.source.commit, workspace / "repo")
        if test_file not in {entry.path for entry in snapshot.files}:
            raise SourceRejected("selected test file is not in the admitted snapshot")
        snapshot_at = utc_now_ms()
        prepare_rootfs(RootfsConfig(sandbox_id, image, workspace, artifacts, tmp, home))
        seccomp_path = scratch / "seccomp.json"
        seccomp_path.write_bytes(seccomp_data)
        try:
            group = setup_cgroup(
                CgroupConfig(
                    sandbox_id=sandbox_id,
                    memory_mb=resource["memory_mb"],
                    cpu_cores=resource["cpu_cores"],
                    pids_max=resource["pids_max"],
                )
            )
            if group != cgroup_path:
                raise DevInfrastructureError("cgroup setup did not return the admitted scope")
            config = BwrapConfig(
                sandbox_id=sandbox_id,
                workload_type=WorkloadType.TEST,
                readonly_root=image,
                workspace_dir=workspace,
                evidence_dir=artifacts,
                tmp_dir=tmp,
                home_dir=home,
                network_mode=NetworkMode.NONE,
                seccomp_profile=seccomp_path,
                landlock_mode="hardened",
                landlock_rules=filesystem["rules"],
                command=command["argv"],
                env=command["environment"],
                workdir="/workspace/repo",
                cgroup_procs=group / "cgroup.procs",
                sealed_test=True,
            )
            with open(os.devnull, "wb") as discard:
                proc = run_bwrap(config, capture=False, stdout_file=discard, stderr_file=discard)
                returncode = proc.wait(timeout=resource["timeout_seconds"])
            checks_at = utc_now_ms()
        finally:
            # Use the expected path even when setup failed after mkdir. The
            # cleanup helper re-observes process and cgroup state on the host.
            try:
                observed = teardown_and_verify({"test": proc}, cgroup_path, None, [])
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                raise DevTeardownError("could not observe process and cgroup teardown") from exc
            if not observed.processes_terminated or not observed.cgroup_removed:
                raise DevTeardownError(
                    "host could not verify that the test process scope and cgroup were removed"
                )

        if returncode not in (0, 1):
            raise DevInfrastructureError(f"isolated pytest did not complete (exit {returncode})")
        try:
            status = _read_guest_json(artifacts / "landlock-status-test.json")
            if status.get("status") != "LANDLOCK_APPLIED" or status.get("mode") != "hardened":
                raise ValueError("required Landlock status missing")
            data = _read_guest_json(artifacts / "pytest-report.json")
        except (OSError, ValueError, RecursionError) as exc:
            raise DevInfrastructureError(
                "the isolated workload did not return usable report and Landlock evidence"
            ) from exc
        report = normalize_pytest_report(data, returncode, test_file)
    finally:
        # Guest scratch contains the only raw report; nothing under it is
        # retained, and the signer is not called if any of it remains.
        shutil.rmtree(scratch, ignore_errors=True)
        try:
            scratch.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise DevTeardownError(
                "could not observe removal of the workspace and guest scratch"
            ) from exc
        else:
            raise DevTeardownError(
                "host could not verify removal of the workspace and guest scratch"
            )

    if measure_runtime(image) != runtime_digest:
        raise DevInfrastructureError("the runtime image changed during the run")
    teardown = NamespaceTeardownVerificationV1(
        verification_id=f"teardown-{token}",
        outcome=TrustVerificationStatus.VERIFIED_CLEAN,
        verifier=ProducerIdentityV1(
            component=ProducerComponent.HOST_WORKER, instance_id=sandbox_id, version=PROFILE_ID
        ),
        checks=(
            NamespaceTeardownCheckV1(
                check_id=NamespaceTeardownCheckId.PROCESS_SCOPE_EMPTY,
                passed=observed.processes_terminated,
            ),
            NamespaceTeardownCheckV1(
                check_id=NamespaceTeardownCheckId.CGROUPS_REMOVED, passed=observed.cgroup_removed
            ),
            NamespaceTeardownCheckV1(
                check_id=NamespaceTeardownCheckId.WORKSPACE_REMOVED, passed=True
            ),
        ),
        observed_at=utc_now_ms(),
    )
    return LocalDevResult(spec, policy, snapshot, report, teardown, snapshot_at, checks_at)
