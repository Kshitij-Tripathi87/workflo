"""Egress policy tests: default-deny, always-blocked, fail-closed."""

from __future__ import annotations

import pytest

from workflo_schema.contracts.runspec import (
    AllowedDestinationV1,
    NetworkPolicySpecV1,
    NetworkProtocol,
)

from workflo_worker_host.network import (
    ALWAYS_BLOCKED,
    EgressPolicyError,
    apply_ruleset_or_block,
    build_nftables_ruleset,
    validate_policy,
)


def _deny() -> NetworkPolicySpecV1:
    return NetworkPolicySpecV1()


def test_default_policy_is_deny_and_validates():
    validate_policy(_deny())  # no raise


def test_non_deny_default_refused():
    policy = NetworkPolicySpecV1(default="deny")
    tampered = policy.model_copy(update={"default": "allow"})
    with pytest.raises(EgressPolicyError):
        validate_policy(tampered)


def test_hostname_destination_refused():
    policy = NetworkPolicySpecV1(
        allowed_destinations=(
            AllowedDestinationV1(host="pypi.org", port=443, protocol=NetworkProtocol.TCP),
        )
    )
    with pytest.raises(EgressPolicyError, match="IP literal"):
        validate_policy(policy)


@pytest.mark.parametrize(
    "host",
    ["169.254.169.254", "10.0.0.5", "172.16.0.9", "192.168.1.1", "100.64.0.1", "fe80::1"],
)
def test_always_blocked_destinations_refused(host):
    policy = NetworkPolicySpecV1(
        allowed_destinations=(
            AllowedDestinationV1(host=host, port=80, protocol=NetworkProtocol.TCP),
        )
    )
    with pytest.raises(EgressPolicyError, match="always-blocked"):
        validate_policy(policy)


def test_duplicate_destinations_refused():
    policy = NetworkPolicySpecV1(
        allowed_destinations=(
            AllowedDestinationV1(host="1.1.1.1", port=443, protocol=NetworkProtocol.TCP),
            AllowedDestinationV1(host="1.1.1.1", port=443, protocol=NetworkProtocol.TCP),
        )
    )
    with pytest.raises(EgressPolicyError, match="duplicate"):
        validate_policy(policy)


def test_ruleset_is_default_deny_with_explicit_allows():
    policy = NetworkPolicySpecV1(
        allowed_destinations=(
            AllowedDestinationV1(host="8.8.8.8", port=53, protocol=NetworkProtocol.UDP),
        )
    )
    ruleset = build_nftables_ruleset("sbx-1", policy)
    assert "policy drop;" in ruleset
    assert "ip daddr 8.8.8.8 udp dport 53" in ruleset
    assert "169.254.169.254" in ruleset  # metadata explicitly blocked
    assert "counter drop" in ruleset


def test_ruleset_without_allows_is_full_deny():
    ruleset = build_nftables_ruleset("sbx-1", _deny())
    assert "no allowed destinations: full default-deny" in ruleset


def test_apply_failure_means_no_egress_not_open_egress():
    def broken(ruleset):
        raise RuntimeError("nft unavailable")

    verdict = apply_ruleset_or_block(broken, "sbx-1", _deny())
    assert verdict.enforced is False
    assert "nft unavailable" in verdict.reason


def test_apply_invalid_policy_blocks():
    verdict = apply_ruleset_or_block(lambda r: None, "sbx-1", _deny().model_copy(update={"default": "allow"}))
    assert verdict.enforced is False


def test_apply_success_is_enforced():
    applied = {}
    verdict = apply_ruleset_or_block(applied.setdefault("r", None) or (lambda r: applied.__setitem__("r", r)), "sbx-1", _deny())
    assert verdict.enforced is True
    assert "r" in applied


def test_metadata_is_in_the_always_blocked_set():
    import ipaddress

    addr = ipaddress.ip_address("169.254.169.254")
    assert any(
        addr.version == net.version and addr in net for net in ALWAYS_BLOCKED
    )
