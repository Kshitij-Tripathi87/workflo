"""Seccomp profile loading and compiled-BPF export for bubblewrap.

The JSON profiles (``seccomp/*.json``) are the source of truth and use
the familiar seccomp-tools/Docker shape. Bubblewrap's ``--seccomp FD``
does *not* consume that JSON (or syscall names): it requires a compiled
classic seccomp-BPF program, such as the one produced by
``seccomp_export_bpf(3)`` from libseccomp.

At spawn time we compile the JSON allowlist through libseccomp using a
small ctypes binding and write the resulting BPF program to a run-local
file. ``bwrap.py`` opens that file and passes the descriptor to bwrap.
The verifier never trusts this file as evidence; it is only a launcher
input.
"""

from __future__ import annotations

import ctypes
import errno
import json
import sys
from pathlib import Path
from typing import Optional

from sandbox_runtime.config import WorkloadType

SECCOMP_DIR = Path(__file__).parent / "seccomp"

PROFILE_MAP = {
    WorkloadType.APP: "app.json",
    WorkloadType.TEST: "test.json",
    WorkloadType.AGENT: "agent.json",
    WorkloadType.BROWSER: "browser.json",
    WorkloadType.EVIDENCE: "test.json",  # Reuse test profile for evidence collector
}


def get_seccomp_profile(workload_type: WorkloadType) -> Path:
    """Get path to the seccomp profile for workload type."""
    profile_name = PROFILE_MAP.get(workload_type, "test.json")
    return SECCOMP_DIR / profile_name


def validate_seccomp_profile(profile_path: Path) -> bool:
    """Validate seccomp profile exists and is readable."""
    return profile_path.exists() and profile_path.is_file()


def profile_allowed_syscalls(profile_path: Path) -> list[str]:
    """Read a JSON profile and return its allowed syscall names."""
    data = json.loads(Path(profile_path).read_text())
    names: list[str] = []
    for entry in data.get("syscalls", []):
        if entry.get("action") == "SCMP_ACT_ALLOW":
            names.extend(entry.get("names", []))
    # A duplicate rule is unnecessary and libseccomp reports it as an
    # error on some versions. Preserve profile order for deterministic
    # generated files while removing duplicates.
    return list(dict.fromkeys(names))


def write_bwrap_profile(profile_path: Path, dest_path: Path) -> Path:
    """Compile a JSON profile into the classic BPF bwrap expects.

    ``dest_path`` contains binary BPF instructions, not human-readable
    text. The caller must open it and pass the resulting FD to bwrap's
    ``--seccomp`` option.

    Raises RuntimeError when libseccomp is unavailable or a syscall in
    the profile cannot be resolved. Silently dropping an allow rule
    would turn a configuration error into an unexplained workload kill,
    so unknown names are treated as a hard failure.
    """
    if sys.platform != "linux":
        raise RuntimeError("compiled bubblewrap seccomp profiles require Linux")

    names = profile_allowed_syscalls(profile_path)
    lib = _load_libseccomp()

    # SCMP_ACT_KILL_PROCESS and SCMP_ACT_ALLOW are the libseccomp ABI
    # constants. The JSON profiles currently declare KILL_PROCESS as the
    # default action; keep that policy rather than weakening it to errno.
    SCMP_ACT_KILL_PROCESS = ctypes.c_uint32(0x80000000).value
    SCMP_ACT_ALLOW = ctypes.c_uint32(0x7FFF0000).value

    ctx = lib.seccomp_init(SCMP_ACT_KILL_PROCESS)
    if not ctx:
        raise RuntimeError("libseccomp seccomp_init() failed")

    try:
        for name in names:
            syscall_nr = lib.seccomp_syscall_resolve_name(name.encode("ascii"))
            if syscall_nr < 0:
                raise RuntimeError(
                    f"libseccomp cannot resolve syscall {name!r} in {profile_path}"
                )
            result = lib.seccomp_rule_add_array(
                ctx,
                SCMP_ACT_ALLOW,
                syscall_nr,
                0,
                None,
            )
            if result != 0:
                raise RuntimeError(
                    f"libseccomp could not allow syscall {name!r}: "
                    f"error {result}"
                )

        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os_open_binary(dest_path)
        try:
            result = lib.seccomp_export_bpf(ctx, fd)
            if result != 0:
                raise RuntimeError(
                    f"libseccomp seccomp_export_bpf() failed: error {result}"
                )
        finally:
            os_close(fd)
    except Exception:
        try:
            Path(dest_path).unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        lib.seccomp_release(ctx)

    return Path(dest_path)


def write_empty_bwrap_profile(dest_path: Path) -> Path:
    """Write a compiled profile that allows NOTHING (for enforcement tests)."""
    if sys.platform != "linux":
        raise RuntimeError("compiled bubblewrap seccomp profiles require Linux")

    lib = _load_libseccomp()
    SCMP_ACT_KILL_PROCESS = ctypes.c_uint32(0x80000000).value
    ctx = lib.seccomp_init(SCMP_ACT_KILL_PROCESS)
    if not ctx:
        raise RuntimeError("libseccomp seccomp_init() failed")
    try:
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os_open_binary(dest_path)
        try:
            result = lib.seccomp_export_bpf(ctx, fd)
            if result != 0:
                raise RuntimeError(
                    f"libseccomp seccomp_export_bpf() failed: error {result}"
                )
        finally:
            os_close(fd)
    except Exception:
        try:
            Path(dest_path).unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        lib.seccomp_release(ctx)
    return Path(dest_path)


def _load_libseccomp():
    """Load libseccomp and configure the small fixed-argument API surface."""
    try:
        lib = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    except OSError as exc:
        raise RuntimeError(
            "libseccomp.so.2 is required to compile bubblewrap seccomp profiles"
        ) from exc

    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p

    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int

    # seccomp_rule_add_array avoids ctypes varargs handling. With zero
    # comparisons the final pointer is legitimately NULL.
    lib.seccomp_rule_add_array.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.c_void_p,
    ]
    lib.seccomp_rule_add_array.restype = ctypes.c_int

    lib.seccomp_export_bpf.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.seccomp_export_bpf.restype = ctypes.c_int

    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.restype = None
    return lib


def os_open_binary(path: Path) -> int:
    """Open a BPF output file with restrictive permissions."""
    import os

    return os.open(
        str(path),
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )


def os_close(fd: int) -> None:
    """Close a raw output descriptor."""
    import os

    os.close(fd)
