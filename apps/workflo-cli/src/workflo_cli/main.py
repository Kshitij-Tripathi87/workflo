"""Main CLI entrypoint — `workflo run`, `workflo verify`, `workflo keygen`.

Uses Click for the command framework. The CLI is intentionally thin —
it builds a SandboxSpec, calls SandboxExecutor.run(), and prints the result.
All the heavy lifting is in the executor + probe engine.

Flag design:
  --test            Surface: repo's native pytest + basic smoke
  --deep-test       Deep: + LLM-generated edge cases, API contracts
  --aggressive-test Aggressive: + fuzz, property-based, chaos
  --security        Security: tenant isolation, network isolation, canary

  These are COMPOSABLE — combine any functional tier with --security.
  Only one functional tier may be selected at a time.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

import click

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from workflo_schema.sandbox import SandboxSpec

from workflo_executor import SandboxExecutor
from workflo_executor.executor import generate_sandbox_id
from sandbox_isolation import generate_keypair, verify_receipt_signature

# Auth commands
from workflo_cli.auth_commands import (
    auth_group,
    login_alias,
    logout_alias,
    org_group,
    workspace_group,
)

# Hard limits to prevent DoS / abuse
MAX_RECEIPT_BYTES = 10 * 1024 * 1024   # 10 MB
MAX_OUTPUT_BYTES = 100 * 1024 * 1024   # 100 MB
MAX_CONFIG_BYTES = 1024 * 1024          # 1 MB
MAX_REPO_URL_LEN = 2048
MAX_COMMIT_SHA_LEN = 64

# Config file recognized keys (CLI flag names, not Python identifiers)
_CONFIG_KEYS = {
    "repo", "path", "test", "deep_test", "aggressive_test", "security", "web", "publish",
    "start_command", "port", "commit_sha", "output", "worker_image",
    "deep_worker_image", "web_worker_image", "timeout", "memory", "cpu",
    "pubkey", "force", "dry_run", "via_api", "api_key",
}

# Repo URL must look like an http(s), git, or ssh URL.
# `file://` is ALSO allowed for local fixture testing in development — there's
# no risk of leaking customer code via file:// (the URL can only point at the
# host's filesystem, and the executor still clones into a tmpfs that gets
# unmounted post-run), and it lets us validate integration against local
# test repos without standing up a git HTTP server.
_REPO_URL_RE = re.compile(r"^(https?://|git@|git://|ssh://|file://).+", re.IGNORECASE)
# Commit SHA must be hex (allow full SHA, short SHA, or branch-like refs).
_COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{1,64}$|^[A-Za-z0-9._/\-]{1,200}$")


def _validate_repo_url(url: str) -> str:
    """Strip and validate repo URL. Raises click.BadParameter on invalid input."""
    url = url.strip()
    if not url:
        raise click.BadParameter("Repo URL must not be empty")
    if len(url) > MAX_REPO_URL_LEN:
        raise click.BadParameter(f"Repo URL too long ({len(url)} > {MAX_REPO_URL_LEN})")
    if not _REPO_URL_RE.match(url):
        raise click.BadParameter(
            "Repo URL must start with https://, http://, git@, git://, or ssh://"
        )
    return url


def _validate_commit_sha(sha: Optional[str]) -> Optional[str]:
    """Validate commit SHA / ref format."""
    if sha is None:
        return None
    sha = sha.strip()
    if not sha:
        return None
    if len(sha) > MAX_COMMIT_SHA_LEN:
        raise click.BadParameter(f"Commit SHA too long ({len(sha)} > {MAX_COMMIT_SHA_LEN})")
    if not _COMMIT_SHA_RE.match(sha):
        raise click.BadParameter(
            f"Invalid commit SHA format: {sha!r}. "
            "Use hex chars or a valid ref name."
        )
    return sha


def _validate_local_path(path: str) -> str:
    """Validate a local directory path for --path input.

    Resolves to absolute, verifies the path exists and is a directory. We
    allow any characters in the resolved path (it's host-side, not a
    Docker argv element), but reject obviously dangerous input before
    resolving — a hostile path with shell metacharacters shouldn't make
    it to the executor at all.
    """
    path = path.strip()
    if not path:
        raise click.BadParameter("--path must not be empty")
    # Reject control characters and shell-metachar-ish bytes before resolving.
    if any(c in path for c in ["\x00", "\n", "\r"]):
        raise click.BadParameter("--path contains forbidden characters (NUL/newline)")
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise click.BadParameter(f"--path does not exist: {resolved}")
    if not resolved.is_dir():
        raise click.BadParameter(f"--path is not a directory: {resolved}")
    return str(resolved)


# Same conservative manifest set the executor uses for two-stage install.
# Kept in sync intentionally: a manifest the CLI detects is the same one
# the executor will try to install from.
_PACKAGE_MANIFESTS = (
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "package.json",
    "go.mod",
    "Cargo.toml",
)


def _path_has_package_manifest(path: str) -> bool:
    """Return True if the local directory has a recognized package manifest.

    Drives the CLI's two-stage-flow gate: when --path points at a directory
    with one of these manifests, dependency_install=True and the executor
    runs Stage 1 (networked prep) before Stage 2 (sealed test). When no
    manifest is present, the run stays single-stage sealed — no install
    needed → no networked prep stage → no `dependency_install_had_network`
    claim on the receipt.
    """
    repo_path = Path(path)
    return any((repo_path / name).is_file() for name in _PACKAGE_MANIFESTS)


def _load_config_file(path: str) -> dict[str, Any]:
    """Load a YAML or JSON config file and validate its keys.

    Recognized keys match CLI flag names (with underscores instead of hyphens).
    Unknown keys raise an error to catch typos early.
    """
    config_path = Path(path).resolve()
    if not config_path.exists():
        raise click.BadParameter(f"Config file not found: {config_path}")

    try:
        raw = _safe_read_text(config_path, MAX_CONFIG_BYTES)
    except (OSError, UnicodeDecodeError) as e:
        raise click.BadParameter(f"Cannot read config file: {e}")

    ext = config_path.suffix.lower()
    if ext in (".yaml", ".yml"):
        if yaml is None:
            raise click.BadParameter(
                "YAML config requires PyYAML. Install with: pip install pyyaml"
            )
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise click.BadParameter(f"Invalid YAML in config: {e}")
    elif ext == ".json":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise click.BadParameter(f"Invalid JSON in config: {e}")
    else:
        raise click.BadParameter(
            f"Config file must be .yaml, .yml, or .json (got {ext!r})"
        )

    if not isinstance(data, dict):
        raise click.BadParameter(
            f"Config root must be a mapping/object, got {type(data).__name__}"
        )

    # Normalize keys: hyphens → underscores so `deep-test` and `deep_test` both work
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        norm_key = key.replace("-", "_")
        if norm_key not in _CONFIG_KEYS:
            raise click.BadParameter(
                f"Unknown config key: {key!r}. "
                f"Recognized: {sorted(_CONFIG_KEYS)}"
            )
        normalized[norm_key] = value

    return normalized


def _safe_read_text(path: Path, max_bytes: int) -> str:
    """Read a text file with a hard size limit. Raises on overflow."""
    size = path.stat().st_size
    if size > max_bytes:
        raise click.BadParameter(
            f"File too large: {size} bytes (max {max_bytes})"
        )
    return path.read_text(encoding="utf-8")


def _load_ed25519_pubkey(path: Path) -> Ed25519PublicKey:
    """Load and validate an Ed25519 public key from PEM file.

    Raises click.BadParameter on any failure with a clear message.
    Does NOT trust a key that's the wrong type.
    """
    try:
        data = _safe_read_text(path, 4096)
    except (OSError, UnicodeDecodeError) as e:
        raise click.BadParameter(f"Cannot read pubkey file: {e}")

    try:
        key = serialization.load_pem_public_key(data.encode("utf-8"))
    except ValueError as e:
        raise click.BadParameter(f"Invalid PEM format: {e}")

    if not isinstance(key, Ed25519PublicKey):
        raise click.BadParameter(
            f"Pubkey must be Ed25519, got {type(key).__name__}. "
            f"workflo uses Ed25519 signatures exclusively."
        )

    return key


def _load_ed25519_pubkey_from_string(pem: str) -> Ed25519PublicKey:
    """Load and validate an Ed25519 public key from a PEM string.

    Same validation as _load_ed25519_pubkey but takes a string instead
    of a file path. Used when the control plane returns the key inline.
    """
    try:
        key = serialization.load_pem_public_key(pem.encode("utf-8"))
    except ValueError as e:
        raise click.BadParameter(f"Invalid PEM format: {e}")

    if not isinstance(key, Ed25519PublicKey):
        raise click.BadParameter(
            f"Pubkey must be Ed25519, got {type(key).__name__}. "
            f"workflo uses Ed25519 signatures exclusively."
        )

    return key


def _confirm_overwrite(path: Path) -> None:
    """Confirm before overwriting an existing file."""
    if path.exists():
        if not click.confirm(
            f"File {path} already exists. Overwrite?", default=False
        ):
            raise click.Abort()


def _internal_to_public_probe_groups(internal: list[str]) -> list[str]:
    """Translate CLI/internal probe-group names to the public contract names.

    The CLI internally uses the executor's vocabulary (surface, deep,
    aggressive, security, web); the frozen REST contract speaks the public
    vocabulary (test, deep-test, aggressive-test, security, web). The
    control-plane translates public -> internal server-side, so the CLI
    must send public names.
    """
    return [
        {
            "surface": "test",
            "deep": "deep-test",
            "aggressive": "aggressive-test",
        }.get(g, g)
        for g in internal
    ]


def _read_cli_workflo_yaml(repo_url: str) -> tuple[Optional[str], Optional[int]]:
    """Best-effort read of the target repo's workflo.yaml `web:` or `security:` section.

    Only works for `file://` repos — for remote URLs the yaml is read
    INSIDE the container after the clone (worker-side resolve_web_config / resolve_security_config).
    This gives the CLI a local pre-flight fail-fast for dev/test repos
    while remote runs still get a clean worker-side failure.

    Returns (start_command, port), either may be None when absent.
    """
    if not repo_url.lower().startswith("file://"):
        return None, None
    repo_dir = Path(repo_url[len("file://"):])
    for name in ("workflo.yaml", "workflo.yml"):
        path = repo_dir / name
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            # Check security section first, then fall back to web
            for section_name in ("security", "web"):
                if isinstance(data.get(section_name), dict):
                    section = data[section_name]
                    return section.get("start_command"), section.get("port")
    return None, None


@click.group()
@click.version_option(version="0.1.0", prog_name="workflo")
def cli():
    """workflo - sandboxed code-testing agent that verifies specific claims.

    Commands:
      run           Execute sandboxed tests against a repo
      verify        Verify a receipt's Ed25519 signature (Claim #4)
      keygen        Generate Ed25519 keypair for receipt signing
      auth          Authentication and profile management
      login         Authenticate via device flow (alias for auth login)
      logout        Log out and revoke tokens (alias for auth logout)
      org           Organization management
      workspace     Workspace management
    """


# Register auth-related command groups and aliases
cli.add_command(auth_group)
cli.add_command(login_alias, name="login")
cli.add_command(logout_alias, name="logout")
cli.add_command(org_group)
cli.add_command(workspace_group)


@cli.command()
@click.option("--repo", default=None, help="Git repository URL to test")
@click.option("--path", "repo_path", default=None,
              help="Local directory to test (mutually exclusive with --repo). "
                   "If a package manifest is detected (requirements.txt, package.json, etc.), "
                   "a networked prep stage runs to install dependencies before the sealed test stage.")
@click.option("--test", "surface", is_flag=True, default=None, help="Surface tests: native pytest + basic smoke")
@click.option("--deep-test", "deep", is_flag=True, default=None, help="Deep tests: + generated edge cases, API contracts")
@click.option("--aggressive-test", "aggressive", is_flag=True, default=None, help="Aggressive tests: + fuzz, property-based, chaos")
@click.option("--security", is_flag=True, default=None, help="Security: tenant isolation, network isolation, canary")
@click.option("--web", is_flag=True, default=None, help="Web tier: run Playwright browser probes against a running app")
@click.option("--publish", is_flag=True, default=None, help="Publish results to Cortex cloud (requires auth)")
@click.option("--start-command", default=None,
              help="Command that starts the app under test (web tier). Shell-free; auto-start + port-wait.")
@click.option("--port", default=None, type=int,
              help="Port the app under test binds (web tier). Waited-on before browser probes run.")
@click.option("--commit-sha", default=None, help="Pin a specific commit (default: HEAD)")
@click.option("--output", "-o", default=None, help="Write the result JSON to a file")
@click.option(
    "--worker-image", default=None,
    help="Docker image for the sandbox worker (default: workflo-worker:latest)",
)
@click.option(
    "--deep-worker-image", default=None,
    help=(
        "Docker image for the model-bearing worker used by --deep-test / --aggressive-test. "
        "Auto-selected when those flags are set; --worker-image is for plain --test/--security. "
        "(default: workflo-worker-deep:latest)"
    ),
)
@click.option(
    "--web-worker-image", default=None,
    help=(
        "Docker image for the Playwright-bearing worker used by --web. "
        "Auto-selected when --web is set. (default: workflo-worker-web:latest)"
    ),
)
@click.option("--timeout", default=None, type=int, help="Sandbox timeout in seconds (default: 600)")
@click.option("--memory", default=None, type=int, help="Memory limit in MB (default: 2048)")
@click.option("--cpu", default=None, type=float, help="CPU core limit (default: 2.0)")
@click.option("--pubkey", default=None, help="Path to public key PEM for receipt verification")
@click.option("--force", is_flag=True, default=False, help="Overwrite output file if it exists")
@click.option("--via-api", "via_api", default=None,
              help="Base URL of a control-plane API (e.g. http://localhost:8000). "
                   "Round-trips through the frozen REST contract instead of running locally.")
@click.option("--api-key", default=None,
              help="API key for --via-api (X-API-Key header). If omitted, requests a demo token.")
@click.option("--dry-run", "--plan-only", "dry_run", is_flag=True, default=False,
              help="Validate and print what would run, then exit 0 — no Docker, no clone")
@click.option("--config", "config_path", default=None,
              help="Load defaults from a YAML or JSON config file (CLI flags override)")
def run(
    repo, repo_path, surface, deep, aggressive, security, web, publish, start_command, port,
    commit_sha, output, worker_image, deep_worker_image, web_worker_image,
    timeout, memory, cpu, pubkey, force, dry_run, config_path, via_api, api_key,
):
    """Run the sandbox pipeline against a repo.

    Probe groups are COMPOSABLE - combine any:
      --test            Surface: repo's pytest + basic smoke
      --deep-test       Deep: + generated edge cases, API contracts
      --aggressive-test Aggressive: + fuzz, property-based, chaos
      --security        Security: tenant isolation, network canary, teardown proof (needs --start-command/--port)
      --web             Web: Playwright browser probes (needs --start-command/--port)
      --publish         Publish results to Cortex cloud (requires `workflo auth login`)

    Only one functional tier (--test / --deep-test / --aggressive-test) may
    be selected. --security is independent and composable.

    --deep-test / --aggressive-test auto-select the model-bearing worker image
    (`workflo-worker-deep:latest` by default) so the base image stays small
    and fast. Override with --deep-worker-image.

    --web auto-selects the Playwright-bearing worker image
    (`workflo-worker-web:latest` by default). Override with --web-worker-image.

    --dry-run validates everything and prints the plan without touching Docker.
    --config loads defaults from a file; explicit CLI flags override file values.

    Examples:
      workflo run --repo https://github.com/psf/requests.git --test
      workflo run --repo https://github.com/psf/requests.git --test --security \
          --start-command "python app.py" --port 5000
      workflo run --repo https://github.com/psf/requests.git --deep-test
      workflo run --repo https://github.com/psf/requests.git --web \
          --start-command "python app.py" --port 5000
      workflo run --repo https://github.com/psf/requests.git --test --publish
      workflo run --config workflo.yaml --dry-run
      workflo run --config workflo.yaml --test --force
    """

    # --- 1. Load config file (if specified), then overlay CLI flags ---
    cfg: dict[str, Any] = {}
    if config_path:
        cfg = _load_config_file(config_path)

    # Helper: CLI flag wins over config file, config wins over built-in default
    def merge(cli_val: Any, cfg_key: str, default: Any = None) -> Any:
        if cli_val is not None:
            return cli_val
        if cfg_key in cfg:
            return cfg[cfg_key]
        return default

    repo = merge(repo, "repo")
    repo_path = merge(repo_path, "path")
    surface = merge(surface, "test", False)
    deep = merge(deep, "deep_test", False)
    aggressive = merge(aggressive, "aggressive_test", False)
    security = merge(security, "security", False)
    web = merge(web, "web", False)
    publish = merge(publish, "publish", False)
    start_command = merge(start_command, "start_command")
    port = merge(port, "port")
    commit_sha = merge(commit_sha, "commit_sha")
    output = merge(output, "output")
    worker_image = merge(worker_image, "worker_image", "workflo-worker:latest")
    # The deep image has NO default here: we leave it None so the executor
    # can resolve to DEFAULT_DEEP_WORKER_IMAGE only when a deep-tier run is
    # actually requested. We surface it in the plan either way (resolved or
    # default) so a reviewer can see what image a deep-test run would use.
    deep_worker_image = merge(deep_worker_image, "deep_worker_image", None)
    web_worker_image = merge(web_worker_image, "web_worker_image", None)
    timeout = merge(timeout, "timeout", 600)
    memory = merge(memory, "memory", 2048)
    cpu = merge(cpu, "cpu", 2.0)
    force = merge(force, "force", False)
    via_api = merge(via_api, "via_api")
    api_key = merge(api_key, "api_key")

    # --- 2. Validate inputs FIRST - fail fast before any expensive work ---
    if repo and repo_path:
        raise click.BadParameter(
            "--repo and --path are mutually exclusive: choose one input source. "
            "--repo for a git URL, --path for a local directory."
        )
    if not repo and not repo_path:
        raise click.BadParameter(
            "Either --repo <url> or --path <local-dir> is required "
            "(or provide one in a config file)."
        )
    if repo_path:
        repo_path = _validate_local_path(repo_path)
        # --path implies no commit_sha (commit is only meaningful for git clones)
        if commit_sha:
            raise click.BadParameter(
                "--commit-sha cannot be combined with --path "
                "(commit_sha is only meaningful for git URL inputs)"
            )
    else:
        repo = _validate_repo_url(repo)
    commit_sha = _validate_commit_sha(commit_sha)

    # Validate worker-image name (defense in depth)
    if not re.match(r"^[A-Za-z0-9._:/\-@]+$", worker_image):
        raise click.BadParameter(
            f"Invalid worker-image: {worker_image!r}. "
            "Only alphanumeric, '.', '_', ':', '/', '-', '@' allowed."
        )

    # Same validation for --deep-worker-image (if provided). An invalid deep
    # image name is a config bug; the CLI must fail fast rather than let the
    # docker create call reject it later inside the sandbox run (where the
    # failure surface is messier).
    if deep_worker_image is not None:
        if not re.match(r"^[A-Za-z0-9._:/\-@]+$", deep_worker_image):
            raise click.BadParameter(
                f"Invalid deep-worker-image: {deep_worker_image!r}. "
                "Only alphanumeric, '.', '_', ':', '/', '-', '@' allowed."
            )

    # Same validation for --web-worker-image (if provided).
    if web_worker_image is not None:
        if not re.match(r"^[A-Za-z0-9._:/\-@]+$", web_worker_image):
            raise click.BadParameter(
                f"Invalid web-worker-image: {web_worker_image!r}. "
                "Only alphanumeric, '.', '_', ':', '/', '-', '@' allowed."
            )

    # Validate ranges explicitly for clearer errors than Pydantic's defaults
    try:
        timeout = int(timeout)
        memory = int(memory)
        cpu = float(cpu)
    except (ValueError, TypeError) as e:
        raise click.BadParameter(f"Invalid numeric argument: {e}")

    if not (10 <= timeout <= 3600):
        raise click.BadParameter("timeout must be 10..3600 seconds")
    if not (256 <= memory <= 16384):
        raise click.BadParameter("memory must be 256..16384 MB")
    if not (0.5 <= cpu <= 8.0):
        raise click.BadParameter("cpu must be 0.5..8.0 cores")

    # --- 3. Build probe groups from flags ---
    probe_groups = []
    functional_tiers = []

    if surface:
        functional_tiers.append("surface")
    if deep:
        functional_tiers.append("deep")
    if aggressive:
        functional_tiers.append("aggressive")

    if len(functional_tiers) > 1:
        raise click.UsageError(
            "Only one functional tier allowed: choose one of --test, --deep-test, --aggressive-test"
        )
    if not functional_tiers and not security and not web:
        raise click.UsageError(
            "At least one probe group required: --test, --deep-test, --aggressive-test, --security, or --web"
        )

    # Fail fast for the web tier: a web run WITHOUT app-start config would
    # burn a full sandbox cycle just to report "start_command missing" from
    # inside the container. Validate the config HERE, pre-Docker, and also
    # resolve it from the target repo's workflo.yaml if the flags are absent.
    if web and not (start_command and port):
        yaml_start, yaml_port = _read_cli_workflo_yaml(repo)
        start_command = start_command or yaml_start
        port = port or yaml_port

    if web:
        missing = []
        if not start_command:
            missing.append("start_command")
        if not port:
            missing.append("port")
        if missing:
            flag_names = ", ".join("--" + m.replace("_", "-") for m in missing)
            raise click.UsageError(
                f"--web requires {flag_names}: "
                f"provide them on the command line, in the config file, or via the "
                f"repo's workflo.yaml:\n"
                f"  web:\n"
                f"    start_command: <cmd>\n"
                f"    port: <n>"
            )
        try:
            port = int(port)
        except (ValueError, TypeError):
            raise click.BadParameter(f"web port is not an integer: {port!r}")
        if not (1 <= port <= 65535):
            raise click.BadParameter(f"web port out of range: {port}")

    # Fail fast for the security tier: same rationale as web — a security run
    # without app-start config would burn a full sandbox cycle. Reuse the same
    # --start-command/--port flags (and workflo.yaml web: section as fallback)
    # since the security tier boots the same app-under-test.
    if security and not (start_command and port):
        yaml_start, yaml_port = _read_cli_workflo_yaml(repo)
        start_command = start_command or yaml_start
        port = port or yaml_port

    if security:
        missing = []
        if not start_command:
            missing.append("start_command")
        if not port:
            missing.append("port")
        if missing:
            flag_names = ", ".join("--" + m.replace("_", "-") for m in missing)
            raise click.UsageError(
                f"--security requires {flag_names}: "
                f"provide them on the command line, in the config file, or via the "
                f"repo's workflo.yaml (web: or security: section):\n"
                f"  security:\n"
                f"    start_command: <cmd>\n"
                f"    port: <n>\n"
                f"  # or reuse web config:\n"
                f"  web:\n"
                f"    start_command: <cmd>\n"
                f"    port: <n>"
            )
        try:
            port = int(port)
        except (ValueError, TypeError):
            raise click.BadParameter(f"security port is not an integer: {port!r}")
        if not (1 <= port <= 65535):
            raise click.BadParameter(f"security port out of range: {port}")

    # Auth gate: every `workflo run` (including --dry-run and --via-api) requires
    # authentication. Fail fast BEFORE any tmpfs mount, Docker create, or HTTP
    # round-trip — an unauthenticated user should not watch sandbox setup start
    # only to fail later. This is independent of --publish: publishing is an
    # additional optional feature, but every run needs to be attributable to a
    # logged-in user. Note: this only gates IDENTITY, not data egress — the
    # "code never leaves your machine" privacy claim is unaffected.
    try:
        from cortex_auth.session import AuthSession
        from cortex_auth.scopes import WORKFLO_SCOPES, PRODUCT_CLIENT_IDS
        auth_session = AuthSession(
            product="workflo",
            client_id=PRODUCT_CLIENT_IDS["workflo"],
            base_url=os.environ.get("WORKFLO_AUTH_BASE_URL", "http://localhost:3001"),
            scopes=WORKFLO_SCOPES,
        )
        if auth_session.status() is None:
            click.echo(
                "Not authenticated. Run `workflo auth login` first.",
                err=True,
            )
            sys.exit(1)
    except SystemExit:
        raise
    except Exception:
        # If credential store is unreadable or auth status can't be determined,
        # treat as unauthenticated rather than letting the run proceed with an
        # unknown identity state.
        click.echo(
            "Not authenticated. Run `workflo auth login` first.",
            err=True,
        )
        sys.exit(1)

    # --publish requires authentication (local-first: auth is mandatory for --publish)
    if publish:
        try:
            from cortex_auth.session import AuthSession
            from cortex_auth.scopes import WORKFLO_SCOPES, PRODUCT_CLIENT_IDS
            auth_session = AuthSession(
                product="workflo",
                client_id=PRODUCT_CLIENT_IDS["workflo"],
                base_url=os.environ.get("WORKFLO_AUTH_BASE_URL", "http://localhost:3001"),
                scopes=WORKFLO_SCOPES,
            )
            if auth_session.status() is None:
                raise click.UsageError(
                    "--publish requires authentication. Run `workflo auth login` first."
                )
        except Exception as e:
            if isinstance(e, click.UsageError):
                raise
            raise click.UsageError(
                "--publish requires authentication. Run `workflo auth login` first."
            )

    probe_groups.extend(functional_tiers)
    if security:
        probe_groups.append("security")
    if web:
        probe_groups.append("web")

    # --- 4. Validate output path safety ---
    output_path: Optional[Path] = None
    if output:
        output_path = Path(output).resolve()
        if not force:
            _confirm_overwrite(output_path)

    sandbox_id = generate_sandbox_id()

    # Web-tier and security-tier config flows to the container via env vars
    # (the executor forwards spec.run_spec["env"] into the container env
    # verbatim). The worker's resolve_web_config / resolve_security_config
    # reads these; workflo.yaml in the repo is only a fallback for config
    # NOT passed at the CLI.
    run_env: dict[str, str] = {}
    if web:
        run_env["WORKFLO_START_COMMAND"] = str(start_command)
        run_env["WORKFLO_WEB_PORT"] = str(port)
    if security:
        run_env["WORKFLO_SECURITY_START_COMMAND"] = str(start_command)
        run_env["WORKFLO_SECURITY_PORT"] = str(port)

    run_spec = {
        "goal": "security" if security else "functional",
        # NOTE: `markers` here are workflo's internal probe tiers (surface/deep/etc.)
        # and are NOT passed through to pytest -m. Passing them as pytest markers
        # would deselect any test that doesn't bear an explicit `@pytest.mark.surface`
        # decorator — which is every test in a typical repo. The worker engine
        # treats `markers` as the probe-group identification only; pytest runs
        # the repo's whole suite unfiltered for surface tests.
        "markers": probe_groups,
        "probe_groups": probe_groups,
        "env": run_env,
    }

    # Two-stage flow gate: when --path is used AND a package manifest is
    # detected, set dependency_install=True so the executor runs Stage 1
    # (networked prep) before Stage 2 (sealed test). For plain --repo runs
    # we keep the single-stage-after-clone flow — git clone already pulls
    # the repo's source, and most repos don't need a separate install step
    # beyond that. Plain --path runs without a manifest also stay
    # single-stage (no install needed → no networked prep).
    dependency_install = False
    if repo_path:
        dependency_install = _path_has_package_manifest(repo_path)

    try:
        spec = SandboxSpec(
            sandbox_id=sandbox_id,
            repo_url=repo or "",
            repo_path=repo_path,
            commit_sha=commit_sha,
            run_spec=run_spec,
            timeout_seconds=timeout,
            memory_mb=memory,
            cpu_cores=cpu,
            dependency_install=dependency_install,
        )
    except Exception as e:
        raise click.BadParameter(f"Invalid spec: {e}")

    # Resolve which worker image this run will use. The executor is the
    # source of truth at run time (see SandboxExecutor.select_worker_image),
    # but the CLI also needs the answer for the dry-run plan and for the
    # stderr banner — we mirror the same rule here so the printed plan
    # matches what the executor would actually do.
    from workflo_executor.executor import (
        DEFAULT_DEEP_WORKER_IMAGE,
        DEFAULT_WEB_WORKER_IMAGE,
        _DEEP_PROBE_GROUPS,
        _WEB_PROBE_GROUPS,
    )
    needs_deep_image = bool(set(probe_groups) & _DEEP_PROBE_GROUPS)
    needs_web_image = bool(set(probe_groups) & _WEB_PROBE_GROUPS)
    if needs_deep_image and needs_web_image:
        raise click.UsageError(
            "Combining a deep tier (--deep-test/--aggressive-test) with --web "
            "is not supported yet: the combined worker image "
            "(workflo-worker-deep-web:latest) has not been built. "
            "Choose one tier for this run."
        )
    if needs_deep_image:
        selected_worker_image = deep_worker_image or DEFAULT_DEEP_WORKER_IMAGE
    elif needs_web_image:
        selected_worker_image = web_worker_image or DEFAULT_WEB_WORKER_IMAGE
    else:
        selected_worker_image = worker_image

    # --- 5. Dry-run: print the plan and exit 0 (no Docker, no clone) ---
    if dry_run:
        plan = {
            "mode": "dry-run",
            "sandbox_id": sandbox_id,
            "repo": repo,
            "repo_path": repo_path,
            "commit_sha": commit_sha,
            "probe_groups": probe_groups,
            # Surface BOTH images and the auto-switch decision so a reviewer
            # can see what was configured AND what was selected. The selected
            # image is the one that would actually be passed to `docker create`.
            "worker_image": worker_image,
            "deep_worker_image": deep_worker_image,
            "web_worker_image": web_worker_image,
            # `selected_worker_image` is the resolved image for this run. For
            # --deep-test/--aggressive-test, this is the deep image (the model-
            # bearing one). For --web, this is the web image (the Playwright
            # one). For --test/--security, this is the surface image.
            "selected_worker_image": selected_worker_image,
            # Two-stage flow flag — when True, the executor runs Stage 1
            # (networked prep to install dependencies) before Stage 2
            # (sealed test, network=none). The reviewer sees this in the
            # plan AND in the receipt's dependency_install_had_network.
            "dependency_install": dependency_install,
            "web_config": {
                "start_command": start_command,
                "port": port,
            } if web else None,
            "security_config": {
                "start_command": start_command,
                "port": port,
            } if security else None,
            "publish": publish,
            "timeout_seconds": timeout,
            "memory_mb": memory,
            "cpu_cores": cpu,
            "output": str(output_path) if output_path else None,
            "spec_valid": True,
        }
        click.echo(json.dumps(plan, indent=2, sort_keys=True))
        sys.exit(0)

    # --- 6. Via-API run: round-trip through the frozen REST contract ---
    if via_api:
        _run_via_api(
            via_api=via_api,
            api_key=api_key,
            repo=repo,
            probe_groups=probe_groups,
            commit_sha=commit_sha,
            start_command=start_command,
            port=port,
            timeout=timeout,
            memory=memory,
            cpu=cpu,
            output_path=output_path,
        )

    # --- 7. Real run ---
    signer = generate_keypair()

    click.echo(f"Sandbox ID: {sandbox_id}", err=True)
    click.echo(f"Repo: {repo}", err=True)
    if commit_sha:
        click.echo(f"Commit: {commit_sha}", err=True)
    click.echo(f"Probe groups: {', '.join(probe_groups)}", err=True)
    # The banner prints both images when a deep-tier run was requested, so a
    # reviewer watching stderr sees the auto-switch happen explicitly.
    click.echo(f"Worker image: {worker_image}", err=True)
    if needs_deep_image:
        click.echo(f"Deep worker image (selected): {selected_worker_image}", err=True)
    if needs_web_image:
        click.echo(f"Web worker image (selected): {selected_worker_image}", err=True)
        click.echo(
            f"Web config: start_command={start_command!r} port={port}",
            err=True,
        )
    if security:
        click.echo(
            f"Security config: start_command={start_command!r} port={port}",
            err=True,
        )
    click.echo(f"Public key fingerprint: {signer.public_key_fingerprint}", err=True)
    click.echo("Starting sandbox run...", err=True)

    # Pass ALL THREE images to the executor — it picks the right one based on
    # the spec's probe groups (the executor is the single source of truth at
    # run time, so the CLI's banner choice and the executor's choice can't
    # drift).
    executor = SandboxExecutor(
        worker_image=worker_image,
        deep_worker_image=deep_worker_image,
        web_worker_image=web_worker_image,
        signer=signer,
    )

    try:
        result = executor.run(spec)
    except KeyboardInterrupt:
        click.echo("Interrupted - sandbox may not be fully torn down.", err=True)
        sys.exit(130)
    except Exception as e:
        click.echo(f"Executor error: {type(e).__name__}: {e}", err=True)
        sys.exit(2)

    click.echo(f"Run complete: {'SUCCESS' if result.success else 'FAILURE'}", err=True)
    click.echo(f"  Tests: {result.report.passed}/{result.report.total} passed", err=True)
    click.echo(f"  Container removed: {result.receipt.teardown_proof.container_removed}", err=True)
    click.echo(f"  Filesystem removed: {result.receipt.teardown_proof.filesystem_removed}", err=True)
    click.echo(f"  Canary passed (egress blocked): {not result.receipt.canary_check.request_succeeded}", err=True)
    click.echo(f"  Receipt signature: {result.receipt.signature[:16] if result.receipt.signature else 'NONE'}...", err=True)

    output_json = result.to_json()

    if output_path:
        if len(output_json.encode("utf-8")) > MAX_OUTPUT_BYTES:
            click.echo(f"Output too large ({MAX_OUTPUT_BYTES} byte limit)", err=True)
            sys.exit(1)
        try:
            output_path.write_text(output_json, encoding="utf-8")
            click.echo(f"Report written to {output_path}", err=True)
        except OSError as e:
            click.echo(f"Failed to write report to {output_path}: {e}", err=True)
            sys.exit(1)
    else:
        click.echo(output_json)

    sys.exit(0 if result.success else 1)


def _run_via_api(
    via_api: str,
    api_key: Optional[str],
    repo: str,
    probe_groups: list[str],
    commit_sha: Optional[str],
    start_command: Optional[str],
    port: Optional[int],
    timeout: int,
    memory: int,
    cpu: float,
    output_path: Optional[Path],
) -> None:
    """Round-trip a run through the frozen REST contract (docs/api_contract.md).

    Flow:
      1. (no --api-key) POST /v1/auth/demo-token to obtain the demo key
      2. POST /v1/runs with a RunRequest (public probe-group names)
      3. Poll GET /v1/runs/{run_id} until terminal (completed | failed)
      4. Print the RunStatus (with receipt when completed) and exit.

    Status semantics follow the contract: completed means the sandbox ran
    (test outcomes are inside the receipt — failing tests are NOT an exit
    code 1), failed means infrastructure crashed (error field, no receipt,
    exit code 1).
    """
    import httpx
    import time

    base = via_api.rstrip("/")
    headers: dict[str, str] = {}

    if not api_key:
        click.echo(f"Requesting demo token from {base}...", err=True)
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(f"{base}/v1/auth/demo-token")
            if resp.status_code != 200:
                click.echo(
                    f"Failed to obtain demo token: HTTP {resp.status_code}: {resp.text[:200]}",
                    err=True,
                )
                sys.exit(2)
            api_key = resp.json()["api_key"]
        except httpx.HTTPError as e:
            click.echo(f"Cannot reach control plane at {base}: {e}", err=True)
            sys.exit(2)

    headers["X-API-Key"] = api_key

    request_body: dict[str, Any] = {
        "repo_url": repo,
        "probe_groups": _internal_to_public_probe_groups(probe_groups),
        "config": {
            "timeout_seconds": timeout,
            "memory_mb": memory,
            "cpu_cores": cpu,
        },
    }
    if commit_sha:
        request_body["commit_sha"] = commit_sha
    if start_command:
        request_body["start_command"] = start_command
    if port is not None:
        request_body["port"] = port

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{base}/v1/runs", json=request_body, headers=headers)
            if resp.status_code != 200:
                detail = ""
                try:
                    detail = resp.json().get("detail", "")
                except ValueError:
                    detail = resp.text[:200]
                click.echo(
                    f"Run rejected: HTTP {resp.status_code}: {detail}",
                    err=True,
                )
                sys.exit(2)
            run = resp.json()
    except httpx.HTTPError as e:
        click.echo(f"Cannot submit run to {base}: {e}", err=True)
        sys.exit(2)

    run_id = run["run_id"]
    click.echo(f"Run submitted: {run_id} (status={run['status']})", err=True)

    # Poll until terminal. Polling interval grows: 0.5s -> 1s -> 2s,
    # capped, so short runs finish fast and long runs don't hammer the API.
    interval = 0.5
    while run["status"] in ("queued", "running"):
        time.sleep(interval)
        interval = min(interval * 2, 5.0)
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{base}/v1/runs/{run_id}", headers=headers)
                if resp.status_code != 200:
                    click.echo(
                        f"Status poll failed: HTTP {resp.status_code}: {resp.text[:200]}",
                        err=True,
                    )
                    sys.exit(2)
                run = resp.json()
        except httpx.HTTPError as e:
            click.echo(f"Cannot poll run status at {base}: {e}", err=True)
            sys.exit(2)

    click.echo(f"Run finished: status={run['status']}", err=True)

    if run["status"] == "failed":
        click.echo(f"Run failed: {run.get('error')}", err=True)
        sys.exit(1)

    receipt = run.get("receipt")
    if receipt is None:
        click.echo("Run completed but no receipt present in the response.", err=True)
        sys.exit(2)

    output_json = json.dumps(receipt, indent=2, sort_keys=True)
    if output_path:
        if len(output_json.encode("utf-8")) > MAX_OUTPUT_BYTES:
            click.echo(f"Output too large ({MAX_OUTPUT_BYTES} byte limit)", err=True)
            sys.exit(1)
        try:
            output_path.write_text(output_json, encoding="utf-8")
            click.echo(f"Report written to {output_path}", err=True)
        except OSError as e:
            click.echo(f"Failed to write report to {output_path}: {e}", err=True)
            sys.exit(1)
    else:
        click.echo(output_json)

    # completed means the sandbox ran to completion — test failures live
    # inside the receipt and do NOT affect the exit code (the contract's
    # status semantics: status reflects infrastructure, not test outcomes).
    sys.exit(0)


@cli.command()
@click.option("--receipt", "receipt_path", required=True, help="Path to receipt JSON file")
@click.option("--pubkey", default=None,
              help="Path to Ed25519 public key PEM file (not needed if receipt has key_id)")
@click.option("--fingerprint", default=None, help="Expected public key fingerprint (SHA-256 hex)")
@click.option("--control-plane", default=None,
              help="Control plane base URL for auto-fetching provisioned keys (default: env WORKFLO_AUTH_BASE_URL)")
def verify(receipt_path, pubkey, fingerprint, control_plane):
    """Verify a receipt's Ed25519 signature against a published public key.

    Backs Claim #4: "every run produces a signed, tamper-evident receipt."

    If the receipt contains a `key_id` (i.e. it was signed by a key
    provisioned via `workflo keygen --provision`), this command will
    auto-fetch the public key from the control plane and also check
    that the key is still active (not revoked). Use --pubkey to
    override and verify against a local PEM file instead.
    """

    # Read receipt with size limit to prevent DoS
    receipt_file = Path(receipt_path)
    try:
        receipt_text = _safe_read_text(receipt_file, MAX_RECEIPT_BYTES)
    except (OSError, UnicodeDecodeError) as e:
        click.echo(f"FAILED: cannot read receipt file: {e}", err=True)
        sys.exit(1)

    try:
        receipt_data = json.loads(receipt_text)
    except json.JSONDecodeError as e:
        click.echo(f"FAILED: receipt is not valid JSON: {e}", err=True)
        sys.exit(1)

    if not isinstance(receipt_data, dict):
        click.echo(f"FAILED: receipt root must be a JSON object, got {type(receipt_data).__name__}", err=True)
        sys.exit(1)

    receipt_dict = receipt_data.get("receipt", receipt_data)

    try:
        from workflo_schema.sandbox import SignedReceipt
        receipt = SignedReceipt(**receipt_dict)
    except Exception as e:
        click.echo(f"FAILED: receipt does not match schema: {e}", err=True)
        sys.exit(1)

    # Resolve public key: prefer auto-fetch by key_id (provenance), fall back to --pubkey
    public_key = None
    key_status = None
    key_metadata = {}

    if receipt.key_id and not pubkey:
        # Auto-fetch from control plane
        import httpx
        cp_base = (
            control_plane
            or os.environ.get("WORKFLO_AUTH_BASE_URL", "http://localhost:3001")
        ).rstrip("/")
        try:
            resp = httpx.get(
                f"{cp_base}/v1/auth/keys/{receipt.key_id}",
                timeout=10,
            )
        except httpx.HTTPError as e:
            click.echo(f"FAILED: cannot reach control plane: {e}", err=True)
            sys.exit(1)

        if resp.status_code == 404:
            click.echo(f"FAILED: key_id {receipt.key_id} not found in control plane directory", err=True)
            sys.exit(1)
        if resp.status_code != 200:
            click.echo(f"FAILED: control plane error (HTTP {resp.status_code}): {resp.text[:200]}", err=True)
            sys.exit(1)

        key_info = resp.json()
        key_status = key_info.get("status")
        key_metadata = {
            "device_id": key_info.get("device_id"),
            "user_id": key_info.get("user_id"),
            "organization_id": key_info.get("organization_id"),
            "provisioned_at": key_info.get("provisioned_at"),
        }

        if key_status == "revoked":
            click.echo(f"FAILED: signing key has been REVOKED (revoked_at={key_info.get('revoked_at')})", err=True)
            sys.exit(1)

        # Load PEM from response
        try:
            public_key = _load_ed25519_pubkey_from_string(key_info["public_key"])
        except Exception as e:
            click.echo(f"FAILED: control plane returned invalid public key: {e}", err=True)
            sys.exit(1)

        click.echo(f"Auto-fetched public key from control plane (key_id={receipt.key_id})", err=True)
    elif pubkey:
        # Explicit --pubkey override
        pubkey_file = Path(pubkey)
        try:
            public_key = _load_ed25519_pubkey(pubkey_file)
        except click.BadParameter as e:
            click.echo(f"FAILED: {e.message}", err=True)
            sys.exit(1)
    else:
        click.echo("FAILED: receipt has no key_id and --pubkey not provided", err=True)
        sys.exit(1)

    # Optional fingerprint check
    if fingerprint:
        from sandbox_isolation import fingerprint_public_key
        actual_fp = fingerprint_public_key(public_key)
        if actual_fp != fingerprint:
            click.echo(
                f"FAILED: fingerprint mismatch (expected {fingerprint}, got {actual_fp})",
                err=True,
            )
            sys.exit(1)

    if verify_receipt_signature(receipt, public_key):
        click.echo("VERIFIED: receipt signature is valid.")
        click.echo(f"  Sandbox ID: {receipt.sandbox_id}", err=True)
        click.echo(f"  Fingerprint: {receipt.public_key_fingerprint}", err=True)
        if receipt.key_id:
            click.echo(f"  Key ID: {receipt.key_id}", err=True)
            click.echo(f"  Key Status: {key_status or 'unknown'}", err=True)
            if key_metadata.get("device_id"):
                click.echo(f"  Device: {key_metadata['device_id']}", err=True)
            if key_metadata.get("user_id"):
                click.echo(f"  User: {key_metadata['user_id']}", err=True)
            if key_metadata.get("organization_id"):
                click.echo(f"  Organization: {key_metadata['organization_id']}", err=True)
            if key_metadata.get("provisioned_at"):
                click.echo(f"  Provisioned: {key_metadata['provisioned_at']}", err=True)
        sys.exit(0)
    else:
        click.echo("FAILED: receipt signature is INVALID or tampered.", err=True)
        sys.exit(1)


@cli.command()
@click.option("--output", "-o", default=None, help="Write the public key PEM to a file")
@click.option("--force", is_flag=True, help="Overwrite output file if it exists")
@click.option("--provision", is_flag=True, help="Register the public key with Cortex (provenance)")
@click.option("--device-id", default=None,
              help="Device identifier (default: hostname-based). Used for provenance tracking.")
def keygen(output, force, provision, device_id):
    """Generate a new Ed25519 keypair for receipt signing.

    Prints the public key PEM to stdout and the fingerprint to stderr.
    The private key is printed to stderr - capture it securely.

    With --provision: registers the public key with the Cortex control-plane
    (requires prior `workflo auth login`). The private key stays on this
    device; only the public key is sent. Once provisioned, receipts signed
    by this key carry a key_id that verifiers can look up to confirm the
    key belongs to a known, authenticated device/user.
    """

    signer = generate_keypair()

    public_pem = signer.public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    private_pem = signer.private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    # Optionally provision with Cortex for provenance
    provisioned_key_id = None
    if provision:
        import platform as _platform
        import socket as _socket
        import uuid as _uuid
        import httpx

        # Use provided device_id or generate one based on hostname
        resolved_device_id = device_id or f"{_socket.gethostname()}-{_uuid.uuid4().hex[:8]}"

        # Check auth status — must be logged in
        try:
            from cortex_auth.session import AuthSession
            from cortex_auth.scopes import WORKFLO_SCOPES, PRODUCT_CLIENT_IDS
            auth = AuthSession(
                product="workflo",
                client_id=PRODUCT_CLIENT_IDS["workflo"],
                base_url=os.environ.get("WORKFLO_AUTH_BASE_URL", "http://localhost:3001"),
                scopes=WORKFLO_SCOPES,
            )
            access_token = auth.get_access_token()
        except Exception as e:
            click.echo(f"FAILED: --provision requires authentication. Run `workflo auth login` first. ({e})", err=True)
            sys.exit(1)

        # POST to provisioning endpoint
        base_url = os.environ.get("WORKFLO_AUTH_BASE_URL", "http://localhost:3001").rstrip("/")
        try:
            resp = httpx.post(
                f"{base_url}/v1/auth/keys/provision",
                json={"public_key": public_pem, "device_id": resolved_device_id},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
        except httpx.HTTPError as e:
            click.echo(f"FAILED: cannot reach control plane: {e}", err=True)
            sys.exit(1)

        if resp.status_code != 200:
            click.echo(f"FAILED: provisioning rejected (HTTP {resp.status_code}): {resp.text[:200]}", err=True)
            sys.exit(1)

        provisioned_key_id = resp.json()["key_id"]
        click.echo(f"Key provisioned: {provisioned_key_id} (device: {resolved_device_id})", err=True)
        click.echo(f"  Fingerprint: {resp.json()['fingerprint']}", err=True)

    if output:
        output_path = Path(output).resolve()
        if not force and output_path.exists():
            if not click.confirm(
                f"File {output_path} already exists. Overwrite?", default=False
            ):
                raise click.Abort()
        try:
            # Write public key + (if provisioned) the key_id as a sidecar file
            output_path.write_text(public_pem, encoding="utf-8")
            click.echo(f"Public key written to {output_path}", err=True)
            if provisioned_key_id:
                key_id_path = output_path.with_suffix(output_path.suffix + ".keyid")
                key_id_path.write_text(provisioned_key_id, encoding="utf-8")
                click.echo(f"Key ID written to {key_id_path}", err=True)
        except OSError as e:
            click.echo(f"Failed to write public key: {e}", err=True)
            sys.exit(1)
    else:
        click.echo(public_pem)

    click.echo(f"Fingerprint: {signer.public_key_fingerprint}", err=True)
    if not provision:
        click.echo(
            "Note: This key is local-only. Use --provision to register it with Cortex "
            "for receipt provenance (requires `workflo auth login`).",
            err=True,
        )
    click.echo("Private key (keep secret!):", err=True)
    click.echo(private_pem, err=True)


if __name__ == "__main__":
    cli()