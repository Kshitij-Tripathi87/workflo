"""Dependency resolution modes for sealed execution."""

from __future__ import annotations

import hashlib
import json
import subprocess
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from sandbox_runtime.config import DepConfig, DepResult, DepMode


def resolve_dependencies(config: DepConfig) -> DepResult:
    """Resolve dependencies per configured mode."""
    lockfile_path = _find_lockfile(config.repo_path, config.lockfile)
    lockfile_sha = _hash_file(lockfile_path) if lockfile_path else None
    
    if config.mode == DepMode.PREFLIGHT_CACHE:
        return _preflight_cache(config, lockfile_path)
    elif config.mode == DepMode.VENDOR_CACHE:
        return _vendor_cache(config, lockfile_path)
    elif config.mode == DepMode.FIXTURE_MIRROR:
        return _fixture_mirror(config, lockfile_path)
    elif config.mode == DepMode.USER_APPROVED:
        return _user_approved(config, lockfile_path)
    else:
        raise ValueError(f"Unknown dep mode: {config.mode}")


def _preflight_cache(config: DepConfig, lockfile: Optional[Path]) -> DepResult:
    """Download/cache packages before sealed run."""
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    
    lockfile_sha = _hash_file(lockfile) if lockfile else None
    
    # Detect package manager and run install with cache
    if (config.repo_path / "requirements.txt").exists():
        _pip_cache_install(config.repo_path, config.cache_dir)
    elif (config.repo_path / "package.json").exists():
        _npm_cache_install(config.repo_path, config.cache_dir)
    elif (config.repo_path / "go.mod").exists():
        _go_cache_install(config.repo_path, config.cache_dir)
    elif (config.repo_path / "Cargo.toml").exists():
        _cargo_cache_install(config.repo_path, config.cache_dir)
    
    cache_manifest = _generate_cache_manifest(config.cache_dir)
    
    return DepResult(
        mode=DepMode.PREFLIGHT_CACHE,
        network_policy="user-approved",
        lockfile_sha256=lockfile_sha,
        cache_manifest_sha256=cache_manifest,
        resolved=True,
    )


def _vendor_cache(config: DepConfig, lockfile: Optional[Path]) -> DepResult:
    """Use committed vendor/cache directory (no network).

    A repo with no lockfile AND no vendor/ directory has no dependencies
    to vendor — that resolves trivially (nothing to install, network
    policy none). Only a repo WITH a lockfile but WITHOUT a vendored
    cache is an error: its deps are missing for a sealed run.
    """
    lockfile_sha = _hash_file(lockfile) if lockfile else None

    vendor_dir = None
    for candidate in [config.repo_path / "vendor",
                      config.repo_path / ".vendor",
                      config.repo_path / "node_modules",
                      config.repo_path / "vendor" / "cache"]:
        if candidate.exists():
            vendor_dir = candidate
            break

    if vendor_dir is None:
        if lockfile is None:
            # No dependencies declared and none vendored: sealed run is
            # self-contained by definition.
            return DepResult(
                mode=DepMode.VENDOR_CACHE,
                network_policy="none",
                lockfile_sha256=None,
                cache_manifest_sha256=None,
                resolved=True,
            )
        raise RuntimeError(
            f"lockfile {lockfile.name} present but no vendor/ directory — "
            "run the vendor step first or use --dependency-install"
        )

    cache_manifest = _generate_cache_manifest(vendor_dir)

    return DepResult(
        mode=DepMode.VENDOR_CACHE,
        network_policy="none",
        lockfile_sha256=lockfile_sha,
        cache_manifest_sha256=cache_manifest,
        resolved=True,
    )


def _fixture_mirror(config: DepConfig, lockfile: Optional[Path]) -> DepResult:
    """Use internal fixture mirror (advanced teams)."""
    # This would point to an internal package mirror
    mirror_url = os.environ.get("WORKFLO_PACKAGE_MIRROR")
    if not mirror_url:
        raise RuntimeError("WORKFLO_PACKAGE_MIRROR not set for fixture_mirror mode")
    
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Install from mirror
    if (config.repo_path / "requirements.txt").exists():
        subprocess.run([
            "pip", "install", "--no-deps", "--no-build-isolation",
            "--index-url", mirror_url,
            "-r", str(config.repo_path / "requirements.txt")
        ], check=True, cwd=config.repo_path)
    elif (config.repo_path / "package.json").exists():
        subprocess.run([
            "npm", "ci", "--registry", mirror_url
        ], check=True, cwd=config.repo_path)
    
    cache_manifest = _generate_cache_manifest(config.cache_dir)
    
    return DepResult(
        mode=DepMode.FIXTURE_MIRROR,
        network_policy="internal-only",
        lockfile_sha256=lockfile_sha,
        cache_manifest_sha256=cache_manifest,
        resolved=True,
    )


def _user_approved(config: DepConfig, lockfile: Optional[Path]) -> DepResult:
    """Temporary network access for dependency resolution (beta)."""
    # This is the legacy two-stage approach - network ON for prep, then OFF for test
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    
    if (config.repo_path / "requirements.txt").exists():
        _pip_cache_install(config.repo_path, config.cache_dir)
    elif (config.repo_path / "package.json").exists():
        _npm_cache_install(config.repo_path, config.cache_dir)
    elif (config.repo_path / "go.mod").exists():
        _go_cache_install(config.repo_path, config.cache_dir)
    elif (config.repo_path / "Cargo.toml").exists():
        _cargo_cache_install(config.repo_path, config.cache_dir)
    
    cache_manifest = _generate_cache_manifest(config.cache_dir)
    
    return DepResult(
        mode=DepMode.USER_APPROVED,
        network_policy="user-approved-temporary",
        lockfile_sha256=lockfile_sha,
        cache_manifest_sha256=cache_manifest,
        resolved=True,
    )


def _pip_cache_install(repo: Path, cache: Path) -> None:
    subprocess.run([
        "pip", "install", "--no-deps", "--no-build-isolation",
        "--cache-dir", str(cache / "pip"),
        "-r", str(repo / "requirements.txt")
    ], check=True, cwd=repo)


def _npm_cache_install(repo: Path, cache: Path) -> None:
    subprocess.run([
        "npm", "ci", "--cache", str(cache / "npm"), "--offline"
    ], check=True, cwd=repo)


def _go_cache_install(repo: Path, cache: Path) -> None:
    env = {**os.environ, "GOMODCACHE": str(cache / "go")}
    subprocess.run([
        "go", "mod", "download", "-modcacherw"
    ], check=True, cwd=repo, env=env)


def _cargo_cache_install(repo: Path, cache: Path) -> None:
    env = {**os.environ, "CARGO_HOME": str(cache / "cargo")}
    subprocess.run([
        "cargo", "fetch", "--locked"
    ], check=True, cwd=repo, env=env)


def _generate_cache_manifest(cache_dir: Path) -> str:
    """SHA-256 of all cached artifacts."""
    hasher = hashlib.sha256()
    for f in sorted(cache_dir.rglob("*")):
        if f.is_file():
            hasher.update(f.read_bytes())
    return hasher.hexdigest()


def _find_lockfile(repo: Path, explicit: Optional[str]) -> Optional[Path]:
    if explicit and (repo / explicit).exists():
        return repo / explicit
    for name in ["requirements.txt", "package-lock.json", "yarn.lock", 
                 "pnpm-lock.yaml", "go.sum", "Cargo.lock"]:
        p = repo / name
        if p.exists():
            return p
    return None


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()