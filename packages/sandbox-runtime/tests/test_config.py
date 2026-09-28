"""Tests for sandbox-runtime config models."""

import pytest
from pathlib import Path

from sandbox_runtime.config import (
    BwrapConfig,
    CgroupConfig,
    NetworkConfig,
    RunConfig,
    DepMode,
    NetworkMode,
    WorkloadType,
)


def test_bwrap_config_defaults():
    config = BwrapConfig(
        sandbox_id="test-123",
        workload_type=WorkloadType.TEST,
        readonly_root=Path("/opt/workflo/rootfs"),
        workspace_dir=Path("/tmp/workspace"),
        evidence_dir=Path("/tmp/evidence"),
        tmp_dir=Path("/tmp/tmp"),
        home_dir=Path("/tmp/home"),
    )
    
    assert config.memory_mb == 2048
    assert config.cpu_cores == 2.0
    assert config.network_mode == NetworkMode.NONE
    assert "CAP_SYS_ADMIN" in config.drop_caps
    assert "CAP_CHOWN" in config.keep_caps


def test_run_config():
    config = RunConfig(
        sandbox_id="test-456",
        repo_url="https://github.com/test/repo.git",
        probe_groups=["surface", "security"],
    )
    
    assert config.memory_mb == 2048
    assert config.dep_mode == DepMode.PREFLIGHT_CACHE
    assert "surface" in config.probe_groups


def test_network_config():
    config = NetworkConfig(sandbox_id="test-789")

    assert config.subnet == "10.200.0.0/24"
    # Single-veth topology: host end runs dnsmasq, guest end is the only
    # address in the netns; all *.workflo.internal names point there.
    assert config.host_ip == "10.200.0.1"
    assert config.guest_ip == "10.200.0.2"
    assert config.app_ip == "10.200.0.2"
    assert config.dns_ip == "10.200.0.1"
    assert config.dnsmasq_pid is None
    assert config.netns_name == "workflo-test-789"
    # IFNAMSIZ: interface names must stay under 16 chars
    assert len(config.veth_host) <= 15
    assert len(config.veth_guest) <= 15
    assert config.veth_host == "wf-test-789-h"
    assert config.veth_guest == "wf-test-789-g"