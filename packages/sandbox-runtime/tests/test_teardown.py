"""Tests for fail-closed teardown verification."""

from unittest.mock import MagicMock, patch

from sandbox_runtime.teardown import (
    TeardownVerification,
    verify_processes_terminated,
    verify_cgroup_removed,
    verify_paths_removed,
    verify_network_namespace_removed,
    teardown_and_verify,
    teardown_proof_fields,
)
from sandbox_runtime.config import NetworkConfig


def _fake_proc(returncode=0):
    """A fake Popen that reports itself exited."""
    proc = MagicMock()
    proc.poll.return_value = returncode
    proc.returncode = returncode
    return proc


def _running_proc():
    """A fake Popen that reports itself still running."""
    proc = MagicMock()
    proc.poll.return_value = None
    proc.returncode = None
    return proc


class TestVerifyProcessesTerminated:
    def test_all_exited_passes(self):
        procs = {"test": _fake_proc(0), "probe": _fake_proc(1)}
        assert verify_processes_terminated(procs) is True

    def test_still_running_fails(self):
        procs = {"test": _fake_proc(0), "app": _running_proc()}
        assert verify_processes_terminated(procs) is False

    def test_none_entries_ignored(self):
        assert verify_processes_terminated({"app": None}) is True

    def test_empty_registry_passes(self):
        assert verify_processes_terminated({}) is True


class TestVerifyCgroupRemoved:
    def test_missing_path_passes(self, tmp_path):
        assert verify_cgroup_removed(tmp_path / "gone") is True

    def test_existing_path_fails(self, tmp_path):
        cgroup = tmp_path / "workflo" / "sandbox-1"
        cgroup.mkdir(parents=True)
        assert verify_cgroup_removed(cgroup) is False

    def test_none_fails_closed(self):
        # No cgroup was created -> nothing to prove -> fail closed
        assert verify_cgroup_removed(None) is False


class TestVerifyPathsRemoved:
    def test_all_missing_passes(self, tmp_path):
        assert verify_paths_removed([tmp_path / "a", tmp_path / "b"]) is True

    def test_existing_path_fails(self, tmp_path):
        (tmp_path / "a").mkdir()
        assert verify_paths_removed([tmp_path / "a"]) is False


class TestVerifyNetworkNamespaceRemoved:
    def _patch_netns_list(self, output: str, returncode: int = 0):
        result = MagicMock()
        result.returncode = returncode
        result.stdout = output
        return patch("sandbox_runtime.teardown.subprocess.run", return_value=result)

    def test_absent_netns_passes(self):
        config = NetworkConfig(sandbox_id="sbx-123")
        with self._patch_netns_list("other-ns\n"):
            assert verify_network_namespace_removed(config) is True

    def test_present_netns_fails(self):
        config = NetworkConfig(sandbox_id="sbx-123")
        with self._patch_netns_list("workflo-sbx-123 (id: 2)\nother\n"):
            assert verify_network_namespace_removed(config) is False

    def test_ip_command_failure_fails_closed(self):
        config = NetworkConfig(sandbox_id="sbx-123")
        with self._patch_netns_list("", returncode=1):
            assert verify_network_namespace_removed(config) is False

    def test_none_config_fails_closed(self):
        assert verify_network_namespace_removed(None) is False


class TestTeardownAndVerify:
    def test_clean_teardown_verifies_all(self, tmp_path):
        cgroup = tmp_path / "cgroup" / "workflo" / "sbx"
        cgroup.mkdir(parents=True)
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        config = NetworkConfig(sandbox_id="sbx")

        with patch("sandbox_runtime.teardown.verify_network_namespace_removed", return_value=True), \
             patch("sandbox_runtime.teardown._kill_cgroup_processes"):
            verification = teardown_and_verify(
                processes={"test": _fake_proc(0)},
                cgroup_path=cgroup,
                network_config=config,
                writable_paths=[workspace],
            )

        assert verification.processes_terminated is True
        # cgroup_removed is True because the real rmdir ran and the
        # post-check re-observed the path is gone
        assert verification.cgroup_removed is True
        assert verification.workspace_removed is True
        assert verification.all_verified is True

    def test_surviving_process_fails(self, tmp_path):
        proc = _running_proc()
        proc.wait.side_effect = Exception("still running")
        proc.kill.side_effect = Exception("cannot kill")

        with patch("sandbox_runtime.teardown.verify_network_namespace_removed", return_value=True):
            verification = teardown_and_verify(
                processes={"app": proc},
                cgroup_path=None,
                network_config=NetworkConfig(sandbox_id="sbx"),
                writable_paths=[],
            )

        assert verification.processes_terminated is False
        assert verification.all_verified is False


class TestCgroupDrain:
    """F-9: the cgroup — not the tracked PID list — is the containment unit."""

    def _make_cgroup(self, tmp_path, pids):
        cgroup = tmp_path / "cgroup" / "sbx"
        cgroup.mkdir(parents=True, exist_ok=True)
        (cgroup / "cgroup.procs").write_text("".join(f"{p}\n" for p in pids))
        (cgroup / "cgroup.threads").write_text("")
        return cgroup

    def test_drains_untracked_descendants(self, tmp_path):
        from sandbox_runtime.teardown import _kill_cgroup_processes

        cgroup = self._make_cgroup(tmp_path, [111, 222])

        killed = []

        def fake_kill(cmd, **kwargs):
            killed.append(cmd[-1])
            # The processes die: remove them from cgroup.procs
            (cgroup / "cgroup.procs").write_text("")
            result = MagicMock()
            result.returncode = 0
            return result

        with patch("sandbox_runtime.teardown.subprocess.run", side_effect=fake_kill):
            result = _kill_cgroup_processes(cgroup, deadline_seconds=2.0)

        assert result["drained"] is True
        assert sorted(killed) == ["111", "222"]
        assert result["killed"] == 2
        assert result["remaining"] == []

    def test_stragglers_reported_not_hidden(self, tmp_path):
        """Processes that survive SIGKILL surface in the result — and the
        cgroup cannot be removed, so verification fails the receipt."""
        from sandbox_runtime.teardown import _kill_cgroup_processes

        cgroup = self._make_cgroup(tmp_path, [666])
        # kill runs but the PID never leaves cgroup.procs (D-state)

        with patch("sandbox_runtime.teardown.subprocess.run") as fake_run:
            fake_run.return_value = MagicMock(returncode=0)
            result = _kill_cgroup_processes(cgroup, deadline_seconds=0.3)

        assert result["drained"] is False
        assert result["remaining"] == ["666"]
        assert result["killed"] >= 1

    def test_empty_cgroup_drains_immediately(self, tmp_path):
        from sandbox_runtime.teardown import _kill_cgroup_processes

        cgroup = self._make_cgroup(tmp_path, [])
        result = _kill_cgroup_processes(cgroup)
        assert result == {"drained": True, "killed": 0, "remaining": []}

    def test_threads_are_collected_too(self, tmp_path):
        from sandbox_runtime.teardown import _cgroup_members

        cgroup = self._make_cgroup(tmp_path, [10])
        (cgroup / "cgroup.threads").write_text("10\n11\n12\n")
        assert _cgroup_members(cgroup) == ["10", "11", "12"]

    def test_drain_result_lands_in_verification_details(self, tmp_path):
        cgroup = tmp_path / "cgroup" / "sbx"
        cgroup.mkdir(parents=True)
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with patch("sandbox_runtime.teardown.verify_network_namespace_removed", return_value=True), \
             patch("sandbox_runtime.teardown._kill_cgroup_processes",
                   return_value={"drained": False, "killed": 3, "remaining": ["9"]}):
            verification = teardown_and_verify(
                processes={},
                cgroup_path=cgroup,
                network_config=NetworkConfig(sandbox_id="sbx"),
                writable_paths=[workspace],
            )

        assert verification.details["cgroup_drain"]["drained"] is False
        assert verification.details["cgroup_drain"]["remaining"] == ["9"]


class TestTeardownProofFields:
    def test_all_verified_maps_to_true_claims(self):
        verification = TeardownVerification(
            processes_terminated=True,
            cgroup_removed=True,
            network_namespace_removed=True,
            workspace_removed=True,
        )
        fields = teardown_proof_fields("sbx", verification, 12.5, 9)

        assert fields["runtime_type"] == "namespaces"
        assert fields["container_removed"] is True  # composite claim
        assert fields["filesystem_removed"] is True
        assert fields["processes_terminated"] is True
        assert fields["cgroup_removed"] is True
        assert fields["network_namespace_removed"] is True
        assert fields["workspace_removed"] is True
        assert fields["session_duration_seconds"] == 12.5
        assert fields["events_count"] == 9

    def test_partial_verification_fails_composite_claim(self):
        verification = TeardownVerification(
            processes_terminated=True,
            cgroup_removed=False,  # cgroup survived
            network_namespace_removed=True,
            workspace_removed=True,
        )
        fields = teardown_proof_fields("sbx", verification, 1.0, 3)

        assert fields["container_removed"] is False
        assert fields["cgroup_removed"] is False
        assert fields["workspace_removed"] is True
