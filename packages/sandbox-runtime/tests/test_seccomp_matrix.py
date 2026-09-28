"""Seccomp syscall matrix — hand-crafted assurance tests over the JSON profiles.

SOC 2 CC6.1/CC6.7 and the security-testing plan (§33 "syscall abuse"):
rather than fuzzing the kernel, we pin the POLICY. The JSON profiles in
sandbox_runtime/seccomp/ are the source of truth that libseccomp compiles
for bwrap's --seccomp. These tests run on every platform (pure JSON):

1. Deny-by-default: every profile's defaultAction is a terminating deny.
2. Dangerous syscalls (kernel modules, mounts, bpf/perf, keyring, cross-
   process memory, system control) are NEVER in any workload's allowlist.
3. The baseline functional set IS allowed — a profile that grew too tight
   breaks every workload; too loose fails the deny test. Both directions
   are pinned so profile edits stay deliberate.

Kernel enforcement of the compiled BPF is covered on the Linux gate
(tests/integration/test_linux_gate.py) — this file is the cross-platform
contract those gates compile from.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sandbox_runtime.config import WorkloadType
from sandbox_runtime.seccomp import PROFILE_MAP, SECCOMP_DIR, profile_allowed_syscalls

# --- 1. The dangerous set ------------------------------------------------
# Syscalls a workload must never be able to make. Curated from the Docker
# default-block list + sandbox escape primitives (mount/ptrace/bpf/keyring).
# If a workload EVER legitimately needs one, that is a design change —
# discuss it before adding the name here or in a profile.
DANGEROUS_SYSCALLS = frozenset({
    # Mount / filesystem-namespace manipulation (sandbox escape)
    "mount", "umount", "umount2", "pivot_root", "chroot",
    "open_tree", "move_mount", "fsopen", "fsconfig", "fsmount",
    "swapon", "swapoff", "quotactl", "name_to_handle_at", "setns", "unshare",
    # Kernel modules, kexec, BPF/perf observability handles
    "init_module", "finit_module", "delete_module",
    "kexec_load", "kexec_file_load", "bpf", "perf_event_open", "userfaultfd",
    # Cross-process inspection/injection
    "ptrace", "process_vm_readv", "process_vm_writev", "kcmp",
    # Keyring (credential theft primitives)
    "add_key", "request_key", "keyctl",
    # System control / host identity
    "reboot", "sethostname", "setdomainname", "acct", "vhangup",
    "_sysctl", "sysfs", "iopl", "ioperm", "lookup_dcookie",
    # io_uring bypasses classic seccomp filters for file ops
    "io_uring_setup", "io_uring_enter", "io_uring_register",
})

# --- 2. The baseline functional set ---------------------------------------
# Each entry is an ALTERNATIVE GROUP: at least one name must be allowed.
# (32-bit/64-bit and legacy/modern pairs differ across profiles.)
FUNCTIONAL_BASELINE = (
    ("open", "openat"),
    ("read",),
    ("write",),
    ("close",),
    ("fstat", "newfstatat", "statx"),
    ("mmap",),
    ("munmap",),
    ("brk",),
    ("exit",),
    ("exit_group",),
    ("futex",),
    ("rt_sigreturn",),
)

ALLOW_ACTION = "SCMP_ACT_ALLOW"
DENY_ACTIONS = {"SCMP_ACT_KILL_PROCESS", "SCMP_ACT_ERRNO", "SCMP_ACT_TRAP"}

ALL_PROFILE_PATHS = sorted(
    {SECCOMP_DIR / name for name in PROFILE_MAP.values()},
)


def _profile_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestProfileCoverage:
    def test_every_workload_type_maps_to_a_profile_that_exists(self):
        for workload in WorkloadType:
            mapped = PROFILE_MAP.get(workload)
            assert mapped is not None, f"{workload} has no seccomp profile mapping"
            assert (SECCOMP_DIR / mapped).is_file(), f"{mapped} missing from {SECCOMP_DIR}"

    def test_profiles_are_valid_json_with_seccomp_shape(self):
        for path in ALL_PROFILE_PATHS:
            data = _profile_json(path)
            assert data.get("defaultAction") in DENY_ACTIONS, (
                f"{path.name}: defaultAction {data.get('defaultAction')!r} is not deny-by-default"
            )
            assert isinstance(data.get("syscalls"), list) and data["syscalls"], (
                f"{path.name}: no syscall rules"
            )


class TestDenyMatrix:
    """No dangerous syscall may appear in ANY workload's allowlist."""

    @pytest.mark.parametrize("profile_path", ALL_PROFILE_PATHS, ids=lambda p: p.name)
    def test_dangerous_syscalls_not_allowed(self, profile_path: Path):
        allowed = set(profile_allowed_syscalls(profile_path))
        leaked = sorted(allowed & DANGEROUS_SYSCALLS)
        assert not leaked, (
            f"{profile_path.name} allows dangerous syscalls: {leaked}. "
            "Remove them or justify the change in the profile's commit message."
        )

    @pytest.mark.parametrize("profile_path", ALL_PROFILE_PATHS, ids=lambda p: p.name)
    def test_only_allow_action_rules_present(self, profile_path: Path):
        """Profiles are allowlist-format: a non-ALLOW rule here would be a
        hand-edited policy bypass the compile step doesn't model."""
        data = _profile_json(profile_path)
        for rule in data["syscalls"]:
            assert rule.get("action") == ALLOW_ACTION, (
                f"{profile_path.name}: rule with action {rule.get('action')!r} "
                "— profiles may only contain SCMP_ACT_ALLOW entries"
            )

    @pytest.mark.parametrize("profile_path", ALL_PROFILE_PATHS, ids=lambda p: p.name)
    def test_no_duplicate_syscall_names(self, profile_path: Path):
        """libseccomp fails on duplicate rules on some versions; the build
        step dedups silently, so a duplicate in source would hide a diff."""
        data = _profile_json(profile_path)
        names = [n for rule in data["syscalls"] for n in rule.get("names", [])]
        dupes = sorted({n for n in names if names.count(n) > 1})
        assert not dupes, f"{profile_path.name}: duplicate syscall names {dupes}"


class TestAllowMatrix:
    """Every profile must keep the baseline functional set — a tightened
    profile that breaks read/write/exit is a regression, not hardening."""

    @pytest.mark.parametrize("profile_path", ALL_PROFILE_PATHS, ids=lambda p: p.name)
    @pytest.mark.parametrize("alternatives", FUNCTIONAL_BASELINE)
    def test_baseline_syscall_allowed(self, profile_path: Path, alternatives):
        allowed = set(profile_allowed_syscalls(profile_path))
        assert any(a in allowed for a in alternatives), (
            f"{profile_path.name}: none of {alternatives} allowed — workload "
            "cannot perform basic process function"
        )

    def test_agent_profile_allows_landlock_and_sockets(self):
        """The AGENT workload applies Landlock from inside and speaks HTTP
        to *.workflo.internal — both capabilities are load-bearing."""
        allowed = set(profile_allowed_syscalls(SECCOMP_DIR / "agent.json"))
        assert {
            "landlock_create_ruleset", "landlock_add_rule", "landlock_restrict_self"
        } <= allowed
        assert {"socket", "connect", "sendmsg", "recvmsg"} & allowed, (
            "agent profile must allow sockets (goes through the netns + ToolGateway)"
        )
