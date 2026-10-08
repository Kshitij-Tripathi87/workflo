"""Landlock ruleset builder and application — ABI-aware (spec §5, F-1/F-2/F-11).

Two consumers:

1. The HOST (supervisor / bwrap launcher) builds per-workload rule tables
   (``build_ruleset_for_workload``) and serializes them as the rules JSON the
   in-sandbox wrapper consumes. The host also probes the kernel ABI once per
   run so the receipt can record requested/applied and hardened mode can fail
   closed BEFORE anything is spawned.

2. The IN-SANDBOX wrapper (``landlock_exec.py`` — deliberately a standalone
   script with its own syscall bindings, because it runs inside the sandbox
   where this package is not importable) applies the ruleset and execs the
   real workload command.

Landlock must be applied INSIDE the sandbox process before the workload
executes — applying it from the supervisor would be a no-op for the sandbox's
mount namespace view and would not survive bwrap's fork/exec.

ABI discipline (F-2): handled access bits are masked to what the running
kernel's Landlock ABI supports BEFORE any ruleset is created — not rejected
after an EINVAL. Base filesystem rights ship with ABI 1 (Linux 5.13);
REFER requires ABI 2 (5.19); TRUNCATE requires ABI 3 (6.2).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

# Landlock syscall numbers (x86_64/aarch64; Linux 5.13+)
LANDLOCK_CREATE_RULESET = 444
LANDLOCK_ADD_RULE = 445
LANDLOCK_RESTRICT_SELF = 446

# landlock_create_ruleset flags
LANDLOCK_CREATE_RULESET_VERSION = 1

# Landlock rule types
LANDLOCK_RULE_PATH_BENEATH = 1

# How to open rule paths: O_PATH|O_CLOEXEC per man landlock_add_rule —
# accepts files AND directories (the older O_RDONLY|O_DIRECTORY approach
# made file rules like /dev/null fail with ENOTDIR -> INVALID_POLICY,
# which in compatible mode silently DROPPED Landlock for that workload).
_RULE_OPEN_FLAGS = (
    (os.O_PATH | getattr(os, "O_CLOEXEC", 0))
    if hasattr(os, "O_PATH")
    else (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
)

# How to open rule paths: O_PATH|O_CLOEXEC per man landlock_add_rule —
# accepts files AND directories (the older O_RDONLY|O_DIRECTORY approach
# made file rules like /dev/null fail with ENOTDIR -> INVALID_POLICY,
# which in compatible mode silently DROPPED Landlock for that workload).
_RULE_OPEN_FLAGS = (
    (os.O_PATH | getattr(os, "O_CLOEXEC", 0))
    if hasattr(os, "O_PATH")
    else (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
)

# Access rights (bit -> minimum kernel Landlock ABI that supports it)
LANDLOCK_ACCESS_FS_EXECUTE = 1 << 0       # ABI 1
LANDLOCK_ACCESS_FS_WRITE_FILE = 1 << 1    # ABI 1
LANDLOCK_ACCESS_FS_READ_FILE = 1 << 2     # ABI 1
LANDLOCK_ACCESS_FS_READ_DIR = 1 << 3      # ABI 1
LANDLOCK_ACCESS_FS_REMOVE_DIR = 1 << 4    # ABI 1
LANDLOCK_ACCESS_FS_REMOVE_FILE = 1 << 5   # ABI 1
LANDLOCK_ACCESS_FS_MAKE_CHAR = 1 << 6     # ABI 1
LANDLOCK_ACCESS_FS_MAKE_DIR = 1 << 7      # ABI 1
LANDLOCK_ACCESS_FS_MAKE_REG = 1 << 8      # ABI 1
LANDLOCK_ACCESS_FS_MAKE_SOCK = 1 << 9     # ABI 1
LANDLOCK_ACCESS_FS_MAKE_FIFO = 1 << 10    # ABI 1
LANDLOCK_ACCESS_FS_MAKE_BLOCK = 1 << 11   # ABI 1
LANDLOCK_ACCESS_FS_MAKE_SYM = 1 << 12     # ABI 1
LANDLOCK_ACCESS_FS_REFER = 1 << 13        # ABI 2 (Linux 5.19)
LANDLOCK_ACCESS_FS_TRUNCATE = 1 << 14     # ABI 3 (Linux 6.2)

ACCESS_MIN_ABI = {
    LANDLOCK_ACCESS_FS_EXECUTE: 1,
    LANDLOCK_ACCESS_FS_WRITE_FILE: 1,
    LANDLOCK_ACCESS_FS_READ_FILE: 1,
    LANDLOCK_ACCESS_FS_READ_DIR: 1,
    LANDLOCK_ACCESS_FS_REMOVE_DIR: 1,
    LANDLOCK_ACCESS_FS_REMOVE_FILE: 1,
    LANDLOCK_ACCESS_FS_MAKE_CHAR: 1,
    LANDLOCK_ACCESS_FS_MAKE_DIR: 1,
    LANDLOCK_ACCESS_FS_MAKE_REG: 1,
    LANDLOCK_ACCESS_FS_MAKE_SOCK: 1,
    LANDLOCK_ACCESS_FS_MAKE_FIFO: 1,
    LANDLOCK_ACCESS_FS_MAKE_BLOCK: 1,
    LANDLOCK_ACCESS_FS_MAKE_SYM: 1,
    LANDLOCK_ACCESS_FS_REFER: 2,
    LANDLOCK_ACCESS_FS_TRUNCATE: 3,
}

# Combined access sets
LANDLOCK_ACCESS_FS_READ = (
    LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR | LANDLOCK_ACCESS_FS_EXECUTE
)
LANDLOCK_ACCESS_FS_WRITE = (
    LANDLOCK_ACCESS_FS_WRITE_FILE | LANDLOCK_ACCESS_FS_TRUNCATE
)
LANDLOCK_ACCESS_FS_DIR_MOD = (
    LANDLOCK_ACCESS_FS_REMOVE_DIR | LANDLOCK_ACCESS_FS_REMOVE_FILE |
    LANDLOCK_ACCESS_FS_MAKE_CHAR | LANDLOCK_ACCESS_FS_MAKE_DIR |
    LANDLOCK_ACCESS_FS_MAKE_REG | LANDLOCK_ACCESS_FS_MAKE_SOCK |
    LANDLOCK_ACCESS_FS_MAKE_FIFO | LANDLOCK_ACCESS_FS_MAKE_BLOCK |
    LANDLOCK_ACCESS_FS_MAKE_SYM | LANDLOCK_ACCESS_FS_REFER
)
LANDLOCK_ACCESS_FS_RW = (
    LANDLOCK_ACCESS_FS_READ | LANDLOCK_ACCESS_FS_WRITE | LANDLOCK_ACCESS_FS_DIR_MOD
)

# Rights applicable to NON-directory rules: the kernel rejects a file rule
# carrying directory-only rights (EINVAL -> LANDLOCK_APPLY_FAILED), so file
# rules are masked down at rule-add time. "rw" on /dev/null lands as
# READ_FILE|WRITE_FILE|TRUNCATE.
LANDLOCK_ACCESS_FS_FILE_MASK = (
    LANDLOCK_ACCESS_FS_EXECUTE | LANDLOCK_ACCESS_FS_WRITE_FILE
    | LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_TRUNCATE
)

# Serializable access names used in the rules JSON consumed by the
# in-sandbox wrapper. Keep in sync with landlock_exec.py.
ACCESS_NAMES = {
    "read": LANDLOCK_ACCESS_FS_READ,
    "rw": LANDLOCK_ACCESS_FS_RW,
}


class LandlockStatus(str, Enum):
    """Deterministic outcomes for a Landlock application attempt (spec §5.3)."""

    APPLIED = "LANDLOCK_APPLIED"
    UNSUPPORTED_KERNEL = "UNSUPPORTED_KERNEL"
    INVALID_POLICY = "INVALID_POLICY"
    APPLY_FAILED = "LANDLOCK_APPLY_FAILED"


@dataclass
class LandlockApplyResult:
    status: LandlockStatus
    abi: int = 0
    detail: str = ""


def probe_abi() -> int:
    """Return the kernel's Landlock ABI version (1, 2, 3, ...).

    0 means Landlock is not supported (or not on this platform). This is a
    host-side probe: the host and sandbox share the kernel, so the result
    is valid for the sandbox too.
    """
    if os.name != "posix" or not hasattr(os, "sysconf"):
        return 0
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        # landlock_create_ruleset(NULL, 0, LANDLOCK_CREATE_RULESET_VERSION)
        # returns the highest supported ABI version — no ruleset is created.
        version = libc.syscall(LANDLOCK_CREATE_RULESET, None, 0,
                               LANDLOCK_CREATE_RULESET_VERSION)
        if version < 0:
            return 0
        return int(version)
    except Exception:
        return 0


def mask_for_abi(requested: int, abi: int) -> int:
    """Mask requested access bits down to those the given ABI supports.

    Pure function — unit-testable on any platform. F-2: this is applied
    BEFORE ruleset creation, so an older kernel never sees unsupported
    handled bits (which would fail with EINVAL).
    """
    supported = 0
    for bit, min_abi in ACCESS_MIN_ABI.items():
        if abi >= min_abi:
            supported |= bit
    return requested & supported


@dataclass
class LandlockRule:
    """Single Landlock path rule (path-beneath)."""
    path: str
    access: int
    is_beneath: bool = True


@dataclass
class LandlockRuleset:
    """ABI-aware Landlock ruleset builder.

    The abi is probed (or injected for tests) at construction; every rule's
    access mask and the ruleset's handled-access mask are computed against
    it. apply() applies the ruleset to the CALLING thread — which is why
    the real enforcement point is landlock_exec.py running inside the
    sandbox, not this class on the host.
    """

    rules: list[LandlockRule] = field(default_factory=list)
    abi: int = 0
    _ruleset_fd: Optional[int] = None

    def __init__(self, abi: Optional[int] = None):
        self.rules = []
        self._ruleset_fd = None
        self.abi = probe_abi() if abi is None else abi

    def add_rule(self, access: int, path, beneath: bool = True) -> None:
        self.rules.append(LandlockRule(str(path), access, beneath))

    def add_read_only(self, path, beneath: bool = True) -> None:
        self.add_rule(LANDLOCK_ACCESS_FS_READ, path, beneath)

    def add_read_write(self, path, beneath: bool = True) -> None:
        self.add_rule(LANDLOCK_ACCESS_FS_RW, path, beneath)

    # -- planning (pure) ----------------------------------------------------

    def planned_rules(self) -> list[tuple[str, int]]:
        """Rules after ABI masking: (path, masked_access). Raises
        LandlockStatus.INVALID_POLICY material when a rule masks to zero
        or references a nonexistent path — over-restriction and
        misconfiguration must be loud, never silent."""
        planned = []
        for rule in self.rules:
            masked = mask_for_abi(rule.access, self.abi)
            if masked == 0:
                raise PolicyError(
                    f"rule for {rule.path} masks to zero access on ABI {self.abi}"
                )
            planned.append((rule.path, masked))
        return planned

    @property
    def handled_access(self) -> int:
        """Union of all rule masks, itself ABI-masked."""
        combined = 0
        for rule in self.rules:
            combined |= rule.access
        return mask_for_abi(combined, self.abi)

    # -- application (Linux, in-process) ------------------------------------

    def apply(self) -> LandlockApplyResult:
        """Create, populate and apply the ruleset to the current thread.

        Used by landlock_exec.py inside the sandbox and by tests with an
        injected fake libc. Irreversible for this thread and its children.
        """
        if self.abi <= 0:
            return LandlockApplyResult(
                LandlockStatus.UNSUPPORTED_KERNEL, abi=0,
                detail="kernel has no Landlock support",
            )
        try:
            planned = self.planned_rules()
        except PolicyError as e:
            return LandlockApplyResult(
                LandlockStatus.INVALID_POLICY, abi=self.abi, detail=str(e)
            )

        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6", use_errno=True)

            class RulesetAttr(ctypes.Structure):
                _fields_ = [("handled_access_fs", ctypes.c_uint64)]

            attr = RulesetAttr(handled_access_fs=self.handled_access)
            fd = libc.syscall(
                LANDLOCK_CREATE_RULESET,
                ctypes.byref(attr),
                ctypes.sizeof(attr),
                0,
            )
            if fd < 0:
                errno = ctypes.get_errno()
                return LandlockApplyResult(
                    LandlockStatus.APPLY_FAILED, abi=self.abi,
                    detail=f"landlock_create_ruleset failed: {os.strerror(errno)}",
                )
            self._ruleset_fd = fd
            try:
                for path, access in planned:
                    result = _add_path_rule(libc, fd, path, access)
                    if result is not None:
                        return result
                ret = libc.syscall(LANDLOCK_RESTRICT_SELF, fd, 0)
                if ret < 0:
                    errno = ctypes.get_errno()
                    return LandlockApplyResult(
                        LandlockStatus.APPLY_FAILED, abi=self.abi,
                        detail=f"landlock_restrict_self failed: {os.strerror(errno)}",
                    )
            finally:
                os.close(fd)
                self._ruleset_fd = None
            return LandlockApplyResult(LandlockStatus.APPLIED, abi=self.abi)
        except OSError as e:
            return LandlockApplyResult(
                LandlockStatus.APPLY_FAILED, abi=self.abi, detail=str(e)
            )


class PolicyError(Exception):
    """The requested ruleset is invalid for this ABI (INVALID_POLICY)."""


def _add_path_rule(libc, fd: int, path: str, access: int) -> Optional[LandlockApplyResult]:
    import ctypes

    class PathBeneathAttr(ctypes.Structure):
        _fields_ = [
            ("allowed_access", ctypes.c_uint64),
            ("parent_fd", ctypes.c_int32),
        ]

    try:
        # landlock_add_rule(2): parent_fd must be an O_PATH descriptor —
        # which (unlike O_RDONLY|O_DIRECTORY) works for FILE rules too
        # (e.g. /dev/null) as well as directories.
        parent_fd = os.open(path, _RULE_OPEN_FLAGS)
    except OSError as e:
        return LandlockApplyResult(
            LandlockStatus.INVALID_POLICY, detail=f"cannot open rule path {path}: {e}"
        )
    try:
        import stat as _stat

        if not _stat.S_ISDIR(os.fstat(parent_fd).st_mode):
            access &= LANDLOCK_ACCESS_FS_FILE_MASK
            if access == 0:
                return LandlockApplyResult(
                    LandlockStatus.INVALID_POLICY,
                    detail=f"file rule for {path} masks to zero file access",
                )
        attr = PathBeneathAttr(allowed_access=access, parent_fd=parent_fd)
        ret = libc.syscall(
            LANDLOCK_ADD_RULE, fd, LANDLOCK_RULE_PATH_BENEATH,
            ctypes.byref(attr), 0,
        )
        if ret < 0:
            errno = ctypes.get_errno()
            return LandlockApplyResult(
                LandlockStatus.APPLY_FAILED,
                detail=f"landlock_add_rule failed for {path}: {os.strerror(errno)}",
            )
    finally:
        os.close(parent_fd)
    return None


# ---------------------------------------------------------------------------
# Per-workload rule tables (spec §5.4). Paths are SANDBOX-VIEW paths — the
# same strings the in-sandbox wrapper resolves. The read-only grant on "/"
# is defense-in-depth BENEATH the bwrap mount namespace: it can only ever
# expose the sandbox's own mounted tree, never the host's (F-11).
# ---------------------------------------------------------------------------

WORKLOAD_RULE_TABLES = {
    # workload type: {sandbox path: access name}
    "test":    {"/": "read", "/workspace": "rw", "/tmp": "rw",
                "/workflo/artifacts": "rw", "/dev/null": "rw"},
    "app":     {"/": "read", "/workspace": "rw", "/tmp": "rw", "/home/workflo": "rw",
                "/workflo/artifacts": "rw", "/dev/null": "rw"},
    "agent":   {"/": "read", "/workspace": "rw", "/tmp": "rw", "/home/workflo": "rw",
                "/workflo/artifacts": "rw", "/dev/null": "rw"},
    "browser": {"/": "read", "/workspace": "rw", "/tmp": "rw", "/home/workflo": "rw",
                "/workflo/artifacts": "rw", "/dev/null": "rw"},
}


def rules_for_workload(workload_type) -> list[dict]:
    """Serializable rule list for a workload type (the rules JSON body).

    workload_type may be a WorkloadType enum or its string value.
    """
    key = getattr(workload_type, "value", str(workload_type)).lower()
    table = WORKLOAD_RULE_TABLES.get(key, WORKLOAD_RULE_TABLES["test"])
    return [{"path": p, "access": a} for p, a in table.items()]


def rules_payload(workload_type, security_mode: str = "compatible") -> dict:
    """Full rules JSON document handed to landlock_exec inside the sandbox."""
    return {
        "workload": getattr(workload_type, "value", str(workload_type)).lower(),
        "mode": security_mode,
        "rules": rules_for_workload(workload_type),
    }


def build_ruleset_for_workload(workload_type, abi: Optional[int] = None) -> LandlockRuleset:
    """Host-side builder used for planning/tests (the sandbox applies its own)."""
    ruleset = LandlockRuleset(abi=abi)
    for rule in rules_for_workload(workload_type):
        access = ACCESS_NAMES[rule["access"]]
        ruleset.add_rule(access, rule["path"])
    return ruleset


def enable_for_workload(config, workload_type, security_mode: str = "compatible") -> None:
    """Turn on Landlock for a BwrapConfig at spawn time.

    Sets the serializable rules and the security mode; bwrap.run_bwrap
    writes the rules JSON, RO-binds the wrapper script, and rewrites the
    command when landlock_rules is non-empty.
    """
    config.landlock_rules = rules_for_workload(workload_type)
    config.landlock_mode = security_mode
