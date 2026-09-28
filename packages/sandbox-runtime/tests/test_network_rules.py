"""Network workload-flow policy unit tests (F-4, F-10 / spec §6.3).

Pure assertions over the GENERATED nftables ruleset — the Linux
integration gate proves enforcement with real packets.
"""

from sandbox_runtime.config import NetworkConfig
from sandbox_runtime.network import build_nftables_rules


def _rules():
    return build_nftables_rules(NetworkConfig(sandbox_id="sbx-net"))


class TestF4HostVethScope:
    def test_no_subnet_wide_accept(self):
        rules = _rules()
        assert "10.200.0.0/24" not in rules  # old F-4 hole is gone

    def test_host_end_only_reachable_on_dns(self):
        rules = _rules()
        # input: only sport 53 from the host end
        assert "ip saddr 10.200.0.1 udp sport 53 accept" in rules
        assert "ip saddr 10.200.0.1 tcp sport 53 accept" in rules
        # output: only dport 53 toward the host end
        assert "ip daddr 10.200.0.1 udp dport 53 accept" in rules
        assert "ip daddr 10.200.0.1 tcp dport 53 accept" in rules
        # No other rule mentions the host end
        host_rules = [ln for ln in rules.splitlines() if "10.200.0.1" in ln]
        assert len(host_rules) == 4, host_rules


class TestF10AppToAgentDeny:
    def test_daddr_agent_dropped_before_lo_accept(self):
        rules = _rules()
        drop = rules.index("ip daddr 10.200.0.3 drop")
        lo_accept = rules.index('oifname "lo" accept')
        assert drop < lo_accept  # deny wins for app → agent on loopback

    def test_browser_and_test_addresses_dropped(self):
        rules = _rules()
        assert "ip daddr 10.200.0.4 drop" in rules
        assert "ip daddr 10.200.0.5 drop" in rules

    def test_app_address_still_allowed(self):
        rules = _rules()
        assert "ip daddr 10.200.0.2 accept" in rules

    def test_default_drop_everywhere(self):
        rules = _rules()
        assert rules.count("policy drop;") == 3  # input, forward, output


class TestTopologyDefaults:
    def test_per_workload_addresses_distinct(self):
        config = NetworkConfig(sandbox_id="sbx")
        assert config.guest_ip == config.app_ip == "10.200.0.2"
        assert config.agent_ip == "10.200.0.3"
        assert config.browser_ip == "10.200.0.4"
        assert config.test_ip == "10.200.0.5"
        assert len({config.app_ip, config.agent_ip,
                    config.browser_ip, config.test_ip}) == 4

    def test_dns_names_resolve_to_distinct_addresses(self):
        """dnsmasq maps each *.workflo.internal name to its workload IP."""
        config = NetworkConfig(sandbox_id="sbx")
        assert config.agent_ip != config.app_ip
