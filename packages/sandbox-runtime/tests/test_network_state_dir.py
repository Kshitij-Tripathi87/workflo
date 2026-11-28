import os
import stat

import pytest

from sandbox_runtime import network
from sandbox_runtime.config import NetworkConfig


pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "geteuid"),
    reason="private runtime directory ownership checks require POSIX",
)


def test_run_state_dir_creates_owned_private_directories(tmp_path, monkeypatch):
    root = tmp_path / "run" / "workflo"
    monkeypatch.setattr(network, "RUN_STATE_ROOT", root)

    state_dir = network._run_state_dir(NetworkConfig(sandbox_id="test"))

    assert state_dir == root / "workflo-test"
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(state_dir.stat().st_mode) == 0o700
    assert root.stat().st_uid == os.geteuid()
    assert state_dir.stat().st_uid == os.geteuid()


def test_run_state_dir_tolerates_a_shared_parent_directory(tmp_path, monkeypatch):
    """The runtime must own only its own leaf, not the shared run directory.

    /run/workflo also holds the supervisor socket and the worker host's vmm/
    vsock directories, so it may legitimately exist with non-0700 permissions.
    Requiring or chmod'ing the parent would break those components.
    """
    shared = tmp_path / "shared-run"
    shared.mkdir()
    shared.chmod(0o755)
    monkeypatch.setattr(network, "RUN_STATE_ROOT", shared / "sandbox-network")

    state_dir = network._run_state_dir(NetworkConfig(sandbox_id="test"))

    assert state_dir == shared / "sandbox-network" / "workflo-test"
    assert stat.S_IMODE(state_dir.stat().st_mode) == 0o700
    # The shared parent keeps the permissions its other owners need.
    assert stat.S_IMODE(shared.stat().st_mode) == 0o755


def test_run_state_dir_rejects_preexisting_group_writable_root(tmp_path, monkeypatch):
    root = tmp_path / "run" / "workflo"
    root.mkdir(parents=True)
    root.chmod(0o777)
    monkeypatch.setattr(network, "RUN_STATE_ROOT", root)

    with pytest.raises(PermissionError, match="unsafe private runtime directory"):
        network._run_state_dir(NetworkConfig(sandbox_id="test"))


def test_run_state_dir_rejects_symlinked_run_directory(tmp_path, monkeypatch):
    target = tmp_path / "attacker-controlled"
    target.mkdir()
    root = tmp_path / "run" / "workflo"
    root.parent.mkdir()
    root.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(network, "RUN_STATE_ROOT", root)

    with pytest.raises(PermissionError, match="unsafe private runtime directory"):
        network._run_state_dir(NetworkConfig(sandbox_id="test"))
