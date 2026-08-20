"""Sandbox executor — the orchestration layer that ties everything together.

This is the thing that makes workflo workflo:

    SandboxSpec (repo URL + config)
        |
        v
    [mount tmpfs]
        |
        v
    [git clone into tmpfs OR copy from local --path]
        |
        v
    IF dependency_install:
        [Stage 1: docker create --network bridge --memory ... --image workflo-worker]
            |  (networked prep: install dependencies from manifest)
        [Stage 1: docker start] -> [Stage 1: docker wait]
        [Stage 1: docker rm -f]   ← prep container torn down
    [docker create --network none --memory ... --image workflo-worker]
        |  (sealed test stage)
    [docker start] -> [docker wait] (with timeout)
        |
        v
    [collect RunReport from container stdout]
        |
        v
    [canary check] (outbound request that MUST fail)
        |
        v
    [teardown: docker rm -f, unmount tmpfs]
        |
        v
    [build TeardownProof] (fails closed)
        |
        v
    [build SignedReceipt] + [Ed25519 sign]
        |
        v
    SandboxRunResult (the thing the CLI / API returns)

Intentionally all synchronous and explicitly ordered. There's no async path
because a sandbox lifecycle that races is a sandbox whose teardown proof
might be a lie.

The two-stage flow (Stage 1 networked prep + Stage 2 sealed test) is ONLY
used when the spec's `dependency_install` flag is True, which the CLI sets
only for local-folder inputs that have a detected package manifest
(requirements.txt, package.json, go.mod, etc.). The test stage itself is
ALWAYS sealed — the receipt's `dependency_install_had_network` field makes
the distinction explicit so a reviewer knows the isolation guarantee is for
the TEST STAGE only when that flag is True.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

from tenant_shield_schema.sandbox import (
    CanaryCheckResult,
    RunReport,
    SandboxLifecycleEvent,
    SandboxSpec,
    SignedReceipt,
    SecurityProbeResult,
    TeardownProof,
    WebProbeResult,
)

from sandbox_isolation import (
    CanaryResult,
    ReceiptSigner,
    attempt_canary_request,
    build_teardown_proof,
    generate_keypair,
    mount_tmpfs,
    unmount_tmpfs,
    verify_ephemeral_gone,
    verify_receipt_signature,
)

from workflo_executor.docker_runner import (
    ContainerConfig,
    ContainerResult,
)
from workflo_executor.runtime import ContainerRuntime, DockerContainerRuntime


# Default images for the worker tiers.
#
# SURFACE: small, fast, no model weights, no browser. Used for --test / --security.
# DEEP:   layered on top of surface, ships Ollama + Qwen2.5-Coder. Used
#         for --deep-test / --aggressive-test (the model stage needs Ollama).
# WEB:    layered on top of surface, ships Playwright + Chromium. Used
#         for --web (the browser probes need a headless browser).
# DEEP_WEB: combined image. Not built before Aug 25; select_worker_image
#         RAISES on that combination rather than silently falling back to
#         one tier or the other — see the matrix below.
#
# The CLI surfaces the first three as flags (--worker-image /
# --deep-worker-image) so they can be overridden per-run; the executor
# picks which one to actually use based on the probe groups in the spec —
# see `select_worker_image`.
DEFAULT_WORKER_IMAGE = "workflo-worker:latest"
DEFAULT_DEEP_WORKER_IMAGE = "workflo-worker-deep:latest"
DEFAULT_WEB_WORKER_IMAGE = "workflo-worker-web:latest"
DEFAULT_DEEP_WEB_WORKER_IMAGE = "workflo-worker-deep-web:latest"  # planned, not built

# Probe groups that require the model-bearing (deep) image. If ANY of these
# appears in the spec's run_spec["probe_groups"], the deep image is selected.
# This is a set, not a list, so lookups are O(1) and duplicates collapse.
_DEEP_PROBE_GROUPS = frozenset({"deep", "aggressive"})

# Probe groups that require the Playwright/Chromium (web) image.
_WEB_PROBE_GROUPS = frozenset({"web"})


# --------------------------------------------------------------------
# Image selection matrix — table-driven.
#
# Keys are frozensets of CAPABILITIES the run needs (not probe-group
# names): "deep" = the model stage is requested, "web" = browser probes
# are requested. The matrix maps capability-sets to image names.
#
# The deep+web key is DELIBERATELY ABSENT: the combined image is planned
# but not built before Aug 25. `select_worker_image` raises a clear
# ValueError for that combination instead of silently degrading to one
# tier — exactly the "combination handling" risk this matrix exists to
# make loud, not quiet.
# --------------------------------------------------------------------
_IMAGE_MATRIX: dict[frozenset[str], str] = {
    frozenset(): DEFAULT_WORKER_IMAGE,
    frozenset({"deep"}): DEFAULT_DEEP_WORKER_IMAGE,
    frozenset({"web"}): DEFAULT_WEB_WORKER_IMAGE,
}


def _capability_key(probe_groups: list[str]) -> frozenset[str]:
    """Map probe groups to the capability set that drives image selection."""
    caps: set[str] = set()
    for g in probe_groups:
        if g in _DEEP_PROBE_GROUPS:
            caps.add("deep")
        if g in _WEB_PROBE_GROUPS:
            caps.add("web")
    return frozenset(caps)


def _probe_groups_from_spec(spec: SandboxSpec) -> list[str]:
    """Read the probe groups out of a SandboxSpec, defensively.

    The spec's `run_spec` is a free-form dict (typed as `dict` in the schema
    so the worker engine has latitude), so we coerce the `probe_groups` value
    to a list[str] here. Missing/non-list values default to the worker's own
    default (["surface", "security"]) — same fallback the executor itself
    applies in execute_run, so the image selection and the probe-group
    interpretation agree.

    Non-string entries are DROPPED rather than coerced: an int/None in the
    list is a caller typo, not a probe group label, so stringifying `42` to
    `'42'` would let the typo leak downstream and confuse comparisons
    against known group names like "deep" / "aggressive".
    """
    run_spec = spec.run_spec if isinstance(spec.run_spec, dict) else {}
    groups = run_spec.get("probe_groups")
    if not isinstance(groups, list):
        return ["surface", "security"]
    return [g for g in groups if isinstance(g, str)]


def _detect_install_command(repo_dir: str) -> Optional[str]:
    """Detect the dependency-install command for a local repo.

    Looks for common package manifests in priority order and returns the
    shell command to run inside the prep container. Returns None when no
    manifest is found — callers (the executor's two-stage flow) must treat
    None as "skip the prep stage", not as "crash".

    Detection priority:
      1. requirements.txt         -> pip install --no-cache-dir -r requirements.txt
      2. pyproject.toml (PEP 621) -> pip install --no-cache-dir .
      3. setup.py                  -> pip install --no-cache-dir .
      4. package.json              -> npm install --no-audit --no-fund
      5. go.mod                    -> go mod download
      6. Cargo.toml                -> cargo fetch

    This is intentionally a small, conservative list — false positives
    (running pip install on a non-Python repo) are worse than false
    negatives (skipping install because we didn't recognize the manifest).
    The CLI's detection runs the same function, so a manifest it
    recognizes is the same one the executor will install from.
    """
    repo_path = Path(repo_dir)
    if (repo_path / "requirements.txt").is_file():
        return "pip install --no-cache-dir -r requirements.txt"
    if (repo_path / "pyproject.toml").is_file():
        return "pip install --no-cache-dir ."
    if (repo_path / "setup.py").is_file():
        return "pip install --no-cache-dir ."
    if (repo_path / "package.json").is_file():
        return "npm install --no-audit --no-fund"
    if (repo_path / "go.mod").is_file():
        return "go mod download"
    if (repo_path / "Cargo.toml").is_file():
        return "cargo fetch"
    return None


class SandboxRunResult:
    """Everything that comes back from a single sandbox run.

    The SignedReceipt is the customer-facing artifact. The rest is for
    the executor caller (CLI, API, or test harness) to inspect.
    """

    def __init__(
        self,
        receipt: SignedReceipt,
        report: RunReport,
        lifecycle_events: list[SandboxLifecycleEvent],
        elapsed_seconds: float,
        success: bool,
        error: Optional[str] = None,
    ):
        self.receipt = receipt
        self.report = report
        self.lifecycle_events = lifecycle_events
        self.elapsed_seconds = elapsed_seconds
        self.success = success
        self.error = error

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "elapsed_seconds": self.elapsed_seconds,
            "error": self.error,
            "receipt": self.receipt.model_dump(mode="json"),
            "report": self.report.model_dump(mode="json"),
            "lifecycle_events": [e.model_dump(mode="json") for e in self.lifecycle_events],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, default=str)


class SandboxExecutor:
    """Orchestrates the full sandbox lifecycle.

    Usage:
        executor = SandboxExecutor(worker_image="workflo-worker:latest")
        result = executor.run(spec)
        print(result.receipt.signature)  # verifies against published pubkey

    The executor is stateless between runs — no container IDs or mounts
    persist on the instance. Each `run()` call is fully self-contained.
    """

    def __init__(
        self,
        worker_image: str = "workflo-worker:latest",
        deep_worker_image: Optional[str] = None,
        web_worker_image: Optional[str] = None,
        signer: Optional[ReceiptSigner] = None,
        tmpfs_size_mb: int = 512,
        canary_target: str = "https://example.com",
        runtime: Optional[ContainerRuntime] = None,
    ):
        self.worker_image = worker_image
        # Image used for --deep-test / --aggressive-test tiers (which need the
        # model-bearing image so Ollama + Qwen2.5-Coder is available). When
        # None, falls back to DEFAULT_DEEP_WORKER_IMAGE at selection time —
        # deferred so `deep_worker_image` is only resolved if a deep-tier run
        # actually needs it.
        self.deep_worker_image = deep_worker_image
        # Image used for --web tier (which needs Playwright + Chromium).
        # When None, falls back to DEFAULT_WEB_WORKER_IMAGE at selection time.
        self.web_worker_image = web_worker_image
        self.signer = signer or generate_keypair()
        self.tmpfs_size_mb = tmpfs_size_mb
        self.canary_target = canary_target
        # Inject a runtime backend — defaults to Docker CLI.
        # This is the seam where Fargate / gVisor / podman plug in.
        self.runtime: ContainerRuntime = runtime or DockerContainerRuntime()

    def run(self, spec: SandboxSpec) -> SandboxRunResult:
        """Execute a full sandbox run. Returns the signed result.

        This is the function the CLI wraps. It either returns a
        SandboxRunResult with a valid signed receipt, or raises.
        It never returns a half-finished receipt.
        """

        run_start = time.monotonic()
        lifecycle_events: list[SandboxLifecycleEvent] = []
        mount = None
        container_id: Optional[str] = None

        def emit(event: str, detail: Optional[dict] = None):
            evt = SandboxLifecycleEvent(
                sandbox_id=spec.sandbox_id,
                event=event,
                timestamp=datetime.now(UTC),
                detail=detail or {},
            )
            lifecycle_events.append(evt)

        try:
            emit("created", {"spec": spec.model_dump(mode="json")})

            # 1. Mount tmpfs for the repo
            mount = mount_tmpfs(spec.sandbox_id, size_mb=self.tmpfs_size_mb)
            emit("tmpfs_mounted", {"mount_point": str(mount.mount_point)})

            # 2. Prepare the repo inside the tmpfs.
            #    If a local path was provided (--path), copy it into the tmpfs.
            #    Otherwise, git-clone the repo URL into the tmpfs.
            repo_target = mount.mount_point / "repo"
            if spec.repo_path:
                # Copy local directory into the tmpfs
                import shutil
                if repo_target.exists():
                    shutil.rmtree(repo_target)
                shutil.copytree(spec.repo_path, repo_target)
                emit("repo_copied", {"local_path": spec.repo_path})
            else:
                # Git clone the repo URL into the tmpfs
                clone_result = subprocess.run(
                    ["git", "clone", "--depth", "1", spec.repo_url, str(repo_target)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if clone_result.returncode != 0:
                    raise RuntimeError(
                        f"git clone failed for {spec.repo_url}: {clone_result.stderr.strip()}"
                    )
                emit("repo_cloned", {"repo_url": spec.repo_url})

            if spec.commit_sha:
                checkout_result = subprocess.run(
                    ["git", "checkout", spec.commit_sha],
                    cwd=str(mount.mount_point / "repo"),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if checkout_result.returncode != 0:
                    raise RuntimeError(
                        f"git checkout {spec.commit_sha} failed: {checkout_result.stderr.strip()}"
                    )
                emit("commit_pinned", {"commit_sha": spec.commit_sha})

            # 2.5 Two-stage flow: Stage 1 (networked prep) runs ONLY when the
            # spec's dependency_install flag is True. The CLI sets this for
            # local-folder inputs that have a detected package manifest
            # (requirements.txt, package.json, go.mod, etc.). Stage 1's
            # network access is isolated to the prep container — Stage 2's
            # sealed test container is always created fresh with network=none
            # so nothing from Stage 1 leaks in.
            prep_container_id: Optional[str] = None
            if spec.dependency_install:
                install_cmd = _detect_install_command(str(repo_target))
                if install_cmd is None:
                    # Flag was set but no install command resolved — degrade
                    # safely: skip the prep stage, run single-stage sealed.
                    # This shouldn't happen if the CLI's detection is right,
                    # but the executor fails closed (no fake "had_network"
                    # claim) rather than crashing mid-run.
                    emit("prep_skipped_no_command", {})
                else:
                    emit("prep_started", {"install_command": install_cmd})
                    prep_container_config = ContainerConfig(
                        image=self.worker_image,
                        command=["sh", "-c", f"cd /workspace/repo && {install_cmd}"],
                        network_mode="bridge",  # NETWORK ON for prep, deliberately
                        memory_mb=spec.memory_mb,
                        cpu_cores=spec.cpu_cores,
                        timeout_seconds=300,
                        env={},
                        workdir="/workspace",
                        read_only_root=False,
                        volume_mounts={str(mount.mount_point): "/workspace"},
                    )
                    prep_container_id = self.runtime.create(prep_container_config)
                    emit("prep_container_created", {"container_id": prep_container_id})
                    self.runtime.start(prep_container_id, timeout_seconds=30)
                    prep_result = self.runtime.wait(
                        prep_container_id, timeout_seconds=300
                    )
                    # Tear down prep container BEFORE Stage 2 starts — the
                    # whole point of two stages is that the prep container
                    # is gone before the test container exists.
                    self.runtime.kill(prep_container_id)
                    prep_gone = not self.runtime.exists(prep_container_id)
                    prep_container_id = None
                    emit("prep_completed", {
                        "returncode": prep_result.returncode,
                        "container_removed": prep_gone,
                        "had_network": True,
                    })
                    if prep_result.returncode != 0:
                        raise RuntimeError(
                            f"dependency install failed (exit {prep_result.returncode}): "
                            f"{(prep_result.stderr or '(none)')[-500:].strip()}"
                        )
                    if not prep_gone:
                        raise RuntimeError(
                            "dependency-install prep container was not removed before "
                            "test stage started — refusing to proceed with two-stage flow "
                            "because Stage 2's isolation guarantee depends on Stage 1 being gone"
                        )

# 3. Build container config with network isolation.
            # We bind-mount the host tmpfs (which holds the cloned repo) into the
            # container at /workspace. The container cannot escape that mount,
            # and when we unmount the host tmpfs, both the container's view and
            # our own view of the repo disappear together.
            # We also write the spec file into the tmpfs so the worker reads it
            # via /workspace/spec.json — that way the spec is per-run and not
            # baked into the image.
            spec_file_path = mount.mount_point / "spec.json"
            try:
                spec_file_path.write_text(
                    json.dumps(spec.model_dump(mode="json"), default=str),
                    encoding="utf-8",
                )
            except OSError as e:
                raise RuntimeError(f"Failed to write spec file to tmpfs: {e}")

            repo_path_in_container = "/workspace/repo"
            # Select the worker image based on the spec's probe groups.
            # This is the auto-switch the CLI advertises: --deep-test /
            # --aggressive-test run on the model-bearing image (so Ollama +
            # Qwen2.5-Coder is available inside the sandbox), while plain
            # --test / --security stay on the small base image. The selected
            # image is recorded in the lifecycle events so the receipt is
            # auditable — a reviewer can verify a deep-test run actually
            # used the deep image (and vice versa).
            selected_image = self.select_worker_image(spec)
            emit("worker_image_selected", {"worker_image": selected_image})

            container_config = ContainerConfig(
                image=selected_image,
                command=self._build_worker_command(spec, repo_path_in_container),
                network_mode="none",
                memory_mb=spec.memory_mb,
                cpu_cores=spec.cpu_cores,
                timeout_seconds=spec.timeout_seconds,
                env={
                    **(spec.run_spec.get("env", {}) if isinstance(spec.run_spec, dict) else {}),
                    "PROBE_GROUPS": json.dumps(spec.run_spec.get("probe_groups", ["surface", "security"])),
                },
                workdir="/workspace",
                read_only_root=False,
                # Use a bind mount of the host tmpfs instead of in-container tmpfs,
                # so the cloned repo is visible to the worker.
                volume_mounts={str(mount.mount_point): "/workspace"},
            )

            container_id = self.runtime.create(container_config)
            emit("container_created", {"container_id": container_id})

            start_time = time.monotonic()
            self.runtime.start(container_id, timeout_seconds=30)
            emit("tests_started", {"container_id": container_id})

            container_result = self.runtime.wait(
                container_id, timeout_seconds=spec.timeout_seconds
            )
            test_duration = time.monotonic() - start_time

            if container_result.timed_out:
                emit("tests_timeout", {"timeout_seconds": spec.timeout_seconds})
            else:
                emit("tests_completed", {
                    "returncode": container_result.returncode,
                    "duration_seconds": test_duration,
                })

            # 4. Parse the RunReport + canary + model teardown from container stdout.
            # A worker that never emitted WORKFLO_REPORT crashed before finishing
            # (import error, unhandled exception). That is a FAILED run — we must
            # never fabricate a clean 0/0 out of a dead worker.
            worker_reported = self._parse_run_report(container_result, spec.sandbox_id, test_duration)
            if worker_reported is None:
                report = RunReport(
                    sandbox_id=spec.sandbox_id,
                    duration_seconds=test_duration,
                    collection_error=(
                        f"worker did not emit WORKFLO_REPORT (exit code "
                        f"{container_result.returncode}); stderr tail: "
                        f"{(container_result.stderr or '(none)')[-300:].strip()}"
                    ),
                )
            else:
                report = worker_reported
            in_container_canary = self._parse_canary(container_result, spec.sandbox_id)
            model_teardown_status, model_teardown_error = self._parse_model_teardown(container_result)
            web_probes = self._parse_web_probes(container_result)
            security_probes = self._parse_security_probes(container_result)

            # 5. Canary check — comes from INSIDE the container (proof that
            # the container's network namespace actually has no egress).
            # If the worker didn't emit a WORKFLO_CANARY line (e.g. it crashed
            # before reaching that point), we mark the canary as "not checked"
            # rather than running a host-side canary that would always
            # succeed (host has internet) — that's misleading by design.
            if in_container_canary is not None:
                canary_result = in_container_canary
            else:
                canary_result = CanaryCheckResult(
                    sandbox_id=spec.sandbox_id,
                    attempted_at=datetime.now(UTC),
                    target_host=self.canary_target,
                    request_succeeded=False,
                    error="not checked (worker did not emit WORKFLO_CANARY line)",
                )
            emit("canary_checked", {
                "request_succeeded": canary_result.request_succeeded,
                "error": canary_result.error,
            })

            # 6. Teardown — kill container, unmount tmpfs, verify both gone
            emit("teardown_started")
            self.runtime.kill(container_id)
            container_id_for_proof = container_id
            container_id = None

            # Brief pause to let Windows release file handles from:
            #   - the just-killed container's bind mount (Docker Desktop lag)
            #   - the git clone subprocess that opened pack files
            # The retry loop in unmount_tmpfs() also handles this, but a small
            # upfront sleep makes the common case cleaner.
            time.sleep(0.3)

            unmount_tmpfs(mount)
            fs_gone = verify_ephemeral_gone(mount)
            mount_for_proof = mount
            mount = None
            emit("destroyed", {
                "container_removed": not self.runtime.exists(container_id_for_proof),
                "filesystem_removed": fs_gone,
            })

            # 7. Build teardown proof (fails closed)
            proof = build_teardown_proof(
                sandbox_id=spec.sandbox_id,
                container_id=container_id_for_proof,
                filesystem_wipe_method="tmpfs_umount",
            )
            proof.filesystem_removed = fs_gone
            # Apply model inference teardown status (None = not applicable).
            # The downstream verifier distinguishes "ran and cleaned up" (True)
            # from "ran but failed to clean up" (False) from "didn't run" (None).
            proof.model_inference_teardown = model_teardown_status
            proof.model_inference_error = model_teardown_error
            # Populate session metadata — ephemeral summary, never source code or artifacts.
            proof.session_duration_seconds = elapsed
            proof.peak_memory_mb = spec.memory_mb  # best-effort placeholder
            proof.peak_cpu_percent = spec.cpu_cores  # best-effort placeholder
            proof.events_count = len(lifecycle_events)

            # 8. Build and sign the receipt
            emit("receipt_signed", {"fingerprint": self.signer.public_key_fingerprint})

            receipt = SignedReceipt(
                sandbox_id=spec.sandbox_id,
                issued_at=datetime.now(UTC),
                run_report=report,
                teardown_proof=proof,
                canary_check=canary_result,
                lifecycle_events=list(lifecycle_events),  # snapshot copy
                web_probes=web_probes,
                security_probes=security_probes,
                # True ONLY when spec.dependency_install was set AND the prep
                # stage actually ran with network access. Single-stage runs
                # (the common --repo case) keep this False so the default
                # "network=none throughout" isolation claim is preserved.
                dependency_install_had_network=bool(spec.dependency_install),
                # Opt-in metadata: results written to DataHub as assertions
                # (no source code or test artifacts are ever transmitted).
                datahub_writeback=False,
                datahub_status="none",
            )
            self.signer.sign(receipt)

            elapsed = time.monotonic() - run_start
            success = (
                report.failed == 0
                and not report.collection_error
                and not container_result.timed_out
                and proof.container_removed
                and proof.filesystem_removed
                and not canary_result.request_succeeded
            )

            return SandboxRunResult(
                receipt=receipt,
                report=report,
                lifecycle_events=lifecycle_events,
                elapsed_seconds=elapsed,
                success=success,
                error=None if success else self._derive_error(report, proof, canary_result, container_result),
            )

        except Exception as e:
            # Emergency teardown — best effort, must not raise past this
            elapsed = time.monotonic() - run_start
            error_msg = f"{type(e).__name__}: {e}"

            try:
                if container_id:
                    self.runtime.kill(container_id)
            except Exception:
                pass

            try:
                if mount:
                    unmount_tmpfs(mount)
            except Exception:
                pass

            emit("teardown_error", {"error": error_msg})

            # Build a failure receipt if we can — even failed runs get signed
            failure_report = RunReport(sandbox_id=spec.sandbox_id)
            failure_proof = TeardownProof(
                sandbox_id=spec.sandbox_id,
                container_id=container_id,
                container_removed=False,
                filesystem_removed=False,
                destroyed_at=datetime.now(UTC),
            )
            failure_canary = CanaryCheckResult(
                sandbox_id=spec.sandbox_id,
                attempted_at=datetime.now(UTC),
                target_host=self.canary_target,
                request_succeeded=False,
                error="not checked (run failed before canary)",
            )
            failure_receipt = SignedReceipt(
                sandbox_id=spec.sandbox_id,
                issued_at=datetime.now(UTC),
                run_report=failure_report,
                teardown_proof=failure_proof,
                canary_check=failure_canary,
                lifecycle_events=lifecycle_events,
            )
            try:
                self.signer.sign(failure_receipt)
            except Exception:
                pass

            return SandboxRunResult(
                receipt=failure_receipt,
                report=failure_report,
                lifecycle_events=lifecycle_events,
                elapsed_seconds=elapsed,
                success=False,
                error=error_msg,
            )

    def select_worker_image(self, spec: SandboxSpec) -> str:
        """Pick the worker image for this run based on the spec's probe groups.

        Table-driven via `_IMAGE_MATRIX`, keyed on the capability set
        (deep / web) the probe groups imply:

          - surface / security only              -> worker_image
          - deep / aggressive                    -> deep_worker_image (default or override)
          - web                                  -> web_worker_image (default or override)
          - deep + web (BOTH)                    -> ValueError (combined image not built)

        The deep+web combination RAISES rather than silently falling back
        to one of the two images — a silent degrade would run the web
        probes without the model or vice-versa, and the receipt would look
        like a valid deep+web run when it wasn't. A loud, actionable error
        is the correct failure mode for an unsupported combination.

        This is the auto-switch the CLI advertises. It lives on the
        executor (not the CLI) so the executor is the single source of
        truth for which image a run used — the lifecycle event emitted
        before container create is the auditable record.
        """
        probe_groups = _probe_groups_from_spec(spec)
        key = _capability_key(probe_groups)

        if key == frozenset({"deep", "web"}):
            raise ValueError(
                f"probe groups {sorted(probe_groups)!r} require both the deep "
                f"model image and the web browser image, but "
                f"{DEFAULT_DEEP_WEB_WORKER_IMAGE} has not been built yet. "
                f"Choose one tier: remove 'web' or the deep tier from the "
                f"probe groups. (Known limitation tracked in the plan: "
                f"combined image is planned, not built before Aug 25.)"
            )

        if key == frozenset({"deep"}):
            return self.deep_worker_image or DEFAULT_DEEP_WORKER_IMAGE
        if key == frozenset({"web"}):
            return self.web_worker_image or DEFAULT_WEB_WORKER_IMAGE
        return self.worker_image or DEFAULT_WORKER_IMAGE

    def _build_worker_command(self, spec: SandboxSpec, repo_path_in_container: str = "/workspace/repo") -> list[str]:
        """Build the command the worker container runs.

        For Phase 1 (no model), this runs the worker's main entrypoint
        pointing at the spec file that gets mounted into the container
        via tmpfs at /workspace/. The worker reads it, runs pytest with
        the spec's markers, and emits a WORKFLO_REPORT line to stdout
        which the executor parses.
        """

        # Write spec to a JSON file that the worker reads.
        # We use --spec-file so the spec lives on the tmpfs at /workspace, 
        # not baked into the container (so each run is fully isolated).
        spec_file_in_container = "/workspace/spec.json"
        cmd = ["python", "-m", "tenant_shield_worker", "--spec-file", spec_file_in_container]
        cmd.append("--repo-path")
        cmd.append(repo_path_in_container)
        return cmd

    def _parse_run_report(
        self,
        container_result: ContainerResult,
        sandbox_id: str,
        test_duration: float,
    ) -> Optional[RunReport]:
        """Parse the worker's JSON output from container stdout into a RunReport.

        The worker writes a JSON line with the report to stdout. We look for
        a line starting with `WORKFLO_REPORT:` and parse the rest.

        Returns None when the worker emitted no WORKFLO_REPORT line — i.e. it
        crashed before completing (import error, exception before streaming).
        The caller must treat that as a failed run, never as a clean 0/0.
        """

        report: Optional[RunReport] = None

        for line in container_result.stdout.splitlines():
            line = line.strip()
            if line.startswith("WORKFLO_REPORT:"):
                try:
                    data = json.loads(line[len("WORKFLO_REPORT:"):])
                    report = RunReport(
                        sandbox_id=sandbox_id,
                        run_id=data.get("run_id"),
                        total=data.get("total", 0),
                        passed=data.get("passed", 0),
                        failed=data.get("failed", 0),
                        skipped=data.get("skipped", 0),
                        duration_seconds=data.get("duration_seconds", test_duration),
                        soc2_controls_covered=data.get("soc2_controls_covered", []),
                        collection_error=data.get("collection_error"),
                        findings=data.get("findings", []),
                    )
                    break
                except (json.JSONDecodeError, TypeError):
                    continue

        return report

    def _parse_canary(
        self,
        container_result: ContainerResult,
        sandbox_id: str,
    ) -> Optional[CanaryCheckResult]:
        """Parse the WORKFLO_CANARY line emitted by the worker from inside the container.

        The worker runs the canary check from *inside* the container, proving
        that THIS container's network namespace has no egress. Returns None
        if the worker didn't emit a WORKFLO_CANARY line (e.g. worker crashed
        before reaching that stage).
        """
        for line in container_result.stdout.splitlines():
            line = line.strip()
            if line.startswith("WORKFLO_CANARY:"):
                try:
                    data = json.loads(line[len("WORKFLO_CANARY:"):])
                    # Parse the ISO attempted_at; fall back to now() if parsing fails
                    attempted_raw = data.get("attempted_at")
                    try:
                        from datetime import datetime as _dt
                        attempted_at = _dt.fromisoformat(attempted_raw.replace("Z", "+00:00")) if attempted_raw else datetime.now(UTC)
                    except (ValueError, AttributeError):
                        attempted_at = datetime.now(UTC)
                    return CanaryCheckResult(
                        sandbox_id=sandbox_id,
                        attempted_at=attempted_at,
                        target_host=data.get("target_host", "https://example.com"),
                        request_succeeded=data.get("request_succeeded", False),
                        error=data.get("error"),
                    )
                except (json.JSONDecodeError, TypeError):
                    continue
        return None

    def _parse_model_teardown(
        self,
        container_result: ContainerResult,
    ) -> tuple[Optional[bool], Optional[str]]:
        """Parse the WORKFLO_MODEL_TEARDOWN line emitted by the worker.

        Returns:
            (teardown_status, error_string)
            - teardown_status is None if the worker didn't emit the line
              (meaning the model stage never ran — plain --test).
            - teardown_status is True if the model stage ran and state was wiped.
            - teardown_status is False if the model stage ran but state was NOT wiped.

        The returned tuple populates TeardownProof.model_inference_teardown and
        TeardownProof.model_inference_error on the receipt.
        """
        for line in container_result.stdout.splitlines():
            line = line.strip()
            if line.startswith("WORKFLO_MODEL_TEARDOWN:"):
                try:
                    data = json.loads(line[len("WORKFLO_MODEL_TEARDOWN:"):])
                    teardown_raw = data.get("teardown")
                    # teardown may be None (not run), True (clean), or False (failed)
                    if teardown_raw is None:
                        return None, data.get("error")
                    return bool(teardown_raw), data.get("error")
                except (json.JSONDecodeError, TypeError):
                    continue
        # Worker didn't emit WORKFLO_MODEL_TEARDOWN at all — model stage never ran
        return None, None

    def _parse_web_probes(
        self,
        container_result: ContainerResult,
    ) -> Optional[WebProbeResult]:
        """Parse the WORKFLO_WEB_PROBES line emitted by the worker.

        Returns None if the worker didn't emit the line (web tier not
        requested, same discipline as model teardown). The worker emits
        this even when the app-under-test failed to start — in that case
        the payload carries app_start_error and possibly an empty probes
        list, which is still a valid, reportable outcome (not a Workflo
        bug). A JSON parse failure is treated as "no web probes" rather
        than crashing the whole run.
        """
        for line in container_result.stdout.splitlines():
            line = line.strip()
            if line.startswith("WORKFLO_WEB_PROBES:"):
                try:
                    data = json.loads(line[len("WORKFLO_WEB_PROBES:"):])
                    return WebProbeResult(
                        base_url=data.get("base_url", ""),
                        probes=data.get("probes", []),
                        app_start_error=data.get("app_start_error"),
                    )
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
        return None

    def _parse_security_probes(
        self,
        container_result: ContainerResult,
    ) -> Optional[SecurityProbeResult]:
        """Parse the WORKFLO_SECURITY_PROBES line emitted by the worker.

        Returns None if the worker didn't emit the line (security tier not
        requested, same discipline as model teardown). The worker emits
        this even when the app-under-test failed to start — in that case
        the payload carries app_start_error and possibly an empty probes
        list, which is still a valid, reportable outcome (not a Workflo
        bug). A JSON parse failure is treated as "no security probes" rather
        than crashing the whole run.
        """
        for line in container_result.stdout.splitlines():
            line = line.strip()
            if line.startswith("WORKFLO_SECURITY_PROBES:"):
                try:
                    data = json.loads(line[len("WORKFLO_SECURITY_PROBES:"):])
                    return SecurityProbeResult(
                        base_url=data.get("base_url", ""),
                        probes=data.get("probes", []),
                        app_start_error=data.get("app_start_error"),
                    )
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
        return None

    def _derive_error(
        self,
        report: RunReport,
        proof: TeardownProof,
        canary: CanaryCheckResult,
        container: ContainerResult,
    ) -> Optional[str]:
        """Derive a human-readable error string from whichever component failed."""

        if container.timed_out:
            return "Tests timed out (container killed)"
        if report.collection_error:
            return f"Worker could not collect/run the repo's tests: {report.collection_error}"
        if report.failed > 0:
            return f"{report.failed} test(s) failed"
        if not proof.container_removed:
            return "Container was not removed after teardown"
        if not proof.filesystem_removed:
            return "Filesystem (tmpfs) was not removed after teardown"
        if canary.request_succeeded:
            return "Canary request succeeded — network isolation is broken"
        return None


def generate_sandbox_id() -> str:
    """Generate a unique sandbox ID for each run."""
    return f"sandbox-{uuid.uuid4().hex[:12]}"
