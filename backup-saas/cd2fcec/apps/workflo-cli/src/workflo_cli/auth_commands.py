"""Auth commands for workflo CLI: login, logout, auth status, profile/org/workspace management."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

import click

from cortex_auth.session import AuthSession, AuthError, LoginResult
from cortex_auth.profile import DEFAULT_CONFIG_DIR
from cortex_auth.scopes import WORKFLO_SCOPES, PRODUCT_CLIENT_IDS


# Local-first default: the auth site is served by the local control plane on
# :3001 (spawned on demand by `workflo auth login`). The real hosted
# endpoint (https://auth.cortex.dev) is a later rollout; WORKFLO_AUTH_BASE_URL
# overrides either way.
DEFAULT_BASE_URL = os.environ.get("WORKFLO_AUTH_BASE_URL", "http://localhost:3001")


def _server_up(base_url: str) -> bool:
    """Return True if the control plane's health endpoint responds 200."""
    url = f"{base_url.rstrip('/')}/v1/health"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def _find_control_plane_dir() -> Optional[Path]:
    """Locate the control-plane app dir (repo layout or WORKFLO_CP_APP_DIR)."""
    override = os.environ.get("WORKFLO_CP_APP_DIR")
    if override:
        candidate = Path(override)
        if (candidate / "app" / "main.py").exists():
            return candidate
        return None
    # Repo layout: <repo>/apps/control-plane — four levels above this file.
    repo_root = Path(__file__).resolve().parents[4]
    candidate = repo_root / "apps" / "control-plane"
    if (candidate / "app" / "main.py").exists():
        return candidate
    return None


def _ensure_local_server(base_url: str) -> Optional[subprocess.Popen]:
    """Spawn the control plane if the default local server is not running.

    Returns the child process (to be terminated after login) or None when
    no spawn happened (server already up, or non-local base URL, or the
    control plane is not installed locally).
    """
    if not (base_url.startswith("http://localhost") or base_url.startswith("http://127.0.0.1")):
        return None
    if _server_up(base_url):
        return None
    cp_dir = _find_control_plane_dir()
    if cp_dir is None:
        return None
    db_dir = Path(DEFAULT_CONFIG_DIR).expanduser() / "cortex"
    db_dir.mkdir(parents=True, exist_ok=True)
    env = dict(
        os.environ,
        DATABASE_URL=f"sqlite+aiosqlite:///{(db_dir / 'local-cp.db').as_posix()}",
    )
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            str(cp_dir),
            "--host",
            "127.0.0.1",
            "--port",
            "3001",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        if _server_up(base_url):
            return proc
        time.sleep(0.25)
    proc.terminate()
    return None


def _get_session() -> AuthSession:
    """Create an AuthSession for the workflo product."""
    return AuthSession(
        product="workflo",
        client_id=PRODUCT_CLIENT_IDS["workflo"],
        base_url=DEFAULT_BASE_URL,
        scopes=WORKFLO_SCOPES,
    )


def _print_login_result(result: LoginResult) -> None:
    """Print a consistent login success message."""
    click.echo(f"Logged in as {result.session.email} ({result.session.organization_name})", err=True)
    click.echo(f"Profile: {result.profile.name}", err=True)
    click.echo(f"Credential store: {result.backend_name}", err=True)
    if result.session.workspace_name:
        click.echo(f"Workspace: {result.session.workspace_name}", err=True)


@click.group("auth")
def auth_group():
    """Authentication and profile management commands."""
    pass


@auth_group.command("login")
@click.option("--profile", "-p", default="default", help="Profile name (default: 'default')")
@click.option("--no-browser", is_flag=True, help="Print the device code URL instead of opening the browser")
@click.option("--keep-server", is_flag=True, help="Keep the spawned local auth server running after login")
@click.option("--service-token", help="Use a pre-existing service token (CI/CD) instead of device flow")
@click.option("--workspace-id", help="Workspace ID for service token login (required with --service-token)")
@click.option("--scopes", help="Comma-separated scopes for service token (default: workflo scopes)")
def login(profile: str, no_browser: bool, keep_server: bool, service_token: Optional[str], workspace_id: Optional[str], scopes: Optional[str]):
    """Authenticate via device flow or service token.

    Device flow (default):
      1. Requests a device code from the Cortex auth server
      2. Opens the verification URL in your browser (unless --no-browser)
      3. Polls for the token grant once you approve

    The local auth server (:3001) is spawned on demand if it isn't running;
    it is stopped when login completes unless --keep-server is given.

    Service token (CI/CD):
      Provide --service-token and --workspace-id to create a profile
      from a workspace-scoped service token (never expires until revoked).
    """
    session = _get_session()

    if service_token:
        if not workspace_id:
            raise click.UsageError("--workspace-id is required when using --service-token")
        scope_list = [s.strip() for s in scopes.split(",")] if scopes else WORKFLO_SCOPES
        try:
            result = session.login_with_service_token(
                profile_name=profile,
                token=service_token,
                workspace_id=workspace_id,
                scopes=scope_list,
            )
            _print_login_result(result)
        except AuthError as e:
            raise click.ClickException(str(e))
        return

    # Device flow — spawn the local auth server if needed (identity binding
    # happens against the local control plane for the default endpoint).
    spawned = _ensure_local_server(session.base_url)
    try:
        result = session.login(
            profile_name=profile,
            open_browser=not no_browser,
            poll_callback=lambda dc: click.echo(f"Waiting for approval... (user code: {dc.user_code})", err=True),
        )
        _print_login_result(result)
    except AuthError as e:
        raise click.ClickException(str(e))
    finally:
        if spawned is not None and not keep_server:
            spawned.terminate()


@auth_group.command("logout")
@click.option("--profile", "-p", default=None, help="Profile to logout (default: active profile)")
def logout(profile: Optional[str]):
    """Log out and revoke tokens for the active (or specified) profile."""
    session = _get_session()

    if profile:
        # Temporarily switch to the target profile to logout
        session.switch_profile(profile)

    try:
        session.logout()
        click.echo("Logged out", err=True)
    except AuthError as e:
        raise click.ClickException(str(e))


@auth_group.command("status")
def auth_status():
    """Show the current authentication status."""
    session = _get_session()

    try:
        status = session.status()
    except AuthError as e:
        raise click.ClickException(str(e))

    if status is None:
        click.echo("Not logged in. Run `workflo auth login` to authenticate.", err=True)
        return

    click.echo(f"Authenticated: Yes")
    click.echo(f"  Email: {status.email}")
    click.echo(f"  User ID: {status.user_id}")
    click.echo(f"  Organization: {status.organization_name} ({status.organization_id})")
    click.echo(f"  Workspace: {status.workspace_name} ({status.workspace_id})")
    click.echo(f"  Product: {status.product}")
    click.echo(f"  Scopes: {', '.join(status.scopes)}")
    click.echo(f"  Token valid: {'Yes' if status.is_access_token_valid() else 'No (will refresh on use)'}")
    click.echo(f"  Service token: {'Yes' if status.is_service_token else 'No'}")


@auth_group.command("list")
def auth_list():
    """List all configured profiles."""
    session = _get_session()

    try:
        profiles = session.list_profiles()
    except AuthError as e:
        raise click.ClickException(str(e))

    if not profiles:
        click.echo("No profiles configured. Run `workflo auth login` to create one.", err=True)
        return

    active_name = session._profiles.get_active_profile_name()
    for p in profiles:
        marker = " * " if p.name == active_name else "   "
        org = p.organization_name or p.active_organization_id or "no org"
        ws = p.workspace_name or p.active_workspace_id or "no workspace"
        svc = " (service token)" if p.is_service_token else ""
        click.echo(f"{marker}{p.name}: {p.email or 'unknown'} @ {org} / {ws}{svc}")


@auth_group.command("switch")
@click.argument("profile_name")
def auth_switch(profile_name: str):
    """Switch the active profile."""
    session = _get_session()

    try:
        session.switch_profile(profile_name)
        click.echo(f"Switched to profile: {profile_name}", err=True)
    except AuthError as e:
        raise click.ClickException(str(e))


# Organization commands
@click.group("org")
def org_group():
    """Organization management commands."""
    pass


@org_group.command("list")
def org_list():
    """List organizations available to the active profile."""
    session = _get_session()

    try:
        profile = session._profiles.get_active_profile()
    except AuthError as e:
        raise click.ClickException(str(e))

    if profile is None:
        raise click.ClickException("Not logged in. Run `workflo auth login` first.")

    click.echo(f"Active organization: {profile.organization_name or profile.active_organization_id or 'none'}")
    click.echo("(Use `workflo auth status` to see full details)")
    # Note: Full org listing would require an API call to the backend.
    # The CLI stores only the active org; listing all orgs needs server round-trip.


@org_group.command("use")
@click.argument("org_id")
@click.option("--name", help="Organization display name (optional)")
def org_use(org_id: str, name: Optional[str]):
    """Set the active organization for the current profile."""
    session = _get_session()

    try:
        session.set_active_org(org_id, org_name=name)
        click.echo(f"Active organization set to: {org_id}" + (f" ({name})" if name else ""), err=True)
    except AuthError as e:
        raise click.ClickException(str(e))


# Workspace commands
@click.group("workspace")
def workspace_group():
    """Workspace management commands."""
    pass


@workspace_group.command("list")
def workspace_list():
    """List workspaces available to the active profile."""
    session = _get_session()

    try:
        profile = session._profiles.get_active_profile()
    except AuthError as e:
        raise click.ClickException(str(e))

    if profile is None:
        raise click.ClickException("Not logged in. Run `workflo auth login` first.")

    click.echo(f"Active workspace: {profile.workspace_name or profile.active_workspace_id or 'none'}")
    click.echo("(Use `workflo auth status` to see full details)")
    # Note: Full workspace listing would require an API call to the backend.


@workspace_group.command("use")
@click.argument("workspace_id")
@click.option("--name", help="Workspace display name (optional)")
def workspace_use(workspace_id: str, name: Optional[str]):
    """Set the active workspace for the current profile."""
    session = _get_session()

    try:
        session.set_active_workspace(workspace_id, workspace_name=name)
        click.echo(f"Active workspace set to: {workspace_id}" + (f" ({name})" if name else ""), err=True)
    except AuthError as e:
        raise click.ClickException(str(e))


# Also add a top-level `login` command as an alias for `auth login`
@click.command()
@click.option("--profile", "-p", default="default", help="Profile name (default: 'default')")
@click.option("--no-browser", is_flag=True, help="Print the device code URL instead of opening the browser")
@click.option("--keep-server", is_flag=True, help="Keep the spawned local auth server running after login")
@click.option("--service-token", help="Use a pre-existing service token (CI/CD) instead of device flow")
@click.option("--workspace-id", help="Workspace ID for service token login (required with --service-token)")
@click.option("--scopes", help="Comma-separated scopes for service token (default: workflo scopes)")
def login_alias(profile: str, no_browser: bool, keep_server: bool, service_token: Optional[str], workspace_id: Optional[str], scopes: Optional[str]):
    """Authenticate via device flow or service token (alias for `workflo auth login`)."""
    ctx = click.get_current_context()
    ctx.invoke(login, profile=profile, no_browser=no_browser, keep_server=keep_server, service_token=service_token, workspace_id=workspace_id, scopes=scopes)


# Also add a top-level `logout` command as an alias
@click.command()
@click.option("--profile", "-p", default=None, help="Profile to logout (default: active profile)")
def logout_alias(profile: Optional[str]):
    """Log out and revoke tokens (alias for `workflo auth logout`)."""
    ctx = click.get_current_context()
    ctx.invoke(logout, profile=profile)