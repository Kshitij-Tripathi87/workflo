"""Tests for bwrap command builder."""

import pytest
from pathlib import Path

from sandbox_runtime.config import BwrapConfig, WorkloadType, NetworkMode
from sandbox_runtime.bwrap import build_bwrap_args, build_launch_command


def _config(**overrides):
    defaults = dict(
        sandbox_id="test-123",
        workload_type=WorkloadType.TEST,
        readonly_root=Path("/opt/workflo/rootfs"),
        workspace_dir=Path("/tmp/workspace"),
        evidence_dir=Path("/tmp/evidence/artifacts"),
        tmp_dir=Path("/tmp/tmp"),
        home_dir=Path("/tmp/home"),
        command=["echo", "hello"],
    )
    defaults.update(overrides)
    return BwrapConfig(**defaults)


def test_build_bwrap_args_basic():
    config = _config()

    args = build_bwrap_args(config)

    # Check essential flags
    assert args[0] == "bwrap"
    assert "--unshare-user" in args
    assert "--unshare-pid" in args
    assert "--unshare-ipc" in args
    assert "--unshare-uts" in args
    assert "--unshare-cgroup" in args

    # Check binds
    assert "--ro-bind" in args
    assert any("workflo/rootfs" in str(arg) or "workflo\\rootfs" in str(arg) for arg in args)
    assert "--bind" in args
    assert any("tmp/workspace" in str(arg) or "tmp\\workspace" in str(arg) for arg in args)

    # Check command
    assert "--" in args
    idx = args.index("--")
    assert args[idx + 1:] == ["echo", "hello"]


def test_build_bwrap_args_with_env():
    config = _config(env={"FOO": "bar", "BAZ": "qux"})

    args = build_bwrap_args(config)

    assert "--setenv" in args
    idx = args.index("--setenv")
    assert args[idx + 1] == "FOO"
    assert args[idx + 2] == "bar"


def test_network_none_sealed_unshare_net():
    """NONE mode must use bwrap's anonymous empty netns."""
    config = _config(network_mode=NetworkMode.NONE)

    args = build_bwrap_args(config)

    assert "--unshare-net" in args


def test_network_private_no_unshare_net():
    """PRIVATE mode joins the NAMED netns — --unshare-net would create a
    different anonymous one and silently bypass veth/dnsmasq/nftables."""
    config = _config(network_mode=NetworkMode.PRIVATE, netns="workflo-sbx-1")

    args = build_bwrap_args(config)

    assert "--unshare-net" not in args


def test_private_launch_wrapped_with_ip_netns_exec():
    """PRIVATE mode must launch via `ip netns exec <netns> bwrap ...`."""
    config = _config(network_mode=NetworkMode.PRIVATE, netns="workflo-sbx-1")

    cmd = build_launch_command(config)

    assert cmd[:4] == ["ip", "netns", "exec", "workflo-sbx-1"]
    assert cmd[4] == "bwrap"


def test_private_without_netns_rejected():
    """PRIVATE mode without an explicit netns is a wiring error — fail loud."""
    config = _config(network_mode=NetworkMode.PRIVATE, netns=None)

    with pytest.raises(ValueError, match="netns"):
        build_launch_command(config)


def test_none_launch_has_no_wrapper():
    config = _config(network_mode=NetworkMode.NONE)

    cmd = build_launch_command(config)

    assert cmd[0] == "bwrap"


def test_seccomp_passed_as_fd_number():
    """bwrap --seccomp takes an FD number, not a path."""
    config = _config(seccomp_profile=Path("/opt/workflo/seccomp/test.allow"))

    args = build_bwrap_args(config, seccomp_fd=7)

    idx = args.index("--seccomp")
    assert args[idx + 1] == "7"


def test_resolv_conf_bind_when_private():
    config = _config(
        network_mode=NetworkMode.PRIVATE,
        netns="workflo-sbx-1",
        resolv_conf=Path("/tmp/run/resolv.conf"),
    )

    args = build_bwrap_args(config)

    idx = args.index("--ro-bind")
    # find the resolv.conf bind specifically
    assert any(
        str(arg).endswith("resolv.conf") and args[i + 1] == "/etc/resolv.conf"
        for i, arg in enumerate(args[:-1])
    )


def test_no_resolv_conf_bind_when_none():
    config = _config(network_mode=NetworkMode.NONE)

    args = build_bwrap_args(config)

    assert "/etc/resolv.conf" not in args
