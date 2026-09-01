"""workflo CLI — `workflo run --repo <repo-url> --test --security` runs the full sandbox pipeline.

This is the user-facing command that ties everything together:
  - probe-engine generates the default probe config based on flags
  - sandbox-executor mounts tmpfs, clones the repo, creates a Docker container
    with --network none, runs the tests via the probe engine, tears down,
    and signs the receipt
  - CLI prints the signed receipt JSON to stdout

Usage:
    workflo run --repo https://github.com/example/repo.git --test
    workflo run --repo https://github.com/example/repo.git --deep-test --security
    workflo run --repo https://github.com/example/repo.git --aggressive-test
    workflo verify --receipt receipt.json --pubkey public.pem
    workflo keygen
"""

from workflo_cli.main import cli

__all__ = ["cli"]

__version__ = "0.1.0"
