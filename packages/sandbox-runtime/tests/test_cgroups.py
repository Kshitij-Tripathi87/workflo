"""Tests for cgroups v2 controller."""

import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

from sandbox_runtime.config import CgroupConfig
from sandbox_runtime.cgroups import setup_cgroup, attach_process, cleanup_cgroup


def test_setup_cgroup():
    config = CgroupConfig(
        sandbox_id="test-123",
        memory_mb=1024,
        cpu_cores=1.5,
        pids_max=100,
    )

    with patch("pathlib.Path.mkdir") as mock_mkdir, \
         patch("pathlib.Path.write_text") as mock_write, \
         patch.object(Path, "exists", return_value=True):
        path = setup_cgroup(config)

        assert path == Path("/sys/fs/cgroup/workflo/test-123")
        assert mock_mkdir.called

        # Check write calls - write_text is called with content only (self is the Path)
        # The calls are: subtree_control x2, memory.max, memory.swap.max,
        # cpu.max, pids.max, io.weight
        contents = [call[0][0] for call in mock_write.call_args_list]

        # Controllers enabled on both levels of the chain
        assert contents.count("+memory +cpu +io +pids") == 2
        assert "1024M" in contents
        assert "0" in contents
        assert "150000 100000" in contents
        assert "default 100" in contents


def test_setup_cgroup_fails_when_delegation_missing():
    """A leaf without control files is a delegation misconfiguration —
    fail loudly instead of EACCESing cryptically on the first write."""
    config = CgroupConfig(
        sandbox_id="test-123",
        memory_mb=1024,
        cpu_cores=1.5,
        pids_max=100,
    )

    with patch("pathlib.Path.mkdir"), \
         patch("pathlib.Path.write_text"), \
         patch.object(Path, "exists", return_value=False):
        with pytest.raises(RuntimeError, match="memory.max"):
            setup_cgroup(config)


def test_attach_process():
    with patch("pathlib.Path.write_text") as mock_write:
        attach_process(Path("/sys/fs/cgroup/workflo/test-123"), 42)
        mock_write.assert_called_with("42")


def test_cleanup_cgroup():
    with patch("pathlib.Path.rmdir") as mock_rmdir:
        cleanup_cgroup(Path("/sys/fs/cgroup/workflo/test-123"))
        mock_rmdir.assert_called_once()