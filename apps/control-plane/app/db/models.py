"""ORM models for the Tenant Shield Control Plane."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Integer, Float, Text, DateTime, ForeignKey, JSON, Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    # Naive UTC — see app.core.crypto.utc_now for why (SQLite round-trip).
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan_tier: Mapped[str] = mapped_column(String(50), default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    projects: Mapped[list["Project"]] = relationship(back_populates="org", cascade="all, delete-orphan")
    users: Mapped[list["User"]] = relationship(back_populates="org")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)

    org: Mapped["Organization"] = relationship(back_populates="projects")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    devices: Mapped[list["Device"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    runs: Mapped[list["TestRun"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    scopes: Mapped[dict] = mapped_column(JSON, default=list)
    last_used: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped["Project"] = relationship(back_populates="api_keys")


class Device(Base):
    """A registered device (e.g. a CI runner / developer machine) that runs
    sandboxed test runs on behalf of a project.

    The demo-token flow (POST /v1/auth/demo-token) registers a device
    bound to the demo project. Real OAuth device flows are on the
    roadmap; this model is the frozen skeleton the future flow fills in.
    """

    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), default="")
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped["Project"] = relationship(back_populates="devices")


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    goal: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="queued")
    spec_json: Mapped[dict] = mapped_column(JSON, default=dict)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    logs: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="runs")
    results: Mapped[list["TestResultRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class TestResultRecord(Base):
    __tablename__ = "test_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id", ondelete="CASCADE"))
    nodeid: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    markers: Mapped[dict] = mapped_column(JSON, default=list)
    soc2_controls: Mapped[dict] = mapped_column(JSON, default=list)
    assertion: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped["TestRun"] = relationship(back_populates="results")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    run: Mapped["TestRun"] = relationship(back_populates="artifacts")


class DeviceCode(Base):
    """OAuth 2.0 Device Authorization Grant (RFC 8628) — device code.

    Created when a CLI requests a device code. The user authorizes it via
    the verification URI, then the CLI polls /device/token to exchange the
    device_code for tokens. ``user_id`` is bound at approval time (POST
    /device, which requires an authenticated browser session) — the device
    code carries no identity before then.
    """

    __tablename__ = "device_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_code: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    user_code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    client_id: Mapped[str] = mapped_column(String(100), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    token_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # FK to OAuthToken after auth
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    user: Mapped["User | None"] = relationship(back_populates="device_codes")


class OAuthToken(Base):
    """OAuth access/refresh token pair for a user+client combination."""

    __tablename__ = "oauth_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    client_id: Mapped[str] = mapped_column(String(100), nullable=False)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    access_token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    access_token_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    refresh_token_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    user: Mapped["User"] = relationship(back_populates="oauth_tokens")

    # Index for token lookup by refresh token hash
    __table_args__ = ()


class ProvisionedKey(Base):
    """A registered Ed25519 public key for receipt provenance.

    When a CLI user runs `workflo keygen --provision`, their local keypair
    stays on their device; only the public key is sent to Cortex. The
    private key signs receipts locally. The `key_id` is embedded in the
    receipt, so verifiers can fetch the public key from this table to
    verify the signature AND check that the key was provisioned by a
    known, authenticated device/user.

    This enables the authenticity/provenance guarantee: a receipt signed
    by a key registered to a specific device + user + org is traceable,
    not just internally consistent.
    """

    __tablename__ = "provisioned_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    public_key: Mapped[str] = mapped_column(String(2048), nullable=False)  # PEM-encoded
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)  # SHA-256 hex
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)  # unique per device
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    provisioned_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | revoked

    user: Mapped["User"] = relationship(back_populates="provisioned_keys")

    __table_args__ = (
        # One key per (device, fingerprint) — prevents double-registration
        {"sqlite_autoincrement": False},
    )


class User(Base):
    """A registered user account with email + password hash.

    Linked to an Organization. Owns OAuth tokens and provisioned keys.
    ``project_id`` is the user's own default workspace (created at signup) —
    per-user project ownership, so users never share a workspace.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)  # argon2id hash
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"))
    project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    org: Mapped["Organization | None"] = relationship(back_populates="users")
    project: Mapped["Project | None"] = relationship()
    oauth_tokens: Mapped[list["OAuthToken"]] = relationship(back_populates="user")
    provisioned_keys: Mapped[list["ProvisionedKey"]] = relationship(back_populates="user")
    device_codes: Mapped[list["DeviceCode"]] = relationship(back_populates="user")
