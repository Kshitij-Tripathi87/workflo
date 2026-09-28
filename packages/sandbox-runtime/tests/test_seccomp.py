"""Tests for seccomp profile loading and compiled-BPF export.

BPF compilation itself requires Linux + libseccomp — those tests skip
elsewhere. The JSON-reading contract is testable on any platform.
"""

import json
import sys
from pathlib import Path

import pytest

from sandbox_runtime.seccomp import (
    get_seccomp_profile,
    validate_seccomp_profile,
    profile_allowed_syscalls,
    write_bwrap_profile,
    write_empty_bwrap_profile,
)
from sandbox_runtime.config import WorkloadType


def test_profiles_exist_for_all_workload_types():
    for wt in WorkloadType:
        profile = get_seccomp_profile(wt)
        assert validate_seccomp_profile(profile), f"missing profile for {wt}"


def test_profile_allowed_syscalls():
    profile = get_seccomp_profile(WorkloadType.TEST)
    names = profile_allowed_syscalls(profile)

    # Sanity: the test profile allows the syscalls a python run needs
    assert "execve" in names
    assert "clone" in names       # subprocess/threads
    assert "lseek" in names       # file iteration
    assert "sendmsg" in names     # DNS via resolver
    assert "recvmsg" in names
    assert "rt_sigreturn" in names  # signal handlers crash without it


def test_profile_syscalls_deduplicated():
    profile = get_seccomp_profile(WorkloadType.TEST)
    names = profile_allowed_syscalls(profile)
    assert len(names) == len(set(names))


def test_write_bwrap_profile_requires_linux(tmp_path):
    """BPF compilation is a Linux capability; on other platforms it must
    fail loudly rather than silently skip enforcement."""
    profile = get_seccomp_profile(WorkloadType.TEST)
    dest = tmp_path / "seccomp.bpf"

    if sys.platform == "linux":
        pytest.skip("covered by test_write_bwrap_profile_bpf on linux")
    else:
        with pytest.raises(RuntimeError, match="Linux"):
            write_bwrap_profile(profile, dest)


@pytest.mark.skipif(sys.platform != "linux", reason="requires libseccomp")
def test_write_bwrap_profile_bpf(tmp_path):
    """The exported profile is compiled BPF, not text."""
    profile = get_seccomp_profile(WorkloadType.TEST)
    dest = tmp_path / "seccomp.bpf"

    result = write_bwrap_profile(profile, dest)

    assert result == dest
    data = dest.read_bytes()
    assert len(data) > 0
    # BPF instructions are 8 bytes each; the program must be a multiple
    # of 8 (bwrap rejects anything else) and NOT parseable as JSON text.
    assert len(data) % 8 == 0
    with pytest.raises(ValueError):  # JSONDecodeError or UnicodeDecodeError
        json.loads(data)
    # A real BPF program starts with the arch-load instruction
    # (BPF_LD|BPF_W|BPF_ABS = opcode 0x20 in the first byte).
    assert data[0] == 0x20


@pytest.mark.skipif(sys.platform != "linux", reason="requires libseccomp")
def test_write_empty_bwrap_profile_bpf(tmp_path):
    """An empty profile compiles to a minimal KILL-everything program."""
    dest = tmp_path / "empty.bpf"
    write_empty_bwrap_profile(dest)

    data = dest.read_bytes()
    assert len(data) % 8 == 0
    # Minimal program: arch load + arch check + kill + ret (~4-8 instructions)
    assert len(data) <= 8 * 8
