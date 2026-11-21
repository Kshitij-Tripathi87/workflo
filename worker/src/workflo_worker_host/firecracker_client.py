"""Real Firecracker client: pinned jailer subprocess lifecycle (Linux/KVM).

Implements the ``FirecrackerClient`` seam against the actual jailer binary:

- materializes the VM config JSON (canonical bytes) and stages kernel,
  rootfs, scratch, and config **inside the jailer's chroot layout**
  (``<chroot_base>/<exec_file_name>/<id>/root``) — after ``pivot_root``
  Firecracker resolves every path relative to that root, so the host-side
  view of a path is ``chroot + path`` (docs/jailer.md, v1.18.0);
- builds the jailer argv (``--chroot-base-dir`` — the flag the jailer
  actually accepts) and spawns it with ``start_new_session`` so the whole
  VMM process group can be signalled;
- captures stdout+stderr (guest serial console + VMM logs) to a per-run
  serial log — host evidence;
- stops with SIGTERM → grace → SIGKILL, records how termination happened;
- removes the jail directory (staged hardlinks + sockets) after the
  process is dead; a live process is never yanked from under.

Jailer and root are required for a REAL boot; the lifecycle machinery is
tested here against a stand-in jailer/firecracker pair (no KVM needed) —
the KVM-gated e2e covers the real binaries.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from workflo_schema.contracts.canonical import canonical_bytes, digest_of, sha256_hex
from workflo_schema.contracts.common import utc_now_ms

from workflo_worker_host.admission import PinnedRuntime
from workflo_worker_host.manager import build_jailer_argv

__all__ = ["CONFIG_PATH_IN_CHROOT", "JailerFirecrackerClient", "VmmError"]

# Where the config JSON lives INSIDE the jail (host view:
# <chroot_dir><CONFIG_PATH_IN_CHROOT>). Absolute, because Firecracker
# resolves it from the jail root after pivot_root.
CONFIG_PATH_IN_CHROOT = "/run/workflo/config.json"


class VmmError(RuntimeError):
    """The VMM process could not be started, staged, or stopped."""


@dataclass
class _VmmRecord:
    sandbox_id: str
    pid: int
    proc: subprocess.Popen
    argv: list
    config_path: str
    config_digest: str
    jail_dir: str
    serial_path: str
    serial_file: object
    started_at: str
    stopped_at: str | None = None
    exit_code: int | None = None
    termination: str | None = None  # "sigterm" | "sigkill" | "already_exited"
    cleanup_error: str | None = None
    staged: list = field(default_factory=list)


class JailerFirecrackerClient:
    """Firecracker-under-jailer process lifecycle. No fallback backends."""

    def __init__(
        self,
        *,
        pinned: PinnedRuntime,
        chroot_base: str = "/srv/jailer",
        work_dir: str = "/run/workflo/vmm",
        uid: int = 0,
        gid: int = 0,
        stop_grace_seconds: float = 5.0,
        popen=None,
    ):
        if not os.path.isabs(chroot_base):
            raise VmmError(f"chroot_base must be an absolute path: {chroot_base}")
        if not os.path.isabs(work_dir):
            raise VmmError(f"work_dir must be an absolute path: {work_dir}")
        self._pinned = pinned
        self._chroot_base = chroot_base.rstrip("/")
        self._work_dir = work_dir.rstrip("/")
        self._uid = uid
        self._gid = gid
        self._grace = stop_grace_seconds
        self._popen = popen or subprocess.Popen
        self._records: dict[str, _VmmRecord] = {}

    # -- Paths ------------------------------------------------------------

    def sandbox_chroot(self, sandbox_id: str) -> str:
        """The jailer's chroot dir for this sandbox (docs/jailer.md layout)."""
        exec_name = Path(self._pinned.firecracker_path).name
        return f"{self._chroot_base}/{exec_name}/{sandbox_id}/root"

    def host_view_path(self, sandbox_id: str, in_chroot_path: str) -> str:
        """Map an in-jail absolute path to the host filesystem view."""
        if not in_chroot_path.startswith("/"):
            raise VmmError(f"in-jail path must be absolute: {in_chroot_path}")
        return f"{self.sandbox_chroot(sandbox_id)}{in_chroot_path}"

    def serial_log_path(self, sandbox_id: str) -> str:
        return f"{self._work_dir}/{sandbox_id}/serial.log"

    # -- FirecrackerClient seam -------------------------------------------

    def start(self, sandbox_id: str, vm_config: dict, argv: list) -> None:
        existing = self._records.get(sandbox_id)
        if existing is not None and existing.proc.poll() is None:
            raise VmmError(f"VMM already running for sandbox {sandbox_id}")

        firecracker = Path(self._pinned.firecracker_path)
        jailer = Path(self._pinned.jailer_path)
        if not jailer.is_file():
            raise VmmError(f"jailer binary not found: {jailer}")
        if not firecracker.is_file():
            raise VmmError(f"firecracker binary not found: {firecracker}")

        chroot_dir = self.sandbox_chroot(sandbox_id)
        work_dir = Path(f"{self._work_dir}/{sandbox_id}")
        work_dir.mkdir(parents=True, exist_ok=True)
        staged: list[str] = []
        try:
            # Stage every path Firecracker will open, at its in-jail
            # absolute location. Hardlinks only: a cross-device staging
            # target would silently fork the image's identity, so EXDEV
            # is a hard error with an actionable message.
            for src in self._config_paths(vm_config):
                dst = self.host_view_path(sandbox_id, src)
                Path(dst).parent.mkdir(parents=True, exist_ok=True)
                if not os.path.islink(dst) and os.path.exists(dst):
                    # Prior run with the same (unique) sandbox id: replace.
                    os.unlink(dst)
                try:
                    os.link(src, dst)
                except OSError as exc:
                    raise VmmError(
                        f"cannot stage {src} into the jail at {dst}: "
                        f"{type(exc).__name__}: {exc} — chroot_base and the "
                        "kernel/rootfs/scratch images must share a filesystem "
                        "(hardlink staging; no silent copies)"
                    ) from exc
                staged.append(dst)
            config_dst = self.host_view_path(sandbox_id, CONFIG_PATH_IN_CHROOT)
            Path(config_dst).parent.mkdir(parents=True, exist_ok=True)
            config_bytes = canonical_bytes(vm_config)
            Path(config_dst).write_bytes(config_bytes)
            staged.append(config_dst)
            # The vsock parent dir must exist for Firecracker to bind its
            # host-initiated listener (and our guest-initiated listener
            # lives beside it, bound by the channel before start).
            vsock_path = (vm_config.get("vsock") or {}).get("uds_path")
            if vsock_path:
                Path(self.host_view_path(sandbox_id, vsock_path)).parent.mkdir(
                    parents=True, exist_ok=True
                )
        except VmmError:
            self._cleanup_staging(staged, sandbox_id)
            # Staging created the per-id jail tree before failing; a failed
            # start must not leave directory residue behind.
            shutil.rmtree(str(Path(chroot_dir).parent), ignore_errors=True)
            raise

        serial_path = self.serial_log_path(sandbox_id)
        serial_file = open(serial_path, "wb")  # noqa: SIM115 — closed in stop()
        jailer_argv = build_jailer_argv(
            self._pinned,
            sandbox_id=sandbox_id,
            config_path=CONFIG_PATH_IN_CHROOT,
            uid=self._uid,
            gid=self._gid,
            chroot_base=self._chroot_base,
        ) + [str(a) for a in (argv or [])]
        try:
            proc = self._popen(
                jailer_argv,
                stdin=subprocess.DEVNULL,
                stdout=serial_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # own process group → signallable as one
            )
        except OSError as exc:
            serial_file.close()
            self._cleanup_staging(staged, sandbox_id)
            raise VmmError(
                f"cannot spawn jailer: {type(exc).__name__}: {exc}"
            ) from exc

        self._records[sandbox_id] = _VmmRecord(
            sandbox_id=sandbox_id,
            pid=proc.pid,
            proc=proc,
            argv=jailer_argv,
            config_path=CONFIG_PATH_IN_CHROOT,
            config_digest=digest_of(vm_config),
            jail_dir=str(Path(chroot_dir).parent),
            serial_path=serial_path,
            serial_file=serial_file,
            started_at=utc_now_ms(),
            staged=staged,
        )

    def stop(self, sandbox_id: str) -> None:
        """SIGTERM → grace → SIGKILL; then serial evidence + jail cleanup."""
        rec = self._records.get(sandbox_id)
        if rec is None or rec.stopped_at is not None:
            return  # idempotent: unknown or already-stopped sandbox
        proc = rec.proc
        if proc.poll() is None:
            self._signal_group(proc, signal.SIGTERM)
            deadline = time.monotonic() + self._grace
            while proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            if proc.poll() is None:
                self._signal_group(proc, signal.SIGKILL)
                rec.termination = "sigkill"
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:  # pragma: no cover
                    rec.cleanup_error = "process still alive after SIGKILL"
            else:
                rec.termination = "sigterm"
        else:
            rec.termination = "already_exited"
        rec.exit_code = proc.poll()
        rec.stopped_at = utc_now_ms()
        # Serial log is evidence: close the handle (flush) but keep the file.
        try:
            rec.serial_file.close()
        except OSError:  # pragma: no cover — best effort
            pass
        if rec.exit_code is not None and rec.cleanup_error is None:
            # Process is dead: the jail dir (staged links, config, sockets,
            # the jailer's private firecracker copy) can go. Hardlinks —
            # originals are untouched.
            try:
                shutil.rmtree(rec.jail_dir)
            except OSError as exc:
                rec.cleanup_error = f"{type(exc).__name__}: {exc}"

    def is_running(self, sandbox_id: str) -> bool:
        rec = self._records.get(sandbox_id)
        return rec is not None and rec.proc.poll() is None

    # -- Evidence ---------------------------------------------------------

    def lifecycle_record(self, sandbox_id: str) -> dict:
        """Host-side VMM lifecycle facts for the evidence bundle."""
        rec = self._records.get(sandbox_id)
        if rec is None:
            return {}
        serial_sha = None
        try:
            serial_sha = sha256_hex(Path(rec.serial_path).read_bytes())
        except OSError:
            pass
        return {
            "event": "vmm_lifecycle",
            "sandbox_id": sandbox_id,
            "pid": rec.pid,
            "argv": rec.argv,
            "argv_digest": digest_of(rec.argv),
            "config_path": rec.config_path,
            "config_digest": rec.config_digest,
            "jail_dir": rec.jail_dir,
            "serial_log": rec.serial_path,
            "serial_log_sha256": serial_sha,
            "started_at": rec.started_at,
            "stopped_at": rec.stopped_at,
            "exit_code": rec.exit_code,
            "termination": rec.termination,
            "cleanup_error": rec.cleanup_error,
            "observed_at": utc_now_ms(),
        }

    # -- Helpers ----------------------------------------------------------

    @staticmethod
    def _config_paths(vm_config: dict) -> list:
        """Every host path Firecracker opens from inside the jail."""
        paths: list[str] = []
        kernel = (vm_config.get("boot-source") or {}).get("kernel_image_path")
        if kernel:
            paths.append(kernel)
        for drive in vm_config.get("drives") or []:
            path = drive.get("path_on_host")
            if path:
                paths.append(path)
        # Deduplicate, preserve order (rootfs and scratch may coincide in
        # degenerate configs — staging twice would EEXIST ourselves).
        return list(dict.fromkeys(paths))

    @staticmethod
    def _signal_group(proc: subprocess.Popen, sig: int) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except ProcessLookupError:
            pass
        except OSError:  # pragma: no cover — fall back to the pid itself
            try:
                proc.send_signal(sig)
            except OSError:
                pass

    @staticmethod
    def _cleanup_staging(staged: list, sandbox_id: str) -> None:
        for path in staged:
            try:
                os.unlink(path)
            except OSError:
                pass
