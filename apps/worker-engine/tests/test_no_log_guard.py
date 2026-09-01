"""Unit tests for workflo_worker.model.no_log_guard (the teardown wipe).

The teardown-side guard's contract is what makes the receipt's
`model_inference_teardown: true` field trustworthy: the wipe MUST have
happened, and the receipt MUST record "false" (fail closed) when it
didn't. These tests back that contract without ever touching a real
`~/.ollama` directory — we route the wipe at `extra_dirs` pointing into
`tmp_path`, which the source appends verbatim without expanduser.

Contract being tested:
    - wipe_model_state() returns True when all targets are already gone
    - wipe_model_state() returns True when all targets are removed on first try
    - wipe_model_state() returns True when targets don't exist at all
    - wipe_model_state() retries PermissionError up to max_retries then fails closed (False)
    - wipe_model_state() retries PermissionError and SUCCEEDS once the handle releases
    - wipe_model_state() lets non-PermissionError OSError propagate (never swallow)
    - confirm_no_ollama_state() returns True when nothing exists
    - confirm_no_ollama_state() returns False when at least one target exists
    - resolve_state_dirs() returns the 3 default ollama state dirs under $HOME
    - resolve_state_dirs() with extra_dirs extends the list (paths preserved verbatim)

The DEFAULT_STATE_DIRS list lives in the module and is what the Dockerfile.deep
comments reference — the test asserts the names so a future rename can't silently
break the script's drift-detection.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from workflo_worker.model.no_log_guard import (
    DEFAULT_STATE_DIRS,
    confirm_no_ollama_state,
    resolve_state_dirs,
    wipe_model_state,
)


# --------------------------------------------------------------------
# resolve_state_dirs
# --------------------------------------------------------------------

class TestResolveStateDirs:
    def test_defaults_under_home(self, tmp_path, monkeypatch):
        """Without extra_dirs, resolve_state_dirs returns the 3 default
        Ollama state directories under $HOME — that's the contract the
        Dockerfile.deep teardown script depends on."""
        monkeypatch.setenv("HOME", str(tmp_path))
        # On Windows, expanduser('~') ignores HOME and returns the user
        # profile. Patch expanduser so the test runs cross-platform:
        monkeypatch.setattr("os.path.expanduser", lambda _p: str(tmp_path))

        paths = resolve_state_dirs()

        assert len(paths) == 3
        base = tmp_path / ".ollama"
        # The defaults must match what the Dockerfile.deep wipes — a
        # silent rename here would break the deep-image's teardown.
        assert set(DEFAULT_STATE_DIRS) == {
            ".ollama/logs",
            ".ollama/history",
            ".ollama/.tmp",
        }
        assert paths == [
            base / "logs",
            base / "history",
            base / ".tmp",
        ]

    def test_extra_dirs_appended_verbatim(self, tmp_path, monkeypatch):
        """extra_dirs must be appended as absolute paths, unmodified —
        we don't expanduser them (the executor passes already-absolute
        tmpfs paths in real runs)."""
        monkeypatch.setattr("os.path.expanduser", lambda _p: str(tmp_path / "fakehome"))

        extra1 = tmp_path / "custom_state" / "thing"
        extra2 = Path("/tmp/some/absolute/path")  # an absolute path stays as-is
        paths = resolve_state_dirs(extra_dirs=[str(extra1), str(extra2)])

        # 3 defaults + 2 extras
        assert len(paths) == 5
        assert paths[3] == extra1
        assert paths[4] == extra2

    def test_no_extra_dirs_no_extras_appended(self):
        paths = resolve_state_dirs()
        assert len(paths) == 3


# --------------------------------------------------------------------
# wipe_model_state — the actual wipe
# --------------------------------------------------------------------

class TestWipeModelState:
    def test_returns_true_when_all_targets_already_absent(self, tmp_path):
        """No state exists at all → nothing to do → True (still 'clean')."""
        extra = tmp_path / "never_created"
        assert wipe_model_state(extra_dirs=[str(extra)]) is True

    def test_returns_true_when_all_targets_removed_first_try(self, tmp_path):
        """Real directories on disk get removed by rmtree, on the first try."""
        d1 = tmp_path / "ollama_logs"
        d2 = tmp_path / "ollama_history"
        d1.mkdir()
        d2.mkdir()
        (d1 / "request.log").write_text("should be wiped")
        (d2 / "history.txt").write_text("secrets")

        assert wipe_model_state(extra_dirs=[str(d1), str(d2)]) is True
        assert not d1.exists()
        assert not d2.exists()

    def test_returns_true_when_some_targets_exist_some_dont(self, tmp_path):
        """A mix of existing and pre-absent directories must still come back True
        as long as everything that existed is gone afterward."""
        exists = tmp_path / "exists" / "sub"
        missing = tmp_path / "missing"
        exists.mkdir(parents=True)
        (exists / "x.log").write_text("wipe me")

        assert wipe_model_state(extra_dirs=[str(exists), str(missing)]) is True
        assert not exists.exists()
        assert not missing.exists()

    def test_retries_permissionerror_then_succeeds(self, tmp_path):
        """PermissionError is retried up to max_retries. Once rmtree succeeds
        (handle released by the OS after N attempts), wipe returns True.

        This is the Windows + Docker Desktop + Ollama lag scenario the
        source's docstring describes — the test exercises the retry loop
        without needing Windows.
        """
        target = tmp_path / "stubborn"
        target.mkdir()
        (target / "x").write_text("locked")

        # rmtree fails twice with PermissionError, then succeeds. This
        # exercise is the equivalent of: OS still has a file handle open
        # for a moment after the container exits; on the third rmtree
        # call the handle has been released and we delete cleanly.
        call_count = [0]
        original_rmtree = shutil.rmtree

        def flaky_rmtree(path, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise PermissionError(13, "Access is denied", str(path))
            return original_rmtree(path, *args, **kwargs)

        with patch("workflo_worker.model.no_log_guard.shutil.rmtree",
                   side_effect=flaky_rmtree), \
             patch("workflo_worker.model.no_log_guard.time.sleep") as _sleep:
            result = wipe_model_state(
                extra_dirs=[str(target)],
                max_retries=5,
                retry_sleep_seconds=0.01,
            )

        assert result is True
        assert not target.exists()
        # Our flaky rmtree was called 3 times for this single path.
        assert call_count[0] == 3

    def test_retries_exhausted_returns_false_fail_closed(self, tmp_path):
        """If PermissionError persists past max_retries, the directory is
        still on disk — wipe_model_state MUST return False (fail closed)
        so the receipt records teardown=failure rather than lying."""
        target = tmp_path / "stuck"
        target.mkdir()
        (target / "x").write_text("locked")

        # rmtree always raises PermissionError — never succeeds.
        with patch("workflo_worker.model.no_log_guard.shutil.rmtree",
                   side_effect=PermissionError(13, "denied", str(target))), \
             patch("workflo_worker.model.no_log_guard.time.sleep"):
            result = wipe_model_state(
                extra_dirs=[str(target)],
                max_retries=3,
                retry_sleep_seconds=0.001,
            )

        assert result is False
        # The directory is still on disk — that's the leak the receipt
        # needs to be honest about. Don't delete it here; assert it remains.
        assert target.exists()

        # Clean up so tmp_path teardown doesn't fail on Windows due to
        # the simulated lock leaving files behind. We patch rmtree back to
        # the real one for pytest's tmp_path cleanup.
        shutil.rmtree(target, ignore_errors=True)

    def test_filenotfounderror_during_rmtree_is_swallowed(self, tmp_path):
        """rmtree raising FileNotFoundError (race: another process beat us)
        is the success case — not an error. wipe must return True."""
        target = tmp_path / "race"
        target.mkdir()

        call_count = [0]
        # First rmtree raises FileNotFoundError (as if the dir vanished
        # between our `path.exists()` check and the rmtree call). After
        # that, the dir is gone — confirm True.
        def racing_rmtree(path, *args, **kwargs):
            call_count[0] += 1
            raise FileNotFoundError("already gone")

        with patch("workflo_worker.model.no_log_guard.shutil.rmtree",
                   side_effect=racing_rmtree):
            result = wipe_model_state(extra_dirs=[str(target)])

        assert result is True
        # The source's `except FileNotFoundError: continue` skips the
        # append to `still_here`, so the path is treated as already gone
        # even though rmtree technically raised.

    def test_other_oserror_propagates_unswallowed(self, tmp_path):
        """An OSError that's NOT PermissionError or FileNotFoundError must
        bubble up — the source's "don't swallow errors" stance from the
        plan. The receipt can't claim teardown=false if we never know
        the wipe errored."""
        target = tmp_path / "bad"
        target.mkdir()

        with patch("workflo_worker.model.no_log_guard.shutil.rmtree",
                   side_effect=OSError("cross-device link")):
            with pytest.raises(OSError, match="cross-device link"):
                wipe_model_state(extra_dirs=[str(target)])

        # Cleanup for tmp_path sake.
        shutil.rmtree(target, ignore_errors=True)

    def test_returns_true_with_no_extra_dirs_when_defaults_dont_exist(
        self, tmp_path, monkeypatch
    ):
        """A real default invocation (no extra_dirs) when ~/.ollama doesn't
        exist must report True — there's nothing to wipe, and that's clean."""
        monkeypatch.setattr("os.path.expanduser", lambda _p: str(tmp_path))

        result = wipe_model_state()
        assert result is True


# --------------------------------------------------------------------
# confirm_no_ollama_state — pure existence check
# --------------------------------------------------------------------

class TestConfirmNoOllamaState:
    def test_returns_true_when_nothing_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr("os.path.expanduser", lambda _p: str(tmp_path))
        assert confirm_no_ollama_state() is True

    def test_returns_false_when_default_dir_exists(self, tmp_path, monkeypatch):
        """If even one of the default state directories exists, the check
        must report False — there's leftover state on disk."""
        monkeypatch.setattr("os.path.expanduser", lambda _p: str(tmp_path))
        (tmp_path / ".ollama" / "logs").mkdir(parents=True)

        assert confirm_no_ollama_state() is False

    def test_returns_false_when_only_extra_dir_exists(self, tmp_path, monkeypatch):
        """If an extra_dir exists (e.g. an OLLAMA_MODELS override), the
        check sees it and reports False — completes the receipt's audit."""
        monkeypatch.setattr("os.path.expanduser", lambda _p: str(tmp_path / "other_home"))
        leftover = tmp_path / "extra_state"
        leftover.mkdir()

        assert confirm_no_ollama_state(extra_dirs=[str(leftover)]) is False

    def test_returns_true_when_extra_dir_then_removed(self, tmp_path, monkeypatch):
        """Smoke test the round-trip: state exists → confirm False → wipe → confirm True."""
        monkeypatch.setattr("os.path.expanduser", lambda _p: str(tmp_path / "home"))
        leftover = tmp_path / "extra"
        leftover.mkdir()
        (leftover / "a.log").write_text("wiped")

        assert confirm_no_ollama_state(extra_dirs=[str(leftover)]) is False
        assert wipe_model_state(extra_dirs=[str(leftover)]) is True
        assert confirm_no_ollama_state(extra_dirs=[str(leftover)]) is True
