"""Project detection for `workflo init`.

Pure filesystem inspection — never executes anything, never mutates.
Maps the detected conventions onto ProjectConfig fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Detection:
    """What we found in a project directory."""
    language: str                        # "nodejs" | "python" | "unknown"
    package_manager: Optional[str]       # pnpm | npm | yarn | uv | poetry | pip
    framework: Optional[str]             # vitest | jest | pytest | playwright | next | express | flask | ...
    test_command: Optional[str]
    start_command: Optional[str]
    port: Optional[int]
    notes: list[str] = field(default_factory=list)

    @property
    def detected(self) -> bool:
        return self.language != "unknown"


_NODE_MANIFEST = "package.json"
_PY_MARKERS = ("pyproject.toml", "requirements.txt", "setup.py", "pytest.ini",
               "tox.ini", "Pipfile")


def detect_project(path: Path) -> Detection:
    """Inspect a project root and return what Workflo found.

    Never modifies anything. Robust on a half-empty directory: returns
    language='unknown' with notes explaining the gap instead of guessing.
    """
    path = Path(path)
    if not path.exists() or not path.is_dir():
        return Detection("unknown", None, None, None, None, None,
                         notes=[f"not a directory: {path}"])

    node = _detect_node(path)
    if node is not None:
        return node
    python = _detect_python(path)
    if python is not None:
        return python
    return Detection("unknown", None, None, None, None, None,
                     notes=["no package.json or Python manifest found"])


# ---------------------------------------------------------------------------

def _detect_node(path: Path) -> Optional[Detection]:
    manifest = path / _NODE_MANIFEST
    if not manifest.exists():
        return None
    try:
        pkg = json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Detection("nodejs", None, None, None, None, None,
                         notes=["package.json unreadable"])

    scripts = pkg.get("scripts", {})
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

    # package manager
    pkg_mgr = None
    for marker, mgr in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"),
                        ("package-lock.json", "npm")):
        if (path / marker).exists():
            pkg_mgr = mgr
            break
    pkg_mgr = pkg_mgr or "npm"

    runner = {"pnpm": "pnpm", "yarn": "yarn", "npm": "npm"}[pkg_mgr]
    run_prefix = {"pnpm": "pnpm", "yarn": "yarn", "npm": "npm run"}[pkg_mgr]

    # framework
    framework = None
    for fw in ("next", "nuxt", "remix", "astro", "svelte",
               "express", "fastify", "koa", "nestjs"):
        if fw in deps:
            framework = fw
            break

    # test framework + command
    test_fw = None
    test_cmd = None
    if "vitest" in deps:
        test_fw = "vitest"
    elif "jest" in deps:
        test_fw = "jest"
    elif "mocha" in deps:
        test_fw = "mocha"
    if "@playwright/test" in deps:
        test_fw = f"{test_fw or 'playwright'}"
    if test_fw:
        test_cmd = scripts.get("test", f"{runner} run test" if pkg_mgr != "npm" else "npm test")
    elif scripts.get("test"):
        test_cmd = f"{run_prefix} test"

    # start command + port
    start_cmd = None
    port = None
    for name in ("start", "dev", "serve"):
        if scripts.get(name):
            start_cmd = f"{run_prefix} {name}"
            break
    engine_port = _guess_node_port(path, scripts, deps)
    if engine_port:
        port = engine_port

    return Detection("nodejs", pkg_mgr, framework, test_cmd, start_cmd, port)


def _guess_node_port(path: Path, scripts: dict, deps: dict) -> Optional[int]:
    # Common framework defaults. We prefer an explicit .env/PORT if present.
    env = path / ".env"
    if env.exists():
        try:
            for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("PORT="):
                    return int(line.split("=", 1)[1].strip().strip('"\''))
        except (OSError, ValueError):
            pass
    if "next" in deps:
        return 3000
    if "vite" in deps or "vitest" in deps:
        return 5173
    if "remix" in deps:
        return 3000
    if scripts.get("dev") and "vite" not in deps:
        return 3000
    return 3000 if any(s in scripts for s in ("dev", "start", "serve")) else None


# ---------------------------------------------------------------------------

def _detect_python(path: Path) -> Optional[Detection]:
    for marker in _PY_MARKERS:
        if not (path / marker).exists():
            continue
        break
    else:
        return None

    # package manager
    pkg_mgr = None
    if (path / "pyproject.toml").exists():
        content = (path / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
        if "[tool.poetry]" in content:
            pkg_mgr = "poetry"
        elif "uv" in content:
            pkg_mgr = "uv"
        else:
            pkg_mgr = "pip"
    elif (path / "Pipfile").exists():
        pkg_mgr = "pip"
    elif (path / "requirements.txt").exists():
        pkg_mgr = "pip"
    pkg_mgr = pkg_mgr or "pip"

    # framework: flask/django/fastapi/express=none
    framework = None
    manifests = " ".join(
        (path / m).read_text(encoding="utf-8", errors="ignore").lower()
        for m in ("requirements.txt", "pyproject.toml") if (path / m).exists()
    )
    for fw in ("fastapi", "django", "flask", "starlette"):
        if fw in manifests:
            framework = fw
            break

    # test framework + command
    test_fw = None
    test_cmd = None
    if (path / "pytest.ini").exists() or "pytest" in manifests:
        test_fw = "pytest"
        test_cmd = "pytest"
    elif (path / "tests").is_dir():
        test_fw = "pytest"
        test_cmd = "pytest"

    # start command + port
    start_cmd = None
    port = None
    if framework == "fastapi":
        start_cmd = "uvicorn app:app --host 0.0.0.0 --port 8000"
        port = 8000
    elif framework == "flask":
        start_cmd = "flask run --host 0.0.0.0 --port 5000"
        port = 5000
    elif framework == "django":
        start_cmd = "python manage.py runserver 0.0.0.0:8000"
        port = 8000

    return Detection("python", pkg_mgr, framework, test_cmd, start_cmd, port)


# ---------------------------------------------------------------------------

def config_for_detection(det: Detection):
    """Translate a Detection into a ProjectConfig."""
    from workflo_utils.project_config import ProjectConfig

    cfg = ProjectConfig()
    cfg.name = ""
    cfg.test_command = det.test_command or "pytest"
    cfg.start_command = det.start_command or ""
    cfg.start_port = det.port or 0
    return cfg
