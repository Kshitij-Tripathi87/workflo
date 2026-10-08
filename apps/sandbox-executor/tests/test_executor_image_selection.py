"""Unit tests for SandboxExecutor.select_worker_image + the deep-worker auto-switch.

The Phase 1.4 exit gate lives here. The executor is the single source of
truth for WHICH Docker image a run actually used — the CLI mirrors the logic
for the dry-run plan, but the executor's decision is the one that ends up
in `docker create`. So the executor tests are the load-bearing ones for the
auto-switch; the CLI tests just verify the CLI prints the right plan + wires
the right constructor kwargs.

Contract being tested:
    select_worker_image(spec) -> str
      - surface (or surface+security) probe groups -> self.worker_image
      - deep / aggressive probe groups in spec.run_spec.probe_groups
        -> self.deep_worker_image, falling back to DEFAULT_DEEP_WORKER_IMAGE
      - when the spec has NO probe_groups in run_spec at all -> worker_image
        (defensive default; this happens if a future caller forgets to set
        the field)
      - an explicit deep_worker_image override is honored on deep runs
      - an explicit deep_worker_image override is IGNORED on surface runs
        (the surface image selection is what wins)
      - worker_image override (custom surface) is honored on surface runs
      - the selected image is what gets passed to ContainerConfig.image
      - the executor emits a 'worker_image_selected' lifecycle event with
        the selected image name BEFORE creating the container, so the
        receipt is auditable: a reviewer can verify each run used the
        right image tier.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import datetime, UTC
from unittest.mock import patch, MagicMock

import pytest

from workflo_executor import SandboxExecutor
from workflo_executor.docker_runner import ContainerConfig, ContainerResult
from workflo_executor.executor import (
    DEFAULT_DEEP_WORKER_IMAGE,
    DEFAULT_WEB_WORKER_IMAGE,
    DEFAULT_WORKER_IMAGE,
    _DEEP_PROBE_GROUPS,
    _WEB_PROBE_GROUPS,
    _probe_groups_from_spec,
)
from workflo_schema.sandbox import SandboxSpec


def _spec_with_probe_groups(groups):
    """Build a SandboxSpec with the given probe_groups list in run_spec."""
    return SandboxSpec(
        sandbox_id="test-sb",
        repo_url="https://github.com/example/repo.git",
        run_spec={"goal": "functional", "probe_groups": groups, "markers": groups},
        timeout_seconds=60,
    )


# --------------------------------------------------------------------
# select_worker_image: pure selection logic
# --------------------------------------------------------------------

class TestSelectWorkerImage:
    def test_surface_only_uses_worker_image(self):
        """--test: worker_image is the chosen image. deep_worker_image
        must NOT be selected even if it happens to be set on the executor."""
        ex = SandboxExecutor(worker_image="custom-surface:1", deep_worker_image="custom-deep:2")
        assert ex.select_worker_image(_spec_with_probe_groups(["surface"])) == "custom-surface:1"

    def test_surface_plus_security_uses_worker_image(self):
        """--test --security: still the surface image (security doesn't pull
        the model; canary/teardown checks don't need Ollama)."""
        ex = SandboxExecutor()
        assert ex.select_worker_image(_spec_with_probe_groups(["surface", "security"])) == DEFAULT_WORKER_IMAGE

    def test_deep_only_uses_deep_image(self):
        """--deep-test: switches to the deep image."""
        ex = SandboxExecutor()
        assert ex.select_worker_image(_spec_with_probe_groups(["deep"])) == DEFAULT_DEEP_WORKER_IMAGE

    def test_aggressive_only_uses_deep_image(self):
        """--aggressive-test needs the model-bearing image too."""
        ex = SandboxExecutor()
        assert ex.select_worker_image(_spec_with_probe_groups(["aggressive"])) == DEFAULT_DEEP_WORKER_IMAGE

    def test_deep_plus_security_uses_deep_image(self):
        """Composability: --deep-test --security composes, deep wins for image."""
        ex = SandboxExecutor()
        assert ex.select_worker_image(_spec_with_probe_groups(["deep", "security"])) == DEFAULT_DEEP_WORKER_IMAGE

    def test_security_only_uses_surface_image(self):
        """--security without --test: surface image (security doesn't boot Ollama)."""
        ex = SandboxExecutor()
        assert ex.select_worker_image(_spec_with_probe_groups(["security"])) == DEFAULT_WORKER_IMAGE

    def test_explicit_deep_worker_image_is_used_on_deep_run(self):
        """When --deep-test is selected AND deep_worker_image was passed
        (either via --deep-worker-image or constructor), it's chosen over the
        default."""
        ex = SandboxExecutor(deep_worker_image="registry/overridden-deep:v9")
        assert ex.select_worker_image(_spec_with_probe_groups(["deep"])) == "registry/overridden-deep:v9"

    def test_explicit_deep_worker_image_ignored_on_surface_run(self):
        """A deep_worker_image override does NOT bleed into surface runs.
        Surface runs are limited by the surface image contract (no model)."""
        ex = SandboxExecutor(worker_image="surf:v1", deep_worker_image="deep:v9")
        assert ex.select_worker_image(_spec_with_probe_groups(["surface"])) == "surf:v1"

    def test_default_worker_image_when_worker_image_is_none(self):
        """worker_image=None on the executor falls back to DEFAULT_WORKER_IMAGE
        for surface runs — never crash with None passed to docker create."""
        # We construct with None to simulate a caller that explicitly opted
        # out of the instance default — ensure the fallback engages rather
        # than passing None to docker create.
        ex = SandboxExecutor(worker_image=None)
        assert ex.select_worker_image(_spec_with_probe_groups(["surface"])) == DEFAULT_WORKER_IMAGE

    def test_default_deep_image_when_deep_worker_image_is_none(self):
        """deep_worker_image=None on the executor falls back to
        DEFAULT_DEEP_WORKER_IMAGE for deep runs. The deep tier MUST have the
        model-bearing image, so a missing override is NOT a silent degrade
        to the surface image."""
        ex = SandboxExecutor(deep_worker_image=None)
        assert ex.select_worker_image(_spec_with_probe_groups(["deep"])) == DEFAULT_DEEP_WORKER_IMAGE

    def test_deep_probe_groups_constant_immutable(self):
        """The deep probe groups set acts as a frozen configuration knob —
        callers must NOT be able to mutate it at runtime (a stray append
        would silently turn surface runs into deep runs)."""
        assert isinstance(_DEEP_PROBE_GROUPS, frozenset)
        assert "deep" in _DEEP_PROBE_GROUPS
        assert "aggressive" in _DEEP_PROBE_GROUPS
        # Critical contract: surface and security are NOT in here.
        assert "surface" not in _DEEP_PROBE_GROUPS
        assert "security" not in _DEEP_PROBE_GROUPS


class TestProbeGroupsFromSpec:
    """The defensive reader that pulls probe_groups out of a SandboxSpec's
    free-form run_spec dict. The CLI/worker both assume it returns a list;
    the executor's image selection relies on this not raising on missing /
    malformed input."""

    def test_reads_list_from_run_spec(self):
        spec = _spec_with_probe_groups(["deep", "security"])
        assert _probe_groups_from_spec(spec) == ["deep", "security"]

    def test_missing_probe_groups_defaults_to_surface_security(self):
        """A spec with no probe_groups in run_spec gets the same default the
        worker engine applies in execute_run — image selection must agree
        with the worker's interpretation."""
        spec = SandboxSpec(
            sandbox_id="x", repo_url=".", run_spec={"goal": "functional"}
        )
        result = _probe_groups_from_spec(spec)
        assert result == ["surface", "security"]

    def test_non_list_probe_groups_defaults(self):
        """A non-list probe_groups (e.g. a typo'd string) gets the default
        rather than crashing or treating the string as iterable."""
        spec = SandboxSpec(
            sandbox_id="x", repo_url=".", run_spec={"probe_groups": "deep"}
        )
        result = _probe_groups_from_spec(spec)
        assert result == ["surface", "security"]

    def test_non_dict_run_spec_defaults(self):
        """If run_spec itself isn't a dict (graceless caller), default kicks in.

        We bypass Pydantic here (a real SandboxSpec rejects run_spec=None at
        construction time) and exercise the helper's own isinstance check with
        a stub object — that's the defensive layer the helper exists to be.
        """
        from types import SimpleNamespace
        spec = SimpleNamespace(run_spec=None)
        result = _probe_groups_from_spec(spec)
        assert isinstance(result, list)
        assert result == ["surface", "security"]

        # Same defensive path: empty run_spec, somehow.
        spec2 = SimpleNamespace(run_spec={})
        assert _probe_groups_from_spec(spec2) == ["surface", "security"]

    def test_filters_non_string_items(self):
        """A non-string entry in probe_groups is dropped (rather than coercing
        e.g. 42 -> '42' and confusing downstream code that compares to known
        group names)."""
        spec = SandboxSpec(
            sandbox_id="x",
            repo_url=".",
            run_spec={"probe_groups": ["deep", 42, "security", None, "aggressive"]},
        )
        result = _probe_groups_from_spec(spec)
        assert result == ["deep", "security", "aggressive"]


# --------------------------------------------------------------------
# run() actually passes the selected image to docker create
# --------------------------------------------------------------------

class TestRunImageSelectionEndToEnd:
    """Tie the select_worker_image decision to the actual ContainerConfig
    that's passed to the runtime. This is the test that proves
    --deep-test produces a different worker_image at docker create time
    than --test does — the executor-level output of the auto-switch."""

    @pytest.fixture
    def fake_git_success(self):
        """A subprocess.run side_effect that succeeds for git clone AND for
        docker create (returns a fake container ID). Other commands get
        empty success — the test only exercises the image selection path,
        not the full container lifecycle."""
        import subprocess
        def _f(*args, **kwargs):
            cmd = args[0] if args else []
            # docker create: return a fake container ID so create_container succeeds
            if isinstance(cmd, list) and len(cmd) >= 2 and cmd[0] == "docker" and cmd[1] == "create":
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="fake-container-id-1234\n", stderr=""
                )
            # git clone: return success with no output
            if isinstance(cmd, list) and "clone" in cmd:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            # anything else (docker start, docker wait, docker logs, etc.)
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        return _f

    @pytest.fixture
    def deep_spec(self):
        return _spec_with_probe_groups(["deep"])

    @pytest.fixture
    def surface_spec(self):
        return _spec_with_probe_groups(["surface"])

    @contextmanager
    def _patched_run(self, fake_git_success, deep_image_in_constructor=None):
        """A minimal patch around SandboxExecutor.run used by these tests.

        Yields (executor, mock_runtime) — the caller can do
            `with self._patched_run(fake) as (executor, mock_runtime):`
        and inspect `mock_runtime.create.call_args[0][0]` to see the
        `ContainerConfig` (which carries the selected image).

        Patches:
           - subprocess.run (for git clone) -> fake success
           - mount_tmpfs / unmount_tmpfs / verify_ephemeral_gone
             with a real tmpdir as the mount point
           - build_teardown_proof -> a clean TeardownProof
           - ContainerRuntime is a MagicMock whose wait() returns a worker
             stdout that emits a WORKFLO_REPORT and WORKFLO_CANARY line, so
             the executor doesn't roll over into the "canary not checked"
             failure path.
        """
        import tempfile as _tempfile, shutil as _shutil
        from pathlib import Path
        from sandbox_isolation.ephemeral_fs import EphemeralMount
        from sandbox_isolation.network_policy import CanaryResult
        from workflo_schema.sandbox import TeardownProof

        # In-container worker emits both WORKFLO_REPORT and WORKFLO_CANARY
        # so the executor doesn rollover into the "not checked" canary path.
        container_stdout = (
            'WORKFLO_REPORT: {"total":5,"passed":5,"failed":0,"skipped":0}\n'
            f'WORKFLO_CANARY: {{"attempted_at":"{datetime.now(UTC).isoformat()}",'
            f'"target_host":"https://example.com","request_succeeded":false,"error":"blocked"}}'
        )

        real_mount_dir = _tempfile.mkdtemp(prefix="workflo-imagetest-")
        fake_mount = EphemeralMount(
            sandbox_id="image-test", mount_point=Path(real_mount_dir), size_mb=8,
        )

        mock_runtime = MagicMock()
        mock_runtime.create.return_value = "fake-container-id"
        mock_runtime.wait.return_value = ContainerResult(
            container_id="fake-container-id",
            returncode=0,
            stdout=container_stdout,
            stderr="",
            timed_out=False,
        )
        mock_runtime.exists.return_value = False  # container gone after kill

        def _fake_teardown(sandbox_id, container_id, **kwargs):
            return TeardownProof(
                sandbox_id=sandbox_id,
                container_id=container_id,
                filesystem_wipe_method=kwargs.get("filesystem_wipe_method", "tmpfs_umount"),
                container_removed=True,
                filesystem_removed=True,
                no_snapshot_retained=True,
                destroyed_at=datetime.now(UTC),
            )

        # Enter all patches via ExitStack, then yield the executor+runtime.
        # ExitStack handles the __enter__/__exit__ for all nested context managers.
        with ExitStack() as stack:
            stack.enter_context(patch("subprocess.run", side_effect=fake_git_success))
            stack.enter_context(patch("workflo_executor.executor.mount_tmpfs", return_value=fake_mount))
            stack.enter_context(patch("workflo_executor.executor.unmount_tmpfs"))
            stack.enter_context(patch("workflo_executor.executor.verify_ephemeral_gone", return_value=True))
            stack.enter_context(patch("workflo_executor.executor.build_teardown_proof", side_effect=_fake_teardown))

            executor = SandboxExecutor(
                worker_image="workflo-worker:test",
                deep_worker_image=deep_image_in_constructor,
            )
            # Inject the mock runtime so wait() uses our stub instead of
            # the real DockerContainerRuntime (which would poll docker
            # inspect forever on a fake container ID).
            executor.runtime = mock_runtime
            yield executor, mock_runtime

        # ExitStack exits the patches; then clean up the tempdir.
        _shutil.rmtree(real_mount_dir, ignore_errors=True)

    def test_surface_run_passes_surface_image_to_create(
        self, fake_git_success, surface_spec
    ):
        """--test run: ContainerConfig.image == the surface image."""
        with self._patched_run(fake_git_success) as (executor, mock_runtime):
            executor.run(surface_spec)

        mock_runtime.create.assert_called_once()
        config: ContainerConfig = mock_runtime.create.call_args[0][0]
        assert config.image == "workflo-worker:test"

    def test_deep_run_passes_default_deep_image_to_create(
        self, fake_git_success, deep_spec
    ):
        """--deep-test run (no explicit deep_worker_image): ContainerConfig.image
        falls back to DEFAULT_DEEP_WORKER_IMAGE — the model-bearing image."""
        with self._patched_run(fake_git_success) as (executor, mock_runtime):
            executor.run(deep_spec)

        mock_runtime.create.assert_called_once()
        config: ContainerConfig = mock_runtime.create.call_args[0][0]
        assert config.image == DEFAULT_DEEP_WORKER_IMAGE
        # And the surface image is NOT what got used.
        assert config.image != "workflo-worker:test"

    def test_deep_run_honors_explicit_deep_worker_image(
        self, fake_git_success, deep_spec
    ):
        """--deep-test + custom deep_worker_image: ContainerConfig.image is
        the override (not the default)."""
        with self._patched_run(
            fake_git_success, deep_image_in_constructor="custom-deep:v7",
        ) as (executor, mock_runtime):
            executor.run(deep_spec)

        config: ContainerConfig = mock_runtime.create.call_args[0][0]
        assert config.image == "custom-deep:v7"

    def test_worker_image_selected_lifecycle_event_recorded(
        self, fake_git_success, deep_spec
    ):
        """The executor must emit a `worker_image_selected` lifecycle event
        with the chosen image, BEFORE container create. This is the receipt-
        auditable record of the auto-switch — a reviewer checking a deep-test
        run can confirm it actually used the deep image (and didn't silently
        downgrade to surface on a config bug)."""
        with self._patched_run(fake_git_success) as (executor, mock_runtime):
            result = executor.run(deep_spec)

        events = result.receipt.lifecycle_events
        names = [e.event for e in events]
        assert "worker_image_selected" in names

        evt = next(e for e in events if e.event == "worker_image_selected")
        assert evt.detail["worker_image"] == DEFAULT_DEEP_WORKER_IMAGE

        # The event must come BEFORE container_created — order matters: the
        # image choice drove the container creation, not vice-versa. If the
        # event arrives after create, the audit trail loses its "the image
        # was selected because of THIS spec" meaning.
        idx_select = names.index("worker_image_selected")
        idx_create = names.index("container_created")
        assert idx_select < idx_create, (
            f"worker_image_selected (idx={idx_select}) must precede "
            f"container_created (idx={idx_create}); got order {names}"
        )

    def test_surface_run_lifecycle_event_names_the_surface_image(
        self, fake_git_success, surface_spec
    ):
        """The same lifecycle event for a --test run names the SURFACE image —
        so the difference between --test and --deep-test is observable in the
        receipt, not just in the docker create call."""
        with self._patched_run(fake_git_success) as (executor, mock_runtime):
            result = executor.run(surface_spec)

        events = result.receipt.lifecycle_events
        evt = next(e for e in events if e.event == "worker_image_selected")
        assert evt.detail["worker_image"] == "workflo-worker:test"


# --------------------------------------------------------------------
# select_worker_image: web-tier selection (Phase 3, Track A.2)
# --------------------------------------------------------------------

class TestSelectWebWorkerImage:
    def test_web_only_uses_web_image(self):
        """--web: switches to the Playwright-bearing image."""
        ex = SandboxExecutor()
        assert ex.select_worker_image(_spec_with_probe_groups(["web"])) == DEFAULT_WEB_WORKER_IMAGE

    def test_web_plus_security_uses_web_image(self):
        """--web --security: composes; web wins for image."""
        ex = SandboxExecutor()
        assert ex.select_worker_image(_spec_with_probe_groups(["web", "security"])) == DEFAULT_WEB_WORKER_IMAGE

    def test_explicit_web_worker_image_is_used_on_web_run(self):
        """--web + custom web_worker_image: the override wins."""
        ex = SandboxExecutor(web_worker_image="registry/overridden-web:v9")
        assert ex.select_worker_image(_spec_with_probe_groups(["web"])) == "registry/overridden-web:v9"

    def test_explicit_web_worker_image_ignored_on_surface_run(self):
        """A web_worker_image override does NOT bleed into surface runs."""
        ex = SandboxExecutor(worker_image="surf:v1", web_worker_image="web:v9")
        assert ex.select_worker_image(_spec_with_probe_groups(["surface"])) == "surf:v1"

    def test_explicit_web_worker_image_ignored_on_deep_run(self):
        """A web_worker_image override does NOT bleed into deep runs."""
        ex = SandboxExecutor(deep_worker_image="deep:v9", web_worker_image="web:v9")
        assert ex.select_worker_image(_spec_with_probe_groups(["deep"])) == "deep:v9"

    def test_default_web_image_when_web_worker_image_is_none(self):
        """web_worker_image=None on the executor falls back to
        DEFAULT_WEB_WORKER_IMAGE for web runs."""
        ex = SandboxExecutor(web_worker_image=None)
        assert ex.select_worker_image(_spec_with_probe_groups(["web"])) == DEFAULT_WEB_WORKER_IMAGE

    def test_deep_plus_web_raises_value_error(self):
        """deep + web together is NOT silently degraded to either image.
        The combined image (workflo-worker-deep-web:latest) has not been
        built, so this must raise a loud, actionable error — the failing
        mode is a receipt that looks like a valid deep+web run but only
        ran one tier."""
        ex = SandboxExecutor()
        with pytest.raises(ValueError, match="deep.*web|has not been built"):
            ex.select_worker_image(_spec_with_probe_groups(["deep", "web"]))

    def test_aggressive_plus_web_raises_value_error(self):
        """aggressive + web is the same unsupported combination."""
        ex = SandboxExecutor()
        with pytest.raises(ValueError, match="has not been built"):
            ex.select_worker_image(_spec_with_probe_groups(["aggressive", "web"]))

    def test_web_probe_groups_constant_immutable(self):
        """The web probe groups set is a frozen configuration knob."""
        assert isinstance(_WEB_PROBE_GROUPS, frozenset)
        assert "web" in _WEB_PROBE_GROUPS
        # Critical contract: surface/security/deep are NOT in here.
        assert "surface" not in _WEB_PROBE_GROUPS
        assert "security" not in _WEB_PROBE_GROUPS
        assert "deep" not in _WEB_PROBE_GROUPS


# --------------------------------------------------------------------
# run() passes the selected WEB image to docker create
# --------------------------------------------------------------------

class TestRunWebImageSelectionEndToEnd:
    @pytest.fixture
    def fake_git_success(self):
        import subprocess
        def _f(*args, **kwargs):
            cmd = args[0] if args else []
            if isinstance(cmd, list) and len(cmd) >= 2 and cmd[0] == "docker" and cmd[1] == "create":
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="fake-container-id-1234\n", stderr=""
                )
            if isinstance(cmd, list) and "clone" in cmd:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        return _f

    @contextmanager
    def _patched_run(self, fake_git_success, web_image_in_constructor=None):
        import tempfile as _tempfile, shutil as _shutil
        from pathlib import Path
        from sandbox_isolation.ephemeral_fs import EphemeralMount
        from workflo_schema.sandbox import TeardownProof

        container_stdout = (
            'WORKFLO_REPORT: {"total":5,"passed":5,"failed":0,"skipped":0}\n'
            f'WORKFLO_CANARY: {{"attempted_at":"{datetime.now(UTC).isoformat()}",'
            f'"target_host":"https://example.com","request_succeeded":false,"error":"blocked"}}'
        )

        real_mount_dir = _tempfile.mkdtemp(prefix="workflo-webtest-")
        fake_mount = EphemeralMount(
            sandbox_id="web-test", mount_point=Path(real_mount_dir), size_mb=8,
        )

        mock_runtime = MagicMock()
        mock_runtime.create.return_value = "fake-container-id"
        mock_runtime.wait.return_value = ContainerResult(
            container_id="fake-container-id",
            returncode=0,
            stdout=container_stdout,
            stderr="",
            timed_out=False,
        )
        mock_runtime.exists.return_value = False

        def _fake_teardown(sandbox_id, container_id, **kwargs):
            return TeardownProof(
                sandbox_id=sandbox_id,
                container_id=container_id,
                filesystem_wipe_method=kwargs.get("filesystem_wipe_method", "tmpfs_umount"),
                container_removed=True,
                filesystem_removed=True,
                no_snapshot_retained=True,
                destroyed_at=datetime.now(UTC),
            )

        with ExitStack() as stack:
            stack.enter_context(patch("subprocess.run", side_effect=fake_git_success))
            stack.enter_context(patch("workflo_executor.executor.mount_tmpfs", return_value=fake_mount))
            stack.enter_context(patch("workflo_executor.executor.unmount_tmpfs"))
            stack.enter_context(patch("workflo_executor.executor.verify_ephemeral_gone", return_value=True))
            stack.enter_context(patch("workflo_executor.executor.build_teardown_proof", side_effect=_fake_teardown))

            executor = SandboxExecutor(
                worker_image="workflo-worker:test",
                web_worker_image=web_image_in_constructor,
            )
            executor.runtime = mock_runtime
            yield executor, mock_runtime

        _shutil.rmtree(real_mount_dir, ignore_errors=True)

    def test_web_run_passes_web_image_to_create(self, fake_git_success):
        """--web run: ContainerConfig.image == the web image (default)."""
        with self._patched_run(fake_git_success) as (executor, mock_runtime):
            executor.run(_spec_with_probe_groups(["web"]))

        config: ContainerConfig = mock_runtime.create.call_args[0][0]
        assert config.image == DEFAULT_WEB_WORKER_IMAGE
        assert config.image != "workflo-worker:test"

    def test_web_run_honors_explicit_web_worker_image(self, fake_git_success):
        """--web + custom web_worker_image: the override is passed to create."""
        with self._patched_run(
            fake_git_success, web_image_in_constructor="custom-web:v7",
        ) as (executor, mock_runtime):
            executor.run(_spec_with_probe_groups(["web"]))

        config: ContainerConfig = mock_runtime.create.call_args[0][0]
        assert config.image == "custom-web:v7"

    def test_web_run_lifecycle_event_names_the_web_image(self, fake_git_success):
        """The worker_image_selected lifecycle event names the WEB image."""
        with self._patched_run(fake_git_success) as (executor, mock_runtime):
            result = executor.run(_spec_with_probe_groups(["web"]))

        events = result.receipt.lifecycle_events
        evt = next(e for e in events if e.event == "worker_image_selected")
        assert evt.detail["worker_image"] == DEFAULT_WEB_WORKER_IMAGE

        idx_select = [e.event for e in events].index("worker_image_selected")
        idx_create = [e.event for e in events].index("container_created")
        assert idx_select < idx_create
