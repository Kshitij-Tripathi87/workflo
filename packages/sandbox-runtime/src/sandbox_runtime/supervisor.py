"""Supervisor - orchestrates full sandbox lifecycle.

Lifecycle (every step emits an event into the hash-chained evidence ledger):

    preflight -> validate -> snapshot repo -> resolve deps -> build rootfs
    -> create isolation (cgroups + netns) -> isolation probes (INSIDE the
    sandbox, fail-closed) -> tests -> app (if web/deep/security tier) ->
    agent/browser workers -> teardown + VERIFICATION -> unsigned receipt.

The supervisor never holds a signing key. It produces an unsigned
SignedReceipt payload (with the evidence binding digests); the caller —
CLI or daemon — signs it. A compromised supervisor therefore cannot
forge receipts.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from datetime import datetime, UTC
from pathlib import Path
from dataclasses import asdict

from sandbox_runtime.config import RunConfig, RunResult, WorkloadType, NetworkMode, ProbeResult
from sandbox_runtime.bwrap import run_bwrap
from sandbox_runtime.cgroups import CgroupConfig, setup_cgroup, attach_process
from sandbox_runtime.network import NetworkConfig, setup_private_network
from sandbox_runtime.rootfs import RootfsConfig, prepare_rootfs
from sandbox_runtime.snapshot import SnapshotConfig, create_snapshot
from sandbox_runtime.deps import DepConfig, resolve_dependencies
from sandbox_runtime.workloads import (
    run_app_workload, run_test_workload, run_agent_workload, run_browser_workload
)
from sandbox_runtime.evidence import EvidenceCollector
from sandbox_runtime.teardown import (
    TeardownVerification,
    teardown_and_verify,
    teardown_proof_fields,
)


def _json_safe(value):
    """Recursively convert a value into JSON-serializable primitives.

    RunConfig contains Path objects; the evidence ledger must only ever
    hold plain JSON types (the hash chain is computed over the JSON dump).
    """
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class Supervisor:
    """Main supervisor - orchestrates full sandbox lifecycle."""

    def __init__(self, config: RunConfig):
        self.config = config
        # Coerce str inputs (dataclasses don't enforce annotations; the
        # CLI and daemon IPC both hand us plain JSON types).
        if self.config.repo_path is not None and not isinstance(self.config.repo_path, Path):
            self.config.repo_path = Path(self.config.repo_path)
        if self.config.runtime_image is not None and not isinstance(self.config.runtime_image, Path):
            self.config.runtime_image = Path(self.config.runtime_image)
        if self.config.evidence_dir is not None and not isinstance(self.config.evidence_dir, Path):
            self.config.evidence_dir = Path(self.config.evidence_dir)
        # Run layout:
        #   <evidence_dir>/<sandbox_id>/          - run root (receipt lives here)
        #   <evidence_dir>/<sandbox_id>/evidence/ - evidence bundle (SURVIVES teardown)
        #   <evidence_dir>/<sandbox_id>/workspace|- tmp | home | deps  - REMOVED at teardown
        self._run_dir = config.evidence_dir / config.sandbox_id
        self.evidence = EvidenceCollector(self._run_dir / "evidence")
        self.lifecycle_events = []
        self.processes = {}  # workload name -> Popen (registered for teardown)
        self.cgroup_path = None
        self.network_config = None
        self.canary_result = None  # from the in-sandbox probe report
        self.teardown_verification: TeardownVerification | None = None
        self._started_at = None
        self._receipt_payload = None
        self._last_test_result = {}
        self._app_log_path = None
        self.agent_activity = None  # governed agent tool summary
        # Repository provenance (git-url runs): which ref was requested,
        # which exact commit it resolved to, and the snapshot tree digest.
        self.repo_provenance: Optional[dict] = None
        # Judge outputs: findings produced from the agent's governed
        # records, and the ledger event ids each record maps to
        # (evidence_refs for findings).
        self._findings: list[dict] = []
        self._tool_event_ids: dict[int, str] = {}
        # Full governed records from the last agent run (evidence pipeline
        # only — never serialized into the receipt) — the Judge consumes
        # these whether it's driven inline or via the orchestrator.
        self._last_agent_records_full: list[dict] = []
        # Security posture (spec §5.3): enforcement outcomes collected
        # during the run, reported in the receipt's security_attestation.
        self._cgroup_attach_failures: list[str] = []
        self.landlock_abi = 0          # host-side kernel probe result
        self.landlock_requested = False
        self._current_stage = "preflight"
        self.run_status: Optional[str] = None
        self.failure_stage: Optional[str] = None
        # Day 13: live console state — a ~4KB always-current snapshot the
        # local app reads while the run is happening. It is a VIEW, never
        # evidence: nothing consumes it for trust decisions.
        from sandbox_runtime.run_state import RunStateWriter
        self._run_state = RunStateWriter(self._run_dir)

    # The current stage is a property so every transition also updates the
    # console state file: entering a stage marks it active; the previous
    # stage (if still active) is marked passed.
    @property
    def _current_stage(self) -> str:
        return self.__stage

    @_current_stage.setter
    def _current_stage(self, value: str) -> None:
        previous = getattr(self, "_Supervisor__stage", None)
        self.__stage = value
        writer = getattr(self, "_run_state", None)
        if writer is not None:
            if previous and previous != value:
                writer.on_stage(previous, "pass")
            writer.on_stage(value, "active")

    @property
    def security_mode(self) -> str:
        mode = getattr(self.config, "security_mode", "compatible")
        return "hardened" if mode == "hardened" else "compatible"

    def emit(self, event: str, detail: dict = None):
        evt = {
            "event": event,
            "timestamp": datetime.now(UTC).isoformat(),
            "detail": _json_safe(detail or {}),
        }
        self.lifecycle_events.append(evt)
        event_id = self.evidence.write_event(event, evt["detail"])
        # Console mirror (best-effort: the ledger is the authority).
        state = getattr(self, "_run_state", None)
        if state is not None:
            try:
                state.on_event(event, evt["detail"])
            except Exception:
                pass
        return event_id

    def register_process(self, name: str, proc) -> None:
        """Track a workload process so teardown can terminate and verify it.

        Also attaches the process to the sandbox cgroup so resource
        limits (memory/cpu/pids) are actually enforced on it.

        F-5: an attach failure is never silent. In hardened mode it
        aborts the run — Workflo must not believe in a resource boundary
        that was never applied. In compatible mode it is recorded as
        evidence and the receipt reports cgroup_attached=false.
        """
        if proc is None:
            return
        self.processes[name] = proc
        if self.cgroup_path is not None:
            try:
                attach_process(self.cgroup_path, proc.pid)
            except OSError as e:
                self._cgroup_attach_failures.append(name)
                self.emit("CGROUP_ATTACH_FAILED", {
                    "workload": name, "pid": proc.pid, "error": str(e),
                    "security_mode": self.security_mode,
                })
                if self.security_mode == "hardened":
                    raise RuntimeError(
                        f"cgroup attach failed for {name} (pid {proc.pid}) "
                        f"in hardened mode: {e}"
                    )
        else:
            # No cgroup exists at all — the primary enforcement path
            # (pre-exec cgroup join in run_bwrap) could not have applied
            # either. Record it; hardened mode refuses.
            self._cgroup_attach_failures.append(name)
            self.emit("CGROUP_NOT_ATTACHED", {
                "workload": name, "reason": "no_cgroup",
                "security_mode": self.security_mode,
            })
            if self.security_mode == "hardened":
                raise RuntimeError(
                    f"no cgroup exists — cannot enforce limits on {name} "
                    "in hardened mode"
                )

    async def run(self) -> RunResult:
        """Execute full sandbox lifecycle."""
        self._started_at = time.monotonic()
        self.emit("created", {"config": asdict(self.config)})

        try:
            # 1. Preflight checks (any failure = CONFIGURATION_ERROR)
            self._current_stage = "preflight"
            await self._preflight()

            # 2. Validate project config
            self._current_stage = "config"
            self._validate_config()

            # 3. Snapshot repository
            self._current_stage = "snapshot"
            await self._snapshot_repo()

            # 4. Resolve dependencies
            self._current_stage = "deps"
            await self._resolve_deps()

            # 5. Build rootfs
            self._current_stage = "rootfs"
            await self._build_rootfs()

            # 6. Create namespaces + cgroups + network
            self._current_stage = "isolation"
            await self._create_isolation()

            # 7. Run isolation probes INSIDE the sandbox (FAIL CLOSED)
            self._current_stage = "probes"
            await self._run_probes()

            # 8. Start evidence collector
            self.evidence.start()

            # 9. Run deterministic tests
            self._current_stage = "tests"
            test_result = await run_test_workload(self.config, self.evidence)
            self._last_test_result = test_result
            self.register_process("test", test_result.get("proc"))
            self.emit("tests_completed", {
                "returncode": test_result.get("returncode"),
                "total": test_result.get("total", 0),
                "passed": test_result.get("passed", 0),
                "failed": test_result.get("failed", 0),
                "duration_seconds": test_result.get("duration_seconds", 0.0),
            })

            # 10. Start app (if web/deep/security tier needs it)
            self._current_stage = "app"
            app_result = None
            if any(tier in self.config.probe_groups for tier in ["web", "security", "deep", "aggressive"]):
                app_result = await run_app_workload(self.config, self.evidence)
                self.register_process("app", app_result.get("proc"))
                self._app_log_path = app_result.get("app_log_path")
                self._app_log_handle = app_result.get("app_log")

            # 11. Start agent/browser workers
            self._current_stage = "agent"
            if "deep" in self.config.probe_groups or "aggressive" in self.config.probe_groups:
                agent_result = await run_agent_workload(self.config, self.evidence)
                self.register_process("agent", agent_result.get("proc"))
                self.agent_activity = agent_result.get("activity")
                # Planner-mode events through emit() (receipt trail + ledger)
                if agent_result.get("planner_enabled"):
                    self.emit("AGENT_PLANNER_ENABLED", {"mode": "llm"})
                elif getattr(self.config, "agent_planner", False):
                    self.emit("AGENT_PLANNER_FALLBACK", {"mode": "task_spec"})
                for evt in agent_result.get("planner_events", []):
                    self.emit("AGENT_PLANNER_EVENT", evt)
                # Ingest the agent's self-reported tool records into the
                # lifecycle/event trail (emit writes BOTH the receipt's
                # event list and the hash-chained ledger).
                self.emit("AGENT_REPORTED", {
                    "steps_total": self.agent_activity.get("steps_total", 0),
                    "steps_completed": self.agent_activity.get("steps_completed", 0),
                    "steps_failed": self.agent_activity.get("steps_failed", 0),
                    "tool_calls": self.agent_activity.get("tool_calls", 0),
                    "denied_attempts": self.agent_activity.get("denied_attempts", 0),
                })
                for record in agent_result.get("records", []):
                    evt_id = self.emit("AGENT_TOOL_CALL", record)
                    seq = record.get("seq")
                    if isinstance(seq, int):
                        self._tool_event_ids[seq] = evt_id
                # Day 10: the deterministic Judge reads the FULL governed
                # records (kept out of the receipt; evidence-ledger only) and
                # converts reproduced, localized failures into findings.
                from sandbox_runtime.judge import judge_findings
                full_records = agent_result.get("records_full", [])
                self._last_agent_records_full = full_records
                judged = judge_findings(full_records, self._tool_event_ids)
                self._findings = judged.findings
                if judged.hypotheses:
                    self.emit("FINDINGS_JUDGED", {
                        "hypotheses": judged.hypotheses,
                        "confirmed": judged.confirmed,
                        "reported": judged.reported,
                    })

            if "web" in self.config.probe_groups:
                browser_result = await run_browser_workload(self.config, self.evidence)
                self.register_process("browser", browser_result.get("proc"))

            # 12. Teardown + VERIFICATION (fail-closed)
            self._current_stage = "teardown"
            await self._teardown()

            # 13. Build unsigned receipt payload (with evidence binding)
            if self.teardown_verification is not None and \
                    self.teardown_verification.all_verified:
                self.run_status = "completed"
            else:
                self.run_status = "failed"
                self.failure_stage = "teardown"
            self._current_stage = "receipt"
            receipt_path = await self._build_receipt()

            elapsed = time.monotonic() - self._started_at
            teardown_ok = bool(self.teardown_verification and self.teardown_verification.all_verified)
            self._run_state.finish(self.run_status or "completed", self.failure_stage)

            return RunResult(
                sandbox_id=self.config.sandbox_id,
                success=teardown_ok,
                receipt_path=receipt_path,
                lifecycle_events=self.lifecycle_events,
                receipt_payload=self._receipt_payload,
                evidence_dir=self.evidence.evidence_dir,
                teardown_verified=teardown_ok,
                elapsed_seconds=elapsed,
            )

        except Exception as e:
            self.emit("error", {"error": str(e), "stage": self._current_stage})
            await self._emergency_teardown()
            elapsed = time.monotonic() - self._started_at if self._started_at else 0.0
            self.run_status = "failed"
            self.failure_stage = self._current_stage
            self._run_state.finish("failed", self.failure_stage)
            # Failure receipts are still produced (and still signed by the
            # caller) — a failed run must be provable, not invisible.
            try:
                receipt_path = await self._build_receipt()
            except Exception:
                receipt_path = None
            return RunResult(
                sandbox_id=self.config.sandbox_id,
                success=False,
                error=str(e),
                receipt_path=receipt_path,
                lifecycle_events=self.lifecycle_events,
                receipt_payload=self._receipt_payload,
                evidence_dir=self.evidence.evidence_dir,
                teardown_verified=bool(
                    self.teardown_verification and self.teardown_verification.all_verified
                ),
                elapsed_seconds=elapsed,
            )

    async def _preflight(self):
        """Validate host environment."""
        checks = [
            ("Linux namespaces", self._check_namespaces),
            ("cgroups v2", self._check_cgroups_v2),
            ("seccomp", self._check_seccomp),
            ("bwrap", self._check_bwrap),
            ("runtime image", self._check_runtime_image),
        ]

        for name, check in checks:
            try:
                check()
                self.emit("preflight_pass", {"check": name})
            except Exception as e:
                self.emit("preflight_fail", {"check": name, "error": str(e)})
                raise RuntimeError(f"Preflight failed: {name}: {e}")

    def _check_namespaces(self):
        result = subprocess.run(["unshare", "--user", "--pid", "true"], capture_output=True)
        if result.returncode != 0:
            raise RuntimeError("User/PID namespaces not available")

    def _check_cgroups_v2(self):
        if not Path("/sys/fs/cgroup/cgroup.controllers").exists():
            raise RuntimeError("cgroups v2 not mounted")

    def _check_seccomp(self):
        with open("/proc/self/status") as f:
            if "Seccomp:" not in f.read():
                raise RuntimeError("seccomp not supported")

    def _check_bwrap(self):
        result = subprocess.run(["bwrap", "--version"], capture_output=True)
        if result.returncode != 0:
            raise RuntimeError("bwrap not installed")

    def _check_runtime_image(self):
        if not self.config.runtime_image.exists():
            raise RuntimeError(f"Runtime image not found: {self.config.runtime_image}")

    def _validate_config(self):
        self.emit("config_validated", {})

    async def _snapshot_repo(self):
        # The snapshot ALWAYS lands in the run workspace — the user's
        # original repo is never mutated.
        workspace_repo = self._workspace_dir / "repo"
        if self.config.repo_path:
            snapshot_config = SnapshotConfig(
                repo_path=self.config.repo_path,
                sandbox_id=self.config.sandbox_id,
                dest_dir=workspace_repo,
            )
        else:
            # GitHub connector: parse the URL, resolve the requested ref to
            # an EXACT commit SHA (a branch is a moving target — a receipt
            # must name the commit), then clone pinned at that commit. The
            # clone lands in a run-local staging dir; create_snapshot then
            # copies it into the workspace with secret exclusion applied.
            from sandbox_runtime.github_connector import (
                build_provenance, clone_pinned, parse_repository_url, resolve_ref,
            )
            spec = parse_repository_url(self.config.repo_url)
            resolved = resolve_ref(spec.clone_url, self.config.commit_sha)
            self.emit("repository_resolved", {
                "provider": spec.provider,
                "repository": spec.repository,
                "ref": resolved.requested_ref,
                "commit": resolved.commit_sha,
            })
            staging = self._run_dir / "clone-staging"
            clone_pinned(spec.clone_url, resolved.commit_sha, staging / "repo")
            self.repo_provenance = build_provenance(spec, resolved)
            snapshot_config = SnapshotConfig(
                repo_path=staging / "repo",
                sandbox_id=self.config.sandbox_id,
                dest_dir=workspace_repo,
            )

        result = create_snapshot(snapshot_config)
        if self.repo_provenance is not None:
            # Bind the exact tree that entered the sandbox to the resolved
            # commit — together they pin the run byte-for-byte.
            self.repo_provenance["snapshot_digest"] = result.tree_sha256
        self.emit("snapshot_created", {
            "tree_sha256": result.tree_sha256,
            "files": result.files,
            "excluded": result.excluded[:10]
        })
        return result

    @property
    def _workspace_dir(self) -> Path:
        return self._run_dir / "workspace"

    async def _resolve_deps(self):
        # Resolve against the SNAPSHOT (the sealed source of truth), never
        # the user's original repo.
        dep_config = DepConfig(
            mode=self.config.dep_mode,
            repo_path=self._workspace_dir / "repo",
            cache_dir=self._run_dir / "deps"
        )
        result = resolve_dependencies(dep_config)
        self.emit("dependencies_resolved", {
            "mode": result.mode.value,
            "lockfile_sha": result.lockfile_sha256,
            "cache_sha": result.cache_manifest_sha256
        })
        return result

    async def _build_rootfs(self):
        # Prepare writable bind sources: workspace, evidence ARTIFACTS, tmp, home.
        # Only the artifacts dir is exposed to the sandbox (/workflo/artifacts);
        # the ledger, logs and traces stay host-side and untamperable.
        workspace = self._workspace_dir
        evidence = self.evidence.artifacts_dir
        tmp = self._run_dir / "tmp"
        home = self._run_dir / "home"

        for d in [workspace, evidence, tmp, home]:
            d.mkdir(parents=True, exist_ok=True)

        # bwrap maps the sandbox's uid 0 to the launcher's effective uid
        # (it creates its own mapping with --unshare-user), so every
        # writable bind must be owned by the user running the supervisor
        # or the sandbox gets EACCES on its own workspace. Recursive for
        # the workspace — the snapshot copied files with mixed ownership.
        if hasattr(os, "chown"):
            uid = os.geteuid()
            gid = os.getegid()
            try:
                self._chown_tree(workspace, uid, gid)
                for d in [evidence, tmp, home]:
                    os.chown(d, uid, gid)
            except PermissionError:
                # Not the owner / no CAP_CHOWN: the chown is required for
                # the sandbox to write its own binds, so a failure here
                # will surface as a sandbox write error — visible, not silent.
                pass

        rootfs_config = RootfsConfig(
            sandbox_id=self.config.sandbox_id,
            base_image=self.config.runtime_image,
            workspace_src=workspace,
            evidence_src=evidence,
            tmp_src=tmp,
            home_src=home,
        )
        prepare_rootfs(rootfs_config)
        self.emit("rootfs_built", {})

    @staticmethod
    def _chown_tree(root: Path, uid: int, gid: int) -> None:
        import shutil as _shutil
        _shutil.chown(root, uid, gid)
        for path in root.rglob("*"):
            _shutil.chown(path, uid, gid)

    async def _create_isolation(self):
        # Cgroups
        cgroup_config = CgroupConfig(
            sandbox_id=self.config.sandbox_id,
            memory_mb=self.config.memory_mb,
            cpu_cores=self.config.cpu_cores,
        )
        self.cgroup_path = setup_cgroup(cgroup_config)
        # Workloads read this to join the cgroup before exec (so limits
        # apply to the sandboxed process tree, not just the launcher)
        self.config.cgroup_path = self.cgroup_path

        # Network
        self.network_config = NetworkConfig(sandbox_id=self.config.sandbox_id)
        setup_private_network(self.network_config)

        # Landlock: host-side kernel ABI probe (host and sandbox share the
        # kernel). In hardened mode an unsupported kernel REFUSES the run
        # before anything is spawned; in compatible mode the run proceeds
        # and the receipt records reduced isolation — never a silent
        # downgrade (spec §5.3, F-1/F-2).
        from sandbox_runtime.landlock import probe_abi
        self.landlock_abi = probe_abi()
        if self.landlock_abi > 0:
            self.landlock_requested = True
            self.config.landlock_requested = True
            self.emit("LANDLOCK_AVAILABLE", {
                "abi": self.landlock_abi,
                "security_mode": self.security_mode,
            })
        else:
            self.emit("LANDLOCK_UNAVAILABLE", {
                "reason": "unsupported_kernel",
                "security_mode": self.security_mode,
            })
            if self.security_mode == "hardened":
                raise RuntimeError(
                    "Landlock is not supported by this kernel and "
                    "security_mode=hardened — refusing to run (fail closed)"
                )

        self.emit("isolation_created", {
            "cgroup": str(self.cgroup_path),
            "netns": self.network_config.netns_name,
            "landlock_abi": self.landlock_abi,
        })

    async def _run_probes(self):
        """Run isolation probes INSIDE a probe sandbox, fail closed.

        The probe process runs under the same bwrap isolation as the real
        workloads (namespaces, seccomp, read-only root) AND joins the
        private network namespace (veth + dnsmasq + nftables) so the
        probes observe the sandbox's real view of the network. It
        reports a JSON object on stdout: probe results plus the egress
        canary.

        The internal-reachability probe is advisory at this stage (the
        app has not started yet); internal DNS resolution is critical.
        """
        from sandbox_runtime.config import BwrapConfig
        from sandbox_runtime.seccomp import get_seccomp_profile
        from sandbox_runtime.landlock import rules_for_workload

        # resolv.conf pointing at the netns dnsmasq
        resolv_conf = self._run_dir / "resolv.conf"
        resolv_conf.write_text(f"nameserver {self.network_config.dns_ip}\n")

        probe_config = BwrapConfig(
            sandbox_id=f"{self.config.sandbox_id}-probe",
            workload_type=WorkloadType.TEST,
            readonly_root=self.config.runtime_image,
            workspace_dir=self._workspace_dir,
            evidence_dir=self.evidence.artifacts_dir,
            tmp_dir=self._run_dir / "tmp",
            home_dir=self._run_dir / "home",
            memory_mb=512,
            cpu_cores=0.5,
            network_mode=NetworkMode.PRIVATE,
            netns=self.network_config.netns_name,
            resolv_conf=resolv_conf,
            seccomp_profile=get_seccomp_profile(WorkloadType.TEST),
            landlock_rules=(
                rules_for_workload(WorkloadType.TEST)
                if self.landlock_requested else []
            ),
            landlock_mode=self.security_mode,
            command=["python3", "-m", "sandbox_runtime.probes_report"],
            env={
                "PYTHONPATH": "/opt/workflo/runtime",
                "PATH": "/usr/bin:/bin",
                "HOME": "/home/workflo",
            },
            workdir="/workspace",
            cgroup_procs=(
                self.cgroup_path / "cgroup.procs" if self.cgroup_path else None
            ),
        )

        proc = run_bwrap(probe_config)
        self.register_process("probe", proc)

        loop = asyncio.get_event_loop()
        try:
            stdout, stderr = await loop.run_in_executor(
                None, lambda: proc.communicate(timeout=60)
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise RuntimeError("Isolation probes timed out — treating as failed (fail closed)")

        if proc.returncode != 0:
            raise RuntimeError(
                f"Probe process failed (exit {proc.returncode}): "
                f"{(stderr or b'').decode(errors='replace')[:500]}"
            )

        try:
            report = json.loads(stdout.decode(errors="replace"))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Probe report is not valid JSON: {e}")

        probes = [ProbeResult(**p) for p in report.get("probes", [])]
        self.canary_result = report.get("canary")

        # Canary: a real egress attempt that MUST have failed.
        if not self.canary_result or self.canary_result.get("request_succeeded"):
            raise RuntimeError(
                "Egress canary SUCCEEDED or is missing — network isolation is broken"
            )

        failed = [r for r in probes if not r.passed and r.severity == "critical"]
        if failed:
            details = "; ".join(f"{r.name}: {r.detail}" for r in failed)
            raise RuntimeError(f"Isolation verification failed: {details}")

        self.emit("probes_passed", {
            "count": len(probes),
            "canary_blocked": True,
        })

    async def _teardown(self):
        self.emit("teardown_started", {})

        # Ingest the app log into the host-side evidence BEFORE the
        # workspace (its bind source) is removed.
        self._ingest_app_log()

        # Writable binds that must NOT survive: workspace (repo copy),
        # tmp, home, browser profile, deps cache, clone staging. The
        # evidence directory intentionally survives — it backs the receipt.
        writable_paths = [
            self._workspace_dir,
            self._run_dir / "tmp",
            self._run_dir / "home",
            self._run_dir / "browser-profile",
            self._run_dir / "deps",
            self._run_dir / "clone-staging",
        ]

        self.teardown_verification = teardown_and_verify(
            processes=self.processes,
            cgroup_path=self.cgroup_path,
            network_config=self.network_config,
            writable_paths=writable_paths,
        )

        # Evidence collection stops after teardown verification so the
        # teardown evidence itself is part of the ledger.
        self.evidence.stop()

        self.emit("destroyed", {
            "teardown_verified": self.teardown_verification.all_verified,
            "processes_terminated": self.teardown_verification.processes_terminated,
            "cgroup_removed": self.teardown_verification.cgroup_removed,
            "network_namespace_removed": self.teardown_verification.network_namespace_removed,
            "workspace_removed": self.teardown_verification.workspace_removed,
            "cgroup_drain": self.teardown_verification.details.get("cgroup_drain"),
        })

    def _ingest_app_log(self) -> None:
        """Copy the app-under-test's log into the evidence ledger and
        release the supervisor's append handle on it."""
        if self._app_log_path is None:
            return
        try:
            path = Path(self._app_log_path)
            if path.exists():
                content = path.read_text(errors="replace")
                if content.strip():
                    self.evidence.write_log("app", content)
        except OSError:
            pass
        finally:
            handle = getattr(self, "_app_log_handle", None)
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass
                self._app_log_handle = None

    async def _emergency_teardown(self):
        try:
            await self._teardown()
        except Exception:
            pass

    def _landlock_outcome(self) -> tuple[bool, Optional[str]]:
        """Aggregate the in-sandbox landlock-status files.

        The wrapper inside every Landlocked sandbox writes
        landlock-status-<workload>.json into the shared artifacts dir;
        the host reads them here. All workloads that ran under Landlock
        must report LANDLOCK_APPLIED — a single failure reduces the
        attestation (and would have failed the run in hardened mode).
        """
        if not self.landlock_requested:
            return False, "not_requested"
        statuses = []
        artifacts = self.evidence.artifacts_dir
        if artifacts.exists():
            for path in sorted(artifacts.glob("landlock-status-*.json")):
                try:
                    statuses.append(json.loads(path.read_text()))
                except (OSError, json.JSONDecodeError):
                    statuses.append({"status": "LANDLOCK_APPLY_FAILED",
                                     "reason": "status_unreadable"})
        if not statuses:
            return False, "no_status_reported"
        applied = [s for s in statuses if s.get("status") == "LANDLOCK_APPLIED"]
        if len(applied) == len(statuses):
            return True, None
        failed = next((s for s in statuses
                       if s.get("status") != "LANDLOCK_APPLIED"), {})
        return False, failed.get("status", "mixed_outcomes")

    async def _build_receipt(self) -> Path:
        """Finalize evidence and build the unsigned receipt payload.

        The payload is a SignedReceipt-compatible dict. The caller (CLI /
        daemon) signs it — the private key never enters the supervisor.
        """
        manifest_path = self.evidence.finalize(
            self.lifecycle_events,
            self.config.sandbox_id,
            self.config.sandbox_id
        )
        binding = self.evidence.build_binding()

        session_duration = (
            time.monotonic() - self._started_at if self._started_at else 0.0
        )

        test_result = getattr(self, "_last_test_result", None) or {}

        # TeardownProof from the VERIFIED post-teardown state
        if self.teardown_verification is not None:
            proof_fields = teardown_proof_fields(
                sandbox_id=self.config.sandbox_id,
                verification=self.teardown_verification,
                session_duration_seconds=session_duration,
                events_count=len(self.lifecycle_events),
            )
        else:
            # Teardown never ran (preflight/probe failure) — fail closed.
            proof_fields = {
                "sandbox_id": self.config.sandbox_id,
                "runtime_type": "namespaces",
                "destroyed_at": datetime.now(UTC).isoformat(),
                "container_removed": False,
                "filesystem_removed": False,
                "no_snapshot_retained": True,
                "session_duration_seconds": session_duration,
                "events_count": len(self.lifecycle_events),
            }

        # CanaryCheckResult from the in-sandbox probe report
        if self.canary_result:
            canary_fields = {
                "sandbox_id": self.config.sandbox_id,
                "attempted_at": datetime.now(UTC).isoformat(),
                "target_host": self.canary_result.get("target_host", "unknown"),
                "request_succeeded": bool(self.canary_result.get("request_succeeded")),
                "error": self.canary_result.get("error"),
            }
        else:
            canary_fields = {
                "sandbox_id": self.config.sandbox_id,
                "attempted_at": datetime.now(UTC).isoformat(),
                "target_host": "unknown",
                "request_succeeded": True,  # worst case: must fail verification
                "error": "canary never ran",
            }

        # Security attestation (spec §4 of the receipt plan): what
        # Workflo ACTUALLY enforced, derived from observed outcomes —
        # host kernel probe, in-sandbox landlock-status files, cgroup
        # attach results. This is an attestation of the execution
        # environment, not of the workload.
        landlock_applied, landlock_reason = self._landlock_outcome()

        payload = {
            "sandbox_id": self.config.sandbox_id,
            "receipt_version": 4,
            "issued_at": datetime.now(UTC).isoformat(),
            "run_report": {
                "sandbox_id": self.config.sandbox_id,
                "run_id": self.config.sandbox_id,
                "total": test_result.get("total", 0),
                "passed": test_result.get("passed", 0),
                "failed": test_result.get("failed", 0),
                "skipped": test_result.get("skipped", 0),
                "duration_seconds": test_result.get("duration_seconds", 0.0),
                "collection_error": test_result.get("collection_error"),
                # Judge output (Day 10/11): findings derived deterministically
                # from the agent's governed records. Empty when no agent tier
                # ran or nothing failed — never model-invented certainty.
                "findings": list(self._findings),
            },
            "teardown_proof": proof_fields,
            "canary_check": canary_fields,
            "lifecycle_events": [
                {
                    "sandbox_id": self.config.sandbox_id,
                    "event": evt["event"],
                    "timestamp": evt["timestamp"],
                    "detail": evt["detail"],
                }
                for evt in self.lifecycle_events
            ],
            "evidence_binding": binding,
            "agent_activity": self.agent_activity,
            "security_attestation": {
                "security_mode": self.security_mode,
                "landlock": {
                    "requested": self.landlock_requested,
                    "applied": landlock_applied,
                    "abi_version": self.landlock_abi or None,
                    "reason": landlock_reason,
                },
                "cgroup_attached": not self._cgroup_attach_failures,
                "cgroup_attach_failures": list(self._cgroup_attach_failures),
                "seccomp_applied": True,
                "network_isolated": self.network_config is not None,
                "source_code_included": False,
            },
            "signature_algorithm": "ed25519",
        }

        # Repository provenance: which exact commit and tree the run
        # tested. Present for git-url runs; the key appears in the
        # canonical (signed) payload only when set.
        if self.repo_provenance is not None:
            payload["repository"] = self.repo_provenance

        # Phase 7 run status fields: included when set so the receipt
        # honestly says "failed at stage X" — never a fake success (R-2
        # in the contract's abort-first-class rule).
        if self.run_status is not None:
            payload["run_status"] = self.run_status
        if self.failure_stage is not None:
            payload["failure_stage"] = self.failure_stage

        self._receipt_payload = payload

        # Persist the UNSIGNED payload next to the evidence bundle. The
        # signed receipt is written by the caller after signing.
        receipt_path = self._run_dir / "receipt.unsigned.json"
        receipt_path.write_text(json.dumps(payload, indent=2, default=str))
        return receipt_path
