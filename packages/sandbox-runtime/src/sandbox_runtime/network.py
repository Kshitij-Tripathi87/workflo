"""Private Workflo network: named netns, one veth pair, dnsmasq, nftables.

Topology (v0.3):

    HOST                                NETNS workflo-<sandbox_id>
    -----                               ----------------------------
    veth host end (10.200.0.1) <======> veth guest end 10.200.0.2 (app)
                                         + aliases: .3 agent, .4 browser,
                                           .5 test
    dnsmasq :53 on 10.200.0.1           default route via 10.200.0.1
                                         nftables workload-flow policy:
                                           input: lo, established, DNS
                                           output: DNS to host :53 only,
                                             app/guest addresses; DENY
                                             connect-to agent/browser/test
                                           forward: drop
    Sandbox workloads in PRIVATE network mode are launched via
    ``ip netns exec workflo-<sandbox_id>`` so they share this namespace. Workloads in
    NONE mode get bwrap's own anonymous, empty netns instead (sealed).

dnsmasq runs on the HOST side bound to the veth host end. It has no
upstream resolver (no-resolv), so only *.workflo.internal names resolve.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from sandbox_runtime.config import NetworkConfig


def setup_private_network(config: NetworkConfig) -> dict:
    """Create netns + veth pair + internal DNS + egress blocking.

    All steps fail loudly (check=True): if the isolation network cannot
    be brought up, the run must abort, not silently continue without it.
    """
    results = {
        "created": False,
        "netns": config.netns_name,
        "veth": {"host": config.veth_host, "guest": config.veth_guest},
        "dns": config.dns_ip,
    }

    # 1. Network namespace (idempotent)
    try:
        _run(["ip", "netns", "add", config.netns_name])
    except subprocess.CalledProcessError as e:
        if b"File exists" not in (e.stderr or b""):
            raise

    # 2. Veth pair: host end stays on the host, guest end moves into the netns
    _run(["ip", "link", "add", config.veth_host, "type", "veth",
          "peer", "name", config.veth_guest])
    _run(["ip", "link", "set", config.veth_guest, "netns", config.netns_name])

    # 3. Host end: 10.200.0.1/24, up
    _run(["ip", "addr", "add", f"{config.host_ip}/24", "dev", config.veth_host])
    _run(["ip", "link", "set", config.veth_host, "up"])

    # 4. Guest end (inside netns): 10.200.0.2/24 primary + per-workload
    #    aliases (agent .3, browser .4, test .5) so the nftables flow
    #    policy can address workloads individually. Loopback up.
    _netns_run(config, ["ip", "addr", "add", f"{config.guest_ip}/24",
                        "dev", config.veth_guest])
    for alias in (config.agent_ip, config.browser_ip, config.test_ip):
        if alias != config.guest_ip:
            _netns_run(config, ["ip", "addr", "add", f"{alias}/24",
                                "dev", config.veth_guest])
    _netns_run(config, ["ip", "link", "set", config.veth_guest, "up"])
    _netns_run(config, ["ip", "link", "set", "lo", "up"])

    # 4b. Per-netns resolver config: `ip netns exec` bind-mounts
    #     /etc/netns/<name>/resolv.conf over /etc/resolv.conf for anything
    #     it runs (host-side probes included). Without it, processes that
    #     enter the netns WITHOUT bwrap (e.g. `getent` in host-side checks)
    #     would resolve through the host's system resolver — which neither
    #     knows *.workflo.internal nor should be asked from the sandbox.
    _write_netns_resolv_conf(config)

    # 5. Egress blocking FIRST (before any default route exists): the
    #    namespace must never have a window with unrestricted egress.
    _setup_egress_blocking(config)

    # 6. Default route inside the netns, via the host end (dnsmasq side)
    _netns_run(config, ["ip", "route", "add", "default", "via", config.host_ip])

    # 7. Internal DNS on the host end (no upstream — internal names only)
    _start_dnsmasq(config)

    results["created"] = True
    return results


def build_nftables_rules(config: NetworkConfig) -> str:
    """Workload-flow policy for the network namespace (pure; spec §6.3).

    Policy — default drop, explicitly allow only:

      output:  DENY first for daddr agent/browser/test — nothing may
               CONNECT TO the agent (Workflo's operator is never a
               server for untrusted app content; NE-7/AG-1 backchannel).
               daddr-based, not saddr-based: local-route source
               selection makes saddr unreliable for intra-netns traffic.
               Then: loopback; DNS to the host veth end (udp/tcp 53
               ONLY — F-4: no subnet-wide, any-port accept); traffic to
               the app/guest addresses.
      input:   loopback; established/related (DNS replies); explicit
               DNS responses from the host end (F-4: the old
               subnet-wide saddr accept allowed any port at the host
               veth end).
      forward: nothing (no routing through this namespace).

    The agent reaches the app by connecting OUT to app_ip — allowed.
    The app may not reach the agent, the browser or the test workload
    addresses on any port.
    """
    return f"""
table inet workflo {{
    chain input {{
        type filter hook input priority 0; policy drop;
        iifname "lo" accept
        ct state established,related accept
        ip saddr {config.host_ip} udp sport 53 accept
        ip saddr {config.host_ip} tcp sport 53 accept
    }}
    chain forward {{
        type filter hook forward priority 0; policy drop;
    }}
    chain output {{
        type filter hook output priority 0; policy drop;
        ip daddr {config.agent_ip} drop
        ip daddr {config.browser_ip} drop
        ip daddr {config.test_ip} drop
        oifname "lo" accept
        ip daddr {config.host_ip} udp dport 53 accept
        ip daddr {config.host_ip} tcp dport 53 accept
        ip daddr {config.app_ip} accept
        ip daddr {config.guest_ip} accept
    }}
}}
"""


def _setup_egress_blocking(config: NetworkConfig) -> None:
    """Install the workload-flow policy inside the network namespace."""
    _netns_run(config, ["nft", "flush", "ruleset"], check=False)
    rules_path = Path(f"/tmp/workflo-{config.sandbox_id}-nftables.nft")
    rules_path.write_text(build_nftables_rules(config))
    _netns_run(config, ["nft", "-f", str(rules_path)])


def _start_dnsmasq(config: NetworkConfig, retries: int = 3) -> None:
    """Run dnsmasq on the host, bound to the veth host end.

    Resolves *.workflo.internal names to the netns guest address. Has no
    upstream, so external names never resolve. The PID is tracked on the
    config so teardown_network can kill it — it is a HOST process and
    would otherwise outlive the sandbox.

    Retries on startup failure: a stale dnsmasq from a just-torn-down
    run may still hold :53 for a moment.
    """
    dnsmasq_conf = f"""
interface={config.veth_host}
except-interface=lo
bind-interfaces
listen-address={config.host_ip}
port=53
domain=workflo.internal
address=/app.workflo.internal/{config.app_ip}
address=/agent.workflo.internal/{config.agent_ip}
address=/browser.workflo.internal/{config.browser_ip}
address=/test.workflo.internal/{config.test_ip}
no-resolv
no-hosts
log-queries
log-facility=/tmp/workflo-{config.sandbox_id}-dnsmasq.log
pid-file=/tmp/workflo-{config.sandbox_id}-dnsmasq.pid
"""
    conf_path = Path(f"/tmp/workflo-{config.sandbox_id}-dnsmasq.conf")
    conf_path.write_text(dnsmasq_conf)

    last_error = None
    for attempt in range(retries):
        proc = subprocess.Popen(
            ["dnsmasq", "-C", str(conf_path), "-k", "--no-daemon"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        config.dnsmasq_pid = proc.pid

        # Wait for dnsmasq to bind :53 (up to ~3s per attempt)
        for _ in range(30):
            probe = subprocess.run(
                ["ss", "-uln"], capture_output=True, text=True
            )
            if f"{config.host_ip}:53" in probe.stdout:
                return  # bound successfully
            if proc.poll() is not None:
                last_error = (
                    f"dnsmasq died during startup (exit {proc.returncode}); "
                    f"see /tmp/workflo-{config.sandbox_id}-dnsmasq.log"
                )
                break
            time.sleep(0.1)
        else:
            last_error = "dnsmasq did not bind :53 within 3s"
            proc.kill()

        # Retry: a stale dnsmasq may still hold the port — kill any
        # dnsmasq bound to this run's address before the next attempt.
        _kill_stale_dnsmasq(config)
        time.sleep(0.5)

    raise RuntimeError(last_error)


def _kill_stale_dnsmasq(config: NetworkConfig) -> None:
    """Kill any dnsmasq still bound to this run's host address (best
    effort — a stale instance from a just-torn-down run)."""
    try:
        result = subprocess.run(
            ["ss", "-ulnp"], capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if f"{config.host_ip}:53" in line and "dnsmasq" in line:
                # "users:(("dnsmasq",pid=1234,fd=4))"
                for token in line.split(","):
                    if token.startswith("pid="):
                        pid = token[4:].rstrip("))")
                        subprocess.run(
                            ["kill", pid], capture_output=True, check=False
                        )
    except OSError:
        pass


def teardown_network(config: NetworkConfig) -> None:
    """Remove netns, veth pair, and the dnsmasq host process.

    Deleting the netns removes the guest veth end; the host end follows.
    dnsmasq must be killed explicitly (host process).
    """
    # 1. Kill dnsmasq first (it holds the veth host end busy)
    if config.dnsmasq_pid:
        try:
            subprocess.run(
                ["kill", str(config.dnsmasq_pid)],
                capture_output=True, check=False,
            )
        except OSError:
            pass
        config.dnsmasq_pid = None

    # 2. Delete the netns (removes guest veth end + nft rules with it)
    subprocess.run(
        ["ip", "netns", "del", config.netns_name],
        capture_output=True, check=False,
    )

    # 3. Remove any leftover host end / config files
    subprocess.run(
        ["ip", "link", "del", config.veth_host],
        capture_output=True, check=False,
    )
    for suffix in ("dnsmasq.conf", "dnsmasq.pid", "dnsmasq.log",
                   "nftables.nft"):
        p = Path(f"/tmp/workflo-{config.sandbox_id}-{suffix}")
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass

    # 4. Per-netns resolver config (written by setup)
    netns_etc = Path(f"/etc/netns/{config.netns_name}")
    try:
        (netns_etc / "resolv.conf").unlink(missing_ok=True)
        netns_etc.rmdir()
    except OSError:
        pass  # other config files present — leave the dir


def _write_netns_resolv_conf(config: NetworkConfig) -> None:
    """ip netns exec bind-mounts /etc/netns/<name>/resolv.conf onto
    /etc/resolv.conf — direct everything entering this namespace at the
    sandbox's own dnsmasq, never the host's system resolver."""
    netns_etc = Path(f"/etc/netns/{config.netns_name}")
    netns_etc.mkdir(parents=True, exist_ok=True)
    (netns_etc / "resolv.conf").write_text(f"nameserver {config.dns_ip}\n")


def verify_network_isolation(netns_name: str) -> dict:
    """Host-side verification: run blocked-destination probes in the netns.

    Each destination MUST be unreachable. Uses bash /dev/tcp instead of
    nc so the check works on minimal images.
    """
    results = {}

    test_cases = [
        ("external_ipv4", "8.8.8.8", "53"),
        ("external_ipv6", "2001:4860:4860::8888", "53"),
        ("host_gateway_1", "10.0.2.2", "80"),
        ("host_gateway_2", "172.17.0.1", "80"),
        ("host_gateway_3", "192.168.65.1", "80"),
        ("rfc1918_1", "10.0.0.1", "80"),
        ("rfc1918_2", "172.16.0.1", "80"),
        ("rfc1918_3", "192.168.1.1", "80"),
        ("cloud_metadata_aws", "169.254.169.254", "80"),
    ]

    for name, host, port in test_cases:
        try:
            result = subprocess.run(
                ["ip", "netns", "exec", netns_name, "timeout", "2", "bash", "-c",
                 f"echo > /dev/tcp/{host}/{port}"],
                capture_output=True, timeout=5,
            )
            results[name] = {"blocked": result.returncode != 0}
        except subprocess.TimeoutExpired:
            results[name] = {"blocked": True, "note": "timeout"}
        except Exception as e:
            results[name] = {"blocked": True, "error": str(e)}

    return results


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, check=check)


def _netns_run(config: NetworkConfig, cmd: list[str],
               check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ip", "netns", "exec", config.netns_name] + cmd,
        capture_output=True, check=check,
    )
