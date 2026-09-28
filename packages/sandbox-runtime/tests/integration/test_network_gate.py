"""Network workload-flow policy gate (spec §6; NI-4, NI-5 NE-1 subset).

Linux-only: requires the named netns, veth and nftables. Verifies the
F-4/F-10 hardening — that a workload inside the netns cannot reach the
host veth end except for DNS and cannot connect to the agent address.
"""

from __future__ import annotations

import subprocess
import uuid

import pytest

from sandbox_runtime.config import NetworkConfig
from sandbox_runtime.network import (
    setup_private_network,
    teardown_network,
    verify_network_isolation,
)

pytestmark = pytest.mark.linux


def _require_linux():
    import os
    import sys
    if sys.platform != "linux":
        pytest.skip("network gate is Linux-only")
    if os.geteuid() != 0:
        pytest.skip("namespace execution requires root on this host")
    import shutil
    for tool in ("ip", "nft", "dnsmasq"):
        if not shutil.which(tool):
            pytest.skip(f"{tool} not installed")


@pytest.fixture(scope="module")
def net_ctx():
    _require_linux()
    config = NetworkConfig(sandbox_id=f"sg-{uuid.uuid4().hex[:10]}")
    try:
        setup_private_network(config)
        yield config
    finally:
        teardown_network(config)


def _try(netns: str, expr: str) -> bool:
    """Run a connectivity attempt inside the netns. True = CONNECTED (bad)."""
    result = subprocess.run(
        ["ip", "netns", "exec", netns, "timeout", "3", "bash", "-c", expr],
        capture_output=True,
    )
    return result.returncode == 0


class TestFlowPolicy:
    def test_external_egress_blocked(self, net_ctx):
        results = verify_network_isolation(net_ctx.netns_name)
        blocked = [k for k, v in results.items() if v.get("blocked")]
        assert len(blocked) == len(results), f"some destinations reachable: {results}"

    def test_ni5_host_veth_non_dns_blocked(self, net_ctx):
        """F-4: the host veth end must not expose arbitrary ports."""
        assert not _try(net_ctx.netns_name,
                        f"echo > /dev/tcp/{net_ctx.host_ip}/80")
        assert not _try(net_ctx.netns_name,
                        f"echo > /dev/tcp/{net_ctx.host_ip}/443")

    def test_ni5_dns_on_host_end_works(self, net_ctx):
        """Internal DNS is the ONLY host-end service reachable (NI-5)."""
        result = subprocess.run(
            ["ip", "netns", "exec", net_ctx.netns_name,
             "getent", "hosts", "app.workflo.internal"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert net_ctx.app_ip in result.stdout

    def test_ni4_app_to_agent_denied(self, net_ctx):
        """F-10: nothing connects TO the agent's address."""
        assert not _try(net_ctx.netns_name,
                        f"echo > /dev/tcp/{net_ctx.agent_ip}/80")

    def test_app_to_browser_test_denied(self, net_ctx):
        assert not _try(net_ctx.netns_name,
                        f"echo > /dev/tcp/{net_ctx.browser_ip}/9222")
        assert not _try(net_ctx.netns_name,
                        f"echo > /dev/tcp/{net_ctx.test_ip}/5432")

    def test_agent_address_unreachable_from_host(self, net_ctx):
        """The whole netns is private: even the HOST cannot reach the
        agent address through normal routing."""
        result = subprocess.run(
            ["timeout", "2", "bash", "-c",
             f"echo > /dev/tcp/{net_ctx.agent_ip}/80"],
            capture_output=True,
        )
        assert result.returncode != 0
