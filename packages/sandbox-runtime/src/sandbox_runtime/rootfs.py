"""Rootfs extraction and bind mount preparation."""

from __future__ import annotations

import tarfile
import subprocess
import hashlib
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from sandbox_runtime.config import RootfsConfig


@dataclass
class RootfsInfo:
    """Information about extracted rootfs."""
    path: Path
    sha256: str
    size_bytes: int


def extract_rootfs_tarball(tarball_path: Path, dest_dir: Path) -> RootfsInfo:
    """Extract rootfs tarball to destination directory."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # Calculate SHA256 of tarball
    hasher = hashlib.sha256()
    with open(tarball_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    tarball_sha = hasher.hexdigest()
    
    # Extract
    with tarfile.open(tarball_path, "r:gz") as tar:
        tar.extractall(dest_dir)
    
    # Calculate size
    size = sum(f.stat().st_size for f in dest_dir.rglob("*") if f.is_file())
    
    return RootfsInfo(
        path=dest_dir,
        sha256=tarball_sha,
        size_bytes=size
    )


def export_docker_image(image_name: str, output_path: Path) -> Path:
    """Export Docker image to tarball using docker export."""
    # Create a temporary container and export its filesystem
    result = subprocess.run(
        ["docker", "create", "--name", f"workflo-extract-{image_name.replace('/', '-').replace(':', '-')}", image_name],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"docker create failed: {result.stderr}")
    
    container_id = result.stdout.strip()
    
    try:
        with open(output_path, "wb") as f:
            result = subprocess.run(
                ["docker", "export", container_id],
                stdout=f, check=True
            )
    finally:
        subprocess.run(["docker", "rm", "-f", container_id], capture_output=True)
    
    # Compress
    compressed_path = output_path.with_suffix(".tar.gz")
    subprocess.run(["gzip", "-f", str(output_path)], check=True)
    
    return compressed_path


def prepare_rootfs(config: RootfsConfig) -> Path:
    """Prepare rootfs directory structure for bwrap."""
    # Verify base image exists and has required structure
    required = ["/bin", "/lib", "/lib64", "/usr", "/etc"]
    for req in required:
        if not (config.base_image / req.lstrip("/")).exists():
            raise RuntimeError(f"Base image missing {req}")
    
    # Ensure writable dirs exist on host
    for d in [config.workspace_src, config.evidence_src, config.tmp_src, config.home_src]:
        d.mkdir(parents=True, exist_ok=True)
        d.chmod(0o700)
    
    # Create empty home
    (config.home_src / ".bashrc").write_text("")
    
    return config.base_image


def verify_rootfs_isolation(sandbox_pid: int) -> dict:
    """Verify sandbox cannot access host paths via mountinfo."""
    results = {}
    
    forbidden = [
        "/home", "/root", "/var/run/docker.sock", "/run/containerd",
        "/run/user", "/.ssh", "/.aws", "/.config/gcloud", "/.npmrc"
    ]
    
    try:
        with open(f"/proc/{sandbox_pid}/mountinfo") as f:
            mounts = f.read()
            for path in forbidden:
                results[f"no_{path.replace('/', '_').lstrip('_')}"] = path not in mounts
    except Exception:
        results["mountinfo_readable"] = False
    
    return results