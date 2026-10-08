"""Envelope encryption tests (SOC 2 CC6.7/CC6.8).

Covers the crypto module (format, round-trip, tamper, rotation) and the
credential paths wired onto it (signup/login passwords, API keys,
OAuth token hashes) with the KEK both configured and unconfigured.
"""

import asyncio

import pytest
from sqlalchemy import select

from app.core import envelope
from app.core.config import settings
from app.db import database
from app.db.models import ApiKey, OAuthToken, User

DEV_KEK = "aa" * 32  # 32-byte dev KEK, hex


@pytest.fixture
def kek_on(monkeypatch):
    """Enable envelope encryption with a static dev KEK for one test."""
    monkeypatch.setattr(settings, "master_kek_hex", DEV_KEK)
    envelope.reset_provider()
    yield
    envelope.reset_provider()


def _run(coro):
    return asyncio.run(coro)


def _db_query(model, **filters):
    async def _go():
        async with database.async_session_factory() as s:
            stmt = select(model)
            for k, v in filters.items():
                stmt = stmt.where(getattr(model, k) == v)
            return list((await s.execute(stmt)).scalars())

    return _run(_go())


class TestEnvelopeModule:
    def test_disabled_passthrough(self, monkeypatch):
        """Zero-config dev: no KEK configured -> plaintext pass-through."""
        monkeypatch.setattr(settings, "master_kek_hex", "")
        envelope.reset_provider()
        assert envelope.is_enabled() is False

        async def _go():
            async with database.async_session_factory() as s:
                stored = await envelope.protect(s, "org-x", "salt:hash")
                assert stored == "salt:hash"
                assert await envelope.reveal(s, "org-x", stored) == "salt:hash"

        _run(_go())

    def test_round_trip_and_format(self, kek_on):
        async def _go():
            async with database.async_session_factory() as s:
                stored = await envelope.protect(s, "org-a", "deadbeef:0123")
                assert stored.startswith("wfenc1:v1:")
                assert "deadbeef" not in stored
                assert await envelope.reveal(s, "org-a", stored) == "deadbeef:0123"
                # A second encryption differs (random nonce) — nondeterministic
                stored2 = await envelope.protect(s, "org-a", "deadbeef:0123")
                assert stored2 != stored
                assert await envelope.reveal(s, "org-a", stored2) == "deadbeef:0123"

        _run(_go())

    def test_tampered_ciphertext_fails(self, kek_on):
        async def _go():
            async with database.async_session_factory() as s:
                stored = await envelope.protect(s, "org-a", "victim")
                prefix, nonce, ct = stored.rsplit(":", 2) if stored.count(":") == 3 else stored.split(":", 3)
                # Flip the last base64 char of the ciphertext
                bad = stored[:-2] + ("AA" if not stored.endswith("AA") else "BB")
                with pytest.raises(envelope.EnvelopeError):
                    await envelope.reveal(s, "org-a", bad)

        _run(_go())

    def test_tenant_blast_radius_other_org_cannot_decrypt(self, kek_on):
        """A ciphertext sealed for org-a must not open under org-b's DEK."""
        async def _go():
            async with database.async_session_factory() as s:
                stored = await envelope.protect(s, "org-a", "secret-hash")
                with pytest.raises(envelope.EnvelopeError):
                    await envelope.reveal(s, "org-b", stored)

        _run(_go())

    def test_key_rotation_keeps_old_rows_readable(self, kek_on):
        from app.db.models import OrgDataKey
        from app.core.crypto import utc_now

        async def _go():
            async with database.async_session_factory() as s:
                v1_ct = await envelope.protect(s, "org-a", "old-hash")
                # Rotate: retire v1, next protect() creates v2
                k1 = (await s.execute(
                    select(OrgDataKey).where(OrgDataKey.org_id == "org-a"))
                ).scalar_one()
                k1.status = "retired"
                k1.retired_at = utc_now()
                await s.flush()
                v2_ct = await envelope.protect(s, "org-a", "new-hash")
                assert v2_ct.startswith("wfenc1:v2:")
                # Old row still decrypts via the retired DEK
                assert await envelope.reveal(s, "org-a", v1_ct) == "old-hash"
                assert await envelope.reveal(s, "org-a", v2_ct) == "new-hash"

        _run(_go())


class TestCredentialSealing:
    def test_signup_seals_password_hash_and_login_still_works(self, client, kek_on):
        resp = client.post(
            "/v1/auth/signup",
            data={"email": "sealed@example.com", "password": "pw-12345"},
        )
        assert resp.status_code == 200, resp.text

        users = _db_query(User, email="sealed@example.com")
        assert len(users) == 1
        # On disk: sealed, not a raw argon2 hash
        assert users[0].password_hash.startswith("wfenc1:")
        assert users[0].password_hash.count("$") == 0  # argon2 params not exposed

        login = client.post(
            "/v1/auth/login",
            data={"email": "sealed@example.com", "password": "pw-12345"},
        )
        assert login.status_code == 200, login.text
        assert "access_token" in login.json()

        # Wrong password still fails against the sealed hash
        bad = client.post(
            "/v1/auth/login",
            data={"email": "sealed@example.com", "password": "wrong"},
        )
        assert bad.status_code == 400

    def test_api_key_sealed_and_validates(self, client, kek_on):
        resp = client.post("/v1/keys", json={"label": "sealed-key"})
        assert resp.status_code == 200, resp.text
        raw = resp.json()["raw_key"]

        records = _db_query(ApiKey, label="sealed-key")
        assert records and records[0].key_hash.startswith("wfenc1:")

        # The sealed key authenticates requests end-to-end
        runs = client.get("/v1/runs", headers={"X-API-Key": raw})
        assert runs.status_code == 200

    def test_oauth_tokens_sealed_at_rest(self, client, kek_on):
        client.post(
            "/v1/auth/signup",
            data={"email": "tok@example.com", "password": "pw-12345"},
        )
        client.post(
            "/v1/auth/login",
            data={"email": "tok@example.com", "password": "pw-12345"},
        )
        tokens = _db_query(OAuthToken)
        assert tokens, "login must mint a token"
        assert all(t.access_token_hash.startswith("wfenc1:") for t in tokens)
        assert all(t.refresh_token_hash.startswith("wfenc1:") for t in tokens)

    def test_refresh_round_trip_with_sealed_hashes(self, client, kek_on):
        client.post(
            "/v1/auth/signup",
            data={"email": "rt@example.com", "password": "pw-12345"},
        )
        login = client.post(
            "/v1/auth/login",
            data={"email": "rt@example.com", "password": "pw-12345"},
        )
        refresh = login.json()["refresh_token"]
        resp = client.post(
            "/v1/auth/token/refresh",
            data={"grant_type": "refresh_token",
                  "refresh_token": refresh,
                  "client_id": "workflo_cli"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["access_token"]

    def test_legacy_plaintext_hash_verifies_with_encryption_on(self, client, kek_on):
        """Migration path: rows written before encryption was enabled still
        authenticate (reveal passes non-prefixed values through)."""
        import asyncio
        from app.core.crypto import hash_api_key
        from app.db.models import Organization, Project

        raw_key = "wfl_legacy_" + "0" * 32

        async def _go():
            async with database.async_session_factory() as s:
                org = Organization(name="Legacy Org")
                s.add(org)
                await s.flush()
                proj = Project(org_id=org.id, name="Legacy Proj")
                s.add(proj)
                await s.flush()
                s.add(ApiKey(project_id=proj.id,
                             key_hash=hash_api_key(raw_key),  # PLAINTEXT (legacy)
                             label="legacy",
                             scopes=["run_tests", "admin"]))
                await s.commit()

        asyncio.run(_go())
        resp = client.get("/v1/runs", headers={"X-API-Key": raw_key})
        assert resp.status_code == 200
