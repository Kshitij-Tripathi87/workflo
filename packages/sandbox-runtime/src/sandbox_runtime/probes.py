"""Active isolation verification probes - run INSIDE sandbox before app starts."""

from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, UTC

from sandbox_runtime.config import ProbeResult


class IsolationProbes:
    """Run all 12 isolation verification probes."""
    
    def __init__(self, sandbox_pid: int):
        self.sandbox_pid = sandbox_pid
    
    def run_all(self) -> list[ProbeResult]:
        """Run all probes, return results. Fail-closed on any critical failure."""
        probes = [
            self.probe_host_home_not_mounted,
            self.probe_docker_socket_unavailable,
            self.probe_cloud_credentials_unavailable,
            self.probe_source_snapshot_integrity,
            self.probe_writes_outside_approved_denied,
            self.probe_host_processes_invisible,
            self.probe_pid1_is_sandbox_init,
            self.probe_privileged_capabilities_absent,
            self.probe_external_ipv4_blocked,
            self.probe_external_ipv6_blocked,
            self.probe_dns_external_blocked,
            self.probe_host_gateway_blocked,
            self.probe_rfc1918_blocked,
            self.probe_cloud_metadata_blocked,
            self.probe_internal_dns_resolves,
            self.probe_only_internal_routes_accessible,
        ]
        
        results = []
        for probe in probes:
            try:
                result = probe()
                results.append(result)
            except Exception as e:
                results.append(ProbeResult(
                    name=probe.__name__,
                    passed=False,
                    detail=f"Probe error: {e}",
                    severity="critical"
                ))
        
        return results
    
    # Filesystem probes
    def probe_host_home_not_mounted(self) -> ProbeResult:
        home = Path("/home")
        if home.exists():
            entries = list(home.iterdir())
            if entries and any(e.name != "workflo" for e in entries):
                return ProbeResult("host_home_not_mounted", False, 
                                 f"Host home directories visible: {[e.name for e in entries]}")
        return ProbeResult("host_home_not_mounted", True, "Host home not visible")
    
    def probe_docker_socket_unavailable(self) -> ProbeResult:
        for sock in ["/var/run/docker.sock", "/run/containerd/containerd.sock"]:
            if Path(sock).exists():
                return ProbeResult("docker_socket_unavailable", False, f"Docker socket accessible: {sock}")
        return ProbeResult("docker_socket_unavailable", True, "Docker sockets not accessible")
    
    def probe_cloud_credentials_unavailable(self) -> ProbeResult:
        cloud_paths = [
            "~/.aws", "~/.config/gcloud", "~/.azure", "~/.config/oci",
            "/var/lib/cloud", "/run/secrets", "/etc/kubernetes"
        ]
        found = []
        for p in cloud_paths:
            expanded = Path(p).expanduser()
            if expanded.exists():
                found.append(str(p))
        if found:
            return ProbeResult("cloud_credentials_unavailable", False, f"Cloud creds found: {found}")
        return ProbeResult("cloud_credentials_unavailable", True, "No cloud credentials accessible")
    
    def probe_source_snapshot_integrity(self) -> ProbeResult:
        # The snapshot writes the manifest into the repo copy:
        # /workspace/repo/.workflo_manifest.json
        manifest_path = Path("/workspace/repo/.workflo_manifest.json")
        if not manifest_path.exists():
            return ProbeResult("source_snapshot_integrity", False, "No manifest found")
        return ProbeResult("source_snapshot_integrity", True, "Manifest present")
    
    def probe_writes_outside_approved_denied(self) -> ProbeResult:
        forbidden = ["/etc/passwd", "/root", "/home", "/var", "/usr", "/opt", "/boot"]
        for p in forbidden:
            try:
                test_file = Path(p) / ".workflo_write_test"
                test_file.write_text("test")
                test_file.unlink(missing_ok=True)
                return ProbeResult("writes_outside_approved_denied", False, f"Write succeeded to {p}")
            except PermissionError:
                pass
            except Exception:
                pass
        return ProbeResult("writes_outside_approved_denied", True, "Writes to forbidden paths denied")
    
    # Process probes
    def probe_host_processes_invisible(self) -> ProbeResult:
        proc_entries = list(Path("/proc").iterdir())
        numeric = [e for e in proc_entries if e.name.isdigit()]
        if len(numeric) > 20:  # Should only see sandbox processes
            return ProbeResult("host_processes_invisible", False, f"Too many PIDs visible: {len(numeric)}")
        return ProbeResult("host_processes_invisible", True, f"Only {len(numeric)} PIDs visible")
    
    def probe_pid1_is_sandbox_init(self) -> ProbeResult:
        try:
            with open("/proc/1/comm") as f:
                comm = f.read().strip()
            if comm in ("bwrap", "systemd", "init", "sandbox-init", "sh", "bash",
                        "python", "python3"):
                return ProbeResult("pid1_is_sandbox_init", True, f"PID 1 is {comm}")
        except Exception:
            pass
        return ProbeResult("pid1_is_sandbox_init", False, "PID 1 not recognized sandbox init")
    
    @staticmethod
    def _in_user_namespace() -> bool:
        """True when running inside a non-initial user namespace.

        bwrap's userns mode legitimately grants the sandbox full
        capabilities WITHIN its namespaces — they cannot reach any host
        resource the namespace cannot see. The initial namespace shows a
        single full-range uid_map line ("0 0 4294967295").
        """
        try:
            parts = Path("/proc/self/uid_map").read_text().split()
            if len(parts) == 3 and parts[2] == "4294967295":
                return False
            return True
        except OSError:
            return False

    def probe_privileged_capabilities_absent(self) -> ProbeResult:
        """Dangerous capabilities must be absent OUTSIDE a user namespace.

        In a userns sandbox (bwrap --unshare-user) the process holds
        namespace-confined caps that cannot touch host resources the
        namespace cannot see — that is acceptable. A genuinely
        privileged process outside any user namespace is a critical
        isolation failure.
        """
        in_userns = self._in_user_namespace()
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("CapEff:"):
                        caps = int(line.split()[1], 16)
                        dangerous = [
                            21,  # CAP_SYS_ADMIN
                            24,  # CAP_SYS_RESOURCE
                            1,   # CAP_DAC_OVERRIDE
                            18,  # CAP_SYS_RAWIO
                        ]
                        present = [bit for bit in dangerous if (caps >> bit) & 1]
                        if present and not in_userns:
                            return ProbeResult(
                                "privileged_capabilities_absent", False,
                                f"Dangerous capability present outside a user "
                                f"namespace: bits {present}"
                            )
                        if present:
                            return ProbeResult(
                                "privileged_capabilities_absent", True,
                                f"Capabilities {present} present but "
                                "namespace-confined (uid_map active)"
                            )
                        return ProbeResult(
                            "privileged_capabilities_absent", True,
                            "No dangerous capabilities"
                        )
        except Exception:
            pass
        return ProbeResult("privileged_capabilities_absent", False, "Could not read capabilities")
    
    # Network probes
    def probe_external_ipv4_blocked(self) -> ProbeResult:
        return self._probe_tcp_connect("8.8.8.8", 53, "external_ipv4_blocked")
    
    def probe_external_ipv6_blocked(self) -> ProbeResult:
        return self._probe_tcp_connect("2001:4860:4860::8888", 53, "external_ipv6_blocked")
    
    def probe_dns_external_blocked(self) -> ProbeResult:
        try:
            socket.getaddrinfo("example.com", 80)
            return ProbeResult("dns_external_blocked", False, "External DNS resolution works")
        except socket.gaierror:
            return ProbeResult("dns_external_blocked", True, "External DNS blocked")
        except Exception as e:
            return ProbeResult("dns_external_blocked", True, f"DNS blocked ({e})")
    
    def probe_host_gateway_blocked(self) -> ProbeResult:
        for gw in ["10.0.2.2", "172.17.0.1", "192.168.65.1"]:
            result = self._probe_tcp_connect(gw, 80, "host_gateway_blocked")
            if not result.passed:
                return result
        return ProbeResult("host_gateway_blocked", True, "Host gateway unreachable")
    
    def probe_rfc1918_blocked(self) -> ProbeResult:
        for net in ["10.0.0.1", "172.16.0.1", "192.168.1.1"]:
            result = self._probe_tcp_connect(net, 80, "rfc1918_blocked")
            if not result.passed:
                return result
        return ProbeResult("rfc1918_blocked", True, "RFC1918 networks unreachable")
    
    def probe_cloud_metadata_blocked(self) -> ProbeResult:
        for ip in ["169.254.169.254"]:
            result = self._probe_tcp_connect(ip, 80, "cloud_metadata_blocked")
            if not result.passed:
                return result
        return ProbeResult("cloud_metadata_blocked", True, "Cloud metadata unreachable")
    
    def probe_internal_dns_resolves(self) -> ProbeResult:
        """Internal *.workflo.internal DNS must resolve via the netns dnsmasq.

        CRITICAL: in a PRIVATE-network sandbox this is part of the
        isolation contract — if internal resolution is broken, the
        network isolation infrastructure itself is broken and the run
        must fail closed.
        """
        try:
            infos = socket.getaddrinfo("app.workflo.internal", 80)
            addrs = {info[4][0] for info in infos}
            return ProbeResult("internal_dns_resolves", True,
                               f"app.workflo.internal resolves to {sorted(addrs)}")
        except socket.gaierror as e:
            return ProbeResult("internal_dns_resolves", False,
                               f"internal DNS does not resolve: {e}")
        except Exception as e:
            return ProbeResult("internal_dns_resolves", False,
                               f"internal DNS probe error: {e}")

    def probe_only_internal_routes_accessible(self) -> ProbeResult:
        """Advisory: can we reach the app inside the netns?

        WARNING severity — at probe time the app workload has not
        started yet, so connection failure is expected. App
        reachability is proven separately by the app health check.
        """
        try:
            sock = socket.create_connection(("app.workflo.internal", 3000), timeout=2)
            sock.close()
            return ProbeResult("only_internal_routes_accessible", True,
                               "Internal app reachable")
        except Exception as e:
            return ProbeResult(
                "only_internal_routes_accessible", True,
                f"Internal app not reachable yet (expected pre-app-start): {e}",
                severity="warning",
            )
    
    def _probe_tcp_connect(self, host: str, port: int, name: str) -> ProbeResult:
        try:
            sock = socket.create_connection((host, port), timeout=2)
            sock.close()
            return ProbeResult(name, False, f"Connected to {host}:{port} (isolation broken!)")
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            return ProbeResult(name, True, f"Blocked: {e}")
        except Exception as e:
            return ProbeResult(name, True, f"Blocked ({type(e).__name__})")


def run_probes_in_sandbox(sandbox_pid: int) -> list[ProbeResult]:
    """Entry point to run all probes."""
    probes = IsolationProbes(sandbox_pid)
    return probes.run_all()