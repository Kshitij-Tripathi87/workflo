#!/usr/bin/env python3
"""Landlock pre-exec wrapper — runs INSIDE the sandbox, before the workload.

This file is DELIBERATELY standalone (stdlib only, no sandbox_runtime
imports): it is bind-mounted read-only into every Landlocked sandbox and
executed as the outermost command:

    python3 /workflo/landlock_exec.py --rules /workflo/landlock-rules.json \
            --status /workflo/artifacts/landlock-status-<workload>.json \
            -- <original command...>

It probes the kernel Landlock ABI, masks the requested access rights to
what that ABI supports (never passing unsupported handled bits — they
fail with EINVAL on older kernels), applies the ruleset to its own
thread — irreversible and inherited by every descendant (LK-7) — and
then execs the real workload.

Fail-closed policy (spec §5.3):

    mode=hardened    Landlock unavailable -> exit 125, nothing executes
    mode=compatible  Landlock unavailable -> status recorded, exec anyway
                     (the host already recorded reduced isolation in the
                     receipt — never a silent downgrade)

The status JSON it writes is ingested by the supervisor and becomes the
receipt's security_attestation.landlock fields.

Syscall constants are duplicated from sandbox_runtime.landlock on
purpose: this script must not import the package. Keep the two in sync
(ACCESS_NAMES: read / rw).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

LANDLOCK_CREATE_RULESET = 444
LANDLOCK_ADD_RULE = 445
LANDLOCK_RESTRICT_SELF = 446
LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1

# Access bits -> minimum Landlock ABI (kernel) that supports them.
ACCESS_MIN_ABI = {
    1 << 0: 1,   # EXECUTE
    1 << 1: 1,   # WRITE_FILE
    1 << 2: 1,   # READ_FILE
    1 << 3: 1,   # READ_DIR
    1 << 4: 1,   # REMOVE_DIR
    1 << 5: 1,   # REMOVE_FILE
    1 << 6: 1,   # MAKE_CHAR
    1 << 7: 1,   # MAKE_DIR
    1 << 8: 1,   # MAKE_REG
    1 << 9: 1,   # MAKE_SOCK
    1 << 10: 1,  # MAKE_FIFO
    1 << 11: 1,  # MAKE_BLOCK
    1 << 12: 1,  # MAKE_SYM
    1 << 13: 2,  # REFER (Linux 5.19)
    1 << 14: 3,  # TRUNCATE (Linux 6.2)
}

ACCESS_SETS = {
    "read": (1 << 0) | (1 << 2) | (1 << 3),           # EXECUTE|READ_FILE|READ_DIR
    "rw": (
        (1 << 0) | (1 << 2) | (1 << 3)                # read
        | (1 << 1) | (1 << 14)                        # WRITE_FILE|TRUNCATE
        | (1 << 4) | (1 << 5) | (1 << 6) | (1 << 7)   # dir mod
        | (1 << 8) | (1 << 9) | (1 << 10) | (1 << 11)
        | (1 << 12) | (1 << 13)
    ),
}

# File-rule mask: directory-only rights on a FILE rule make the kernel
# answer EINVAL (LANDLOCK_APPLY_FAILED) — e.g. /dev/null. Mask at add time.
FILE_ACCESS_MASK = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 14)  # EXEC|W|R|TRUNC

EXIT_LANDLOCK_FAILED = 125

STATUS_APPLIED = "LANDLOCK_APPLIED"
STATUS_UNSUPPORTED = "UNSUPPORTED_KERNEL"
STATUS_INVALID = "INVALID_POLICY"
STATUS_FAILED = "LANDLOCK_APPLY_FAILED"


def _load_libc():
    import ctypes
    return ctypes.CDLL("libc.so.6", use_errno=True)


def probe_abi() -> int:
    try:
        libc = _load_libc()
        version = libc.syscall(LANDLOCK_CREATE_RULESET, None, 0,
                               LANDLOCK_CREATE_RULESET_VERSION)
        return int(version) if version > 0 else 0
    except Exception:
        return 0


def mask_for_abi(requested: int, abi: int) -> int:
    supported = 0
    for bit, min_abi in ACCESS_MIN_ABI.items():
        if abi >= min_abi:
            supported |= bit
    return requested & supported


def plan(rules: list, abi: int) -> tuple:
    """Pure planning step (unit-testable without Linux): returns
    (handled_access, [(path, masked_access), ...]) or raises ValueError
    on an invalid policy."""
    if not rules:
        raise ValueError("empty ruleset")
    planned = []
    handled = 0
    for rule in rules:
        access = ACCESS_SETS.get(str(rule.get("access")))
        if access is None:
            raise ValueError(f"unknown access {rule.get('access')!r}")
        masked = mask_for_abi(access, abi)
        if masked == 0:
            raise ValueError(
                f"rule for {rule['path']} masks to zero access on ABI {abi}"
            )
        planned.append((rule["path"], masked))
        handled |= masked
    return handled, planned


def apply_ruleset(handled: int, planned: list, libc) -> str:
    """Create + populate + restrict. Returns a STATUS_* string."""
    import ctypes

    class RulesetAttr(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]

    class PathBeneathAttr(ctypes.Structure):
        _fields_ = [
            ("allowed_access", ctypes.c_uint64),
            ("parent_fd", ctypes.c_int32),
        ]

    attr = RulesetAttr(handled_access_fs=handled)
    fd = libc.syscall(LANDLOCK_CREATE_RULESET, ctypes.byref(attr),
                      ctypes.sizeof(attr), 0)
    if fd < 0:
        return STATUS_FAILED
    try:
        for path, access in planned:
            try:
                # O_PATH|O_CLOEXEC per man landlock_add_rule: accepts file
                # rules (e.g. /dev/null) as well as directory rules, unlike
                # O_RDONLY|O_DIRECTORY (ENOTDIR -> silently dropped policy).
                o_path = getattr(os, "O_PATH", None)
                flags = (o_path | getattr(os, "O_CLOEXEC", 0)) if o_path is not None \
                    else (os.O_RDONLY | os.O_DIRECTORY)
                parent_fd = os.open(path, flags)
            except OSError:
                return STATUS_INVALID
            try:
                import stat as _stat
                if not _stat.S_ISDIR(os.fstat(parent_fd).st_mode):
                    access &= FILE_ACCESS_MASK
                    if access == 0:
                        return STATUS_INVALID
                rule_attr = PathBeneathAttr(allowed_access=access,
                                            parent_fd=parent_fd)
                ret = libc.syscall(LANDLOCK_ADD_RULE, fd,
                                   LANDLOCK_RULE_PATH_BENEATH,
                                   ctypes.byref(rule_attr), 0)
                if ret < 0:
                    return STATUS_FAILED
            finally:
                os.close(parent_fd)
        ret = libc.syscall(LANDLOCK_RESTRICT_SELF, fd, 0)
        if ret < 0:
            return STATUS_FAILED
    finally:
        os.close(fd)
    return STATUS_APPLIED


def write_status(path: str, payload: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(payload, f, sort_keys=True)
    except OSError as e:
        # The status file is observability, not enforcement — failing to
        # write it must not stop (or silently weaken) execution.
        print(f"landlock_exec: could not write status: {e}", file=sys.stderr)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply a Landlock ruleset, then exec the workload."
    )
    parser.add_argument("--rules", required=True,
                        help="path to the rules JSON (sandbox view)")
    parser.add_argument("--status", required=True,
                        help="where to write the application status JSON")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="workload command (after --)")
    args = parser.parse_args(argv)
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("landlock_exec: no workload command", file=sys.stderr)
        return 2

    try:
        with open(args.rules) as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        print(f"landlock_exec: cannot read rules {args.rules}: {e}",
              file=sys.stderr)
        return EXIT_LANDLOCK_FAILED  # unreadable policy is fail-closed, always

    mode = doc.get("mode", "compatible")
    rules = doc.get("rules", [])
    workload = doc.get("workload", "unknown")

    abi = probe_abi()
    if abi <= 0:
        write_status(args.status, {
            "workload": workload, "mode": mode, "abi": 0,
            "status": STATUS_UNSUPPORTED,
            "reason": "unsupported_kernel",
        })
        if mode == "hardened":
            print("landlock_exec: Landlock unavailable in hardened mode — "
                  "refusing to exec", file=sys.stderr)
            return EXIT_LANDLOCK_FAILED
        os.execvp(command[0], command)  # compatible: continue, loudly noted
        return EXIT_LANDLOCK_FAILED  # unreachable on successful exec

    try:
        handled, planned = plan(rules, abi)
    except ValueError as e:
        # Invalid policy is fail-closed in BOTH modes: a misparsed or
        # empty ruleset must never degrade into "no Landlock".
        write_status(args.status, {
            "workload": workload, "mode": mode, "abi": abi,
            "status": STATUS_INVALID, "reason": str(e),
        })
        print(f"landlock_exec: invalid policy: {e}", file=sys.stderr)
        return EXIT_LANDLOCK_FAILED

    status = apply_ruleset(handled, planned, _load_libc())
    write_status(args.status, {
        "workload": workload, "mode": mode, "abi": abi,
        "status": status,
        "reason": None if status == STATUS_APPLIED else "apply_failed",
    })
    if status != STATUS_APPLIED:
        if mode == "hardened":
            print(f"landlock_exec: {status} in hardened mode — refusing to exec",
                  file=sys.stderr)
            return EXIT_LANDLOCK_FAILED
        print(f"landlock_exec: {status} in compatible mode — exec continues "
              "with reduced isolation", file=sys.stderr)
    os.execvp(command[0], command)
    return EXIT_LANDLOCK_FAILED  # exec failed to replace us


if __name__ == "__main__":
    sys.exit(main())
