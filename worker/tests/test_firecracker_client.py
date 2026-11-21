"""Real Firecracker client tests against a stand-in jailer/firecracker.

No KVM here: the "jailer" is a scripted binary that mimics the real
one's observable contract — creates ``<chroot_base>/<exec_name>/<id>/root``,
forwards args after ``--``, writes serial output, exits on SIGTERM. That
exercises staging, argv construction, serial capture, signal escalation,
and jail cleanup for real; the KVM-gated e2e covers the actual binaries.
"""

from __future__ import annotations

import os
import stat
import textwrap
import time
from pathlib import Path

import pytest
from workflo_worker_host.admission import PinnedRuntime
from workflo_worker_host.firecracker_client import (
    CONFIG_PATH_IN_CHROOT,
    JailerFirecrackerClient,
    VmmError,
)


def _pinned(firecracker: str, jailer: str) -> PinnedRuntime:
    return PinnedRuntime(
        firecracker_version="v1.18.0",
        jailer_version="v1.18.0",
        firecracker_path=firecracker,
        jailer_path=jailer,
        guest_images={"11" * 32: "/srv/images/vmlinux.bin",
                      "22" * 32: "/srv/images/rootfs.ext4"},
    )


def _write_script(path, body: str) -> str:
    # lstrip so the shebang lands on line 1 — exec(2) requires it there.
    path.write_text(textwrap.dedent(body).lstrip("\n"))
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


@pytest.fixture
def fake_jailer(tmp_path):
    """A jailer stand-in: creates the chroot layout, runs 'firecracker'.

    The fake firecracker (same script, argv-dependent) prints serial
    output, then sleeps until SIGTERM (or forever if FAKE_IGNORE_TERM=1).
    """
    script = tmp_path / "fake_jailer.py"
    return _write_script(
        script,
        """
        #!/usr/bin/env python3
        import os, sys, time, signal, json, pathlib

        args = sys.argv[1:]
        # Split jailer args from firecracker args (after --).
        if "--" in args:
            split = args.index("--")
            jailer_args, fc_args = args[:split], args[split + 1:]
        else:
            jailer_args, fc_args = args, []

        def value_of(flag):
            return jailer_args[jailer_args.index(flag) + 1]

        sandbox_id = value_of("--id")
        chroot_base = value_of("--chroot-base-dir")
        exec_file = value_of("--exec-file")
        exec_name = os.path.basename(exec_file)
        chroot_dir = pathlib.Path(chroot_base) / exec_name / sandbox_id / "root"
        # Jailer contract: create the layout (nothing to do if it exists).
        (chroot_dir / exec_name).parent.mkdir(parents=True, exist_ok=True)
        chroot_dir.mkdir(parents=True, exist_ok=True)
        # Copy the exec file into the jail (like the real jailer).
        staged_exec = chroot_dir / exec_name
        if not staged_exec.exists():
            staged_exec.write_bytes(b"fake-binary")

        # The config path must resolve INSIDE the chroot: the real
        # firecracker would be pivot_root'ed, so verify our staged copy.
        config_arg = fc_args[fc_args.index("--config-file") + 1]
        staged_config = chroot_dir / config_arg.lstrip("/")
        if not staged_config.exists():
            print(f"fatal: config {config_arg} missing in jail", flush=True)
            sys.exit(2)
        config = json.loads(staged_config.read_text())
        vcpus = config["machine-config"]["vcpu_count"]
        kernel = config["boot-source"]["kernel_image_path"]
        if not (chroot_dir / kernel.lstrip("/")).exists():
            print(f"fatal: kernel {kernel} missing in jail", flush=True)
            sys.exit(3)

        print(f"fake-firecracker: booting {vcpus} vcpu kernel={kernel}", flush=True)
        print(f"fake-firecracker: serial line two sandbox={sandbox_id}", flush=True)

        ignore = os.environ.get("FAKE_IGNORE_TERM") == "1"
        if ignore:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        else:
            def on_term(signum, frame):
                print("fake-firecracker: SIGTERM received, exiting", flush=True)
                sys.exit(0)
            signal.signal(signal.SIGTERM, on_term)

        while True:
            time.sleep(0.05)
        """,
    )


def _vm_config(kernel: str, rootfs: str, scratch: str, vsock: str) -> dict:
    return {
        "boot-source": {
            "kernel_image_path": kernel,
            "boot_args": "console=ttyS0 reboot=k panic=1",
        },
        "drives": [
            {"path_on_host": rootfs, "is_root_device": True, "is_read_only": True},
            {"path_on_host": scratch, "is_root_device": False, "is_read_only": False},
        ],
        "machine-config": {"vcpu_count": 2, "mem_size_mib": 2048},
        "vsock": {"uds_path": vsock, "guest_cid": 3},
    }


def _scratch(tmp_path: Path) -> str:
    """The manager pre-creates the scratch disk; tests must too."""
    scratch_dir = tmp_path / "scratch"
    scratch_dir.mkdir(exist_ok=True)
    scratch = scratch_dir / "sbx-1.img"
    scratch.write_bytes(b"scratch-bytes")
    return str(scratch)


def _stage_images(tmp_path):
    images = tmp_path / "images"
    images.mkdir(exist_ok=True)
    kernel = images / "vmlinux.bin"
    rootfs = images / "rootfs.ext4"
    kernel.write_bytes(b"kernel-bytes")
    rootfs.write_bytes(b"rootfs-bytes")
    return str(kernel), str(rootfs)


def _client(tmp_path, fake_jailer, **kwargs) -> JailerFirecrackerClient:
    return JailerFirecrackerClient(
        pinned=_pinned(fake_jailer, fake_jailer),  # exec-file name = fake_jailer.py
        chroot_base=str(tmp_path / "jailer"),
        work_dir=str(tmp_path / "vmm"),
        uid=1000,
        gid=1000,
        stop_grace_seconds=2.0,
        **kwargs,
    )


def test_start_stages_into_chroot_and_boots(tmp_path, fake_jailer):
    kernel, rootfs = _stage_images(tmp_path)
    scratch = _scratch(tmp_path)

    client = _client(tmp_path, fake_jailer)
    vsock = "/run/workflo/vsock/sbx-1.sock"
    config = _vm_config(kernel, rootfs, scratch, vsock)
    client.start("sbx-1", config, [])

    assert client.is_running("sbx-1")
    chroot = client.sandbox_chroot("sbx-1")
    # Staged hardlinks at their in-jail absolute paths.
    assert os.path.exists(f"{chroot}{kernel}")
    assert os.path.exists(f"{chroot}{rootfs}")
    assert os.path.exists(f"{chroot}{scratch}")
    assert os.path.exists(f"{chroot}{CONFIG_PATH_IN_CHROOT}")
    # host_view_path is the chroot-relative mapping.
    assert client.host_view_path("sbx-1", kernel) == f"{chroot}{kernel}"

    client.stop("sbx-1")
    assert not client.is_running("sbx-1")


def test_serial_log_captures_guest_console(tmp_path, fake_jailer):
    kernel, rootfs = _stage_images(tmp_path)
    scratch = _scratch(tmp_path)
    client = _client(tmp_path, fake_jailer)
    client.start(
        "sbx-1",
        _vm_config(kernel, rootfs, scratch, "/run/workflo/vsock/sbx-1.sock"),
        [],
    )
    # Give the fake a moment to print.
    deadline = time.monotonic() + 3.0
    serial = client.serial_log_path("sbx-1")
    while time.monotonic() < deadline:
        if os.path.exists(serial) and b"fake-firecracker" in open(serial, "rb").read():
            break
        time.sleep(0.02)
    client.stop("sbx-1")
    content = open(serial, "rb").read()
    assert b"fake-firecracker: booting 2 vcpu" in content
    assert b"serial line two" in content

    record = client.lifecycle_record("sbx-1")
    assert record["serial_log"] == serial
    assert record["serial_log_sha256"]  # digest captured as evidence
    assert record["termination"] == "sigterm"
    assert record["exit_code"] == 0
    assert record["config_digest"].startswith("sha256:")


def test_stop_escalates_to_sigkill_when_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_IGNORE_TERM", "1")
    jailer = tmp_path / "stubborn_jailer.py"
    script = _write_script(
        jailer,
        """
        #!/usr/bin/env python3
        import os, sys, time, signal, pathlib
        # Ignore SIGTERM BEFORE any other work: stop() may signal as soon
        # as spawn returns, so the handler must already be installed.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        args = sys.argv[1:]
        split = args.index("--")
        jailer_args, fc_args = args[:split], args[split + 1:]
        def value_of(flag):
            return jailer_args[jailer_args.index(flag) + 1]
        sandbox_id = value_of("--id")
        chroot_base = value_of("--chroot-base-dir")
        exec_name = os.path.basename(value_of("--exec-file"))
        chroot_dir = pathlib.Path(chroot_base) / exec_name / sandbox_id / "root"
        chroot_dir.mkdir(parents=True, exist_ok=True)
        (chroot_dir / exec_name).parent.mkdir(parents=True, exist_ok=True)
        config_arg = fc_args[fc_args.index("--config-file") + 1]
        staged = chroot_dir / config_arg.lstrip("/")
        if not staged.exists():
            sys.exit(2)
        print("stubborn: ignoring SIGTERM", flush=True)
        while True:
            time.sleep(0.05)
        """,
    )
    kernel, rootfs = _stage_images(tmp_path)
    scratch = _scratch(tmp_path)
    client = JailerFirecrackerClient(
        pinned=_pinned(script, script),
        chroot_base=str(tmp_path / "jailer"),
        work_dir=str(tmp_path / "vmm"),
        stop_grace_seconds=0.2,  # short grace so the test is fast
    )
    client.start(
        "sbx-1",
        _vm_config(kernel, rootfs, scratch, "/run/workflo/vsock/sbx-1.sock"),
        [],
    )
    assert client.is_running("sbx-1")
    # Wait until the child has actually installed SIG_IGN — signalling
    # before the interpreter boots would hit the default disposition and
    # die on SIGTERM, defeating the escalation test.
    serial = client.serial_log_path("sbx-1")
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if os.path.exists(serial) and b"ignoring SIGTERM" in open(serial, "rb").read():
            break
        time.sleep(0.02)
    else:
        pytest.fail("stubborn child never reported ready")
    client.stop("sbx-1")
    assert not client.is_running("sbx-1")
    record = client.lifecycle_record("sbx-1")
    assert record["termination"] == "sigkill"


def test_start_refuses_when_already_running(tmp_path, fake_jailer):
    kernel, rootfs = _stage_images(tmp_path)
    scratch = _scratch(tmp_path)
    client = _client(tmp_path, fake_jailer)
    config = _vm_config(kernel, rootfs, scratch, "/run/workflo/vsock/sbx-1.sock")
    client.start("sbx-1", config, [])
    try:
        with pytest.raises(VmmError, match="already running"):
            client.start("sbx-1", config, [])
    finally:
        client.stop("sbx-1")


def test_start_fails_cleanly_when_staging_source_missing(tmp_path, fake_jailer):
    scratch = _scratch(tmp_path)
    client = _client(tmp_path, fake_jailer)
    config = _vm_config(
        str(tmp_path / "no-such-kernel"),  # missing source
        str(tmp_path / "no-such-rootfs"),
        scratch,
        "/run/workflo/vsock/sbx-1.sock",
    )
    with pytest.raises(VmmError, match="cannot stage"):
        client.start("sbx-1", config, [])
    assert not client.is_running("sbx-1")
    # No jail dir left behind by the failed staging.
    assert not os.path.exists(client.sandbox_chroot("sbx-1"))


def test_start_fails_when_jailer_missing(tmp_path):
    client = _client(tmp_path, tmp_path / "does-not-exist.py")
    kernel, rootfs = _stage_images(tmp_path)
    with pytest.raises(VmmError, match="jailer binary not found"):
        client.start(
            "sbx-1",
            _vm_config(kernel, rootfs, _scratch(tmp_path), "/v/x.sock"),
            [],
        )


def test_stop_is_idempotent_and_unknown_is_noop(tmp_path, fake_jailer):
    kernel, rootfs = _stage_images(tmp_path)
    client = _client(tmp_path, fake_jailer)
    client.start(
        "sbx-1",
        _vm_config(kernel, rootfs, _scratch(tmp_path), "/v/x.sock"),
        [],
    )
    client.stop("sbx-1")
    first = client.lifecycle_record("sbx-1")
    client.stop("sbx-1")  # second stop must not clobber the record
    second = client.lifecycle_record("sbx-1")
    assert first["termination"] == second["termination"]
    client.stop("never-started")  # no-op, no raise
    assert client.lifecycle_record("never-started") == {}


def test_stop_removes_jail_dir_but_keeps_serial_log(tmp_path, fake_jailer):
    kernel, rootfs = _stage_images(tmp_path)
    client = _client(tmp_path, fake_jailer)
    client.start(
        "sbx-1",
        _vm_config(kernel, rootfs, _scratch(tmp_path), "/v/x.sock"),
        [],
    )
    jail_dir = os.path.dirname(client.sandbox_chroot("sbx-1"))
    serial = client.serial_log_path("sbx-1")
    client.stop("sbx-1")
    assert not os.path.exists(jail_dir)
    # Serial log survives: it is host evidence, not jail state.
    assert os.path.exists(serial)


def test_rejects_relative_paths():
    with pytest.raises(VmmError, match="absolute"):
        JailerFirecrackerClient(
            pinned=_pinned("/bin/true", "/bin/true"), chroot_base="relative/path"
        )
    with pytest.raises(VmmError, match="absolute"):
        JailerFirecrackerClient(
            pinned=_pinned("/bin/true", "/bin/true"), work_dir="relative/path"
        )
