"""Run real admission/evidence/signing with a simulated namespace launch.

The Linux gate separately exercises the fixture against actual namespaces.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from click.testing import CliRunner
from sandbox_isolation.dev_evidence import validate_dev_evidence
from sandbox_isolation.dev_receipt import sign_dev_receipt
from sandbox_runtime import dev_check
from sandbox_runtime.bwrap import build_launch_command
from sandbox_runtime.config import NetworkMode
from workflo_cli.main import cli
from workflo_schema.contracts import SignedReceiptV5, decode_dsse_payload, is_full_pass
from workflo_schema.contracts.canonical import canonical_bytes, sha256_digest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="local dev runner targets Linux")


@pytest.fixture
def local_run(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-q", "--template=", "--object-format=sha1")
    (repo / "checks.py").write_text("def test_contract():\n    assert True\n")
    git("add", "--", "checks.py")
    git(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@workflo.invalid",
        "commit",
        "-qm",
        "fixture",
    )
    sha = git("rev-parse", "HEAD")
    state = SimpleNamespace(
        returncode=0, report="complete", launch_count=0, output_dir=tmp_path / "proof"
    )

    def setup(config):
        path = tmp_path / "cgroups" / config.sandbox_id
        path.mkdir(parents=True)
        assert (config.memory_mb, config.cpu_cores, config.pids_max) == (512, 1, 64)
        return path

    def launch(config, **_kwargs):
        state.launch_count += 1
        state.scratch = config.evidence_dir.parent.parent
        args = build_launch_command(config)
        assert config.network_mode is NetworkMode.NONE
        assert {"--unshare-net", "--clearenv", "--disable-userns"}.issubset(args)
        wrapper = args.index("/workflo/landlock_exec.py", args.index("--"))
        assert args[wrapper - 3 : wrapper] == ["/usr/bin/python3", "-I", "-S"]
        assert config.env["PYTHONPATH"] == "/opt/workflo/site"
        assert args[args.index("/workspace") - 2] == "--ro-bind"
        assert config.cgroup_procs.parent.is_dir()
        assert config.landlock_mode == "hardened"
        assert state.output_dir not in config.evidence_dir.parents
        assert not (state.output_dir / "receipt-key.pub.pem").exists()
        outcome = "failed" if state.returncode else "passed"
        test = {
            "nodeid": "checks.py::test_contract",
            "outcome": outcome,
            "setup": {"outcome": "passed"},
            "call": {"outcome": outcome},
            "teardown": {"outcome": "passed"},
        }
        filename = config.evidence_dir / "pytest-report.json"
        (config.evidence_dir / "landlock-status-test.json").write_text(
            '{"status":"LANDLOCK_APPLIED","mode":"hardened"}',
            encoding="utf-8",
        )
        if state.report == "setup-error":
            test["setup"]["outcome"] = "failed"
        if state.report == "symlink":
            filename.symlink_to(repo / "checks.py")
        elif state.report != "missing":
            tests = [] if state.report == "empty" else [test]
            filename.write_text(
                json.dumps(
                    {
                        "exitcode": state.returncode,
                        "tests": tests,
                        "summary": {
                            "collected": len(tests),
                            "total": len(tests),
                            outcome: len(tests),
                        },
                    }
                ),
                encoding="utf-8",
            )
        return SimpleNamespace(wait=lambda timeout: state.returncode, poll=lambda: state.returncode)

    monkeypatch.setattr(dev_check.shutil, "which", lambda _: "/usr/bin/bwrap")
    monkeypatch.setattr(dev_check, "probe_abi", lambda: 3)
    monkeypatch.setattr(dev_check, "measure_runtime", lambda _: sha256_digest(b"simulated-runtime"))
    monkeypatch.setattr(
        dev_check, "prepare_rootfs", lambda cfg: cfg.evidence_src.mkdir(parents=True)
    )
    monkeypatch.setattr(dev_check, "WORKFLO_CGROUP_ROOT", tmp_path / "cgroups")
    monkeypatch.setattr(dev_check, "setup_cgroup", setup)
    monkeypatch.setattr(dev_check, "run_bwrap", launch)

    runner = CliRunner()
    image = tmp_path / "image"
    image.mkdir()
    state.run = lambda **overrides: runner.invoke(
        cli,
        [
            "run-dev",
            "--repo",
            str(repo),
            "--runtime-image",
            str(image),
            "--commit",
            overrides.get("commit", sha),
            "--test-file",
            overrides.get("test_file", "checks.py"),
            "--output-dir",
            str(state.output_dir),
        ],
    )
    state.verify = lambda *args, trusted=True: runner.invoke(
        cli,
        [
            "verify",
            str(state.output_dir / "receipt.json"),
            *(["--pubkey", str(state.output_dir / "receipt-key.pub.pem")] if trusted else []),
            *args,
        ],
    )
    state.sha = sha
    return state


@pytest.mark.parametrize("returncode,verdict", [(0, "PASS"), (1, "FAIL")])
def test_pinned_development_receipt(local_run, tmp_path, monkeypatch, returncode, verdict):
    local_run.returncode = returncode
    result = local_run.run()
    assert result.exit_code == returncode, result.output
    assert not local_run.scratch.exists()
    proof = local_run.output_dir
    assert set(p.name for p in proof.iterdir()) == {
        "receipt.json",
        "receipt-key.pub.pem",
        "evidence",
    }
    receipt = SignedReceiptV5.model_validate_json((proof / "receipt.json").read_bytes())
    payload = decode_dsse_payload(receipt.envelope)
    assert payload.source.commit == local_run.sha
    assert is_full_pass(payload.outcome) is (returncode == 0)
    assert {c.check_id.value for c in payload.teardown_verification.checks} == {
        "process_scope_empty",
        "cgroups_removed",
        "workspace_removed",
    }
    findings = json.loads((proof / "evidence/findings.json").read_bytes())
    assert len(findings) == returncode
    if findings:
        assert findings[0]["category"] == "verified_failure"
        assert findings[0]["reproduction_reference"] == "checks.py::test_contract"
        assert findings[0]["evidence_refs"] == ["checks"]
    local_run.output_dir = proof.rename(tmp_path / "moved")
    monkeypatch.chdir(tmp_path)
    verified = local_run.verify()
    assert verified.exit_code == 0, verified.output
    assert f"QA verdict: {verdict}" in verified.output
    assert local_run.verify(trusted=False).exit_code == 4


@pytest.mark.parametrize(
    "rc,report", [(2, "complete"), (0, "empty"), (1, "missing"), (1, "setup-error"), (0, "symlink")]
)
def test_incomplete_check_is_infra_failure_not_finding(local_run, rc, report):
    local_run.returncode = rc
    local_run.report = report
    result = local_run.run()
    assert result.exit_code == 6, result.output
    assert "Infrastructure failure" in result.output
    assert not (local_run.output_dir / "receipt.json").exists()
    assert not local_run.scratch.exists()


def test_teardown_failure_blocks_receipt_even_when_checks_pass(local_run, monkeypatch):
    monkeypatch.setattr(
        dev_check,
        "teardown_and_verify",
        lambda *a: SimpleNamespace(
            processes_terminated=True,
            cgroup_removed=False,
        ),
    )
    result = local_run.run()
    assert result.exit_code == 4, result.output
    assert "Teardown verification failed" in result.output
    assert not (local_run.output_dir / "receipt.json").exists()
    assert not local_run.scratch.exists()


@pytest.mark.parametrize(
    "overrides",
    [
        {"commit": "main"},
        {"commit": "abcd123"},
        {"test_file": "../checks.py"},
        {"test_file": "missing.py"},
    ],
)
def test_policy_rejection_precedes_launch(local_run, overrides):
    result = local_run.run(**overrides)
    assert result.exit_code == 2, result.output
    assert local_run.launch_count == 0
    assert not (local_run.output_dir / "receipt.json").exists()


@pytest.mark.parametrize(
    "filename",
    [
        "policy.json",
        "checks.json",
        "snapshot.json",
        "findings.json",
        "events.jsonl",
        "manifest.json",
        "teardown.json",
    ],
)
def test_verification_and_signing_reject_evidence_tamper(local_run, filename):
    assert local_run.run().exit_code == 0
    directory = local_run.output_dir / "evidence"
    _, manifest, _ = validate_dev_evidence(directory)
    target = directory / filename
    target.write_bytes(target.read_bytes() + b" ")
    verify = local_run.verify()
    assert verify.exit_code == 4, verify.output
    key = Mock()
    with pytest.raises(ValueError, match="evidence"):
        sign_dev_receipt(directory, manifest.digest(), key)
    key.sign.assert_not_called()


def test_no_teardown_no_receipt_verification(local_run):
    assert local_run.run().exit_code == 0
    directory = local_run.output_dir / "evidence"
    _, manifest, _ = validate_dev_evidence(directory)
    (directory / "teardown.json").unlink()
    assert local_run.verify().exit_code == 4
    with pytest.raises(ValueError, match="missing"):
        sign_dev_receipt(directory, manifest.digest(), Mock())
    directory.rename(directory.with_name("elsewhere"))
    assert local_run.verify().exit_code == 4


def test_receipt_payload_tamper(local_run):
    assert local_run.run().exit_code == 0
    file = local_run.output_dir / "receipt.json"
    original = json.loads(file.read_bytes())
    payload = json.loads(base64.b64decode(original["envelope"]["payload"]))
    payload["source"]["commit"] = "f" * 40
    original["envelope"]["payload"] = base64.b64encode(canonical_bytes(payload)).decode("ascii")
    file.write_text(json.dumps(original), encoding="utf-8")
    failure = local_run.verify()
    assert failure.exit_code == 4
    assert "signature verification failed" in failure.output


def test_evidence_from_another_run_is_not_portable_to_this_one(local_run, tmp_path):
    assert local_run.run().exit_code == 0
    first = local_run.output_dir / "evidence"
    _, manifest, _ = validate_dev_evidence(first)
    local_run.output_dir = tmp_path / "other"
    assert local_run.run().exit_code == 0
    assert local_run.verify("--evidence", str(first)).exit_code == 4
    with pytest.raises(ValueError, match="host's finalized manifest"):
        sign_dev_receipt(local_run.output_dir / "evidence", manifest.digest(), Mock())
