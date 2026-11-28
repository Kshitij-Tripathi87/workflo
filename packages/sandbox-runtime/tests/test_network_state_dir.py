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
