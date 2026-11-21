"""Provision script tests: digest verification fails closed.

The script installs binaries onto a KVM host — its only safety property
is that a digest mismatch is a HARD error. We cannot download the real
release here (release-assets host blocked), but the fail-closed path is
fully testable: feed it a fabricated archive and assert refusal.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "linux" / "provision_firecracker.sh"


def test_script_exists_and_is_valid_bash():
    assert SCRIPT.exists()
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_digest_mismatch_refuses_to_install(tmp_path):
    """A fabricated archive must be rejected — never installed."""
    fake = tmp_path / "firecracker-fake.tgz"
    # Valid tgz structure, wrong content → wrong digest.
    src = tmp_path / "payload"
    src.mkdir()
    (src / "firecracker").write_bytes(b"not-the-real-binary")
    (src / "jailer").write_bytes(b"not-the-real-binary")
    subprocess.run(
        ["tar", "-czf", str(fake), "-C", str(tmp_path), "payload"],
        check=True,
    )

    prefix = tmp_path / "prefix"
    prefix.mkdir()
    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--from-archive",
            str(fake),
            "--prefix",
            str(prefix),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0, "digest mismatch must be fatal"
    assert "digest mismatch" in (result.stderr + result.stdout)
    # Nothing was installed.
    assert list(prefix.iterdir()) == []


def test_missing_archive_is_an_error(tmp_path):
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--from-archive",
            str(tmp_path / "nope.tgz"),
            "--prefix",
            str(prefix),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert list(prefix.iterdir()) == []


def test_pin_is_v1_18_0_with_release_digests():
    """The pinned version + digests are the contract with the release."""
    content = SCRIPT.read_text()
    assert 'VERSION="v1.18.0"' in content
    # x86_64 + aarch64 release digests (GitHub releases, v1.18.0).
    assert "1ac8eec866dd5eea14efecf6323e22b23eea24054545338a5b34bc5bca6623cd" in content
    assert "2a6130ff0338901ff9d7fbd73ce046c6b1c6123889dc84a34d678aa53bd0c0c2" in content
    # Both binaries are required — a firecracker-only archive is refused.
    assert "jailer binary not found" in content


def test_unsupported_arch_is_rejected(tmp_path, monkeypatch):
    # Simulate an unsupported arch by overriding uname via a PATH shim.
    shim = tmp_path / "bin"
    shim.mkdir()
    uname = shim / "uname"
    uname.write_text("#!/bin/sh\necho riscv64\n")
    uname.chmod(0o755)
    fake = tmp_path / "x.tgz"
    fake.write_bytes(b"")
    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--from-archive",
            str(fake),
            "--prefix",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PATH": f"{shim}:{__import__('os').environ.get('PATH', '')}",
        },
    )
    assert result.returncode != 0
    assert "unsupported arch" in result.stderr
