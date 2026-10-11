"""Sandbox lifecycle models — the contract for ephemeral, no-retention execution.

These models are the architectural enforcement of the Airlock privacy guarantee.
A SandboxSpec describes what to spin up; a SandboxReceipt proves what was spun
down. Nothing else survives a run by design — not source code, not prompts,
not logs of customer data — only these structured artifacts.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from workflo_schema.inference import InferenceProvenance

# Receipt protocol versions — the deliberate compatibility boundary.
#
#   1 = legacy Docker receipts: no receipt_version field in the JSON,
#       no evidence binding. canonical_payload does NOT include the
#       version for these (byte-compatibility with already-signed v1
#       receipts).
#   2 = namespace-runtime receipts: evidence binding present, version
#       field explicit, canonical_payload includes receipt_version.
#   3 = agent-runtime receipts: adds agent_activity (governed agent
#       tool-call summary) to the signed canonical payload.
#   4 = hosted-inference receipts: adds inference provenance to the
#       agent activity summary (gateway/direct mode, bounded-observation
#       and prompt/response hashes, request IDs).
#
# Verifiers reject versions outside the supported set with an explicit
# UNSUPPORTED_RECEIPT_VERSION error rather than a generic failure.
SUPPORTED_RECEIPT_VERSIONS = (1, 2, 3, 4)
CURRENT_RECEIPT_VERSION = 4


class SandboxSpec(BaseModel):
    """Input contract: what the Control Plane hands the Sandbox Executor."""

    sandbox_id: str = Field(description="Unique one-time ID for this sandbox run")
    repo_url: str = Field(description="Git URL to clone inside the sandbox")
    repo_path: Optional[str] = Field(
        default=None, description="Local directory path to copy into sandbox (instead of git clone)"
    )
    commit_sha: Optional[str] = Field(default=None, description="Pinned commit, if not HEAD")
    run_spec: dict = Field(
        description="The RunSpec dict passed through to the worker-engine payload"
    )
    # Hard limits — enforced by the executor, not configurable by the caller
    timeout_seconds: int = Field(default=600, ge=10, le=3600)
    memory_mb: int = Field(default=2048, ge=256, le=16384)
    cpu_cores: float = Field(default=2.0, ge=0.5, le=8.0)
    # Network: by default, egress is BLOCKED except back to the Control Plane status endpoint
    allowed_egress_hosts: list[str] = Field(
        default_factory=list,
        description="Hosts the sandbox may reach. Empty = no egress (default for privacy).",
    )
    # Two-stage dependency install (networked prep + sealed test).
    # When True, the executor runs Stage 1 with network ON to install
    # dependencies from the repo's manifest, then Stage 2 with network OFF
    # for the actual test run. Used only for local-folder inputs that need
    # dependency installation; --repo runs that don't need install stay
    # on the single-stage-after-clone flow.
    dependency_install: bool = Field(
        default=False,
        description=(
            "True = run a networked prep stage (Stage 1) to install "
            "dependencies from a detected package manifest before the "
            "sealed test stage (Stage 2). The receipt carries "
            "dependency_install_had_network=True so reviewers can see the "
            "two-stage flow was used."
        ),
    )


class SandboxLifecycleEvent(BaseModel):
    """One row in the sandbox's lifecycle log — emitted by the executor."""

    sandbox_id: str
    event: str  # "created" | "repo_cloned" | "tests_started" | "tests_completed" | "teardown_started" | "destroyed"
    timestamp: datetime
    detail: dict = Field(default_factory=dict)


class TeardownProof(BaseModel):
    """Evidence that the sandbox was actually destroyed, not just claimed to be."""

    sandbox_id: str
    container_id: Optional[str] = Field(default=None, description="Docker container ID at teardown")
    filesystem_wipe_method: str = Field(
        default="tmpfs_umount",
        description="How the filesystem was destroyed. tmpfs_umount = unmounted tmpfs volume.",
    )
    container_removed: bool = Field(
        default=False,
        description="True if the execution environment is confirmed gone after teardown. "
        "For runtime_type='docker': docker rm -f succeeded and post-check confirms no "
        "container exists. For runtime_type='namespaces': all tracked sandbox processes "
        "terminated AND the cgroup was removed AND the network namespace was deleted.",
    )
    filesystem_removed: bool = Field(
        default=False,
        description="True if post-teardown check confirms the sandbox filesystem no longer "
        "exists. Docker: tmpfs mount gone. Namespaces: workspace/tmp/home binds gone.",
    )
    no_snapshot_retained: bool = Field(
        default=True,
        description="True if no Docker commit/image snapshot was taken before destruction",
    )
    # Namespace-runtime teardown evidence (runtime_type='namespaces').
    # None = not applicable (Docker receipts). Each is the verified post-check
    # result, not the teardown command's exit status — fail-closed.
    runtime_type: Optional[str] = Field(
        default=None,
        description="Execution runtime this proof covers: 'docker' (default/legacy) or "
        "'namespaces' (bwrap + cgroups v2 + netns). Verifiers branch on this.",
    )
    processes_terminated: Optional[bool] = Field(
        default=None,
        description="Namespaces only: True if every tracked sandbox process is confirmed "
        "exited (poll() returncode set) after teardown.",
    )
    cgroup_removed: Optional[bool] = Field(
        default=None,
        description="Namespaces only: True if the sandbox cgroup directory is confirmed "
        "gone from /sys/fs/cgroup after teardown.",
    )
    network_namespace_removed: Optional[bool] = Field(
        default=None,
        description="Namespaces only: True if the sandbox network namespace is confirmed "
        "deleted after teardown.",
    )
    workspace_removed: Optional[bool] = Field(
        default=None,
        description="Namespaces only: True if the writable workspace (repo copy), tmp and "
        "home bind directories are confirmed gone after teardown. The evidence "
        "directory intentionally survives — it backs the receipt.",
    )
    # Model inference teardown — deep/aggressive stages own a local model
    # process and its ephemeral state. For surface/security runs, the model
    # stage never runs.
    #
    # We use Optional[bool] with default=None so the verifier can distinguish
    # three states cleanly:
    #   None = not applicable (plain --test, no model stage ran)
    #   True = model stage ran AND state was wiped (clean)
    #   False = model stage ran AND state was NOT wiped (FAIL CLOSED)
    #
    # Collapsing "not applicable" into False would mean every non-deep-test
    # receipt looks like a teardown failure.
    model_inference_teardown: Optional[bool] = Field(
        default=None,
        description=(
            "None = model stage never ran (--test/--security only); "
            "True = model stage ran and process/state teardown was verified; "
            "False = model stage ran but state was NOT wiped."
        ),
    )
    model_inference_error: Optional[str] = Field(
        default=None,
        description="Human-readable error if model_inference_teardown is False or None.",
    )
    destroyed_at: datetime
    # Session metadata — ephemeral summary, never source code or test artifacts.
    session_duration_seconds: float = Field(
        default=0.0,
        description="Wall-clock duration of the sandbox run from start to destroy.",
    )
    peak_memory_mb: int = Field(
        default=0,
        description="Peak RSS observed by the executor during the run (best-effort).",
    )
    peak_cpu_percent: float = Field(
        default=0.0,
        description="Peak CPU % observed by the executor during the run (best-effort).",
    )
    events_count: int = Field(
        default=0,
        description="Number of lifecycle events emitted during the run.",
    )


class CanaryCheckResult(BaseModel):
    """Result of the Claim #3 canary — a real outbound request that MUST fail."""

    sandbox_id: str
    attempted_at: datetime
    target_host: str = Field(
        default="https://example.com",
        description="Host the sandbox was asked to reach. Default is a known-good external host.",
    )
    request_succeeded: bool = Field(
        description="True ONLY if the sandbox could reach the target. Expected False.",
    )
    error: Optional[str] = Field(
        default=None,
        description="Connection error string if the request failed (expected case).",
    )


class RunReport(BaseModel):
    """The customer-facing result — test counts, not source code."""

    sandbox_id: str
    run_id: Optional[str] = None
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    soc2_controls_covered: list[str] = Field(default_factory=list)
    collection_error: Optional[str] = Field(
        default=None,
        description="Present when pytest could not collect or run the repo's "
        "tests (nonzero exit with nothing collected). Distinguishes a real "
        "'0 tests ran' from a clean '0/0 passed'.",
    )
    findings: list[dict] = Field(
        default_factory=list,
        description="Structured findings — test name + status + assertion. Never source code.",
    )


class WebProbeResult(BaseModel):
    """Outcome of the Playwright-driven browser probes (the `web` tier).

    None on the receipt = web tier not requested (same discipline as
    `model_inference_teardown`). When the web tier IS requested, this is
    populated even if the app-under-test failed to start — a broken app is
    a valid, reportable outcome (probe failed), not a Workflo bug.
    """

    base_url: str = Field(description="URL the probes were run against (e.g. http://127.0.0.1:5000)")
    probes: list[dict] = Field(
        default_factory=list,
        description="Per-probe results: {name, passed, detail}. Never contains source code.",
    )
    app_start_error: Optional[str] = Field(
        default=None,
        description="If the app under test could not be started/bound, the error message. "
        "Probes list may be empty when this is set.",
    )


class SecurityProbeResult(BaseModel):
    """Outcome of the API-driven security probes (the `security` tier).

    None on the receipt = security tier not requested (same discipline as
    `model_inference_teardown`). When the security tier IS requested, this is
    populated even if the app-under-test failed to start — a broken app is
    a valid, reportable outcome (probe failed), not a Workflo bug.

    The security tier uses the same app bootstrap primitive as the web tier
    but runs API-based security probes (tenant isolation, etc.) instead of
    Playwright browser probes.
    """

    base_url: str = Field(description="URL the probes were run against (e.g. http://127.0.0.1:5000)")
    probes: list[dict] = Field(
        default_factory=list,
        description="Per-probe results: {name, passed, detail}. Never contains source code.",
    )
    app_start_error: Optional[str] = Field(
        default=None,
        description="If the app under test could not be started/bound, the error message. "
        "Probes list may be empty when this is set.",
    )


class EvidenceBinding(BaseModel):
    """Cryptographic binding between a receipt and its evidence bundle.

    The sandbox runtime records every lifecycle event in a hash-chained
    JSONL ledger (events.jsonl) and finalizes it into a manifest with
    SHA-256 digests. These digests are embedded in the signed receipt, so
    the Ed25519 signature transitively covers the entire evidence chain:
    a verifier that has both the receipt and the evidence directory can
    (a) check the signature, (b) recompute the chain, and (c) confirm the
    digests match — proving the evidence was produced in the same run and
    was not altered afterwards.

    manifest_sha256 hashes the manifest.json file itself, pinning the
    exact manifest bytes the run produced.
    """

    evidence_dir: str = Field(
        description="Path to the evidence bundle directory (as produced by the run). "
        "May be relative to the run root; verifiers resolve it against the "
        "receipt's location or an explicitly provided --evidence path.",
    )
    events_count: int = Field(
        description="Number of events in the hash-chained ledger.",
    )
    events_sha256: str = Field(
        description="SHA-256 of the event hash chain (rolling hash of event hashes).",
    )
    bundle_sha256: str = Field(
        description="SHA-256 combining events, logs, traces and artifacts digests.",
    )
    manifest_sha256: str = Field(
        description="SHA-256 of the manifest.json file bytes.",
    )


class LocalModelProvenance(BaseModel):
    """Signed provenance for source-bearing inference inside the sandbox.

    Unlike hosted planner provenance, local inference may inspect the bounded
    repository snapshot. The endpoint must therefore be loopback-only and the
    exact base model, adapters, and serving image are cryptographically pinned.
    """

    backend: Literal["llamacpp"] = "llamacpp"
    model: str = Field(min_length=1, max_length=128)
    server_image: str = Field(
        pattern=r"^.+@sha256:[0-9a-f]{64}$",
        description="Immutable llama.cpp image reference.",
    )
    base_model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_sha256: dict[str, str]
    endpoint_scope: Literal["loopback"] = "loopback"
    source_code_included: Literal[True] = True
    requests: int = Field(default=0, ge=0, le=100)
    inference_seconds: float = Field(default=0.0, ge=0.0)
    error: Optional[str] = Field(default=None, max_length=1024)

    @field_validator("adapter_sha256")
    @classmethod
    def _exact_adapter_set(cls, value: dict[str, str]) -> dict[str, str]:
        expected = {"test-gen", "reasoning", "reporting"}
        if set(value) != expected:
            raise ValueError(f"adapter hashes must contain exactly {sorted(expected)}")
        for name, digest in value.items():
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError(f"adapter {name!r} has invalid SHA-256")
        return value


class AgentActivity(BaseModel):
    """Summary of governed agent tool activity during a run.

    The DETAILED records live in the evidence ledger (agent_tool_calls
    JSONL, ingested by the supervisor as hash-chained events and bound
    to the receipt via the evidence binding). This summary is the
    supervisor's signed claim about what the agent did, computed from
    those records.

    Trust note (v0.3): agent tool records are self-reported by the
    sandboxed process and notarized by the host. Host-observed evidence
    (isolation probes, canary, teardown) remains the stronger claim.
    """

    tool_calls: int = Field(
        default=0,
        description="Total governed tool calls made by the agent (allowed + denied).",
    )
    tools_used: list[str] = Field(
        default_factory=list,
        description="Distinct tools the agent invoked (e.g. http_get, read_log).",
    )
    steps_total: int = Field(
        default=0,
        description="Task steps the agent executed.",
    )
    steps_completed: int = Field(
        default=0,
        description="Task steps whose expectations were met (or observation-only).",
    )
    steps_failed: int = Field(
        default=0,
        description="Task steps that failed their expectations — a valid, "
        "reportable outcome (e.g. a broken app), not an infra crash.",
    )
    denied_attempts: int = Field(
        default=0,
        description="Tool calls REJECTED by the allowlist — the agent tried to "
        "do something outside its governance and was stopped.",
    )
    errors: int = Field(
        default=0,
        description="Allowed tool calls that failed at execution time.",
    )
    planner: str = Field(
        default="task_spec",
        description="Which planner drove the agent: 'task_spec' (deterministic "
        "default task) or 'llm' (host-side LLM planner, batch-driven).",
    )
    planner_note: Optional[str] = Field(
        default=None,
        description="Human-readable note about the planner (e.g. LLM fallback).",
    )
    inference_provenance: Optional["InferenceProvenance"] = Field(
        default=None,
        description="Hosted/direct inference provenance. None when the agent "
        "used no model planner. For gateway mode, source_code_included is "
        "always false and the hashes bind only bounded observations.",
    )
    mission: Optional[str] = Field(
        default=None,
        max_length=512,
        description="The user's natural-language testing mission for this run "
        "(from --instruction). None = no mission was given. Signed verbatim "
        "so a reviewer sees exactly what the agent was asked to do.",
    )


class LandlockAttestation(BaseModel):
    """Filesystem-isolation outcome for one run (Phase 6, spec §5.3).

    requested/applied are separate so a Landlock-unavailable host is
    VISIBLE in the receipt rather than silently downgraded: requested
    true + applied false + reason 'unsupported_kernel' means the run
    proceeded in compatible mode with namespace-only filesystem
    isolation. In hardened mode such a run never happens.
    """

    requested: bool = Field(
        default=False,
        description="True when the run was configured to apply Landlock.",
    )
    applied: bool = Field(
        default=False,
        description="True only when every Landlocked workload reported "
        "LANDLOCK_APPLIED from inside its sandbox.",
    )
    abi_version: Optional[int] = Field(
        default=None,
        description="Kernel Landlock ABI version observed by the host probe "
        "(1=5.13, 2=5.19, 3=6.2, ...). None when unsupported/not requested.",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Why Landlock was not applied: 'unsupported_kernel', "
        "'not_requested', 'no_status_reported', or a failure status.",
    )


class SecurityAttestation(BaseModel):
    """Machine-readable attestation of what Workflo ACTUALLY enforced.

    Derived from observed outcomes (kernel probes, in-sandbox status
    files, cgroup attach results) — not from configuration intent. The
    receipt hereby reports the execution environment itself, not just
    the test outcome.
    """

    security_mode: str = Field(
        default="compatible",
        description="'hardened' (enforcement failures abort the run) or "
        "'compatible' (failures are recorded and the run proceeds).",
    )
    landlock: LandlockAttestation = Field(
        default_factory=LandlockAttestation,
        description="Filesystem isolation outcome.",
    )
    cgroup_attached: bool = Field(
        default=True,
        description="True when every workload joined the resource cgroup "
        "successfully. False means some limits were never applied.",
    )
    cgroup_attach_failures: list[str] = Field(
        default_factory=list,
        description="Workloads whose cgroup attachment failed.",
    )
    seccomp_applied: bool = Field(
        default=True,
        description="True when syscall allowlists were compiled and passed "
        "to every sandbox.",
    )
    network_isolated: bool = Field(
        default=True,
        description="True when the run used the private netns (veth + "
        "dnsmasq + nftables workload-flow policy).",
    )
    source_code_included: bool = Field(
        default=False,
        description="Always false: source code never leaves the sandbox; "
        "only bounded runtime observations reach a hosted model.",
    )


class RepositoryProvenance(BaseModel):
    """Exactly which code the run tested.

    Resolved host-side BEFORE the snapshot: the connector turns the user's
    (possibly moving) ref into an exact commit SHA, and the supervisor
    binds the snapshot tree digest after the copy. Together they pin the
    run: the ref the user asked for, the commit it resolved to, and the
    hash of the tree that actually entered the sandbox.
    """

    provider: str = Field(
        description="git hosting provider, e.g. 'github'; 'git' for other hosts.",
    )
    repository: str = Field(
        description="owner/name as resolved from the clone URL.",
    )
    ref: Optional[str] = Field(
        default=None,
        description="The ref (branch/tag/SHA) the caller requested; None means the remote default branch.",
    )
    commit: str = Field(
        description="Exact commit SHA the ref resolved to at run time.",
    )
    snapshot_digest: Optional[str] = Field(
        default=None,
        description="SHA-256 of the snapshotted tree (post secret-exclusion) that entered the sandbox.",
    )


class SignedReceipt(BaseModel):
    """The tamper-evident receipt that closes every run. This is what survives."""

    # Populated by the model_validator below when absent in input:
    #   no evidence_binding and no explicit version -> 1 (legacy)
    #   evidence_binding present without agent activity -> 2 (interim
    #   namespace receipts from before explicit versioning)
    #   evidence_binding + agent activity without explicit version -> 3
    #   (interim agent receipts from before explicit v4 provenance)
    receipt_version: Optional[int] = Field(
        default=None,
        description="Receipt protocol version. None in input: inferred (1 for "
        "legacy receipts without evidence binding, 2 when a binding is present "
        "without agent activity, 3 when agent activity is present, and 4 when "
        "local-model provenance or inference provenance is present). "
        "Serialized receipts always carry an explicit version.",
    )
    sandbox_id: str
    issued_at: datetime
    run_report: RunReport
    teardown_proof: TeardownProof
    canary_check: CanaryCheckResult
    lifecycle_events: list[SandboxLifecycleEvent] = Field(default_factory=list)
    # Web probes — None when the web tier wasn't requested. Same three-state
    # discipline as model_inference_teardown: None = not applicable, never
    # conflated with "ran and everything failed".
    web_probes: Optional[WebProbeResult] = Field(
        default=None,
        description="None = web tier not requested. Populated (even with failing "
        "probes or an app-start error) when the web tier ran.",
    )
    # Security probes — None when the security tier wasn't requested. Same
    # three-state discipline as model_inference_teardown: None = not applicable,
    # never conflated with "ran and everything failed".
    security_probes: Optional[SecurityProbeResult] = Field(
        default=None,
        description="None = security tier not requested. Populated (even with failing "
        "probes or an app-start error) when the security tier ran.",
    )
    # Datahub writeback status — opt-in metadata only; no source code or test
    # artifacts are ever transmitted. When enabled, records that test results were
    # written to DataHub as assertions for downstream consumers.
    datahub_writeback: bool = Field(
        default=False,
        description="True = test results were written to DataHub as assertions.",
    )
    datahub_status: str = Field(
        default="none",
        description="Status of datahub writeback: 'none', 'success', 'failed'.",
    )
    # Security attestation (Phase 6): what Workflo actually enforced.
    # None on receipts produced before Phase 6 — the canonical payload
    # includes the key ONLY when set, so already-signed receipts keep
    # verifying byte-for-byte (same discipline as agent_activity/v3).
    security_attestation: Optional[SecurityAttestation] = Field(
        default=None,
        description="Attestation of the enforced execution environment "
        "(Landlock, cgroups, seccomp, network isolation, privacy). None "
        "on pre-Phase-6 receipts.",
    )
    # Run outcome (Phase 7, run_contract.md §5): every run — including a
    # FAILED one — produces a signed receipt that says which lifecycle
    # stage it died in. None/silent on success-compatible pre-Phase-7
    # receipts (canonical payload only includes these when set).
    run_status: Optional[str] = Field(
        default=None,
        description="'completed' or 'failed'. None on pre-Phase-7 receipts.",
    )
    failure_stage: Optional[str] = Field(
        default=None,
        description="Lifecycle stage that failed (e.g. 'preflight', "
        "'probes', 'app_start', 'teardown'). None unless run_status==failed.",
    )
    # The signature is over a canonical JSON of all the above fields
    signature_algorithm: str = Field(default="ed25519")
    public_key_fingerprint: Optional[str] = Field(
        default=None,
        description="SHA-256 fingerprint of the public key the receipt can be verified against. "
        "Filled by ReceiptSigner.sign(); None until signed.",
    )
    signature: Optional[str] = Field(
        default=None,
        description="Hex-encoded Ed25519 signature over the canonical payload. "
        "Filled by ReceiptSigner.sign(); None until signed.",
    )
    # Provenance fields — populated when the signing key was provisioned
    # via `workflo keygen --provision`. None for local-only keys. Verifiers
    # can use key_id to fetch the registered public key from Cortex's
    # directory and check status (active/revoked).
    key_id: Optional[str] = Field(
        default=None,
        description="Cortex key_id for the provisioned signing key. None for local-only keys.",
    )
    provisioned_at: Optional[str] = Field(
        default=None,
        description="ISO timestamp when the key was provisioned. None for local-only keys.",
    )
    device_id: Optional[str] = Field(
        default=None,
        description="Device identifier that provisioned the key. None for local-only keys.",
    )
    # Two-stage flow marker. False (default) means the run used the standard
    # single-stage-after-clone flow with --network none throughout, the strict
    # isolation guarantee already documented. True means the run went through
    # a networked prep stage (Stage 1) before the sealed test stage (Stage 2),
    # because the local-folder input had a package manifest requiring install
    # (e.g. requirements.txt). The TEST STAGE was still sealed — only Stage 1
    # had network access. This field makes the distinction explicit so a
    # reviewer reading the receipt knows the isolation guarantee is for the
    # TEST STAGE only when this is True.
    dependency_install_had_network: bool = Field(
        default=False,
        description=(
            "False = single-stage run, network=none throughout. "
            "True = two-stage run: Stage 1 (networked prep to install deps) "
            "ran before Stage 2 (sealed test, network=none). The test "
            "stage itself was still sealed; only the dependency-install "
            "stage had network access."
        ),
    )
    # Evidence bundle binding — None when the run produced no evidence
    # bundle (legacy Docker receipts). When present, the signature covers
    # these digests, binding the receipt to the exact evidence ledger.
    evidence_binding: Optional[EvidenceBinding] = Field(
        default=None,
        description="None = no evidence bundle (legacy receipts). Populated by the "
        "namespace runtime: digests of the hash-chained evidence ledger this "
        "receipt was produced from.",
    )
    # Governed agent activity summary — None when no agent tier ran.
    # The detailed tool-call records live in the evidence ledger; this is
    # the supervisor's signed summary computed from them.
    agent_activity: Optional[AgentActivity] = Field(
        default=None,
        description="None = no agent tier ran. Populated for deep/aggressive tiers: "
        "summary of the agent's governed tool activity (tool calls, denials, "
        "step outcomes).",
    )
    # Local source-bearing inference is separate from hosted planner
    # provenance: it is allowed only on loopback inside the sandbox.
    local_model_provenance: Optional[LocalModelProvenance] = Field(
        default=None,
        description="Pinned llama.cpp artifacts and request metrics for a local model stage.",
    )
    # Repository provenance — present for git-url runs. Which ref was asked
    # for, which exact commit it resolved to, and the digest of the tree
    # that entered the sandbox. Canonical payload includes the key ONLY
    # when set (same byte-compat discipline as security_attestation).
    repository: Optional[RepositoryProvenance] = Field(
        default=None,
        description="None = run used a local path or a legacy receipt. Populated "
        "for git-url runs: provider, repository, requested ref, resolved commit, "
        "and the snapshot tree digest.",
    )

    @model_validator(mode="after")
    def _resolve_receipt_version(self) -> "SignedReceipt":
        """Infer the protocol version when the field is absent.

        v1 = legacy Docker receipts (no evidence binding). v2 = evidence
        binding present (namespace runtime). Unknown explicit versions
        are REJECTED here so an incomprehensible receipt can never be
        silently treated as a known one — verifiers surface a clear
        UNSUPPORTED_RECEIPT_VERSION instead of a signature failure.
        """
        if self.receipt_version is None:
            if self.local_model_provenance is not None:
                # Local-model provenance was introduced with the current v4
                # protocol and must never masquerade as a legacy v1 receipt.
                self.receipt_version = 4
            elif self.evidence_binding is None:
                self.receipt_version = 1
            elif self.agent_activity is None:
                self.receipt_version = 2
            elif self.agent_activity.inference_provenance is not None:
                self.receipt_version = 4
            else:
                self.receipt_version = 3
        if self.receipt_version not in SUPPORTED_RECEIPT_VERSIONS:
            raise ValueError(
                f"UNSUPPORTED_RECEIPT_VERSION: receipt_version="
                f"{self.receipt_version} is not in supported set "
                f"{list(SUPPORTED_RECEIPT_VERSIONS)}"
            )
        return self

    def canonical_payload(self) -> str:
        """The exact bytes that were signed. Stable across runs.

        Version discipline: v1 receipts are canonicalized EXACTLY as the
        legacy code did (no receipt_version key) so already-signed v1
        receipts keep verifying. v2 receipts include the version.
        """
        import json

        payload = {
            "sandbox_id": self.sandbox_id,
            "issued_at": self.issued_at.isoformat(),
            "run_report": self.run_report.model_dump(mode="json"),
            "teardown_proof": self.teardown_proof.model_dump(mode="json"),
            "canary_check": self.canary_check.model_dump(mode="json"),
            "lifecycle_events": [e.model_dump(mode="json") for e in self.lifecycle_events],
            "web_probes": self.web_probes.model_dump(mode="json") if self.web_probes else None,
            "security_probes": self.security_probes.model_dump(mode="json") if self.security_probes else None,
            "signature_algorithm": self.signature_algorithm,
            "public_key_fingerprint": self.public_key_fingerprint or "",
            "key_id": self.key_id or "",
            "provisioned_at": self.provisioned_at or "",
            "device_id": self.device_id or "",
            "dependency_install_had_network": self.dependency_install_had_network,
            "evidence_binding": self.evidence_binding.model_dump(mode="json") if self.evidence_binding else None,
        }
        if self.receipt_version and self.receipt_version >= 2:
            payload["receipt_version"] = self.receipt_version
        if self.receipt_version and self.receipt_version >= 3:
            activity = (
                self.agent_activity.model_dump(mode="json") if self.agent_activity else None
            )
            if self.receipt_version == 3 and activity is not None:
                # v3 canonical bytes predate inference provenance — strip
                # it so v3 receipts signed before the field existed keep
                # verifying byte-for-byte.
                activity = {k: v for k, v in activity.items()
                            if k != "inference_provenance"}
            payload["agent_activity"] = activity
        # Byte compatibility: local-model provenance is omitted entirely when
        # absent, so receipts signed before this field existed still verify.
        if self.local_model_provenance is not None:
            payload["local_model_provenance"] = self.local_model_provenance.model_dump(
                mode="json"
            )
        # Byte-compatibility: the security attestation key appears in the
        # canonical payload ONLY when the field is set. Pre-Phase-6
        # receipts (field None) canonicalize to exactly the bytes that
        # were signed; new receipts carry the attestation.
        if self.security_attestation is not None:
            payload["security_attestation"] = self.security_attestation.model_dump(
                mode="json"
            )
        # Phase 7 byte-compat (same rule as security_attestation): the
        # keys appear only when the run carried them.
        if self.run_status is not None:
            payload["run_status"] = self.run_status
        if self.failure_stage is not None:
            payload["failure_stage"] = self.failure_stage
        # Repository provenance: appears in the canonical payload only when
        # the run carried it (same byte-compat rule as security_attestation),
        # so pre-existing receipts keep verifying byte-for-byte.
        if self.repository is not None:
            payload["repository"] = self.repository.model_dump(mode="json")
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
