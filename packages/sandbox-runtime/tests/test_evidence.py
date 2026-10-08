"""Tests for evidence collector."""

import pytest
from pathlib import Path
import json

from sandbox_runtime.evidence import (
    EvidenceCollector, verify_evidence_bundle, _hash_directory
)


def test_evidence_write_event(tmp_path):
    evidence_dir = tmp_path / "evidence"
    collector = EvidenceCollector(evidence_dir)
    
    event_id = collector.write_event("TEST_EVENT", {"key": "value"})
    
    assert event_id == "evt_00000001"
    
    events_file = evidence_dir / "events.jsonl"
    assert events_file.exists()
    
    with open(events_file) as f:
        line = f.readline()
        event = json.loads(line)
    
    assert event["event_id"] == "evt_00000001"
    assert event["event_type"] == "TEST_EVENT"
    assert event["data"]["key"] == "value"
    assert event["prev_hash"] == "0" * 64


def test_evidence_hash_chain(tmp_path):
    evidence_dir = tmp_path / "evidence"
    collector = EvidenceCollector(evidence_dir)
    
    collector.write_event("EVENT_1", {"a": 1})
    collector.write_event("EVENT_2", {"b": 2})
    collector.write_event("EVENT_3", {"c": 3})
    
    events_file = evidence_dir / "events.jsonl"
    with open(events_file) as f:
        events = [json.loads(line) for line in f]
    
    # Verify hash chain
    assert events[0]["prev_hash"] == "0" * 64
    assert events[1]["prev_hash"] == events[0]["event_hash"]
    assert events[2]["prev_hash"] == events[1]["event_hash"]


def test_evidence_write_log(tmp_path):
    evidence_dir = tmp_path / "evidence"
    collector = EvidenceCollector(evidence_dir)
    
    log_path = collector.write_log("test", "log content")
    
    assert Path(log_path).exists()
    assert Path(log_path).read_text() == "log content"


def test_evidence_finalize(tmp_path):
    evidence_dir = tmp_path / "evidence"
    collector = EvidenceCollector(evidence_dir)
    
    collector.write_event("START", {})
    collector.write_event("END", {})
    
    manifest_path = collector.finalize([], "run-123", "sandbox-456")
    
    assert manifest_path.exists()
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    assert manifest["run_id"] == "run-123"
    assert manifest["sandbox_id"] == "sandbox-456"
    assert manifest["events_count"] == 2
    assert "events_sha256" in manifest


def test_hash_directory(tmp_path):
    (tmp_path / "file1.txt").write_text("hello")
    (tmp_path / "file2.txt").write_text("world")
    
    hash_val = _hash_directory(tmp_path)
    
    assert len(hash_val) == 64


def test_verify_evidence_bundle(tmp_path):
    evidence_dir = tmp_path / "evidence"
    collector = EvidenceCollector(evidence_dir)
    
    collector.write_event("TEST", {"data": "value"})
    collector.finalize([], "run-123", "sandbox-456")
    
    assert verify_evidence_bundle(evidence_dir) is True


def test_verify_evidence_bundle_tampered(tmp_path):
    evidence_dir = tmp_path / "evidence"
    collector = EvidenceCollector(evidence_dir)
    
    collector.write_event("TEST", {"data": "value"})
    collector.finalize([], "run-123", "sandbox-456")
    
    # Tamper with events.jsonl
    events_file = evidence_dir / "events.jsonl"
    with open(events_file, "a") as f:
        f.write('{"event_id":"evt_99999999","event_type":"TAMPERED"}\n')
    
    assert verify_evidence_bundle(evidence_dir) is False