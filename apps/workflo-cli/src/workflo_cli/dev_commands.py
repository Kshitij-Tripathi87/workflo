"""Explicit, local-only CLI surface for the Phase 1 development profile."""

import subprocess
from pathlib import Path

import click
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from workflo_cli.exit_codes import (
    EXIT_INFRASTRUCTURE_ERROR,
    EXIT_POLICY_BLOCKED,
    EXIT_VERIFICATION_FAILED,
)


@click.command("run-dev")
@click.option(
    "--repo",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Local Git repository. Uncommitted work is not used.",
)
@click.option("--commit", required=True, help="Full lowercase Git commit SHA (SHA-1).")
@click.option(
    "--test-file", required=True, help="One tracked pytest file, relative to the repository root."
)
@click.option(
    "--output-dir",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="New directory for the receipt, evidence and public key.",
)
@click.option(
    "--runtime-image",
    default="/opt/workflo/workflo-worker",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Trusted, locally built Workflo runtime tree.",
)
def run_dev(repo: Path, commit: str, test_file: str, output_dir: Path, runtime_image: Path) -> None:
    """Run a pinned, offline pytest check in Linux namespaces (development only)."""
    from sandbox_isolation.dev_evidence import DevEvidence, write_dev_evidence
    from sandbox_isolation.dev_receipt import sign_dev_receipt
    from sandbox_runtime.dev_check import DevTeardownError, run_local_check

    try:
        observed = run_local_check(repo, commit, test_file, runtime_image, output_dir)
    except ValueError as exc:
        click.echo(f"Policy rejected the run (no receipt): {exc}", err=True)
        raise click.exceptions.Exit(EXIT_POLICY_BLOCKED) from exc
    except DevTeardownError as exc:
        click.echo(f"Teardown verification failed (no receipt): {exc}", err=True)
        raise click.exceptions.Exit(EXIT_VERIFICATION_FAILED) from exc
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        click.echo(f"Infrastructure failure (no receipt): {exc}", err=True)
        raise click.exceptions.Exit(EXIT_INFRASTRUCTURE_ERROR) from exc

    evidence = DevEvidence(
        spec=observed.spec,
        policy=observed.policy,
        snapshot=observed.snapshot,
        report=observed.report,
        teardown=observed.teardown,
        snapshot_at=observed.snapshot_at,
        checks_at=observed.checks_at,
    )
    directory = output_dir / "evidence"
    try:
        anchor = write_dev_evidence(directory, evidence)
        # Generated only after the isolated process and its scratch are gone.
        # The private key never enters the runtime or proof directory.
        key = Ed25519PrivateKey.generate()
        receipt = sign_dev_receipt(directory, anchor, key)
        (output_dir / "receipt-key.pub.pem").write_bytes(
            key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        staged_receipt = output_dir / ".receipt.json.tmp"
        staged_receipt.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
        staged_receipt.replace(output_dir / "receipt.json")
    except (OSError, ValueError) as exc:
        click.echo(f"Attestation failed (no receipt): {exc}", err=True)
        raise click.exceptions.Exit(EXIT_VERIFICATION_FAILED) from exc

    failures = [check.node_id for check in observed.report.checks if check.outcome == "failed"]
    click.echo(f"Development QA: {'FAIL' if failures else 'PASS'}; host teardown: verified")
    click.echo(f"Pinned commit: {observed.snapshot.commit}")
    for node_id in failures:
        click.echo(f"  Failed: {node_id}")
    click.echo(f"Receipt: {output_dir / 'receipt.json'}")
    raise click.exceptions.Exit(observed.report.returncode)
