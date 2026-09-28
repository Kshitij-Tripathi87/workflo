"""Tests for isolation probes."""

import pytest
import socket
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

from sandbox_runtime.probes import IsolationProbes, ProbeResult


def test_probe_host_home_not_mounted():
    probes = IsolationProbes(1)
    
    with patch("pathlib.Path.exists", return_value=False):
        result = probes.probe_host_home_not_mounted()
        assert result.passed is True
        assert "not visible" in result.detail


def test_probe_docker_socket_unavailable():
    probes = IsolationProbes(1)
    
    with patch("pathlib.Path.exists", return_value=False):
        result = probes.probe_docker_socket_unavailable()
        assert result.passed is True


def test_probe_cloud_credentials_unavailable():
    probes = IsolationProbes(1)
    
    with patch("pathlib.Path.expanduser") as mock_expand, \
         patch("pathlib.Path.exists", return_value=False):
        
        mock_expand.return_value = Path("/home/user/.aws")
        
        result = probes.probe_cloud_credentials_unavailable()
        assert result.passed is True


def test_probe_writes_outside_approved_denied():
    probes = IsolationProbes(1)
    
    def mock_write_text(path, content):
        if "/etc/passwd" in str(path):
            raise PermissionError("Permission denied")
    
    with patch("pathlib.Path.write_text", side_effect=mock_write_text), \
         patch("pathlib.Path.unlink"):
        
        result = probes.probe_writes_outside_approved_denied()
        assert result.passed is True


def test_probe_external_ipv4_blocked():
    probes = IsolationProbes(1)
    
    with patch("socket.create_connection", side_effect=ConnectionRefusedError()):
        result = probes.probe_external_ipv4_blocked()
        assert result.passed is True
        assert "Blocked" in result.detail


def test_probe_dns_external_blocked():
    import socket
    probes = IsolationProbes(1)
    
    with patch("socket.getaddrinfo", side_effect=socket.gaierror()):
        result = probes.probe_dns_external_blocked()
        assert result.passed is True


def test_probe_privileged_capabilities_absent():
    probes = IsolationProbes(1)
    
    # Mock /proc/self/status with no dangerous caps
    mock_status = "CapEff:\t0000000000000000\n"
    
    with patch("builtins.open", mock_open(read_data=mock_status)):
        result = probes.probe_privileged_capabilities_absent()
        assert result.passed is True