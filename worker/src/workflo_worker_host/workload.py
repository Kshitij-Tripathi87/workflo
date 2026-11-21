"""The fixed safe workload for the microVM slice (no AI, no network).

One deterministic, bounded workload the guest runs after its capability is
verified and GUEST_READY is announced. It proves the slice executed real
work inside the guest without any model, tool, or egress surface:

1. **workspace marker** — write a fixed marker into the provisioned
   workspace, read it back, digest must match the pinned constant
   (proves the workspace is writable and intact);
2. **hash determinism** — ``sha256(b"workflo-slice-v1")`` computed twice
   must agree with the pinned digest baked into this module (proves the
   guest crypto stack matches the host's expectation byte-for-byte);
3. **environment sanity** — ``/proc/meminfo`` must be readable with a
   positive ``MemTotal`` (proves we are really running on a live kernel,
   not a stub).

Every check is recorded; ``ok`` is true only when ALL checks pass. The
result travels back inside the evidence manifest (``workload_result``),
and the host derives ``qa_status`` from it — the guest never sets QA.
"""

from __future__ import annotations

from pathlib import Path

from workflo_schema.contracts.common import utc_now_ms

__all__ = ["FIXED_WORKLOAD_ID", "PINNED_MARKER_SHA256", "run_fixed_workload"]

FIXED_WORKLOAD_ID = "workflo-slice-workload-v1"

# sha256(b"workflo-slice-v1") — pinned so a diverging guest stack fails
# the determinism check instead of silently hashing differently.
PINNED_MARKER_SHA256 = (
    "90ade0e9c57a748f941249f69099820181f2fad724de6fc0986daaaff4e30188"
)

_MARKER_BYTES = b"workflo-slice-v1"
_MARKER_FILENAME = "workflo-slice-marker.bin"


def run_fixed_workload(workspace: Path | str) -> dict:
    """Run the fixed workload inside ``workspace``. Never raises.

    Returns ``{workload_id, checks, ok, completed_at}`` where each check
    is ``{name, ok, detail}``. ``ok`` is true iff every check passed.
    """
    import hashlib

    workspace = Path(workspace)
    checks: list[dict] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail[:256]})

    # 1. Workspace marker: write → read → digest must match the pin.
    marker_path = workspace / _MARKER_FILENAME
    try:
        workspace.mkdir(parents=True, exist_ok=True)
        marker_path.write_bytes(_MARKER_BYTES)
        read_back = marker_path.read_bytes()
        digest = hashlib.sha256(read_back).hexdigest()
        if read_back == _MARKER_BYTES and digest == PINNED_MARKER_SHA256:
            record("workspace_marker", True, f"wrote and verified {digest}")
        else:
            record(
                "workspace_marker",
                False,
                f"read-back mismatch: got {digest!r}",
            )
    except OSError as exc:
        record("workspace_marker", False, f"{type(exc).__name__}: {exc}")

    # 2. Hash determinism: two independent computations vs the pin.
    try:
        first = hashlib.sha256(_MARKER_BYTES).hexdigest()
        second = hashlib.sha256(bytes(_MARKER_BYTES)).hexdigest()
        if first == second == PINNED_MARKER_SHA256:
            record("hash_determinism", True, f"both computations = {first}")
        else:
            record(
                "hash_determinism",
                False,
                f"first={first} second={second} pinned={PINNED_MARKER_SHA256}",
            )
    except Exception as exc:  # noqa: BLE001 — a failing check is a result
        record("hash_determinism", False, f"{type(exc).__name__}: {exc}")

    # 3. Live kernel: /proc/meminfo readable, MemTotal positive.
    try:
        meminfo = Path("/proc/meminfo").read_text()
        total_line = next(
            (ln for ln in meminfo.splitlines() if ln.startswith("MemTotal:")),
            "",
        )
        total_kib = int(total_line.split()[1])
        if total_kib > 0:
            record("environment_sanity", True, f"MemTotal={total_kib} kB")
        else:
            record("environment_sanity", False, f"MemTotal={total_kib} kB")
    except Exception as exc:  # noqa: BLE001 — missing /proc is a failed check
        record("environment_sanity", False, f"{type(exc).__name__}: {exc}")

    return {
        "workload_id": FIXED_WORKLOAD_ID,
        "checks": checks,
        "ok": all(check["ok"] for check in checks),
        "completed_at": utc_now_ms(),
    }
