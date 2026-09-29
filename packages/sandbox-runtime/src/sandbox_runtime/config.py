"""Configuration models for sandbox runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from enum import Enum


class DepMode(str, Enum):
    PREFLIGHT_CACHE = "preflight_cache"
    VENDOR_CACHE = "vendor_cache"
    FIXTURE_MIRROR = "fixture_mirror"
    USER_APPROVED = "user_approved"


class NetworkMode(str, Enum):
    NONE = "none"
    PRIVATE = "private"


class WorkloadType(str, Enum):
    APP = "app"
    TEST = "test"
    AGENT = "agent"
    BROWSER = "browser"
    EVIDENCE = "evidence"


@dataclass
class BwrapConfig:
    sandbox_id: str
    workload_type: WorkloadType
    readonly_root: Path
    workspace_dir: Path
    evidence_dir: Path
    tmp_dir: Path
    home_dir: Path
    memory_mb: int = 2048
    cpu_cores: float = 2.0
    pids_max: int = 256
    network_mode: NetworkMode = NetworkMode.NONE
    veth_peer: Optional[str] = None
    seccomp_profile: Optional[Path] = None
    drop_caps: list[str] = field(default_factory=lambda: [
        "CAP_SYS_ADMIN", "CAP_SYS_RESOURCE", "CAP_DAC_OVERRIDE",
        "CAP_SYS_PTRACE", "CAP_SYS_MODULE", "CAP_SYS_RAWIO",
        "CAP_SYS_PACCT", "CAP_SYS_NICE", "CAP_MKNOD",
        "CAP_AUDIT_WRITE", "CAP_AUDIT_CONTROL", "CAP_MAC_OVERRIDE",
        "CAP_MAC_ADMIN", "CAP_SYSLOG", "CAP_WAKE_ALARM",
        "CAP_BLOCK_SUSPEND", "CAP_BPF", "CAP_CHECKPOINT_RESTORE",
        "CAP_PERFMON",
    ])
    keep_caps: list[str] = field(default_factory=lambda: [
        "CAP_CHOWN", "CAP_DAC_READ_SEARCH", "CAP_FOWNER",
        "CAP_FSETID", "CAP_KILL", "CAP_SETGID", "CAP_SETUID",
        "CAP_SETPCAP", "CAP_NET_BIND_SERVICE",
    ])
    uid_map: str = "0 100000 65536"
    gid_map: str = "0 100000 65536"
    # Landlock (spec §5). Non-empty landlock_rules turns ON the in-sandbox
    # pre-exec wrapper: run_bwrap writes the rules JSON, RO-binds
    # landlock_exec.py + the rules, and wraps the command with it.
    landlock_rules: list[dict] = field(default_factory=list)
    # Fail-closed policy when Landlock cannot be applied:
    #   hardened   -> the workload must not exec (exit 125 in-sandbox;
    #                 the supervisor also refuses up front on unsupported
    #                 kernels)
    #   compatible -> exec continues; the receipt records reduced isolation
    # Never silently downgrade either way.
    landlock_mode: str = "compatible"
    command: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    workdir: str = "/workspace"
    # resolv.conf to bind over /etc/resolv.conf (PRIVATE network mode).
    # None = leave the rootfs default (no DNS in NONE mode anyway).
    resolv_conf: Optional[Path] = None
    # Named network namespace to join (PRIVATE network mode). The sandbox
    # is launched via `ip netns exec <netns>` and --unshare-net is omitted.
    # None = sealed anonymous netns (--unshare-net).
    netns: Optional[str] = None
    # cgroup.procs file to join BEFORE exec. bwrap's launcher forks the
    # sandbox child at startup — attaching the launcher PID after spawn
    # would leave the child OUTSIDE the cgroup and no limit would apply.
    # Joining via a shell wrapper before exec puts the whole tree inside.
    cgroup_procs: Optional[Path] = None


@dataclass
class CgroupConfig:
    sandbox_id: str
    memory_mb: int = 2048
    cpu_cores: float = 2.0
    pids_max: int = 256
    io_weight: int = 100
    cgroup_root: Path = Path("/sys/fs/cgroup")


@dataclass
class NetworkConfig:
    """Private network topology for one sandbox run.

    Topology (v0.3): a single named network namespace shared by the
    probe/app/agent/browser workloads, connected to the host by ONE veth
    pair. The host end (host_ip) runs dnsmasq for *.workflo.internal;
    the guest end carries the app address plus per-workload aliases
    (agent/browser/test) so nftables can enforce the workload flow
    policy: DNS to the host on :53 only, agent → app allowed, and
    NOTHING may connect to the agent/browser/test addresses. External
    egress does not flow.

    Known limitation: the subnet is fixed, so concurrent sandboxes would
    collide — per-run allocation is deferred until per-workload netns
    isolation lands.
    """

    sandbox_id: str
    subnet: str = "10.200.0.0/24"
    host_ip: str = "10.200.0.1"    # veth host end + dnsmasq listener
    guest_ip: str = "10.200.0.2"   # veth guest end inside the netns
    # Internal service addresses — per-workload aliases on the guest veth
    # (spec §6.3). app stays on the primary guest address; agent/browser/
    # test get their own aliases so nftables can enforce the workload flow
    # policy (notably: NOTHING may connect TO the agent — the agent is
    # Workflo's operator, never a server for untrusted app content).
    app_ip: str = "10.200.0.2"
    agent_ip: str = "10.200.0.3"
    browser_ip: str = "10.200.0.4"
    test_ip: str = "10.200.0.5"
    dns_ip: str = "10.200.0.1"
    # Populated by setup_private_network: dnsmasq PID on the host side.
    # teardown_network kills it — it must not outlive the sandbox.
    dnsmasq_pid: Optional[int] = None

    @property
    def netns_name(self) -> str:
        return f"workflo-{self.sandbox_id}"

    @property
    def veth_host(self) -> str:
        # Linux IFNAMSIZ is 16 incl. NUL -> 15 usable chars.
        # "wf-" (3) + 9 + "-h"/"-g" (2) = 14.
        return f"wf-{self.sandbox_id[:9]}-h"

    @property
    def veth_guest(self) -> str:
        return f"wf-{self.sandbox_id[:9]}-g"


@dataclass
class RootfsConfig:
    sandbox_id: str
    base_image: Path
    workspace_src: Path
    evidence_src: Path
    tmp_src: Path
    home_src: Path
    readonly: bool = True


@dataclass
class SnapshotConfig:
    repo_path: Path
    sandbox_id: str
    # Destination for the snapshot copy. None = snapshot in place (the
    # source already IS a run-local clone). When set, included files are
    # COPIED here and the manifest is written here — the source repo is
    # never mutated.
    dest_dir: Optional[Path] = None
    include_untracked: list[str] = field(default_factory=list)
    secret_patterns: list[str] = field(default_factory=lambda: [
        ".env", ".env.*", "*.pem", "*.key", "*.crt", "*.p12", "*.pfx",
        "id_rsa*", "id_ed25519*", "id_ecdsa*", "*.ppk",
        ".ssh/", ".aws/", ".config/gcloud/", ".azure/", ".kube/",
        "*.env", "*.secret", "*.token", "*credential*", "*password*",
        ".npmrc", ".dockercfg", ".docker/config.json",
        "git-credentials", ".git-credentials",
    ])


@dataclass
class DepConfig:
    mode: DepMode = DepMode.PREFLIGHT_CACHE
    repo_path: Path = Path(".")
    cache_dir: Path = Path(".workflo/cache")
    lockfile: Optional[str] = None


@dataclass
class RunConfig:
    sandbox_id: str
    repo_url: Optional[str] = None
    repo_path: Optional[Path] = None
    commit_sha: Optional[str] = None
    probe_groups: list[str] = field(default_factory=lambda: ["surface", "security"])
    runtime_image: Path = Path("/opt/workflo/workflo-worker")
    memory_mb: int = 2048
    cpu_cores: float = 2.0
    timeout_seconds: int = 600
    dep_mode: DepMode = DepMode.PREFLIGHT_CACHE
    evidence_dir: Path = Path(".workflo/runs")
    policy_path: Optional[Path] = None
    start_command: Optional[str] = None
    port: Optional[int] = None
    # Set by the Supervisor once isolation is created: workloads join
    # this cgroup so resource limits actually apply to them.
    cgroup_path: Optional[Path] = None
    # True = run the agent in LLM-planner mode (batch-driven by the
    # host-side planner through the plan/observations file protocol).
    # Falls back to task-spec mode when no LLM endpoint is reachable.
    agent_planner: bool = False
    # Security posture for the whole run (spec §5.3): "hardened" refuses to
    # run when an enforcement mechanism (Landlock, cgroup attach) cannot be
    # applied; "compatible" proceeds and records reduced isolation in the
    # receipt. The default keeps current behavior; hardened mode is the
    # Phase 6 release posture.
    security_mode: str = "compatible"
    # Set by the Supervisor after the host-side Landlock ABI probe: True
    # means workloads spawn with the in-sandbox Landlock wrapper.
    landlock_requested: bool = False
    # The user's natural-language testing mission ("Test authentication and
    # checkout"). Reaches the hosted model only as bounded, secret-redacted
    # text via the planner; recorded verbatim in the receipt's agent
    # activity so a reviewer sees exactly what the agent was asked to do.
    mission: Optional[str] = None


@dataclass
class FileManifestEntry:
    path: str
    mode: str
    size: int
    sha256: str


@dataclass
class SnapshotResult:
    tree_sha256: str
    files: int
    total_bytes: int
    manifest: list[FileManifestEntry]
    excluded: list[str]
    secret_exclusion_report: list[str]


@dataclass
class DepResult:
    mode: DepMode
    network_policy: str
    lockfile_sha256: Optional[str]
    cache_manifest_sha256: Optional[str]
    resolved: bool


@dataclass
class ProbeResult:
    name: str
    passed: bool
    detail: str
    severity: str = "critical"


@dataclass
class RunResult:
    sandbox_id: str
    success: bool
    receipt_path: Optional[Path] = None
    error: Optional[str] = None
    lifecycle_events: list[dict] = field(default_factory=list)
    # Unsigned receipt payload — a SignedReceipt-compatible dict built by the
    # supervisor from verified run state (run report, teardown proof, canary,
    # evidence binding). The caller (CLI / daemon) holds the Ed25519 keypair
    # and signs this payload: the private key never enters the supervisor.
    receipt_payload: Optional[dict] = None
    # Root directory of this run's evidence bundle (hash-chained ledger +
    # manifest). Survives teardown — it backs the receipt.
    evidence_dir: Optional[Path] = None
    # True only if post-teardown verification confirmed every sandbox
    # resource (processes, cgroup, netns, writable dirs) is gone.
    teardown_verified: bool = False
    elapsed_seconds: float = 0.0