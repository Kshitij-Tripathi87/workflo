"""Per-test evidence sink shared by the isolation library and the reporting plugin.

The isolation library pushes `VerificationRecord`s here when a test exercises
an `IsolationScenario`. The reporting plugin registers a sink per test and
reads the collected records on teardown to build evidence rows. When no sink
is registered (plain `pytest` run), `add_record` is a no-op, so there is zero
overhead and no behavior change for users who do not opt in.
"""

import threading

_sinks = {}
_current_key = None
_lock = threading.Lock()


class EvidenceSink:
    def __init__(self, key: str):
        self.key = key
        self.records = []
        self.tenant_pair = []

    def add(self, record):
        self.records.append(record)
        rec_pair = record.tenant_pair
        for t in rec_pair:
            if t and t not in self.tenant_pair:
                self.tenant_pair.append(t)

    def to_confirmation(self):
        pair = []
        controls = []
        for r in self.records:
            for t in (r.tenant_pair or []):
                if t and t != "none" and t not in pair:
                    pair.append(t)
            for c in (r.evidence or {}).get("soc2_controls", []):
                if c not in controls:
                    controls.append(c)
        return self.records, pair, controls


def register_sink(key: str) -> EvidenceSink:
    sink = EvidenceSink(key)
    with _lock:
        _sinks[key] = sink
    return sink


def get_sink(key: str):
    with _lock:
        return _sinks.get(key)


def clear_sink(key: str):
    with _lock:
        return _sinks.pop(key, None)


def set_current_key(key):
    """Set the key the isolation scenario should push to for the active test."""
    global _current_key
    _current_key = key


def add_record(record):
    """Called by the isolation scenario. No-op if no sink is registered."""
    key = _current_key or "default"
    with _lock:
        sink = _sinks.get(key)
    if sink is not None:
        sink.add(record)
